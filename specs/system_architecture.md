# Multi-Agent Brain Orchestrator — 系统架构定版文档

**文档版本**: v1.0-final
**定版日期**: 2026-08-13
**状态**: 全项目唯一权威设计文档，后续所有开发必须以此为准

---

## 1 项目概述与参考来源

### 1.1 项目定位

Multi-Agent Brain Orchestrator 是一个基于 Claude 编排者-工作者（Orchestrator-Worker）范式的多智能体集群系统。项目目标不是构建一个"更强的单体模型"，而是构建一套**让多个模型在结构化约束下协作产出超越单体能力边界的研究成果**的协作基础设施。

### 1.2 三大参考来源

**主骨架：Claude Orchestrator-Worker 编排者-工作者多智能体集群**

系统采用单编排者、多工作者的星型拓扑。LeadResearcher 作为唯一编排者负责科研规划与任务调度，各 Worker 子智能体在其分配的领域内独立产出原始观点。编排者不拥有最终裁决权——所有子 Agent 输出统一上交 Harness 层进行客观化处理。

**管控底座：Harness 协作管控层**

Harness 的核心理念来源于一个反复验证的工程观察：**模型能力越强，上层协作层的厚度越关键**。当单个 Agent 已经具备高质量推理能力时，多 Agent 集群的瓶颈不再是"某个 Agent 不够聪明"，而是"多个聪明 Agent 之间的协调断裂"——具体表现为：

- 上下文版本不一致：不同 Agent 基于不同时间点或不同来源的信息做出判断
- 结论漂移：多轮讨论后偏离初始事实依据
- 协作死锁：两个 Agent 互不退让，辩论无法收敛

Harness 层正是为解决这些协调断裂而设计的外层管控基础设施。

**生物启发：PV 中间神经元 + 胶质稳态理论**

PV 中间神经元的兴奋-抑制平衡机制和胶质细胞的稳态维持理论为 Harness 的元协作规则提供了设计灵感。关键约束：**生物理论仅作为抽象启发，不作为系统运行主体代码**。所有从生物启发中抽象出的元协作规则全部部署在 Harness 层，子 Agent 内部不包含任何生物细胞逻辑。

### 1.3 四条元协作规则

从 PV 中间神经元和胶质稳态理论中抽象出以下四条元协作规则，全部实现在 Harness 层：

**规则①：强势信号抑制（Strong Signal Inhibition）**

生物启发：PV 中间神经元对锥体神经元的前馈抑制，防止单一兴奋信号过度传播。

抽象机制：当集群内某个观点或结论的主导度超过阈值（单一 Agent 或单一观点占据超过 60% 的讨论权重），Harness 主动注入反向质询，抑制该观点进一步垄断集群讨论方向。这确保弱势但可能正确的观点不被淹没。

**规则②：集群震荡检测（Cluster Oscillation Detection）**

生物启发：神经网络中异常同步振荡往往与功能失调相关（如癫痫样放电），正常认知依赖于振荡模式的动态切换。

抽象机制：识别集群在多轮讨论中反复推翻重建的无效震荡模式。当检测到同一问题被来回推翻超过 3 轮且无新增证据时，Harness 强制中断讨论链条，回归到最原始的客观观测数据进行重新锚定。

**规则③：冲突调解（Conflict Mediation）**

生物启发：PV 中间神经元通过去抑制机制调节局部微环路中的竞争性信号。

抽象机制：当多个 Agent 的输出存在不可调和矛盾时，不以"多数票"或"编排者主观判断"裁决，而是以客观仿真结果（B1 内核模拟输出）为基准，过滤掉偏离基准超过阈值的纯主观推演结论。

**规则④：超限熔断（Over-limit Circuit Breaker）**

生物启发：胶质细胞的能量稳态调节——当神经元活动超出代谢供给能力时，胶质细胞限制过量放电。

抽象机制：当同一问题在多轮迭代后仍无法收敛（连续 5 轮后各 Agent 结论方差仍大于阈值），Harness 触发熔断，输出"证据不足，无法收敛"标记，强制禁止强行下定论。熔断后的任务进入待补充证据队列，等待新的外部数据注入后再重新激活。

---

## 2 角色划分

### 2.1 编排者：LeadResearcher Agent

**唯一编排者**。LeadResearcher 不参与具体观点的生成与辩护，其职责限于：

- **任务拆解**：将顶层科研问题分解为可并行或串行的子任务 DAG
- **科研规划**：制定研究路径，决定先采集再假说还是先假说再验证
- **子 Agent 调度**：根据子任务类型分配对应 Worker，控制并发与顺序
- **全局记忆维护**：持有集群共享上下文，确保所有 Worker 看到一致的版本化信息

**刚性约束**：LeadResearcher 不做最终裁决。它不判断哪个 Agent 的结论"更正确"，不充当"终极裁判"。所有子 Agent 的原始输出统一上交 Harness 层，由 Harness 的元规则进行客观化处理。

### 2.2 工作者子智能体（Worker Agents）

所有 Worker 共享以下行为约束：
- 只输出**原始观点**，无最终决策权
- 全部输出上交 Harness，不直接与其他 Worker 通信
- 内部不包含任何生物启发逻辑（PV/胶质等）
- 不感知集群整体状态（无全局视野）

**Worker 角色清单**：

| Worker | 类名 | 核心职责 |
|--------|------|----------|
| 采集感知 Agent | `WorkerPerception` | 从外部数据源采集原始观测数据，执行初步清洗与结构化，不做推论 |
| 假说构建 Agent | `WorkerHypothesisBuilder` | 基于观测数据构建可验证的科学假说，每个假说必须附带可证伪条件 |
| 怀疑批判 Agent | `WorkerSkeptic` | 对现有假说和结论进行系统性批判，寻找逻辑漏洞、样本偏差、方法论缺陷 |
| 红队裁判 Agent | `WorkerRedTeam` | 以对抗性视角设计最坏情况测试用例，验证结论在极端条件下的鲁棒性 |
| 记录归档 Agent | `WorkerArchivist` | 将每轮讨论的完整上下文、各 Agent 输出、元规则裁决记录归档为结构化日志 |

### 2.3 角色交互约束

```
LeadResearcher (编排者)
    │
    │ 任务分配 ───────────────────────────────────────────┐
    │                                                      │
    ▼                                                      ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ Perception    │  │ Hypothesis    │  │ Skeptic        │  │ RedTeam       │  │ Archivist     │
│ (采集感知)     │  │ Builder       │  │ (怀疑批判)      │  │ (红队裁判)      │  │ (记录归档)     │
│               │  │ (假说构建)     │  │               │  │               │  │               │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │                  │                  │
        └──────────────────┴──────────────────┴──────────────────┴──────────────────┘
                                          │
                                          ▼
                              ┌─────────────────────┐
                              │  Harness 管控底座     │
                              │  (元规则处理 + 客观化) │
                              └─────────────────────┘
```

---

## 3 Harness 管控底座

### 3.1 职责总览

Harness 是架设在所有 Agent 上方的外层管控基础设施，承担四大核心职责。Agent 不直接感知 Harness 的内部机制，但所有跨 Agent 协调行为均通过 Harness 完成。

### 3.2 职责一：任务执行循环（Task Execution Loop）

Harness 维护集群的完整执行生命周期：

```
[任务注入] → [分解] → [调度分配] → [并行执行] → [结果回收] → [元规则处理] → [输出/再循环]
                                                              ↑                    │
                                                              └── 需要迭代 ────────┘
```

- **任务注入**：外部系统或用户通过 Harness 的标准接口提交任务
- **分解**：Harness 将任务转发给 LeadResearcher 进行分解，返回子任务 DAG
- **调度分配**：Harness 的 Scheduler 根据子任务类型和 Worker 能力矩阵进行匹配分配
- **并行执行**：Worker 在 Harness 分配的沙箱环境中独立执行
- **结果回收**：所有 Worker 输出统一回收到 Harness，不做中间裁决
- **元规则处理**：Harness 的 MetaRules 引擎对回收结果执行四条元规则，决定是否需要迭代
- **输出/再循环**：若结果收敛则输出，否则生成新一轮子任务进入循环

### 3.3 职责二：状态上下文管理（State & Context Management）

- **版本化上下文**：每次任务分解时生成上下文快照版本号，所有 Worker 基于同一版本执行
- **全局记忆读写**：Worker 通过 Harness 提供的只读接口访问全局记忆，写入通过 Harness 的写接口统一版本化
- **上下文一致性校验**：任何 Worker 输出中引用的上下文版本号必须与当前活跃版本一致，否则标记为过期输出
- **快照与回滚**：每个执行循环结束后自动生成状态快照，支持回滚到任意历史版本

### 3.4 职责三：工具资源调度（Tool & Resource Scheduling）

- **工具注册与发现**：Worker 声明所需工具，Harness 统一管理工具的生命周期和权限
- **并发控制**：根据 B1-Final 常量池定义的 `MAX_ACTIVE_AGENTS` 限制并发 Worker 数量
- **资源配额**：每个 Worker 分配独立资源配额（CPU/内存/API 调用次数），超限自动降级
- **背压控制**：当消息队列深度超过阈值时，Harness 主动限制新任务注入速率

### 3.5 职责四：安全边界治理（Security Boundary Governance）

- **输入校验**：所有进入集群的外部输入必须通过 Harness Validator 的格式与约束校验
- **输出合规**：所有 Worker 输出必须通过 Harness Validator 的内容合规性检查
- **沙箱隔离**：每个 Worker 在独立沙箱中运行，禁止越权访问（文件系统、网络、其他 Worker 状态）
- **审计追踪**：所有 Harness 决策（元规则触发、熔断、回滚）均记录为不可篡改的审计日志

---

## 4 Brain Subsystem B1-Final

### 4.1 状态声明

**brain_subsystem 模块标记为永久冻结（B1-Final）**。冻结范围包括：

- `constants.py`：所有内核常量，禁止增删改
- `kernel.py`：所有内核算法逻辑，禁止修改
- `interface.py`：所有外部接口签名，禁止修改

### 4.2 允许的外部参数

BrainInterface 仅允许通过以下两个参数进行外部控制：

| 参数 | 类型 | 说明 |
|------|------|------|
| `sim_mode` | `str` | 仿真模式选择。可选值：`"default"`（标准推理）、`"fast"`（快速模式，降低推理深度）、`"deep"`（深度模式，增加推理链长度） |
| `inject_disturb_start` | `float` | 扰动注入起始时间。在振荡模拟中，从此时间点开始注入外部扰动信号，用于模拟外部干扰对系统稳态的影响。范围 `[0.0, ∞)`，`0.0` 表示不注入扰动 |

### 4.3 调用约束

- B1 内核的调用必须通过 `BrainInterface`，禁止直接实例化 `BrainKernel`
- Harness 层可以通过适配器封装 B1 接口，但不得修改 B1 内部实现
- B1 的输出仅作为 Harness 元规则③（冲突调解）的客观基准参考，不作为最终裁决依据

---

## 5 完整文本数据流

### 5.1 主数据流图

```
                              ┌─────────────────────┐
                              │   外部任务输入         │
                              │  (User / System)     │
                              └──────────┬──────────┘
                                         │
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│                              Harness 管控底座                                    │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        Validator (输入校验)                                │  │
│  │   校验格式 → 校验约束 → 注入任务ID → 生成上下文版本号                        │  │
│  └──────────────────────────────────┬───────────────────────────────────────┘  │
│                                     │                                           │
│                                     ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        LeadResearcher (编排者)                             │  │
│  │   接收任务 → 分解为子任务DAG → 维护全局记忆 → 返回子任务列表                 │  │
│  └──────────────────────────────────┬───────────────────────────────────────┘  │
│                                     │                                           │
│                                     ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        Scheduler (调度引擎)                                │  │
│  │   能力匹配 → 优先级排序 → 并发控制 → 分配Worker → 注入上下文版本号           │  │
│  └───────┬──────────┬──────────┬──────────┬──────────┬──────────────────────┘  │
│          │          │          │          │          │                          │
│          ▼          ▼          ▼          ▼          ▼                          │
│  ┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐                  │
│  │Perception││Hypothesis││ Skeptic  ││ RedTeam  ││Archivist │                  │
│  │(采集感知) ││ Builder  ││(怀疑批判) ││(红队裁判) ││(记录归档) │                  │
│  │          ││(假说构建) ││          ││          ││          │                  │
│  └────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘└────┬─────┘                  │
│       │           │           │           │           │                         │
│       └───────────┴───────────┴───────────┴───────────┘                         │
│                            │                                                    │
│                            ▼                                                    │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        Validator (输出校验)                                │  │
│  │   校验上下文版本 → 校验内容合规 → 校验输出格式 → 通过/驳回                  │  │
│  └──────────────────────────────────┬───────────────────────────────────────┘  │
│                                     │                                           │
│                                     ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        MetaRules (元协作规则引擎)                           │  │
│  │                                                                           │  │
│  │  ① 强势信号抑制: 检测主导度 > 60% → 注入反向质询                            │  │
│  │  ② 集群震荡检测: 检测推翻 > 3轮 → 回归原始观测                             │  │
│  │  ③ 冲突调解:     多Agent矛盾 → B1基准过滤 → 剔除偏离 > 阈值                │  │
│  │  ④ 超限熔断:     连续 > 5轮不收敛 → 标记证据不足                            │  │
│  │                                                                           │  │
│  │  判断结果:                                                                │  │
│  │    ├── 收敛 → 进入输出阶段                                                 │  │
│  │    ├── 需迭代 → 生成新子任务 → 回到 Scheduler                              │  │
│  │    └── 熔断 → 标记证据不足 → 进入待补充证据队列                             │  │
│  └──────────────────────────────────┬───────────────────────────────────────┘  │
│                                     │                                           │
│                                     ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        SnapshotManager (快照归档)                          │  │
│  │   生成状态快照 → 版本化存储 → 审计日志 → 可选回滚                           │  │
│  └──────────────────────────────────┬───────────────────────────────────────┘  │
│                                     │                                           │
│                                     ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │                        Validator (最终输出校验)                            │  │
│  │   结构完整性 → 证据链完整性 → 不确定性标注 → 最终输出                        │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │   结构化输出          │
                              │  (ReflectionOutput)  │
                              └─────────────────────┘
```

### 5.2 数据流关键节点说明

| 节点 | 输入 | 输出 | 校验点 |
|------|------|------|--------|
| 输入校验 | 外部原始任务 | 标准化任务 + 版本号 | 格式、必填字段、约束合规 |
| 编排分解 | 标准化任务 | 子任务 DAG | 子任务可执行性、Worker 能力覆盖 |
| 调度分配 | 子任务 DAG | Worker 分配方案 | 并发上限、资源配额 |
| Worker 执行 | 子任务 + 上下文版本 | 原始观点输出 | 沙箱边界、输出格式 |
| 输出校验 | 原始观点输出 | 合规输出 | 上下文版本一致性、内容合规 |
| 元规则处理 | 合规输出集合 | 收敛/迭代/熔断决策 | 四条元规则依次执行 |
| 快照归档 | 完整状态 | 版本化快照 | 存储完整性 |
| 最终输出 | 收敛结果 | ReflectionOutput | 结构完整性、证据链 |

### 5.3 B1 内核在数据流中的位置

```
MetaRules ③ 冲突调解
        │
        │ 存在矛盾时调用
        ▼
┌─────────────────┐
│ BrainInterface   │
│ (B1-Final 冻结)  │
│                 │
│ sim_mode = 当前  │
│ inject_disturb_  │
│ start = 0.0      │
└────────┬────────┘
         │
         ▼
    客观基准参考值
    (用于过滤偏离的主观推演)
```

B1 内核仅在 MetaRules 规则③触发时被调用，其输出作为客观仿真基准，用于衡量各 Agent 主观推演结论的偏离程度。偏离超过阈值（`COGNITION_THRESHOLD_MAX = 0.95`）的结论被标记为"过度主观推演"并排除。

---

## 6 重要声明

**胶质细胞稳态理论与 PV 中间神经元理论在本系统中仅作为生物启发来源，不是系统运行主体。**

具体而言：

- 本系统不模拟神经元放电、突触传递、离子通道等生物物理过程
- Harness 层的四条元协作规则是**工程抽象**，命名和设计灵感来源于生物机制，但实现为纯软件工程逻辑
- 子 Agent 内部不包含任何与生物机制相关的代码、变量或逻辑分支
- B1-Final 内核的振荡模拟和稳态检测是**数学仿真**，用于为 Harness 提供客观基准，不模拟生物神经活动
- 任何将本系统描述为"神经形态计算"或"类脑系统"的表述均为误解

---

## 7 输出结构体定义

### 7.1 ReflectionOutput

```python
@dataclass
class ReflectionOutput:
    """Harness 元规则处理后的最终输出结构体"""

    # 任务标识
    task_id: str                              # 顶层任务唯一标识
    context_version: str                      # 上下文版本号

    # 收敛状态
    status: Literal["converged", "diverged", "circuit_broken", "evidence_insufficient"]

    # 各 Agent 原始输出
    worker_outputs: dict[str, Any]            # key: agent_id, value: 原始输出

    # 元规则裁决记录
    meta_rules_log: list[MetaRuleRecord]      # 每条元规则的触发记录

    # 最终结论
    conclusion: str                           # 最终结论文本
    confidence: float                         # 置信度 [0.0, 1.0]
    evidence_chain: list[EvidenceLink]        # 证据链

    # 不确定性标注
    limitations: list[str]                    # 已知局限
    open_questions: list[str]                 # 未解决问题
    requires_more_data: bool                  # 是否需要更多数据

    # 元信息
    created_at: str                           # ISO 8601 时间戳
    iteration_count: int                      # 迭代轮数
    snapshot_id: str                          # 关联快照 ID
```

### 7.2 ProposedTaskPayload

```python
@dataclass
class ProposedTaskPayload:
    """编排者分解后的子任务结构体"""

    # 任务标识
    task_id: str                              # 子任务唯一标识
    parent_task_id: str                       # 父任务 ID
    task_type: Literal[
        "perception",                         # 采集感知
        "hypothesis_building",                # 假说构建
        "skepticism",                         # 怀疑批判
        "red_team",                           # 红队裁判
        "archiving"                           # 记录归档
    ]

    # 任务内容
    description: str                          # 任务描述
    context_ref: str                          # 上下文版本引用
    input_data: dict[str, Any]                # 输入数据

    # 约束
    constraints: TaskConstraints              # 任务约束（超时、资源、输出格式）

    # 依赖
    depends_on: list[str]                     # 依赖的子任务 ID 列表
    priority: int                             # 优先级 (0 = 最高)

    # 元信息
    created_at: str                           # ISO 8601 时间戳
    assigned_worker: str | None               # 分配的 Worker ID（初值为 None）
```

### 7.3 ProposedRedTeamCase

```python
@dataclass
class ProposedRedTeamCase:
    """红队裁判 Agent 提出的对抗性测试用例结构体"""

    # 用例标识
    case_id: str                              # 用例唯一标识
    target_conclusion_id: str                 # 目标结论 ID（被测试的结论）

    # 攻击场景
    attack_type: Literal[
        "edge_case",                          # 边界条件
        "adversarial_input",                  # 对抗性输入
        "methodology_flaw",                   # 方法论缺陷
        "data_poisoning",                     # 数据投毒
        "assumption_break",                   # 假设破坏
        "extreme_condition"                   # 极端条件
    ]
    scenario_description: str                 # 场景描述

    # 测试参数
    modified_input: dict[str, Any]            # 修改后的输入
    expected_behavior: str                    # 期望的行为（结论应如何变化）
    failure_criterion: str                    # 失败判定标准

    # 结果
    actual_result: str | None                 # 实际结果（执行后填写）
    severity: Literal["critical", "high", "medium", "low"]  # 严重程度

    # 元信息
    created_by: str                           # 创建 Agent ID
    created_at: str                           # ISO 8601 时间戳
```

### 7.4 辅助结构体

```python
@dataclass
class MetaRuleRecord:
    """元规则触发记录"""
    rule_id: int                              # 规则编号 (1-4)
    rule_name: str                            # 规则名称
    triggered_at: str                         # 触发时间 ISO 8601
    trigger_reason: str                       # 触发原因
    action_taken: str                         # 执行的动作
    affected_agents: list[str]                # 受影响的 Agent ID 列表
    resolution: str                           # 处理结果


@dataclass
class EvidenceLink:
    """证据链节点"""
    source: str                               # 来源（Agent ID 或外部数据源）
    content: str                              # 证据内容
    timestamp: str                            # 采集时间
    reliability: float                        # 可靠性评分 [0.0, 1.0]


@dataclass
class TaskConstraints:
    """任务约束"""
    max_duration_sec: int = 300               # 最大执行时长
    max_tokens: int = 10000                   # 最大 Token 消耗
    required_output_format: str = "json"      # 输出格式要求
    retry_count: int = 2                      # 最大重试次数
    sandbox_level: str = "standard"           # 沙箱级别
```

---

## 附录 A：文件清单与模块对应关系

| 文件路径 | 对应角色/职责 | 状态 |
|----------|--------------|------|
| `agents/lead_researcher.py` | LeadResearcher 编排者 | 已实现 |
| `agents/worker_researcher.py` | → 待重构为 WorkerPerception | 待更新 |
| `agents/worker_coder.py` | → 待重构为 WorkerHypothesisBuilder | 待更新 |
| `agents/worker_reviewer.py` | → 待重构为 WorkerSkeptic | 待更新 |
| `agents/worker_retrospective.py` | → 待重构为 WorkerRedTeam | 待更新 |
| `agents/worker_archivist.py` | → 新增 WorkerArchivist | 待创建 |
| `harness/scheduler.py` | 调度引擎 | 已实现 |
| `harness/meta_rules.py` | 元协作规则引擎 | 待扩展（四条规则） |
| `harness/validator.py` | 安全校验 | 已实现 |
| `harness/snapshot.py` | 快照归档 | 已实现 |
| `brain_subsystem/constants.py` | B1-Final 冻结常量 | 已冻结 |
| `brain_subsystem/kernel.py` | B1-Final 冻结内核 | 已冻结 |
| `brain_subsystem/interface.py` | B1-Final 冻结接口 | 已冻结 |

## 附录 B：版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0-final | 2026-08-13 | 定版发布，全项目唯一权威架构文档 |