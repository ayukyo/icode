"""pycalc 靶场的既有用例。

用标准库 unittest，任意平台 `python -m unittest discover` 即可运行，
不依赖 pytest、编译器或 Unix 工具链。
"""

from __future__ import annotations

import unittest

from calc import (
    CALC_ERR_DIV_ZERO,
    CALC_ERR_INVALID,
    CALC_ERR_OVERFLOW,
    CalcError,
    calc_basic,
    calc_isqrt,
    calc_power,
    calc_sqrt,
)


class TestCalcBasic(unittest.TestCase):
    def test_四则运算(self) -> None:
        self.assertEqual(calc_basic(10, 3, "+"), 13)
        self.assertEqual(calc_basic(10, 3, "-"), 7)
        self.assertEqual(calc_basic(10, 3, "*"), 30)
        self.assertEqual(calc_basic(10, 3, "/"), 3)

    def test_取模(self) -> None:
        self.assertEqual(calc_basic(10, 3, "%"), 1)
        with self.assertRaises(CalcError) as ctx:
            calc_basic(10, 0, "%")
        self.assertEqual(ctx.exception.code, CALC_ERR_DIV_ZERO)

    def test_除零(self) -> None:
        with self.assertRaises(CalcError) as ctx:
            calc_basic(1, 0, "/")
        self.assertEqual(ctx.exception.code, CALC_ERR_DIV_ZERO)

    def test_非法运算符(self) -> None:
        with self.assertRaises(CalcError) as ctx:
            calc_basic(1, 1, "^")
        self.assertEqual(ctx.exception.code, CALC_ERR_INVALID)

    def test_溢出(self) -> None:
        with self.assertRaises(CalcError) as ctx:
            calc_basic(2**31 - 1, 2, "*")
        self.assertEqual(ctx.exception.code, CALC_ERR_OVERFLOW)


class TestPower(unittest.TestCase):
    def test_正常幂(self) -> None:
        self.assertEqual(calc_power(2, 10), 1024)

    def test_零次幂(self) -> None:
        self.assertEqual(calc_power(5, 0), 1)

    def test_负指数无效(self) -> None:
        with self.assertRaises(CalcError) as ctx:
            calc_power(2, -1)
        self.assertEqual(ctx.exception.code, CALC_ERR_INVALID)

    def test_幂溢出(self) -> None:
        with self.assertRaises(CalcError) as ctx:
            calc_power(2, 64)
        self.assertEqual(ctx.exception.code, CALC_ERR_OVERFLOW)


class TestSqrt(unittest.TestCase):
    def test_向下取整(self) -> None:
        self.assertEqual(calc_sqrt(0), 0)
        self.assertEqual(calc_sqrt(1), 1)
        self.assertEqual(calc_sqrt(10), 3)
        self.assertEqual(calc_sqrt(16), 4)

    def test_负数无效(self) -> None:
        with self.assertRaises(CalcError) as ctx:
            calc_sqrt(-4)
        self.assertEqual(ctx.exception.code, CALC_ERR_INVALID)

    def test_别名等价(self) -> None:
        self.assertEqual(calc_isqrt(10), calc_sqrt(10))


if __name__ == "__main__":
    unittest.main()
