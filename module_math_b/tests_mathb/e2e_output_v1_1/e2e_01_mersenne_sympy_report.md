# E2E 验证 ①: 梅森数猜想 + SymPy 插件

## 任务配置
```json
{
  "plugins": {
    "sympy_bridge": {
      "enabled": true,
      "timeout_seconds": 10
    },
    "stagnation_analyzer": {
      "enabled": false
    },
    "lean_repl_bridge": {
      "enabled": false
    }
  }
}
```

## 执行结果
- **最终状态**: `PROVEN`
- **总轮次**: 1
- **错误信息**: 无

## 命题状态
| 命题ID | 陈述 | 状态 | 推导步数 | 缺口数 |
|--------|------|------|----------|--------|
| `prop_0` | 验证梅森素数猜想：若 n 为素数，则 2^n-1 为素数 | `INCONCLUSIVE` | 0 | 0 |
| `prop_1` | 请拆分为两个子命题：子命题A：若 2^n-1 为素数 ⇒ n 是素数（正向）子命题B：若 n 为素数 ⇒ 2^n-1 是 | `PROVEN` | 1 | 0 |

## 插件执行结果
| 插件 | 状态 | 耗时(ms) | 错误 |
|------|------|----------|------|
| `sympy_bridge` | enabled | 0.0 |  |

## 收敛判定
```json
{
  "type": "PROVEN",
  "rounds": 1,
  "stagnation_rounds": 0
}
```