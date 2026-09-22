# E2E 靶场：pycalc（跨平台主靶场）

用标准库实现的整数计算器，与 `../demo`（C 版）**能力与错误码语义一一对应**，
但不依赖编译器、make 或任何 Unix 工具链。

## 为什么需要它

`../demo` 是 C 工程，跑 E2E 的前提是目标机器装了 gcc + make。
在跨平台目标下这是最脆的一环（Windows 需 MinGW、macOS 需 Xcode CLT、Linux 需 build-essential），
本机现在就装不了。

所以分工是：

| 靶场 | 角色 | 依赖 |
|---|---|---|
| `pycalc`（本目录） | **主 E2E**：验证闭环必须能自己跑起来 | Python 标准库 |
| `demo` | 附加靶场：有 C 工具链时才有意义 | gcc + make |

主 E2E 能真跑测试，Agent 的"验证通过"才是真证据；否则只能降级声明 `unobserved`。

## 运行

```bash
python -m unittest discover -v
```

任意平台一致，零第三方依赖。

## 建议的 E2E 需求

现有能力已覆盖四则运算、取模、整数幂、整数开方（含错误码与溢出检查）。
建议用**尚未实现**且可断言的需求，例如：

- `calc_gcd(a, b)` / `calc_lcm(a, b)`
- 或 `calc_eval` 表达式求值

## 验收信号

`python -m unittest` 退出码 —— 0 即通过。这是 Agent「证据」的客观来源。
