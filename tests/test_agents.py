"""
tests.test_agents — Agents 编排者-工作者单元测试

验证 LeadResearcher 编排和 5 个 Worker 执行流程。
每个 Worker 加载 prompt 模板，产出 Mock 原始输出。
"""

import pytest
from agents.lead_researcher import LeadResearcher
from agents.worker_perception import WorkerPerception
from agents.worker_hypothesis_builder import WorkerHypothesisBuilder
from agents.worker_skeptic import WorkerSkeptic
from agents.worker_red_team import WorkerRedTeam
from agents.worker_archivist import WorkerArchivist
from agents.base_worker import TaskResult, TaskDescription


class TestLeadResearcher:
    """编排者测试"""

    def test_register_worker(self):
        lead = LeadResearcher()
        worker = WorkerPerception()
        lead.register_worker(worker)
        assert "collect_agent" in lead.worker_registry

    def test_prompt_loaded(self):
        lead = LeadResearcher()
        assert len(lead.prompt_template) > 0
        assert "编排者" in lead.prompt_template

    def test_task_decomposition_explicit_subtasks(self):
        lead = LeadResearcher()
        task = {
            "task_id": "t1",
            "subtasks": [
                {"task_id": "st1", "task_type": "perception"},
                {"task_id": "st2", "task_type": "hypothesis_building"},
            ],
        }
        subtasks = lead.decompose_task(task)
        assert len(subtasks) == 2

    def test_task_decomposition_auto(self):
        """测试自动分解：composite 类型生成完整流水线"""
        lead = LeadResearcher()
        task = {"task_id": "t1", "task_type": "composite", "query": "test"}
        subtasks = lead.decompose_task(task)
        assert len(subtasks) == 5
        types = [s["task_type"] for s in subtasks]
        assert "perception" in types
        assert "hypothesis_building" in types
        assert "skepticism" in types
        assert "red_team" in types
        assert "archiving" in types

    def test_worker_assignment(self):
        lead = LeadResearcher()
        assert lead.assign_worker({"task_type": "perception"}) == "collect_agent"
        assert lead.assign_worker({"task_type": "hypothesis_building"}) == "hypo_builder_agent"
        assert lead.assign_worker({"task_type": "skepticism"}) == "skeptic_agent"
        assert lead.assign_worker({"task_type": "red_team"}) == "red_judge_agent"
        assert lead.assign_worker({"task_type": "archiving"}) == "archive_agent"

    def test_result_aggregation(self):
        """测试编排者聚合结果（execute 方法返回聚合 dict）"""
        lead = LeadResearcher()
        lead.register_worker(WorkerPerception())
        lead.register_worker(WorkerHypothesisBuilder())
        lead.register_worker(WorkerSkeptic())
        lead.register_worker(WorkerRedTeam())
        lead.register_worker(WorkerArchivist())

        import asyncio
        task = {"task_id": "test_agg", "task_type": "composite", "query": "test"}
        result = asyncio.run(lead.execute(task))
        assert result["status"] == "success"
        assert result["subtask_count"] == 5


class TestWorkers:
    """工作者 Worker 测试 — 均返回 TaskDescription 对象"""

    @pytest.mark.asyncio
    async def test_perception(self):
        worker = WorkerPerception()
        assert len(worker.prompt_template) > 0
        result: TaskDescription = await worker.execute({"task_id": "t1", "query": "test"})
        assert result.agent_id == "collect_agent"
        assert result.task_type == "perception"
        assert result.task_id == "t1"

    @pytest.mark.asyncio
    async def test_hypothesis_builder(self):
        worker = WorkerHypothesisBuilder()
        assert len(worker.prompt_template) > 0
        result: TaskDescription = await worker.execute({"task_id": "t1", "query": "test"})
        assert result.agent_id == "hypo_builder_agent"
        assert result.task_type == "hypothesis_building"
        assert result.task_id == "t1"

    @pytest.mark.asyncio
    async def test_skeptic(self):
        worker = WorkerSkeptic()
        assert len(worker.prompt_template) > 0
        result: TaskDescription = await worker.execute({"task_id": "t1"})
        assert result.agent_id == "skeptic_agent"
        assert result.task_type == "skepticism"

    @pytest.mark.asyncio
    async def test_red_team(self):
        worker = WorkerRedTeam()
        assert len(worker.prompt_template) > 0
        result: TaskDescription = await worker.execute({"task_id": "t1"})
        assert result.agent_id == "red_judge_agent"
        assert result.task_type == "red_team"

    @pytest.mark.asyncio
    async def test_archivist(self):
        worker = WorkerArchivist()
        assert len(worker.prompt_template) > 0
        result: TaskDescription = await worker.execute({
            "task_id": "t1",
            "round_number": 1,
            "worker_outputs": {"agent_a": {}, "agent_b": {}},
        })
        assert result.agent_id == "archive_agent"
        assert result.task_type == "archiving"


class TestLeadResearcherExecute:
    """编排者完整执行测试"""

    @pytest.mark.asyncio
    async def test_full_orchestration(self):
        lead = LeadResearcher()
        lead.register_worker(WorkerPerception())
        lead.register_worker(WorkerHypothesisBuilder())
        lead.register_worker(WorkerSkeptic())
        lead.register_worker(WorkerRedTeam())
        lead.register_worker(WorkerArchivist())

        task = {"task_id": "test_001", "task_type": "composite", "query": "测试任务"}
        result = await lead.execute(task)
        assert result["status"] == "success"
        assert result["subtask_count"] == 5
        assert len(result["worker_outputs"]) == 5
        assert "不做最终裁决" in result["note"]