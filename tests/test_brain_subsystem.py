"""
tests.unit.test_brain_subsystem — B1-Final 冻结内核单元测试

验证冻结常量池和内核逻辑的正确性。
"""

import pytest
from brain_subsystem.constants import BRAIN_CONSTANTS, BrainConstants
from brain_subsystem.kernel import BrainKernel
from brain_subsystem.interface import BrainInterface


class TestBrainConstants:
    """B1-Final 冻结常量池测试"""

    def test_constants_are_frozen(self):
        """验证常量池不可修改"""
        assert isinstance(BRAIN_CONSTANTS, BrainConstants)
        # 尝试验证 frozen dataclass 特性
        with pytest.raises(Exception):
            BRAIN_CONSTANTS.COGNITION_THRESHOLD_MIN = 0.99  # type: ignore

    def test_threshold_bounds(self):
        """验证认知阈值在合理范围"""
        assert 0.0 < BRAIN_CONSTANTS.COGNITION_THRESHOLD_MIN < 1.0
        assert BRAIN_CONSTANTS.COGNITION_THRESHOLD_MIN < BRAIN_CONSTANTS.COGNITION_THRESHOLD_MAX


class TestBrainKernel:
    """B1-Final 冻结内核测试"""

    def test_infer(self):
        """验证基础推理"""
        kernel = BrainKernel()
        result = kernel.infer("test context", depth=2)
        assert result["context"] == "test context"
        assert result["depth"] == 2

    def test_infer_depth_capped(self):
        """验证推理深度被上限约束"""
        kernel = BrainKernel()
        result = kernel.infer("test", depth=999)
        assert result["depth"] == BRAIN_CONSTANTS.MAX_INFERENCE_DEPTH

    def test_oscillate(self):
        """验证振荡模拟"""
        kernel = BrainKernel()
        val = kernel.oscillate(0.0)
        assert 0.0 <= val <= 1.0

    def test_homeostasis(self):
        """验证稳态检测"""
        kernel = BrainKernel()
        stable = [0.5] * 20
        assert kernel.check_homeostasis(stable)


class TestBrainInterface:
    """B1-Final 冻结接口测试"""

    def test_run_inference(self):
        """验证外部推理接口"""
        iface = BrainInterface()
        result = iface.run_inference("hello", depth=1)
        assert result["context"] == "hello"

    def test_merge_context(self):
        """验证上下文融合接口"""
        iface = BrainInterface()
        result = iface.merge_context("A", "B")
        assert "A" in result["fused_context"]
        assert "B" in result["fused_context"]