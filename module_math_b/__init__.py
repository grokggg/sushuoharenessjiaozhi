"""
module_math_b — Module-MathB v1.0 数学智能体集群扩展

Claude 级数学猜想证明、迭代探索、多层审查、反例挖掘、严谨推理集群。

架构铁律：
  1. 全域非侵入式扩展：禁止修改项目原有任何文件/类/函数/常量/Prompt/规则
  2. 双轨绝对隔离运行：非数学任务 0 加载/0 初始化/0 性能损耗
  3. 零共享资源：独立 DB、独立连接池、独立缓存、独立结构体、独立假说池、独立收敛器
  4. 内存硬锁死：模块常驻内存上限 = 整机 RAM 60%，超限三级降级
  5. 零未来信息、纯渐进式迭代：每轮仅依赖上一轮快照
  6. Prompt 绝对只读：数学能力仅通过「单次任务层模板注入」实现
  7. 架构三级严格隔离：核心层(brain_subsystem)永久冻结 | 调度层(harness)完全不动 | 扩展层(module_math_b)完全独立挂载

模块定位：
  复刻 Claude 数学多智能体集群工作范式
  专为：数论猜想、代数证明、形式推导、反例搜索、逻辑断层审查、多轮迭代证明探索

用法：
  from module_math_b.math_router import MathRouter
  router = MathRouter()
  if router.is_math_task(task):
      result = router.execute_math_workflow(task, orchestrator)
"""

__version__ = "1.0.0"
__author__ = "Module-MathB Team"
__all__ = [
    "MathRouter",
    "MathResourceLock",
    "MathProposition",
    "MathDerivationStep",
    "MathCounterExample",
    "MathProofSnapshot",
    "MathHypothesisPool",
    "MathConvergence",
    "MathValidator",
    "MathTemplateEngine",
    "MathSnapshotBridge",
    "MathDatabase",
]