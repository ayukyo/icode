import importlib.util
import importlib
from dataclasses import FrozenInstanceError
import struct
import unittest


class StartupSecurityInterfaceTests(unittest.TestCase):
    def test_parser_module_exists(self):
        self.assertIsNotNone(importlib.util.find_spec("icode.windows_startup_security"))

    def test_policy_interface_exists(self):
        module = importlib.import_module("icode.windows_startup_security")
        self.assertTrue(callable(getattr(module, "check_startup_security", None)))


def sid(authority=5, subauthorities=(32, 544)):
    return bytes((1, len(subauthorities))) + authority.to_bytes(6, "big") + b"".join(
        struct.pack("<I", item) for item in subauthorities)


def ace(kind=0, flags=0, mask=0x120089, trustee=None):
    trustee = sid() if trustee is None else trustee
    return struct.pack("<BBHI", kind, flags, 8 + len(trustee), mask) + trustee


def acl(entries=(), padding=b"", revision=2):
    body = b"".join(entries) + padding
    return struct.pack("<BBHHH", revision, 0, 8 + len(body), len(entries), 0) + body


def descriptor(owner=None, group=None, dacl=None, order=("owner", "group", "dacl"),
               shared=False, gap=b"", tail=b"", control=0x8004):
    components = {"owner": sid() if owner is None else owner,
                  "group": group, "dacl": acl((ace(),)) if dacl is None else dacl}
    body = bytearray(gap)
    offsets = {"owner": 0, "group": 0, "dacl": 0}
    for name in order:
        component = components[name]
        if component is not None:
            offsets[name] = 20 + len(body)
            body.extend(component)
    if shared:
        offsets["group"] = offsets["owner"]
    return struct.pack("<BBHIIII", 1, 0, control, offsets["owner"],
                       offsets["group"], 0, offsets["dacl"]) + body + tail


def replace(data, offset, value):
    return data[:offset] + value + data[offset + len(value):]


class StartupSecurityParserTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("icode.windows_startup_security"))
        self.module = importlib.import_module("icode.windows_startup_security")
        self.parse = self.module.parse_startup_security

    def rejects(self, value):
        with self.assertRaises(self.module.StartupSecurityError):
            self.parse(value)

    def test_error_inherits_pin_error(self):
        from icode.windows_startup_pin import StartupPinError
        self.assertTrue(issubclass(self.module.StartupSecurityError, StartupPinError))

    def test_basic_allow_and_deny_snapshot(self):
        data = descriptor(dacl=acl((ace(), ace(1, 0x1f, 0xf01f01ff, sid(5, (18,))))))
        before = bytes(data)
        result = self.parse(data)
        self.assertEqual(result.raw, before)
        self.assertEqual(data, before)
        self.assertEqual(result.owner_sid, "S-1-5-32-544")
        self.assertIsNone(result.group_sid)
        self.assertEqual(result.control, 0x8004)
        self.assertEqual(result.entries, (
            self.module.StartupAccessEntry(True, 0, 0x120089, "S-1-5-32-544"),
            self.module.StartupAccessEntry(False, 0x1f, 0xf01f01ff, "S-1-5-18")))
        self.assertIs(type(result.raw), bytes)
        self.assertIs(type(result.entries), tuple)
        with self.assertRaises(FrozenInstanceError):
            result.control = 0
        with self.assertRaises(FrozenInstanceError):
            result.entries[0].mask = 0

    def test_owner_group_distinct_and_shared(self):
        self.assertEqual(self.parse(descriptor(group=sid(5, (18,)))).group_sid, "S-1-5-18")
        self.assertEqual(self.parse(descriptor(shared=True)).group_sid, "S-1-5-32-544")

    def test_components_can_be_reordered(self):
        for order in (("dacl", "group", "owner"), ("group", "owner", "dacl")):
            with self.subTest(order=order):
                self.assertEqual(self.parse(descriptor(group=sid(5, (18,)), order=order)).owner_sid,
                                 "S-1-5-32-544")

    def test_empty_dacl_and_zero_padding(self):
        result = self.parse(descriptor(dacl=acl(padding=b"\0" * 4), gap=b"\0" * 4,
                                       tail=b"\0" * 4))
        self.assertEqual(result.entries, ())

    def test_acl_revision_four_and_control_bits(self):
        self.assertEqual(self.parse(descriptor(dacl=acl((ace(),), revision=4),
                                               control=0x950f)).control, 0x950f)

    def test_sid_zero_and_fifteen_subauthorities(self):
        for subs in ((), tuple(range(15))):
            with self.subTest(subauthorities=subs):
                expected = "S-1-281474976710655" + "".join(f"-{n}" for n in subs)
                value = sid(2**48 - 1, subs)
                self.assertEqual(self.parse(descriptor(owner=value,
                    dacl=acl((ace(trustee=value),)))).entries[0].sid, expected)

    def test_maximum_descriptor_size(self):
        data = descriptor()
        self.assertEqual(len(self.parse(data + b"\0" * (128 * 1024 - len(data))).raw), 128 * 1024)

    def test_exact_bytes_only(self):
        class BytesSubclass(bytes):
            pass
        for value in (bytearray(descriptor()), memoryview(descriptor()), BytesSubclass(descriptor()),
                      None, "", 20, []):
            with self.subTest(type=type(value)):
                self.rejects(value)

    def test_descriptor_length_bounds(self):
        for value in (b"", b"\0" * 19, b"\0" * (128 * 1024 + 1)):
            with self.subTest(length=len(value)):
                self.rejects(value)

    def test_header_revision_and_reserved(self):
        for offset, value in ((0, b"\0"), (0, b"\2"), (1, b"\1")):
            with self.subTest(offset=offset, value=value):
                self.rejects(replace(descriptor(), offset, value))

    def test_control_rejects_missing_required_and_unknown_bits(self):
        for control in (0, 4, 0x8000, 0x8014, 0x8024, 0x8044, 0x8084, 0x8204,
                        0x8804, 0xa004, 0xc004):
            with self.subTest(control=control):
                self.rejects(descriptor(control=control))

    def test_sacl_offset_forbidden(self):
        self.rejects(replace(descriptor(), 12, struct.pack("<I", 20)))

    def test_offsets_require_bounded_aligned_components(self):
        data = descriptor(group=sid(5, (18,)))
        for header_offset in (4, 8, 16):
            for offset in (1, 16, 21, len(data), len(data) + 4, 0xfffffffc):
                with self.subTest(field=header_offset, offset=offset):
                    self.rejects(replace(data, header_offset, struct.pack("<I", offset)))
        for header_offset in (4, 16):
            self.rejects(replace(data, header_offset, b"\0" * 4))

    def test_owner_group_partial_overlap_rejected(self):
        # Both offset 20 and 28 describe syntactically valid SIDs, but share only a suffix.
        overlapping_owner = sid(5, (0x00000101, 0x05000000, 18))
        with self.assertRaisesRegex(self.module.StartupSecurityError, "overlapping"):
            self.parse(replace(descriptor(owner=overlapping_owner), 8, struct.pack("<I", 28)))

    def test_sid_and_acl_overlap_rejected(self):
        # The owner's two subauthorities also form a valid revision-2 empty ACL.
        data = descriptor(owner=sid(5, (0x00080002, 0)), dacl=acl())
        with self.assertRaisesRegex(self.module.StartupSecurityError, "overlapping"):
            self.parse(replace(data, 16, struct.pack("<I", 28)))

    def test_sid_revision_count_and_truncation(self):
        for value in (b"\2" + sid()[1:], b"\1\20" + sid()[2:], sid()[:7], sid()[:-1]):
            with self.subTest(value=value):
                self.rejects(descriptor(owner=value, order=("dacl", "owner", "group")))
                self.rejects(descriptor(group=value, order=("dacl", "owner", "group")))

    def test_acl_header_truncation_revision_reserved_size(self):
        for value in (acl()[:7], replace(acl(), 0, b"\1"), replace(acl(), 1, b"\1"),
                      replace(acl(), 6, b"\1\0"), replace(acl(), 2, b"\4\0"),
                      replace(acl(), 2, b"\11\0"), replace(acl(), 2, b"\14\0")):
            with self.subTest(value=value):
                self.rejects(descriptor(dacl=value))

    def test_acl_count_and_ace_truncation(self):
        for value in (replace(acl(), 4, b"\1\0"), acl((ace()[:3],)),
                      acl((ace()[:-1],)), acl((replace(ace(), 2, b"\14\0"),)),
                      acl((replace(ace(), 2, b"\21\0"),)),
                      acl((replace(ace(), 2, b"\xff\xff"),))):
            with self.subTest(value=value):
                self.rejects(descriptor(dacl=value))

    def test_aligned_acl_with_truncated_ace_header(self):
        with self.assertRaisesRegex(self.module.StartupSecurityError, "truncated ACE header"):
            self.parse(descriptor(dacl=acl((ace()[:3],), padding=b"\0")))

    def test_aligned_ace_with_truncated_sid(self):
        with self.assertRaisesRegex(self.module.StartupSecurityError, "invalid or truncated SID"):
            self.parse(descriptor(dacl=acl((ace(trustee=sid()[:-4]),))))

    def test_ace_types_flags_and_masks(self):
        for kind in (2, 3, 4, 5, 6, 9, 10, 17, 255):
            with self.subTest(kind=kind):
                self.rejects(descriptor(dacl=acl((ace(kind=kind),))))
        for flags in (0x20, 0x40, 0x80, 0xff):
            with self.subTest(flags=flags):
                self.rejects(descriptor(dacl=acl((ace(flags=flags),))))
        for mask in (0x200, 0x8000, 0x200000, 0x1000000, 0x8000000):
            with self.subTest(mask=mask):
                self.rejects(descriptor(dacl=acl((ace(mask=mask),))))

    def test_ace_sid_must_fill_exact_ace(self):
        for trustee in (sid() + b"\0" * 4, b"\2" + sid()[1:], b"\1\20" + sid()[2:]):
            with self.subTest(trustee=trustee):
                self.rejects(descriptor(dacl=acl((ace(trustee=trustee),))))

    def test_nonzero_acl_and_descriptor_unused_bytes(self):
        for data in (descriptor(dacl=acl(padding=b"\1\0\0\0")),
                     descriptor(gap=b"\0\1\0\0"), descriptor(tail=b"\1"),
                     descriptor(dacl=replace(acl((ace(),)), 4, b"\0\0"))):
            with self.subTest(data=data):
                self.rejects(data)


class StartupSecurityPolicyTests(unittest.TestCase):
    HOST = "S-1-5-21-100-200-300-1001"
    HOST_BYTES = sid(5, (21, 100, 200, 300, 1001))
    UNKNOWN = sid(5, (21, 999))
    MUTATION_BITS = (0x2, 0x4, 0x10, 0x100, 0x10000, 0x40000, 0x80000,
                     0x40000000, 0x10000000)

    def setUp(self):
        self.module = importlib.import_module("icode.windows_startup_security")
        self.check = getattr(self.module, "check_startup_security", None)
        self.assertTrue(callable(self.check))

    def checked(self, data, *, role="source", host_sid=HOST, directory=False):
        return self.check(data, role=role, host_sid=host_sid, directory=directory)

    def rejects(self, data, **kwargs):
        with self.assertRaises(self.module.StartupSecurityError):
            self.checked(data, **kwargs)

    def test_host_owner_and_mutation_only_trusted_for_source(self):
        data = descriptor(owner=self.HOST_BYTES,
                          dacl=acl((ace(mask=0x10000000, trustee=self.HOST_BYTES),)))
        self.assertEqual(self.checked(data).owner_sid, self.HOST)
        self.rejects(data, role="protected")

    def test_admin_and_system_owners_and_mutators_trusted(self):
        for trusted in (sid(), sid(5, (18,))):
            for role in ("source", "protected"):
                for mask in (0x120089, 0x10000000):
                    with self.subTest(trusted=trusted, role=role, mask=mask):
                        data = descriptor(owner=trusted, dacl=acl((ace(mask=mask, trustee=trusted),)))
                        self.assertEqual(self.checked(data, role=role).raw, data)

    def test_protected_host_read_execute_allowed_but_each_mutation_rejected(self):
        for mask in (0x1200a9, 0x80000000, 0x20000000, 0xa0000000):
            with self.subTest(read_execute=mask):
                self.checked(descriptor(dacl=acl((ace(mask=mask, trustee=self.HOST_BYTES),))),
                             role="protected")
        for mask in self.MUTATION_BITS:
            with self.subTest(mutation=mask):
                self.rejects(descriptor(dacl=acl((ace(mask=mask, trustee=self.HOST_BYTES),))),
                             role="protected")

    def test_unknown_owner_denies_and_owner_rights_cannot_establish_trust(self):
        for entries in ((ace(kind=1, mask=0x10000000, trustee=self.UNKNOWN),),
                        (ace(mask=0x120089), ace(mask=0x40000, trustee=sid(3, (4,)))),
                        (ace(kind=1, mask=0x40000, trustee=sid(3, (4,))),)):
            for role in ("source", "protected"):
                with self.subTest(entries=entries, role=role):
                    self.rejects(descriptor(owner=self.UNKNOWN, dacl=acl(entries)), role=role)

    def test_empty_dacl_valid_for_parser_rejected_by_policy(self):
        data = descriptor(dacl=acl())
        self.assertEqual(self.module.parse_startup_security(data).entries, ())
        for role in ("source", "protected"):
            self.rejects(data, role=role)

    def test_every_untrusted_mutation_bit_rejected(self):
        for role in ("source", "protected"):
            for mask in self.MUTATION_BITS:
                with self.subTest(role=role, mask=mask):
                    self.rejects(descriptor(dacl=acl((ace(mask=mask, trustee=self.UNKNOWN),))),
                                 role=role)

    def test_delete_child_dangerous_only_for_directories(self):
        data = descriptor(dacl=acl((ace(mask=0x40, trustee=self.UNKNOWN),)))
        for role in ("source", "protected"):
            self.assertEqual(self.checked(data, role=role, directory=False).raw, data)
            self.rejects(data, role=role, directory=True)

    def test_deny_does_not_cancel_dangerous_allow_in_either_order(self):
        allow = ace(mask=0x2, trustee=self.UNKNOWN)
        deny = ace(kind=1, mask=0x10000000, trustee=self.UNKNOWN)
        for entries in ((deny, allow), (allow, deny)):
            self.rejects(descriptor(dacl=acl(entries)))
        # A deny-only DACL passes mutation policy; this does not grant RX access.
        self.checked(descriptor(dacl=acl((deny,))))

    def test_inheritance_flags_do_not_exempt_untrusted_mutation(self):
        for flags in (0x8, 0x10, 0x1f):
            for role in ("source", "protected"):
                with self.subTest(flags=flags, role=role):
                    self.rejects(descriptor(dacl=acl((ace(flags=flags, mask=0x2,
                                                         trustee=self.UNKNOWN),))), role=role)

    def test_creator_owner_not_automatically_trusted(self):
        for role in ("source", "protected"):
            self.rejects(descriptor(dacl=acl((ace(flags=0x8, mask=0x2,
                                                 trustee=sid(3, (0,))),))), role=role)

    def test_owner_rights_maps_only_to_already_trusted_owner(self):
        entries = acl((ace(mask=0x10000000, trustee=sid(3, (4,))),))
        for owner in (sid(), sid(5, (18,))):
            for role in ("source", "protected"):
                self.checked(descriptor(owner=owner, dacl=entries), role=role)
        data = descriptor(owner=self.HOST_BYTES, dacl=entries)
        self.checked(data, role="source")
        self.rejects(data, role="protected")

    def test_exact_role_host_and_directory_types_required(self):
        class StrSubclass(str):
            pass
        for role in (None, [], 1, "SOURCE", "protected ", "", StrSubclass("source")):
            with self.subTest(role=role):
                self.rejects(descriptor(), role=role)
        for host in (None, [], 1, b"S-1-5-18", StrSubclass(self.HOST)):
            with self.subTest(host=host):
                self.rejects(descriptor(), host_sid=host)
        for directory in (None, 0, 1, "false", []):
            with self.subTest(directory=directory):
                self.rejects(descriptor(), directory=directory)

    def test_host_sid_requires_bounded_canonical_decimal(self):
        invalid = ("", "S-2-5-18", "s-1-5-18", "S-01-5-18", "S-1-05-18",
                   "S-1-5-018", "S-1-5-+18", "S-1-5--18", " S-1-5-18",
                   "S-1-5-18 ", "S-1-5-１８", "S-1-5-١٨", "S-1-0x5-18",
                   "S-1-281474976710656", "S-1-5-4294967296", "S-1-5-",
                   "S-1-5" + "-0" * 16, "S-1-" + "9" * 5000)
        for host in invalid:
            with self.subTest(host=host[:80]):
                self.rejects(descriptor(), host_sid=host)

    def test_host_sid_zero_and_maximum_bounds_accepted(self):
        for host_bytes, host in ((sid(0, ()), "S-1-0"),
                                 (sid(2**48 - 1, (2**32 - 1,) * 15),
                                  "S-1-281474976710655" + "-4294967295" * 15)):
            data = descriptor(owner=host_bytes, dacl=acl((ace(mask=0x2, trustee=host_bytes),)))
            self.assertEqual(self.checked(data, host_sid=host).owner_sid, host)

    def test_forged_snapshots_and_nonbytes_rejected(self):
        forged = self.module.StartupSecurityDescriptor(
            b"not a descriptor", "S-1-5-32-544", None, 0x8004,
            (self.module.StartupAccessEntry(True, 0, 0x120089, "S-1-5-32-544"),))
        for data in (forged, self.module.parse_startup_security(descriptor()),
                     bytearray(descriptor()), memoryview(descriptor()), b"bad"):
            with self.subTest(type=type(data)):
                self.rejects(data)

    def test_reparses_raw_bytes_and_returns_frozen_snapshot(self):
        data = descriptor(dacl=acl((ace(mask=0x120089, trustee=self.UNKNOWN),)))
        expected = self.module.parse_startup_security(data)
        result = self.checked(data)
        self.assertEqual(result, expected)
        self.assertIsNot(result, expected)
        self.assertIs(type(result.raw), bytes)
        self.assertIs(type(result.entries), tuple)
        with self.assertRaises(FrozenInstanceError):
            result.owner_sid = self.HOST
        with self.assertRaises(FrozenInstanceError):
            result.entries[0].mask = 0x2

    def test_policy_keeps_parser_rejection_of_unknown_masks_and_ace_types(self):
        for entry in (ace(mask=0x200), ace(kind=2)):
            self.rejects(descriptor(dacl=acl((entry,))))
