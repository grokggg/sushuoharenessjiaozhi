# Multi-Agent Brain Orchestrator — 约束文档

## 硬性约束 (Hard Constraints)

### HC-01: 架构约束
- 主架构必须为 Orchestrator-Worker 编排者-工作者多智能体集群
- LeadResearcher 是唯一编排者，不允许存在第二个编排者
- 所有 Worker 子智能体必须通过 LeadResearcher 接收任务

### HC-02: 管控底座约束
- Harness 作为整个集群的外层管控基础设施
- 所有调度、规则、校验、归档操作必须经由 Harness 层
- 子 Agent 禁止直接相互通信，必须通过 Harness 中转

### HC-03: 生物启发约束
- PV 中间神经元和胶质稳态理论仅作为生物启发来源
- 抽象得到的协作元机制全部实现在 harness 模块
- 禁止把生物细胞逻辑直接写进各个子 Agent 内部

### HC-04: B1-Final 冻结约束
- brain_subsystem 模块标记为永久冻结
- 禁止修改内部常量（constants.py）
- 禁止修改内核逻辑（kernel.py）
- 禁止修改接口签名（interface.py）
- 仅允许通过定义好的入参进行调用

## 软性约束 (Soft Constraints)

### SC-01: 代码风格
- 使用 Python 3.11+ 类型注解
- 遵循 PEP 8 规范
- 模块文档字符串使用 Google 风格

### SC-02: 测试覆盖
- 每个模块对应单元测试
- 集成测试覆盖编排全流程
- Demo 测试验证闭环