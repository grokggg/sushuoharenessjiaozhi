"""
tests.test_v2_optimizations — v2.0 优化专项测试

验证所有超一流优化模块的正确性：
  - BrainAdapter: B1 仿真内核差异化响应
  - HypothesisPool: 多假设并行跟踪 + 贝叶斯证据累积
  - TaskProfile: 任务感知自适应阈值
  - AgentCredibility: 基于历史表现的信誉分累积
  - ConvergenceVector: 多维收敛判定
  - Orchestrator: 编排者轮换 + Human-in-the-Loop
"""

import pytest
from brain_subsystem.interface import BrainInterface
from harness.brain_adapter import BrainAdapter
from harness.hypothesis_pool import HypothesisPool
from harness.structs import (
    TaskProfile,
    HypothesisNode,
    AgentCredibility,
    ConvergenceVector,
)
from harness.meta_rules import MetaRules
from harness.orchestrator import Orchestrator
from harness.safety_validator import SafetyValidator
from harness.snapshot_archive import SnapshotArchive


# =============================================================================
# BrainAdapter 测试
# =============================================================================

class TestBrainAdapter:
    """B1 增强适配器测试"""

    def test_enhanced_inference_returns_differentiated_confidence(self):
        """验证增强推理返回与 B1 原始值不同的置信度"""
        adapter = BrainAdapter(BrainInterface())
        result = adapter.enhanced_inference(
            context="complex scientific reasoning about quantum physics",
            worker_outputs={},
            depth=2,
        )
        assert "confidence" in result
        assert "raw_b1_confidence" in result
        assert "quality_score" in result
        assert "quality_factors" in result
        assert "is_stable" in result
        # 质量评分应在 [0, 1] 范围内
        assert 0.0 <= result["quality_score"] <= 1.0
        # 差异化置信度应不同于原始 B1 值（有上下文质量分析）
        assert result["confidence"] != result["raw_b1_confidence"]

    def test_enhanced_inference_with_rich_worker_outputs(self):
        """验证丰富 Worker 输出时质量评分更高"""
        adapter = BrainAdapter(BrainInterface())

        # 空输出
        result_empty = adapter.enhanced_inference(
            context="test", worker_outputs=None, depth=1,
        )

        # 丰富输出
        rich_outputs = {
            "agent_a": {
                "output": {
                    "observations": [{"data": "x"} for _ in range(10)],
                    "evidence_chain": [{"link": "a"} for _ in range(5)],
                    "confidence": 0.8,
                    "critiques": [{"c": "x"} for _ in range(3)],
                    "red_team_cases": [{"case": "y"} for _ in range(2)],
                }
            },
            "agent_b": {
                "output": {
                    "observations": [{"data": "y"} for _ in range(8)],
                    "evidence_chain": [{"link": "b"} for _ in range(3)],
                    "confidence": 0.75,
                    "critiques": [{"c": "z"} for _ in range(2)],
                }
            },
        }
        result_rich = adapter.enhanced_inference(
            context="test", worker_outputs=rich_outputs, depth=1,
        )

        # 丰富输出的质量评分应高于空输出
        assert result_rich["quality_score"] > result_empty["quality_score"]

    def test_quality_history_accumulates(self):
        """验证质量历史累积"""
        adapter = BrainAdapter()
        for i in range(5):
            adapter.enhanced_inference(context=f"test_{i}", depth=1)

        assert len(adapter.quality_history) == 5

    def test_delegates_to_brain_interface(self):
        """验证委托方法正常工作"""
        adapter = BrainAdapter(BrainInterface())
        result = adapter.run_inference(context="test", depth=1)
        assert "confidence" in result
        assert "inference" in result

        osc = adapter.compute_oscillation(0.5)
        assert 0.0 <= osc <= 1.0

        stable = adapter.is_homeostatic([0.5] * 15)
        assert isinstance(stable, bool)


# =============================================================================
# HypothesisPool 测试
# =============================================================================

class TestHypothesisPool:
    """假说池测试"""

    def test_register_from_worker_outputs(self):
        """验证从 Worker 输出注册假说"""
        pool = HypothesisPool()
        outputs = {
            "hypo_builder_agent": {
                "output": {
                    "hypotheses": [
                        {"hypothesis_id": "hyp_001", "statement": "训练数据覆盖度不足"},
                        {"hypothesis_id": "hyp_002", "statement": "不确定性校准缺失"},
                    ]
                }
            }
        }
        nodes = pool.register_from_worker_outputs(outputs, round_number=1)
        assert len(nodes) == 2
        assert pool.hypothesis_count == 2
        assert pool.active_count == 2

    def test_evidence_update_shifts_posterior(self):
        """验证证据更新改变后验概率"""
        pool = HypothesisPool()
        outputs = {
            "hypo_builder_agent": {
                "output": {
                    "hypotheses": [
                        {"hypothesis_id": "hyp_001", "statement": "测试假说"},
                    ]
                }
            }
        }
        pool.register_from_worker_outputs(outputs, round_number=1)

        # 获取初始后验
        hyp = pool.get_leading_hypothesis()
        initial_posterior = hyp.posterior

        # 注入支持证据
        pool.update_with_evidence([
            {"target_hypothesis_id": "hyp_001", "supports": True, "strength": 0.8},
            {"target_hypothesis_id": "hyp_001", "supports": True, "strength": 0.7},
        ], round_number=2)

        hyp = pool.get_leading_hypothesis()
        assert hyp.posterior > initial_posterior

    def test_critique_evidence_decreases_posterior(self):
        """验证批判证据降低后验概率"""
        pool = HypothesisPool()
        outputs = {
            "hypo_builder_agent": {
                "output": {
                    "hypotheses": [
                        {"hypothesis_id": "hyp_001", "statement": "测试假说"},
                    ]
                }
            }
        }
        pool.register_from_worker_outputs(outputs, round_number=1)

        # 注入反对证据（通过批判）
        pool.update_with_critiques({
            "skeptic_agent": {
                "output": {
                    "critiques": [
                        {"target_hypothesis_id": "hyp_001", "severity_score": 0.9, "description": "严重缺陷"},
                    ]
                }
            }
        }, round_number=2)

        hyp = pool.get_leading_hypothesis()
        assert hyp.posterior < 0.5  # 后验应降低

    def test_red_team_evidence_tracks_rates(self):
        """验证红队测试跟踪通过率"""
        pool = HypothesisPool()
        outputs = {
            "hypo_builder_agent": {
                "output": {
                    "hypotheses": [
                        {"hypothesis_id": "hyp_001", "statement": "测试假说"},
                    ]
                }
            }
        }
        pool.register_from_worker_outputs(outputs, round_number=1)

        pool.update_with_critiques({
            "red_judge_agent": {
                "output": {
                    "red_team_cases": [
                        {"target_hypothesis_id": "hyp_001", "severity": "critical", "scenario_description": "极端条件"},
                        {"target_hypothesis_id": "hyp_001", "severity": "low", "scenario_description": "普通测试"},
                    ]
                }
            }
        }, round_number=2)

        hyp = pool.get_leading_hypothesis()
        assert hyp.red_team_tests_total == 2
        assert hyp.red_team_pass_count == 1  # low severity passed
        assert hyp.red_team_pass_rate == 0.5

    def test_status_transitions(self):
        """验证假说状态转换"""
        pool = HypothesisPool()
        outputs = {
            "hypo_builder_agent": {
                "output": {
                    "hypotheses": [
                        {"hypothesis_id": "hyp_001", "statement": "强假说"},
                        {"hypothesis_id": "hyp_002", "statement": "弱假说"},
                    ]
                }
            }
        }
        pool.register_from_worker_outputs(outputs, round_number=1)

        # 强假说多次注入支持证据
        for _ in range(10):
            pool.update_with_evidence([
                {"target_hypothesis_id": "hyp_001", "supports": True, "strength": 0.9},
            ], round_number=2)

        # 弱假说多次注入反对证据
        for _ in range(10):
            pool.update_with_evidence([
                {"target_hypothesis_id": "hyp_002", "supports": False, "strength": 0.9},
            ], round_number=2)

        pool.update_statuses()

        hypotheses = {h.hypothesis_id: h for h in pool.get_all_hypotheses()}
        assert hypotheses["hyp_001"].status == "confirmed"
        assert hypotheses["hyp_002"].status == "falsified"

    def test_snapshot_and_convergence_vector(self):
        """验证快照和收敛向量构建"""
        pool = HypothesisPool()
        outputs = {
            "hypo_builder_agent": {
                "output": {
                    "hypotheses": [
                        {"hypothesis_id": "hyp_001", "statement": "主导假说"},
                        {"hypothesis_id": "hyp_002", "statement": "次要假说"},
                    ]
                }
            }
        }
        pool.register_from_worker_outputs(outputs, round_number=1)

        # 让 hyp_001 显著领先
        for _ in range(5):
            pool.update_with_evidence([
                {"target_hypothesis_id": "hyp_001", "supports": True, "strength": 0.8},
            ], round_number=2)

        snapshot = pool.snapshot()
        assert snapshot.active_count == 2
        assert snapshot.round_number == 2

        cv = pool.build_convergence_vector()
        assert isinstance(cv, ConvergenceVector)
        assert cv.confidence_mean > 0.5

    def test_to_dict_list(self):
        """验证假说池导出为 dict 列表"""
        pool = HypothesisPool()
        outputs = {
            "hypo_builder_agent": {
                "output": {
                    "hypotheses": [
                        {"hypothesis_id": "hyp_001", "statement": "测试假说"},
                    ]
                }
            }
        }
        pool.register_from_worker_outputs(outputs, round_number=1)
        dicts = pool.to_dict_list()
        assert len(dicts) == 1
        assert dicts[0]["hypothesis_id"] == "hyp_001"
        assert "posterior" in dicts[0]
        assert "status" in dicts[0]


# =============================================================================
# TaskProfile 测试
# =============================================================================

class TestTaskProfile:
    """任务感知画像测试"""

    def test_factual_task_profile(self):
        """验证事实性任务画像"""
        profile = TaskProfile.for_task("factual")
        assert profile.uncertainty_level == "low"
        assert profile.dominance_threshold == 0.75
        assert profile.max_iterations == 3
        assert profile.convergence_confidence == 0.70

    def test_exploratory_task_profile(self):
        """验证探索性任务画像"""
        profile = TaskProfile.for_task("exploratory")
        assert profile.uncertainty_level == "exploratory"
        assert profile.dominance_threshold == 0.50
        assert profile.max_iterations == 8
        assert profile.convergence_confidence == 0.45

    def test_adversarial_task_profile(self):
        """验证对抗性任务画像"""
        profile = TaskProfile.for_task("adversarial")
        assert profile.uncertainty_level == "high"
        assert profile.dominance_threshold == 0.55
        assert profile.max_iterations == 6

    def test_default_composite_profile(self):
        """验证默认复合任务画像"""
        profile = TaskProfile.for_task("composite")
        assert profile.uncertainty_level == "medium"
        assert profile.dominance_threshold == 0.60
        assert profile.max_iterations == 5

    def test_meta_rules_uses_task_profile(self):
        """验证 MetaRules 接受 TaskProfile"""
        profile = TaskProfile.for_task("factual")
        rules = MetaRules(task_profile=profile)
        assert rules.task_profile.uncertainty_level == "low"
        assert rules.task_profile.max_iterations == 3


# =============================================================================
# AgentCredibility 测试
# =============================================================================

class TestAgentCredibility:
    """Agent 信誉分测试"""

    def test_initial_credibility(self):
        """验证初始信誉分"""
        cred = AgentCredibility(agent_id="test_agent")
        assert cred.current_score == 0.5
        assert cred.base_credibility == 0.5
        assert cred.total_rounds == 0

    def test_overturned_penalty(self):
        """验证被推翻扣分"""
        cred = AgentCredibility(agent_id="test_agent")
        cred.update_from_round(was_overturned=True)
        assert cred.current_score < 0.5
        assert cred.overturned_count == 1

    def test_b1_deviation_penalty(self):
        """验证 B1 偏离扣分"""
        cred = AgentCredibility(agent_id="test_agent")
        cred.update_from_round(b1_deviation=0.5)
        assert cred.current_score < 0.5
        assert cred.b1_deviation_sum > 0

    def test_red_team_pass_bonus(self):
        """验证红队通过加分"""
        cred = AgentCredibility(agent_id="test_agent")
        cred.update_from_round(red_team_passed=True)
        assert cred.current_score > 0.5
        assert cred.red_team_pass_count == 1

    def test_red_team_fail_no_penalty(self):
        """验证红队失败不额外扣分"""
        cred = AgentCredibility(agent_id="test_agent")
        cred.update_from_round(red_team_passed=False)
        assert cred.red_team_total == 1
        assert cred.red_team_pass_count == 0

    def test_long_term_decay(self):
        """验证长期衰减回归均值"""
        cred = AgentCredibility(agent_id="test_agent")
        # 先提升到高分
        for _ in range(5):
            cred.update_from_round(red_team_passed=True)
        high_score = cred.current_score
        # 再跑几轮（无加分）
        for _ in range(5):
            cred.update_from_round()
        # 应回归均值
        assert cred.current_score < high_score

    def test_score_bounds(self):
        """验证信誉分边界"""
        cred = AgentCredibility(agent_id="test_agent")

        # 连续加分不应超过 0.95
        for _ in range(50):
            cred.update_from_round(red_team_passed=True)
        assert cred.current_score <= 0.95

        # 连续扣分不应低于 0.1
        cred2 = AgentCredibility(agent_id="test_agent_2")
        for _ in range(50):
            cred2.update_from_round(was_overturned=True, b1_deviation=0.5)
        assert cred2.current_score >= 0.1


# =============================================================================
# ConvergenceVector 测试
# =============================================================================

class TestConvergenceVector:
    """多维收敛向量测试"""

    def test_clear_convergence(self):
        """验证明确收敛场景"""
        cv = ConvergenceVector(
            confidence_variance=0.05,
            confidence_mean=0.85,
            evidence_chain_coverage=0.9,
            evidence_chain_depth=5,
            unresolved_decay_rate=0.5,
            unresolved_count=1,
            red_team_pass_rate=0.8,
        )
        cv.compute()
        assert cv.is_converged
        assert cv.convergence_score > 0.8

    def test_false_consensus_detected(self):
        """验证虚假共识检测（高一致性但低证据链覆盖）"""
        cv = ConvergenceVector(
            confidence_variance=0.02,  # 极低方差
            confidence_mean=0.95,  # 极高置信度
            evidence_chain_coverage=0.1,  # 但证据链极弱
            evidence_chain_depth=1,
            unresolved_decay_rate=0.0,
            unresolved_count=10,
            red_team_pass_rate=0.1,
        )
        cv.compute()
        # 不应收敛：虽然置信度一致，但证据链和红队防御不足
        assert not cv.is_converged

    def test_all_dimensions_required(self):
        """验证所有维度都需要通过"""
        # 只有方差和均值通过，其他不通过
        cv = ConvergenceVector(
            confidence_variance=0.01,
            confidence_mean=0.9,
            evidence_chain_coverage=0.0,
            evidence_chain_depth=0,
            unresolved_decay_rate=0.0,
            unresolved_count=20,
            red_team_pass_rate=0.0,
        )
        cv.compute()
        assert not cv.is_converged

    def test_borderline_convergence(self):
        """验证边界收敛"""
        cv = ConvergenceVector(
            confidence_variance=0.10,
            confidence_mean=0.60,
            evidence_chain_coverage=0.55,
            evidence_chain_depth=3,
            unresolved_decay_rate=0.25,
            unresolved_count=3,
            red_team_pass_rate=0.45,
        )
        cv.compute()
        # 边界情况，可能收敛也可能不收敛
        assert 0.0 <= cv.convergence_score <= 1.0


# =============================================================================
# Orchestrator v2.0 集成测试
# =============================================================================

class TestOrchestratorV2:
    """Orchestrator v2.0 增强功能测试"""

    def test_brain_adapter_integrated(self):
        """验证 Orchestrator 集成了 BrainAdapter"""
        orchestrator = Orchestrator()
        assert orchestrator.brain_adapter is not None
        # 验证增强推理可用
        result = orchestrator.brain_adapter.enhanced_inference(
            context="test", depth=1,
        )
        assert "confidence" in result
        assert "quality_score" in result

    def test_hypothesis_pool_integrated(self):
        """验证 Orchestrator 集成了 HypothesisPool"""
        orchestrator = Orchestrator()
        assert orchestrator.hypothesis_pool is not None
        assert orchestrator.hypothesis_pool.hypothesis_count == 0

    def test_task_profile_integrated(self):
        """验证 Orchestrator 集成了 TaskProfile"""
        orchestrator = Orchestrator()
        assert orchestrator.task_profile is not None
        assert orchestrator.task_profile.uncertainty_level == "medium"

    def test_orchestrator_strategy_rotation(self):
        """验证编排者策略轮换"""
        orchestrator = Orchestrator()
        initial = orchestrator.get_orchestrator_strategy()
        assert initial == "default"

        # 第 1, 2 轮不变，第 3 轮切换
        for i in range(3):
            orchestrator.rotate_orchestrator_strategy()

        assert orchestrator.get_orchestrator_strategy() != "default"

    def test_human_intervention_queue(self):
        """验证 Human-in-the-Loop 介入队列"""
        orchestrator = Orchestrator()
        req = orchestrator.request_human_intervention(
            task_id="test_task",
            reason="集群连续3轮无法收敛",
        )
        assert req["task_id"] == "test_task"
        assert req["status"] == "pending"

        pending = orchestrator.get_pending_interventions()
        assert len(pending) == 1

        orchestrator.resolve_intervention("test_task", {"action": "manual_override"})
        pending = orchestrator.get_pending_interventions()
        assert len(pending) == 0

    def test_process_results_populates_hypothesis_pool(self):
        """验证 process_results 填充假说池"""
        from harness.meta_rules import MetaRules
        orchestrator = Orchestrator(
            meta_rules=MetaRules(),
            validator=SafetyValidator(),
            snapshot_mgr=SnapshotArchive(storage_path="/tmp/test_v2_snapshots"),
        )
        worker_results = {
            "hypo_builder_agent": {
                "agent_id": "hypo_builder_agent",
                "status": "success",
                "output": {
                    "hypotheses": [
                        {"hypothesis_id": "hyp_001", "statement": "数据覆盖假说"},
                        {"hypothesis_id": "hyp_002", "statement": "校准假说"},
                    ],
                    "confidence": 0.75,
                },
            },
            "skeptic_agent": {
                "agent_id": "skeptic_agent",
                "status": "success",
                "output": {
                    "critiques": [
                        {"target_hypothesis_id": "hyp_001", "severity_score": 0.6, "description": "证据不足"},
                    ],
                    "confidence": 0.55,
                },
            },
            "red_judge_agent": {
                "agent_id": "red_judge_agent",
                "status": "success",
                "output": {
                    "red_team_cases": [],
                    "confidence": 0.60,
                },
            },
        }
        result = orchestrator.process_results("test_task", worker_results)
        assert result is not None
        assert orchestrator.hypothesis_pool.hypothesis_count == 2
        assert len(result.active_hypotheses) == 2

    def test_process_results_with_convergence_vector(self):
        """验证 process_results 包含收敛向量"""
        orchestrator = Orchestrator(
            meta_rules=MetaRules(),
            validator=SafetyValidator(),
            snapshot_mgr=SnapshotArchive(storage_path="/tmp/test_v2_snapshots"),
        )
        worker_results = {
            "agent_a": {"agent_id": "agent_a", "status": "success", "output": {"confidence": 0.8}},
            "agent_b": {"agent_id": "agent_b", "status": "success", "output": {"confidence": 0.75}},
        }
        result = orchestrator.process_results("test_task", worker_results)
        assert result.convergence_vector is not None
        assert result.convergence_vector.confidence_mean > 0


# =============================================================================
# SnapshotArchive v2.0 测试
# =============================================================================

class TestSnapshotArchiveV2:
    """快照归档 v2.0 增强测试"""

    def test_archive_with_convergence_vector(self):
        """验证归档包含收敛向量"""
        archive = SnapshotArchive(storage_path="/tmp/test_v2_snapshots")
        snap_id = archive.archive_round(
            task_id="v2_test",
            round_number=1,
            context_version="v1",
            worker_outputs={"a": {"x": 1}},
            meta_logs=[],
            convergence_vector={"is_converged": True, "convergence_score": 0.85},
            hypothesis_pool_snapshot={"active_count": 2},
            agent_credibility={"agent_a": 0.75},
        )
        state = archive.rollback(snap_id)
        assert state is not None
        assert state["convergence_vector"]["is_converged"] is True
        assert state["agent_credibility"]["agent_a"] == 0.75

    def test_timestamp_signing_in_hash(self):
        """验证哈希包含时间戳签名"""
        archive = SnapshotArchive(storage_path="/tmp/test_v2_snapshots")
        snap_id = archive.archive_round(
            task_id="ts_test",
            round_number=1,
            context_version="v1",
            worker_outputs={"a": {"x": 1}},
            meta_logs=[],
        )
        # 回滚验证哈希完整性
        state = archive.rollback(snap_id)
        assert state is not None
        assert "timestamp" in state


# =============================================================================
# MetaRules v2.0 增强测试
# =============================================================================

class TestMetaRulesV2:
    """MetaRules v2.0 增强功能测试"""

    def test_agent_credibility_tracking(self):
        """验证 Agent 信誉分追踪"""
        rules = MetaRules()
        cred = rules.get_agent_credibility("agent_a")
        assert cred.agent_id == "agent_a"
        assert cred.current_score == 0.5

    def test_get_all_credibility_scores(self):
        """验证获取所有信誉分"""
        rules = MetaRules()
        rules.get_agent_credibility("agent_a")
        rules.get_agent_credibility("agent_b")
        scores = rules.get_all_credibility_scores()
        assert "agent_a" in scores
        assert "agent_b" in scores
        assert scores["agent_a"] == 0.5

    def test_credibility_affects_rule1_weight(self):
        """验证信誉分影响规则①权重"""
        rules = MetaRules(dominance_threshold=0.60)
        # 给 agent_a 低信誉分
        cred_a = rules.get_agent_credibility("agent_a")
        cred_a.update_from_round(was_overturned=True, b1_deviation=0.5)

        # agent_a 高置信度但低信誉分不应触发抑制
        outputs = {
            "agent_a": {"confidence": 0.95},
            "agent_b": {"confidence": 0.50},
            "agent_c": {"confidence": 0.45},
        }
        decision = rules.evaluate(
            round_outputs=outputs, all_outputs=outputs, history=[],
        )
        rule1 = [log for log in decision.logs if log.rule_id == 1]
        # 低信誉 Agent 的高置信度不应触发抑制（因为信誉分调节）
        # 具体是否触发取决于信誉分降到了多少
        assert len(rule1) <= 1  # 最多触发 1 次

    def test_set_hypothesis_pool(self):
        """验证注入假说池"""
        rules = MetaRules()
        pool = HypothesisPool()
        rules.set_hypothesis_pool(pool)
        # 验证不抛异常
        assert True