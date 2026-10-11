"""Real PE bytes, never mocked RVA or directory reads."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
import hashlib
import importlib
import importlib.util
import io
import struct
import unittest

from tests.test_windows_pe_reader import pe_bytes, changed
from scripts.windows_pe_reader import PeFormatError

XML = ('<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">'
       '<trustInfo xmlns="urn:schemas-microsoft-com:asm.v3"><security><requestedPrivileges>'
       '<requestedExecutionLevel level="asInvoker" uiAccess="false"/>'
       '</requestedPrivileges></security></trustInfo></assembly>').encode()


class Fixture:
    """Two independently backed sections: metadata and payload/name tables."""
    def __init__(self, arch="x64", manifests=None, extra=(), *, meta_size=0x6000,
                 payload_size=0x6000, payload_base=0x9000, size_of_image=0x10000):
        self.payload_base = payload_base
        self.payload_file = 0x400 + meta_size
        self.body = bytearray(pe_bytes(arch=arch, directories=((0, 0),) * 14,
                                      sections=((0x1000, meta_size, meta_size, 0x400),
                                                (payload_base, payload_size, payload_size, self.payload_file)),
                                      size_of_image=size_of_image))
        self.meta = 0x1100
        self.payload = payload_base
        self.manifest_data = []
        leaves = [(24, name, lang, raw) for name, lang, raw in
                  ([(1, 1033, XML)] if manifests is None else manifests)] + list(extra)
        tree = {}
        for typ, name, lang, raw in leaves:
            tree.setdefault(typ, {}).setdefault(name, {})[lang] = raw
        self.root = self.resource_node(tree, 0)
        self.directory(2, self.root, self.meta - self.root)

    def offset(self, rva):
        return rva - 0x1000 + 0x400 if rva < self.payload_base else rva - self.payload_base + self.payload_file

    def put(self, rva, raw):
        off = self.offset(rva)
        if off + len(raw) > len(self.body):
            self.body.extend(bytes(off + len(raw) - len(self.body)))
        self.body[off:off + len(raw)] = raw
        return rva

    def pack(self, rva, fmt, *values):
        return self.put(rva, struct.pack(fmt, *values))

    def alloc(self, raw, payload=False):
        attr = "payload" if payload else "meta"
        rva = getattr(self, attr)
        setattr(self, attr, rva + len(raw))
        return self.put(rva, raw)

    def directory(self, index, rva, size):
        struct.pack_into("<II", self.body, 0x98 + 112 + index * 8, rva, size)

    def resource_node(self, node, depth):
        keys = sorted(node, key=lambda k: (isinstance(k, int), str(k)))
        base = self.alloc(bytes(16 + 8 * len(keys)))
        if depth == 0:
            self.root = base
        named = sum(isinstance(k, str) for k in keys)
        self.pack(base, "<IIHHHH", 0, 0, 0, 0, named, len(keys) - named)
        for i, key in enumerate(keys):
            if isinstance(key, str):
                raw = key.encode("utf-16-le")
                name = 0x80000000 | (self.alloc(struct.pack("<H", len(raw)//2) + raw) - self.root)
            else:
                name = key
            value = node[key]
            if depth < 2:
                target = 0x80000000 | (self.resource_node(value, depth + 1) - self.root)
            else:
                rva = self.alloc(value, True) if value else 0
                target_rva = self.alloc(struct.pack("<IIII", rva, len(value), 0, 0))
                target = target_rva - self.root
                if self.root and depth == 2:
                    self.manifest_data.append((target_rva, rva, value))
            self.pack(base + 16 + 8*i, "<II", name, target)
        return base

    def imports(self, *, delay=False, oft=True, symbols=("CreateFileW", 7), dll=b"kernel32.dll", resolver=False):
        name = self.alloc(dll + b"\0", True)
        values = []
        for symbol in symbols:
            values.append((1 << 63) | symbol if isinstance(symbol, int) else
                          self.alloc(b"\0\0" + symbol.encode() + b"\0", True))
        lookup = self.alloc(struct.pack("<" + "Q"*(len(values)+1), *values, 0), True)
        iat_values = [0x140001234]*len(values) if resolver else values
        iat = self.alloc(struct.pack("<" + "Q"*(len(values)+1), *iat_values, 0), True)
        if delay:
            handle = self.alloc(bytes(8), True)
            descriptor = self.alloc(struct.pack("<IIIIIIII", 1, name, handle, iat, lookup, 0, 0, 0) + bytes(32))
            self.directory(13, descriptor, 64)
        else:
            descriptor = self.alloc(struct.pack("<IIIII", lookup if oft else 0, 0, 0, name, iat) + bytes(20))
            self.directory(1, descriptor, 40)
        return descriptor, lookup, iat, name

    def image(self):
        return bytes(self.body)


def valid_pe_bytes(arch="x64"):
    """Reusable complete fixture for capture's actual-byte integration tests."""
    return Fixture(arch).image()


class TestWindowsPeDirectories(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.find_spec("scripts.windows_pe_directories")
        module = importlib.import_module("scripts.windows_pe_directories") if spec else None
        self.inspect = getattr(module, "inspect_directories", None)
        self.assertTrue(callable(self.inspect), "inspect_directories callable is missing")
        self.Error = module.PeDirectoryError

    def reject(self, reason, fixture):
        with self.assertRaises(self.Error) as caught:
            self.inspect(fixture.image(), expected_arch="x64")
        self.assertIs(type(caught.exception), self.Error)
        self.assertEqual(caught.exception.reason, reason)
        self.assertEqual(str(caught.exception), reason)

    def test_empty_imports_both_architectures_and_frozen_quiet_result(self):
        for arch in ("x64", "arm64"):
            f = Fixture(arch)
            original = f.image()
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                result = self.inspect(original, expected_arch=arch)
            self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))
            self.assertEqual(result.architecture, arch)
            self.assertEqual(result.scope, "imports_delay_manifest")
            self.assertEqual((result.ordinary_imports, result.delay_imports), ((), ()))
            self.assertEqual(result.manifests[0].raw, XML)
            self.assertEqual(result.manifests[0].sha256, hashlib.sha256(XML).hexdigest())
            self.assertEqual(result.manifests[0].level, "asInvoker")
            self.assertFalse(result.manifests[0].ui_access)
            self.assertNotIn("<assembly", repr(result))
            self.assertEqual(original, f.image())
            for record in (result, result.manifests[0], result.resources[0]):
                with self.assertRaises(FrozenInstanceError):
                    setattr(record, "architecture" if record is result else "sha256", "changed")
            for name in ("parse_complete", "runtime_load_verified", "source_launch_verified"):
                self.assertFalse(hasattr(result, name))

    def test_imports_oft_ordinal_and_independent_section(self):
        for oft in (True, False):
            f = Fixture()
            f.imports(oft=oft)
            r = self.inspect(f.image(), expected_arch="x64")
            self.assertEqual(r.ordinary_imports[0].name, "kernel32.dll")
            self.assertEqual(r.ordinary_imports[0].symbols[0].name, "CreateFileW")
            self.assertEqual(r.ordinary_imports[0].symbols[1].ordinal, 7)

    def test_lookup_and_names_cannot_join_adjacent_sections(self):
        for delay, kind in ((False, "lookup"), (True, "lookup"),
                            (False, "dll"), (False, "symbol"), (False, "hint")):
            with self.subTest(delay=delay, kind=kind):
                f = Fixture(payload_base=0x7000)
                desc, lookup, iat, _ = f.imports(delay=delay, symbols=(7,))
                data = f.manifest_data[0][0]
                relocated = f.alloc(XML, True)
                f.pack(data, "<I", relocated)
                if kind == "lookup":
                    f.pack(0x6FF8, "<Q", (1<<63)|7)
                    f.pack(0x7000, "<Q", 0)
                    f.pack(desc+(16 if delay else 0), "<I", 0x6FF8)
                elif kind == "dll":
                    f.put(0x6FFB, b"kernel32.dll\0")
                    f.pack(desc+12, "<I", 0x6FFB)
                else:
                    rva = 0x6FFE if kind == "hint" else 0x6FFB
                    f.put(rva, b"\0\0Symbol\0")
                    f.pack(lookup, "<Q", rva)
                    f.pack(iat, "<Q", rva)
                with self.assertRaises(PeFormatError) as caught:
                    self.inspect(f.image(), expected_arch="x64")
                self.assertEqual(caught.exception.reason, "rva_not_file_backed")

    def test_lookup_and_name_at_single_section_exact_end(self):
        f = Fixture(payload_base=0x7000)
        desc, _, _, _ = f.imports(symbols=(7,))
        f.pack(0x6FF0, "<QQ", (1<<63)|7, 0)
        f.pack(desc, "<I", 0x6FF0)
        self.assertEqual(self.inspect(f.image(), expected_arch="x64").ordinary_imports[0].symbols[0].ordinal, 7)
        f = Fixture(payload_base=0x7000)
        desc, _, _, _ = f.imports(symbols=(7,))
        f.put(0x6FFE, b"x\0")
        f.pack(desc+12, "<I", 0x6FFE)
        self.assertEqual(self.inspect(f.image(), expected_arch="x64").ordinary_imports[0].name, "x")

    def test_delay_iat_resolver_and_unload(self):
        f = Fixture()
        desc, lookup, iat, _ = f.imports(delay=True, resolver=True)
        unload = f.alloc(struct.pack("<QQQ", 99, 88, 0), True)
        f.pack(desc + 24, "<I", unload)
        r = self.inspect(f.image(), expected_arch="x64")
        self.assertEqual(r.delay_imports[0].symbols[1].ordinal, 7)

    def test_descriptor_tail_metadata_and_duplicate_dll_preserved(self):
        f = Fixture()
        desc, _, _, _ = f.imports()
        raw = f.image()[f.offset(desc):f.offset(desc)+20]
        f.put(desc+20, raw + bytes(20) + b"TAIL")
        f.directory(1, desc, 64)
        r = self.inspect(f.image(), expected_arch="x64")
        self.assertEqual(len(r.ordinary_imports), 2)

    def test_all_resource_paths_and_manifest_encodings(self):
        f = Fixture(manifests=[(1, 1033, XML), (2, 1031, b"\xef\xbb\xbf"+XML),
                               ("named", "language", b"\xff\xfe"+XML.decode().encode("utf-16-le"))],
                    extra=[("OTHER", 1, 0, b"payload")])
        r = self.inspect(f.image(), expected_arch="x64")
        self.assertEqual(len(r.resources), 4)
        self.assertEqual(len(r.manifests), 3)
        self.assertIn((24, "named", "language"), [leaf.path for leaf in r.resources])

    def test_nonmanifest_empty_rva_contract(self):
        for rva in (0, 0x10000, 0x8000):
            f = Fixture(extra=[(10, 1, 0, b"")])
            data = next(d for d in f.manifest_data if not d[2])
            f.pack(data[0], "<I", rva)
            r = self.inspect(f.image(), expected_arch="x64")
            empty = next(x for x in r.resources if x.size == 0)
            self.assertEqual(empty.rva, rva)
            self.assertEqual(empty.sha256, hashlib.sha256(b"").hexdigest())
        f.pack(data[0], "<I", 0x10001)
        self.reject("invalid_resource", f)

    def test_directory_count_pairs_and_backing(self):
        f = Fixture()
        f.body = bytearray(changed(f.image(), 0x98+108, "<I", 13))
        self.reject("directory_not_declared", f)
        for index in (1, 2, 11, 13):
            for pair in ((0, 1), (0x1000, 0)):
                f = Fixture()
                f.directory(index, *pair)
                self.reject("directory_pair_invalid", f)
        f = Fixture()
        f.directory(1, 0x8000, 40)
        with self.assertRaises(PeFormatError) as caught:
            self.inspect(f.image(), expected_arch="x64")
        self.assertEqual(caught.exception.reason, "rva_not_file_backed")

    def test_import_rejections(self):
        for mutate, reason in (
                (lambda f,d,l,i,n: f.pack(d+4, "<I", 1), "unsupported_bound_import"),
                (lambda f,d,l,i,n: f.directory(11, d, 20), "unsupported_bound_import"),
                (lambda f,d,l,i,n: f.directory(1, d, 20), "unterminated_table"),
                (lambda f,d,l,i,n: f.pack(l, "<Q", 1<<32), "invalid_import"),
                (lambda f,d,l,i,n: f.pack(l, "<Q", (1<<63)|(1<<16)|1), "invalid_import"),
                (lambda f,d,l,i,n: f.pack(i, "<Q", 3), "invalid_import"),
                (lambda f,d,l,i,n: f.put(n, b"x/y\0"), "invalid_import")):
            f = Fixture()
            args = f.imports()
            mutate(f, *args)
            self.reject(reason, f)
        for dll in (b"", b".", b"..", b"x:y", b"x\\y", b"\x7f", b"x"*1024):
            f = Fixture()
            f.imports(dll=dll)
            self.reject("budget_exceeded" if len(dll)==1024 else "invalid_import", f)

    def test_delay_rejections(self):
        for offset, value, reason in ((0, 0, "unsupported_delay_mode"), (0, 3, "unsupported_delay_mode"),
                                     (20, 1, "unsupported_bound_import"), (28, 1, "unsupported_bound_import"),
                                     (8, 0, "invalid_import")):
            f = Fixture()
            d, _, _, _ = f.imports(delay=True)
            f.pack(d+offset, "<I", value)
            self.reject(reason, f)

    def test_resource_cycle_alias_wrong_depth_and_reserved(self):
        for mutate, reason in (
                (lambda f: f.pack(f.root+20, "<I", 0x80000000), "resource_cycle_or_alias"),
                (lambda f: f.pack(f.root+20, "<I", 24), "invalid_resource"),
                (lambda f: f.pack(f.root, "<I", 1), "invalid_resource"),
                (lambda f: f.pack(f.manifest_data[0][0]+12, "<I", 1), "invalid_resource")):
            f = Fixture()
            mutate(f)
            self.reject(reason, f)
        f = Fixture(manifests=[(1, 0, XML), (2, 0, XML)])
        name_node = f.root + 24
        target = struct.unpack_from("<I", f.body, f.offset(name_node+20))[0]
        f.pack(name_node+28, "<I", target)
        self.reject("resource_cycle_or_alias", f)
        f = Fixture(manifests=[(1, 0, XML), (2, 0, XML)])
        f.pack(f.root+24+24, "<I", 1)
        self.reject("invalid_resource", f)

    def test_resource_named_count_and_utf16(self):
        f = Fixture(manifests=[("name", 0, XML)])
        node = f.root+24
        f.pack(node+12, "<HH", 0, 1)
        self.reject("invalid_resource", f)
        f = Fixture(manifests=[("name", 0, XML)])
        name = struct.unpack_from("<I", f.body, f.offset(f.root+24+16))[0]&0x7fffffff
        f.pack(f.root+name+2, "<H", 0xD800)
        self.reject("invalid_resource", f)

    def test_every_manifest_checked_and_xml_policy(self):
        invalid = [b"", b"not xml", XML+b"garbage", b"<!DOCTYPE assembly>"+XML,
                   b"<!ENTITY secret 'x'>"+XML, XML.replace(b"asInvoker", b"requireAdministrator"),
                   XML.replace(b'uiAccess="false"', b'uiAccess="true"'),
                   XML.replace(b'asm.v3', b'asm.v1'), XML.replace(b'manifestVersion="1.0"', b''),
                   XML.replace(b'<requestedExecutionLevel', b'<requestedExecutionLevel extra="x"'),
                   XML.replace(b'/></requestedPrivileges>', b'/><requestedExecutionLevel level="asInvoker" uiAccess="false"/></requestedPrivileges>'),
                   XML.replace(b'</assembly>', b'<x:requestedExecutionLevel xmlns:x="other"/></assembly>'),
                   XML.replace(b'/></requestedPrivileges>', b'>text</requestedExecutionLevel></requestedPrivileges>')]
        for raw in invalid:
            f = Fixture(manifests=[(1, 0, XML), (2, 1, raw)])
            self.reject("invalid_manifest", f)
        self.reject("invalid_manifest", Fixture(manifests=[]))

    def test_manifest_extensions_and_utf16be(self):
        raw = XML.replace(b'</assembly>', b'<assemblyIdentity name="helper"/><dependency/><compiler xmlns="extension"/></assembly>')
        for data in (raw, b"\xfe\xff"+raw.decode().encode("utf-16-be")):
            self.assertEqual(len(self.inspect(Fixture(manifests=[(1,0,data)]).image(), expected_arch="x64").manifests), 1)

    def test_manifest_budgets(self):
        self.reject("budget_exceeded", Fixture(manifests=[(1, 0, XML + b" "*(4097-len(XML)))]))
        raw = XML + b" "*(4096-len(XML))
        accepted = Fixture(manifests=[(n, 0, raw) for n in range(16)],
                           payload_size=0x20000, size_of_image=0x30000)
        self.assertEqual(len(self.inspect(accepted.image(), expected_arch="x64").manifests), 16)
        f = Fixture(manifests=[(n, 0, raw) for n in range(17)],
                    payload_size=0x20000, size_of_image=0x30000)
        self.reject("budget_exceeded", f)

    def test_ascii_exact_nul_boundary(self):
        f = Fixture()
        f.imports(dll=b"x"*1023, symbols=("s"*1023,))
        r = self.inspect(f.image(), expected_arch="x64")
        self.assertEqual(len(r.ordinary_imports[0].name), 1023)
        self.assertEqual(len(r.ordinary_imports[0].symbols[0].name), 1023)

    def test_symbols_budget_counts_duplicates_exact_boundary(self):
        for count in (4096, 4097):
            f = Fixture(payload_size=0x20000, size_of_image=0x30000)
            f.imports(symbols=(1,)*count)
            if count == 4096:
                self.assertEqual(len(self.inspect(f.image(), expected_arch="x64").ordinary_imports[0].symbols), count)
            else:
                self.reject("budget_exceeded", f)

    def test_module_budget_shared_between_ordinary_and_delay(self):
        for count in (128, 129):
            f = Fixture()
            desc, _, _, _ = f.imports(symbols=())
            raw = f.image()[f.offset(desc):f.offset(desc)+20]
            f.put(desc, raw*(count-1) + bytes(20))
            f.directory(1, desc, count*20)
            f.meta = desc + count*20
            f.imports(delay=True, symbols=(), resolver=True)
            if count == 128:
                r = self.inspect(f.image(), expected_arch="x64")
                self.assertEqual(len(r.ordinary_imports)+len(r.delay_imports), count)
            else:
                self.reject("budget_exceeded", f)

    def test_resource_entry_plus_leaf_budget_exact_boundary(self):
        for count in (2045, 2046):
            # Manifest contributes 4 units. Second type/name contributes 2;
            # every language entry plus data leaf contributes two more.
            f = Fixture(extra=[(10, 1, n, b"") for n in range(count)],
                        meta_size=0x10000, payload_base=0x20000,
                        payload_size=0x10000, size_of_image=0x40000)
            if count == 2045:
                self.assertEqual(len(self.inspect(f.image(), expected_arch="x64").resources), count+1)
            else:
                self.reject("budget_exceeded", f)

    def test_cumulative_read_budget_counts_repeated_payloads(self):
        f = Fixture(extra=[(10, 1, n, b"p") for n in range(3)],
                    payload_size=6*1024*1024, size_of_image=0x700000)
        repeated = f.alloc(bytes(5*1024*1024), True)
        for data, _, raw in f.manifest_data:
            if raw == b"p":
                f.pack(data, "<II", repeated, 5*1024*1024)
        # 15MiB plus metadata fits, although the same 5MiB is read three times.
        self.assertEqual(len(self.inspect(f.image(), expected_arch="x64").resources), 4)
        for data, _, raw in f.manifest_data:
            if raw == b"p":
                f.pack(data+4, "<I", 6*1024*1024-512)
        self.reject("budget_exceeded", f)

    def test_cumulative_read_budget_exact_16mib_and_one_over(self):
        f = Fixture(extra=[(10, 1, n, b"p") for n in range(3)],
                    payload_size=6*1024*1024, size_of_image=0x700000)
        repeated = f.payload_base
        # Five directory headers, eight entries and four data entries total
        # 208 bytes; the manifest adds its raw length.
        remaining = 16*1024*1024 - 208 - len(XML)
        lengths = (5*1024*1024, 5*1024*1024, remaining-10*1024*1024)
        data_entries = [data for data, _, raw in f.manifest_data if raw == b"p"]
        for data, length in zip(data_entries, lengths):
            f.pack(data, "<II", repeated, length)
        self.assertEqual(len(self.inspect(f.image(), expected_arch="x64").resources), 4)
        f.pack(data_entries[-1]+4, "<I", lengths[-1]+1)
        self.reject("budget_exceeded", f)

    def test_truncated_descriptor_and_lookup_backing(self):
        f = Fixture()
        desc, _, _, _ = f.imports()
        f.directory(1, desc, 19)
        self.reject("unterminated_table", f)
        f = Fixture()
        desc, _, _, _ = f.imports(delay=True)
        f.directory(13, desc, 32)
        self.reject("unterminated_table", f)
        f = Fixture()
        desc, _, _, _ = f.imports()
        f.pack(desc, "<I", 0xEFFF)
        with self.assertRaises(PeFormatError) as caught:
            self.inspect(f.image(), expected_arch="x64")
        self.assertEqual(caught.exception.reason, "rva_not_file_backed")

    def test_missing_thunk_terminator_and_empty_symbol(self):
        f = Fixture(payload_size=0x20000, size_of_image=0x30000)
        desc, _, _, _ = f.imports(symbols=(1,)*4096)
        table = f.alloc(struct.pack("<"+"Q"*4097, *((1<<63)|1,)*4097), True)
        f.pack(desc, "<I", table)
        self.reject("budget_exceeded", f)
        f = Fixture()
        f.imports(symbols=("",))
        self.reject("invalid_import", f)

    def test_missing_iat_and_unload_terminators(self):
        for delay, unload in ((False, False), (True, False), (True, True)):
            f = Fixture()
            desc, _, iat, _ = f.imports(delay=delay)
            if unload:
                iat = f.alloc(struct.pack("<QQQ", 1, 2, 3), True)
                f.pack(desc+24, "<I", iat)
            else:
                f.pack(iat+16, "<Q", 1)
            self.reject("invalid_import", f)

    def test_resource_metadata_bounds_wrong_language_target_and_names(self):
        for modify in (
                lambda f: f.directory(2, f.root, 15),
                lambda f: f.pack(f.root+20, "<I", 0xFFFFFFFF),
                lambda f: f.pack(f.root+24+24+20, "<I", 0x80000000)):
            f = Fixture()
            modify(f)
            self.reject("invalid_resource", f)
        for name in ("", "a\0b"):
            f = Fixture(manifests=[(name, 0, XML)])
            self.reject("invalid_resource", f)

    def test_manifest_wrong_security_placement_and_element_content(self):
        bad = [XML.replace(b'<security>', b'<wrapper><security>').replace(b'</security>', b'</security></wrapper>'),
               XML.replace(b'/></requestedPrivileges>', b'><child/></requestedExecutionLevel></requestedPrivileges>'),
               XML.replace(b'asm.v3', b'other'), b'\xff\xfe\x00']
        for raw in bad:
            self.reject("invalid_manifest", Fixture(manifests=[(1, 0, raw)]))

    def test_utf16_without_bom_cannot_bypass_decoded_text_policy(self):
        for codec in ("utf-16-le", "utf-16-be"):
            self.reject("invalid_manifest", Fixture(manifests=[(1, 0, XML.decode().encode(codec))]))

    def test_closed_error_reasons_and_base_errors(self):
        with self.assertRaises(ValueError):
            self.Error("private payload")
        with self.assertRaises(PeFormatError) as caught:
            self.inspect(b"", expected_arch="x64")
        self.assertEqual(caught.exception.reason, "image_limit")
