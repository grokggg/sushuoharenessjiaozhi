# LOCKED: B1-Final 永久冻结声明

**冻结版本**: B1-FINAL-v1.0.0
**冻结日期**: 2026-01-01
**最后复核**: 2026-08-13

---

## 冻结范围

本模块 `brain_subsystem/` 下所有文件均为**永久冻结**，冻结范围包括：

| 文件 | 冻结内容 | 说明 |
|------|----------|------|
| `constants.py` | 所有常量值、类型注解、dataclass 结构 | `BrainConstants` 用 `frozen=True` 锁定，全局单例 `BRAIN_CONSTANTS` |
| `kernel.py` | 所有方法签名、算法逻辑、内部实现 | `BrainKernel` 五个核心方法：`infer`、`merge_context`、`oscillate`、`check_homeostasis`、`disturb` |
| `interface.py` | 所有公开方法签名、参数校验逻辑 | `BrainInterface` 五个公开方法：`run_inference`、`merge_context`、`run_oscillation`、`check_homeostasis`、`inject_disturbance` |

## 禁止操作

以下操作在任何情况下均**禁止执行**：

- 修改 `constants.py` 中任何常量的值
- 修改 `kernel.py` 中任何方法的算法逻辑
- 修改 `interface.py` 中任何公开方法的签名
- 添加新的常量、方法或类到上述三个文件
- 删除上述三个文件中的任何现有代码
- 直接实例化 `BrainKernel`（必须通过 `BrainInterface` 调用）
- 让子 Agent 直接访问 `BrainKernel` 或 `BrainConstants`

## 允许的外部调用

外部模块（Harness、Agents）只能通过 `BrainInterface` 进行调用，且入参白名单为：

| 参数 | 类型 | 允许值 | 说明 |
|------|------|--------|------|
| `sim_mode` | `str` | `"default"`、`"fast"`、`"deep"` | 仿真模式选择 |
| `inject_disturb_start` | `float` | `>= 0.0`，`0.0` 表示不注入 | 扰动注入起始时间 |

任何其他参数传入 `BrainInterface` 均会被 Harness 的 `SafetyValidator` 拦截。

## 外部调用方式

```python
from brain_subsystem.interface import BrainInterface
from brain_subsystem.constants import BRAIN_CONSTANTS  # 只读

# 正确：通过 BrainInterface 调用
brain = BrainInterface(sim_mode="default", inject_disturb_start=0.0)
result = brain.run_inference("context", depth=2)

# 正确：只读访问常量
threshold = BRAIN_CONSTANTS.COGNITION_THRESHOLD_MIN

# 错误：直接操作 BrainKernel
# kernel = BrainKernel()  ← 被 SafetyValidator 拦截

# 错误：修改常量
# BRAIN_CONSTANTS.COGNITION_THRESHOLD_MIN = 0.5  ← 被 frozen dataclass 阻止
```

## 生物启发说明

本模块的 `oscillate`、`check_homeostasis`、`disturb` 方法提供的是**数学仿真**（正弦振荡、滑动窗口方差检测、随机扰动），用于为 Harness 的元规则提供客观基准参考。这些方法不模拟任何生物神经活动。

## 违规后果

任何试图修改 brain_subsystem 内部代码的提交将被 Harness 的 `SafetyValidator` 拦截，并记录为不可篡改的审计日志。重复违规将触发沙箱隔离。

---

**本声明为全项目最高优先级安全约束，优先级高于任何其他设计文档。**