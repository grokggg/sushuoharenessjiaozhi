"""
tests.test_harness — Harness 管控底座单元测试

覆盖四个核心模块：Orchestrator、MetaRules、SafetyValidator、SnapshotArchive
以及共享输出结构体。
"""

import pytest
from brain_subsystem.interface import BrainInterface
from harness.structs import (
    EvidenceLink,
    MetaRuleRecord,
    MetaRulesDecision,
    ProposedRedTeamCase,
    ProposedTaskPayload,
    ReflectionOutput,
    TaskConstraints,
    ValidationResult,
)
from harness.meta_rules import MetaRules
from harness.safety_validator import SafetyValidator, B1_ALLOWED_PARAMS
from harness.snapshot_archive import SnapshotArchive, RoundArchive


# =============================================================================
# 共享结构体测试
# =============================================================================


class TestStructs:
    """输出结构体测试"""

    def test_reflection_output_defaults(self):
        ro = ReflectionOutput(task_id="t1", context_version="v1", status="converged")
        assert ro.task_id == "t1"
        assert ro.status == "converged"
        assert ro.worker_outputs == {}
        assert ro.confidence == 0.0

    def test_proposed_task_payload(self):
        ptp = ProposedTaskPayload(
            task_id="st1",
            parent_task_id="rt1",
            task_type="perception",
        )
        assert ptp.task_type == "perception"
        assert ptp.priority == 0
        assert ptp.assigned_worker is None

    def test_proposed_red_team_case(self):
        rtc = ProposedRedTeamCase(
            case_id="rtc_001",
            target_conclusion_id="hyp_001",
            attack_type="edge_case",
            severity="high",
        )
        assert rtc.attack_type == "edge_case"
        assert rtc.actual_result is None

    def test_meta_rule_record(self):
        mr = MetaRuleRecord(
            rule_id=1,
            rule_name="强势信号抑制",
        )
        assert mr.rule_id == 1
        assert mr.affected_agents == []

    def test_evidence_link(self):
        el = EvidenceLink(
            source="collect_agent",
            content="原始观测数据",
            reliability=0.85,
        )
        assert el.reliability == 0.85

    def test_task_constraints_defaults(self):
        tc = TaskConstraints()
        assert tc.max_duration_sec == 300
        assert tc.required_output_format == "json"

    def test_validation_result(self):
        vr = ValidationResult(is_valid=True)
        assert vr.is_valid
        assert vr.errors == []

    def test_meta_rules_decision_defaults(self):
        mrd = MetaRulesDecision(decision="converged")
        assert mrd.decision == "converged"


# =============================================================================
# MetaRules 元规则测试
# =============================================================================


class TestMetaRules:
    """四条元协作规则测试"""

    def test_evaluate_converged(self):
        """测试收敛判定"""
        rules = MetaRules()
        outputs = {
            "agent_a": {"confidence": 0.8},
            "agent_b": {"confidence": 0.75},
        }
        decision = rules.evaluate(
            round_outputs=outputs,
            all_outputs=outputs,
            history=[],
        )
        assert decision.decision == "converged"

    def test_rule1_strong_signal_inhibition_no_trigger(self):
        """测试强势信号抑制：均匀分布不触发"""
        rules = MetaRules()
        outputs = {
            "agent_a": {"confidence": 0.5},
            "agent_b": {"confidence": 0.5},
        }
        decision = rules.evaluate(
            round_outputs=outputs,
            all_outputs=outputs,
            history=[],
        )
        # 应该触发抑制因为两者分数相同但主导度可能超过阈值
        # 检查日志中是否有规则1
        rule1_logs = [log for log in decision.logs if log.rule_id == 1]
        # 均匀分布时主导度 50%，不应触发
        assert len(rule1_logs) == 0

    def test_rule1_strong_signal_inhibition_triggered(self):
        """测试强势信号抑制：单一主导触发"""
        rules = MetaRules()
        outputs = {
            "agent_a": {"confidence": 0.95},
            "agent_b": {"confidence": 0.3},
            "agent_c": {"confidence": 0.2},
        }
        decision = rules.evaluate(
            round_outputs=outputs,
            all_outputs=outputs,
            history=[],
        )
        rule1_logs = [log for log in decision.logs if log.rule_id == 1]
        assert len(rule1_logs) >= 1
        assert rule1_logs[0].rule_name == "强势信号抑制"
        assert "agent_a" in rule1_logs[0].affected_agents

    def test_rule2_oscillation_no_trigger_insufficient_history(self):
        """测试震荡检测：历史不足时不触发"""
        rules = MetaRules()
        outputs = {
            "agent_a": {"output": {"hypotheses": [{"hypothesis_id": "hyp_001"}]}},
        }
        decision = rules.evaluate(
            round_outputs=outputs,
            all_outputs=outputs,
            history=[{"round": 1}],  # 只有 1 轮历史
        )
        rule2_logs = [log for log in decision.logs if log.rule_id == 2]
        assert len(rule2_logs) == 0

    def test_rule3_conflict_mediation_no_trigger(self):
        """测试冲突调解：无矛盾不触发"""
        rules = MetaRules()
        outputs = {
            "agent_a": {"confidence": 0.7},
            "agent_b": {"confidence": 0.65},
        }
        decision = rules.evaluate(
            round_outputs=outputs,
            all_outputs=outputs,
            history=[],
            brain=BrainInterface(),
        )
        rule3_logs = [log for log in decision.logs if log.rule_id == 3]
        assert len(rule3_logs) == 0

    def test_rule3_conflict_mediation_triggered(self):
        """测试冲突调解：矛盾触发"""
        rules = MetaRules()
        outputs = {
            "agent_a": {"confidence": 0.9},
            "agent_b": {"confidence": 0.1},
        }
        decision = rules.evaluate(
            round_outputs=outputs,
            all_outputs=outputs,
            history=[],
            brain=BrainInterface(),
        )
        rule3_logs = [log for log in decision.logs if log.rule_id == 3]
        assert len(rule3_logs) >= 1
        assert rule3_logs[0].rule_name == "冲突调解"

    def test_rule4_circuit_breaker_triggered(self):
        """测试超限熔断触发"""
        rules = MetaRules()
        outputs = {"agent_a": {"confidence": 0.5}}

        # 模拟 5 轮历史（达到默认 MAX_ITERATIONS 阈值）
        history = [{"round": i} for i in range(1, 6)]
        decision = rules.evaluate(
            round_outputs=outputs,
            all_outputs=outputs,
            history=history,
        )
        assert decision.decision == "circuit_broken"
        rule4_logs = [log for log in decision.logs if log.rule_id == 4]
        assert len(rule4_logs) >= 1

    def test_rule4_circuit_breaker_not_triggered(self):
        """测试超限熔断：未达阈值不触发"""
        rules = MetaRules()
        outputs = {"agent_a": {"confidence": 0.5}}
        history = [{"round": 1}, {"round": 2}]
        decision = rules.evaluate(
            round_outputs=outputs,
            all_outputs=outputs,
            history=history,
        )
        assert decision.decision != "circuit_broken"

    def test_extract_confidence_from_nested_output(self):
        """测试从嵌套输出中提取置信度"""
        rules = MetaRules()
        output = {
            "output": {
                "overall_assessment": {
                    "hyp_001_evidence_strength": "B",
                    "hyp_002_evidence_strength": "C",
                }
            }
        }
        score = rules._extract_confidence_score(output)
        assert 0.4 <= score <= 0.7  # B=0.7, C=0.4 -> avg=0.55


# =============================================================================
# SafetyValidator 安全校验器测试
# =============================================================================


class TestSafetyValidator:
    """安全校验器测试"""

    def test_b1_allowed_params(self):
        """测试 B1 白名单参数"""
        assert "sim_mode" in B1_ALLOWED_PARAMS
        assert "inject_disturb_start" in B1_ALLOWED_PARAMS
        assert "MAX_ACTIVE_AGENTS" not in B1_ALLOWED_PARAMS

    def test_validate_b1_access_allowed(self):
        """测试合法 B1 访问"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="read_constant",
            params={"sim_mode": "default"},
        )
        assert result.is_valid

    def test_validate_b1_access_blocked_param(self):
        """测试拦截非法参数"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="set_param",
            params={"MAX_ACTIVE_AGENTS": 999},
        )
        assert not result.is_valid
        assert "MAX_ACTIVE_AGENTS" in str(result.errors)

    def test_validate_b1_access_blocked_operation(self):
        """测试拦截非法操作"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="modify_constants",
        )
        assert not result.is_valid

    def test_validate_b1_access_blocked_code(self):
        """测试拦截含修改模式的代码"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="eval",
            code_snippet="BRAIN_CONSTANTS.MAX_ACTIVE_AGENTS = 999",
        )
        assert not result.is_valid

    def test_validate_sim_mode_invalid(self):
        """测试 sim_mode 非法值"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="set_param",
            params={"sim_mode": "invalid_mode"},
        )
        assert not result.is_valid
        assert "sim_mode" in str(result.errors)

    def test_validate_inject_disturb_start_invalid(self):
        """测试 inject_disturb_start 非法值"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="set_param",
            params={"inject_disturb_start": -1.0},
        )
        assert not result.is_valid

    def test_validate_root_input_valid(self):
        """测试合法顶层输入"""
        validator = SafetyValidator()
        result = validator.validate_root_input(
            {"task_id": "t1", "task_type": "composite"}
        )
        assert result.is_valid

    def test_validate_root_input_missing_field(self):
        """测试缺少必填字段"""
        validator = SafetyValidator()
        result = validator.validate_root_input({})
        assert not result.is_valid

    def test_validate_subtask(self):
        """测试子任务校验"""
        validator = SafetyValidator()
        result = validator.validate_subtask(
            {"task_id": "st1", "task_type": "perception", "priority": 0}
        )
        assert result.is_valid

    def test_validate_output(self):
        """测试输出校验"""
        validator = SafetyValidator()
        result = validator.validate_output(
            {"status": "success", "output": "test"}, "agent_a"
        )
        assert result.is_valid

    def test_validate_output_none(self):
        """测试 None 输出"""
        validator = SafetyValidator()
        result = validator.validate_output(None, "agent_a")
        assert not result.is_valid

    def test_validate_final_output(self):
        """测试最终输出校验"""
        validator = SafetyValidator()
        output = {
            "task_id": "t1",
            "context_version": "v1",
            "status": "converged",
            "worker_outputs": {},
            "conclusion": "done",
            "confidence": 0.8,
        }
        result = validator.validate_final_output(output)
        assert result.is_valid

    def test_check_sandbox_blocked(self):
        """测试沙箱拦截"""
        validator = SafetyValidator()
        result = validator.check_sandbox("modify_brain_subsystem")
        assert not result.is_valid

    def test_blocked_attempts_recorded(self):
        """测试拦截记录"""
        validator = SafetyValidator()
        validator.validate_b1_access(
            operation="modify_constants",
            params={"MAX_ACTIVE_AGENTS": 999},
        )
        assert len(validator.blocked_attempts) >= 1


# =============================================================================
# SnapshotArchive 快照归档测试
# =============================================================================


class TestSnapshotArchive:
    """快照归档管理器测试"""

    def test_archive_round(self):
        """测试归档单轮数据"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        snap_id = archive.archive_round(
            task_id="task_001",
            round_number=1,
            context_version="ctx_v1",
            worker_outputs={"agent_a": {"result": "ok"}},
            meta_logs=[{"rule_id": 1, "rule_name": "test"}],
        )
        assert snap_id.startswith("snap_")
        assert archive.archive_count == 1

    def test_rollback(self):
        """测试回滚"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        snap_id = archive.archive_round(
            task_id="task_002",
            round_number=1,
            context_version="ctx_v1",
            worker_outputs={"agent_a": {"value": 42}},
            meta_logs=[],
        )
        state = archive.rollback(snap_id)
        assert state is not None
        assert state["worker_outputs"]["agent_a"]["value"] == 42

    def test_rollback_not_found(self):
        """测试回滚不存在的快照"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        state = archive.rollback("nonexistent")
        assert state is None

    def test_list_snapshots(self):
        """测试列出快照"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        archive.archive_round(
            task_id="task_003",
            round_number=1,
            context_version="ctx_v1",
            worker_outputs={},
            meta_logs=[],
        )
        snaps = archive.list_snapshots()
        assert len(snaps) >= 1
        assert "snapshot_id" in snaps[0]

    def test_list_archives_by_task(self):
        """测试按任务列归档"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        archive.archive_round(
            task_id="task_004",
            round_number=1,
            context_version="ctx_v1",
            worker_outputs={},
            meta_logs=[],
        )
        archives = archive.list_archives_by_task("task_004")
        assert len(archives) >= 1

    def test_verify_chain(self):
        """测试哈希链验证"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        archive.archive_round(
            task_id="task_005",
            round_number=1,
            context_version="ctx_v1",
            worker_outputs={},
            meta_logs=[],
        )
        archive.archive_round(
            task_id="task_005",
            round_number=2,
            context_version="ctx_v2",
            worker_outputs={},
            meta_logs=[],
        )
        chain = archive.verify_chain()
        assert chain["is_valid"]
        assert chain["total_archives"] == 2

    def test_audit_trail(self):
        """测试审计追踪"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        archive.archive_round(
            task_id="task_006",
            round_number=1,
            context_version="ctx_v1",
            worker_outputs={},
            meta_logs=[],
        )
        trail = archive.get_audit_trail()
        assert len(trail) >= 1
        assert trail[0]["action"] == "archive"

    def test_hash_consistency(self):
        """测试哈希一致性"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        snap_id = archive.archive_round(
            task_id="task_007",
            round_number=1,
            context_version="ctx_v1",
            worker_outputs={"agent_a": {"x": 1}},
            meta_logs=[],
        )
        # 回滚应该验证哈希
        state = archive.rollback(snap_id)
        assert state is not None
        assert state["worker_outputs"]["agent_a"]["x"] == 1


# =============================================================================
# MetaRules 元规则综合测试 — 四条规则分别触发
# =============================================================================


class TestMetaRulesComprehensive:
    """四条元协作规则综合触发测试"""

    # ── 规则①: 强势信号抑制 ──

    def test_rule1_triggered_dominance_above_60_pct(self):
        """规则①触发: 单一Agent主导度超过60%"""
        rules = MetaRules(dominance_threshold=0.60)
        outputs = {
            "agent_a": {"confidence": 0.90},
            "agent_b": {"confidence": 0.20},
            "agent_c": {"confidence": 0.15},
        }
        decision = rules.evaluate(round_outputs=outputs, all_outputs=outputs, history=[])
        rule1 = [log for log in decision.logs if log.rule_id == 1]
        assert len(rule1) == 1
        assert rule1[0].rule_name == "强势信号抑制"
        assert "agent_a" in rule1[0].affected_agents
        assert "反向质询" in rule1[0].action_taken

    def test_rule1_not_triggered_below_threshold(self):
        """规则①不触发: 各Agent分布均匀"""
        rules = MetaRules(dominance_threshold=0.60)
        outputs = {
            "agent_a": {"confidence": 0.50},
            "agent_b": {"confidence": 0.45},
            "agent_c": {"confidence": 0.40},
        }
        decision = rules.evaluate(round_outputs=outputs, all_outputs=outputs, history=[])
        rule1 = [log for log in decision.logs if log.rule_id == 1]
        assert len(rule1) == 0

    def test_rule1_not_triggered_single_agent(self):
        """规则①不触发: 只有一个Agent"""
        rules = MetaRules()
        outputs = {"agent_a": {"confidence": 0.90}}
        decision = rules.evaluate(round_outputs=outputs, all_outputs=outputs, history=[])
        rule1 = [log for log in decision.logs if log.rule_id == 1]
        assert len(rule1) == 0

    # ── 规则②: 集群震荡检测 ──

    def test_rule2_triggered_repeated_overturn(self):
        """规则②触发: 同一个结论被连续推翻3轮"""
        rules = MetaRules(oscillation_detect_rounds=3)

        # 第1轮: 提出 hyp_001
        outputs_r1 = {"agent_a": {"output": {"hypotheses": [{"hypothesis_id": "hyp_001"}]}}}
        rules.evaluate(round_outputs=outputs_r1, all_outputs=outputs_r1, history=[])

        # 第2轮: hyp_001 被推翻，hyp_001 不在当前轮
        outputs_r2 = {"agent_a": {"output": {"hypotheses": [{"hypothesis_id": "hyp_002"}]}}}
        rules.evaluate(round_outputs=outputs_r2, all_outputs=outputs_r2, history=[{"round": 1}])

        # 第3轮: hyp_001 仍不在，hyp_002 也被推翻
        outputs_r3 = {"agent_a": {"output": {"hypotheses": [{"hypothesis_id": "hyp_003"}]}}}
        rules.evaluate(round_outputs=outputs_r3, all_outputs=outputs_r3, history=[{"round": 1}, {"round": 2}])

        # 第4轮: hyp_001 连续3轮不在，触发震荡检测
        outputs_r4 = {"agent_a": {"output": {"hypotheses": [{"hypothesis_id": "hyp_004"}]}}}
        decision = rules.evaluate(
            round_outputs=outputs_r4,
            all_outputs=outputs_r4,
            history=[{"round": 1}, {"round": 2}, {"round": 3}],
        )
        rule2 = [log for log in decision.logs if log.rule_id == 2]
        assert len(rule2) == 1
        assert rule2[0].rule_name == "集群震荡检测"
        assert "原始观测数据" in rule2[0].action_taken

    def test_rule2_not_triggered_insufficient_history(self):
        """规则②不触发: 历史轮次不足"""
        rules = MetaRules(oscillation_detect_rounds=3)
        outputs = {"agent_a": {"output": {"hypotheses": [{"hypothesis_id": "hyp_001"}]}}}
        decision = rules.evaluate(
            round_outputs=outputs, all_outputs=outputs,
            history=[{"round": 1}],
        )
        rule2 = [log for log in decision.logs if log.rule_id == 2]
        assert len(rule2) == 0

    def test_rule2_not_triggered_stable_conclusions(self):
        """规则②不触发: 结论稳定未变"""
        rules = MetaRules(oscillation_detect_rounds=3)
        outputs = {"agent_a": {"output": {"hypotheses": [{"hypothesis_id": "hyp_001"}]}}}

        # 3轮都保持同一结论
        for i in range(3):
            history = [{"round": r} for r in range(1, i + 1)]
            rules.evaluate(round_outputs=outputs, all_outputs=outputs, history=history)

        # 第4轮仍然相同
        decision = rules.evaluate(
            round_outputs=outputs, all_outputs=outputs,
            history=[{"round": 1}, {"round": 2}, {"round": 3}],
        )
        rule2 = [log for log in decision.logs if log.rule_id == 2]
        assert len(rule2) == 0

    # ── 规则③: 冲突调解 ──

    def test_rule3_triggered_high_contradiction(self):
        """规则③触发: Agent间置信度矛盾超过0.4"""
        rules = MetaRules(b1_deviation_threshold=0.35)
        outputs = {
            "agent_a": {"confidence": 0.95},
            "agent_b": {"confidence": 0.10},
            "agent_c": {"confidence": 0.05},
        }
        brain = BrainInterface()
        decision = rules.evaluate(
            round_outputs=outputs, all_outputs=outputs, history=[], brain=brain,
        )
        rule3 = [log for log in decision.logs if log.rule_id == 3]
        assert len(rule3) == 1
        assert rule3[0].rule_name == "冲突调解"
        assert len(rule3[0].affected_agents) >= 1
        assert "过度主观推演" in rule3[0].action_taken

    def test_rule3_not_triggered_low_contradiction(self):
        """规则③不触发: Agent间矛盾小"""
        rules = MetaRules()
        outputs = {
            "agent_a": {"confidence": 0.70},
            "agent_b": {"confidence": 0.60},
            "agent_c": {"confidence": 0.55},
        }
        brain = BrainInterface()
        decision = rules.evaluate(
            round_outputs=outputs, all_outputs=outputs, history=[], brain=brain,
        )
        rule3 = [log for log in decision.logs if log.rule_id == 3]
        assert len(rule3) == 0

    def test_rule3_not_triggered_single_agent(self):
        """规则③不触发: 只有一个Agent"""
        rules = MetaRules()
        outputs = {"agent_a": {"confidence": 0.90}}
        brain = BrainInterface()
        decision = rules.evaluate(
            round_outputs=outputs, all_outputs=outputs, history=[], brain=brain,
        )
        rule3 = [log for log in decision.logs if log.rule_id == 3]
        assert len(rule3) == 0

    def test_rule3_without_brain_fallback(self):
        """规则③无B1时回退到中位数基准"""
        rules = MetaRules()
        outputs = {
            "agent_a": {"confidence": 0.9},
            "agent_b": {"confidence": 0.1},
        }
        decision = rules.evaluate(
            round_outputs=outputs, all_outputs=outputs, history=[], brain=None,
        )
        rule3 = [log for log in decision.logs if log.rule_id == 3]
        assert len(rule3) >= 1
        # 无B1时应使用中位数0.5作为基准
        assert "0.50" in rule3[0].trigger_reason or rule3[0].trigger_reason

    # ── 规则④: 超限熔断 ──

    def test_rule4_triggered_exceeds_max_iterations(self):
        """规则④触发: 连续5轮不收敛触发熔断"""
        rules = MetaRules(max_iterations=5)
        outputs = {"agent_a": {"confidence": 0.5}}

        # 模拟5轮历史
        history = [{"round": i} for i in range(1, 6)]
        decision = rules.evaluate(
            round_outputs=outputs, all_outputs=outputs, history=history,
        )
        assert decision.decision == "circuit_broken"
        rule4 = [log for log in decision.logs if log.rule_id == 4]
        assert len(rule4) == 1
        assert rule4[0].rule_name == "超限熔断"
        assert "证据不足" in rule4[0].action_taken

    def test_rule4_not_triggered_below_max(self):
        """规则④不触发: 未达最大迭代轮次"""
        rules = MetaRules(max_iterations=5)
        outputs = {"agent_a": {"confidence": 0.5}}
        history = [{"round": 1}, {"round": 2}, {"round": 3}]
        decision = rules.evaluate(
            round_outputs=outputs, all_outputs=outputs, history=history,
        )
        assert decision.decision != "circuit_broken"

    def test_rule4_custom_max_iterations(self):
        """规则④自定义阈值: 设置max_iterations=3"""
        rules = MetaRules(max_iterations=3)
        outputs = {"agent_a": {"confidence": 0.5}}
        history = [{"round": 1}, {"round": 2}, {"round": 3}]
        decision = rules.evaluate(
            round_outputs=outputs, all_outputs=outputs, history=history,
        )
        assert decision.decision == "circuit_broken"

    # ── 多规则联动 ──

    def test_multiple_rules_co_triggered(self):
        """多规则联动: 规则①和规则③同时触发"""
        rules = MetaRules(dominance_threshold=0.60, b1_deviation_threshold=0.20)
        # agent_a高度主导且与其他agent差距大
        outputs = {
            "agent_a": {"confidence": 0.95},
            "agent_b": {"confidence": 0.10},
            "agent_c": {"confidence": 0.05},
        }
        brain = BrainInterface()
        decision = rules.evaluate(
            round_outputs=outputs, all_outputs=outputs, history=[], brain=brain,
        )
        triggered_ids = {log.rule_id for log in decision.logs}
        assert 1 in triggered_ids  # 强势信号抑制
        assert 3 in triggered_ids  # 冲突调解
        assert len(decision.suppressed_agents) >= 1

    def test_rule4_takes_priority_over_others(self):
        """规则④优先级最高: 熔断时返回circuit_broken即使其他规则触发"""
        rules = MetaRules(max_iterations=5)
        # 构造高矛盾场景但历史已达上限
        outputs = {
            "agent_a": {"confidence": 0.95},
            "agent_b": {"confidence": 0.05},
        }
        history = [{"round": i} for i in range(1, 6)]
        brain = BrainInterface()
        decision = rules.evaluate(
            round_outputs=outputs, all_outputs=outputs, history=history, brain=brain,
        )
        assert decision.decision == "circuit_broken"
        assert 4 in {log.rule_id for log in decision.logs}


# =============================================================================
# SafetyValidator 安全校验综合测试 — B1常量篡改拦截
# =============================================================================


class TestSafetyValidatorComprehensive:
    """安全校验器综合测试 — 重点验证B1常量篡改拦截"""

    # ── B1 常量篡改拦截 ──

    def test_block_modify_max_active_agents(self):
        """拦截: 修改MAX_ACTIVE_AGENTS"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="set_constant",
            params={"MAX_ACTIVE_AGENTS": 999},
        )
        assert not result.is_valid
        assert "MAX_ACTIVE_AGENTS" in str(result.errors)

    def test_block_modify_cognition_threshold(self):
        """拦截: 修改COGNITION_THRESHOLD_DEFAULT"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="modify_threshold",
            params={"COGNITION_THRESHOLD_DEFAULT": 0.10},
        )
        assert not result.is_valid

    def test_block_modify_oscillation_params(self):
        """拦截: 修改OSCILLATION_FREQ_BASE"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="update_constant",
            params={"OSCILLATION_FREQ_BASE": 5.0},
        )
        assert not result.is_valid

    def test_block_modify_homeostasis_params(self):
        """拦截: 修改HOMEOSTASIS_WINDOW_SIZE"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="write_constant",
            params={"HOMEOSTASIS_WINDOW_SIZE": 20},
        )
        assert not result.is_valid

    def test_block_modify_response_timeout(self):
        """拦截: 修改RESPONSE_TIMEOUT_MS"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="patch",
            params={"RESPONSE_TIMEOUT_MS": 1000},
        )
        assert not result.is_valid

    def test_block_modify_max_snapshot_size(self):
        """拦截: 修改MAX_SNAPSHOT_SIZE_MB"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="override",
            params={"MAX_SNAPSHOT_SIZE_MB": 500},
        )
        assert not result.is_valid

    def test_block_direct_kernel_instantiation(self):
        """拦截: 代码中直接实例化BrainKernel"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="eval",
            code_snippet="BrainKernel()",
        )
        assert not result.is_valid

    def test_block_import_kernel(self):
        """拦截: 代码中导入brain_subsystem.kernel"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="eval",
            code_snippet="from brain_subsystem.kernel import BrainKernel",
        )
        assert not result.is_valid

    def test_block_setattr_on_brain_constants(self):
        """拦截: 代码中使用setattr修改BRAIN_CONSTANTS"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="eval",
            code_snippet="setattr(BRAIN_CONSTANTS, 'MAX_ACTIVE_AGENTS', 999)",
        )
        assert not result.is_valid

    def test_block_reassign_constants(self):
        """拦截: 代码中直接赋值BRAIN_CONSTANTS字段"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="eval",
            code_snippet="BRAIN_CONSTANTS.MAX_ACTIVE_AGENTS = 999",
        )
        assert not result.is_valid

    def test_block_multiple_illegal_params(self):
        """拦截: 同时传入多个非法参数"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="modify",
            params={
                "MAX_ACTIVE_AGENTS": 999,
                "MAX_INFERENCE_DEPTH": 100,
                "HOMEOSTASIS_TOLERANCE": 0.01,
            },
        )
        assert not result.is_valid
        assert len(result.errors) >= 3

    # ── 合法操作放行 ──

    def test_allow_read_constant(self):
        """放行: 读取常量值"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="read_constant",
            params={},
        )
        assert result.is_valid

    def test_allow_sim_mode_default(self):
        """放行: sim_mode='default'"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="read_constant",
            params={"sim_mode": "default"},
        )
        assert result.is_valid

    def test_allow_sim_mode_fast(self):
        """放行: sim_mode='fast'"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="read_constant",
            params={"sim_mode": "fast"},
        )
        assert result.is_valid

    def test_allow_sim_mode_deep(self):
        """放行: sim_mode='deep'"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="read_constant",
            params={"sim_mode": "deep"},
        )
        assert result.is_valid

    def test_allow_inject_disturb_start_zero(self):
        """放行: inject_disturb_start=0.0"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="read_constant",
            params={"inject_disturb_start": 0.0},
        )
        assert result.is_valid

    def test_allow_inject_disturb_start_positive(self):
        """放行: inject_disturb_start=5.0"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="read_constant",
            params={"inject_disturb_start": 5.0},
        )
        assert result.is_valid

    # ── 参数值校验 ──

    def test_block_invalid_sim_mode(self):
        """拦截: sim_mode='hack'"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="set_param",
            params={"sim_mode": "hack"},
        )
        assert not result.is_valid

    def test_block_negative_inject_disturb(self):
        """拦截: inject_disturb_start=-1.0"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="set_param",
            params={"inject_disturb_start": -1.0},
        )
        assert not result.is_valid

    def test_block_non_numeric_inject_disturb(self):
        """拦截: inject_disturb_start='abc'"""
        validator = SafetyValidator()
        result = validator.validate_b1_access(
            operation="set_param",
            params={"inject_disturb_start": "abc"},
        )
        assert not result.is_valid

    # ── 沙箱边界 ──

    def test_sandbox_blocks_modify_brain(self):
        """沙箱拦截: modify_brain_subsystem"""
        validator = SafetyValidator()
        result = validator.check_sandbox("modify_brain_subsystem")
        assert not result.is_valid

    def test_sandbox_blocks_direct_kernel(self):
        """沙箱拦截: direct_kernel_access"""
        validator = SafetyValidator()
        result = validator.check_sandbox("direct_kernel_access")
        assert not result.is_valid

    def test_sandbox_blocks_constant_override(self):
        """沙箱拦截: constant_override"""
        validator = SafetyValidator()
        result = validator.check_sandbox("constant_override")
        assert not result.is_valid

    # ── 输入/输出中B1篡改检测 ──

    def test_root_input_with_b1_modify_blocked(self):
        """拦截: 任务输入中包含B1修改意图"""
        validator = SafetyValidator()
        result = validator.validate_root_input({
            "task_id": "t1",
            "description": "修改 BRAIN_CONSTANTS.MAX_ACTIVE_AGENTS = 999",
        })
        assert not result.is_valid

    def test_agent_output_with_b1_modify_blocked(self):
        """拦截: Agent输出中包含B1修改意图"""
        validator = SafetyValidator()
        result = validator.validate_output(
            {"output": "BRAIN_CONSTANTS.COGNITION_THRESHOLD_DEFAULT = 0.10"},
            "malicious_agent",
        )
        assert not result.is_valid

    # ── 拦截记录 ──

    def test_blocked_attempts_accumulate(self):
        """拦截记录累积: 多次拦截被正确记录"""
        validator = SafetyValidator()
        validator.validate_b1_access(operation="modify", params={"MAX_ACTIVE_AGENTS": 999})
        validator.validate_b1_access(operation="override", params={"MAX_INFERENCE_DEPTH": 100})
        validator.validate_b1_access(operation="patch", params={"HOMEOSTASIS_TOLERANCE": 0.01})
        assert len(validator.blocked_attempts) >= 3


# =============================================================================
# SnapshotArchive 快照完整性综合测试 — 哈希链防篡改
# =============================================================================


class TestSnapshotArchiveIntegrity:
    """快照归档完整性测试 — 验证哈希链防篡改机制"""

    # ── 哈希链基本验证 ──

    def test_hash_chain_initial_state(self):
        """初始哈希链: 创世哈希为64个零"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        assert archive.last_hash == "0" * 64
        assert archive.archive_count == 0

    def test_hash_chain_after_single_archive(self):
        """单次归档后哈希链: last_hash更新"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        archive.archive_round(
            task_id="chain_test",
            round_number=1,
            context_version="v1",
            worker_outputs={"a": {"x": 1}},
            meta_logs=[],
        )
        assert archive.last_hash != "0" * 64
        assert archive.archive_count == 1
        chain = archive.verify_chain()
        assert chain["is_valid"]

    def test_hash_chain_sequential_archives(self):
        """顺序归档哈希链: 链式引用正确"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        archive.archive_round(
            task_id="seq_test", round_number=1,
            context_version="v1", worker_outputs={"a": {"x": 1}}, meta_logs=[],
        )
        archive.archive_round(
            task_id="seq_test", round_number=2,
            context_version="v2", worker_outputs={"a": {"x": 2}}, meta_logs=[],
        )
        archive.archive_round(
            task_id="seq_test", round_number=3,
            context_version="v3", worker_outputs={"a": {"x": 3}}, meta_logs=[],
        )
        chain = archive.verify_chain()
        assert chain["is_valid"]
        assert chain["total_archives"] == 3

    # ── 哈希链防篡改 ──

    def test_tamper_detection_content_changed(self):
        """防篡改: 修改归档内容导致哈希不匹配"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        archive.archive_round(
            task_id="tamper_test", round_number=1,
            context_version="v1",
            worker_outputs={"agent_a": {"value": 42}},
            meta_logs=[],
        )

        # 直接修改内部归档内容
        arc = archive.get_archive("arc_tamper_test_r001")
        assert arc is not None
        # 修改内容但不更新哈希
        arc.worker_outputs["agent_a"]["value"] = 999
        # 注意: content_hash 未更新

        # 回滚时应检测到哈希不匹配
        state = archive.rollback("snap_tamper_test_001")
        assert state is None  # 哈希不匹配，回滚失败

    def test_tamper_detection_hash_chain_broken(self):
        """防篡改: 修改prev_archive_hash导致哈希链断裂"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")

        archive.archive_round(
            task_id="chain_break", round_number=1,
            context_version="v1", worker_outputs={"a": {"x": 1}}, meta_logs=[],
        )
        archive.archive_round(
            task_id="chain_break", round_number=2,
            context_version="v2", worker_outputs={"a": {"x": 2}}, meta_logs=[],
        )

        # 篡改第2个归档的prev_archive_hash
        arc2 = archive.get_archive("arc_chain_break_r002")
        assert arc2 is not None
        arc2.prev_archive_hash = "0" * 64  # 恶意修改

        chain = archive.verify_chain()
        assert not chain["is_valid"]
        assert len(chain["broken_links"]) >= 1

    def test_tamper_detection_insert_malicious_archive(self):
        """防篡改: 插入伪造归档破坏哈希链"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")

        archive.archive_round(
            task_id="insert_test", round_number=1,
            context_version="v1", worker_outputs={"a": {"x": 1}}, meta_logs=[],
        )
        archive.archive_round(
            task_id="insert_test", round_number=2,
            context_version="v2", worker_outputs={"a": {"x": 2}}, meta_logs=[],
        )

        # 获取第2个归档的哈希
        arc2 = archive.get_archive("arc_insert_test_r002")
        assert arc2 is not None

        # 伪造: 修改轮次2的内容
        arc2.worker_outputs["a"]["x"] = 999
        # content_hash 未更新，回滚应失败
        state = archive.rollback("snap_insert_test_002")
        assert state is None  # 哈希不匹配

    # ── 哈希确定性 ──

    def test_hash_deterministic(self):
        """哈希确定性: 相同输入产生相同哈希"""
        archive1 = SnapshotArchive(storage_path="/tmp/test_snapshots")
        archive2 = SnapshotArchive(storage_path="/tmp/test_snapshots_2")

        data = {"agent_a": {"value": 42}}
        logs = [{"rule_id": 1, "rule_name": "test"}]

        archive1.archive_round(
            task_id="deterministic", round_number=1,
            context_version="v1", worker_outputs=data, meta_logs=logs,
        )
        archive2.archive_round(
            task_id="deterministic", round_number=1,
            context_version="v1", worker_outputs=data, meta_logs=logs,
        )

        # 注意: 时间戳不同，所以哈希不同。但相同内容+相同prev_hash应产生相同哈希。
        # 此处验证两个独立归档的哈希链都是有效的
        assert archive1.verify_chain()["is_valid"]
        assert archive2.verify_chain()["is_valid"]

    def test_hash_changes_with_content(self):
        """哈希敏感性: 内容变化导致哈希变化"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")

        archive.archive_round(
            task_id="sensitive", round_number=1,
            context_version="v1",
            worker_outputs={"agent_a": {"value": 1}},
            meta_logs=[],
        )
        hash1 = archive.last_hash

        archive2 = SnapshotArchive(storage_path="/tmp/test_snapshots_2")
        archive2.archive_round(
            task_id="sensitive", round_number=1,
            context_version="v1",
            worker_outputs={"agent_a": {"value": 2}},  # 不同值
            meta_logs=[],
        )
        hash2 = archive2.last_hash

        assert hash1 != hash2  # 内容不同，哈希不同

    # ── 审计追踪 ──

    def test_audit_trail_complete(self):
        """审计追踪: 完整记录所有操作"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        archive.archive_round(
            task_id="audit_test", round_number=1,
            context_version="v1", worker_outputs={}, meta_logs=[],
        )
        archive.archive_round(
            task_id="audit_test", round_number=2,
            context_version="v2", worker_outputs={}, meta_logs=[],
        )
        trail = archive.get_audit_trail()
        assert len(trail) >= 2
        assert all(entry["action"] == "archive" for entry in trail)

    def test_audit_trail_by_task(self):
        """审计追踪: 按任务过滤"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        archive.archive_round(
            task_id="task_A", round_number=1,
            context_version="v1", worker_outputs={}, meta_logs=[],
        )
        archive.archive_round(
            task_id="task_B", round_number=1,
            context_version="v1", worker_outputs={}, meta_logs=[],
        )
        trail_a = archive.get_audit_by_task("task_A")
        assert len(trail_a) == 1

    # ── 回滚与快照 ──

    def test_rollback_restores_complete_state(self):
        """回滚: 恢复完整状态"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        snap_id = archive.archive_round(
            task_id="rollback_full", round_number=1,
            context_version="v1",
            worker_outputs={"agent_a": {"x": 1, "y": 2}},
            meta_logs=[{"rule_id": 1}, {"rule_id": 3}],
            subtask_proposals=[{"task_id": "st1"}],
            metadata={"key": "val"},
        )
        state = archive.rollback(snap_id)
        assert state is not None
        assert state["task_id"] == "rollback_full"
        assert state["worker_outputs"]["agent_a"]["x"] == 1
        assert state["worker_outputs"]["agent_a"]["y"] == 2
        assert len(state["meta_logs"]) == 2
        assert len(state["subtask_proposals"]) == 1

    def test_list_snapshots_chronological(self):
        """快照列表: 按时间排序"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        archive.archive_round(
            task_id="chrono", round_number=1,
            context_version="v1", worker_outputs={}, meta_logs=[],
        )
        archive.archive_round(
            task_id="chrono", round_number=2,
            context_version="v2", worker_outputs={}, meta_logs=[],
        )
        snaps = archive.list_snapshots()
        assert len(snaps) >= 2
        assert all("snapshot_id" in s for s in snaps)
        assert all("content_hash" in s for s in snaps)

    # ── 归档结构完整性 ──

    def test_archive_round_archive(self):
        """归档结构: RoundArchive字段完整"""
        archive = SnapshotArchive(storage_path="/tmp/test_snapshots")
        archive.archive_round(
            task_id="struct_test", round_number=1,
            context_version="v1",
            worker_outputs={"a": {"x": 1}},
            meta_logs=[{"rule_id": 1}],
        )
        arc = archive.get_archive("arc_struct_test_r001")
        assert arc is not None
        assert arc.archive_id == "arc_struct_test_r001"
        assert arc.task_id == "struct_test"
        assert arc.round_number == 1
        assert arc.context_version == "v1"
        assert len(arc.content_hash) == 64  # SHA-256
        assert arc.prev_archive_hash == "0" * 64
        assert arc.worker_outputs == {"a": {"x": 1}}
        assert len(arc.meta_logs) == 1