"""
module_math_b.math_router — 全局任务分流器（双轨切换核心）

双轨机制：
  场景A — 普通科研/生物/仿真任务：
    Module-MathB 0初始化、0加载、0内存占用、0干扰
    原版 v2.0 系统 100% 原生运行

  场景B — 数论/代数/猜想证明任务：
    动态挂载完整数学智能体集群
    启用数学四态假说池
    启用数学防虚假收敛
    启用多层逻辑断层校验
    启用独立 DB + 内存锁
    启用模板式任务注入
    迭代结束彻底卸载、释放资源

任务识别规则：
  含以下关键词之一 → MATH_TASK = True
    猜想、证明、反例、数论、素数、推导、命题、形式化、Lean、
    conjecture, proof, counterexample, number theory, prime,
    derivation, proposition, formal, theorem, lemma
"""

from __future__ import annotations

import gc
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from module_math_b.math_structs import (
    MathProposition,
    MathDerivationStep,
    MathCounterExample,
    MathValidationReport,
    MathConvergenceReport,
    MathAgentTaskPayload,
)
from module_math_b.math_hypo_pool import MathHypothesisPool
from module_math_b.math_convergence import MathConvergence
from module_math_b.math_validator import MathValidator
from module_math_b.math_template_engine import MathTemplateEngine
from module_math_b.math_snapshot_bridge import MathSnapshotBridge
from module_math_b.math_resource_lock import MathResourceLock, DegradationLevel
from module_math_b.math_db.math_sqlite import MathDatabase

# v1.1 插件系统（可选增强）
from module_math_b.plugins.plugin_registry import (
    PluginRegistry,
    PluginConfig,
    PluginResult,
    PluginStatus,
)
from module_math_b.plugins.sympy_bridge import SympyBridge
from module_math_b.plugins.lean_repl_bridge import LeanReplBridge
from module_math_b.plugins.stagnation_analyzer import StagnationAnalyzer


# =============================================================================
# 路由结果
# =============================================================================

@dataclass
class MathRouteResult:
    """数学路由结果"""
    is_math_task: bool = False
    session_id: str = ""
    task_id: str = ""
    matched_keywords: list[str] = field(default_factory=list)
    propositions_extracted: list[dict[str, str]] = field(default_factory=list)
    error: str = ""


# =============================================================================
# 数学工作流执行结果
# =============================================================================

@dataclass
class MathWorkflowResult:
    """数学工作流执行结果"""
    session_id: str
    task_id: str
    total_rounds: int
    final_status: str  # "PROVEN" | "DISPROVEN" | "FORCED_TERMINATE" | "ERROR"
    propositions: list[dict[str, Any]] = field(default_factory=list)
    convergence_report: dict[str, Any] = field(default_factory=dict)
    validation_reports: list[dict[str, Any]] = field(default_factory=list)
    proof_chain_export: dict[str, Any] = field(default_factory=dict)
    resource_status: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    plugin_results: dict[str, Any] = field(default_factory=dict)  # v1.1 插件结果


# =============================================================================
# 数学路由器
# =============================================================================

class MathRouter:
    """
    全局任务分流器

    核心职责：
      1. 自动识别任务类型（数学 vs 非数学）
      2. 非数学任务 → 完全跳过，0 开销
      3. 数学任务 → 初始化完整数学集群，执行工作流，完毕后销毁
    """

    # 数学任务关键词（中英文）
    MATH_KEYWORDS: list[str] = [
        # 中文
        "猜想", "证明", "反例", "数论", "素数", "推导",
        "命题", "形式化", "代数", "几何", "拓扑",
        "定理", "引理", "推论", "公理", "集合论",
        "哥德巴赫", "黎曼", "费马", "庞加莱",
        "质数", "合数", "整除", "同余", "因子",
        "无穷", "极限", "连续", "可微", "积分",
        "群论", "环论", "域论", "伽罗瓦", "阿贝尔",
        "图论", "组合", "优化", "博弈",
        # 英文
        "conjecture", "proof", "counterexample", "number theory",
        "prime", "derivation", "proposition", "formal", "theorem",
        "lemma", "corollary", "axiom", "algebra", "geometry",
        "topology", "riemann", "goldbach", "fermat", "poincare",
        "group theory", "ring theory", "field theory", "galois",
        "graph theory", "combinatorics", "optimization",
        "lean", "coq", "isabelle", "formal proof",
    ]

    # 最大迭代轮次上限
    MAX_ITERATIONS: int = 10

    # 数据库路径
    DB_PATH: str = ""

    __slots__ = (
        "_db", "_lock", "_validator", "_convergence",
        "_template_engine", "_bridge", "_pool",
        "_session_id", "_initialized", "_is_math_session",
        "_plugin_registry",  # v1.1
    )

    def __init__(self, db_path: str | None = None) -> None:
        self._db: MathDatabase | None = None
        self._lock: MathResourceLock | None = None
        self._validator: MathValidator | None = None
        self._convergence: MathConvergence | None = None
        self._template_engine: MathTemplateEngine | None = None
        self._bridge: MathSnapshotBridge | None = None
        self._pool: MathHypothesisPool | None = None
        self._plugin_registry: PluginRegistry | None = None  # v1.1
        self._session_id: str = ""
        self._initialized: bool = False
        self._is_math_session: bool = False

        if db_path:
            self.DB_PATH = db_path

    # =========================================================================
    # 任务识别
    # =========================================================================

    def is_math_task(self, task: dict[str, Any]) -> MathRouteResult:
        """
        识别任务是否为数学任务

        检查任务描述中的关键词。
        """
        query = task.get("query", task.get("description", ""))
        task_type = task.get("task_type", "")
        task_id = task.get("task_id", str(uuid.uuid4())[:8])

        # 聚合并检查文本
        text = f"{query} {task_type}".lower()
        matched = []

        for keyword in self.MATH_KEYWORDS:
            if keyword.lower() in text:
                matched.append(keyword)

        if not matched:
            return MathRouteResult(is_math_task=False, task_id=task_id)

        # 提取命题
        propositions = self._extract_propositions(query)

        return MathRouteResult(
            is_math_task=True,
            session_id=str(uuid.uuid4()),
            task_id=task_id,
            matched_keywords=matched,
            propositions_extracted=propositions,
        )

    def _extract_propositions(self, text: str) -> list[dict[str, str]]:
        """
        从文本中提取数学命题

        简单启发式：按句号/问号分割，筛选包含数学关键词的句子。
        """
        import re
        sentences = re.split(r'[。？?！!\n]', text)
        propositions = []
        for i, sent in enumerate(sentences):
            sent = sent.strip()
            if not sent or len(sent) < 5:
                continue
            # 检查是否包含数学关键词
            if any(kw in sent for kw in ["猜想", "证明", "命题", "定理", "conjecture", "proof", "theorem"]):
                propositions.append({
                    "proposition_id": f"prop_{i}",
                    "statement": sent,
                })
        return propositions

    # =========================================================================
    # 模块初始化
    # =========================================================================

    def init_math_session(self, task_id: str) -> None:
        """
        初始化数学模块完整集群

        按顺序初始化：
          1. 独立数据库
          2. 资源锁
          3. 数学假说池
          4. 收敛判定器
          5. 校验引擎
          6. 模板引擎
          7. 快照桥接
        """
        if self._initialized:
            return

        self._session_id = str(uuid.uuid4())
        self._is_math_session = True

        # 1. 独立数据库
        self._db = MathDatabase(self.DB_PATH if self.DB_PATH else None)
        self._db.log_event(self._session_id, "SESSION_START", f"task_id={task_id}")

        # 2. 资源锁
        self._lock = MathResourceLock(on_l3_callback=self._on_l3_emergency)
        self._db.log_event(self._session_id, "RESOURCE_LOCK_INIT", "RAM threshold 60%")

        # 3. 数学假说池
        self._pool = MathHypothesisPool()
        self._db.log_event(self._session_id, "HYPOTHESIS_POOL_INIT", "")

        # 4. 收敛判定器
        self._convergence = MathConvergence()
        self._db.log_event(self._session_id, "CONVERGENCE_INIT", "")

        # 5. 校验引擎
        self._validator = MathValidator()
        self._db.log_event(self._session_id, "VALIDATOR_INIT", "")

        # 6. 模板引擎
        self._template_engine = MathTemplateEngine()
        self._db.log_event(self._session_id, "TEMPLATE_ENGINE_INIT", "")

        # 7. 快照桥接
        self._bridge = MathSnapshotBridge(task_id=task_id)
        self._db.log_event(self._session_id, "SNAPSHOT_BRIDGE_INIT", "")

        # 8. 插件注册表（v1.1）
        self._plugin_registry = PluginRegistry()
        self._plugin_registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=False))
        self._plugin_registry.register(LeanReplBridge(), PluginConfig(name="lean_repl_bridge", enabled=False))
        self._plugin_registry.register(StagnationAnalyzer(), PluginConfig(name="stagnation_analyzer", enabled=False))
        self._db.log_event(self._session_id, "PLUGIN_REGISTRY_INIT", "3 plugins registered, all disabled")

        self._initialized = True

    # =========================================================================
    # 数学工作流执行
    # =========================================================================

    def execute_math_workflow(
        self,
        task: dict[str, Any],
        orchestrator: Any = None,
        on_round_complete: Callable[[int, dict[str, Any]], None] | None = None,
    ) -> MathWorkflowResult:
        """
        执行完整数学工作流

        Args:
            task:              任务描述
            orchestrator:      主系统 Orchestrator（可选，用于分发子任务）
            on_round_complete: 每轮完成回调

        Returns:
            MathWorkflowResult
        """
        route = self.is_math_task(task)
        if not route.is_math_task:
            return MathWorkflowResult(
                session_id="",
                task_id=route.task_id,
                total_rounds=0,
                final_status="ERROR",
                error="非数学任务，拒绝执行",
            )

        task_id = route.task_id
        session_id = route.session_id

        # 初始化
        self.init_math_session(task_id)
        assert self._pool is not None
        assert self._lock is not None
        assert self._convergence is not None
        assert self._validator is not None
        assert self._template_engine is not None
        assert self._bridge is not None
        assert self._db is not None
        assert self._plugin_registry is not None

        # v1.1: 加载插件配置
        self._plugin_registry.load_config(task)
        self._db.log_event(
            session_id, "PLUGIN_CONFIG_LOADED",
            f"enabled={self._plugin_registry.list_enabled()}",
        )

        try:
            # 注册命题
            for prop_data in route.propositions_extracted:
                self._pool.register_proposition(
                    proposition_id=prop_data["proposition_id"],
                    statement=prop_data["statement"],
                    domain=task.get("task_type", "number_theory"),
                )
                self._db.log_event(
                    session_id, "PROPOSITION_REGISTERED",
                    f"id={prop_data['proposition_id']}",
                )

            # 迭代循环
            round_number = 0
            final_status = "ERROR"

            while round_number < self.MAX_ITERATIONS:
                round_number += 1

                # 检查资源锁
                status = self._lock.check_status()
                if status.level >= DegradationLevel.L3:
                    self._db.log_event(
                        session_id, "FORCED_TERMINATE",
                        f"RAM threshold exceeded at round {round_number}, level={status.level.name}",
                    )
                    final_status = "FORCED_TERMINATE"
                    break

                if status.level >= DegradationLevel.L1:
                    self._db.log_event(
                        session_id, "DEGRADATION",
                        f"level={status.level.name} at round {round_number}",
                    )

                # 检查是否允许执行新任务
                if not self._lock.acquire_task():
                    self._db.log_event(
                        session_id, "TASK_REJECTED",
                        f"Resource lock denied task at round {round_number}",
                    )
                    continue

                try:
                    # 生成任务载荷
                    all_props = self._pool.get_all_propositions()
                    if not all_props:
                        # 没有命题，跳过
                        break

                    # 模拟一轮数学推理
                    round_outputs = self._simulate_math_round(
                        all_props, round_number, task.get("query", ""),
                    )

                    # 注册 Worker 输出到假说池
                    self._pool.register_from_worker_outputs(
                        round_outputs, round_number=round_number,
                    )

                    # 添加推导步骤到假说池
                    self._add_derivation_steps_from_outputs(
                        round_outputs, all_props,
                    )

                    # 持久化命题（必须先于 derivation_steps 和 validation_reports）
                    for prop in all_props:
                        self._db.insert_proposition({
                            "proposition_id": prop.proposition_id,
                            "statement": prop.statement,
                            "domain": prop.domain,
                            "difficulty": prop.difficulty,
                            "iteration_depth": prop.iteration_depth,
                            "status": prop.status,
                            "proven_by": prop.proven_by,
                            "proof_chain_hash": prop.proof_chain_hash,
                            "created_at": prop.created_at,
                        })

                    # 持久化推导步骤
                    for prop in all_props:
                        for step in prop.derivation_steps:
                            try:
                                self._db.insert_derivation_step({
                                    "step_id": step.step_id,
                                    "proposition_id": prop.proposition_id,
                                    "step_number": step.step_number,
                                    "premises": step.premises,
                                    "conclusion": step.conclusion,
                                    "derivation_rule": step.derivation_rule,
                                    "justification": step.justification,
                                    "has_gap": step.has_gap,
                                    "gap_description": step.gap_description,
                                    "has_hidden_assumption": step.has_hidden_assumption,
                                    "hidden_assumption": step.hidden_assumption,
                                    "is_circular": step.is_circular,
                                    "validation_passed": step.validation_passed,
                                    "validation_errors": step.validation_errors,
                                    "source_agent": step.source_agent,
                                })
                            except Exception:
                                pass  # 忽略重复插入

                    # 校验
                    for prop in all_props:
                        report = self._validator.validate_proposition(
                            prop, round_number=round_number,
                        )
                        self._pool.add_validation_report(prop.proposition_id, report)
                        # 持久化校验报告
                        try:
                            self._db.insert_validation_report({
                                "report_id": report.report_id,
                                "proposition_id": report.proposition_id,
                                "round_number": report.round_number,
                                "syntax_valid": report.syntax_valid,
                                "syntax_errors": report.syntax_errors,
                                "logical_gaps": report.logical_gaps,
                                "hidden_assumptions": report.hidden_assumptions,
                                "circular_found": report.circular_reasoning_found,
                                "overall_valid": report.overall_valid,
                                "overall_score": report.overall_score,
                                "requires_iteration": report.requires_iteration,
                                "iteration_hints": report.iteration_hints,
                            })
                        except Exception:
                            pass

                    # 更新状态
                    self._pool.update_statuses_from_validation()

                    # v1.1: 执行已启用的插件
                    plugin_context = self._build_plugin_context(
                        all_props, round_number, task.get("query", ""),
                    )
                    self._plugin_registry.execute_enabled(plugin_context)

                    # 收敛判定
                    conv_report = self._convergence.evaluate(
                        self._pool, round_number=round_number,
                    )

                    # 快照
                    snapshot = self._bridge.create_snapshot(
                        round_number=round_number,
                        pool=self._pool,
                        convergence_report=conv_report,
                    )

                    # 持久化快照
                    self._db.insert_snapshot({
                        "snapshot_id": snapshot.snapshot_id,
                        "task_id": task_id,
                        "round_number": round_number,
                        "timestamp": snapshot.timestamp,
                        "content_hash": snapshot.content_hash,
                        "prev_snapshot_hash": snapshot.prev_snapshot_hash,
                        "snapshot_data": {
                            "propositions": snapshot.propositions,
                            "convergence_report": snapshot.convergence_report,
                        },
                    })

                    # 回调
                    if on_round_complete:
                        on_round_complete(round_number, {
                            "round": round_number,
                            "proposition_count": self._pool.proposition_count,
                            "proven": self._pool.proven_count,
                            "disproven": self._pool.disproven_count,
                            "converged": conv_report.is_converged,
                            "convergence_type": conv_report.convergence_type,
                        })

                    self._db.log_event(
                        session_id, "ROUND_COMPLETE",
                        f"round={round_number}, converged={conv_report.is_converged}, "
                        f"type={conv_report.convergence_type}",
                    )

                    # 检查收敛
                    if conv_report.is_converged:
                        final_status = conv_report.convergence_type or "UNKNOWN"
                        break

                finally:
                    self._lock.release_task()

            # 工作流结束
            if round_number >= self.MAX_ITERATIONS and final_status == "ERROR":
                final_status = "FORCED_TERMINATE"

            # 导出证明链
            proof_chain_export = self._bridge.export_proof_chain()

            # 资源状态
            resource_status = {
                "level": self._lock.current_level.name,
                "active_tasks": self._lock.active_task_count,
                "degradation_count": len(self._lock.degradation_history),
            }

            self._db.log_event(session_id, "SESSION_END", f"final_status={final_status}")

            return MathWorkflowResult(
                session_id=session_id,
                task_id=task_id,
                total_rounds=round_number,
                final_status=final_status,
                propositions=self._pool.to_dict_list(),
                convergence_report={
                    "type": final_status,
                    "rounds": round_number,
                    "stagnation_rounds": self._convergence.stagnation_rounds,
                },
                validation_reports=[
                    {"proposition_id": p.proposition_id, "reports": len(p.validation_reports)}
                    for p in self._pool.get_all_propositions()
                ],
                proof_chain_export=proof_chain_export,
                resource_status=resource_status,
                plugin_results={  # v1.1
                    r.plugin_name: {
                        "plugin_name": r.plugin_name,
                        "status": r.status.value,
                        "output": r.output,
                        "error": r.error,
                        "elapsed_ms": r.elapsed_ms,
                    }
                    for r in self._plugin_registry.get_results()
                },
            )

        except Exception as e:
            self._db.log_event(session_id, "ERROR", str(e))
            return MathWorkflowResult(
                session_id=session_id,
                task_id=task_id,
                total_rounds=round_number if 'round_number' in dir() else 0,
                final_status="ERROR",
                error=str(e),
            )

        finally:
            self.destroy_math_session()

    # =========================================================================
    # 模拟数学推理（不调用外部 LLM API）
    # =========================================================================

    def _add_derivation_steps_from_outputs(
        self,
        round_outputs: dict[str, Any],
        propositions: list[MathProposition],
    ) -> None:
        """从 Worker 输出中提取推导步骤并添加到假说池"""
        assert self._pool is not None
        prop_map = {p.proposition_id: p for p in propositions}

        for agent_id, output in round_outputs.items():
            inner = output.get("output", output)
            if not isinstance(inner, dict):
                continue
            derivation_steps = inner.get("derivation_steps", [])
            if not isinstance(derivation_steps, list):
                continue
            for ds_data in derivation_steps:
                if not isinstance(ds_data, dict):
                    continue
                pid = ds_data.get("proposition_id", "")
                if pid not in prop_map:
                    continue
                step = MathDerivationStep(
                    step_id=ds_data.get("step_id", ""),
                    step_number=ds_data.get("step_number", 0),
                    premises=ds_data.get("premises", []),
                    conclusion=ds_data.get("conclusion", ""),
                    derivation_rule=ds_data.get("derivation_rule", ""),
                    justification=ds_data.get("justification", ""),
                    has_gap=ds_data.get("has_gap", False),
                    gap_description=ds_data.get("gap_description", ""),
                    has_hidden_assumption=ds_data.get("has_hidden_assumption", False),
                    hidden_assumption=ds_data.get("hidden_assumption", ""),
                    is_circular=ds_data.get("is_circular", False),
                    circular_reference=ds_data.get("circular_reference", ""),
                    validation_passed=ds_data.get("validation_passed", False),
                    source_agent=agent_id,
                )
                self._pool.add_derivation_step(pid, step)

    def _simulate_math_round(
        self,
        propositions: list[MathProposition],
        round_number: int,
        query: str,
    ) -> dict[str, Any]:
        """
        模拟一轮数学推理

        模拟 4 个数学 Agent 的输出结构：
          - prover_agent: 构造证明步骤
          - reviewer_agent: 审查证明
          - counter_example_seeker_agent: 搜寻反例
          - experimenter_agent: 数值实验
        """
        outputs: dict[str, Any] = {}

        for prop in propositions:
            pid = prop.proposition_id

            # Prover: 构造证明步骤
            step_num = len(prop.derivation_steps) + 1
            prover_output = {
                "agent_id": "prover_agent",
                "status": "success",
                "output": {
                    "propositions": [{
                        "proposition_id": pid,
                        "statement": prop.statement,
                    }],
                    "derivation_steps": [{
                        "step_id": f"{pid}_step_{step_num}",
                        "proposition_id": pid,
                        "step_number": step_num,
                        "premises": [
                            f"已知 {prop.statement} 的定义",
                            f"第 {step_num - 1} 步结论" if step_num > 1 else "公理系统",
                        ],
                        "conclusion": f"步骤 {step_num} 推导结论: {prop.statement[:50]}...",
                        "derivation_rule": "direct_proof" if step_num <= 3 else "induction",
                        "justification": f"基于第 {step_num} 步的数学推导",
                        "has_gap": step_num > 5,  # 5步后可能出现 gap
                        "gap_description": "推导步骤较多，需要进一步验证" if step_num > 5 else "",
                        "has_hidden_assumption": False,
                        "is_circular": False,
                        "validation_passed": step_num <= 5,
                        "source_agent": "prover_agent",
                    }],
                    "confidence": 0.7 + 0.05 * step_num,
                },
            }
            outputs["prover_agent"] = prover_output

            # Reviewer: 审查
            reviewer_output = {
                "agent_id": "reviewer_agent",
                "status": "success",
                "output": {
                    "critiques": [{
                        "target_proposition_id": pid,
                        "severity_score": 0.3 if step_num <= 3 else 0.6,
                        "description": (
                            "前几步推导严密" if step_num <= 3
                            else "后续步骤存在逻辑跳跃风险"
                        ),
                    }],
                    "confidence": 0.65,
                },
            }
            outputs["reviewer_agent"] = reviewer_output

            # Counter-example seeker: 搜寻反例
            seeker_output = {
                "agent_id": "counter_example_seeker_agent",
                "status": "success",
                "output": {
                    "counter_examples": [],
                    "confidence": 0.5,
                },
            }
            outputs["counter_example_seeker_agent"] = seeker_output

            # Experimenter: 数值实验
            experimenter_output = {
                "agent_id": "experimenter_agent",
                "status": "success",
                "output": {
                    "experiments": [{
                        "proposition_id": pid,
                        "sample_count": 10,
                        "pass_rate": 0.9,
                        "boundary_tested": True,
                    }],
                    "confidence": 0.6,
                },
            }
            outputs["experimenter_agent"] = experimenter_output

        return outputs

    # =========================================================================
    # v1.1 插件上下文构建
    # =========================================================================

    def _build_plugin_context(
        self,
        propositions: list[MathProposition],
        round_number: int,
        query: str,
    ) -> dict[str, Any]:
        """
        构建插件执行上下文

        从当前假说池状态提取插件所需数据。
        """
        assert self._pool is not None
        assert self._convergence is not None

        # 收集推导步骤
        derivation_steps: list[dict[str, Any]] = []
        for prop in propositions:
            for step in prop.derivation_steps:
                derivation_steps.append({
                    "step_id": step.step_id,
                    "proposition_id": prop.proposition_id,
                    "step_number": step.step_number,
                    "has_gap": step.has_gap,
                    "gap_description": step.gap_description,
                    "is_circular": step.is_circular,
                    "has_hidden_assumption": step.has_hidden_assumption,
                    "validation_passed": step.validation_passed,
                })

        # 收集校验报告
        validation_reports: list[dict[str, Any]] = []
        for prop in propositions:
            for report in prop.validation_reports:
                validation_reports.append({
                    "report_id": report.report_id,
                    "proposition_id": report.proposition_id,
                    "overall_score": report.overall_score,
                    "overall_valid": report.overall_valid,
                })

        return {
            "query": query,
            "round_number": round_number,
            "propositions": [
                {
                    "proposition_id": p.proposition_id,
                    "statement": p.statement,
                    "status": p.status,
                    "domain": p.domain,
                }
                for p in propositions
            ],
            "derivation_steps": derivation_steps,
            "validation_reports": validation_reports,
            "stagnation_rounds": self._convergence.stagnation_rounds,
            "pool_snapshot": self._pool.snapshot().__dict__,
        }

    # =========================================================================
    # 模块销毁
    # =========================================================================

    def destroy_math_session(self) -> None:
        """
        完全销毁数学模块实例

        释放内存、关闭独立 DB 连接、强制 GC 回收。
        """
        if self._plugin_registry:
            self._plugin_registry.reset()
            self._plugin_registry = None

        if self._db and not self._db.is_closed:
            self._db.log_event(self._session_id or "unknown", "SESSION_DESTROY", "")
            self._db.close()

        self._pool = None
        self._convergence = None
        self._validator = None
        self._template_engine = None
        self._bridge = None
        self._lock = None
        self._db = None
        self._initialized = False
        self._is_math_session = False
        self._session_id = ""

        gc.collect()

    def _on_l3_emergency(self) -> None:
        """L3 紧急降级回调"""
        if self._db:
            self._db.log_event(
                self._session_id or "unknown",
                "L3_EMERGENCY",
                "RAM 60% exceeded, freezing all tasks",
            )

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_math_session(self) -> bool:
        return self._is_math_session

    @property
    def hypothesis_pool(self) -> MathHypothesisPool | None:
        return self._pool

    @property
    def convergence(self) -> MathConvergence | None:
        return self._convergence

    @property
    def validator(self) -> MathValidator | None:
        return self._validator

    @property
    def template_engine(self) -> MathTemplateEngine | None:
        return self._template_engine

    @property
    def snapshot_bridge(self) -> MathSnapshotBridge | None:
        return self._bridge

    @property
    def resource_lock(self) -> MathResourceLock | None:
        return self._lock

    @property
    def database(self) -> MathDatabase | None:
        return self._db

    @property
    def plugin_registry(self) -> PluginRegistry | None:
        """v1.1 插件注册表"""
        return self._plugin_registry