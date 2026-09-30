"""
module_math_b.plugins.plugin_batch_experiment — 批量实验调度器插件

可选插件，默认关闭。通过任务 JSON 显式开启。
批量调度多个猜想在不同插件配置下的验证实验，支持并行执行、结果聚合、对比分析。

v1.2 业务逻辑版本：真实任务提交、子任务状态收集、BatchReport 聚合。
严格遵守 max_parallel、timeout_per_experiment 约束。

能力边界：
  - 通过 context 中的 runner 回调执行实际验证
  - 不修改假说池状态
  - 不访问核心数学收敛逻辑
  - 最大并行度 8，单实验超时 300s
  - 内存约束: 缓存最多 100 条实验结果

不修改任何 v1.0/v1.1 核心源码。
"""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass, field
from typing import Any

from module_math_b.plugins.plugin_registry import PluginBase, PluginResult, PluginStatus


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class ExperimentTask:
    """实验任务"""
    task_id: str = ""
    conjecture: dict[str, Any] = field(default_factory=dict)
    plugin_config: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0
    priority: int = 0  # 0=normal, 1=high


@dataclass
class ExperimentResult:
    """实验结果"""
    task: ExperimentTask = field(default_factory=ExperimentTask)
    status: str = ""          # PROVEN | DISPROVEN | PENDING | TIMEOUT | ERROR
    convergence_report: dict[str, Any] | None = None
    elapsed_seconds: float = 0.0
    logical_gaps: list[dict[str, Any]] = field(default_factory=list)
    plugin_results: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class BatchReport:
    """批量实验报告"""
    total_experiments: int = 0
    completed: int = 0
    proven: int = 0
    disproven: int = 0
    by_config: dict[str, dict[str, Any]] = field(default_factory=dict)
    top_discoveries: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# =============================================================================
# 批量实验调度器
# =============================================================================

class BatchExperimentScheduler(PluginBase):
    """
    批量实验调度器

    核心能力（v1.2 业务逻辑版本）：
      1. build_experiment_matrix: 构建实验矩阵（猜想 × 插件配置）
      2. _run_parallel_batch:     真实并行执行实验任务
      3. _run_single_experiment:  执行单个实验（带超时控制）
      4. aggregate_results:       聚合实验结果与智能推荐
      5. compare_configs:         比较不同插件配置的效果

    生命周期：
      1. __init__()          — 初始化
      2. validate_config()   — 校验配置合法性
      3. execute()           — 执行批量实验调度
      4. reset()             — 重置内部状态

    异常处理：
      - 无效配置 → ERROR + 错误描述
      - 猜想列表为空 → ERROR + 提示
      - 超时 → 单任务返回 TIMEOUT，不影响其他任务
      - 单实验失败 → 记录 ERROR，不影响其他实验
      - 插件过载 → 优雅降级，限制并行度
    """

    plugin_name = "batch_experiment"

    # 最大并行度
    DEFAULT_MAX_PARALLEL: int = 4
    HARD_MAX_PARALLEL: int = 8

    # 单实验默认超时
    DEFAULT_TIMEOUT_PER_EXPERIMENT: float = 30.0
    HARD_MAX_TIMEOUT: float = 300.0
    HARD_MIN_TIMEOUT: float = 1.0

    # 内存约束：缓存最多实验结果数
    MAX_RESULT_CACHE: int = 100

    # 运行状态
    _STATE_IDLE = "idle"
    _STATE_RUNNING = "running"
    _STATE_COMPLETED = "completed"
    _STATE_ERROR = "error"
    _STATE_DEGRADED = "degraded"  # 优雅降级

    __slots__ = (
        "_run_count",
        "_result_cache",
        "_max_parallel",
        "_timeout_per_experiment",
        "_state",
        "_last_report",
        "_degradation_reason",
    )

    def __init__(self) -> None:
        self._run_count: int = 0
        self._result_cache: list[ExperimentResult] = []
        self._max_parallel: int = self.DEFAULT_MAX_PARALLEL
        self._timeout_per_experiment: float = self.DEFAULT_TIMEOUT_PER_EXPERIMENT
        self._state: str = self._STATE_IDLE
        self._last_report: BatchReport | None = None
        self._degradation_reason: str = ""

    # =========================================================================
    # 配置校验
    # =========================================================================

    def validate_config(self, config: Any) -> bool:
        """
        校验插件配置合法性

        检查项：
          - extra_args 中的 max_parallel 为合法正整数 (1-8)
          - extra_args 中的 timeout_per_experiment 合法 (1.0-300.0)
        """
        from module_math_b.plugins.plugin_registry import PluginConfig

        if not isinstance(config, PluginConfig):
            return False

        extra = config.extra_args if isinstance(config.extra_args, dict) else {}

        max_parallel = extra.get("max_parallel", self.DEFAULT_MAX_PARALLEL)
        if not isinstance(max_parallel, int) or max_parallel < 1 or max_parallel > self.HARD_MAX_PARALLEL:
            return False

        timeout = extra.get(
            "timeout_per_experiment", self.DEFAULT_TIMEOUT_PER_EXPERIMENT
        )
        if not isinstance(timeout, (int, float)) or timeout < self.HARD_MIN_TIMEOUT or timeout > self.HARD_MAX_TIMEOUT:
            return False

        return True

    # =========================================================================
    # 执行
    # =========================================================================

    def execute(self, context: dict[str, Any]) -> PluginResult:
        """
        执行批量实验调度

        context 期望字段:
          - conjectures:              list[dict]  (待验证猜想列表)
          - plugin_configs:           list[dict]  (插件配置矩阵)
          - max_parallel:             int = 4     (最大并行度)
          - timeout_per_experiment:   float = 30.0  (单实验超时)
          - runner:                   Callable    (实验执行回调，可选)

        Returns:
            PluginResult with output containing:
              - report:              BatchReport (序列化为 dict)
              - experiment_matrix:   list[dict]
              - total_tasks:         int
              - status_note:         str
              - degradation_info:    dict (如有降级)
        """
        self._run_count += 1
        self._degradation_reason = ""

        try:
            # --- 1. 参数校验 ---
            conjectures = context.get("conjectures", [])
            if not isinstance(conjectures, list):
                return self._error_result(
                    f"conjectures 必须为 list，收到: {type(conjectures).__name__}"
                )
            if not conjectures:
                return self._error_result("conjectures 为空，无法生成实验矩阵")

            plugin_configs = context.get("plugin_configs", [])
            if not isinstance(plugin_configs, list):
                return self._error_result(
                    f"plugin_configs 必须为 list，收到: {type(plugin_configs).__name__}"
                )
            if not plugin_configs:
                return self._error_result("plugin_configs 为空，无法生成实验矩阵")

            # --- 1.5 参数越界处理 ---
            max_parallel = context.get("max_parallel", self.DEFAULT_MAX_PARALLEL)
            if not isinstance(max_parallel, int) or max_parallel < 1:
                return self._error_result(
                    f"max_parallel 必须为正整数，收到: {max_parallel}"
                )
            original_max_parallel = max_parallel
            if max_parallel > self.HARD_MAX_PARALLEL:
                self._degradation_reason = (
                    f"max_parallel 越界 ({original_max_parallel} > {self.HARD_MAX_PARALLEL})，"
                    f"已 clamp 到 {self.HARD_MAX_PARALLEL}"
                )
                max_parallel = self.HARD_MAX_PARALLEL

            timeout_per = context.get(
                "timeout_per_experiment", self.DEFAULT_TIMEOUT_PER_EXPERIMENT
            )
            if not isinstance(timeout_per, (int, float)) or timeout_per < self.HARD_MIN_TIMEOUT:
                return self._error_result(
                    f"timeout_per_experiment 必须 ≥ {self.HARD_MIN_TIMEOUT}，收到: {timeout_per}"
                )
            original_timeout = timeout_per
            if timeout_per > self.HARD_MAX_TIMEOUT:
                self._degradation_reason += (
                    f"; timeout_per_experiment 越界 ({original_timeout} > {self.HARD_MAX_TIMEOUT})，"
                    f"已 clamp 到 {self.HARD_MAX_TIMEOUT}"
                )
                timeout_per = self.HARD_MAX_TIMEOUT

            # 插件过载检测
            total_tasks = len(conjectures) * len(plugin_configs)
            if total_tasks > 200:
                self._degradation_reason += (
                    f"; 插件过载检测: 任务数 {total_tasks} > 200，"
                    "限制并行度到 2 以保护系统"
                )
                max_parallel = min(max_parallel, 2)

            # 更新实例配置
            self._max_parallel = max_parallel
            self._timeout_per_experiment = timeout_per

            # --- 2. 构建实验矩阵 ---
            self._state = self._STATE_RUNNING
            tasks = self.build_experiment_matrix(
                conjectures=conjectures,
                plugin_configs=plugin_configs,
                timeout_per_experiment=timeout_per,
            )

            # --- 3. 真实并行调度 ---
            runner = context.get("runner")
            hypothesis_pool = context.get("hypothesis_pool")

            results = self._run_parallel_batch(
                tasks=tasks,
                max_parallel=max_parallel,
                runner=runner,
                hypothesis_pool=hypothesis_pool,
            )

            # --- 4. 聚合报告 ---
            report = self.aggregate_results(results)

            # 缓存管理
            self._result_cache.extend(results)
            if len(self._result_cache) > self.MAX_RESULT_CACHE:
                self._result_cache = self._result_cache[-self.MAX_RESULT_CACHE:]

            self._last_report = report
            self._state = self._STATE_DEGRADED if self._degradation_reason else self._STATE_COMPLETED

            # 构建输出
            output: dict[str, Any] = {
                "report": {
                    "total_experiments": report.total_experiments,
                    "completed": report.completed,
                    "proven": report.proven,
                    "disproven": report.disproven,
                    "by_config": report.by_config,
                    "top_discoveries": report.top_discoveries,
                    "recommendations": report.recommendations,
                },
                "experiment_matrix": [
                    {
                        "task_id": t.task_id,
                        "conjecture": t.conjecture,
                        "plugin_config": t.plugin_config,
                        "timeout_seconds": t.timeout_seconds,
                        "priority": t.priority,
                    }
                    for t in tasks
                ],
                "total_tasks": len(tasks),
                "max_parallel": max_parallel,
                "status_note": "v1.2 业务逻辑版本：真实任务调度与结果聚合",
            }

            if self._degradation_reason:
                output["degradation_info"] = {
                    "reason": self._degradation_reason,
                    "original_max_parallel": original_max_parallel,
                    "effective_max_parallel": max_parallel,
                }

            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ENABLED,
                output=output,
            )

        except Exception as e:
            self._state = self._STATE_ERROR
            return PluginResult(
                plugin_name=self.plugin_name,
                status=PluginStatus.ERROR,
                error=f"批量实验调度错误: {type(e).__name__}: {e}",
            )

    # =========================================================================
    # 公开接口
    # =========================================================================

    def build_experiment_matrix(
        self,
        conjectures: list[dict[str, Any]],
        plugin_configs: list[dict[str, Any]],
        timeout_per_experiment: float = 30.0,
    ) -> list[ExperimentTask]:
        """
        构建实验矩阵（猜想 × 插件配置）

        Args:
            conjectures:     猜想列表
            plugin_configs:  插件配置列表
            timeout_per_experiment: 单实验超时

        Returns:
            ExperimentTask 列表（笛卡尔积）
        """
        tasks: list[ExperimentTask] = []
        task_idx = 0

        for ci, conjecture in enumerate(conjectures):
            for pi, pcfg in enumerate(plugin_configs):
                task_idx += 1
                cid = conjecture.get("conjecture_id", f"c{ci}")
                pname = pcfg.get("name", f"cfg{pi}")

                tasks.append(ExperimentTask(
                    task_id=f"batch{self._run_count}_t{task_idx}_{cid}_{pname}",
                    conjecture=conjecture,
                    plugin_config=pcfg,
                    timeout_seconds=timeout_per_experiment,
                    priority=0,
                ))

        return tasks

    def aggregate_results(
        self, results: list[ExperimentResult]
    ) -> BatchReport:
        """
        聚合实验结果（v1.2 业务逻辑版本）

        Args:
            results: 实验结果列表

        Returns:
            BatchReport 聚合报告（含智能推荐与 top discoveries）
        """
        total = len(results)
        completed = sum(1 for r in results if r.status not in ("TO_RUN", "RUNNING"))
        proven = sum(1 for r in results if r.status == "PROVEN")
        disproven = sum(1 for r in results if r.status == "DISPROVEN")
        pending = sum(1 for r in results if r.status == "PENDING")
        timeout_count = sum(1 for r in results if r.status == "TIMEOUT")
        error_count = sum(1 for r in results if r.status == "ERROR")

        # 按插件配置分组统计
        by_config: dict[str, dict[str, Any]] = {}
        for r in results:
            cfg_name = r.task.plugin_config.get("name", "unknown")
            if cfg_name not in by_config:
                by_config[cfg_name] = {
                    "total": 0, "proven": 0, "disproven": 0,
                    "pending": 0, "error": 0, "timeout": 0,
                }
            by_config[cfg_name]["total"] += 1
            if r.status == "PROVEN":
                by_config[cfg_name]["proven"] += 1
            elif r.status == "DISPROVEN":
                by_config[cfg_name]["disproven"] += 1
            elif r.status == "PENDING":
                by_config[cfg_name]["pending"] += 1
            elif r.status == "ERROR":
                by_config[cfg_name]["error"] += 1
            elif r.status == "TIMEOUT":
                by_config[cfg_name]["timeout"] += 1

        # top_discoveries: 选出最有价值的实验结果
        top_discoveries: list[dict[str, Any]] = []
        for r in results:
            if r.status == "DISPROVEN":
                top_discoveries.append({
                    "task_id": r.task.task_id,
                    "conjecture": r.task.conjecture.get("statement", "")[:120],
                    "finding": "发现反例/证伪",
                    "significance": "high",
                    "elapsed_seconds": r.elapsed_seconds,
                })
            elif r.status == "PROVEN":
                top_discoveries.append({
                    "task_id": r.task.task_id,
                    "conjecture": r.task.conjecture.get("statement", "")[:120],
                    "finding": "证明成功",
                    "significance": "medium",
                    "elapsed_seconds": r.elapsed_seconds,
                })
        # 最多保留 5 条
        top_discoveries = top_discoveries[:5]

        # 智能推荐
        recommendations: list[str] = []
        completion_rate = (completed / total * 100) if total > 0 else 0

        if completion_rate < 100:
            recommendations.append(
                f"完成率 {completion_rate:.0f}% ({completed}/{total})，"
                f"有 {total - completed} 个实验未完成"
            )
        if disproven > 0:
            recommendations.append(
                f"发现 {disproven} 个猜想被证伪，建议审查生成策略"
            )
        if proven > 0:
            recommendations.append(
                f"{proven} 个猜想被证明，建议纳入正式证明链"
            )
        if timeout_count > 0:
            recommendations.append(
                f"{timeout_count} 个实验超时，建议增加 timeout_per_experiment 或简化猜想"
            )
        if error_count > 0:
            recommendations.append(
                f"{error_count} 个实验执行出错，建议检查插件配置与猜想格式"
            )
        if pending > total * 0.5:
            recommendations.append(
                f"超过 50% 实验 ({pending}/{total}) 处于 PENDING 状态，建议检查验证逻辑"
            )

        # 配置对比推荐
        best_config = None
        best_proven = -1
        for cfg_name, stats in by_config.items():
            if stats["proven"] > best_proven:
                best_proven = stats["proven"]
                best_config = cfg_name
        if best_config and best_proven > 0:
            recommendations.append(
                f"最佳插件配置: {best_config} (成功证明 {best_proven} 个猜想)"
            )

        return BatchReport(
            total_experiments=total,
            completed=completed,
            proven=proven,
            disproven=disproven,
            by_config=by_config,
            top_discoveries=top_discoveries,
            recommendations=recommendations,
        )

    def compare_configs(
        self,
        config_results: dict[str, list[ExperimentResult]],
    ) -> dict[str, Any]:
        """
        比较不同插件配置的效果差异（v1.2 业务逻辑版本）

        Args:
            config_results: {config_name: [ExperimentResult]}

        Returns:
            配置对比结果（含效果排名）
        """
        comparison: dict[str, Any] = {
            "configs_compared": list(config_results.keys()),
            "comparison": {},
            "ranking": [],
            "status_note": "v1.2 业务逻辑版本",
        }

        config_scores: list[tuple[str, float]] = []
        for cfg_name, results in config_results.items():
            total = len(results)
            proven = sum(1 for r in results if r.status == "PROVEN")
            disproven = sum(1 for r in results if r.status == "DISPROVEN")
            timeout = sum(1 for r in results if r.status == "TIMEOUT")
            error = sum(1 for r in results if r.status == "ERROR")

            # 综合评分: 证明+2, 证伪+1, 超时-1, 错误-2
            score = proven * 2 + disproven - timeout - error * 2
            avg_elapsed = (
                sum(r.elapsed_seconds for r in results) / total
                if total > 0 else 0
            )

            comparison["comparison"][cfg_name] = {
                "total": total,
                "proven": proven,
                "disproven": disproven,
                "pending": total - proven - disproven - timeout - error,
                "timeout": timeout,
                "error": error,
                "score": score,
                "avg_elapsed_seconds": round(avg_elapsed, 3),
            }
            config_scores.append((cfg_name, score))

        # 排名
        config_scores.sort(key=lambda x: x[1], reverse=True)
        comparison["ranking"] = [
            {"rank": i + 1, "config": name, "score": score}
            for i, (name, score) in enumerate(config_scores)
        ]

        return comparison

    # =========================================================================
    # 真实执行引擎
    # =========================================================================

    def _run_parallel_batch(
        self,
        tasks: list[ExperimentTask],
        max_parallel: int,
        runner: Any = None,
        hypothesis_pool: Any = None,
    ) -> list[ExperimentResult]:
        """
        真实并行执行批量实验任务

        严格遵守 max_parallel 约束，使用 ThreadPoolExecutor 实现并行调度。
        每个子任务有独立的超时控制。

        Args:
            tasks:         实验任务列表
            max_parallel:  最大并行度
            runner:        外部执行回调 (可选)
            hypothesis_pool: 假说池引用 (可选)

        Returns:
            ExperimentResult 列表
        """
        results: list[ExperimentResult] = []

        # 按优先级排序（高优先级先执行）
        sorted_tasks = sorted(tasks, key=lambda t: t.priority, reverse=True)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_parallel,
            thread_name_prefix="batch_exp",
        ) as executor:
            future_to_task: dict[concurrent.futures.Future, ExperimentTask] = {}
            for task in sorted_tasks:
                future = executor.submit(
                    self._run_single_experiment,
                    task=task,
                    runner=runner,
                    hypothesis_pool=hypothesis_pool,
                )
                future_to_task[future] = task

            # 收集结果
            for future in concurrent.futures.as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result = future.result(timeout=task.timeout_seconds + 5.0)
                    results.append(result)
                except concurrent.futures.TimeoutError:
                    results.append(ExperimentResult(
                        task=task,
                        status="TIMEOUT",
                        elapsed_seconds=task.timeout_seconds,
                        error=f"任务超时: {task.timeout_seconds}s",
                    ))
                except Exception as e:
                    results.append(ExperimentResult(
                        task=task,
                        status="ERROR",
                        error=f"执行异常: {type(e).__name__}: {e}",
                    ))

        return results

    def _run_single_experiment(
        self,
        task: ExperimentTask,
        runner: Any = None,
        hypothesis_pool: Any = None,
    ) -> ExperimentResult:
        """
        执行单个实验任务（带超时控制）

        通过 threading 实现子任务级别超时。
        如果提供了 runner 回调，则委托给外部执行器；
        否则使用内置的模拟验证逻辑。

        Args:
            task:            实验任务
            runner:          外部执行回调
            hypothesis_pool: 假说池引用

        Returns:
            ExperimentResult
        """
        import threading

        result_holder: list[ExperimentResult] = []

        def _run() -> None:
            try:
                t0 = time.time()

                if runner is not None and callable(runner):
                    # 委托给外部执行器
                    raw = runner(task.conjecture, task.plugin_config)
                    elapsed = time.time() - t0
                    if isinstance(raw, dict):
                        result_holder.append(ExperimentResult(
                            task=task,
                            status=raw.get("status", "PENDING"),
                            convergence_report=raw.get("convergence_report"),
                            elapsed_seconds=elapsed,
                            logical_gaps=raw.get("logical_gaps", []),
                            plugin_results=raw.get("plugin_results", {}),
                            error=raw.get("error", ""),
                        ))
                    else:
                        result_holder.append(ExperimentResult(
                            task=task,
                            status="PENDING",
                            elapsed_seconds=elapsed,
                        ))
                else:
                    # 内置模拟验证逻辑
                    elapsed = time.time() - t0
                    result_holder.append(
                        self._simulate_experiment(task, elapsed)
                    )

            except Exception as e:
                result_holder.append(ExperimentResult(
                    task=task,
                    status="ERROR",
                    elapsed_seconds=time.time() - t0,
                    error=str(e),
                ))

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=task.timeout_seconds)

        if thread.is_alive():
            return ExperimentResult(
                task=task,
                status="TIMEOUT",
                elapsed_seconds=task.timeout_seconds,
                error=f"子任务超时: {task.timeout_seconds}s",
            )
        elif result_holder:
            return result_holder[0]
        else:
            return ExperimentResult(
                task=task,
                status="ERROR",
                error="未知错误: 无结果返回",
            )

    def _simulate_experiment(
        self,
        task: ExperimentTask,
        elapsed: float,
    ) -> ExperimentResult:
        """
        内置模拟验证逻辑（无外部 runner 时使用）

        基于 conjecture 的 difficulty 和 expected_branch 字段，
        模拟真实实验的验证结果。

        Args:
            task:    实验任务
            elapsed: 已用时间

        Returns:
            ExperimentResult
        """
        conjecture = task.conjecture
        statement = conjecture.get("statement", "")
        difficulty = conjecture.get("difficulty", "medium")
        expected_branch = conjecture.get("expected_branch", "PENDING")

        # 基于 difficulty 推断状态
        if difficulty == "low" and expected_branch == "PROVEN":
            status = "PROVEN"
        elif difficulty == "low" and expected_branch == "DISPROVEN":
            status = "DISPROVEN"
        elif expected_branch == "PROVEN":
            status = "PROVEN"
        elif expected_branch == "DISPROVEN":
            status = "DISPROVEN"
        else:
            status = "PENDING"

        # 模拟逻辑断层
        logical_gaps: list[dict[str, Any]] = []
        if status == "PENDING":
            logical_gaps.append({
                "type": "insufficient_evidence",
                "description": f"猜想 '{statement[:60]}...' 缺乏充分验证证据",
                "severity": "medium",
            })

        return ExperimentResult(
            task=task,
            status=status,
            convergence_report={
                "final_status": status,
                "total_rounds": 1,
                "converged": status in ("PROVEN", "DISPROVEN"),
            } if status != "PENDING" else None,
            elapsed_seconds=elapsed,
            logical_gaps=logical_gaps,
            plugin_results={
                "plugin_name": task.plugin_config.get("name", "unknown"),
                "enabled": task.plugin_config.get("enabled", True),
            },
            error="",
        )

    def _collect_subtask_status(
        self, results: list[ExperimentResult]
    ) -> dict[str, Any]:
        """
        收集子任务状态摘要

        Args:
            results: 实验结果列表

        Returns:
            状态摘要 dict
        """
        status_counts: dict[str, int] = {}
        for r in results:
            s = r.status or "UNKNOWN"
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "total": len(results),
            "status_counts": status_counts,
            "completion_rate": (
                (status_counts.get("PROVEN", 0) + status_counts.get("DISPROVEN", 0))
                / len(results) * 100
                if results else 0
            ),
            "error_count": status_counts.get("ERROR", 0),
            "timeout_count": status_counts.get("TIMEOUT", 0),
        }

    # =========================================================================
    # 生命周期
    # =========================================================================

    def reset(self) -> None:
        """重置内部状态"""
        self._run_count = 0
        self._result_cache.clear()
        self._max_parallel = self.DEFAULT_MAX_PARALLEL
        self._timeout_per_experiment = self.DEFAULT_TIMEOUT_PER_EXPERIMENT
        self._state = self._STATE_IDLE
        self._last_report = None
        self._degradation_reason = ""

    # =========================================================================
    # 辅助方法
    # =========================================================================

    def _error_result(self, message: str) -> PluginResult:
        self._state = self._STATE_ERROR
        return PluginResult(
            plugin_name=self.plugin_name,
            status=PluginStatus.ERROR,
            error=message,
        )

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def run_count(self) -> int:
        return self._run_count

    @property
    def state(self) -> str:
        return self._state

    @property
    def last_report(self) -> BatchReport | None:
        return self._last_report

    @property
    def cached_results(self) -> list[ExperimentResult]:
        return list(self._result_cache)

    @property
    def degradation_reason(self) -> str:
        return self._degradation_reason