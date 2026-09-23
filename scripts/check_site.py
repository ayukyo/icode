#!/usr/bin/env python3
"""Validate the repository presentation without network access.

Checks local HTML links and anchors, local assets, basic accessibility metadata,
the no-tracking/no-CDN policy, README-local links, and the exact vendored brand
asset hashes. External links are reported separately because their availability
is not deterministic in CI.
"""

from __future__ import annotations

import hashlib
import re
import struct
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
HTML_FILES = (SITE / "index.html", SITE / "en" / "index.html")
DOC_FILES = (
    ROOT / "README.md",
    ROOT / "README.zh-CN.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    ROOT / "docs" / "brand-assets.md",
    SITE / "README.md",
)
EXPECTED_ASSETS = {
    "icode-ticket-hex.svg": "2e1c2ec9cdc31eef0ae9a54fd6c47aa254605ae5c644568763a73deb5a286a88",
    "icode-ticket-hex-128.png": "4bea5f07d3c2872a5b052218ee6a8bed081e55bbb48dedc95d4af9685a8d1794",
    "icode-ticket-hex-512.png": "32418a9c51ea02d5a6e6bc940f1f7ae8cd0bedddefa00b226d3815fe70573862",
}
EXPECTED_SITE_ASSETS = {
    "social-preview.png": "70d856c5706a3e8147725de53f838dc3cfdfcff1256addbfd4d9516aa9eea05e",
    "social-preview-en.png": "3cf2e2a17a9f6364a330250f30b8a8d1946e9d6646c484fe057bd75d63ad48a3",
}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.references: list[tuple[str, str]] = []
        self.images: list[dict[str, str | None]] = []
        self.html_lang: str | None = None
        self.nav_labels: list[str | None] = []
        self.external_assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(str(values["id"]))
        if tag == "html":
            self.html_lang = values.get("lang")
        if tag == "nav":
            self.nav_labels.append(values.get("aria-label"))
        if tag == "a" and values.get("href"):
            self.references.append(("href", str(values["href"])))
        if tag in {"img", "script"} and values.get("src"):
            url = str(values["src"])
            self.references.append(("src", url))
            if _is_external(url):
                self.external_assets.append(url)
        if tag == "img":
            self.images.append(values)
        if tag == "link" and values.get("href"):
            rel = str(values.get("rel", ""))
            url = str(values["href"])
            if any(name in rel for name in ("stylesheet", "icon")):
                self.references.append(("href", url))
                if _is_external(url):
                    self.external_assets.append(url)


def _is_external(url: str) -> bool:
    return urlsplit(url).scheme in {"http", "https", "mailto"} or url.startswith("//")


def _local_target(page: Path, url: str) -> tuple[Path, str]:
    parts = urlsplit(url)
    path = unquote(parts.path)
    target = (page.parent / path).resolve() if path else page.resolve()
    if target.is_dir():
        target = target / "index.html"
    return target, unquote(parts.fragment)


def check_html() -> tuple[list[str], set[str]]:
    problems: list[str] = []
    external_links: set[str] = set()
    parsed: dict[Path, PageParser] = {}

    for page in HTML_FILES:
        parser = PageParser()
        parser.feed(page.read_text(encoding="utf-8"))
        parsed[page.resolve()] = parser
        if not parser.html_lang:
            problems.append(f"{page.relative_to(ROOT)}: missing html[lang]")
        if not parser.nav_labels or any(not label for label in parser.nav_labels):
            problems.append(f"{page.relative_to(ROOT)}: every nav needs aria-label")
        for image in parser.images:
            if "alt" not in image:
                problems.append(f"{page.relative_to(ROOT)}: img missing alt attribute")
        if parser.external_assets:
            problems.append(
                f"{page.relative_to(ROOT)}: externally hosted asset(s): "
                + ", ".join(sorted(parser.external_assets))
            )

    for page, parser in parsed.items():
        for kind, url in parser.references:
            if _is_external(url):
                if kind == "href":
                    external_links.add(url)
                continue
            if url.startswith(("data:", "javascript:")):
                problems.append(f"{page.relative_to(ROOT)}: disallowed asset/link URL {url!r}")
                continue
            target, fragment = _local_target(page, url)
            if not target.exists():
                problems.append(
                    f"{page.relative_to(ROOT)}: missing local target {url!r} -> "
                    f"{target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}"
                )
                continue
            if fragment and target.suffix.lower() == ".html":
                target_parser = parsed.get(target.resolve())
                if target_parser is None:
                    target_parser = PageParser()
                    target_parser.feed(target.read_text(encoding="utf-8"))
                    parsed[target.resolve()] = target_parser
                if fragment not in target_parser.ids:
                    problems.append(f"{page.relative_to(ROOT)}: missing anchor #{fragment} in {target}")

    css = (SITE / "style.css").read_text(encoding="utf-8")
    if re.search(r"@import\s+url|url\(\s*['\"]?https?://", css, flags=re.IGNORECASE):
        problems.append("site/style.css: external CSS/font/image dependency found")
    return problems, external_links


MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
HTML_RESOURCE = re.compile(r"<(?:img|source)\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)


def check_markdown_links() -> list[str]:
    problems: list[str] = []
    for document in DOC_FILES:
        text = document.read_text(encoding="utf-8")
        targets = [match.group(1) for match in MARKDOWN_LINK.finditer(text)]
        targets.extend(match.group(1) for match in MARKDOWN_IMAGE.finditer(text))
        targets.extend(match.group(1) for match in HTML_RESOURCE.finditer(text))
        for raw_target in targets:
            raw = raw_target.strip()
            target_text = raw.split(maxsplit=1)[0].strip("<>")
            if _is_external(target_text) or target_text.startswith(("#", "mailto:")):
                continue
            path_text = unquote(urlsplit(target_text).path)
            target = (document.parent / path_text).resolve()
            if not target.exists():
                problems.append(f"{document.relative_to(ROOT)}: missing local link {target_text!r}")
    return problems


def check_brand_assets() -> list[str]:
    problems: list[str] = []
    for name, expected in {**EXPECTED_ASSETS, **EXPECTED_SITE_ASSETS}.items():
        path = SITE / "assets" / name
        if not path.is_file():
            problems.append(f"missing brand asset: {path.relative_to(ROOT)}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            problems.append(f"brand asset drift: {name}: expected {expected}, got {actual}")
    preview_sizes = {
        "social-preview.png": (1280, 640),
        "social-preview-en.png": (1280, 640),
    }
    for name, expected_size in preview_sizes.items():
        preview = SITE / "assets" / name
        if not preview.is_file():
            continue
        header = preview.read_bytes()[:24]
        if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
            problems.append(f"{name}: not a valid PNG header")
        else:
            width, height = struct.unpack(">II", header[16:24])
            if (width, height) != expected_size:
                problems.append(
                    f"{name}: expected {expected_size[0]}x{expected_size[1]}, "
                    f"got {width}x{height}"
                )
        if preview.stat().st_size >= 1_000_000:
            problems.append(f"{name}: GitHub preview must stay under 1 MB")
    return problems


def main() -> int:
    problems, external_links = check_html()
    problems.extend(check_markdown_links())
    problems.extend(check_brand_assets())
    if problems:
        print(f"Site checks failed: {len(problems)} problem(s)", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1

    print("Site checks passed")
    print(f"- HTML pages: {len(HTML_FILES)}")
    print(f"- Markdown entry files: {len(DOC_FILES)}")
    print(f"- Exact upstream brand assets: {len(EXPECTED_ASSETS)}")
    print(f"- Repository social preview assets: {len(EXPECTED_SITE_ASSETS)}")
    print(f"- External navigation links (not fetched): {len(external_links)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
