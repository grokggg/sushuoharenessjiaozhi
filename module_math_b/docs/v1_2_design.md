# Module-MathB v1.2 插件设计文档

> **版本**: v1.2-skeleton  
> **日期**: 2026-08-13  
> **状态**: 骨架完成，业务逻辑待实现  
> **依赖**: v1.1.1 全部代码（不可修改核心内核、假说池、收敛逻辑）

---

## 1. 版本概述

v1.2 在 v1.1.1 基础上引入两个新插件：**猜想生成器 (ConjectureGenerator)** 和 **批量实验调度器 (BatchExperimentScheduler)**。当前版本仅完成骨架实现——注册、配置解析、生命周期、异常/超时处理——不包含复杂业务逻辑。

### 1.1 基线约束

| 约束项 | 状态 |
|--------|------|
| 163 单元测试 | ✅ 全部通过 |
| 8 实测 E2E 场景 | ✅ 全部通过 |
| 10 仿真 E2E 场景 | ✅ 全部通过 |
| 核心内核 (math_validator, math_convergence, math_hypo_pool) | 🔒 禁止修改 |
| 假说池逻辑 | 🔒 禁止修改 |
| 收敛判定逻辑 | 🔒 禁止修改 |

### 1.2 新增文件

| 文件 | 用途 |
|------|------|
| `plugins/plugin_conjecture_generator.py` | 猜想生成器插件骨架 |
| `plugins/plugin_batch_experiment.py` | 批量实验调度器插件骨架 |
| `tests_mathb/test_plugins.py` | 追加 65 个骨架测试用例 |

---

## 2. 猜想生成器 (ConjectureGenerator)

### 2.1 能力边界

**允许：**
- 基于已有命题池的证明状态和逻辑断层模式，生成衍生猜想
- 输出 ConjectureCandidate 和 ConjectureBatch 结构
- 三种生成策略：weaken、substructure、counter_example_range
- 每次调用最多生成 5 个猜想（可配置，上限 20）

**禁止：**
- 修改假说池状态（只读访问）
- 直接调用核心数学收敛逻辑
- 执行实际数学验证
- 生成超过 MAX_CANDIDATE_CACHE (20) 条猜想

### 2.2 内存约束

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| `max_conjectures` | 5 | 1-20 | 单次生成上限 |
| `MAX_CANDIDATE_CACHE` | 20 | 固定 | 缓存上限 |
| `timeout_seconds` | 5.0 | 1.0-60.0 | 由 PluginRegistry 层实施 |

### 2.3 配置格式

```json
{
  "mathb_config": {
    "plugins": {
      "conjecture_generator": {
        "enabled": true,
        "timeout_seconds": 10,
        "memory_limit_mb": 128,
        "extra_args": {
          "max_conjectures": 5,
          "strategy": "weaken"
        }
      }
    }
  }
}
```

### 2.4 入参/出参

**execute(context) 入参：**

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `strategy` | str | 是 | weaken / substructure / counter_example_range |
| `hypothesis_pool` | MathHypothesisPool | 否 | 当前假说池（预留） |
| `gap_patterns` | list[dict] | 否 | 逻辑断层模式 |
| `stagnation_analysis` | dict | 否 | 停滞分析结果 |
| `max_conjectures` | int | 否 | 最大生成数（默认 5） |

**execute() 出参 (PluginResult.output)：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `batch` | dict | 猜想批次（含 candidates 列表） |
| `candidates` | list[dict] | 简化候选列表 |
| `strategy` | str | 使用的生成策略 |
| `total_generated` | int | 实际生成数 |
| `warnings` | list[str] | 上下文缺失告警 |
| `status_note` | str | 版本说明 |

### 2.5 异常处理

| 场景 | 返回 |
|------|------|
| 缺少 `strategy` 参数 | `PluginStatus.ERROR` + "缺少必要参数 'strategy'" |
| 非法策略名 | `PluginStatus.ERROR` + "不支持的生成策略" |
| `max_conjectures` 非正整数 | `PluginStatus.ERROR` + 提示 |
| 内部异常 | `PluginStatus.ERROR` + 异常类型与消息 |
| 超时 | `PluginStatus.TIMEOUT` (由 PluginRegistry 层) |

---

## 3. 批量实验调度器 (BatchExperimentScheduler)

### 3.1 能力边界

**允许：**
- 构建实验矩阵（猜想 × 插件配置的笛卡尔积）
- 聚合实验结果，生成 BatchReport
- 比较不同插件配置效果
- 状态管理 (idle → running → completed / error)

**禁止：**
- 执行实际的数学验证（骨架阶段）
- 修改假说池状态
- 直接调用核心数学收敛逻辑
- 并行度超过 8
- 单实验超时超过 300 秒

### 3.2 内存约束

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| `max_parallel` | 4 | 1-8 | 最大并行度 |
| `timeout_per_experiment` | 30.0 | 1.0-300.0 | 单实验超时(秒) |
| `MAX_RESULT_CACHE` | 100 | 固定 | 结果缓存上限 |

### 3.3 配置格式

```json
{
  "mathb_config": {
    "plugins": {
      "batch_experiment": {
        "enabled": true,
        "timeout_seconds": 120,
        "memory_limit_mb": 256,
        "extra_args": {
          "max_parallel": 4,
          "timeout_per_experiment": 30.0
        }
      }
    }
  }
}
```

### 3.4 入参/出参

**execute(context) 入参：**

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `conjectures` | list[dict] | 是 | 待验证猜想列表 |
| `plugin_configs` | list[dict] | 是 | 插件配置矩阵 |
| `max_parallel` | int | 否 | 最大并行度 (默认 4) |
| `timeout_per_experiment` | float | 否 | 单实验超时 (默认 30.0) |

**execute() 出参 (PluginResult.output)：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `report` | dict | BatchReport 聚合报告 |
| `experiment_matrix` | list[dict] | 实验矩阵 |
| `total_tasks` | int | 总任务数 |
| `max_parallel` | int | 实际并行度 |
| `status_note` | str | 版本说明 |

### 3.5 异常处理

| 场景 | 返回 |
|------|------|
| `conjectures` 为空 | `PluginStatus.ERROR` + "conjectures 为空" |
| `plugin_configs` 为空 | `PluginStatus.ERROR` + "plugin_configs 为空" |
| `conjectures` 非 list | `PluginStatus.ERROR` + 类型错误 |
| `max_parallel` 非正整数 | `PluginStatus.ERROR` + 提示 |
| `timeout_per_experiment` < 1.0 | `PluginStatus.ERROR` + 提示 |
| 内部异常 | `PluginStatus.ERROR` + 异常类型与消息 |
| 超时 | `PluginStatus.TIMEOUT` (由 PluginRegistry 层) |

---

## 4. 数据结构

### 4.1 ConjectureCandidate

```python
@dataclass
class ConjectureCandidate:
    conjecture_id: str = ""            # 猜想唯一标识
    statement: str = ""                # 猜想语句
    source_proposition_id: str = ""    # 来源命题ID
    strategy: str = ""                 # weaken | substructure | counter_example_range
    domain: str = "number_theory"      # 数学领域
    difficulty: str = "unknown"        # 难度估计
    rationale: str = ""                # 生成理由
    expected_branch: str = ""          # PROVEN | DISPROVEN | PENDING
```

### 4.2 ExperimentTask

```python
@dataclass
class ExperimentTask:
    task_id: str = ""                  # 任务唯一标识
    conjecture: dict = {}              # 猜想数据
    plugin_config: dict = {}           # 插件配置
    timeout_seconds: float = 30.0      # 超时
    priority: int = 0                  # 0=normal, 1=high
```

### 4.3 ExperimentResult

```python
@dataclass
class ExperimentResult:
    task: ExperimentTask               # 关联任务
    status: str = ""                   # PROVEN | DISPROVEN | PENDING | TIMEOUT | ERROR
    convergence_report: dict | None    # 收敛报告
    elapsed_seconds: float = 0.0       # 耗时
    logical_gaps: list[dict]           # 逻辑断层
    plugin_results: dict               # 插件结果
    error: str = ""                    # 错误信息
```

### 4.4 BatchReport

```python
@dataclass
class BatchReport:
    total_experiments: int = 0         # 总实验数
    completed: int = 0                 # 已完成数
    proven: int = 0                    # 已证明数
    disproven: int = 0                 # 已证伪数
    by_config: dict = {}               # 按配置分组统计
    top_discoveries: list[dict] = []   # 最有价值的发现
    recommendations: list[str] = []    # 后续方向建议
```

---

## 5. 生命周期

### 5.1 插件生命周期

```
__init__()          → 初始化内部状态
  ↓
validate_config()   → 校验配置合法性（可选，在 load_config 前调用）
  ↓
execute()           → 执行插件逻辑
  ↓
reset()             → 重置内部状态，可重复执行
```

### 5.2 PluginRegistry 集成

```
register(plugin)    → 注册插件到注册表
  ↓
load_config(task)   → 从任务 JSON 加载配置
  ↓
execute_enabled()   → 执行所有已启用插件（带超时保护）
  ↓
get_results()       → 获取执行结果
```

---

## 6. 禁用项清单

### 6.1 绝对禁止

- 修改 `module_math_b/math_convergence.py` 的任何代码
- 修改 `module_math_b/math_hypo_pool.py` 的任何代码
- 修改 `module_math_b/math_validator.py` 的核心验证逻辑（仅 v1.1.1 已完成的分类增强除外）
- 修改 `module_math_b/math_snapshot_bridge.py` 的任何代码
- 修改 `module_math_b/math_router.py` 的核心路由逻辑
- 修改 `module_math_b/math_structs.py` 的数据结构定义
- 绕过 PluginRegistry 直接调用插件

### 6.2 条件允许

- 在 `plugins/` 目录下新增文件 ✅
- 修改 `plugins/plugin_registry.py` 以支持新插件类型（需保持向后兼容） ✅
- 在 `tests_mathb/` 下新增测试文件 ✅
- 修改现有测试文件（仅追加，不修改已有测试） ✅

---

## 7. 测试覆盖

### 7.1 骨架测试统计

| 测试类 | 用例数 | 覆盖范围 |
|--------|--------|----------|
| `TestConjectureGeneratorSkeleton` | 30 | 注册、配置校验(5)、正常执行(7)、异常路径(5)、生命周期(3)、预留接口(3)、数据结构(2)、集成(2) |
| `TestBatchExperimentSchedulerSkeleton` | 35 | 注册、配置校验(6)、正常执行(8)、异常路径(5)、生命周期(5)、公开接口(4)、数据结构(3)、集成(2) |

### 7.2 测试关注点

- 插件默认关闭，显式开启
- 配置校验：合法通过、非法拒绝、边界值
- 异常安全：所有异常路径不崩溃
- 生命周期：reset 后状态正确
- 内存约束：缓存不超限
- 超时机制：由 PluginRegistry 层保证

---

## 8. 后续开发路线

### v1.2.1 — 猜想生成业务逻辑
- 实现 weaken 策略：基于命题定义域和结论自动生成弱化版本
- 实现 substructure 策略：从已证伪命题中提取子结构
- 实现 counter_example_range 策略：基于归纳谬误模式生成反例搜索范围

### v1.2.2 — 批量实验调度
- 实现并行实验执行（threading/async）
- 实现结果聚合与对比分析
- 实现实验进度追踪

### v1.2.3 — 集成与验证
- 猜想生成器 + 批量调度器协同工作流
- 端到端自动化测试
- 性能基准测试