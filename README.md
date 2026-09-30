# Multi-Agent Brain Orchestrator

Orchestrator-Worker 多智能体集群编排系统，配备 Harness 协作管控底座与 B1-Final 冻结仿真内核。

---

## 架构概览

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Harness 协作管控底座                               │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌────────────────┐    │
│  │ Scheduler │  │ MetaRules │  │ Validator │  │ SnapshotManager│    │
│  │ (调度引擎) │  │(元协作规则)│  │(安全校验) │  │  (快照归档)    │    │
│  └───────────┘  └───────────┘  └───────────┘  └────────────────┘    │
│                                                                       │
│  生物启发抽象（全部在 Harness 层实现）:                                │
│  PV 中间神经元 → 快速抑制/去抑制 → 冲突仲裁                            │
│  胶质稳态理论   → 离子缓冲/突触修剪 → 背压控制 + 冗余回收              │
└──────────────────────────────────────────────────────────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         ▼                           ▼                           ▼
 ┌──────────────────┐     ┌──────────────────┐     ┌───────────────────┐
 │ LeadResearcher   │     │ BrainSubsystem   │     │    Workers        │
 │  (编排者)         │     │ B1-Final (冻结)   │     │  (工作者集群)      │
 │  - 任务分解       │     │ - 常量池         │     │  - Researcher     │
 │  - 任务分配       │     │ - 推理内核       │     │  - Coder          │
 │  - 结果聚合       │     │ - 外部接口       │     │  - Reviewer       │
 │                  │     │ ⚠️ 禁止修改       │     │  - Retrospective  │
 └──────────────────┘     └──────────────────┘     └───────────────────┘
```

---

## 核心铁律

| # | 约束 | 说明 |
|---|------|------|
| 1 | **Orchestrator-Worker 主架构** | LeadResearcher 是唯一编排者，所有 Worker 仅执行分配的专项子任务 |
| 2 | **Harness 外层管控** | 所有调度、规则、校验、归档由 Harness 层统一管理，子 Agent 不直接通信 |
| 3 | **生物启发仅抽象** | PV 中间神经元和胶质稳态理论仅作为设计灵感，抽象元机制全部实现在 harness 模块，禁止写入子 Agent |
| 4 | **B1-Final 永久冻结** | brain_subsystem 模块禁止修改任何常量、内核逻辑和接口签名 |

---

## 目录结构

```
multi-agent-brain-orchestrator/
├── agents/                   # 智能体封装
│   ├── __init__.py
│   ├── base_worker.py        # Worker 基类
│   ├── lead_researcher.py    # 编排者 (Orchestrator)
│   ├── worker_researcher.py  # 研究子智能体
│   ├── worker_coder.py       # 编码子智能体
│   ├── worker_reviewer.py    # 审查子智能体
│   └── worker_retrospective.py # 复盘子智能体
├── harness/                  # Harness 管控底座
│   ├── __init__.py
│   ├── scheduler.py          # 调度引擎 (PV 快速抑制)
│   ├── meta_rules.py         # 元协作规则 (胶质稳态)
│   ├── validator.py          # 安全校验
│   └── snapshot.py           # 快照归档
├── brain_subsystem/          # B1-Final 冻结内核
│   ├── __init__.py
│   ├── constants.py          # 冻结常量池 ⚠️
│   ├── kernel.py             # 冻结内核逻辑 ⚠️
│   └── interface.py          # 冻结外部接口 ⚠️
├── specs/                    # 系统架构与约束文档
│   ├── architecture.md
│   └── constraints.md
├── prompts/                  # 智能体 Prompt 模板
│   ├── lead_researcher.md
│   ├── worker_researcher.md
│   ├── worker_coder.md
│   ├── worker_reviewer.md
│   └── worker_retrospective.md
├── tests/                    # 测试
│   ├── __init__.py
│   ├── test_brain_subsystem.py
│   ├── test_harness.py
│   ├── test_agents.py
│   └── test_demo.py          # 闭环 Demo
├── data/snapshots/           # 版本快照归档
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## 快速开始

### 环境要求

- Python 3.11+
- pip

### 安装

```bash
cd multi-agent-brain-orchestrator
pip install -e .
```

### 运行测试

```bash
# 运行全部单元测试
pytest tests/ -v

# 运行闭环 Demo
python tests/test_demo.py
```

### 最小示例

```python
import asyncio
from agents.lead_researcher import LeadResearcher
from agents.worker_researcher import WorkerResearcher
from harness.scheduler import Scheduler, TaskPriority
from brain_subsystem.interface import BrainInterface

async def main():
    # 初始化
    lead = LeadResearcher()
    lead.register_worker(WorkerResearcher())
    brain = BrainInterface()

    # 编排执行
    task = {
        "task_id": "demo",
        "subtasks": [
            {"task_id": "s1", "task_type": "research", "query": "Hello"}
        ],
    }
    result = await lead.execute(task)
    print(result.status)

asyncio.run(main())
```

---

## 模块职责

### agents/ — 智能体集群

| 组件 | 角色 | 职责 |
|------|------|------|
| LeadResearcher | Orchestrator | 任务分解、Worker 分配、结果聚合 |
| WorkerResearcher | Worker | 信息检索、事实核查 |
| WorkerCoder | Worker | 代码生成、重构 |
| WorkerReviewer | Worker | 质量审查、合规检查 |
| WorkerRetrospective | Worker | 任务复盘、经验沉淀 |

### harness/ — 管控底座

| 组件 | 生物启发 | 抽象机制 |
|------|---------|---------|
| Scheduler | PV 快速抑制 | 任务优先级抢占、冲突仲裁 |
| MetaRules | 胶质稳态 | 资源阈值监控、背压控制、冗余回收 |
| Validator | — | 输入/输出校验、沙箱边界 |
| SnapshotManager | — | 状态快照、回滚、审计 |

### brain_subsystem/ — 冻结内核

| 组件 | 说明 |
|------|------|
| constants.py | 冻结常量池（认知阈值、振荡参数、稳态窗口） |
| kernel.py | 冻结内核逻辑（推理、上下文融合、振荡模拟） |
| interface.py | 冻结外部接口（仅允许入参） |

---

## 生物启发理论映射

### PV 中间神经元 (Parvalbumin+ Interneuron)

| 生物机制 | 抽象映射 | Harness 实现 |
|---------|---------|-------------|
| 快速抑制 (Fast Inhibition) | 高优先级抢占低优先级任务 | `Scheduler.preempt()` |
| 去抑制 (Disinhibition) | 死锁检测与解除 | `Scheduler` 队列管理 |
| 伽马振荡同步 (Gamma Sync) | 多 Agent 执行节奏对齐 | `MetaRules` 节奏控制 |

### 胶质稳态 (Glial Homeostasis)

| 生物机制 | 抽象映射 | Harness 实现 |
|---------|---------|-------------|
| 离子缓冲 (Ion Buffering) | 消息队列背压控制 | `MetaRules.apply_backpressure()` |
| 突触修剪 (Synaptic Pruning) | 闲置 Agent 回收 | `MetaRules.prune_idle_agents()` |
| 能量调节 (Energy Regulation) | 资源阈值监控与降载 | `MetaRules.update_metrics()` |

---

## 开发指南

### 添加新 Worker

1. 在 `agents/` 下创建新文件，继承 `BaseWorker`
2. 实现 `async def execute(self, task_payload) -> TaskResult`
3. 在 `agents/__init__.py` 中注册导出
4. 在 `prompts/` 下添加对应的 Prompt 模板
5. 在 `tests/` 下添加对应单元测试

### 约束遵守

- 子 Agent 内部禁止引用 `harness.meta_rules` 中的生物启发逻辑
- 子 Agent 内部禁止直接引用 `brain_subsystem` 模块
- 所有跨 Agent 通信通过 `harness` 层中转
- 修改 `brain_subsystem/` 下任何文件即为违规

---

## License

MIT