# textkit 靶场

字符串处理任务集（评测扩量第二任务集，2026-10-19 追加）。验证机制与 pycalc
一致：agent 实现函数并补 `python -B -m unittest` 可发现的测试，独立跑测试
的输出取退出码作为验收证据。

任务：实现 `count_vowels` 与 `reverse_words`，并补充覆盖正常值与边界的用例
（空串、大小写、重复空白）。详见跑批驱动的 `--task` 参数。
