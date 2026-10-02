"""Emit a bounded, privacy-preserving summary for a local WFP diagnostic capture."""

from __future__ import annotations

import argparse
import ipaddress
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


_MAX_XML_BYTES = 8 * 1024 * 1024
_MAX_CONTEXT_BYTES = 16 * 1024
_MAX_NET_EVENTS = 8192
_REQUIRED_FLAGS = frozenset({
    "FWPM_NET_EVENT_FLAG_IP_VERSION_SET",
    "FWPM_NET_EVENT_FLAG_IP_PROTOCOL_SET",
    "FWPM_NET_EVENT_FLAG_REMOTE_ADDR_SET",
    "FWPM_NET_EVENT_FLAG_REMOTE_PORT_SET",
    "FWPM_NET_EVENT_FLAG_PACKAGE_ID_SET",
})
_SID_PATTERN = re.compile(r"S-1-15-2(?:-[0-9]{1,10}){1,14}\Z")


def _inconclusive() -> dict[str, int | str]:
    return {"status": "inconclusive", "exact_classify_drop_count": 0}


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _first_descendant_text(parent: ET.Element, name: str) -> str | None:
    for element in parent.iter():
        if _local_name(element.tag) == name:
            return (element.text or "").strip()
    return None


def _validated_context(context: object) -> tuple[str, frozenset[tuple[str, str, int]]] | None:
    if not isinstance(context, dict) or set(context) != {"version", "package_sid", "targets"}:
        return None
    if type(context.get("version")) is not int or context.get("version") != 1:
        return None
    package_sid = context.get("package_sid")
    if not isinstance(package_sid, str) or len(package_sid) > 184:
        return None
    if _SID_PATTERN.fullmatch(package_sid) is None:
        return None
    try:
        sid_parts = [int(part) for part in package_sid.split("-")[3:]]
    except ValueError:
        return None
    if any(part > 0xFFFFFFFF for part in sid_parts):
        return None

    raw_targets = context.get("targets")
    if not isinstance(raw_targets, list) or len(raw_targets) != 2:
        return None
    targets: set[tuple[str, str, int]] = set()
    for raw_target in raw_targets:
        if not isinstance(raw_target, dict) or set(raw_target) != {
            "ip_version", "remote_address", "remote_port",
        }:
            return None
        ip_version = raw_target.get("ip_version")
        address = raw_target.get("remote_address")
        port = raw_target.get("remote_port")
        if (
            not isinstance(ip_version, str)
            or not isinstance(address, str)
            or type(port) is not int
            or not 1 <= port <= 65535
        ):
            return None
        try:
            parsed_address = ipaddress.ip_address(address)
        except ValueError:
            return None
        if str(parsed_address) not in {"127.0.0.1", "::1"}:
            return None
        expected_version = (
            "FWP_IP_VERSION_V4" if parsed_address.version == 4
            else "FWP_IP_VERSION_V6"
        )
        if ip_version != expected_version:
            return None
        targets.add((ip_version, str(parsed_address), port))
    if len(targets) != 2:
        return None
    return package_sid, frozenset(targets)


def _event_matches(
    event: ET.Element,
    package_sid: str,
    targets: frozenset[tuple[str, str, int]],
) -> bool | None:
    header = next(
        (element for element in event.iter() if _local_name(element.tag) == "header"),
        None,
    )
    classify_drop = next(
        (
            element for element in event.iter()
            if _local_name(element.tag) == "classifyDrop"
        ),
        None,
    )
    if header is None or classify_drop is None:
        return False

    if _first_descendant_text(event, "type") != "FWPM_NET_EVENT_TYPE_CLASSIFY_DROP":
        return False
    if _first_descendant_text(classify_drop, "msFwpDirection") != "MS_FWP_DIRECTION_OUT":
        return False
    if _first_descendant_text(header, "packageSid") != package_sid:
        return False
    if _first_descendant_text(header, "ipProtocol") != "6":
        return False

    ip_version = _first_descendant_text(header, "ipVersion")
    remote_port_text = _first_descendant_text(header, "remotePort")
    if ip_version not in {"FWP_IP_VERSION_V4", "FWP_IP_VERSION_V6"}:
        return False
    if remote_port_text is None or not remote_port_text.isascii() or not remote_port_text.isdecimal():
        return False
    remote_port = int(remote_port_text)
    if not 1 <= remote_port <= 65535:
        return False

    address_field = (
        "remoteAddrV4" if ip_version == "FWP_IP_VERSION_V4"
        else "remoteAddrV6.byteArray16"
    )
    remote_address_text = _first_descendant_text(header, address_field)
    if remote_address_text is None:
        return False
    try:
        remote_address = str(ipaddress.ip_address(remote_address_text))
    except ValueError:
        return False
    if (ip_version, remote_address, remote_port) not in targets:
        return False

    flags_element = next(
        (element for element in header.iter() if _local_name(element.tag) == "flags"),
        None,
    )
    if flags_element is None:
        return None
    flags = {
        (element.text or "").strip()
        for element in flags_element.iter()
        if _local_name(element.tag) == "item"
    }
    if not _REQUIRED_FLAGS.issubset(flags):
        return None
    return True


def _inspect_wfpdiag_bytes(
    xml_bytes: bytes,
    context: object,
) -> dict[str, int | str]:
    if not isinstance(xml_bytes, bytes) or len(xml_bytes) > _MAX_XML_BYTES:
        return _inconclusive()
    upper_xml = xml_bytes.upper()
    if b"<!DOCTYPE" in upper_xml or b"<!ENTITY" in upper_xml:
        return _inconclusive()
    validated = _validated_context(context)
    if validated is None:
        return _inconclusive()
    package_sid, targets = validated

    matched_events = 0
    incomplete_events = 0
    event_count = 0
    try:
        for _event, element in ET.iterparse(io.BytesIO(xml_bytes), events=("end",)):
            if _local_name(element.tag) != "netEvent":
                continue
            event_count += 1
            if event_count > _MAX_NET_EVENTS:
                return _inconclusive()
            match = _event_matches(element, package_sid, targets)
            if match is True:
                matched_events = min(matched_events + 1, _MAX_NET_EVENTS)
            elif match is None:
                incomplete_events += 1
            element.clear()
    except (ET.ParseError, ValueError, RecursionError):
        return _inconclusive()
    if matched_events == 0:
        if incomplete_events:
            return _inconclusive()
        return {"status": "no_match", "exact_classify_drop_count": 0}
    return {"status": "matched", "exact_classify_drop_count": matched_events}


def inspect_wfp_capture(
    xml_path: str | Path,
    context_path: str | Path,
) -> dict[str, int | str]:
    try:
        xml_file = Path(xml_path)
        context_file = Path(context_path)
        if xml_file.stat().st_size > _MAX_XML_BYTES:
            return _inconclusive()
        if context_file.stat().st_size > _MAX_CONTEXT_BYTES:
            return _inconclusive()
        with xml_file.open("rb") as stream:
            xml_bytes = stream.read(_MAX_XML_BYTES + 1)
        with context_file.open("rb") as stream:
            context_bytes = stream.read(_MAX_CONTEXT_BYTES + 1)
        if len(xml_bytes) > _MAX_XML_BYTES or len(context_bytes) > _MAX_CONTEXT_BYTES:
            return _inconclusive()
        context = json.loads(context_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
        return _inconclusive()
    return _inspect_wfpdiag_bytes(xml_bytes, context)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xml", required=True, help="local extracted wfpdiag.xml")
    parser.add_argument("--context", required=True, help="local exact-match context JSON")
    args = parser.parse_args(argv)
    result = inspect_wfp_capture(args.xml, args.context)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
