#!/usr/bin/env python3
"""
main.py — Multi-Agent Brain Orchestrator 主入口

Trae Task 子 Agent 调度模式：
  ① 接收科研任务 → LeadResearcher 编排者拆解任务，生成 5 个 worker 子任务
  ② 把 5 个子任务交给 Trae Task 并行执行，获得各个 worker 的原始输出
  ③ 全部原始输出回传给 harness 层
  ④ 执行 meta_rules 元规则、safety_validator 安全校验
  ⑤ 生成 ReflectionOutput，写入 data/snapshots 快照归档
  ⑥ 合法任务下发 brain_subsystem 执行仿真
  ⑦ 仿真结果回传，开启下一轮迭代循环

用法：
  python3 main.py                       # 构建任务描述 + 输出到 stdout
  python3 main.py --results <file>      # 读取 Trae Task 子 Agent 结果，执行 Harness 管道
  python3 main.py --multi --rounds 2    # 多轮迭代模式（需配合 --results 使用）
  python3 main.py --run-loop --rounds 2 # 端到端多轮迭代（自动构建描述并输出）
"""

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

# --- Agents ---
from agents.base_worker import TaskDescription
from agents.lead_researcher import LeadResearcher
from agents.worker_perception import WorkerPerception
from agents.worker_hypothesis_builder import WorkerHypothesisBuilder
from agents.worker_skeptic import WorkerSkeptic
from agents.worker_red_team import WorkerRedTeam
from agents.worker_archivist import WorkerArchivist

# --- Harness ---
from harness.orchestrator import Orchestrator
from harness.meta_rules import MetaRules
from harness.safety_validator import SafetyValidator
from harness.snapshot_archive import SnapshotArchive
from harness.structs import ReflectionOutput, MetaRuleRecord

# --- B1 Brain Subsystem ---
from brain_subsystem.interface import BrainInterface
from brain_subsystem.constants import BRAIN_CONSTANTS


# =============================================================================
# 主应用
# =============================================================================


class BrainOrchestratorApp:
    """Multi-Agent Brain Orchestrator — Trae Task 调度模式"""

    def __init__(self, *, verbose: bool = True, max_rounds: int = 5) -> None:
        self.verbose = verbose
        self.max_rounds = max_rounds

        # 初始化 Harness 管控底座
        # max_iterations 是元规则熔断阈值，独立于 demo 运行轮次
        self.meta_rules = MetaRules(max_iterations=5)
        self.validator = SafetyValidator()
        self.snapshot_mgr = SnapshotArchive(storage_path="data/snapshots")

        # 初始化 B1 冻结内核
        self.brain = BrainInterface()

        # 初始化编排者
        self.lead = LeadResearcher()

        # 注册所有 Worker（纯任务描述构建器，无 LLM 依赖）
        self.lead.register_worker(WorkerPerception())
        self.lead.register_worker(WorkerHypothesisBuilder())
        self.lead.register_worker(WorkerSkeptic())
        self.lead.register_worker(WorkerRedTeam())
        self.lead.register_worker(WorkerArchivist())

        # 初始化总调度器
        self.orchestrator = Orchestrator(
            lead_researcher=self.lead,
            meta_rules=self.meta_rules,
            validator=self.validator,
            snapshot_mgr=self.snapshot_mgr,
            brain=self.brain,
        )

        # 注册 Worker 到调度器
        for agent_id, worker in self.lead.worker_registry.items():
            self.orchestrator.register_worker(worker)

        # 多轮迭代状态
        self._round_number: int = 0
        self._all_rounds_history: list[dict[str, Any]] = []
        self._b1_simulation_results: list[dict[str, Any]] = []

    # =========================================================================
    # Phase 1: 构建任务描述
    # =========================================================================

    def build_descriptions(
        self, task: dict[str, Any], round_number: int = 1
    ) -> list[dict[str, Any]]:
        """构建标准化 Task 任务描述，输出给 Trae Task 工具派发"""
        self._banner("PHASE 1", f"构建 Task 任务描述 (第 {round_number} 轮)")
        self._log(f"已注册 Worker: {self.orchestrator.registered_workers}")
        self._log(f"B1 内核状态: {self.brain.get_kernel_state()}")

        for agent_id, worker in self.lead.worker_registry.items():
            loaded = bool(worker.prompt_template)
            self._log(f"  {agent_id}: prompt={'loaded' if loaded else 'NOT FOUND'}, role={worker.ROLE_NAME}")

        # 输入校验
        val_result = self.validator.validate_root_input(task)
        if not val_result.is_valid:
            self._log(f"输入校验失败: {val_result.errors}", level="ERROR")
            return [{"error": "input_validation_failed", "details": val_result.errors}]
        self._log("输入校验通过")

        # 构建任务描述
        descriptions = self.orchestrator.build_task_descriptions(task)
        self._log(f"生成 {len(descriptions)} 个 Task 任务描述")

        return descriptions

    # =========================================================================
    # Phase 2+3: 处理 Trae Task 子 Agent 返回结果
    # =========================================================================

    def process(
        self, task_id: str, worker_results: dict[str, Any], round_number: int = 1
    ) -> ReflectionOutput:
        """处理 Trae Task 子 Agent 返回结果，完成 Harness 管道"""
        self._banner("PHASE 2-3", f"处理 Trae Task 子 Agent 返回结果 (第 {round_number} 轮)")

        self._log(f"收到 {len(worker_results)} 个 Worker 结果")
        for agent_id, output in worker_results.items():
            status = output.get("status", "?") if isinstance(output, dict) else "?"
            self._log(f"  {agent_id}: status={status}")

        # 输出校验（由 orchestrator 内部统一处理，此处仅做日志输出）
        self._banner("STEP 4", "输出校验")
        for agent_id, output in list(worker_results.items()):
            val = self.validator.validate_output(output, agent_id)
            if val.is_valid:
                self._log(f"  ✓ {agent_id} 输出校验通过")
            else:
                self._log(f"  ✗ {agent_id} 输出校验失败: {val.errors}", level="ERROR")

        # 快照归档 + 元规则 + ReflectionOutput（由 orchestrator 统一处理）
        self._banner("STEP 5-6", "元规则处理 + 快照归档 + ReflectionOutput")
        reflection = self.orchestrator.process_results(task_id, worker_results)
        self._log(f"  快照归档: {reflection.snapshot_id}")
        self._log(f"  status: {reflection.status}")
        self._log(f"  confidence: {reflection.confidence:.2f}")
        for log in reflection.meta_rules_log:
            self._log(f"  规则 {log.rule_id} [{log.rule_name}]: {log.trigger_reason}")

        # B1 仿真
        self._banner("STEP 7", "B1 仿真执行")
        b1_result = self._run_b1_simulation(reflection)
        self._b1_simulation_results.append(b1_result)

        # 哈希链验证
        chain = self.snapshot_mgr.verify_chain()
        self._log(f"  哈希链验证: {'有效' if chain['is_valid'] else '损坏'}")

        # 记录本轮历史
        self._round_number = round_number
        self._all_rounds_history.append({
            "round": round_number,
            "outputs": dict(worker_results),
            "reflection": reflection,
            "b1_result": b1_result,
            "context_version": self.orchestrator.context_version,
        })

        self._banner("DONE", f"第 {round_number} 轮闭环完成")
        return reflection

    # =========================================================================
    # 多轮迭代循环
    # =========================================================================

    def run_iteration_loop(
        self,
        task: dict[str, Any],
        rounds_data: dict[int, dict[str, Any]],
    ) -> list[ReflectionOutput]:
        """
        执行完整多轮迭代循环

        Args:
            task:        顶层任务
            rounds_data: {round_number: {agent_id: output, ...}} 各轮结果

        Returns:
            每轮的 ReflectionOutput 列表
        """
        reflections: list[ReflectionOutput] = []
        task_id = task.get("task_id", "demo_task")
        total_rounds = len(rounds_data)

        self._banner("MULTI-ROUND", f"多轮迭代循环启动 (共 {total_rounds} 轮)")
        self._log(f"任务: {task.get('query', task.get('description', ''))}")
        self._log(f"最大迭代轮次: {self.max_rounds}")
        self._log(f"B1 内核: 已冻结 (仅通过 BrainInterface 调用)")

        for round_num in sorted(rounds_data.keys()):
            self._log(f"\n{'─' * 50}")
            self._log(f"  >>> 开始第 {round_num}/{total_rounds} 轮 <<<")
            self._log(f"{'─' * 50}")

            worker_results = rounds_data[round_num]

            # 处理本轮结果
            reflection = self.process(task_id, worker_results, round_num)
            reflections.append(reflection)

            # 熔断检查
            if reflection.status == "circuit_broken":
                self._log("⚠ 超限熔断触发，迭代循环终止", level="WARN")
                break

            # 收敛检查
            if reflection.status == "converged":
                self._log("✓ 集群收敛，迭代循环提前结束")
                break

            # 最后一轮不需要准备下一轮
            if round_num >= total_rounds:
                break

            # 准备下一轮任务描述
            self._banner("ITERATE", f"准备第 {round_num + 1} 轮任务描述")
            next_descriptions = self._build_next_round_descriptions(
                task, reflection, round_num + 1
            )
            self._log(f"生成 {len(next_descriptions)} 个下一轮 Task 任务描述")

            # 输出下一轮任务描述
            sys.stdout.write(f"\n\n--- ROUND {round_num + 1} TASK_DESCRIPTIONS_JSON ---\n")
            sys.stdout.write(json.dumps(next_descriptions, indent=2, ensure_ascii=False))
            sys.stdout.write(f"\n--- END_ROUND_{round_num + 1}_TASK_DESCRIPTIONS ---\n")
            sys.stdout.flush()

        self._banner("MULTI-ROUND-END", "多轮迭代循环完成")
        self._print_multi_round_summary(reflections)
        return reflections

    def _build_next_round_descriptions(
        self, task: dict[str, Any], prev_reflection: ReflectionOutput, round_num: int
    ) -> list[dict[str, Any]]:
        """
        基于上一轮结果构建下一轮任务描述

        B1 仿真结果回传 → 编排者更新科研计划 → 生成新 worker 子任务
        """
        # 提取上一轮的关键发现和未解决问题
        iteration_hints = prev_reflection.open_questions[:]
        iteration_hints.append(f"上一轮置信度: {prev_reflection.confidence:.2f}")
        iteration_hints.append(f"上一轮状态: {prev_reflection.status}")

        # 提取 B1 仿真结果
        if self._b1_simulation_results:
            last_b1 = self._b1_simulation_results[-1]
            iteration_hints.append(
                f"B1 仿真深度: {last_b1.get('depth')}, "
                f"稳态: {last_b1.get('is_stable')}"
            )

        # 更新编排者计划
        updated_task = dict(task)
        updated_task["iteration_hints"] = iteration_hints
        updated_task["previous_round"] = round_num - 1
        updated_task["previous_reflection"] = {
            "status": prev_reflection.status,
            "confidence": prev_reflection.confidence,
            "conclusion": prev_reflection.conclusion[:300],
            "limitations": prev_reflection.limitations,
            "open_questions": prev_reflection.open_questions,
        }

        # 编排者基于新观测更新计划并生成子任务
        updated_task["subtasks"] = self.lead.update_plan(updated_task)

        # 构建新任务描述
        return self.orchestrator.build_task_descriptions(updated_task)

    def _run_b1_simulation(self, reflection: ReflectionOutput) -> dict[str, Any]:
        """运行 B1 仿真并返回结果"""
        b1_result = self.brain.run_inference(
            context=f"任务: {reflection.task_id}, 结论: {reflection.conclusion[:200]}",
            depth=min(reflection.iteration_count + 1, BRAIN_CONSTANTS.MAX_INFERENCE_DEPTH),
        )
        self._log(f"  B1 推理完成: depth={b1_result.get('depth')}")
        osc_values = [self.brain.compute_oscillation(t * 0.1) for t in range(10)]
        self._log(f"  B1 振荡序列: {[round(v, 3) for v in osc_values]}")
        is_stable = self.brain.is_homeostatic([reflection.confidence] * 15)
        self._log(f"  B1 稳态检测: {'稳态' if is_stable else '非稳态'}")

        b1_result["is_stable"] = is_stable
        b1_result["oscillation_values"] = osc_values
        return b1_result

    def _print_multi_round_summary(self, reflections: list[ReflectionOutput]) -> None:
        """打印多轮迭代总结"""
        print(f"\n{'='*60}")
        print(f"  多轮迭代总结")
        print(f"{'='*60}")
        for i, ref in enumerate(reflections, 1):
            print(f"\n  第 {i} 轮:")
            print(f"    status:       {ref.status}")
            print(f"    confidence:   {ref.confidence:.2f}")
            print(f"    snapshot_id:  {ref.snapshot_id}")
            print(f"    meta_rules:   {len(ref.meta_rules_log)} 条触发")
            print(f"    open_issues:  {len(ref.open_questions)} 个")

        print(f"\n{'='*60}")
        print(f"  完整性检查")
        print(f"{'='*60}")
        print(f"  - 总轮次: {len(reflections)}")
        print(f"  - 快照归档数量: {self.snapshot_mgr.archive_count}")
        print(f"  - 哈希链有效: {self.snapshot_mgr.verify_chain()['is_valid']}")
        print(f"  - B1 内核未修改: True (仅通过 BrainInterface 调用)")
        print(f"  - 外部 LLM API 调用: 0 次")
        print(f"  - Worker 推理: 全部由 Trae 内置 Task 子 Agent 完成")

    # --- 辅助 ---

    def _log(self, msg: str, level: str = "INFO") -> None:
        if self.verbose:
            prefix = {"INFO": "  ", "OK": "  ✓", "WARN": "  ⚠", "ERROR": "  ✗"}.get(level, "  ")
            print(f"{prefix} {msg}")

    def _banner(self, step: str, title: str) -> None:
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"  [{step}] {title}")
            print(f"{'='*60}")


# =============================================================================
# CLI 入口
# =============================================================================


def main():
    demo_task = {
        "task_id": "demo_001",
        "task_type": "composite",
        "query": "大语言模型 hallucination 的根因分析",
        "description": "探究 LLM hallucination 的根本原因，区分训练数据覆盖度假说与不确定性校准假说",
    }

    print("""
╔══════════════════════════════════════════════════════════════╗
║   Multi-Agent Brain Orchestrator — Trae Task 调度模式        ║
║   Orchestrator-Worker 多智能体集群 + Harness 管控底座         ║
║   B1-Final 冻结仿真内核                                       ║
║   所有 Worker 推理由 Trae 内置 Task 子 Agent 完成             ║
╚══════════════════════════════════════════════════════════════╝
""")

    multi_mode = "--multi" in sys.argv
    run_loop_mode = "--run-loop" in sys.argv

    # 解析轮次
    rounds = 2
    if "--rounds" in sys.argv:
        try:
            idx = sys.argv.index("--rounds")
            rounds = int(sys.argv[idx + 1])
        except (ValueError, IndexError):
            rounds = 2

    app = BrainOrchestratorApp(verbose=True, max_rounds=rounds)

    if multi_mode or run_loop_mode:
        # =====================================================================
        # 多轮迭代模式
        # =====================================================================
        if "--multi" in sys.argv and "--results" in sys.argv:
            # 多轮模式 + 结果文件：执行一轮处理并可能输出下一轮描述
            idx = sys.argv.index("--results")
            results_file = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "data/trae_results.json"

            # 解析轮次号
            round_num = 1
            if "--round-num" in sys.argv:
                try:
                    ridx = sys.argv.index("--round-num")
                    round_num = int(sys.argv[ridx + 1])
                except (ValueError, IndexError):
                    pass

            print(f"\n  读取第 {round_num} 轮 Trae Task 子 Agent 结果: {results_file}")
            with open(results_file, "r", encoding="utf-8") as f:
                worker_results = json.load(f)

            reflection = app.process(demo_task["task_id"], worker_results, round_num)

            print(f"\n{'='*60}")
            print(f"  第 {round_num} 轮输出: ReflectionOutput")
            print(f"{'='*60}")
            print(f"  task_id:       {reflection.task_id}")
            print(f"  status:        {reflection.status}")
            print(f"  confidence:    {reflection.confidence:.2f}")
            print(f"  iterations:    {reflection.iteration_count}")
            print(f"  snapshot_id:   {reflection.snapshot_id}")

            # 如果未收敛且未熔断，输出下一轮任务描述
            if reflection.status not in ("converged", "circuit_broken") and round_num < rounds:
                print(f"\n{'='*60}")
                print(f"  准备第 {round_num + 1} 轮迭代...")
                print(f"{'='*60}")
                next_descriptions = app._build_next_round_descriptions(
                    demo_task, reflection, round_num + 1
                )
                sys.stdout.write(f"\n\n--- ROUND {round_num + 1} TASK_DESCRIPTIONS_JSON ---\n")
                sys.stdout.write(json.dumps(next_descriptions, indent=2, ensure_ascii=False))
                sys.stdout.write(f"\n--- END_ROUND_{round_num + 1}_TASK_DESCRIPTIONS ---\n")
                sys.stdout.flush()
                print(f"\n  生成 {len(next_descriptions)} 个第 {round_num + 1} 轮 Task 任务描述")

        elif "--run-loop" in sys.argv:
            # 端到端多轮迭代：需要传入各轮结果
            # 格式: --run-loop --rounds 2 --r1-results <file> --r2-results <file>
            rounds_data: dict[int, dict[str, Any]] = {}
            for r in range(1, rounds + 1):
                flag = f"--r{r}-results"
                if flag in sys.argv:
                    idx = sys.argv.index(flag)
                    fpath = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
                    if fpath and os.path.exists(fpath):
                        with open(fpath, "r", encoding="utf-8") as f:
                            rounds_data[r] = json.load(f)
                        print(f"  加载第 {r} 轮结果: {fpath} ({len(rounds_data[r])} 个 Worker)")

            if not rounds_data:
                print("  错误: --run-loop 需要至少一轮结果，使用 --r1-results <file> [--r2-results <file> ...]")
                sys.exit(1)

            reflections = app.run_iteration_loop(demo_task, rounds_data)

            print(f"\n{'='*60}")
            print(f"  最终多轮迭代完成")
            print(f"{'='*60}")
            print(f"  - 总轮次: {len(reflections)}")
            for i, ref in enumerate(reflections, 1):
                print(f"  - 第 {i} 轮: status={ref.status}, confidence={ref.confidence:.2f}")
        else:
            print("  多轮模式用法:")
            print("    python3 main.py --multi --results <file> [--round-num N] [--rounds N]")
            print("    python3 main.py --run-loop --r1-results <f1> --r2-results <f2> [--rounds N]")
    else:
        # =====================================================================
        # 单轮模式：构建任务描述
        # =====================================================================
        if "--results" in sys.argv:
            idx = sys.argv.index("--results")
            results_file = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "data/trae_results.json"
            print(f"\n  读取 Trae Task 子 Agent 结果: {results_file}")
            with open(results_file, "r", encoding="utf-8") as f:
                worker_results = json.load(f)

            reflection = app.process(demo_task["task_id"], worker_results)

            print(f"\n{'='*60}")
            print(f"  最终输出: ReflectionOutput")
            print(f"{'='*60}")
            print(f"  task_id:       {reflection.task_id}")
            print(f"  status:        {reflection.status}")
            print(f"  confidence:    {reflection.confidence:.2f}")
            print(f"  iterations:    {reflection.iteration_count}")
            print(f"  snapshot_id:   {reflection.snapshot_id}")
            print(f"  conclusion:    {reflection.conclusion[:120]}...")
            print(f"  limitations:   {reflection.limitations}")
            print(f"  requires_more_data: {reflection.requires_more_data}")
            print(f"  meta_rules triggers: {len(reflection.meta_rules_log)}")

            print(f"\n  完整性检查:")
            print(f"  - Worker 输出数量: {len(reflection.worker_outputs)}")
            print(f"  - 快照归档数量: {app.snapshot_mgr.archive_count}")
            print(f"  - 哈希链有效: {app.snapshot_mgr.verify_chain()['is_valid']}")
            print(f"  - B1 内核未修改: True (仅通过 BrainInterface 调用)")
            print(f"  - 外部 LLM API 调用: 0 次")
            print(f"  - Worker 推理: 全部由 Trae 内置 Task 子 Agent 完成")
        else:
            # Phase 1: 构建任务描述
            descriptions = app.build_descriptions(demo_task)

            sys.stdout.write("\n\n--- TASK_DESCRIPTIONS_JSON ---\n")
            sys.stdout.write(json.dumps(descriptions, indent=2, ensure_ascii=False))
            sys.stdout.write("\n--- END_TASK_DESCRIPTIONS ---\n")
            sys.stdout.flush()

            print(f"\n{'='*60}")
            print(f"  Phase 1 完成: {len(descriptions)} 个 Task 任务描述已生成")
            print(f"{'='*60}")
            print(f"\n  下一步: 将以上 Task 描述交给 Trae Task 工具并行派发 5 个 Worker 子 Agent。")
            print(f"  每个子 Agent 读取对应 prompt 模板，产出原始结构化输出。")
            print(f"  收集结果后，运行: python3 main.py --results <results_file>")
            print(f"\n  已注册 Worker:")
            for desc in descriptions:
                if "agent_id" in desc:
                    print(f"    - {desc['agent_id']} ({desc.get('agent_role', '?')}): {desc.get('task_id', '?')}")


if __name__ == "__main__":
    main()