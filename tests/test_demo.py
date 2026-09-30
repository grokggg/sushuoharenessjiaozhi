"""
tests.test_demo — 闭环 Demo 测试

验证完整 Orchestrator-Worker 集群 + Harness + B1 编排流程。
"""
import asyncio
import json
import pytest
from agents.lead_researcher import LeadResearcher
from agents.worker_perception import WorkerPerception
from agents.worker_hypothesis_builder import WorkerHypothesisBuilder
from agents.worker_skeptic import WorkerSkeptic
from agents.worker_red_team import WorkerRedTeam
from agents.worker_archivist import WorkerArchivist
from harness.orchestrator import Orchestrator
from harness.meta_rules import MetaRules
from harness.safety_validator import SafetyValidator
from harness.snapshot_archive import SnapshotArchive
from harness.structs import ReflectionOutput
from brain_subsystem.interface import BrainInterface


class TestClosedLoopDemo:
    """闭环 Demo：完整编排流程"""

    @pytest.mark.asyncio
    async def test_full_orchestration_with_harness(self):
        """
        Demo: 完整 Harness 编排流程

        场景：BrainOrchestratorApp 接收一个复合研究任务，
        编排者分解为 5 个子任务 → 分配 5 个 Worker → 收集输出
        → 安全校验 → 元规则处理 → 快照归档 → B1 仿真 → 最终输出
        """
        # 1. 初始化 Harness 模块
        meta_rules = MetaRules()
        validator = SafetyValidator()
        snapshot_mgr = SnapshotArchive(storage_path="/tmp/demo_snapshots")
        brain = BrainInterface()

        # 2. 初始化编排者并注册 5 个 Worker
        lead = LeadResearcher()
        lead.register_worker(WorkerPerception())
        lead.register_worker(WorkerHypothesisBuilder())
        lead.register_worker(WorkerSkeptic())
        lead.register_worker(WorkerRedTeam())
        lead.register_worker(WorkerArchivist())

        # 3. 初始化总调度器
        orchestrator = Orchestrator(
            lead_researcher=lead,
            meta_rules=meta_rules,
            validator=validator,
            snapshot_mgr=snapshot_mgr,
            brain=brain,
        )

        # 注册 Worker 到调度器
        for agent_id, worker in lead.worker_registry.items():
            orchestrator.register_worker(worker)

        assert len(orchestrator.registered_workers) == 5

        # 4. 构造顶层任务
        task = {
            "task_id": "demo_task_001",
            "task_type": "composite",
            "query": "LLM hallucination 根因分析",
        }

        # 5. Phase 1: 构建 Task 描述
        descriptions = orchestrator.build_task_descriptions(task)
        assert len(descriptions) >= 1

        # 6. 加载 mock Trae Task 子 Agent 结果
        import os
        results_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "trae_results.json"
        )
        with open(results_file, "r", encoding="utf-8") as f:
            worker_results = json.load(f)

        # 7. Phase 3: 处理结果
        result: ReflectionOutput = orchestrator.process_results(
            task["task_id"], worker_results
        )

        # 8. 验证 ReflectionOutput
        assert result.task_id == "demo_task_001"
        assert result.status in (
            "converged",
            "diverged",
            "circuit_broken",
            "evidence_insufficient",
            "needs_iteration",
        )
        assert result.created_at != ""
        assert result.iteration_count >= 1

        # 9. 验证快照归档
        assert result.snapshot_id != ""
        assert snapshot_mgr.archive_count >= 1

        # 10. 验证哈希链完整性
        chain = snapshot_mgr.verify_chain()
        assert chain["is_valid"]

        print(f"\nDemo 闭环测试通过!")
        print(f"   - 任务 ID: {result.task_id}")
        print(f"   - 收敛状态: {result.status}")
        print(f"   - 迭代轮数: {result.iteration_count}")
        print(f"   - 置信度: {result.confidence:.2f}")
        print(f"   - 快照 ID: {result.snapshot_id}")
        print(f"   - 哈希链: {'有效' if chain['is_valid'] else '损坏'}")


if __name__ == "__main__":
    asyncio.run(TestClosedLoopDemo().test_full_orchestration_with_harness())