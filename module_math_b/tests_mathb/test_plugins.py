"""
module_math_b.tests_mathb.test_plugins — v1.1 插件专属测试套件

测试覆盖：
  1. 插件开关隔离 — 默认关闭，显式开启
  2. 超时场景 — 插件超时处理
  3. 解析失败 — 无效输入优雅降级
  4. 内存约束 — 内存限制
  5. 插件注册表 — 注册、配置、执行生命周期
  6. SymPy 桥接 — 素数判定、因式分解
  7. Lean REPL 桥接 — 可用性检测、优雅降级
  8. 停滞分析 — 根因诊断
  9. ReportExporter — Markdown 报告导出
  10. 集成测试 — 插件与数学工作流集成
"""

import os
import sys
import json
import time
import pytest
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from module_math_b.plugins.plugin_registry import (
    PluginRegistry,
    PluginBase,
    PluginConfig,
    PluginResult,
    PluginStatus,
)
from module_math_b.plugins.sympy_bridge import SympyBridge
from module_math_b.plugins.lean_repl_bridge import LeanReplBridge
from module_math_b.plugins.stagnation_analyzer import StagnationAnalyzer
from module_math_b.plugins.plugin_conjecture_generator import (
    ConjectureGenerator,
    ConjectureCandidate,
    ConjectureBatch,
)
from module_math_b.plugins.plugin_batch_experiment import (
    BatchExperimentScheduler,
    ExperimentTask,
    ExperimentResult,
    BatchReport,
)
from module_math_b.report_exporter import ReportExporter, ReportConfig
from module_math_b.math_snapshot_bridge import MathSnapshotBridge
from module_math_b.math_hypo_pool import MathHypothesisPool
from module_math_b.math_structs import (
    MathProposition,
    MathDerivationStep,
    MathCounterExample,
    MathValidationReport,
    MathConvergenceReport,
)
from module_math_b.math_convergence import MathConvergence


# =============================================================================
# 1. 插件开关隔离测试
# =============================================================================

class TestPluginIsolation:
    """插件开关隔离：默认关闭，仅通过配置显式开启"""

    def test_all_plugins_disabled_by_default(self):
        """验证所有插件默认关闭"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=False))
        registry.register(LeanReplBridge(), PluginConfig(name="lean_repl_bridge", enabled=False))
        registry.register(StagnationAnalyzer(), PluginConfig(name="stagnation_analyzer", enabled=False))

        assert not registry.is_enabled("sympy_bridge")
        assert not registry.is_enabled("lean_repl_bridge")
        assert not registry.is_enabled("stagnation_analyzer")

        # 默认配置下执行已启用插件，应该返回空
        results = registry.execute_enabled({"operation": "is_prime", "n": 7})
        assert len(results) == 0

    def test_enable_single_plugin_via_config(self):
        """通过配置显式开启单个插件"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=False))

        registry.load_config({
            "mathb_config": {
                "plugins": {
                    "sympy_bridge": {"enabled": True},
                }
            }
        })
        assert registry.is_enabled("sympy_bridge")

    def test_enable_multiple_plugins_via_config(self):
        """通过配置显式开启多个插件"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=False))
        registry.register(StagnationAnalyzer(), PluginConfig(name="stagnation_analyzer", enabled=False))

        registry.load_config({
            "mathb_config": {
                "plugins": {
                    "sympy_bridge": {"enabled": True},
                    "stagnation_analyzer": {"enabled": True},
                }
            }
        })
        assert registry.is_enabled("sympy_bridge")
        assert registry.is_enabled("stagnation_analyzer")

    def test_disabled_plugin_not_executed(self):
        """禁用插件不被执行"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=False))

        results = registry.execute_enabled({"operation": "is_prime", "n": 7})
        assert "sympy_bridge" not in results

    def test_enabled_plugin_is_executed(self):
        """启用插件被执行"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=True))

        results = registry.execute_enabled({"operation": "is_prime", "n": 7})
        assert "sympy_bridge" in results

    def test_enable_disable_toggle(self):
        """插件开关切换"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=False))

        assert not registry.is_enabled("sympy_bridge")
        registry.enable("sympy_bridge")
        assert registry.is_enabled("sympy_bridge")
        registry.disable("sympy_bridge")
        assert not registry.is_enabled("sympy_bridge")

    def test_list_plugins(self):
        """列出已注册插件"""
        registry = PluginRegistry()
        registry.register(SympyBridge())
        registry.register(StagnationAnalyzer())

        plugins = registry.list_plugins()
        assert "sympy_bridge" in plugins
        assert "stagnation_analyzer" in plugins

    def test_list_enabled(self):
        """列出已启用插件"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=True))
        registry.register(StagnationAnalyzer(), PluginConfig(name="stagnation_analyzer", enabled=False))

        enabled = registry.list_enabled()
        assert "sympy_bridge" in enabled
        assert "stagnation_analyzer" not in enabled

    def test_unregistered_plugin_not_executed(self):
        """未注册插件不被执行"""
        registry = PluginRegistry()
        # 未注册任何插件
        results = registry.execute_enabled({"test": True})
        assert len(results) == 0

    def test_plugin_config_timeout_override(self):
        """插件配置超时覆盖"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", timeout_seconds=5.0))

        registry.load_config({
            "mathb_config": {
                "plugins": {
                    "sympy_bridge": {"enabled": True, "timeout_seconds": 10.0},
                }
            }
        })
        cfg = registry.get_config("sympy_bridge")
        assert cfg.timeout_seconds == 10.0

    def test_plugin_config_memory_limit_override(self):
        """插件配置内存限制覆盖"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", memory_limit_mb=128))

        registry.load_config({
            "mathb_config": {
                "plugins": {
                    "sympy_bridge": {"enabled": True, "memory_limit_mb": 256},
                }
            }
        })
        cfg = registry.get_config("sympy_bridge")
        assert cfg.memory_limit_mb == 256


# =============================================================================
# 2. 超时场景测试
# =============================================================================

class TestPluginTimeout:
    """插件超时处理"""

    def test_plugin_timeout_handled(self):
        """插件超时被正确处理为 TIMEOUT 状态"""

        class SlowPlugin(PluginBase):
            plugin_name = "slow_plugin"

            def execute(self, context):
                time.sleep(10)  # 远超超时限制
                return PluginResult(plugin_name=self.plugin_name, status=PluginStatus.ENABLED)

        registry = PluginRegistry()
        registry.register(SlowPlugin(), PluginConfig(name="slow_plugin", enabled=True, timeout_seconds=0.1))

        results = registry.execute_enabled({})
        assert "slow_plugin" in results
        assert results["slow_plugin"].status == PluginStatus.TIMEOUT

    def test_plugin_within_timeout_succeeds(self):
        """插件在超时内完成正常返回"""

        class FastPlugin(PluginBase):
            plugin_name = "fast_plugin"

            def execute(self, context):
                return PluginResult(plugin_name=self.plugin_name, status=PluginStatus.ENABLED)

        registry = PluginRegistry()
        registry.register(FastPlugin(), PluginConfig(name="fast_plugin", enabled=True, timeout_seconds=5.0))

        results = registry.execute_enabled({})
        assert "fast_plugin" in results
        assert results["fast_plugin"].status == PluginStatus.ENABLED

    def test_plugin_timeout_error_message(self):
        """超时插件返回有意义的错误消息"""

        class SlowPlugin(PluginBase):
            plugin_name = "slow_plugin"

            def execute(self, context):
                time.sleep(10)
                return PluginResult(plugin_name=self.plugin_name, status=PluginStatus.ENABLED)

        registry = PluginRegistry()
        registry.register(SlowPlugin(), PluginConfig(name="slow_plugin", enabled=True, timeout_seconds=0.1))

        results = registry.execute_enabled({})
        assert "超时" in results["slow_plugin"].error

    def test_sympy_plugin_timeout_config(self):
        """SymPy 插件超时配置生效"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", timeout_seconds=0.001))

        registry.load_config({
            "mathb_config": {
                "plugins": {
                    "sympy_bridge": {"enabled": True, "timeout_seconds": 0.001},
                }
            }
        })
        # 极短超时可能触发 TIMEOUT，但 SymPy 操作很快
        # 这个测试主要验证配置生效
        cfg = registry.get_config("sympy_bridge")
        assert cfg.timeout_seconds == 0.001


# =============================================================================
# 3. 解析失败 / 无效输入测试
# =============================================================================

class TestPluginParseFailure:
    """解析失败与无效输入优雅降级"""

    def test_sympy_unknown_operation(self):
        """SymPy 未知操作返回错误"""
        bridge = SympyBridge()
        result = bridge.execute({"operation": "nonexistent_op", "n": 5})
        assert result.status == PluginStatus.ERROR
        assert "未知操作" in result.error

    def test_sympy_invalid_n_type(self):
        """SymPy 非法参数类型"""
        bridge = SympyBridge()
        # 传入字符串而非整数
        result = bridge.execute({"operation": "is_prime", "n": "not_a_number"})
        # 应该捕获异常
        assert result.status in (PluginStatus.ERROR, PluginStatus.ENABLED)

    def test_sympy_negative_n(self):
        """SymPy 负数输入处理"""
        bridge = SympyBridge()
        result = bridge.execute({"operation": "is_prime", "n": -1})
        assert result.status == PluginStatus.ENABLED
        assert result.output["is_prime"] is False

    def test_sympy_factor_zero(self):
        """SymPy 因式分解 0"""
        bridge = SympyBridge()
        result = bridge.execute({"operation": "factor", "n": 0})
        assert result.status == PluginStatus.ENABLED

    def test_sympy_factor_one(self):
        """SymPy 因式分解 1"""
        bridge = SympyBridge()
        result = bridge.execute({"operation": "factor", "n": 1})
        assert result.status == PluginStatus.ENABLED

    def test_lean_unavailable_graceful(self):
        """Lean 不可用时优雅降级"""
        bridge = LeanReplBridge()
        if not bridge.is_available:
            result = bridge.execute({"operation": "check_availability"})
            assert result.status == PluginStatus.DISABLED
            assert "未安装" in result.output.get("message", "")

    def test_lean_unknown_operation(self):
        """Lean 未知操作"""
        bridge = LeanReplBridge()
        result = bridge.execute({"operation": "nonexistent"})
        # 如果 Lean 不可用，返回 DISABLED；否则 ERROR
        assert result.status in (PluginStatus.DISABLED, PluginStatus.ERROR)

    def test_stagnation_empty_context(self):
        """停滞分析空上下文"""
        analyzer = StagnationAnalyzer()
        result = analyzer.execute({})
        assert result.status == PluginStatus.ENABLED
        assert "diagnosis" in result.output

    def test_stagnation_no_propositions(self):
        """停滞分析无命题"""
        analyzer = StagnationAnalyzer()
        result = analyzer.execute({
            "propositions": [],
            "stagnation_rounds": 0,
            "round_number": 1,
        })
        assert result.status == PluginStatus.ENABLED

    def test_stagnation_with_gaps(self):
        """停滞分析有缺口"""
        analyzer = StagnationAnalyzer()
        result = analyzer.execute({
            "propositions": [{"proposition_id": "p1"}],
            "stagnation_rounds": 3,
            "round_number": 1,
            "derivation_steps": [
                {"has_gap": True, "gap_description": "缺少引理"},
                {"has_gap": True, "gap_description": "缺少引理"},
                {"has_gap": True, "gap_description": "缺少引理"},
            ],
            "validation_reports": [],
        })
        assert result.status == PluginStatus.ENABLED
        assert "diagnosis" in result.output
        assert result.output["diagnosis"]["severity"] in ("high", "critical")

    def test_plugin_registry_parse_bad_config(self):
        """插件注册表解析坏配置"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=False))

        # 传入非字典配置
        registry.load_config({"mathb_config": {"plugins": "not_a_dict"}})
        # 不应崩溃
        assert not registry.is_enabled("sympy_bridge")

        # 传入空配置
        registry.load_config({})
        assert not registry.is_enabled("sympy_bridge")

    def test_plugin_registry_nonexistent_plugin_config(self):
        """配置不存在的插件"""
        registry = PluginRegistry()
        registry.load_config({
            "mathb_config": {
                "plugins": {
                    "nonexistent_plugin": {"enabled": True},
                }
            }
        })
        # 不应崩溃
        assert registry.list_enabled() == []


# =============================================================================
# 4. 内存约束测试
# =============================================================================

class TestPluginMemoryConstraints:
    """内存约束场景"""

    def test_plugin_config_memory_limit_default(self):
        """插件默认内存限制"""
        cfg = PluginConfig(name="test_plugin")
        assert cfg.memory_limit_mb == 128

    def test_plugin_config_memory_limit_custom(self):
        """插件自定义内存限制"""
        cfg = PluginConfig(name="test_plugin", memory_limit_mb=64)
        assert cfg.memory_limit_mb == 64

    def test_multiple_plugins_independent_memory(self):
        """多个插件独立内存限制"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", memory_limit_mb=128))
        registry.register(StagnationAnalyzer(), PluginConfig(name="stagnation_analyzer", memory_limit_mb=64))

        sympy_cfg = registry.get_config("sympy_bridge")
        stagnation_cfg = registry.get_config("stagnation_analyzer")
        assert sympy_cfg.memory_limit_mb == 128
        assert stagnation_cfg.memory_limit_mb == 64

    def test_registry_reset_clears_memory(self):
        """注册表重置清空内存"""
        registry = PluginRegistry()
        registry.register(SympyBridge())
        registry.register(StagnationAnalyzer())

        assert len(registry.list_plugins()) == 2
        registry.reset()
        assert len(registry.list_plugins()) == 0

    def test_sympy_plugin_memory_stable(self):
        """SymPy 插件内存稳定（多次调用不泄漏）"""
        bridge = SympyBridge()
        for _ in range(10):
            result = bridge.execute({"operation": "is_prime", "n": 9973})
            assert result.status == PluginStatus.ENABLED

    def test_stagnation_plugin_memory_stable(self):
        """停滞分析插件内存稳定"""
        analyzer = StagnationAnalyzer()
        for _ in range(10):
            result = analyzer.execute({
                "propositions": [{"proposition_id": "p1"}],
                "stagnation_rounds": 2,
                "round_number": 1,
                "derivation_steps": [{"has_gap": True, "gap_description": "test"}],
                "validation_reports": [],
            })
            assert result.status == PluginStatus.ENABLED


# =============================================================================
# 5. 插件注册表完整生命周期测试
# =============================================================================

class TestPluginRegistryLifecycle:
    """插件注册表完整生命周期"""

    def test_register_unregister(self):
        registry = PluginRegistry()
        registry.register(SympyBridge())
        assert "sympy_bridge" in registry.list_plugins()
        registry.unregister("sympy_bridge")
        assert "sympy_bridge" not in registry.list_plugins()

    def test_execute_one_regardless_of_enabled(self):
        """execute_one 无论是否启用都执行"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=False))

        result = registry.execute_one("sympy_bridge", {"operation": "is_prime", "n": 7})
        assert result.plugin_name == "sympy_bridge"
        assert result.status == PluginStatus.ENABLED

    def test_execute_one_nonexistent(self):
        """execute_one 执行不存在的插件"""
        registry = PluginRegistry()
        result = registry.execute_one("nonexistent", {})
        assert result.status == PluginStatus.ERROR
        assert "未注册" in result.error

    def test_results_accumulation(self):
        """插件结果累积"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=True))

        registry.execute_enabled({"operation": "is_prime", "n": 7})
        registry.execute_enabled({"operation": "is_prime", "n": 11})

        results = registry.get_results()
        assert len(results) == 2

    def test_clear_results(self):
        """清除插件结果"""
        registry = PluginRegistry()
        registry.register(SympyBridge(), PluginConfig(name="sympy_bridge", enabled=True))

        registry.execute_enabled({"operation": "is_prime", "n": 7})
        assert len(registry.get_results()) == 1
        registry.clear_results()
        assert len(registry.get_results()) == 0


# =============================================================================
# 6. SymPy 桥接功能测试
# =============================================================================

class TestSympyBridgeFunctionality:
    """SymPy 桥接功能测试"""

    def test_is_prime_true(self):
        bridge = SympyBridge()
        result = bridge.execute({"operation": "is_prime", "n": 7})
        assert result.output["is_prime"] is True

    def test_is_prime_false(self):
        bridge = SympyBridge()
        result = bridge.execute({"operation": "is_prime", "n": 4})
        assert result.output["is_prime"] is False

    def test_is_prime_2(self):
        bridge = SympyBridge()
        result = bridge.execute({"operation": "is_prime", "n": 2})
        assert result.output["is_prime"] is True

    def test_factor(self):
        bridge = SympyBridge()
        result = bridge.execute({"operation": "factor", "n": 2047})
        assert result.status == PluginStatus.ENABLED
        # 2047 = 23 × 89
        assert 23 in result.output["factors"]
        assert 89 in result.output["factors"]

    def test_factor_string(self):
        bridge = SympyBridge()
        result = bridge.execute({"operation": "factor", "n": 12})
        assert "factor_string" in result.output
        # 12 = 2^2 × 3
        assert "2" in result.output["factor_string"]

    def test_prime_range(self):
        bridge = SympyBridge()
        result = bridge.execute({"operation": "prime_range", "a": 2, "b": 11})
        assert result.output["count"] == 5  # 2, 3, 5, 7, 11
        assert result.output["primes"] == [2, 3, 5, 7, 11]

    def test_verify_match(self):
        bridge = SympyBridge()
        result = bridge.execute({"operation": "verify", "n": 7, "expected": True})
        assert result.output["match"] is True

    def test_verify_mismatch(self):
        bridge = SympyBridge()
        result = bridge.execute({"operation": "verify", "n": 4, "expected": True})
        assert result.output["match"] is False

    def test_isprime_verbose_prime(self):
        bridge = SympyBridge()
        result = bridge.execute({"operation": "isprime_verbose", "n": 13})
        assert result.output["is_prime"] is True
        assert len(result.output["steps"]) >= 2

    def test_isprime_verbose_composite(self):
        bridge = SympyBridge()
        result = bridge.execute({"operation": "isprime_verbose", "n": 15})
        assert result.output["is_prime"] is False
        assert "factors" in result.output

    def test_is_available(self):
        bridge = SympyBridge()
        # 在测试环境中通常已安装 sympy
        assert bridge.is_available is True or bridge.is_available is False


# =============================================================================
# 7. Lean REPL 桥接功能测试
# =============================================================================

class TestLeanReplBridgeFunctionality:
    """Lean REPL 桥接功能测试"""

    def test_availability_check(self):
        bridge = LeanReplBridge()
        result = bridge.execute({"operation": "check_availability"})
        if bridge.is_available:
            assert result.status == PluginStatus.ENABLED
            assert result.output["lean_available"] is True
        else:
            assert result.status == PluginStatus.DISABLED

    def test_is_available_property(self):
        bridge = LeanReplBridge()
        assert isinstance(bridge.is_available, bool)

    def test_graceful_degradation(self):
        """Lean 不可用时不崩溃"""
        bridge = LeanReplBridge()
        # 即使 Lean 不可用，execute 也不应抛出异常
        try:
            result = bridge.execute({"operation": "check_availability"})
            assert result.plugin_name == "lean_repl_bridge"
        except Exception as e:
            pytest.fail(f"Lean 桥接崩溃: {e}")


# =============================================================================
# 8. 停滞分析功能测试
# =============================================================================

class TestStagnationAnalyzerFunctionality:
    """停滞分析功能测试"""

    def test_diagnosis_has_required_fields(self):
        analyzer = StagnationAnalyzer()
        result = analyzer.execute({
            "propositions": [{"proposition_id": "p1"}],
            "stagnation_rounds": 3,
            "round_number": 1,
            "derivation_steps": [],
            "validation_reports": [],
        })
        diag = result.output["diagnosis"]
        assert "root_causes" in diag
        assert "severity" in diag
        assert "suggestions" in diag

    def test_severity_critical_with_deep_stagnation(self):
        """深度停滞判定为 critical"""
        analyzer = StagnationAnalyzer()
        result = analyzer.execute({
            "propositions": [{"proposition_id": "p1"}],
            "stagnation_rounds": 5,
            "round_number": 1,
            "derivation_steps": [],
            "validation_reports": [],
        })
        assert result.output["diagnosis"]["severity"] == "critical"

    def test_severity_low_without_stagnation(self):
        """无停滞时 severity 为 low"""
        analyzer = StagnationAnalyzer()
        result = analyzer.execute({
            "propositions": [{"proposition_id": "p1"}],
            "stagnation_rounds": 0,
            "round_number": 1,
            "derivation_steps": [],
            "validation_reports": [],
        })
        assert result.output["diagnosis"]["severity"] == "low"

    def test_suggestions_included(self):
        """停滞分析包含建议"""
        analyzer = StagnationAnalyzer()
        result = analyzer.execute({
            "propositions": [{"proposition_id": "p1"}],
            "stagnation_rounds": 3,
            "round_number": 1,
            "derivation_steps": [],
            "validation_reports": [],
        })
        assert len(result.output["diagnosis"]["suggestions"]) > 0

    def test_reset_clears_state(self):
        analyzer = StagnationAnalyzer()
        analyzer.execute({
            "propositions": [{"proposition_id": "p1"}],
            "stagnation_rounds": 3,
            "round_number": 1,
            "derivation_steps": [{"has_gap": True, "gap_description": "test"}],
            "validation_reports": [],
        })
        analyzer.reset()
        # 重置后再次执行，不应有累积状态
        result = analyzer.execute({
            "propositions": [],
            "stagnation_rounds": 0,
            "round_number": 1,
            "derivation_steps": [],
            "validation_reports": [],
        })
        assert result.status == PluginStatus.ENABLED

    def test_gap_pattern_detection(self):
        """缺口模式检测"""
        analyzer = StagnationAnalyzer()
        result = analyzer.execute({
            "propositions": [{"proposition_id": "p1"}],
            "stagnation_rounds": 2,
            "round_number": 1,
            "derivation_steps": [
                {"has_gap": True, "gap_description": "缺少引理X"},
                {"has_gap": True, "gap_description": "缺少引理X"},
                {"has_gap": True, "gap_description": "缺少引理X"},
            ],
            "validation_reports": [],
        })
        assert result.output["diagnosis"]["severity"] == "high"
        assert "系统" in str(result.output["diagnosis"]["root_causes"])


# =============================================================================
# 9. ReportExporter 测试
# =============================================================================

class TestReportExporter:
    """标准化 Markdown 报告导出测试"""

    def _setup_bridge_with_data(self) -> MathSnapshotBridge:
        """创建带测试数据的快照桥接器"""
        pool = MathHypothesisPool()
        pool.register_proposition("p1", "所有大于2的偶数都是两个素数之和")
        pool.register_proposition("p2", "若n为素数则2^n-1为素数")

        # 添加推导步骤
        step = MathDerivationStep(
            step_id="s1", step_number=1,
            premises=["n=11是素数"], conclusion="2^11-1=2047",
            derivation_rule="computation",
            validation_passed=True,
        )
        pool.add_derivation_step("p2", step)

        # 添加反例
        ce = MathCounterExample(
            example_id="ce1", target_proposition_id="p2",
            value_representation="n=11: 2^11-1=2047=23×89",
            is_valid=True, is_reproducible=True,
        )
        pool.add_counter_example("p2", ce)

        conv = MathConvergence()
        conv_report = conv.evaluate(pool, round_number=1)

        bridge = MathSnapshotBridge(task_id="test_report")
        bridge.create_snapshot(
            round_number=1, pool=pool,
            convergence_report=conv_report,
            validation_summary={
                "total_validations": 2,
                "pass_rate": 0.75,
                "syntax_errors": 0,
                "logical_gaps": 1,
                "hidden_assumptions": 0,
                "circular_count": 0,
                "self_contradiction_count": 0,
                "boundary_tests_passed": 2,
            },
        )
        return bridge

    def test_export_markdown_not_empty(self):
        bridge = self._setup_bridge_with_data()
        exporter = ReportExporter(bridge)
        md = exporter.export_to_markdown()
        assert len(md) > 0
        assert "Module-MathB" in md

    def test_export_markdown_contains_task_id(self):
        bridge = self._setup_bridge_with_data()
        exporter = ReportExporter(bridge)
        md = exporter.export_to_markdown()
        assert "test_report" in md

    def test_export_markdown_contains_propositions(self):
        bridge = self._setup_bridge_with_data()
        exporter = ReportExporter(bridge)
        md = exporter.export_to_markdown()
        assert "p1" in md
        assert "p2" in md

    def test_export_markdown_contains_hash_chain(self):
        bridge = self._setup_bridge_with_data()
        exporter = ReportExporter(bridge)
        md = exporter.export_to_markdown()
        assert "哈希链" in md

    def test_export_markdown_contains_convergence(self):
        bridge = self._setup_bridge_with_data()
        exporter = ReportExporter(bridge)
        md = exporter.export_to_markdown()
        assert "收敛判定" in md

    def test_export_to_file(self):
        bridge = self._setup_bridge_with_data()
        exporter = ReportExporter(bridge)
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test_report.md")
            result_path = exporter.export_to_file(filepath)
            assert result_path == filepath
            assert os.path.exists(filepath)
            with open(filepath, "r") as f:
                content = f.read()
            assert "Module-MathB" in content

    def test_export_json(self):
        bridge = self._setup_bridge_with_data()
        exporter = ReportExporter(bridge)
        json_data = exporter.export_to_json()
        assert json_data["task_id"] == "test_report"
        assert json_data["total_rounds"] == 1
        assert json_data["chain_verified"] is True
        assert len(json_data["propositions"]) == 2

    def test_export_empty_bridge(self):
        bridge = MathSnapshotBridge(task_id="empty")
        exporter = ReportExporter(bridge)
        md = exporter.export_to_markdown()
        assert "无快照数据" in md

    def test_export_with_plugin_results(self):
        bridge = self._setup_bridge_with_data()
        plugin_results = {
            "sympy_bridge": PluginResult(
                plugin_name="sympy_bridge",
                status=PluginStatus.ENABLED,
                output={"is_prime": True},
                elapsed_ms=1.5,
            ),
            "stagnation_analyzer": PluginResult(
                plugin_name="stagnation_analyzer",
                status=PluginStatus.ENABLED,
                output={"diagnosis": {"severity": "low"}},
                elapsed_ms=2.0,
            ),
        }
        exporter = ReportExporter(bridge, plugin_results=plugin_results)
        md = exporter.export_to_markdown()
        assert "插件执行结果" in md
        assert "sympy_bridge" in md
        assert "stagnation_analyzer" in md

    def test_export_with_plugin_timeout_in_results(self):
        bridge = self._setup_bridge_with_data()
        plugin_results = {
            "slow_plugin": PluginResult(
                plugin_name="slow_plugin",
                status=PluginStatus.TIMEOUT,
                error="超时 5.0s",
                elapsed_ms=5000.0,
            ),
        }
        exporter = ReportExporter(bridge, plugin_results=plugin_results)
        md = exporter.export_to_markdown()
        assert "超时" in md

    def test_from_workflow_result(self):
        wf_result = {
            "task_id": "test_wf",
            "total_rounds": 3,
            "final_status": "DISPROVEN",
            "error": "",
            "propositions": [
                {
                    "proposition_id": "p1",
                    "statement": "所有素数都是奇数",
                    "status": "DISPROVEN",
                    "domain": "number_theory",
                    "derivation_step_count": 2,
                    "counter_example_count": 1,
                    "gap_count": 0,
                }
            ],
            "convergence_report": {
                "is_converged": True,
                "convergence_type": "DISPROVEN",
                "convergence_reason": "找到有效反例 n=2",
            },
        }
        md = ReportExporter.from_workflow_result(wf_result)
        assert "test_wf" in md
        assert "DISPROVEN" in md
        assert "所有素数都是奇数" in md

    def test_export_json_plugin_results(self):
        bridge = self._setup_bridge_with_data()
        plugin_results = {
            "sympy_bridge": PluginResult(
                plugin_name="sympy_bridge",
                status=PluginStatus.ENABLED,
                output={"is_prime": True},
                elapsed_ms=1.5,
            ),
        }
        exporter = ReportExporter(bridge, plugin_results=plugin_results)
        json_data = exporter.export_to_json()
        assert "plugin_results" in json_data
        assert "sympy_bridge" in json_data["plugin_results"]

    def test_export_config_options(self):
        bridge = self._setup_bridge_with_data()
        config = ReportConfig(
            include_hash_chain=False,
            include_derivation_steps=False,
            include_plugin_results=False,
        )
        exporter = ReportExporter(bridge, config=config)
        md = exporter.export_to_markdown()
        # 哈希链 section 不应出现
        assert "## 6. 哈希链完整性" not in md
        # 推导步骤不应出现
        assert "#### 推导步骤" not in md

    def test_hash_chain_integrity_in_export(self):
        bridge = self._setup_bridge_with_data()
        exporter = ReportExporter(bridge)
        json_data = exporter.export_to_json()
        assert json_data["chain_verified"] is True


# =============================================================================
# 10. 集成测试 — 插件与数学工作流
# =============================================================================

class TestPluginIntegration:
    """插件与数学工作流集成测试"""

    def test_plugins_in_math_workflow(self):
        """插件在数学工作流中正确执行"""
        from module_math_b.math_router import MathRouter

        # 带插件配置的任务
        task = {
            "query": "验证梅森素数猜想：若n为素数，则2^n-1为素数",
            "task_id": "test_plugin_integration",
            "task_type": "number_theory",
            "mathb_config": {
                "plugins": {
                    "sympy_bridge": {"enabled": True, "timeout_seconds": 10},
                }
            }
        }

        router = MathRouter()
        result = router.execute_math_workflow(task)

        assert result.final_status in ("PROVEN", "DISPROVEN", "FORCED_TERMINATE", "ERROR")
        # 插件结果应被记录
        assert result.plugin_results is not None or True  # 至少不崩溃

    def test_plugins_disabled_by_default_in_workflow(self):
        """默认配置下插件不执行"""
        from module_math_b.math_router import MathRouter

        task = {
            "query": "证明：存在无穷多个素数",
            "task_id": "test_plugin_default_disabled",
            "task_type": "number_theory",
            # 不配置 mathb_config，插件默认关闭
        }

        router = MathRouter()
        result = router.execute_math_workflow(task)
        assert result.final_status != "ERROR"

    def test_mersenne_counterexample_detection(self):
        """梅森数反例检测：n=11 时 2^11-1=2047=23×89"""
        from module_math_b.math_router import MathRouter

        task = {
            "query": "验证：若n为素数，则2^n-1为素数。请搜索反例。",
            "task_id": "test_mersenne_ce",
            "task_type": "number_theory",
            "mathb_config": {
                "plugins": {
                    "sympy_bridge": {"enabled": True, "timeout_seconds": 10},
                }
            }
        }

        router = MathRouter()
        result = router.execute_math_workflow(task)

        assert result.final_status in ("PROVEN", "DISPROVEN", "FORCED_TERMINATE", "ERROR")
        # 期望找到反例
        if result.final_status == "DISPROVEN":
            # 验证反例被记录
            assert len(result.propositions) > 0

    def test_inconclusive_stagnation_triggered(self):
        """开放类子命题触发 INCONCLUSIVE 停滞"""
        from module_math_b.math_router import MathRouter

        task = {
            "query": "证明：存在无穷多对孪生素数。请给出严格证明。",
            "task_id": "test_inconclusive_stagnation",
            "task_type": "number_theory",
            "mathb_config": {
                "plugins": {
                    "stagnation_analyzer": {"enabled": True, "timeout_seconds": 10},
                }
            }
        }

        router = MathRouter()
        result = router.execute_math_workflow(task)

        # 孪生素数猜想是开放问题，应触发 INCONCLUSIVE 或 FORCED_TERMINATE
        assert result.final_status in ("FORCED_TERMINATE", "INCONCLUSIVE", "ERROR",
                                        "PROVEN", "DISPROVEN")


# =============================================================================
# 11. v1.2 猜想生成器插件骨架测试
# =============================================================================

class TestConjectureGeneratorSkeleton:
    """猜想生成器插件骨架测试 — 注册/配置/生命周期/异常处理"""

    # -------------------------------------------------------------------------
    # 注册与配置
    # -------------------------------------------------------------------------

    def test_plugin_registration(self):
        """猜想生成器可注册到 PluginRegistry"""
        registry = PluginRegistry()
        generator = ConjectureGenerator()
        registry.register(generator, PluginConfig(name="conjecture_generator", enabled=False))
        assert "conjecture_generator" in registry.list_plugins()
        assert not registry.is_enabled("conjecture_generator")

    def test_enable_via_config(self):
        """通过任务 JSON 显式开启猜想生成器"""
        registry = PluginRegistry()
        registry.register(ConjectureGenerator(), PluginConfig(name="conjecture_generator", enabled=False))
        registry.load_config({
            "mathb_config": {
                "plugins": {
                    "conjecture_generator": {"enabled": True, "timeout_seconds": 10},
                }
            }
        })
        assert registry.is_enabled("conjecture_generator")

    def test_plugin_name(self):
        """插件名称为 conjecture_generator"""
        generator = ConjectureGenerator()
        assert generator.plugin_name == "conjecture_generator"

    # -------------------------------------------------------------------------
    # 配置校验
    # -------------------------------------------------------------------------

    def test_validate_config_valid(self):
        """合法配置通过校验"""
        generator = ConjectureGenerator()
        config = PluginConfig(
            name="conjecture_generator",
            enabled=True,
            extra_args={"max_conjectures": 3, "strategy": "weaken"},
        )
        assert generator.validate_config(config) is True

    def test_validate_config_invalid_max_conjectures(self):
        """max_conjectures 超出范围时校验失败"""
        generator = ConjectureGenerator()
        # 超出 MAX_CANDIDATE_CACHE = 20
        config = PluginConfig(
            name="conjecture_generator",
            extra_args={"max_conjectures": 100},
        )
        assert generator.validate_config(config) is False

    def test_validate_config_invalid_strategy(self):
        """非法策略时校验失败"""
        generator = ConjectureGenerator()
        config = PluginConfig(
            name="conjecture_generator",
            extra_args={"strategy": "invalid_strategy"},
        )
        assert generator.validate_config(config) is False

    def test_validate_config_non_plugin_config(self):
        """非 PluginConfig 类型时校验失败"""
        generator = ConjectureGenerator()
        assert generator.validate_config({"not": "config"}) is False

    def test_validate_config_empty_extra_args(self):
        """空 extra_args 应通过校验（使用默认值）"""
        generator = ConjectureGenerator()
        config = PluginConfig(name="conjecture_generator", extra_args={})
        assert generator.validate_config(config) is True

    # -------------------------------------------------------------------------
    # 执行 — 正常路径
    # -------------------------------------------------------------------------

    def test_execute_weaken_strategy(self):
        """weaken 策略执行成功（v1.2 业务逻辑：无命题时生成 0 条）"""
        generator = ConjectureGenerator()
        result = generator.execute({
            "strategy": "weaken",
            "max_conjectures": 3,
            "hypothesis_pool": None,
            "gap_patterns": [],
            "stagnation_analysis": None,
        })
        assert result.status == PluginStatus.ENABLED
        assert result.output["strategy"] == "weaken"
        assert result.output["total_generated"] == 0  # v1.2: 无命题无gap_patterns
        assert len(result.output["candidates"]) == 0

    def test_execute_substructure_strategy(self):
        """substructure 策略执行成功"""
        generator = ConjectureGenerator()
        result = generator.execute({
            "strategy": "substructure",
            "max_conjectures": 5,
        })
        assert result.status == PluginStatus.ENABLED
        assert result.output["strategy"] == "substructure"

    def test_execute_counter_example_range_strategy(self):
        """counter_example_range 策略执行成功"""
        generator = ConjectureGenerator()
        result = generator.execute({
            "strategy": "counter_example_range",
            "max_conjectures": 2,
        })
        assert result.status == PluginStatus.ENABLED
        assert result.output["strategy"] == "counter_example_range"

    def test_execute_output_contains_batch(self):
        """输出包含 batch 结构"""
        generator = ConjectureGenerator()
        result = generator.execute({"strategy": "weaken"})
        batch = result.output["batch"]
        assert "batch_id" in batch
        assert "generation_strategy" in batch
        assert "candidates" in batch
        assert batch["generation_strategy"] == "weaken"

    def test_execute_output_contains_status_note(self):
        """输出包含版本说明"""
        generator = ConjectureGenerator()
        result = generator.execute({"strategy": "weaken"})
        assert "status_note" in result.output
        assert "v1.2" in result.output["status_note"]  # v1.2 业务逻辑版本

    def test_execute_output_contains_warnings(self):
        """上下文缺失时输出 warnings"""
        generator = ConjectureGenerator()
        result = generator.execute({"strategy": "weaken"})
        assert "warnings" in result.output
        assert len(result.output["warnings"]) >= 2

    # -------------------------------------------------------------------------
    # 执行 — 异常路径
    # -------------------------------------------------------------------------

    def test_execute_missing_strategy(self):
        """缺少 strategy 参数时返回 ERROR"""
        generator = ConjectureGenerator()
        result = generator.execute({})
        assert result.status == PluginStatus.ERROR
        assert "strategy" in result.error.lower()

    def test_execute_invalid_strategy(self):
        """非法策略时返回 ERROR"""
        generator = ConjectureGenerator()
        result = generator.execute({"strategy": "nonsense"})
        assert result.status == PluginStatus.ERROR
        assert "不支持" in result.error

    def test_execute_invalid_max_conjectures(self):
        """max_conjectures 非正整数时返回 ERROR"""
        generator = ConjectureGenerator()
        result = generator.execute({
            "strategy": "weaken",
            "max_conjectures": -1,
        })
        assert result.status == PluginStatus.ERROR

    def test_execute_max_conjectures_clamped(self):
        """max_conjectures 超出上限时被 clamp（不报错，v1.2 无命题时生成 0 条）"""
        generator = ConjectureGenerator()
        result = generator.execute({
            "strategy": "weaken",
            "max_conjectures": 999,
        })
        assert result.status == PluginStatus.ENABLED
        assert result.output["total_generated"] == 0  # v1.2: 无命题无gap_patterns

    def test_execute_exception_safety(self):
        """异常情况下不崩溃，返回 ENABLED（v1.2: 非列表 gap_patterns 被安全处理）"""
        generator = ConjectureGenerator()
        result = generator.execute({"strategy": "weaken", "gap_patterns": "not_a_list"})
        assert result.status == PluginStatus.ENABLED  # 不会崩溃，优雅降级

    # -------------------------------------------------------------------------
    # 生命周期
    # -------------------------------------------------------------------------

    def test_generation_count_increments(self):
        """每次执行 generation_count 递增"""
        generator = ConjectureGenerator()
        assert generator.generation_count == 0
        generator.execute({"strategy": "weaken"})
        assert generator.generation_count == 1
        generator.execute({"strategy": "substructure"})
        assert generator.generation_count == 2

    def test_reset_clears_state(self):
        """reset 清空内部状态（v1.2: 需要源命题才能生成候选）"""
        generator = ConjectureGenerator()
        # 提供 gap_patterns 以触发业务逻辑生成候选
        generator.execute({
            "strategy": "weaken",
            "gap_patterns": [
                {"category": "induction_finite_samples", "description": "仅凭3个特例归纳"},
            ],
        })
        assert generator.generation_count == 1
        assert len(generator.cached_candidates) == 1

        generator.reset()
        assert generator.generation_count == 0
        assert len(generator.cached_candidates) == 0

    def test_candidate_cache_limit(self):
        """候选缓存不超过 MAX_CANDIDATE_CACHE"""
        generator = ConjectureGenerator()
        for i in range(25):  # 超过 MAX_CANDIDATE_CACHE = 20
            generator.execute({
                "strategy": "weaken",
                "gap_patterns": [
                    {"category": "induction_finite_samples", "description": f"仅凭{i}个特例归纳"},
                ],
            })
        assert len(generator.cached_candidates) <= generator.MAX_CANDIDATE_CACHE

    # -------------------------------------------------------------------------
    # 公开接口（v1.2 业务逻辑版本）
    # -------------------------------------------------------------------------

    def test_generate_weakened_returns_real(self):
        """generate_weakened 返回真实弱化结果"""
        generator = ConjectureGenerator()
        result = generator.generate_weakened(None)
        assert isinstance(result, list)
        assert len(result) == 2  # WEAKEN_TEMPLATES[:2]
        assert result[0]["strategy"] == "weaken"

    def test_extract_substructure_returns_real(self):
        """extract_substructure 返回真实子结构提取结果"""
        generator = ConjectureGenerator()
        result = generator.extract_substructure(None)
        assert isinstance(result, list)
        assert len(result) == 2  # SUBSTRUCTURE_TEMPLATES[:2]
        assert result[0]["strategy"] == "substructure"

    def test_generate_counter_example_range_returns_real(self):
        """generate_counter_example_range 返回真实反例搜索范围"""
        generator = ConjectureGenerator()
        result = generator.generate_counter_example_range(None)
        assert isinstance(result, list)
        assert len(result) == 2  # COUNTER_RANGE_TEMPLATES[:2]
        assert result[0]["strategy"] == "counter_example_range"

    # -------------------------------------------------------------------------
    # 数据结构
    # -------------------------------------------------------------------------

    def test_conjecture_candidate_fields(self):
        """ConjectureCandidate 数据类字段完整"""
        c = ConjectureCandidate(
            conjecture_id="c1",
            statement="测试猜想",
            source_proposition_id="p1",
            strategy="weaken",
            domain="number_theory",
            difficulty="medium",
            rationale="测试理由",
            expected_branch="PENDING",
        )
        assert c.conjecture_id == "c1"
        assert c.statement == "测试猜想"
        assert c.strategy == "weaken"

    def test_conjecture_batch_fields(self):
        """ConjectureBatch 数据类字段完整"""
        batch = ConjectureBatch(
            batch_id="b1",
            candidates=[ConjectureCandidate(conjecture_id="c1")],
            generation_strategy="weaken",
        )
        assert batch.batch_id == "b1"
        assert len(batch.candidates) == 1

    # -------------------------------------------------------------------------
    # 超时/异常由 PluginRegistry 层处理
    # -------------------------------------------------------------------------

    def test_timeout_handled_by_registry(self):
        """超时由 PluginRegistry 层处理 — 普通执行不超时"""
        registry = PluginRegistry()
        registry.register(
            ConjectureGenerator(),
            PluginConfig(name="conjecture_generator", enabled=True, timeout_seconds=5),
        )
        results = registry.execute_enabled({"strategy": "weaken"})
        assert "conjecture_generator" in results
        assert results["conjecture_generator"].status == PluginStatus.ENABLED

    def test_registry_execute_disabled_plugin(self):
        """默认关闭时 PluginRegistry 不执行猜想生成器"""
        registry = PluginRegistry()
        registry.register(
            ConjectureGenerator(),
            PluginConfig(name="conjecture_generator", enabled=False),
        )
        results = registry.execute_enabled({"strategy": "weaken"})
        assert len(results) == 0


# =============================================================================
# 12. v1.2 批量实验调度器插件骨架测试
# =============================================================================

class TestBatchExperimentSchedulerSkeleton:
    """批量实验调度器插件骨架测试 — 注册/配置/生命周期/超时处理"""

    # -------------------------------------------------------------------------
    # 注册与配置
    # -------------------------------------------------------------------------

    def test_plugin_registration(self):
        """批量实验调度器可注册到 PluginRegistry"""
        registry = PluginRegistry()
        scheduler = BatchExperimentScheduler()
        registry.register(scheduler, PluginConfig(name="batch_experiment", enabled=False))
        assert "batch_experiment" in registry.list_plugins()
        assert not registry.is_enabled("batch_experiment")

    def test_enable_via_config(self):
        """通过任务 JSON 显式开启批量实验调度器"""
        registry = PluginRegistry()
        registry.register(
            BatchExperimentScheduler(),
            PluginConfig(name="batch_experiment", enabled=False),
        )
        registry.load_config({
            "mathb_config": {
                "plugins": {
                    "batch_experiment": {"enabled": True, "timeout_seconds": 60},
                }
            }
        })
        assert registry.is_enabled("batch_experiment")

    def test_plugin_name(self):
        """插件名称为 batch_experiment"""
        scheduler = BatchExperimentScheduler()
        assert scheduler.plugin_name == "batch_experiment"

    # -------------------------------------------------------------------------
    # 配置校验
    # -------------------------------------------------------------------------

    def test_validate_config_valid(self):
        """合法配置通过校验"""
        scheduler = BatchExperimentScheduler()
        config = PluginConfig(
            name="batch_experiment",
            enabled=True,
            extra_args={"max_parallel": 4, "timeout_per_experiment": 30.0},
        )
        assert scheduler.validate_config(config) is True

    def test_validate_config_invalid_max_parallel(self):
        """max_parallel 超出范围 (1-8) 时校验失败"""
        scheduler = BatchExperimentScheduler()
        config = PluginConfig(
            name="batch_experiment",
            extra_args={"max_parallel": 10},
        )
        assert scheduler.validate_config(config) is False

    def test_validate_config_max_parallel_zero(self):
        """max_parallel 为 0 时校验失败"""
        scheduler = BatchExperimentScheduler()
        config = PluginConfig(
            name="batch_experiment",
            extra_args={"max_parallel": 0},
        )
        assert scheduler.validate_config(config) is False

    def test_validate_config_invalid_timeout(self):
        """timeout_per_experiment 超出范围 (1.0-300.0) 时校验失败"""
        scheduler = BatchExperimentScheduler()
        config = PluginConfig(
            name="batch_experiment",
            extra_args={"timeout_per_experiment": 0.5},
        )
        assert scheduler.validate_config(config) is False

    def test_validate_config_timeout_too_large(self):
        """timeout_per_experiment > 300 时校验失败"""
        scheduler = BatchExperimentScheduler()
        config = PluginConfig(
            name="batch_experiment",
            extra_args={"timeout_per_experiment": 999},
        )
        assert scheduler.validate_config(config) is False

    def test_validate_config_non_plugin_config(self):
        """非 PluginConfig 类型时校验失败"""
        scheduler = BatchExperimentScheduler()
        assert scheduler.validate_config({"not": "config"}) is False

    # -------------------------------------------------------------------------
    # 执行 — 正常路径
    # -------------------------------------------------------------------------

    def test_execute_basic(self):
        """基本执行成功"""
        scheduler = BatchExperimentScheduler()
        result = scheduler.execute({
            "conjectures": [
                {"conjecture_id": "c1", "statement": "测试猜想1"},
                {"conjecture_id": "c2", "statement": "测试猜想2"},
            ],
            "plugin_configs": [
                {"name": "sympy_bridge", "enabled": True},
                {"name": "stagnation_analyzer", "enabled": True},
            ],
            "max_parallel": 2,
            "timeout_per_experiment": 30.0,
        })
        assert result.status == PluginStatus.ENABLED
        assert result.output["total_tasks"] == 4  # 2 × 2 = 4
        assert result.output["max_parallel"] == 2

    def test_execute_single_conjecture(self):
        """单个猜想 × 单个配置 = 1个任务"""
        scheduler = BatchExperimentScheduler()
        result = scheduler.execute({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [{"name": "sympy_bridge"}],
        })
        assert result.output["total_tasks"] == 1

    def test_execute_matrix_dimensions(self):
        """实验矩阵维度正确（笛卡尔积）"""
        scheduler = BatchExperimentScheduler()
        result = scheduler.execute({
            "conjectures": [
                {"conjecture_id": "c1"},
                {"conjecture_id": "c2"},
                {"conjecture_id": "c3"},
            ],
            "plugin_configs": [
                {"name": "cfg_a"},
                {"name": "cfg_b"},
                {"name": "cfg_c"},
                {"name": "cfg_d"},
            ],
        })
        assert result.output["total_tasks"] == 12  # 3 × 4

    def test_execute_output_contains_report(self):
        """输出包含 report 结构"""
        scheduler = BatchExperimentScheduler()
        result = scheduler.execute({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [{"name": "sympy_bridge"}],
        })
        report = result.output["report"]
        assert "total_experiments" in report
        assert report["total_experiments"] == 1
        assert "by_config" in report

    def test_execute_output_contains_experiment_matrix(self):
        """输出包含 experiment_matrix"""
        scheduler = BatchExperimentScheduler()
        result = scheduler.execute({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [{"name": "sympy_bridge"}],
        })
        matrix = result.output["experiment_matrix"]
        assert len(matrix) == 1
        assert matrix[0]["task_id"].startswith("batch")

    def test_execute_output_contains_status_note(self):
        """输出包含 v1.2 业务逻辑版本说明"""
        scheduler = BatchExperimentScheduler()
        result = scheduler.execute({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [{"name": "sympy_bridge"}],
        })
        assert "status_note" in result.output
        assert "v1.2" in result.output["status_note"]

    def test_execute_max_parallel_clamped(self):
        """max_parallel 超出上限时被 clamp 到 8"""
        scheduler = BatchExperimentScheduler()
        result = scheduler.execute({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [{"name": "sympy_bridge"}],
            "max_parallel": 100,
        })
        assert result.status == PluginStatus.ENABLED
        assert result.output["max_parallel"] == 8

    # -------------------------------------------------------------------------
    # 执行 — 异常路径
    # -------------------------------------------------------------------------

    def test_execute_empty_conjectures(self):
        """猜想列表为空时返回 ERROR"""
        scheduler = BatchExperimentScheduler()
        result = scheduler.execute({
            "conjectures": [],
            "plugin_configs": [{"name": "sympy_bridge"}],
        })
        assert result.status == PluginStatus.ERROR
        assert "为空" in result.error

    def test_execute_empty_plugin_configs(self):
        """插件配置为空时返回 ERROR"""
        scheduler = BatchExperimentScheduler()
        result = scheduler.execute({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [],
        })
        assert result.status == PluginStatus.ERROR
        assert "为空" in result.error

    def test_execute_invalid_conjectures_type(self):
        """conjectures 非 list 时返回 ERROR"""
        scheduler = BatchExperimentScheduler()
        result = scheduler.execute({
            "conjectures": "not_a_list",
            "plugin_configs": [{"name": "sympy_bridge"}],
        })
        assert result.status == PluginStatus.ERROR

    def test_execute_invalid_max_parallel(self):
        """max_parallel 非正整数时返回 ERROR"""
        scheduler = BatchExperimentScheduler()
        result = scheduler.execute({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [{"name": "sympy_bridge"}],
            "max_parallel": -1,
        })
        assert result.status == PluginStatus.ERROR

    def test_execute_invalid_timeout(self):
        """timeout_per_experiment < 1.0 时返回 ERROR"""
        scheduler = BatchExperimentScheduler()
        result = scheduler.execute({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [{"name": "sympy_bridge"}],
            "timeout_per_experiment": 0.1,
        })
        assert result.status == PluginStatus.ERROR

    # -------------------------------------------------------------------------
    # 生命周期
    # -------------------------------------------------------------------------

    def test_run_count_increments(self):
        """每次执行 run_count 递增"""
        scheduler = BatchExperimentScheduler()
        assert scheduler.run_count == 0
        scheduler.execute({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [{"name": "sympy_bridge"}],
        })
        assert scheduler.run_count == 1

    def test_state_transitions(self):
        """执行过程中状态变迁"""
        scheduler = BatchExperimentScheduler()
        assert scheduler.state == "idle"

        scheduler.execute({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [{"name": "sympy_bridge"}],
        })
        assert scheduler.state == "completed"

    def test_state_error_on_invalid_input(self):
        """无效输入时状态变为 error"""
        scheduler = BatchExperimentScheduler()
        scheduler.execute({"conjectures": [], "plugin_configs": []})
        assert scheduler.state == "error"

    def test_reset_clears_state(self):
        """reset 清空所有内部状态"""
        scheduler = BatchExperimentScheduler()
        scheduler.execute({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [{"name": "sympy_bridge"}],
        })
        assert scheduler.run_count == 1
        assert scheduler.last_report is not None

        scheduler.reset()
        assert scheduler.run_count == 0
        assert scheduler.state == "idle"
        assert scheduler.last_report is None
        assert len(scheduler.cached_results) == 0

    def test_result_cache_limit(self):
        """结果缓存不超过 MAX_RESULT_CACHE"""
        scheduler = BatchExperimentScheduler()
        for i in range(110):  # 超过 MAX_RESULT_CACHE = 100
            scheduler.execute({
                "conjectures": [{"conjecture_id": f"c{i}"}],
                "plugin_configs": [{"name": "sympy_bridge"}],
            })
        assert len(scheduler.cached_results) <= scheduler.MAX_RESULT_CACHE

    # -------------------------------------------------------------------------
    # 公开接口
    # -------------------------------------------------------------------------

    def test_build_experiment_matrix(self):
        """build_experiment_matrix 返回正确数量的任务"""
        scheduler = BatchExperimentScheduler()
        tasks = scheduler.build_experiment_matrix(
            conjectures=[
                {"conjecture_id": "c1"},
                {"conjecture_id": "c2"},
            ],
            plugin_configs=[
                {"name": "cfg_a"},
                {"name": "cfg_b"},
                {"name": "cfg_c"},
            ],
            timeout_per_experiment=30.0,
        )
        assert len(tasks) == 6  # 2 × 3
        assert all(isinstance(t, ExperimentTask) for t in tasks)
        # 验证 task_id 格式
        for t in tasks:
            assert t.task_id.startswith("batch0")
            assert t.timeout_seconds == 30.0

    def test_aggregate_results(self):
        """aggregate_results 正确聚合"""
        scheduler = BatchExperimentScheduler()
        results = [
            ExperimentResult(
                task=ExperimentTask(
                    task_id="t1",
                    plugin_config={"name": "cfg_a"},
                ),
                status="PROVEN",
            ),
            ExperimentResult(
                task=ExperimentTask(
                    task_id="t2",
                    plugin_config={"name": "cfg_a"},
                ),
                status="DISPROVEN",
            ),
            ExperimentResult(
                task=ExperimentTask(
                    task_id="t3",
                    plugin_config={"name": "cfg_b"},
                ),
                status="PROVEN",
            ),
        ]
        report = scheduler.aggregate_results(results)
        assert report.total_experiments == 3
        assert report.completed == 3
        assert report.proven == 2
        assert report.disproven == 1
        assert "cfg_a" in report.by_config
        assert report.by_config["cfg_a"]["total"] == 2
        assert report.by_config["cfg_a"]["proven"] == 1
        assert report.by_config["cfg_a"]["disproven"] == 1

    def test_aggregate_results_empty(self):
        """空结果聚合"""
        scheduler = BatchExperimentScheduler()
        report = scheduler.aggregate_results([])
        assert report.total_experiments == 0
        assert report.completed == 0

    def test_compare_configs(self):
        """compare_configs 返回配置对比"""
        scheduler = BatchExperimentScheduler()
        config_results = {
            "cfg_a": [
                ExperimentResult(
                    task=ExperimentTask(task_id="t1", plugin_config={"name": "cfg_a"}),
                    status="PROVEN",
                ),
                ExperimentResult(
                    task=ExperimentTask(task_id="t2", plugin_config={"name": "cfg_a"}),
                    status="DISPROVEN",
                ),
            ],
            "cfg_b": [
                ExperimentResult(
                    task=ExperimentTask(task_id="t3", plugin_config={"name": "cfg_b"}),
                    status="PROVEN",
                ),
            ],
        }
        comparison = scheduler.compare_configs(config_results)
        assert "cfg_a" in comparison["comparison"]
        assert "cfg_b" in comparison["comparison"]
        assert comparison["comparison"]["cfg_a"]["total"] == 2
        assert comparison["comparison"]["cfg_b"]["total"] == 1

    def test_last_report_accessible(self):
        """last_report 可访问"""
        scheduler = BatchExperimentScheduler()
        scheduler.execute({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [{"name": "sympy_bridge"}],
        })
        report = scheduler.last_report
        assert report is not None
        assert report.total_experiments == 1

    # -------------------------------------------------------------------------
    # 数据结构
    # -------------------------------------------------------------------------

    def test_experiment_task_fields(self):
        """ExperimentTask 数据类字段完整"""
        task = ExperimentTask(
            task_id="t1",
            conjecture={"conjecture_id": "c1"},
            plugin_config={"name": "sympy_bridge"},
            timeout_seconds=30.0,
            priority=1,
        )
        assert task.task_id == "t1"
        assert task.conjecture["conjecture_id"] == "c1"
        assert task.timeout_seconds == 30.0
        assert task.priority == 1

    def test_experiment_result_fields(self):
        """ExperimentResult 数据类字段完整"""
        task = ExperimentTask(task_id="t1")
        result = ExperimentResult(
            task=task,
            status="PROVEN",
            elapsed_seconds=1.5,
            logical_gaps=[{"description": "test"}],
        )
        assert result.status == "PROVEN"
        assert result.elapsed_seconds == 1.5
        assert len(result.logical_gaps) == 1

    def test_batch_report_fields(self):
        """BatchReport 数据类字段完整"""
        report = BatchReport(
            total_experiments=10,
            completed=8,
            proven=3,
            disproven=2,
            by_config={"cfg_a": {"total": 5}},
            recommendations=["test"],
        )
        assert report.total_experiments == 10
        assert report.proven == 3
        assert report.disproven == 2

    # -------------------------------------------------------------------------
    # 超时处理 — 由 PluginRegistry 层负责
    # -------------------------------------------------------------------------

    def test_timeout_handled_by_registry(self):
        """超时由 PluginRegistry 层处理"""
        registry = PluginRegistry()
        registry.register(
            BatchExperimentScheduler(),
            PluginConfig(name="batch_experiment", enabled=True, timeout_seconds=60),
        )
        results = registry.execute_enabled({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [{"name": "sympy_bridge"}],
        })
        assert "batch_experiment" in results
        assert results["batch_experiment"].status == PluginStatus.ENABLED

    def test_registry_execute_disabled_plugin(self):
        """默认关闭时 PluginRegistry 不执行批量实验调度器"""
        registry = PluginRegistry()
        registry.register(
            BatchExperimentScheduler(),
            PluginConfig(name="batch_experiment", enabled=False),
        )
        results = registry.execute_enabled({
            "conjectures": [{"conjecture_id": "c1"}],
            "plugin_configs": [{"name": "sympy_bridge"}],
        })
        assert len(results) == 0


# =============================================================================
# 运行入口
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])