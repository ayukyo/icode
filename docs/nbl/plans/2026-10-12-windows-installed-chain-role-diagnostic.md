# Windows 已安装持有链结构角色有限诊断 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在已安装 helper/verifier 实际持有链上输出有限 v2 结构角色、直接操作候选、实际子 DACL protected 位与单父子边旗标候选，并由父进程独立绑定运行时。

**Architecture:** 复用同 HANDLE 双 SD、metadata、原 source policy、独立 backend 与反向关闭账本。只在诊断 probe 增加有限派生、严格 v2 validator，并同步父 observer；生产 owner、IO mutation、security/pin/consumer、readiness 合同不变。派生候选不是 AccessCheck 或准入证明，三个 authority 始终 exact false。

**Tech Stack:** Python 3.11/3.12、unittest、现有 Windows ctypes backend、canonical JSON、现有 Windows 签装四格 CI。

---

日期：2026-10-12。状态：**PLAN ONLY，未实施、未运行任何测试或编译。** 本文新增是本轮唯一文件写入；不写 Git、不读 KEY、不改 Linux Task3 的六个源码候选。writing-plans 的自动实施、工作树创建和提交步骤受本轮明确范围覆盖；本文通过 fresh SPEC → 不同 QUALITY 并由 root 全文阅读后才可进入后续实施阶段，本文不自行委托评审或开始实现。

设计依据：[冻结 DESIGN](../specs/2026-10-12-windows-installed-chain-role-diagnostic-design.md)，205 行，SHA-256 `9c233c11e75f0364184daea7eaeb8533fe6bf3ced4ae3c509a54fae05b52c038`；已完成 fresh SPEC → 不同 QUALITY C0/I0/M0、root 全文阅读。DESIGN历史源码观察基线为 `574033a4df8311a569230bbd0522a0e1be717d8a`；本PLAN冻结基线更新为root刚完成发布的 `1e2e4ab5d0101acf00d609af37add9893e4c57ef`，不改历史DESIGN。vendor/icode-skill 固定 `21566a5`，不是本片修改目标。实施前重新核当时实际候选及脏工作树，不将旧基线或旧 v1 回执补授 v2 信用；本文未跟踪新文档不被“trackedstatus空”描述掩盖。

三问已确认：真实缺口为诊断角色和父运行时归属；held chain/parser/policy/capture/ledger 已存在；调用链为 probe → validator → wheel CI 父 observer → signed installed 四格，必须同步 CLI 和 receipt 测试。sequential-thinking 三步记录在本轮 context：需求/范围分解、复用方案、失败与证据边界风险。

## 文件与现有资产

以下是实施阶段的精确范围，本轮不修改这些文件。

| 文件 | 责任/实际已读资产 | 实施范围 |
| --- | --- | --- |
| `scripts/probe_windows_installed_chain.py` | `_observe_resource/probe/validate_wire/main`，现 286 行 | 有限派生、v2、父期望必需参数、自消费同步 |
| `scripts/run_windows_wheel_ci.py` | `_observe_installed_chain`、相邻 source observer、main signed 调用，477 行 | child 启动前捕获父版本；严格 validator 传参；明确 protected_observed=false |
| `tests/test_windows_installed_chain.py` | `descriptor/acl/ace/sid` 导入、ObservationBackend、六个测试类、receipt/wire，553 行 | 新增三个 observation 方法、两个 wire 方法；旧 fixture 与调用同步 |
| `tests/test_windows_bootstrap_binding.py` | required `InstalledSourceCaptureTests` 与 optional `TestWindowsBootstrapBinding` 的 chain capture/main 顺序 fixture，842 行 | 前者新增一个必需 chain 父版本方法；后者旧 chain mocks 同步 v2/版本/摘要 |
| `tests/test_windows_startup_native.py` | 原生 `WindowsSecurityQueryTests` 自有 temp、root/child HANDLE、close_handles，完整文件已读 | 复用真实 fixture，新增一个自有对象 protected on/off 的方法 |
| `tests/test_windows_startup_pin_ci.py` | `PORTABLE_CLASSES/COUNTS`、`NATIVE_COUNTS`、required body/fixture/subTest skip 守护，391 行 | 精确计数同步，原 skip 语义不变 |
| `scripts/run_workspace_ci.py` | `startup_pin_tests`、selected_pin_ids、fixture/subTest skip 必需守护 | 本片不新增类；现有 selector 已覆盖上述新增方法，预期不改 |
| `.github/workflows/windows-helper-provenance.yml` | 实际 x64/ARM64 × 3.11/3.12、signed wheel 参数与顺序，全文已读 | sign checkout补fetch-depth:0保证固定历史对象；补一个历史RED/当前69required命中步骤，不改签名权限、不触发发布 |

只读复用 `src/icode/windows_startup_security.py` 的 control/entries 与 mutation mask，以及 `tests/test_windows_startup_security_native.py` 的实际自有 descriptor storage/ABI/LocalFree 负控。后者是 portable fake DLL，不能称 Windows OS fixture。原生 fixture 是 `tests/test_windows_startup_native.py::WindowsSecurityQueryTests`；已完整读取 `tests/windows_private_dacl_fixture.py`，复用其 `_Native.open/call`、`_ConvertedDacl` 非NULL自有DACL与 `_close_all`，不改这个文件/旧set_marker/_marker/_stable/窗口合同。

冻结前六类方法数为 `7,1,13,7,9,4`，chain 共 41；required `InstalledSourceCaptureTests` 为 5；原生 security 为 2。新增后对应 `7,1,16,7,11,4`，chain 共 **46**；source capture **6**；native security **3**。总新增 portable 6/native 1，不增加测试类。旧 `TestWindowsBootstrapBinding` 整类和 host compiler 仍 optional，不能仅凭该类的 chain 负控当 required 命中。

## Task 1：实际 descriptor 派生与持有链观察

**状态**

- [x] 任务完成（可移植观察软件门；不是Windows原生）

**Dependencies:** None
**Parallelizable:** No（先冻结唯一派生定义，后续 validator 和 fixture 依赖此合同）

- [ ] Step 1：在 `InstalledObservationTests` 增加以下三个方法，复用真实 byte descriptor parser 与现有 observe/backend；不用新 Mock dict 替实际 SD。

Task1 portable行为RED仍在生产派生实现前执行。Ubuntu本地没有Windowsnative窗口；Task4新native方法在四签装CI分别对固定历史producer实际取得行为RED，再对当前候选取得GREEN，不阻塞本地portable实现，不冒充当前实施前的时间史。测试侧已有imports/backend与descriptor无需新接口；每个目标字段先assertIn再读取，缺字段报告assertion FAIL而不是KeyError ERROR。

```python
def test_structural_roles_control_and_actual_child_edges(self):
    for count in (2, 4, 32):
        backend = ObservationBackend(count=count)
        child_raw = descriptor(control=0x9004)
        backend.security_changes.update({(count, read): child_raw for read in (1, 2)})
        result = self.observe(backend)
        for i, node in enumerate(result["chain"]):
            for key in ("structural_roles", "dacl_protected", "inheritance_to_next"):
                self.assertIn(key, node, "actual descriptor observation must emit role/control/edge")
            expected = []
            if i < count - 1:
                expected.append("route_ancestor")
            if i == 0:
                expected.append("volume_root")
            if i == count - 2:
                expected.append("image_parent")
            if i == count - 1:
                expected.append("image_leaf")
            self.assertEqual(node["structural_roles"], expected)
            self.assertIs(node["dacl_protected"], i == count - 1)
            if i == count - 1:
                self.assertIsNone(node["inheritance_to_next"])
            else:
                edge = node["inheritance_to_next"]
                self.assertEqual(edge["next_index"], i + 1)
                self.assertIs(edge["child_dacl_protected"], i == count - 2)
        self.assertFalse(backend.live)
        self.assertEqual(backend.closed, list(range(count, 0, -1)))

def test_direct_candidates_separate_directory_leaf_and_keep_io_policy(self):
    mask = 0x2 | 0x4 | 0x40 | 0x10 | 0x100 | 0x10000 | 0x40000 | 0x80000 | 0x40000000 | 0x10000000
    raw = descriptor(dacl=acl((ace(mask=mask), ace(1, 0, mask),
                              ace(0, 8, mask, sid(1, (0,))))))
    result = self.observe(ObservationBackend(security=raw))
    common = ["write_ea", "write_attributes", "delete_object", "write_dacl", "write_owner", "generic_write", "generic_all"]
    for node in result["chain"]:
        self.assertIn("direct_operation_candidates", node["entries"][0],
                      "actual allowed ACE must emit direct candidates")
        direct = (["add_file", "add_subdirectory", "delete_child"] if node["directory"]
                  else ["write_data", "append_data"]) + common
        self.assertEqual(node["entries"][0]["direct_operation_candidates"], direct)
        self.assertEqual(node["entries"][1]["direct_operation_candidates"], [])
        self.assertEqual(node["entries"][2]["direct_operation_candidates"], [])
        self.assertEqual(node["policy_result"], "mutation_untrusted")
        self.assertEqual(node["entries"][2]["mutation"], mask if node["directory"] else mask & ~0x40)

def test_single_edge_flags_include_deny_io_np_and_use_child_control(self):
    flags = (0, 1, 2, 4, 8, 16, 1 | 4, 2 | 8, 1 | 2 | 4 | 8 | 16)
    raw = descriptor(dacl=acl(tuple(ace(i % 2, f, 2) for i, f in enumerate(flags))))
    for protected in (False, True):
        backend = ObservationBackend(security=raw)
        # Parent protected is the opposite: it must not replace actual child control.
        parent = descriptor(dacl=acl(tuple(ace(i % 2, f, 2) for i, f in enumerate(flags))),
                            control=0x8004 if protected else 0x9004)
        child = descriptor(control=0x9004 if protected else 0x8004)
        backend.security_changes.update({(3, read): parent for read in (1, 2)})
        backend.security_changes.update({(4, read): child for read in (1, 2)})
        result = self.observe(backend)
        for index, bit in ((0, 2), (2, 1)):
            self.assertIn("inheritance_to_next", result["chain"][index],
                          "actual parent and child observations must emit an edge")
            edge = result["chain"][index]["inheritance_to_next"]
            self.assertEqual(edge["flag_candidate_indices"], [i for i, f in enumerate(flags) if f & bit])
        edge = result["chain"][2]["inheritance_to_next"]
        self.assertIs(edge["child_dacl_protected"], protected)
        self.assertEqual(edge["state"], "flag_candidates_child_protected" if protected
                         else "flag_candidates_child_unprotected")
```

- [ ] Step 2：运行精确 RED 命令，预期三个方法各产生目标字段缺失的assertion FAIL：3 tests/3 failures/0 errors/0 skip；KeyError、缺名字、接口错误、未加载或零命中不算有效RED。若出现ERROR先修测试脚手架再重跑，未取得行为RED不得实现生产派生。

```bash
PYTHONPATH=src .venv/bin/python -B -m unittest tests.test_windows_installed_chain.InstalledObservationTests.test_structural_roles_control_and_actual_child_edges tests.test_windows_installed_chain.InstalledObservationTests.test_direct_candidates_separate_directory_leaf_and_keep_io_policy tests.test_windows_installed_chain.InstalledObservationTests.test_single_edge_flags_include_deny_io_np_and_use_child_control -v
```

- [ ] Step 3：在 probe `_policy_result` 后加入以下完整私有派生函数；所有输入来自已解析/已校验有限字段，不把 helper 暴露成生产 API。

```python
def _structural_roles(index, count):
    roles = []
    if index < count - 1:
        roles.append("route_ancestor")
    if index == 0:
        roles.append("volume_root")
    if index == count - 2:
        roles.append("image_parent")
    if index == count - 1:
        roles.append("image_leaf")
    return roles


def _direct_candidates(entry, directory):
    if not entry["allowed"] or entry["flags"] & 0x08:
        return []
    choices = [(0x2, "add_file" if directory else "write_data"),
               (0x4, "add_subdirectory" if directory else "append_data")]
    if directory:
        choices.append((0x40, "delete_child"))
    choices.extend(((0x10, "write_ea"), (0x100, "write_attributes"),
                    (0x10000, "delete_object"), (0x40000, "write_dacl"),
                    (0x80000, "write_owner"), (0x40000000, "generic_write"),
                    (0x10000000, "generic_all")))
    return [name for bit, name in choices if entry["mutation"] & bit]


def _inheritance_edge(chain, index):
    if index == len(chain) - 1:
        return None
    child = chain[index + 1]
    bit = 0x02 if child["directory"] else 0x01
    candidates = [i for i, entry in enumerate(chain[index]["entries"]) if entry["flags"] & bit]
    state = ("no_flag_candidates" if not candidates else
             "flag_candidates_child_protected" if child["dacl_protected"] else
             "flag_candidates_child_unprotected")
    return {"next_index": index + 1,
            "target_kind": "directory" if child["directory"] else "file",
            "child_dacl_protected": child["dacl_protected"],
            "flag_candidate_indices": candidates, "state": state}
```

- [ ] Step 4：保留 `_observe_resource` 原 try/except/close 结构及双快照预算。将原 chain.append 区域替换为以下块，在 `owner.revalidate()` 前加入第二阶段 edge；不挪动关闭语义、不重试 HANDLE。

```python
entries = [{"allowed": entry.allowed, "flags": entry.flags,
            "mutation": entry.mask & mask,
            "trustee": _trustee_category(entry.sid, host_sid)} for entry in first.entries]
for entry in entries:
    entry["direct_operation_candidates"] = _direct_candidates(entry, baseline.directory)
chain.append({"index": index,
              "kind": "root" if index == 0 else "file" if index == count - 1 else "ancestor",
              "directory": baseline.directory, "metadata_observed_equal": True,
              "descriptor_observed_equal": True, "parser_result": "supported",
              "policy_result": policy, "owner": _owner_category(first.owner_sid, host_sid),
              "entries": entries, "structural_roles": _structural_roles(index, count),
              "dacl_protected": bool(first.control & 0x1000), "inheritance_to_next": None})
```

```python
for index, node in enumerate(chain):
    node["inheritance_to_next"] = _inheritance_edge(chain, index)
```

- [ ] Step 5：重复 Step2 GREEN，预期3 tests/0 skip/error/failure。随后运行 `InstalledObservationTests` 全类16；保持旧读取/SD/metadata drift、unknown policy、close/BaseException、512/514、32/33负控。此时probe schema升级与real receipt自消费同步待Task2；`InstalledProbeTests` 全类7（含实际receiptvalidator）在Task2完成后执行，避免把中间v1/v2接口冲突当任务完成，不以部分步骤授交付信用。

## Task 2：严格 v2 wire、父期望与完整 fixture 同步

**状态**

- [x] 任务完成（便携软件测试；父接线和原生安装验收仍属后续任务）

**Dependencies:** Task 1
**Parallelizable:** No（v2 schema 与 observation 同步）

- [ ] 前置脚手架：先安装本Task Step3给出的完整enrich_receipt/validate/receipt代码和所有实际测试imports，再新增Step1测试。生产仅将validator签名机械同步为 `def validate_wire(wire, source_sha, arch, *, expected_python, expected_windows):`，暂不改其v1 schema/键/范围/派生检查；CLI调用机械补Step4已有完整kwargs块。此为接口兼容脚手架，不记目标v2/runtime已实现或GREEN。两个测试先使用完整有效v2正控，捕获旧validator的ValueError并转成明确self.fail，保证RED来自拒绝有效v2这一目标行为；正控尚未可接受时不继续负控矩阵引入错误。随后Step4才实现目标行为。

- [ ] Step 1：先在 `InstalledWireTests` 新增两个方法。`receipt` 在 Step 3 升级后才提供有效 v2 正控；旧代码下先确认 v2 不被误接收，新增字段伪造由旧 validator 拒绝不能替新 validator 已验证信用。

```python
def test_v2_derived_fields_and_edge_exact_types_are_recomputed(self):
    original = receipt()
    try:
        accepted = validate(wire(original), SHA, "x64")
    except ValueError:
        self.fail("validator must accept the complete valid v2 role/control/edge receipt")
    self.assertEqual(accepted, original)
    paths = [("structural_roles", []), ("structural_roles", ["image_leaf"]),
             ("structural_roles", ["route_ancestor", "volume_root", "image_parent", "image_parent"]),
             ("dacl_protected", 0), ("inheritance_to_next", None)]
    for key, value in paths:
        data = copy.deepcopy(original)
        data["resources"][0]["chain"][0][key] = value
        with self.subTest(key=key), self.assertRaises(ValueError):
            validate(wire(data), SHA, "x64")
    for key in ("structural_roles", "dacl_protected", "inheritance_to_next"):
        data = copy.deepcopy(original)
        del data["resources"][0]["chain"][0][key]
        with self.subTest(missing=key), self.assertRaises(ValueError):
            validate(wire(data), SHA, "x64")
    edge = original["resources"][0]["chain"][0]["inheritance_to_next"]
    for key, value in (("next_index", True), ("next_index", 0), ("target_kind", "directory"),
                       ("child_dacl_protected", True), ("child_dacl_protected", 0),
                       ("flag_candidate_indices", [True]), ("flag_candidate_indices", [0, 0]),
                       ("flag_candidate_indices", [0]), ("state", "flag_candidates_child_protected")):
        data = copy.deepcopy(original)
        data["resources"][0]["chain"][0]["inheritance_to_next"][key] = value
        with self.subTest(edge_key=key), self.assertRaises(ValueError):
            validate(wire(data), SHA, "x64")
    self.assertEqual(set(edge), {"next_index", "target_kind", "child_dacl_protected", "flag_candidate_indices", "state"})
    for value in ([], ["write_data"], ["add_file", "add_file"], [True]):
        data = copy.deepcopy(original)
        data["resources"][0]["chain"][0]["entries"][0]["direct_operation_candidates"] = value
        with self.subTest(direct=value), self.assertRaises(ValueError):
            module().validate_wire(wire(data), SHA, "x64", expected_python=[3, 11], expected_windows=[10, 0, 123])
    for obj_path in (("resources", 0, "chain", 0, "inheritance_to_next"),):
        for mode in ("extra", "missing"):
            data = copy.deepcopy(original)
            obj = data
            for part in obj_path:
                obj = obj[part]
            if mode == "extra":
                obj["PRIVATE"] = True
            else:
                del obj["state"]
            with self.assertRaises(ValueError):
                validate(wire(data), SHA, "x64")

def test_v2_required_runtime_arguments_old_versions_and_wrong_supported_runtime(self):
    m = module()
    good = wire(receipt())
    try:
        accepted = validate(good, SHA, "x64")
    except ValueError:
        self.fail("runtime contract requires an accepted complete v2 positive control first")
    self.assertEqual(accepted, receipt())
    with self.assertRaises(TypeError):
        m.validate_wire(good, SHA, "x64")
    for python, windows in (([3, 12], [10, 0, 123]), ([3, 11], [10, 0, 124]),
                            ([3, True], [10, 0, 123]), ((3, 11), [10, 0, 123]),
                            ([3, 11], [10, 0, True]), ([3, 11], [10, 0, -1])):
        with self.subTest(python=python, windows=windows), self.assertRaises(ValueError):
            m.validate_wire(good, SHA, "x64", expected_python=python, expected_windows=windows)
    for version in (0, 1, 3, True, 2.0):
        data = receipt()
        data["schema_version"] = version
        with self.assertRaises(ValueError):
            validate(wire(data), SHA, "x64")
    # A genuine historical v1 shape must not be upgraded by defaults.
    old = receipt()
    old["schema_version"] = 1
    for resource in old["resources"]:
        for node in resource["chain"]:
            for key in ("structural_roles", "dacl_protected", "inheritance_to_next"):
                del node[key]
            for entry in node["entries"]:
                del entry["direct_operation_candidates"]
    with self.assertRaises(ValueError):
        validate(wire(old), SHA, "x64")
```

- [ ] Step 2：在上述脚手架完成、Step4目标行为未实现时运行两个明确方法RED，预期2 tests/2 assertion failures/0 errors/0 skip，消息为有效v2未被接受。缺validate/receipt/import/必需kwargs接口导致的ERROR须先修脚手架，不算有效RED；不能先实现v2再回写RED记录。实施者不得用跳过规避RED。

```bash
PYTHONPATH=src .venv/bin/python -B -m unittest tests.test_windows_installed_chain.InstalledWireTests.test_v2_derived_fields_and_edge_exact_types_are_recomputed tests.test_windows_installed_chain.InstalledWireTests.test_v2_required_runtime_arguments_old_versions_and_wrong_supported_runtime -v
```

- [ ] Step 3：这里给出前置脚手架使用的完整独立测试侧enrich helper与validate wrapper（执行顺序在Step1/2之前，不重复安装）。保持原字段/资源顺序，schema=2，调用enrich_receipt后返回。既有测试validator正负控改用wrapper；Task2 Step1 mandatory-parameter直接调用不改。真实probe receipt自消费期望用模拟父已知 `[sys.version_info.major,sys.version_info.minor]` 和 `[10,0,123]`，不能误套固定3.11。具体真实probe回执断言替换如下：

```python
self.assertEqual(module().validate_wire(encoded, SHA, "x64",
                 expected_python=[sys.version_info.major, sys.version_info.minor],
                 expected_windows=[10, 0, 123]), data)
```

对应测试模块顶部增加 `import sys`；其现有copy/json/descriptor/acl/ace/sid/module/SHA均已实际存在，不新增伪API。

```python
def enrich_receipt(data):
    for resource in data["resources"]:
        chain = resource["chain"]
        for i, node in enumerate(chain):
            count = len(chain)
            node["structural_roles"] = (["route_ancestor"] if i < count - 1 else []) + (["volume_root"] if i == 0 else []) + (["image_parent"] if i == count - 2 else []) + (["image_leaf"] if i == count - 1 else [])
            node["dacl_protected"] = False
            for entry in node["entries"]:
                choices = [(2, "add_file" if node["directory"] else "write_data"), (4, "add_subdirectory" if node["directory"] else "append_data")]
                if node["directory"]:
                    choices.append((0x40, "delete_child"))
                choices += [(0x10, "write_ea"), (0x100, "write_attributes"), (0x10000, "delete_object"), (0x40000, "write_dacl"), (0x80000, "write_owner"), (0x40000000, "generic_write"), (0x10000000, "generic_all")]
                entry["direct_operation_candidates"] = [name for bit, name in choices if entry["mutation"] & bit] if entry["allowed"] and not entry["flags"] & 8 else []
        for i, node in enumerate(chain):
            if i == len(chain) - 1:
                node["inheritance_to_next"] = None
            else:
                child = chain[i + 1]
                indices = [j for j, entry in enumerate(node["entries"]) if entry["flags"] & (2 if child["directory"] else 1)]
                node["inheritance_to_next"] = {"next_index": i + 1, "target_kind": "directory" if child["directory"] else "file", "child_dacl_protected": False, "flag_candidate_indices": indices, "state": "flag_candidates_child_unprotected" if indices else "no_flag_candidates"}
    return data


def validate(value, source, arch):
    return module().validate_wire(value, source, arch, expected_python=[3, 11], expected_windows=[10, 0, 123])
```

`receipt` 完整替换代码（保留原独立trust enum与purepolicy正控）：

```python
def receipt():
    node = {"index": 0, "kind": "root", "directory": True,
            "metadata_observed_equal": True, "descriptor_observed_equal": True,
            "parser_result": "supported", "policy_result": "pass", "owner": "admin",
            "entries": [{"allowed": True, "flags": 0, "mutation": 2, "trustee": "admin"}]}
    last = dict(copy.deepcopy(node), index=1, kind="file", directory=False)
    resources = [{"resource": name, "role": "source", "image_sha256": "b" * 64,
                  "chain": copy.deepcopy([node, last]), "owned_handles": 2,
                  "confirmed_closes": 2, "unconfirmed_closes": 0}
                 for name in ("helper", "verifier")]
    data = {"schema_version": 2, "scope": "installed_source_chain_observation",
            "source_sha": SHA, "architecture": "x64", "python": [3, 11],
            "windows": [10, 0, 123], "observation_complete": True,
            "source_policy_all_passed": True, "protected_observed": False,
            "compatibility_accepted": False, "launch_authorized": False,
            "resources": resources}
    return enrich_receipt(data)
```

完整同步规则：原 `test_chain32_33_and_ace512_514_wire_budgets` 重建chain/entries后调用 enrich；原 policy 测试替换 entries 后调用 enrich；只在建立有效 fixture阶段 enrich，不在故意篡改后 enrich，否则会消除负控。原 schema 的 `1` byte needles 全部更新为 `2`（重复/NaN/float等负控仍真实命中），`test_semantic_negative_matrix_and_expected_arguments` 的“未知版本2”改为3。新增 top bool/edge精确类型、缺字段/额外字段由新测试覆盖，原每层类型/私有输出/预算负控保留。

- [ ] Step 4：probe 的 schema 精确升为2；键常量增加如下，原 top/resource/owner/trustee枚举不变。

```python
_NODE_KEYS = {"index", "kind", "directory", "metadata_observed_equal", "descriptor_observed_equal",
              "parser_result", "policy_result", "owner", "entries", "structural_roles",
              "dacl_protected", "inheritance_to_next"}
_ENTRY_KEYS = {"allowed", "flags", "mutation", "trustee", "direct_operation_candidates"}
_EDGE_KEYS = {"next_index", "target_kind", "child_dacl_protected", "flag_candidate_indices", "state"}
```

validator 新签名与 runtime段替换为以下完整代码；保留原整体 try/except 固定错误/无私有 cause、canonical wire及预算检查。

```python
def _runtime(value, *, python):
    _require(type(value) is list and len(value) == (2 if python else 3))
    if python:
        _exact_int(value[0], 3, 3)
        _exact_int(value[1], 11, 12)
    else:
        for component in value:
            _exact_int(component, 0, 2**32 - 1)
```

签名为 `def validate_wire(wire, source_sha, arch, *, expected_python, expected_windows):`。在原 try 首部（读取 wire 前）加入：

```python
_runtime(expected_python, python=True)
_runtime(expected_windows, python=False)
```

schema行替为 `_exact_int(data["schema_version"], 2, 2)`；原 python/windows段整体替为：

```python
_runtime(data["python"], python=True)
_runtime(data["windows"], python=False)
_require(data["python"] == expected_python and data["windows"] == expected_windows)
```

在每 node 完成原 directory/kind/metadata/parser 检查后加入：

```python
roles = node["structural_roles"]
_require(type(roles) is list and all(type(role) is str for role in roles))
_require(roles == _structural_roles(index, len(chain)))
_require(type(node["dacl_protected"]) is bool)
```

在每 entry 原 flags/mutation/trustee全部检查之后加入：

```python
direct = entry["direct_operation_candidates"]
_require(type(direct) is list and all(type(candidate) is str for candidate in direct))
_require(direct == _direct_candidates(entry, node["directory"]))
```

在该 resource 的完整 nodes/entries/policy first pass结束后、离开 resource循环前加入以下 second pass。不提前引用尚未验证的child；不通过 dict相等让 bool=int 穿透。

```python
for index, node in enumerate(chain):
    edge = node["inheritance_to_next"]
    expected_edge = _inheritance_edge(chain, index)
    if expected_edge is None:
        _require(edge is None)
        continue
    _object(edge, _EDGE_KEYS)
    _exact_int(edge["next_index"], index + 1, index + 1)
    _finite_string(edge["target_kind"], {expected_edge["target_kind"]})
    _require(type(edge["child_dacl_protected"]) is bool)
    _require(edge["child_dacl_protected"] is expected_edge["child_dacl_protected"])
    indices = edge["flag_candidate_indices"]
    _require(type(indices) is list and len(indices) <= len(node["entries"]))
    for candidate in indices:
        _exact_int(candidate, 0, len(node["entries"]) - 1)
    _require(indices == expected_edge["flag_candidate_indices"])
    _finite_string(edge["state"], {expected_edge["state"]})
```

CLI 自校验只用本次实际采集版本，不授父独立绑定信用：

```python
validate_wire(wire, args.source_sha, data["architecture"],
              expected_python=data["python"], expected_windows=data["windows"])
```

- [ ] Step 5：精确 GREEN 两个新增方法，然后 `PYTHONPATH=src .venv/bin/python -B -m unittest tests.test_windows_installed_chain -v`，预期46实际命中/0 skip/F/E；记录逐方法ID。512双快照/输出256 ACE、32 nodes/resource、wire含唯一尾LF/CRLF 256KiB正负控仍通过，不能扩预算容纳新字段。

## Task 3：父独立 runtime、raw监督与 signed顺序保留

**状态**

- [x] 任务完成（独立父版本接线与便携回归；原生四格仍待验）

**Dependencies:** Task 2
**Parallelizable:** No（父期望必须消费冻结 v2）

- [ ] Step 1：在 required `InstalledSourceCaptureTests` 增加一个方法，明确调用 chain observer，复用该类已有捕获/版本工具但不借 source wire。

实际全文核过本文件顶部已有 `import sys`、`import io`、`from types import SimpleNamespace`、`from contextlib import redirect_stdout`、`from unittest.mock import patch`、`from scripts import run_windows_wheel_ci as wheel_ci` 和 `from tests.test_windows_installed_chain import receipt, wire`；不是类内局部导入。保留这些真实顶部imports，Task2已先安装有效v2 receipt，不再额外新增名字。Task3先取得明确的父调用合同断言RED：直接mock validator返回有效有限data，检查真实父observer提供的call.args/call.kwargs；旧父不传expected kwargs应产生assertion FAIL，不经过TypeError/RuntimeError转换。父接线GREEN后，恢复真实validator进行有效receipt接受及supported-range错runtime拒绝的独立行为验收，不声称这些行为已取得历史RED。

```python
def test_chain_runtime_is_parent_bound_and_three_authorities_false(self):
    version = SimpleNamespace(major=10, minor=0, build=26100)
    expected_python = [sys.version_info.major, sys.version_info.minor]
    contract_data = receipt()
    contract_data.update(python=expected_python, windows=[10, 0, 26100])
    contract_wire = wire(contract_data)
    # This mock isolates the parent call contract. It grants no wire-validation credit.
    with patch.object(wheel_ci.sys, "getwindowsversion", return_value=version, create=True), patch.object(wheel_ci, "_run_unittest_with_bounded_output", return_value=(0, contract_wire, b"")), patch.object(wheel_ci, "validate_wire", return_value=contract_data) as validator, redirect_stdout(io.StringIO()):
        wheel_ci._observe_installed_chain(Path("python.exe"), "a" * 40, "x64", cwd=Path("work"), env={})
    validator.assert_called_once()
    self.assertEqual(validator.call_args.args, (contract_wire, "a" * 40, "x64"))
    self.assertEqual(validator.call_args.kwargs,
                     {"expected_python": expected_python, "expected_windows": [10, 0, 26100]},
                     "parent must supply runtime expectations captured independently of child wire")
    # After the contract passes, use the real validator for separate behavior acceptance.
    for field, value in ((None, None), ("python", [3, 12] if expected_python[1] == 11 else [3, 11]),
                         ("windows", [10, 0, 26200]), ("windows", [10, 1, 26100])):
        data = receipt()
        data.update(python=expected_python, windows=[10, 0, 26100])
        if field is not None:
            data[field] = value
        output = io.StringIO()
        with self.subTest(field=field), patch.object(wheel_ci.sys, "getwindowsversion", return_value=version, create=True), patch.object(wheel_ci, "_run_unittest_with_bounded_output", return_value=(0, wire(data), b"")) as run, redirect_stdout(output):
            if field is None:
                wheel_ci._observe_installed_chain(Path("python.exe"), "a" * 40, "x64", cwd=Path("work"), env={})
                self.assertEqual(output.getvalue(), wire(data).decode("ascii") + "installed-chain observation_complete=true compatibility_accepted=false launch_authorized=false protected_observed=false\n")
            else:
                with self.assertRaisesRegex(RuntimeError, "^installed chain observation failed$") as caught:
                    wheel_ci._observe_installed_chain(Path("python.exe"), "a" * 40, "x64", cwd=Path("work"), env={})
                self.assertIsNone(caught.exception.__cause__)
                self.assertTrue(caught.exception.__suppress_context__)
                self.assertEqual(output.getvalue(), "")
            self.assertEqual(run.call_count, 1)
```

- [ ] Step 2：运行 `PYTHONPATH=src .venv/bin/python -B -m unittest tests.test_windows_bootstrap_binding.InstalledSourceCaptureTests.test_chain_runtime_is_parent_bound_and_three_authorities_false -v` RED；预期1test/调用合同assertion FAIL/0ERROR/0skip，失败位是validator.call_args.kwargs的空dict与父独立expected runtime不等。mock validator接受旧父位置参数，不产生mandatory kwargs TypeError；没有异常转换。此窗口只证明父接线缺失，真实validator行为矩阵尚未到达，不授runtime错值拒绝/有效v2消费信用，也不在取得调用合同RED前实现父绑定。

- [ ] Step 3：在 `_observe_installed_chain` 原 try 内、capture前加入父已知版本；原 validate调用与摘要替为：

```python
expected_python = [sys.version_info.major, sys.version_info.minor]
version = sys.getwindowsversion()
expected_windows = [version.major, version.minor, version.build]
```

```python
data = validate_wire(stdout, source_sha, arch,
                     expected_python=expected_python, expected_windows=expected_windows)
print(json.dumps(data, separators=(",", ":")))
print("installed-chain observation_complete=true compatibility_accepted=false launch_authorized=false protected_observed=false")
```

exact tuple/bytes/code/stderr、timeout30、256KiB、无重试、无replacement/私有输出以及main signed阶段顺序保持。

- [ ] Step 4：同步旧 optional类实际四个chain方法：所有 observer调用所在 patch上下文加当前父 `getwindowsversion` `[10,0,123]`；正控receipt的 `python`设父当前major/minor。其 schema byte needles1→2、成功摘要追加protected_observed=false。main `raw_query` 的 chain返回改为以下块（相邻main外层已经patch OS26100）：

```python
data = receipt()
data["python"] = [sys.version_info.major, sys.version_info.minor]
data["windows"] = [10, 0, 26100]
return (0, wire(data), b"")
```

- [ ] Step 5：运行新增方法GREEN，分别记录mock调用合同已通过及恢复真实validator后有效v2接受、supported-range错runtime拒绝、三个false摘要独立行为验收通过；不把后者写成已有历史RED。然后如下精确调用；required类6全命中无skip；optional类的旧raw shape、unknowncapture、stderr、私有wire、超时/限制/unknowncleanup、main signed失败不export与原顺序负控全部保留，不运行host compiler作Windows信用。

```bash
PYTHONPATH=src .venv/bin/python -B -m unittest tests.test_windows_bootstrap_binding.InstalledSourceCaptureTests tests.test_windows_bootstrap_binding.TestWindowsBootstrapBinding -v
```

## Task 4：自有 Windows native正负控与required计数

**状态**

- [x] 任务完成（软件、夹具实现及静态选择；Windows 原生实际结果仍待四格）

**Dependencies:** Task 1, Task 2, Task 3
**Parallelizable:** No（实机须消费最终软件；计数按最终方法集冻结）

- [ ] Step 1：在实际 `WindowsSecurityQueryTests` 增加以下唯一方法。只更改已有fixture创建的 `self.file`；先close该fixture旧HANDLE，再准备ACL，关闭配置writer后fresh probe自己完整持有/双读/释放。复用既有test-only `_Native` 的WRITE_DAC|READ_CONTROL/fullshare7与SetSecurityInfo ABI、`_ConvertedDacl` owned非NULL DACL和一次LocalFree/Close；security_information分别为DACL|PROTECTED=`0x80000004`、DACL|UNPROTECTED=`0x20000004`，每状态实际读回control后关writer。旧 `_ConvertedDacl` 构造SDDL含P，但输出调用由security_information明确设置on/off；不是复用旧 `set_marker` 当通用on/off。没有owner写、系统ACL写、新生产nativeAPI或PATH/环境变量定位命令。不支持SD/权限/close/未知fixture均fail，不skip，不输出路径/ACL/body私有文本。继承可能改变ACE和metadata，每状态重新baseline，不称control-only因果实验。

```python
def test_owned_file_protected_on_off_matches_actual_chain_descriptor(self):
    from pathlib import PureWindowsPath
    from icode.windows_startup_host_identity import WindowsStartupHostIdentity
    from icode.windows_startup_security import parse_startup_security
    from icode.windows_startup_security_native import WindowsStartupSecurityReader
    from tests.windows_private_dacl_fixture import _Native, _ConvertedDacl, _close_all
    from scripts import probe_windows_installed_chain as probe
    self.close_handles()
    identity = WindowsStartupHostIdentity()
    host_sid = identity.capture()
    self.assertIs(identity.cleanup_unconfirmed, False)
    api = _Native()
    for information, protected in ((0x80000004, True), (0x20000004, False)):
        writer, code = api.open(str(self.file), False)
        self.assertEqual(code, 0, "owned fixture configuration open failed")
        self.assertIsNotNone(writer)
        converted = _ConvertedDacl(api)
        try:
            dacl = converted.acquire(host_sid, 0x80)
            status = api.call(api.advapi.SetSecurityInfo, writer.value, 1, information,
                              None, None, dacl, None)
            self.assertIs(type(status), int)
            self.assertEqual(status, 0, "owned fixture DACL configuration failed")
            reader = WindowsStartupSecurityReader()
            configured = parse_startup_security(reader.read(writer.value))
            self.assertIs(reader.cleanup_unconfirmed, False)
            self.assertIs(bool(configured.control & 0x1000), protected)
        finally:
            _close_all([converted, writer])
        # A separate actual backend reads the same owned object's SD twice.
        backend = probe.WindowsStartupPinBackend()
        owned = []
        try:
            handle = backend.open_root(self.file.drive)
            owned.append(handle)
            for part in self.file.parts[1:-1]:
                handle = backend.open_child(handle, part, directory=True)
                owned.append(handle)
            handle = backend.open_child(handle, self.file.name, directory=False)
            owned.append(handle)
            before = backend.query(handle)
            first = backend.query_security(handle)
            second = backend.query_security(handle)
            self.assertEqual(first, second)
            snapshot = parse_startup_security(first)
            self.assertIs(bool(snapshot.control & 0x1000), protected)
            self.assertEqual(backend.query(handle), before)
            self.assertEqual(backend.read(handle, 0, len(self.content)), self.content)
        finally:
            errors = []
            for handle in reversed(owned):
                try:
                    backend.close(handle)
                except BaseException as error:
                    errors.append(error)
            if errors:
                raise errors[0]
        observed = probe._observe_resource("helper", PureWindowsPath(str(self.file)), host_sid, [0])
        chain = observed["chain"]
        self.assertIn("dacl_protected", chain[-1],
                      "actual held leaf observation must emit the descriptor protected bit")
        self.assertIn("inheritance_to_next", chain[-2],
                      "actual held parent observation must emit its single child edge")
        self.assertIs(chain[-1]["dacl_protected"], protected)
        edge = chain[-2]["inheritance_to_next"]
        self.assertIs(edge["child_dacl_protected"], protected)
        candidates = [i for i, entry in enumerate(chain[-2]["entries"]) if entry["flags"] & 1]
        self.assertTrue(candidates, "owned parent must expose actual OI candidates")
        self.assertEqual(edge["flag_candidate_indices"], candidates)
        self.assertEqual(edge["state"], "flag_candidates_child_protected" if protected else "flag_candidates_child_unprotected")
        self.assertEqual(observed["owned_handles"], len(chain))
        self.assertEqual(observed["confirmed_closes"], len(chain))
        self.assertEqual(observed["unconfirmed_closes"], 0)
```

Linux不能执行此native方法获取信用。native RED采用Task4 Step4完整workflow资产，在四个实际Windows签装格分别读取固定历史producer并执行新增单native方法；预期1 test/1目标assertion FAIL/0 ERROR/0skip，因历史producer未输出actual protected字段，assertIn阻止KeyError。该证据明确称“固定历史producer行为RED”，不声称当前实施前已在Windows取得RED。配置/API/SD/close/cleanup等错误或其它assertion失败须blocking，不能重标目标RED或skip。恢复当前模块后69必需方法取得GREEN，含该native类全部3方法；历史RED不计入当前69 GREEN数量。fixture teardown由原addCleanup反向关闭和temp删除完成；不改默认目录要求flags的既有方法，不把旧_stable的identity/bytes局部检查当完整metadata一致。每次历史/当前运行均配置后freshbackend取得独立baseline；Windowsbackend与actual SD/native API不mock。

- [ ] Step 2：精确同步 `tests/test_windows_startup_pin_ci.py`：PORTABLE_COUNTS中chain observation13→16、wire9→11、sourcecapture5→6；NATIVE_COUNTS第二项2→3；module chain41→46；`test_real_class_and_module_loader_cannot_hide_required_skip` sourcecapture count5→6。其它计数及 optional binding类skip测试不变。无需新selector；现有 native/security 与required前缀已覆盖。

```python
NATIVE_COUNTS = (6, 3, 2, 2, 2)
PORTABLE_COUNTS = (1, 32, 30, 3, 2, 24, 17, 2, 2, 16, 1, 4, 32, 7, 1, 16, 7, 11, 4, 3, 3, 18,
                   1, 6, 21, 5, 6, 5, 11, 3, 13, 18)
```

- [ ] Step 3：执行portable required guard（Linux/Windows都须真实命中）与Windowsnative明确命令；先记录未同步计数时真实FAIL，再同步GREEN。只按实际平台运行，不patch os.name假装Windows，不降低requiredskip。

```bash
PYTHONPATH=src .venv/bin/python -B -m unittest tests.test_windows_startup_pin_ci -v
```

```powershell
$env:PYTHONPATH = 'src'
python -B -m unittest tests.test_windows_startup_native.WindowsSecurityQueryTests -v
python -B -c "from scripts.run_workspace_ci import main; raise SystemExit(main(('tests.test_windows_installed_chain', 'tests.test_windows_bootstrap_binding.InstalledSourceCaptureTests', 'tests.test_windows_startup_native.WindowsSecurityQueryTests', 'tests.test_windows_startup_pin_ci')))"
```

明确命中：chain46、requiredcapture6、nativequery3、guard14，共69；guard14由当前文件实际14个test方法文本核实，实施后不得增加未记录方法。所有必需方法/fixture/subTest skip仍exit1，重复/缺方法仍失败，native默认完整selector仅在nt包含，Linuxportable排除native而不授native。

- [ ] Step 4：签装 `sign` 矩阵当前没有执行该nativequery类，不能借独立workspace命中替四签装hit。在 `.github/workflows/windows-helper-provenance.yml` 的sign job setup-python之后、最终attest之前增加下列一个完整step，所有四格同一checkout实际执行。checkout的sign-job `with` 仅补 `fetch-depth: 0`，保留persist-credentials:false/submodules:recursive和已有actionpin，保证固定历史Git对象本地可读；没有新网络权限、checkout切换、新branch或Git写。若当前checkout已含目标对象则直接本地show；历史对象/摘要/目标FAIL校验任一失败blocking。现有required前缀识别class/module方法与fixture/subTest skip；无额外运行时权限/依赖/hostcompiler，不改变OIDC/签名/发布条件。

历史producer固定commit `1e2e4ab5d0101acf00d609af37add9893e4c57ef`，blob路径 `scripts/probe_windows_installed_chain.py`，本轮只读Git show实际SHA-256为 `19a9c21e204d04675e3d2c46f410afc0d4836add11843d387cf960cc3a6a2b21`。workflow中再次核原始bytes摘要，不能只相信固定commit字符串。脚本嵌入PowerShell here-string，传给python -B -，不新建脚本或扩源码范围。

```yaml
- name: Require chain role diagnostic methods on this Windows signing cell
  shell: pwsh
  env:
    PYTHONPATH: src
  run: |
    @'
    import hashlib
    import os
    from pathlib import Path
    from types import ModuleType
    import unittest
    from unittest.mock import patch
    import scripts
    from scripts import probe_windows_installed_chain as current
    from scripts.run_workspace_ci import main
    from tests.test_windows_startup_pin_ci import cases
    from icode.runner import _run_unittest_with_bounded_output

    def require(condition):
        if not condition:
            raise RuntimeError('historical_chain_role_red_failed')

    class HistoricalResult(unittest.TestResult):
        def __init__(self):
            super().__init__()
            self.target_failures = []

        def addFailure(self, test, error):
            message = error[1].args[0] if type(error[1]) is AssertionError and len(error[1].args) == 1 else None
            self.target_failures.append(
                test.id() == target and type(message) is str
                and message.startswith("'dacl_protected' not found in ")
                and message.endswith(' : actual held leaf observation must emit the descriptor protected bit'))
            super().addFailure(test, error)

    target = 'tests.test_windows_startup_native.WindowsSecurityQueryTests.test_owned_file_protected_on_off_matches_actual_chain_descriptor'
    source_ref = '1e2e4ab5d0101acf00d609af37add9893e4c57ef:scripts/probe_windows_installed_chain.py'
    source_hash = '19a9c21e204d04675e3d2c46f410afc0d4836add11843d387cf960cc3a6a2b21'
    try:
        require(os.name == 'nt')
        captured = _run_unittest_with_bounded_output(
            ['git', 'show', source_ref], workspace=Path.cwd(), timeout=10,
            output_limit_bytes=256 * 1024, environment=os.environ.copy())
        require(type(captured) is tuple and len(captured) == 3)
        code, raw, errors = captured
        require(type(code) is int and code == 0 and type(raw) is bytes
                and type(errors) is bytes and not errors)
        require(hashlib.sha256(raw).hexdigest() == source_hash)
        historical = ModuleType('scripts._historical_chain_role_producer')
        historical.__file__ = source_ref
        historical.__package__ = 'scripts'
        exec(compile(raw, source_ref, 'exec'), historical.__dict__)
        suite = unittest.defaultTestLoader.loadTestsFromName(target)
        require(suite.countTestCases() == 1)
        result = HistoricalResult()
        # Only the from-scripts producer attribute changes. Native backend/SD stay real.
        with patch.object(scripts, 'probe_windows_installed_chain', historical):
            suite.run(result)
        require(scripts.probe_windows_installed_chain is current)
        require(result.testsRun == 1 and len(result.failures) == 1
                and result.target_failures == [True] and not result.errors
                and not result.skipped and not result.unexpectedSuccesses)
    except BaseException:
        raise SystemExit('historical_chain_role_red_failed') from None
    print('historical-chain-role-red commit=1e2e4ab5d0101acf00d609af37add9893e4c57ef tests=1 failures=1 errors=0 skips=0 target=missing_dacl_protected')
    selections = ('tests.test_windows_installed_chain',
                  'tests.test_windows_bootstrap_binding.InstalledSourceCaptureTests',
                  'tests.test_windows_startup_native.WindowsSecurityQueryTests',
                  'tests.test_windows_startup_pin_ci')
    suites = [unittest.defaultTestLoader.loadTestsFromName(name) for name in selections]
    require(tuple(suite.countTestCases() for suite in suites) == (46, 6, 3, 14))
    ids = [case.id() for suite in suites for case in cases(suite)]
    require(len(ids) == 69 and len(set(ids)) == 69)
    for test_id in ids:
        print('chain-role-required-id=' + test_id)
    raise SystemExit(main(selections))
    '@ | python -B -
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

修改前对照Task4已有nativeclass/requiredskip守护，失败先由计数/方法测试观察；增加step后软件检查workflow语法、固定matrix/历史commit/hash/requiredselection原文，并在四签装原logs分别核固定历史producer RED汇总、69个唯一当前ID及当前实际69run/0skip/F/E。历史RED只接受缺dacl_protected的那个assertion，环境API/ACL/cleanup其它failure、errors、skips均拒绝；完整trace/raw Git/私有异常不打印。loader严格计数拒绝0suite/缺类/缺方法/重复选择；恢复module后现有main真实执行并将任意必需body/fixture/subTest skip提升exit1，打印选择ID不能单独授命中。PYTHONPATH=src历史/当前自有temp nativefixture信用与随后-I installed-v2消费信用分开，各格均须实际通过。若现有guard完整类运行超时，报告真实成本，不删/skip guard绕门或延长预算掩盖，返回计划收敛测试选择。

## Task 5：软件完整门、独立评审与同 SHA 四格安装

**状态**

- [ ] 任务完成

**Dependencies:** Task 1, Task 2, Task 3, Task 4
**Parallelizable:** No（必须对最终冻结候选验收；四Windows格可由现有CI矩阵并发）

- [ ] Step 1：对本片最终所有实际修改文件作只读引用/契约与语法检查，确认生产security/pin/native/source/consumer/readiness无diff；`rg -n 'validate_wire\(' scripts/probe_windows_installed_chain.py scripts/run_windows_wheel_ci.py tests/test_windows_installed_chain.py tests/test_windows_bootstrap_binding.py` 每处绑定必需参数，测试wrapper故意缺参仅用于TypeError负控。预算保持32/512/256KiB/30s，枚举与exact keys与DESIGN逐行对应；完整全仓搜索新字段/旧schema引用防改漏。

- [ ] Step 2：执行相关portable suite及workspace必需选择；保存实际逐ID命中，不只exit0。实际CLI/receipt、父main signed顺序、原parser/control/IO/source policy、nativeABI/LocalFree/unknownclose/backendreuse负控一并验收。

```bash
PYTHONPATH=src .venv/bin/python -B -m unittest tests.test_windows_installed_chain tests.test_windows_bootstrap_binding.InstalledSourceCaptureTests tests.test_windows_bootstrap_binding.TestWindowsBootstrapBinding tests.test_windows_startup_security tests.test_windows_startup_security_native tests.test_windows_startup_pin_ci -v
```

- [ ] Step 3：root只运行一次项目原完整preflight门及固定vendor合同，不另默认执行全仓discover或workspace全量造成重复。Step2仅相关suite/requiredskip回归；独立CI的平台验收另记来源。精确命令：

```bash
.venv/bin/python -B scripts/preflight.py
.venv/bin/python -B scripts/check_governance.py
```

ICODE-SKILL契约由原preflight的固定vendor检查取得实际结果；如preflight没有覆盖当前应执行的skill合同，按固定 `vendor/icode-skill` 已有入口补核，先完整读入口再执行，不凭过往1002/69数据补本次信用。不得读取KEY、擅自同步vendor、提交、推送或触发发布。

- [ ] Step 4：阶段结束复用本次固定研究条目，记录采纳/暂缓/不适配与实际验证结果；fresh独立SPEC审查最终实现，随后不同QUALITY，处理真实问题并再验受影响项。root全文阅读最终所有相关文件并完整验收；不把子代理输出、自检或计划代码块当执行证据。评审可独立，实施任务按本计划serial；不得以评审取代Windowsnative。

- [ ] Step 5：经已授权的后续发布步骤取得**同一最终 SHA** x64/ARM64 × CPython3.11/3.12 四Windowsworkspace和四签装。复用现有 `.github/workflows/windows-helper-provenance.yml` 的sign矩阵、实际build/attest与完整参数：脚本接收native-helper、provenance-bundle、provenance-verifier、provenance-notices、wheel-output；值严格取现有workflow `Join-Path RUNNER_TEMP` 和attest实际bundle输出，不手填示例路径。本PLAN不申请/执行Git写或签名权限。Task4 requiredstep在四格签装实际hit；保留原签装执行顺序：gh installed proof → helper绑定实际verifier bytes → installed offline verifier正负控 → directvolume → chain v2 → source observer → bootstrap metadata/拒绝 → export。未通过任意阶段不export。

四格每格提交实际ID/无新增隐skip、独立父版本、v2canonicalwire、同SHA/arch、两资源账本（owned=confirmed，unknown=0）、全局doubleSD ACE≤512、三authority=false。root和另一独立观察者各用父独立SHA/arch/版本调用最终validator核四份原始wire；版本期望不得从该wire取值。四份wire只能声明观察；若root仍owner_untrusted，保留该位置/拒绝，不能提前宣告根兼容。

四格验收的独立validator实际调用形式（值从各job独立runner版本与最终候选台账获取，不能使用下面固定fixture值冒充原生）：`validate_wire(raw_wire, final_source_sha, fixed_arch, expected_python=parent_python, expected_windows=parent_windows)`。变量由观察者证据读取产生；不新增校验API、不把计划里的变量当已完成数据。

- [ ] Step 6：分账交付软件、nativefixture、installed四格、完整项目门。继续保留Reviewer/WFP unknown、UAC、pre-mainDLL/publisher、公共生产consume与R2/R3未完成边界。任何新准入策略、allowowners、系统ACL写、AccessCheck、生产API或ready放宽需求均返回新设计。

## 验收映射与风险

| DESIGN要求 | 实施/验收位置 |
| --- | --- |
| n=2角色并集/中间route/leaf分离/控制位真实读取 | Task1三个真实descriptor方法；Task4实际Windows对象 |
| allowed非IO直接候选、deny/IO不抵消原policy、目录位 | Task1 direct方法与原policy suite；生产mask及_receipt_policy不改 |
| OI/CI/NP/IO/INHERITED、实际下一node/control、父protected不代子 | Task1 edge方法；Task2二阶段validator；Task4原生on/off |
| exactfields/list/order/indices/bool-int、v1/unknownversion/runtime | Task2两个新增方法及旧每层/duplicate/canonical负控；Task3父runtime |
| 32/33、512/514、256KiB含尾行正负控 | 原observation/probe/wire三个预算方法更新有效v2fixture保留 |
| SD/metadata/parser/IO/closeunknown失败、两backend同数字ledger | 原Observation/Probe测试全部运行；Task3 rawcapture与原main顺序 |
| required方法/fixture/subTest skip与实际hit | Task4计数同步；原StartupPinCiTests全部守护；Task5四格 |
| installed同SHA/签装runtime独立核验/三个false | Task5原workflow实际四格，root+独立观察者原wire各核 |

研究复用[持续竞品对照](../../agent-landscape-live.md)本轮Windows角色记录。MicrosoftDocs/win32 `ca8274decead49403d70ceeed4af8d4ca74eaf11` 的 [file access constants](https://github.com/MicrosoftDocs/win32/blob/ca8274decead49403d70ceeed4af8d4ca74eaf11/desktop-src/FileIO/file-access-rights-constants.md) 与 [descriptor control](https://github.com/MicrosoftDocs/win32/blob/ca8274decead49403d70ceeed4af8d4ca74eaf11/desktop-src/SecAuthZ/security-descriptor-control.md)（文档2018-05-31，观察2026-10-12）；root已实际读该固定 [LICENSE](https://github.com/MicrosoftDocs/win32/blob/ca8274decead49403d70ceeed4af8d4ca74eaf11/LICENSE)，CC-BY-4.0。固定Codex8c0f701的Apache-2.0职责分离只作为已有研究依据。不复制上游源码/原文、不重新刷新二十HEAD、不增加运行时依赖或权限。

本轮独立只读夹具研究追加：固定MicrosoftDocs/sdk-api `656e9656bfaef34dd29cd7ee9e1146aec17e924c` [SetSecurityInfo](https://github.com/MicrosoftDocs/sdk-api/blob/656e9656bfaef34dd29cd7ee9e1146aec17e924c/sdk-api-src/content/aclapi/nf-aclapi-setsecurityinfo.md) 的非NULL DACL/继承传播/分享窗口机制采纳为配置前关闭与freshbaseline；两种security_information实际on/off均需Windows读回。MicrosoftDocs/windowsserverdocs `b30da775fdeb9df0c446fda330fd0f101422edbe` [icacls](https://github.com/MicrosoftDocs/windowsserverdocs/blob/b30da775fdeb9df0c446fda330fd0f101422edbe/WindowsServerDocs/administration/windows-commands/icacls.md) 当前 `/inheritancelevel:e|d|r`（ms.date2025-06-06）暂缓，避免新增命令定位/版本兼容成本，d复制继承ACE不作control-only实验；固定许可研究为CC-BY-4.0，ICODE本地MIT，不复制原文或代码。来源观察为2026-10-12独立研究，不以引用替实际native运行。

**采纳：**有限结构并集/ACE位语义/actual child control/父独立runtime，收益是解释拒绝和防错格回执，成本为v2同步、6portable+1native新增方法及四签装。**暂缓：**rootowner例外、effectiveaccess、生产继承屏障、UAC/加载。**不适配：**新allowowners、protected当安全认证、unknown降pass、诊断替AccessCheck、私有fixture认证未知系统owner。阶段开始与结束刷新相关研究结论，但研究不能替测试或固定ICODE-SKILL合同。

【架构级自检报告】

- ✅ 语法/编译：本轮仅新增Markdown；完整代码块供实施/审查，未运行AST/测试/编译，不称代码已通过。
- ✅ 依赖/调用链：实际probe、父observer、receipt、optional/required测试、selector/skip/count与signedworkflow均核实；原生新增复用实际自有tempfixture。
- ✅ 逻辑/边界：n=2/32/33、directory/leaf、IO与flags分离、两阶段child引用、runtime与预算映射完整；执行结果待实施。
- ✅ 异常处理：原IO/parser/drift/BaseException/close未知与capture固定失败保留，无unknown默认false、重试或私有输出信用。
- ✅ 关联模块：本轮仅本文写入；实施两诊断源码、四测试文件和签装workflow一个requiredstep范围冻结，生产准入/nativeAPI、LinuxTask3、vendor不改。
- ✅ 兼容安全：v1拒绝、v2exactkeys、原sourcepolicy/mask/IO不改、三authority恒false；未授Windowsnative或ready。
- ✅ 可运行性：计划命令与真实入口/fixture对应；本轮PLAN未实施，不能声明100%运行通过；root后续审查与完整验收待办。

---

**Execution Mode:** serial

root全文审查指出的Important已在本PLAN纠正：字段/有效v2测试先完成脚手架再真实assertion FAIL/0ERROR；bootstrap顶部imports已实读确认；完整root gate收敛为一次preflight。fresh SPEC的C0/I1/M0指出Task3接口异常不能冒充runtime行为RED，现修为mock validator下真实父call.kwargs合同assertion RED → 父接线GREEN → real validator有效v2/错runtime独立行为验收，不宣称后者已有历史RED。不同QUALITY的C0/I1/M0指出Ubuntu没有前置Windowsnative窗口，现改为四签装CI固定历史producer行为RED（本地Git show固定commit/hash、独立ModuleType、仅patch from-scripts producer属性、actual Windowsbackend/SD不mock、精确1目标FAIL/0ERROR/0skip）→恢复当前module→69当前GREEN→另核installed-I；不阻塞portable实现，不冒充当前实现前native时间史。本文未运行测试/编译/AST，纠正文档不等于已取得任何RED/GREEN或native结果。

仅计划交付：等待root安排freshPLAN SPEC → 不同QUALITY与全文阅读；不自动调用执行skill或启动源码实施。

后续 root 审查记录：完整797行冻结 `33731dac79813939785835818d0d1103a78d07ebe2860bf316c995c8eca203cb` 已 fresh SPEC→不同 QUALITY C0/I0/M0；root 回读完整资产及修订窗口，普通Python代码块和workflow内嵌Python AST均通过。原生仅有GitHub窗口的实际约束已经写成固定历史producer RED→恢复当前69 GREEN，不声称Ubuntu已执行。当前继续先完成Linux公共消费串行片，Windows本计划尚未实施或取得任何新的实际native/installed信用，不与Linux源writer并行修改。

后续实施开始：Linux公共消费软件候选的原完整preflight三道通过，已提交推送main `1c44aa09f1660929d0b6b8e63bf1952deed6f6e3`，远端仅main；其四Linux新CI独立追踪。Windows fresh Task1 实施者先只读准备、在发布后才获root释放写入，唯一writer仅两限定路径。Task1已取得3 tests / 3目标assertion FAIL / 0 ERROR / 0 skip 的字段缺失RED，正实施最小派生；schema/validator/CLI尚未升级。原生/安装四格仍未取得新信用，不由Linux结果补授。

Task1后续完成：仅两限定文件，私有派生/actual control/完整链后edge追加已GREEN，观察类16/16、0skip；实现者内建SPEC→QUALITY零遗留，root独立读全diff并实际复跑16 tests / 0.039s / OK。该中间版本probe `25eac2f5fa58078d43a238637d3df7ebfe545238e32bc8d9b480cdfaec13288c`、tests `65f95f3bd7bc61c6e7e49152d6933d9d3114651a2d51f09ffc45f2cfd4fe5569`，schema/validator/CLI仍v1按阶段保留，不授完整module/父runtime/native通过。Task2由fresh唯一writer串行继续严格v2及fixture同步。

Task2后续完成：两个新方法以完整有效v2正控取得2目标assertion FAIL、0 ERROR/skip，再最小升级schema、必填期望与二阶段edge验证；实现者完整模块46 tests全通过。root独立完整回读生产探针并实际复跑46 tests / 0.079s / 0 skip / OK。两文件SHA256分别为 `5ea795fd49da8e5161fd7eb926dbcf07510d509db8ec2604f3f6c3670e4d3ae5`、`3587e2d55908762c0846db0b54081f4f7a439ae053355ec9fade71d729bd5a12`。外部父接线/guard尚未同步，未运行全仓preflight，不授Windows原生信用；Task3由fresh唯一writer继续。

Task3后续完成：真实父调用kwargs合同取得1 assertion FAIL、0 ERROR/skip，再接独立父runtime；恢复真实validator另核有效匹配接受及三个支持范围内错版本拒绝，原捕获/隐私/顺序合同保留。root完整核两文件diff并独立执行required6＋optional22＝28 tests / 0.155s / 0 skip / OK。runner SHA256 `2ff75e5eff3bc66779facb552c41dec8d2546a52aadc764254a314d924c383ca`，binding测试 `01f31776cc9e38884c733eb72f6dd3979f16cb98959b6d4e0adcfca8cc469877`。Task4 fresh唯一writer继续原生夹具、严格计数与四签装step；未以便携结果代Windows实际安装或准入信用。

Task4软件后续完成：旧计数守护实际3 tests/6 assertion FAIL/0 ERROR/skip，再同步后14 tests全绿。root独立核三文件diff及历史blob摘要，相关六选择151 tests / 2.443s / 0 skip / OK；loader静态46/6/3/14＝69唯一ID，不称原生执行。workflow内嵌Python AST、系统Python已有YAML解析、治理及compileall-j1/site检查通过；venv缺yaml的首验证命令失败保留，未新增包依赖。native/guard/workflow SHA256分别 `aaa42245565b58b8763b35d24322083200606f6735442ce003fd8d74f5536e61`、`1189265c9de646d957e7bfc0df7d039ac6d09919b392fb919419e12a3af42314`、`51b224139d84e81a953bdbd8a11a69dbc64d895d046fd73a11459a3645b6b2e3`。SOURCE7冻结并进入fresh全局SPEC，再由不同QUALITY审查；完整软件门与最终SHA原生四格仍待，不预授通过。

Task5软件候选门后续实际完成（2026-10-11 23:57 UTC）：最终SOURCE7 fresh SPEC及不同QUALITY均C0/I0/M0，各自66 portable tests/0skip通过，冻结摘要与root一致。root完整核实际生产/父接线/fixture/guard/workflow及调用上下文，相关151 tests全绿；原完整preflight session89204实际exit0，密钥扫描、固定vendor完整性、全量unittest三道通过，仅运行一次原完整门。固定vendor仍 `21566a589cbe98bd35372a04bbb6ca1c51d8eed2` clean，未同步或写子仓库。准备按用户阶段授权发布main；Task5整体状态保留未完成，最终SHA四Windowsworkspace及四签装、native历史RED/当前69 GREEN和v2独立回执仍待实测。

【架构级自检报告】（软件候选，不替代Windows原生或整体R2/R3）

- ✅ 语法/编译：实际compileall-j1、Python AST、workflow YAML通过。
- ✅ 依赖/调用链：probe/CLI/父observer/fixtures/required计数同步，真实引用已核。
- ✅ 逻辑/边界：151相关便携测试、两独立66项及精确类型/预算负控通过。
- ✅ 异常处理：原IO/drift/unknown/一次关闭/固定错误与隐私合同保留。
- ✅ 关联模块：限定7SOURCE一致；原完整软件三道门通过。
- ✅ 兼容安全：v1明确拒绝，旧政策及三authority=false不变，无新权限/依赖。
- ✅ 可运行性：软件候选通过；Windows新增native/installed最终四格未验，不声明100%或ready。
