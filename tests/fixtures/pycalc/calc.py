"""跨平台 E2E 靶场：整数计算器核心。

与 tests/fixtures/demo（C 版）保持同样的能力与错误码语义，
但不依赖任何编译器或 Unix 工具链，任意平台 `python -m unittest` 即可验证。

零第三方依赖：只用标准库。
"""

from __future__ import annotations

CALC_OK = 0
CALC_ERR_DIV_ZERO = 1
CALC_ERR_INVALID = 2
CALC_ERR_OVERFLOW = 3

INT_MIN = -(2**31)
INT_MAX = 2**31 - 1


class CalcError(Exception):
    """带错误码的计算失败。"""

    def __init__(self, code: int) -> None:
        super().__init__(f"calc error {code}")
        self.code = code


def _check_overflow(value: int) -> int:
    if value < INT_MIN or value > INT_MAX:
        raise CalcError(CALC_ERR_OVERFLOW)
    return value


def calc_basic(a: int, b: int, op: str) -> int:
    """四则运算 + 取模，复用 C 版错误码语义。"""
    if op == "+":
        return _check_overflow(a + b)
    if op == "-":
        return _check_overflow(a - b)
    if op == "*":
        return _check_overflow(a * b)
    if op == "/":
        if b == 0:
            raise CalcError(CALC_ERR_DIV_ZERO)
        quotient = abs(a) // abs(b)
        return -quotient if (a < 0) != (b < 0) else quotient
    if op == "%":
        if b == 0:
            raise CalcError(CALC_ERR_DIV_ZERO)
        remainder = abs(a) % abs(b)
        return -remainder if a < 0 else remainder
    raise CalcError(CALC_ERR_INVALID)


def calc_power(base: int, exp: int) -> int:
    """整数幂。exp < 0 视为无效，过程中溢出按错误码返回。"""
    if exp < 0:
        raise CalcError(CALC_ERR_INVALID)
    result = 1
    for _ in range(exp):
        result = _check_overflow(result * base)
    return result


def calc_sqrt(x: int) -> int:
    """整数开方，向下取整。负数无效。"""
    if x < 0:
        raise CalcError(CALC_ERR_INVALID)
    if x < 2:
        return x
    lo, hi = 0, x
    while lo <= hi:
        mid = (lo + hi) // 2
        if mid * mid <= x:
            lo = mid + 1
        else:
            hi = mid - 1
    return hi


def calc_isqrt(x: int) -> int:
    """命名别名，与 C 版的兼容转发保持一致。"""
    return calc_sqrt(x)
