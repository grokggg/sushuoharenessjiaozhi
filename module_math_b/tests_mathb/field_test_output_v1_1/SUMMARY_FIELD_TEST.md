# Module-MathB v1.1 应用实测报告

> **生成时间**: 2026-08-13 23:37:03 UTC
> **场景总数**: 8
> **通过**: 8/8

---

## 分支覆盖统计

| 分支 | 场景数 | 场景列表 |
|------|--------|----------|
| PROVEN | 3 | S1, S5, S8 |
| DISPROVEN | 3 | S2, S6, S7 |
| FORCED_TERMINATE | 2 | S3, S4 |
| ERROR | 0 |  |

## 场景详情

| ID | 场景 | 预期 | 实际 | 轮次 | 命题数 | 插件 | 哈希链 | 结果 |
|----|------|------|------|------|--------|------|--------|------|
| S1 | 欧几里得素数无穷性证明 | PROVEN | PROVEN | 1 | 1 | 无 | ✅ | ✅ |
| S2 | sympy_bridge | DISPROVEN | DISPROVEN | 1 | 1 | sympy_bridge | ✅ | ✅ |
| S3 | stagnation_analyzer | FORCED_TERMINATE | FORCED_TERMINATE | 4 | 1 | stagnation_analyzer | ✅ | ✅ |
| S4 | stagnation_analyzer | FORCED_TERMINATE | FORCED_TERMINATE | 4 | 1 | sympy_bridge, lean_r | ✅ | ✅ |
| S5 | sympy_bridge | PROVEN | PROVEN | 1 | 1 | sympy_bridge | ✅ | ✅ |
| S6 | 伪命题: 所有奇数都是素数（反例: 9, 15, 21） | DISPROVEN | DISPROVEN | 1 | 1 | 无 | ✅ | ✅ |
| S7 | stagnation_analyzer | DISPROVEN | DISPROVEN | 1 | 3 | sympy_bridge, stagna | ✅ | ✅ |
| S8 | lean_repl_bridge | PROVEN | PROVEN | 1 | 1 | lean_repl_bridge | ✅ | ✅ |

## 命题状态分布

| 场景 | 命题ID | 语句 | 状态 | 推导步 | 反例 | 缺口 |
|------|--------|------|------|--------|------|------|
| S1 | p1 | 存在无穷多个素数 | PROVEN | 3 | 0 | 0 |
| S2 | p2 | 若 n 为素数，则 2^n-1 为素数 | DISPROVEN | 2 | 1 | 1 |
| S3 | p3 | 存在无穷多对孪生素数 (p, p+2) | PENDING | 2 | 0 | 2 |
| S4 | p4 | 每个大于 2 的偶数可以表示为两个素数之和 | PENDING | 1 | 0 | 1 |
| S5 | p5 | 对于素数 p=7 和整数 a=2，有 2^6 ≡ 1 (mod 7) | PROVEN | 2 | 0 | 0 |
| S6 | p6 | 所有奇数都是素数 | DISPROVEN | 1 | 2 | 1 |
| S7 | p7a | √2 是无理数 | PROVEN | 2 | 0 | 0 |
| S7 | p7b | n² + n + 41 对所有自然数 n 都是素数 | DISPROVEN | 1 | 1 | 1 |
| S7 | p7c | 黎曼猜想: ζ(s) 的所有非平凡零点的实部都是 1/2 | PENDING | 1 | 0 | 1 |
| S8 | p8 | ζ(-2n) = 0 对所有正整数 n 成立（平凡零点） | PROVEN | 2 | 0 | 0 |

## 插件执行结果

| 场景 | 插件 | 状态 | 耗时(ms) | 错误 |
|------|------|------|----------|------|
| S2 | sympy_bridge | enabled | 0.0 |  |
| S3 | stagnation_analyzer | enabled | 0.0 |  |
| S4 | sympy_bridge | enabled | 0.0 |  |
| S4 | lean_repl_bridge | disabled | 0.0 |  |
| S4 | stagnation_analyzer | enabled | 0.0 |  |
| S5 | sympy_bridge | enabled | 0.0 |  |
| S7 | sympy_bridge | enabled | 0.0 |  |
| S7 | stagnation_analyzer | enabled | 0.0 |  |
| S8 | lean_repl_bridge | disabled | 0.0 |  |

## 哈希链完整性

| 场景 | 快照数 | 完整性 |
|------|--------|--------|
| S1 | 1 | ✅ |
| S2 | 1 | ✅ |
| S3 | 4 | ✅ |
| S4 | 4 | ✅ |
| S5 | 1 | ✅ |
| S6 | 1 | ✅ |
| S7 | 1 | ✅ |
| S8 | 1 | ✅ |

---

## S1: 欧几里得素数无穷性证明

- **预期分支**: PROVEN
- **实际分支**: PROVEN
- **总轮次**: 1
- **哈希链**: ✅ 完整
- **结果**: ✅ 通过

### 命题状态
- `p1`: **PROVEN** — 存在无穷多个素数


---

## S2: sympy_bridge

- **预期分支**: DISPROVEN
- **实际分支**: DISPROVEN
- **总轮次**: 1
- **哈希链**: ✅ 完整
- **结果**: ✅ 通过

### 命题状态
- `p2`: **DISPROVEN** — 若 n 为素数，则 2^n-1 为素数

### 插件执行
- `sympy_bridge`: enabled (0.0ms)

---

## S3: stagnation_analyzer

- **预期分支**: FORCED_TERMINATE
- **实际分支**: FORCED_TERMINATE
- **总轮次**: 4
- **哈希链**: ✅ 完整
- **结果**: ✅ 通过

### 命题状态
- `p3`: **PENDING** — 存在无穷多对孪生素数 (p, p+2)

### 插件执行
- `stagnation_analyzer`: enabled (0.0ms)

---

## S4: stagnation_analyzer

- **预期分支**: FORCED_TERMINATE
- **实际分支**: FORCED_TERMINATE
- **总轮次**: 4
- **哈希链**: ✅ 完整
- **结果**: ✅ 通过

### 命题状态
- `p4`: **PENDING** — 每个大于 2 的偶数可以表示为两个素数之和

### 插件执行
- `sympy_bridge`: enabled (0.0ms)
- `lean_repl_bridge`: disabled (0.0ms)
- `stagnation_analyzer`: enabled (0.0ms)

---

## S5: sympy_bridge

- **预期分支**: PROVEN
- **实际分支**: PROVEN
- **总轮次**: 1
- **哈希链**: ✅ 完整
- **结果**: ✅ 通过

### 命题状态
- `p5`: **PROVEN** — 对于素数 p=7 和整数 a=2，有 2^6 ≡ 1 (mod 7)

### 插件执行
- `sympy_bridge`: enabled (0.0ms)

---

## S6: 伪命题: 所有奇数都是素数（反例: 9, 15, 21）

- **预期分支**: DISPROVEN
- **实际分支**: DISPROVEN
- **总轮次**: 1
- **哈希链**: ✅ 完整
- **结果**: ✅ 通过

### 命题状态
- `p6`: **DISPROVEN** — 所有奇数都是素数


---

## S7: stagnation_analyzer

- **预期分支**: DISPROVEN
- **实际分支**: DISPROVEN
- **总轮次**: 1
- **哈希链**: ✅ 完整
- **结果**: ✅ 通过

### 命题状态
- `p7a`: **PROVEN** — √2 是无理数
- `p7b`: **DISPROVEN** — n² + n + 41 对所有自然数 n 都是素数
- `p7c`: **PENDING** — 黎曼猜想: ζ(s) 的所有非平凡零点的实部都是 1/2

### 插件执行
- `sympy_bridge`: enabled (0.0ms)
- `stagnation_analyzer`: enabled (0.0ms)

---

## S8: lean_repl_bridge

- **预期分支**: PROVEN
- **实际分支**: PROVEN
- **总轮次**: 1
- **哈希链**: ✅ 完整
- **结果**: ✅ 通过

### 命题状态
- `p8`: **PROVEN** — ζ(-2n) = 0 对所有正整数 n 成立（平凡零点）

### 插件执行
- `lean_repl_bridge`: disabled (0.0ms)
