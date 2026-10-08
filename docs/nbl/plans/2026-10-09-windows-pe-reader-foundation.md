# Windows PE Reader Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** root 在既有自治授权范围确认选择 A、且计划双审通过后，为 CI 新增仅结构读取、严格有界的 PE32+ 头部与完整 RVA 映射基础层，并将 portable 合同选择一次。

**Architecture:** 独立标准库 reader 持有原 immutable bytes 引用，冻结元数据，仅在完整区间属于一个唯一 file-backed 区域时返回 offset/原始 bytes。保留旧 machine API 与所有消费者，目录只保存声明元信息，不解析目录内容、不接入 capture/生产执行或工作流。

**Tech Stack:** Python 3.11+ 标准库 dataclasses、struct、unittest；实际合成 PE bytes；现有 workspace DEFAULT 与三道 preflight。

---

## 状态、约束与输入冻结

2026-10-09；源码基线 main `118a2621cef92a5fcda510db295ea8c7658e5d4f`。设计 [候选 A](../specs/2026-10-09-windows-pe-reader-foundation-design.md) SHA256 `2a607fd181401ec61303badba8a90401d7ee2e2b8b02ee88b514aff91f7bc8d1`，设计重新 SPEC C0/I0/M0、不同 QUALITY C0/I0/M1。M1 是多重错误优先级，以下完整冻结顺序与三个双错误精确向量将其消解；实施前计划仍须 fresh SPEC → 不同 QUALITY。

A/B 已向用户异步呈现，尚无用户答复，本计划不是用户已选 A 的证明。用户此前明确“高价值都应该吸收进来，你决定阶段”“R2完整跑完后，直接下一阶段，不用等我命令”“不断运行，直到R2/R3整体验收”；A 在既有 CI 范围内无新依赖/权限/生产准入，root 可在设计/计划门全部通过后依据该自治授权选择推荐 A，并明确是 root 的取舍，不捏造新用户答案。计划起草时仅写计划、静态自审，尚无实施，测试/原生/模型运行数为0、未提交推送；当时规划作者STOP、不自动实施、不新建worktree/branch。此为历史起草状态，当前实际实施与审验见各Task及后续履历。

三问已确认：真实缺口是没有严格完整区间读取层；已有轻量 `windows_pe_architecture` 仅验 MZ/PE/machine，不能升级语义；调用链由隔离新增 CI reader 保护。研究采用/暂缓/不适配及固定 Codex/pefile/Microsoft 来源见 [研究输入](../specs/2026-10-09-windows-pe-static-parse-research.md)。不复制上游源码，不新增依赖/特权/网络许可。原 `parse_complete`、`runtime_load_verified`、`source_launch_verified` 三个 false 保持；通过本片不授完整目录、可加载 PE、实际成品、native 隔离、模型 1→6 或 R2/R3 整体信用。

源码改动精确限定四路径：

| 路径 | 操作与责任 |
| --- | --- |
| `scripts/windows_pe_reader.py` | 新建：纯 bytes 结构检查与完整 RVA 映射，没有 CLI/I/O/日志/原生 API |
| `tests/test_windows_pe_reader.py` | 新建：实际合成 bytes、精确错误与不可变/有界/兼容正负控 |
| `scripts/run_workspace_ci.py` | 仅 DEFAULT 增加新 portable 模块一次，旧选择与 runner 行为不变 |
| `tests/test_run_workspace_ci.py` | 仅新增配对选择方法，验证所有新方法一次且没有 skip |

`src/**`、native helper/capture、`.github/**`、vendor、包依赖、权限、三个 false 均无源码修改。root 文档记录属于交付证据，不扩大源码清单。

## 构造与错误顺序（M1 的冻结合同）

按照以下编号顺序检查，先命中的拒绝决定 reason，不尝试拼接多个错误；section 数值边界必须全部检查完再做任何 overlap 比较，结果不依赖 section 输入顺序。

1. image 精确 bytes；expected_arch 精确 str 且为 x64/arm64，否则 invalid_input。
2. image 空/大于 8MiB → image_limit；DOS 长度不足 64 → truncated_headers；MZ 错误 → invalid_signature。
3. e_lfanew <64 → invalid_header_range；PE signature+完整 COFF 不在 image 内 → truncated_headers；PE signature 错误 → invalid_signature。
4. machine 不支持/与 expected_arch 不等 → architecture_mismatch；section 数不在 1..96 → unsupported_section_count。
5. 声明可选头不足 112 或声明完整长度超出 image → truncated_headers；PE32+ magic 错 → invalid_signature。
6. 读取 NumberOfRvaAndSizes 后**先**检查 >16 → unsupported_directory_count；再检查 `112+8*count` 在声明可选头内 → truncated_headers。
7. 全 section 表在 image 内，否则 truncated_headers；SizeOfImage=0，或 SizeOfHeaders=0/未覆盖表/超过 file 或 image → invalid_header_range。
8. 每一 section 的完整非空 raw/virtual span 数值越界 → invalid_section_range；只收集合法 span，不提前比较重叠。
9. 全部合法 span 按各自坐标排序：headers/raw 或 headers/virtual/section 之间 overlap → overlapping_sections；邻接合法。
10. 完成不可变元数据赋值；目录原始对不作 backing/内容判断，index4 仍是 file offset；无 partial 成功。

三个具名双错误：`test_bad_arch_precedes_empty_budget`（bad expected_arch + empty → invalid_input）；`test_directory_limit_precedes_array_truncation`（count17 + optional112 → unsupported_directory_count）；`test_section_ranges_precede_overlap_independent_of_order`（raw 越界 + 其它合法 sections overlap，两种顺序均 invalid_section_range）。读取先参数/整体区间 invalid_rva_range，再唯一 backing rva_not_file_backed。

### Task 1: 实际 bytes 正负控与独立 reader

**状态**

- [x] 任务完成（仅 Task1；独立规格与质量门通过）

**Dependencies:** None
**Parallelizable:** No (选择与计划双审是实施前置；每任务新作者串行 TDD，不并发写四路径)

- [x] **Step 1: root 确认候选选择与计划双审已通过，作者全文读冻结设计、研究和四路径当前文件；核设计 SHA 与基线。** 不拿候选默认项冒充用户已答复。若设计/基线变化，记录实际差异并重新评审，不沿旧 SHA 授信用。

- [x] **Step 2: apply_patch 新建 `tests/test_windows_pe_reader.py`，内容如下。** 这是实际冻结全文；没有导入不存在的 reader 造成 ERROR，setUp 的存在断言提供明确 assertion RED。所有边界来自实际 bytes，不 mock parser/mapping。

```python
"""Actual-byte contracts for the CI-only PE header and RVA foundation."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
import hashlib
import importlib
import importlib.util
import io
import struct
import unittest


LIMIT = 8 * 1024 * 1024
DEFAULT = object()


def pe_bytes(*, arch="x64", sections=None, directories=(), pe_offset=0x80,
             size_of_image=0x4000, size_of_headers=None, file_size=None):
    """Build real DOS/COFF/PE32+ headers and a complete section table."""
    count = 1 if sections is None else len(sections)
    optional_size = 112 + 8 * len(directories)
    optional = pe_offset + 24
    table = optional + optional_size
    headers = ((table + 40 * count + 0xFF) // 0x100) * 0x100
    if size_of_headers is not None:
        headers = size_of_headers
    if sections is None:
        sections = ((0x1000, 0x100, 0x100, headers),)
    required = max(table + 40 * count, headers,
                   *(start + raw for _, _, raw, start in sections if raw))
    body = bytearray(required if file_size is None else file_size)
    body[:2] = b"MZ"
    struct.pack_into("<I", body, 0x3C, pe_offset)
    body[pe_offset:pe_offset + 4] = b"PE\0\0"
    struct.pack_into("<HH", body, pe_offset + 4,
                     {"x64": 0x8664, "arm64": 0xAA64}[arch], count)
    struct.pack_into("<H", body, pe_offset + 20, optional_size)
    struct.pack_into("<H", body, optional, 0x20B)
    struct.pack_into("<II", body, optional + 56, size_of_image, headers)
    struct.pack_into("<I", body, optional + 108, len(directories))
    for index, pair in enumerate(directories):
        struct.pack_into("<II", body, optional + 112 + index * 8, *pair)
    for index, (va, virtual, raw, start) in enumerate(sections):
        struct.pack_into("<IIII", body, table + index * 40 + 8,
                         virtual, va, raw, start)
    return bytes(body)


def changed(image, offset, fmt, *values):
    body = bytearray(image)
    struct.pack_into(fmt, body, offset, *values)
    return bytes(body)


class TestWindowsPeReader(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.find_spec("scripts.windows_pe_reader")
        self.assertIsNotNone(spec, "CI-only PE reader interface is missing")
        module = importlib.import_module("scripts.windows_pe_reader")
        self.PeImage = getattr(module, "PeImage", None)
        self.PeFormatError = getattr(module, "PeFormatError", None)
        self.assertTrue(callable(self.PeImage), "PeImage interface is missing")
        self.assertTrue(isinstance(self.PeFormatError, type))
        self.assertTrue(issubclass(self.PeFormatError, ValueError))

    def reject(self, reason, image=DEFAULT, *, arch="x64"):
        if image is DEFAULT:
            image = pe_bytes()
        with self.assertRaises(self.PeFormatError) as caught:
            self.PeImage(image, expected_arch=arch)
        self.assertIs(type(caught.exception), self.PeFormatError)
        self.assertEqual(caught.exception.reason, reason)
        self.assertEqual(str(caught.exception), reason)

    def read_reject(self, reader, reason, rva, size):
        for method in (reader.rva_to_offset, reader.read_rva):
            with self.subTest(method=method.__name__, rva=rva, size=size):
                with self.assertRaises(self.PeFormatError) as caught:
                    method(rva, size)
                self.assertIs(type(caught.exception), self.PeFormatError)
                self.assertEqual(caught.exception.reason, reason)
                self.assertEqual(str(caught.exception), reason)

    def test_minimal_both_architectures_and_empty_directories(self):
        for arch in ("x64", "arm64"):
            with self.subTest(arch=arch):
                image = pe_bytes(arch=arch)
                reader = self.PeImage(image, expected_arch=arch)
                self.assertEqual(reader.architecture, arch)
                self.assertEqual(reader.data_directories, ())
                self.assertIs(reader._image, image)

    def test_bad_arch_precedes_empty_budget(self):
        self.reject("invalid_input", b"", arch="amd64")

    def test_directory_limit_precedes_array_truncation(self):
        self.reject("unsupported_directory_count", changed(pe_bytes(), 0x98 + 108, "<I", 17))

    def test_exact_input_types_and_arch_values(self):
        class BytesSubclass(bytes):
            pass

        class StrSubclass(str):
            pass

        image = pe_bytes()
        for value in (None, True, object(), bytearray(image), memoryview(image),
                      BytesSubclass(image), "MZ", 7):
            with self.subTest(image_type=type(value)):
                self.reject("invalid_input", value)
        for value in (True, 7, None, "X64", "amd64", "", StrSubclass("x64")):
            with self.subTest(arch=value):
                self.reject("invalid_input", arch=value)

    def test_empty_and_image_budget_exact_boundary(self):
        self.reject("image_limit", b"")
        image = pe_bytes(file_size=LIMIT)
        self.assertIs(self.PeImage(image, expected_arch="x64")._image, image)
        self.reject("image_limit", image + b"\0")

    def test_dos_signature_and_truncation(self):
        self.reject("truncated_headers", b"MZ" + bytes(61))
        self.reject("invalid_signature", changed(pe_bytes(), 0, "<H", 0))

    def test_pe_offset_bounds_and_complete_coff(self):
        self.assertEqual(self.PeImage(pe_bytes(pe_offset=64), expected_arch="x64").architecture, "x64")
        image = pe_bytes()
        self.reject("invalid_header_range", changed(image, 0x3C, "<I", 63))
        for offset in (len(image), len(image) - 23, 0xFFFFFFFF):
            with self.subTest(offset=offset):
                self.reject("truncated_headers", changed(image, 0x3C, "<I", offset))

    def test_pe_signature(self):
        self.reject("invalid_signature", changed(pe_bytes(), 0x80, "<I", 0))

    def test_machine_unsupported_and_expected_mismatch(self):
        self.reject("architecture_mismatch", changed(pe_bytes(), 0x84, "<H", 0x14C))
        self.reject("architecture_mismatch", pe_bytes(arch="arm64"))
        self.reject("architecture_mismatch", arch="arm64")

    def test_section_count_policy(self):
        for count in (0, 97):
            with self.subTest(count=count):
                self.reject("unsupported_section_count", changed(pe_bytes(), 0x86, "<H", count))

    def test_optional_header_length_and_magic(self):
        for length in (111, 0xFFFF):
            with self.subTest(length=length):
                self.reject("truncated_headers", changed(pe_bytes(), 0x94, "<H", length))
        self.reject("invalid_signature", changed(pe_bytes(), 0x98, "<H", 0x10B))

    def test_directory_array_must_fit_declared_optional_header(self):
        self.reject("truncated_headers", changed(pe_bytes(), 0x98 + 108, "<I", 1))

    def test_all_declared_directory_pairs_preserved_only_as_metadata(self):
        pairs = ((0, 0), (0xFFFFFFFF, 9), (0, 8), (9, 0)) + tuple((0x9000 + n, n) for n in range(12))
        reader = self.PeImage(pe_bytes(directories=pairs), expected_arch="x64")
        self.assertIs(type(reader.data_directories), tuple)
        self.assertEqual(reader.data_directories, pairs)
        one = self.PeImage(pe_bytes(directories=((0x9000, 0),)), expected_arch="x64")
        self.assertEqual(one.data_directories, ((0x9000, 0),))
        self.assertFalse(hasattr(reader, "parse_complete"))

    def test_certificate_directory_file_offset_is_not_validated_as_rva(self):
        pairs = ((0, 0),) * 4 + ((0x800, 16),)
        image = pe_bytes(directories=pairs, file_size=0x810)
        reader = self.PeImage(image, expected_arch="x64")
        self.assertEqual(reader.data_directories[4], (0x800, 16))
        self.read_reject(reader, "rva_not_file_backed", 0x800, 16)

    def test_section_table_truncation(self):
        table_end = 0x98 + 112 + 40
        self.reject("truncated_headers", pe_bytes()[:table_end - 1])

    def test_header_ranges_and_zero_image_size(self):
        image = pe_bytes()
        table_end = 0x98 + 112 + 40
        for headers in (0, table_end - 1, len(image) + 1, 0x4001):
            with self.subTest(headers=headers):
                self.reject("invalid_header_range", changed(image, 0x98 + 60, "<I", headers))
        for size in (0, 0x1FF):
            with self.subTest(size=size):
                self.reject("invalid_header_range", changed(image, 0x98 + 56, "<I", size))
        # Isolate the SizeOfImage bound from the file-size bound.
        self.reject("invalid_header_range", pe_bytes(file_size=0x5000, size_of_headers=0x4001))

    def test_header_and_section_reads_at_exact_ends(self):
        image = pe_bytes(size_of_image=0x1100)
        reader = self.PeImage(image, expected_arch="x64")
        for rva, size, offset in ((0, 0x200, 0), (0x1000, 0x100, 0x200),
                                  (0x1FF, 1, 0x1FF), (0x10FF, 1, 0x2FF)):
            with self.subTest(rva=rva, size=size):
                self.assertEqual(reader.rva_to_offset(rva, size), offset)
                self.assertEqual(reader.read_rva(rva, size), image[offset:offset + size])

    def test_unordered_adjacent_sections_and_independent_reads(self):
        sections = ((0x1100, 0x100, 0x100, 0x300), (0x1000, 0x100, 0x100, 0x200))
        body = bytearray(pe_bytes(sections=sections))
        body[0x300:0x400] = b"B" * 0x100
        body[0x200:0x300] = b"A" * 0x100
        reader = self.PeImage(bytes(body), expected_arch="x64")
        for rva, offset, marker in ((0x1100, 0x300, b"B"), (0x1000, 0x200, b"A")):
            with self.subTest(rva=rva):
                self.assertEqual(reader.rva_to_offset(rva, 0x100), offset)
                self.assertEqual(reader.read_rva(rva, 0x100), marker * 0x100)
        self.read_reject(reader, "rva_not_file_backed", 0x10FF, 2)

    def test_section_count_96_and_search_bound(self):
        sections = tuple((0x1000 + n * 0x100, 0x100, 0x100, 0x2000 + n * 0x100) for n in range(96))
        # A 96-entry table fits below RVA 0x1000 only with the legal DOS-end PE
        # offset here; the default 0x80 would round headers up to 0x1100.
        image = pe_bytes(sections=sections, size_of_image=0x7000, pe_offset=64)
        reader = self.PeImage(image, expected_arch="x64")
        self.assertEqual(len(reader._sections), 96)
        self.assertLessEqual(len(reader._regions), 97)
        self.assertEqual(reader.rva_to_offset(0x6FFF, 1), 0x7FFF)
        self.assertEqual(reader.read_rva(0x6FFF, 1), image[0x7FFF:0x8000])

    def test_zero_virtual_size_uses_raw_extent(self):
        image = pe_bytes(sections=((0x1000, 0, 0x100, 0x200),))
        reader = self.PeImage(image, expected_arch="x64")
        self.assertEqual(reader.read_rva(0x1000, 0x100), image[0x200:0x300])
        self.read_reject(reader, "rva_not_file_backed", 0x1100, 1)

    def test_zero_raw_size_ignores_pointer_and_never_zero_fills(self):
        reader = self.PeImage(pe_bytes(sections=((0x1000, 0x100, 0, 0xFFFFFFFF),)), expected_arch="x64")
        self.read_reject(reader, "rva_not_file_backed", 0x1000, 1)

    def test_both_section_sizes_zero_provide_no_mapping(self):
        sections = ((0xFFFFFFFF, 0, 0, 0xFFFFFFFF),)
        reader = self.PeImage(pe_bytes(sections=sections), expected_arch="x64")
        self.assertEqual(reader._sections, sections)
        self.assertEqual(reader._regions, ((0, 0x200, 0),))
        self.read_reject(reader, "invalid_rva_range", 0xFFFFFFFF, 1)

    def test_zero_fill_and_raw_padding_not_file_backed(self):
        for virtual, backed in ((0x200, 0x100), (0x80, 0x80)):
            with self.subTest(virtual=virtual):
                image = pe_bytes(sections=((0x1000, virtual, 0x100, 0x200),))
                reader = self.PeImage(image, expected_arch="x64")
                self.assertEqual(reader.read_rva(0x1000, backed), image[0x200:0x200 + backed])
                self.read_reject(reader, "rva_not_file_backed", 0x1000 + backed, 1)

    def test_raw_and_virtual_section_ranges(self):
        image = pe_bytes()
        section = 0x98 + 112 + 8
        for offset, value in ((12, len(image)), (12, 0xFFFFFFFF), (8, 0xFFFFFFFF),
                              (4, 0x4000), (4, 0xFFFFFFF0), (0, 0xFFFFFFFF)):
            with self.subTest(offset=offset, value=value):
                self.reject("invalid_section_range", changed(image, section + offset, "<I", value))

    def test_header_raw_and_virtual_overlaps(self):
        for sections in (((0x1000, 0x100, 0x100, 0x100),),
                         ((0x100, 0x100, 0x100, 0x200),)):
            with self.subTest(sections=sections):
                self.reject("overlapping_sections", pe_bytes(sections=sections))

    def test_full_raw_padding_and_virtual_zero_fill_overlap(self):
        for sections in (((0x1000, 0x80, 0x200, 0x200), (0x2000, 0x100, 0x100, 0x300)),
                         ((0x1000, 0x200, 0x80, 0x200), (0x1100, 0x100, 0x100, 0x300))):
            with self.subTest(sections=sections):
                self.reject("overlapping_sections", pe_bytes(sections=sections))

    def test_section_ranges_precede_overlap_independent_of_order(self):
        overlap = ((0x1000, 0x100, 0x100, 0x200), (0x1080, 0x100, 0x100, 0x300))
        invalid = (0x2000, 0x100, 0x100, 0x400)
        # The fixture has complete headers/table; only the chosen raw pointer is invalid.
        for sections, index in ((overlap + (invalid,), 2), ((invalid,) + overlap, 0)):
            with self.subTest(index=index):
                image = pe_bytes(sections=sections)
                table = 0x98 + 112
                image = changed(image, table + index * 40 + 20, "<I", len(image))
                self.reject("invalid_section_range", image)

    def test_read_argument_types_sign_and_budget(self):
        class IntSubclass(int):
            pass

        reader = self.PeImage(pe_bytes(), expected_arch="x64")
        for rva, size in ((True, 1), (0, True), (IntSubclass(0), 1), (0, IntSubclass(1)),
                          (0.0, 1), (0, 1.0), (-1, 1), (0, 0), (0, -1),
                          (0x100000000, 1), (0xFFFFFFFF, 2), (0, LIMIT + 1), (0x4000, 1)):
            with self.subTest(rva=rva, size=size):
                self.read_reject(reader, "invalid_rva_range", rva, size)

    def test_exact_read_budget_supported_when_single_header_region(self):
        image = pe_bytes(sections=((0, 0, 0, 0),), size_of_headers=LIMIT,
                         size_of_image=LIMIT, file_size=LIMIT)
        reader = self.PeImage(image, expected_arch="x64")
        self.assertEqual(reader.rva_to_offset(0, LIMIT), 0)
        self.assertEqual(reader.read_rva(0, LIMIT), image)

    def test_gap_overlay_and_header_crossing_are_not_fallbacks(self):
        reader = self.PeImage(pe_bytes(file_size=0x2000), expected_arch="x64")
        for rva, size in ((0x300, 1), (0x1800, 1), (0x1FF, 2), (0x10FF, 2)):
            with self.subTest(rva=rva):
                self.read_reject(reader, "rva_not_file_backed", rva, size)
        adjacent = self.PeImage(pe_bytes(sections=((0x200, 0x100, 0x100, 0x200),)), expected_arch="x64")
        self.assertEqual(adjacent.rva_to_offset(0x1FF, 1), 0x1FF)
        self.assertEqual(adjacent.rva_to_offset(0x200, 1), 0x200)
        self.assertEqual(len(adjacent.read_rva(0x1FF, 1)), 1)
        self.assertEqual(len(adjacent.read_rva(0x200, 1)), 1)
        self.read_reject(adjacent, "rva_not_file_backed", 0x1FF, 2)

    def test_read_methods_have_identical_rejections(self):
        reader = self.PeImage(pe_bytes(), expected_arch="x64")
        self.read_reject(reader, "invalid_rva_range", -1, 1)
        self.read_reject(reader, "rva_not_file_backed", 0x300, 1)

    def test_immutable_metadata_original_bytes_and_quiet_repr(self):
        marker = b"PRIVATE_PE_BODY_MARKER"
        body = bytearray(pe_bytes(directories=((0x9000, 0),)))
        body[0x200:0x200 + len(marker)] = marker
        image = bytes(body)
        digest = hashlib.sha256(image).digest()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            reader = self.PeImage(image, expected_arch="x64")
            self.assertEqual(reader.read_rva(0x1000, len(marker)), marker)
            representation = repr(reader)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn(marker.decode(), representation)
        self.assertIs(reader._image, image)
        self.assertEqual(hashlib.sha256(image).digest(), digest)
        for value in (reader._sections, reader._regions, reader.data_directories):
            self.assertIs(type(value), tuple)
            self.assertTrue(all(type(item) is tuple for item in value))
        for name in ("_image", "architecture", "data_directories", "_size_of_image", "_regions", "_sections"):
            with self.subTest(field=name):
                with self.assertRaises(FrozenInstanceError):
                    setattr(reader, name, None)
        for name in ("parse_complete", "runtime_load_verified", "source_launch_verified"):
            self.assertFalse(hasattr(reader, name))

    def test_old_minimal_machine_contract_remains_distinct(self):
        from icode.native_helper import windows_pe_architecture

        body = bytearray(70)
        body[:2] = b"MZ"
        struct.pack_into("<I", body, 0x3C, 64)
        body[64:68] = b"PE\0\0"
        struct.pack_into("<H", body, 68, 0x8664)
        image = bytes(body)
        self.assertEqual(windows_pe_architecture(image), "x64")
        self.reject("truncated_headers", image)
        self.assertEqual(windows_pe_architecture(image), "x64")
```

- [x] **Step 3: 先运行三项明确 RED，然后全新模块 RED。**

```bash
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest tests.test_windows_pe_reader.TestWindowsPeReader.test_minimal_both_architectures_and_empty_directories tests.test_windows_pe_reader.TestWindowsPeReader.test_bad_arch_precedes_empty_budget tests.test_windows_pe_reader.TestWindowsPeReader.test_directory_limit_precedes_array_truncation
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest tests.test_windows_pe_reader
```

Expected：reader 不存在时 setUp 明确 assertion FAIL，ERROR/skip 为 0；保留原摘要与解释器，不能将导入错误当 RED。若源码已有实现，先确认本计划基线是否漂移；不得删除文件或人为破坏已有代码制造 RED。

- [x] **Step 4: apply_patch 新建 `scripts/windows_pe_reader.py` 全文如下。** 先所有 section 数值，再 overlap；原 bytes 不复制，regions 有界且不可变；精确类约束是本 API 的接受子集，不是通用 PE 规范。

```python
"""CI-only bounded PE32+ headers and complete file-backed RVA reads.

Construction validates this narrow structural subset only. Directory pairs are
metadata; success does not certify directory contents or a loadable executable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import struct


_IMAGE_LIMIT = 8 * 1024 * 1024
_RVA_LIMIT = 1 << 32
_DOS_SIZE = 64
_COFF_SIZE = 20
_OPTIONAL_BASE_SIZE = 112
_SECTION_SIZE = 40
_SECTION_LIMIT = 96
_DIRECTORY_LIMIT = 16
_MACHINES = {0x8664: "x64", 0xAA64: "arm64"}
_REASONS = frozenset({
    "invalid_input", "image_limit", "truncated_headers", "invalid_signature",
    "architecture_mismatch", "unsupported_section_count",
    "unsupported_directory_count", "invalid_header_range",
    "invalid_section_range", "overlapping_sections", "invalid_rva_range",
    "rva_not_file_backed",
})


class PeFormatError(ValueError):
    """A closed, payload-free rejection reason."""

    def __init__(self, reason: str):
        if type(reason) is not str or reason not in _REASONS:
            raise ValueError("invalid_input")
        self.reason = reason
        super().__init__(reason)


def _require_range(image: bytes, start: int, size: int) -> None:
    if start < 0 or size < 0 or start + size > len(image):
        raise PeFormatError("truncated_headers")


def _unpack(image: bytes, start: int, fmt: str) -> tuple[int, ...]:
    # Every struct read has an explicit file-range check, even after a containing
    # header has already been checked. Defined truncations never leak struct.error.
    _require_range(image, start, struct.calcsize(fmt))
    return struct.unpack_from(fmt, image, start)


def _reject_overlaps(spans: list[tuple[int, int]]) -> None:
    previous_end = 0
    for start, end in sorted(spans):
        if start < previous_end:
            raise PeFormatError("overlapping_sections")
        previous_end = end


@dataclass(frozen=True, slots=True, init=False)
class PeImage:
    """Immutable original bytes plus bounded structural metadata."""

    _image: bytes = field(repr=False)
    architecture: str
    data_directories: tuple[tuple[int, int], ...]
    _size_of_image: int
    _sections: tuple[tuple[int, int, int, int], ...]
    _regions: tuple[tuple[int, int, int], ...]

    def __init__(self, image: bytes, *, expected_arch: str):
        if (type(image) is not bytes or type(expected_arch) is not str
                or expected_arch not in ("x64", "arm64")):
            raise PeFormatError("invalid_input")
        if not image or len(image) > _IMAGE_LIMIT:
            raise PeFormatError("image_limit")
        _require_range(image, 0, _DOS_SIZE)
        if image[:2] != b"MZ":
            raise PeFormatError("invalid_signature")
        pe_offset, = _unpack(image, 0x3C, "<I")
        if pe_offset < _DOS_SIZE:
            raise PeFormatError("invalid_header_range")
        _require_range(image, pe_offset, 4 + _COFF_SIZE)
        if image[pe_offset:pe_offset + 4] != b"PE\0\0":
            raise PeFormatError("invalid_signature")
        coff = pe_offset + 4
        machine, section_count = _unpack(image, coff, "<HH")
        architecture = _MACHINES.get(machine)
        if architecture != expected_arch:
            raise PeFormatError("architecture_mismatch")
        if not 1 <= section_count <= _SECTION_LIMIT:
            raise PeFormatError("unsupported_section_count")
        optional_size, = _unpack(image, coff + 16, "<H")
        optional = coff + _COFF_SIZE
        if optional_size < _OPTIONAL_BASE_SIZE:
            raise PeFormatError("truncated_headers")
        _require_range(image, optional, optional_size)
        magic, = _unpack(image, optional, "<H")
        if magic != 0x20B:
            raise PeFormatError("invalid_signature")
        directory_count, = _unpack(image, optional + 108, "<I")
        if directory_count > _DIRECTORY_LIMIT:
            raise PeFormatError("unsupported_directory_count")
        if _OPTIONAL_BASE_SIZE + 8 * directory_count > optional_size:
            raise PeFormatError("truncated_headers")
        table = optional + optional_size
        table_end = table + _SECTION_SIZE * section_count
        _require_range(image, table, _SECTION_SIZE * section_count)
        size_of_image, size_of_headers = _unpack(image, optional + 56, "<II")
        if (not size_of_image or not size_of_headers or size_of_headers < table_end
                or size_of_headers > len(image) or size_of_headers > size_of_image):
            raise PeFormatError("invalid_header_range")

        sections = []
        raw_spans = [(0, size_of_headers)]
        virtual_spans = [(0, size_of_headers)]
        regions = [(0, size_of_headers, 0)]
        for index in range(section_count):
            virtual_size, va, raw_size, raw_start = _unpack(
                image, table + index * _SECTION_SIZE + 8, "<IIII")
            extent = virtual_size if virtual_size else raw_size
            if raw_size and raw_start + raw_size > len(image):
                raise PeFormatError("invalid_section_range")
            if extent and (va + extent > size_of_image or va + extent > _RVA_LIMIT):
                raise PeFormatError("invalid_section_range")
            sections.append((va, virtual_size, raw_size, raw_start))
            if raw_size:
                raw_spans.append((raw_start, raw_start + raw_size))
            if extent:
                virtual_spans.append((va, va + extent))
            backed = min(raw_size, extent)
            if backed:
                regions.append((va, va + backed, raw_start))

        # Check all numeric ranges first, independent of table order. Compare
        # complete spans, including unmapped padding and virtual zero-fill tails.
        _reject_overlaps(raw_spans)
        _reject_overlaps(virtual_spans)
        directories = tuple(_unpack(image, optional + _OPTIONAL_BASE_SIZE + 8 * index, "<II")
                            for index in range(directory_count))
        # Publish no partially validated metadata. In particular, index 4 remains
        # raw file-offset metadata and is never prevalidated as an RVA.
        object.__setattr__(self, "_image", image)
        object.__setattr__(self, "architecture", architecture)
        object.__setattr__(self, "data_directories", directories)
        object.__setattr__(self, "_size_of_image", size_of_image)
        object.__setattr__(self, "_sections", tuple(sections))
        object.__setattr__(self, "_regions", tuple(regions))

    def rva_to_offset(self, rva: int, size: int) -> int:
        """Map one complete request inside one uniquely file-backed region."""
        if (type(rva) is not int or type(size) is not int
                or not 0 <= rva < _RVA_LIMIT or not 1 <= size <= _IMAGE_LIMIT
                or rva + size > _RVA_LIMIT or rva + size > self._size_of_image):
            raise PeFormatError("invalid_rva_range")
        for start, end, file_start in self._regions:
            if start <= rva and rva + size <= end:
                return file_start + rva - start
        raise PeFormatError("rva_not_file_backed")

    def read_rva(self, rva: int, size: int) -> bytes:
        """Return exact original bytes, without concatenation or zero filling."""
        offset = self.rva_to_offset(rva, size)
        return self._image[offset:offset + size]
```

- [x] **Step 5: 运行完整新模块 GREEN，记录实际方法数/0F/E/0skip，然后作者自审与 SHA 冻结。**

```bash
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest tests.test_windows_pe_reader
sha256sum scripts/windows_pe_reader.py tests/test_windows_pe_reader.py
```

Expected：33 方法全部 PASS，0F/E/skip；以实际 discovery 为准，不把 subTest 数算方法数。检查全部三个 M1 精确向量，12 reasons、实际 bytes、无截短/补零/overlay/跨区拼接、没有 catch KI/SystemExit/MemoryError。修改任何例子时同步本计划并记录实际 RED/GREEN，不要求作者为追求数字修改预算或放宽合同。此步骤不提交、不跑全量、不启动原生/model。

### Task 2: DEFAULT 精确一次与配对守卫

**状态**

- [x] 任务完成（全局独立两审覆盖此任务）

**Dependencies:** Task 1
**Parallelizable:** No (配对方法必须消费已实现 reader；新任务作者有序小改)

- [x] **Step 1: apply_patch 在 `tests/test_run_workspace_ci.py` 的 `TestWorkspaceCiCoverage` 类开头插入以下完整方法，保留现有全文。**

```python
    def test_pe_reader_portable_contract_is_selected_once_without_skips(self):
        module_name = "tests.test_windows_pe_reader"
        self.assertEqual(DEFAULT_MODULES.count(module_name), 1)
        module = importlib.import_module(module_name)
        test_class = getattr(module, "TestWindowsPeReader", None)
        self.assertTrue(isinstance(test_class, type))
        methods = unittest.defaultTestLoader.getTestCaseNames(test_class)
        self.assertTrue(methods)
        self.assertFalse(getattr(test_class, "__unittest_skip__", False))
        for method in methods:
            self.assertFalse(getattr(getattr(test_class, method), "__unittest_skip__", False))

        def cases(suite):
            for test in suite:
                if isinstance(test, unittest.TestSuite):
                    yield from cases(test)
                else:
                    yield test

        expected = {module_name + ".TestWindowsPeReader." + method for method in methods}
        actual = [test for selection in DEFAULT_MODULES
                  if selection == module_name or selection.startswith(module_name + ".")
                  for test in cases(unittest.defaultTestLoader.loadTestsFromName(selection))]
        self.assertEqual({test.id() for test in actual}, expected)
        self.assertEqual(len(actual), len(expected))
        for test in actual:
            self.assertIs(type(test), test_class)
```

- [x] **Step 2: 定点运行新增配对方法取得 assertion RED。**

```bash
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest tests.test_run_workspace_ci.TestWorkspaceCiCoverage.test_pe_reader_portable_contract_is_selected_once_without_skips
```

Expected：DEFAULT count 0 !=1 的单 assertion FAIL，0ERROR/skip；不是 reader 导入失败。

- [x] **Step 3: apply_patch 在 `scripts/run_workspace_ci.py` 的 DEFAULT 中原 PE capture 下一行增加一个模块；下面是完整 DEFAULT 赋值，文件其它内容不动。**

```python
DEFAULT_MODULES = (
    "tests.test_workspace",
    "tests.test_workspace_hook_contract",
    "tests.test_windows_snapshot_rejection_diagnostic",
    "tests.test_autonomy",
    "tests.test_workbench",
    "tests.test_workbench_rejected_body",
    "tests.test_cli_resume_sandbox",
    "tests.test_shared_runtime_budget",
    "tests.test_contract_finalization",
    # Portable build/transport contracts only; host C fixtures are not native
    # Windows proof and are intentionally not selected as required coverage.
    "tests.test_windows_bootstrap_binding.TestWindowsBootstrapBinding",
    "tests.test_windows_direct_volume.TestWindowsDirectVolume",
    "tests.test_windows_build_context.TestWindowsBuildContext",
    "tests.test_windows_pe_capture.TestWindowsPeCapture",
    "tests.test_windows_pe_reader",
    *CONTRACT_ENGINEERING_TESTS,
    # Host/framework contracts are bounded; optional Go SDK diagnostics are
    # separate and do not stand in for native resource-scope acceptance.
    "tests.test_engineering_verification.TestEngineeringVerification",
    "tests.test_engineering_verification.TestEngineeringAdapters",
    "tests.test_engineering_verification.TestEngineeringResourceDispatch",
    "tests.test_engineering_verification.TestPythonIsolatedTemplate",
    "tests.test_engineering_evidence.TestEngineeringEvidence",
    "tests.test_engineering_evidence.TestEngineeringReceiptValidation",
    "tests.test_engineering_evidence.TestEngineeringEvidencePack",
    # Keep the integration matrix bounded while exercising task-tree capture,
    # result-commit binding, and receipt export/import on each workspace platform.
    *CROSS_PLATFORM_R3_TESTS,
    # The no-follow POSIX tree walker is shared by Linux and macOS; don't add
    # this POSIX-only Git differential to the Windows workspace test selection.
    *(POSIX_R3_TESTS if os.name == "posix" else ()),
)
```

- [x] **Step 4: 指定新模块、配对选择全文与旧消费者回归；作者按冻结版本自审、四 SHA 后 STOP。**

```bash
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest tests.test_windows_pe_reader tests.test_run_workspace_ci tests.test_native_helper tests.test_windows_bootstrap_binding.TestWindowsBootstrapBinding tests.test_windows_pe_capture.TestWindowsPeCapture
sha256sum scripts/windows_pe_reader.py tests/test_windows_pe_reader.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
```

Expected：0F/E；新 reader/新配对无 skip，既有模块若有平台 skip 必须按实际逐项记录，不代替新合同 PASS。旧 machine 70bytes 正控与新 reader 拒绝共存，bootstrap/capture 正常；作者不 commit/push、不运行 DEFAULT/full/native/model。根代理后续再新鲜独立双审和独立运行。

## 设计→具名覆盖对应（不以计划充当执行证据）

| 合同 | Task 1 方法 / Task 2 配对 |
| --- | --- |
| exact types/arch、三双错误顺序 | exact_input_types_and_arch_values；bad_arch_precedes_empty_budget；directory_limit_precedes_array_truncation；section_ranges_precede_overlap_independent_of_order |
| 空/8MiB、DOS/PE/COFF/optional/magic/section表逐层截断 | empty_and_image_budget_exact_boundary；dos_signature_and_truncation；pe_offset_bounds_and_complete_coff；pe_signature；optional_header_length_and_magic；section_table_truncation |
| machine、1/96/0/97、目录0/16/17与数组不足 | minimal_both_architectures_and_empty_directories；machine_unsupported_and_expected_mismatch；section_count_policy；section_count_96_and_search_bound；all_declared_directory_pairs_preserved_only_as_metadata；directory_array_must_fit_declared_optional_header |
| headers非零/覆盖表/file/image/SizeImage零 | header_ranges_and_zero_image_size；header_and_section_reads_at_exact_ends |
| raw/virtual全数值范围、header overlap、全跨度overlap/order/邻接 | raw_and_virtual_section_ranges；header_raw_and_virtual_overlaps；full_raw_padding_and_virtual_zero_fill_overlap；section_ranges_precede_overlap_independent_of_order；unordered_adjacent_sections_and_independent_reads |
| VirtualSize0、raw0指针忽略、双零、zerofill/padding不补齐 | zero_virtual_size_uses_raw_extent；zero_raw_size_ignores_pointer_and_never_zero_fills；both_section_sizes_zero_provide_no_mapping；zero_fill_and_raw_padding_not_file_backed |
| index4是fileoffset、普通未映射/单边零仅元信息、未声明不补 | certificate_directory_file_offset_is_not_validated_as_rva；all_declared_directory_pairs_preserved_only_as_metadata；minimal_both_architectures_and_empty_directories |
| 严格参数/uint32/SizeImage/单读预算、完整backing/跨区/gap/overlay | read_argument_types_sign_and_budget；exact_read_budget_supported_when_single_header_region；gap_overlay_and_header_crossing_are_not_fallbacks；read_methods_have_identical_rejections；unordered_adjacent_sections_and_independent_reads |
| 原bytes、immutable、quiet/repr/body不泄漏、旧API不改 | immutable_metadata_original_bytes_and_quiet_repr；old_minimal_machine_contract_remains_distinct |
| DEFAULT所有方法恰一次、无skip | Task 2 test_pe_reader_portable_contract_is_selected_once_without_skips |

### Task 3: 新鲜双审与 root 独立软件验收

**状态**

- [x] 任务完成（本机软件合同；不替原生或整体门）

**Dependencies:** Task 2
**Parallelizable:** No (作者冻结 STOP 后 SPEC → 不同 QUALITY → root 串行，禁止第二套全量同时运行)

- [x] **Step 1: 新鲜独立实施 SPEC 逐项比设计/计划/四源码及实际作者履历；通过后由不同人员 QUALITY。** 两审需记录实际 C/I/M、missing/extra/mismatch、四源码 SHA、完整读取范围及运行权限；未通过先恢复作者修改/TDD再冻结，不能继承设计审查代替实施审查。root 另全文回读四文件，核源码范围和调用链。

- [x] **Step 2: root 独立运行定点与 20 轮关键路径。** 下列命令必须在前项已结束后串行；沿现有批准环境把 `.venv/bin/python` 绑定实际解释器，记录 Python/Go 版本、cwd、每轮摘要，不安装工具、不读取 KEY。

```bash
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest tests.test_windows_pe_reader tests.test_run_workspace_ci tests.test_native_helper tests.test_windows_bootstrap_binding.TestWindowsBootstrapBinding tests.test_windows_pe_capture.TestWindowsPeCapture
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -c 'import sys, unittest; suite_name="tests.test_windows_pe_reader"; total=0; runner=unittest.TextTestRunner(verbosity=1)
for round_number in range(1,21):
    print("PE reader round", round_number, flush=True)
    result=runner.run(unittest.defaultTestLoader.loadTestsFromName(suite_name))
    total+=result.testsRun
    if not result.wasSuccessful() or result.skipped: sys.exit(1)
print("PE reader total", total, flush=True)'
```

Expected：定点0F/E，新合同0skip；20轮各33PASS/0F/E/skip，累计660，不把20轮误写成新增660方法。若实际方法数变动，先对照冻结设计与 TDD 原因再重审并按实际记数。任何失败暂停本片交付，不放宽预算/吞异常/skip；长运行每60秒内中文进度。

- [x] **Step 3: 20轮结束后 DEFAULT，结束后原三道完整 preflight。**

```bash
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 GOTOOLCHAIN=local CMAKE_BUILD_PARALLEL_LEVEL=1 .venv/bin/python -B scripts/run_workspace_ci.py
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 GOMAXPROCS=1 GOFLAGS=-p=1 GOTOOLCHAIN=local CMAKE_BUILD_PARALLEL_LEVEL=1 .venv/bin/python -B scripts/preflight.py
```

Expected：两命令退出0；完整 unittest 实际 total/PASS/F/E/环境skip与子退出码/时间均记录。原 preflight 测试是当前解释器 `-m unittest`，不得改选择/argv/cwd/env/返回码；若 root 只读 wrapper 打印原子 summary，需精确保留原合同。DEFAULT 的 portable 成功不是 actual native PE 解析。已有 Windows/Mac 外部门仍另记，不因本片局部成功撤销。

- [x] **Step 4: 编译 j1、治理/网站/排期结构/diff/双轮文档一致性与秘密/子模块重验。**

```bash
PYTHONPATH=src:. PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m compileall -q -j 1 src scripts tests
.venv/bin/python -B scripts/check_governance.py
.venv/bin/python -B scripts/check_site.py
.venv/bin/python -B scripts/check_agent_landscape.py --today 2026-10-09
git diff --check
sha256sum scripts/windows_pe_reader.py tests/test_windows_pe_reader.py scripts/run_workspace_ci.py tests/test_run_workspace_ci.py
.venv/bin/python -B scripts/preflight.py --only secrets
.venv/bin/python -B scripts/preflight.py --only submodule
```

Expected：全部0且四源码 SHA 不变。compileall 缓存仅仓外临时目录（root 可用现有 PYTHONPYCACHEPREFIX），不在仓库留下新 artifacts；资源限制 j1 ≤用户j6。landscape只验观察日期/20项结构，不能声称20上游已刷新。文档技能需由 root 全文读取并跑精确相关文档连续两轮 0疑似项，人工再核12reasons/编号顺序/矩阵/index4/政策与信用字段。更新实际履历后重复治理/site/landscape/diff与secrets/submodule，再冻结，不重写设计审查对象。软件自检七维分别据实际证据填写。

### Task 4: 已授权 main 精确阶段发布与同 SHA 观察

**状态**

- [ ] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No (必须全部守卫通过，精确index核对后发布，再独立观察新SHA)

- [ ] **Step 1: 只暂存四源码及精确相关交付文档。** root 先只读核 `git status --short`、`git branch --show-current`、parent/vendor gitlink、四SHA。精确七文档为本计划、原冻结设计、研究输入、本片更新的 `docs/agent-landscape-live.md`、root独自写入的上一片收尾 `docs/nbl/plans/2026-10-09-windows-snapshot-rejection-diagnostic.md`，及新原生失败输入 `docs/nbl/specs/2026-10-09-macos-detached-output-timing-research.md` / `docs/nbl/specs/2026-10-09-windows-build-context-rejection-research.md`；后二者只有调查，不借此添加实施范围。若有其它用户 dirty 不暂存，必要新 ignored doc 只显式 force-add 单路径。不 `git add .`、不创建分支、不修改 vendor/权限。

- [ ] **Step 2: 核index恰好以上四源码+七文档（总11路径）、逐文件index bytes等于工作树、四SHA和vendor `1693651c1bd7daad3272eb054f0f81d6f254d08d` 干净，再已授权main提交推送。** 如基线/vendor在安全收尾阶段正常前进，先解释实际差异并重验门，不假装仍118a；源码变动返回独立验收。示范命令仅在 exact index 已验证后：

```bash
git commit -m "test: add bounded PE header and RVA reader"
git push origin main
git ls-remote origin refs/heads/main
```

Expected：commit/push退出0；remote main与本次新SHA相同，保留仅main。独立官方GitHub读取核main/parent及新CI/provenance/Pages run的head_sha。不新发release/PyPI、不加CI权限、不取消/重跑原生job。

- [ ] **Step 3: 新独立只读观察者绑定新SHA，root独立回读决定性原生日志/回执。** 记录每格目标/image/Python/commit/vendor/summary/skip/actualreceipt，terminal后STOP；旧118a成功/失败不能挪用作新SHA。签名/provenance/页面各自信用分开。新 portable reader在workspace运行仍不是同SHA成品被实际解析，不更新capture三false；成品目录/manifest接入须下一独立设计，不能本片偷加。

- [ ] **Step 4: 据实写本片阶段结论和整体未过门，自动续安全下一片。** 本片可完成的是软件基础层与具体发布观察，不宣称整个R2/R3完成。模型KEY/endpoint、SKILL Git管道、macOS额度、Windows标准用户/WFP/首次UAC/Win10及其它硬门继续按已确认权限制定后续设计，不用本片绕过。

## 计划静态自审与实施交付报告边界

规划作者已全文读取 writing-plans、AGENTS、冻结设计、研究文档、现有两选择文件与旧 machine/preflight上下文。自审覆盖表对应设计全部具名向量；四源码样例无未定义 API，reader仅标准库/纯bytes，字段与测试一致；没有新增parse_complete/准入字段。实际纯AST解析：四个Python块通过，新模块33个test方法、配对1方法；20轮命令内联Python也静态可解析。新DEFAULT剔除唯一新模块后，与现有DEFAULT AST逐项相同；M1三个具名向量均存在；占位符检索无匹配。未执行任何样例代码、未临时写源码、不计测试通过。实际测试/编译/性能/原生/模型/发布仍0，本阶段不填“可运行100%”。

实施后 root 必须输出【架构级自检报告】七项，按本片实际证据：语法/编译、依赖/调用链、逻辑/边界、异常处理、关联模块、兼容安全、可运行性。没有实际执行的项目标未验证；静态覆盖不能写全异常证明；只证软件子合同，不授总体完成。

root后续：已全文分片回读最终计划、现有选择文件及旧machine源码，独立纯AST四块/33+1/12闭reason/DEFAULT原AST一致。计划61f1e768冻结获新鲜独立SPEC C0/I0/M0，之后不同QUALITY C0/I0/M1，均只读STOP；非阻断M1是双section全零payload辨识度，Task1作者需在实际bytes中放不同marker并断言两个offset，不改算法/范围。root按用户既有“你决定阶段”“不用等命令”“不断运行”的自治授权选择A，未收到新A/B答案、不捏造批准；限定CI基础层且无新依赖/特权/生产准入。使用subagent-driven-development按任务新作者，保留用户直接main约定，不创建默认worktree/branch。Task1已交新作者TDD；作者阶段不得提交推送，其后独立实施SPEC→不同QUALITY和Task2新作者/全局双审及root门仍待实际执行。本文起草段落的0运行是当时历史，本行也不填写尚未取得的GREEN。

---
Task1 作者实际履历（2026-10-09）：最初3方法缺接口 assertion RED为3F/0E/0skip/0.001s，完整33方法缺接口RED为33F/0E/0skip/0.002s，均仅证接口缺失。首实现32P/1夹具ERROR/0skip/0.032s：96节默认PEoffset0x80令table末尾0x1008、headers0x1100与首VA0x1000重叠；只在96正控指定合法PEoffset64（table末尾0xfc8、headers0x1000），没有放宽reader。夹具ERROR不授行为RED/GREEN。修正后33P/0F/E/skip/0.032s；最终计数33方法/127 subtest回调/0F/E/skip/0.027905s。独立两个raw区域实际A/B非零marker及offset0x200/0x300已通过。作者逐行SPEC→QUALITY自审后冻结STOP；两源码SHA分别`af89469f74cc495a88e3db9570cb023920abe25dba8a74cbede4c659515470c4`、`0e934e3110712be7a34e2de9d79776cc86c85e66178b251d06e89dfd3dfb0e29`。root已全文回读并同步本文两完整样例为实际源码；独立实施双审与后续默认/完整/原生门尚待执行。

Task1 新鲜独立实施SPEC C0/I0/M0，33P/0F/E/skip/0.028s/exit0；不同QUALITY C0/I0/M0，33P/0F/E/skip/0.033s/exit0。两审各自全文读取并在审前后核两源码SHA不变，均只读STOP。设计QUALITY M1优先级的三个具名向量及计划QUALITY M1双非零marker/offset均实际通过；不把这些局部门挪作DEFAULT/full/native或整体信用。Task2已交另一个新作者，限定现有两选择文件TDD；后续全局双审/root门尚待。

Task2 新作者实际TDD：paired RED 0P/1F/0E/skip/0.000s/exit1，唯一assertion是count0!=1；DEFAULT仅新增一行后paired GREEN 1P/0F/E/skip/0.005s/exit0。五选择实际101P/0F/E/skip/0.421s/exit0（reader33、CI选择20、native helper7、bootstrap18、capture23），原byte binding PASS。作者全文两阶段SPEC→QUALITY自审C0/I0/M0、exact diff29新增/0删除与diffcheck通过，冻结STOP。Task1两SHA不变；现有两选择SHA分别`e3cb0c27b9eab74d97f61222e7779c3acdf4ac4a9c52da4e56e1328c91d6d81c`、`59f0eeaf5c8daf9c1ba2345a80e32eef215d50372335d0625594dd5f71f4fab0`。root已回读四源码与exact diff；已启动覆盖两任务的新鲜独立全局SPEC，其后不同QUALITY/root软件守卫仍待。

新鲜全局实施SPEC C0/I0/M0（missing/extra/mismatch全0），五选择101P/0F/E/skip/0.466s/exit0；之后不同全局QUALITY C0/I0/M0，101P/0F/E/skip/0.383s/exit0；四SHA审前后不变，均只读STOP。root独立定点101P/0F/E/skip/0.402s/exit0及原byte binding PASS；随后20轮每轮33P/0F/E/skip/exit0，总660执行、wall0.623697s，不是660新增方法。root纯AST核四样例、两新样例逐字等source、paired/完整DEFAULT与source AST相同，去唯一reader项后整runner AST与118a一致，未执行文档样例。DEFAULT正在串行运行，完整preflight/编译/最终文档门/提交推送待实际完成。

root后续软件门进度：DEFAULT实际518P/0F/E/skip/164.581s/exit0，原byte binding PASS；随后启动原三道preflight。只读summary wrapper对原`[sys.executable,-m,unittest]`一次调用核argv/所有kwargs完全相同，原返回对象不修改，结束后还原；本行尚无完整守卫结论。四源码SHA仍冻结；Python实际3.11.15、Go1.27.1，所有构建并发1。下一build-context候选仅独立只读研究与三步结构化思考112–114，未写新设计或实现、未扩大本片四源码/七文档范围。

root完整守卫实际结束（UTC23:01:14核终态）：2373 total/2314P/0F/E/59既有环境skip，unittest481.435s、原子进程exit0/wall481.666395s；byte binding PASS；原三道全部通过exit0/wall482.789821s。只读wrapper实际仅一次原unittest调用，不修改argv/kwargs/返回，结束后还原；不把59skip或本机成功填作原生/成品解析/模型信用。没有第二套全量同时运行；编译与最终文档/治理/秘密/子模块重验随后执行，提交推送尚待。

root最终软件门：compileall显式-j1 exit0/wall0.496253621s，pyc仅仓外`/tmp/icode-pe-foundation-pyc-tX61YzbM`；治理/网站/landscape指定2026-10-09/diff各自exit0。最终七文档连续两轮各0疑似项，人工另核12reason、构造顺序/具名33+1、index4政策与三false、研究固定源码及历史状态界限；最新文档更新后secrets/submodule各自exit0。四源码不变，vendor1693651工作树与gitlink一致。landscape通过只证明20项结构/排期，本片定点研究没有全量刷新20项目。下一build-context类别研究已独立STOP，root复核相关原源码/许可并写入原有研究路径，不扩大源码范围。

### 本片架构级自检报告（发布前软件验收）

- 语法/编译：Python导入、原完整unittest与compileall-j1通过。
- 依赖/调用链：纯标准库新reader；旧machine/消费者/preflight未改，DEFAULT仅一次新选择。
- 逻辑/边界：33具名实际bytes正负控、三个优先级向量、两marker/offset及20轮通过。
- 异常处理：所列闭集精确异常/reason/文本通过，无partial/吞异常成功；不称任意异常穷尽证明。
- 关联模块：root101定点、DEFAULT518及完整2373执行通过，byte binding PASS。
- 兼容安全：旧70-byte API、捕获三false、四源码SHA/vendor及无新依赖/权限保持；原生未过门保留。
- 可运行性：本机本片软件合同通过；59既有环境skip、跨平台成品解析/生产隔离/模型及R2/R3未验证，不填总体100%。

Task4提交/推送和新SHA观察仍待，不能将上述软件验收写作远端已发布。

**Execution Mode:** serial

任务链 Task1→Task2→Task3→Task4，范围四源码且涉及新解析器/边界，因此不选inline，不并发实现或全量测试。历史规划交接为候选计划冻结→root独立静态审验→fresh SPEC→不同QUALITY，当时规划作者STOP、不自动触发实施。root随后依据既有自治授权选A并有序交新作者实施，未冒称取得新的A/B答复；当前实际状态与尚待门以各Task及履历为准。
