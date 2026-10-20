"""UI 落地第二片：真实服务器 E2E 渲染断言 + i18n 静态契约（设计包 §9 遗留项）。

E2E 部分经真实 WorkbenchServer（loopback + 会话 cookie）验证：
公开投影携带三段展示契约；验收记录在证据包事实存在时出现、不存在时不伪造。
i18n 部分为静态契约：index.html 引用的每个文案键在两种语言词典中都存在，
且两套词典键集合一致（缺键会触发前端回退告警——契约层先行拦截）。
"""

import json
import re
import tempfile
import unittest
from pathlib import Path

from tests._support import REPO_ROOT, require_skill, temp_workspace
from tests.test_workbench import _request
from icode.workbench import WorkbenchServer

ASSETS_DIR = REPO_ROOT / "src" / "icode" / "workbench_assets"

_JS_KEY_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*:\s*"')


def _locale_keys(js: str) -> tuple[set[str], set[str]]:
    zh_start = js.index('"zh-CN": {')
    en_start = js.index('"en-US": {')
    en_end = js.index("\n  };", en_start)
    zh_block = js[zh_start:en_start]
    en_block = js[en_start:en_end]
    return set(_JS_KEY_RE.findall(zh_block)), set(_JS_KEY_RE.findall(en_block))


class I18nContractTests(unittest.TestCase):
    def test_data_i18n_keys_exist_in_both_locales(self):
        html = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
        used = set(re.findall(
            r'data-i18n(?:-placeholder)?="([^"]+)"', html))
        self.assertGreater(len(used), 20, "index.html 的 data-i18n 用量异常")
        js = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
        zh, en = _locale_keys(js)
        self.assertEqual(zh, en, "两套词典键集合必须一致（缺键即触发回退告警）")
        missing = sorted(used - zh)
        self.assertEqual(missing, [], f"以下文案键在词典中缺失：{missing}")

    def test_acceptance_and_display_element_ids_present(self):
        html = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
        for element_id in (
            "detail-stage-label", "detail-auxiliary",
            "acceptance-panel", "acceptance-digest",
            "acceptance-signature", "acceptance-anchors",
        ):
            self.assertIn(f'id="{element_id}"', html)
        js = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
        for key in ("acceptanceTitle", "signatureSigned", "signatureMissing",
                    "signatureUnreadable", "anchorsNone", "acceptanceNote"):
            self.assertIn(key, js)


class LandingE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workspace_ctx = temp_workspace()
        cls.workspace = cls.workspace_ctx.__enter__()
        cls.server = WorkbenchServer(
            settings=require_skill(),
            workspace=cls.workspace,
            index_path=cls.workspace / "index.json",
            port=0,
        )
        cls.url = cls.server.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()
        cls.workspace_ctx.__exit__(None, None, None)

    def _cookie(self) -> str:
        status, headers, _ = _request(self.url)
        self.assertEqual(status, 200)
        return headers.get("Set-Cookie", "").split(";", 1)[0]

    def _create(self, cookie: str, request_id: str) -> dict:
        status, _, body = _request(
            self.url + "api/v1/tickets",
            method="POST",
            payload={
                "project_id": self.server.service.project_id,
                "title": "展示契约验证",
                "description": "验证三段展示与验收记录投影。",
                "expected_result": "详情带 display；packs 存在时带 acceptance。",
                "priority": "normal",
                "locale": "zh-CN",
                "execution_mode": "interactive",
                "request_id": request_id,
            },
            cookie=cookie,
        )
        self.assertIn(status, (200, 201))
        return json.loads(body)

    def _ticket_dir(self, ticket_id: str) -> Path:
        for meta_path in sorted(
            (self.workspace / ".icode_output").rglob(".ico_metadata.json")
        ):
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if metadata.get("ticket_id") == ticket_id:
                return meta_path.parent
        raise AssertionError(f"未找到工单目录：{ticket_id}")

    def test_详情带三段展示契约(self):
        cookie = self._cookie()
        created = self._create(cookie, "landing-display-1")
        ticket_id = created["ticket"]["ticket_id"] if "ticket" in created else created["ticket_id"]
        status, _, body = _request(
            self.url + f"api/v1/tickets/{ticket_id}", cookie=cookie)
        self.assertEqual(status, 200)
        ticket = json.loads(body)["ticket"]
        display = ticket["display"]
        self.assertEqual(display["contract_version"], 1)
        self.assertEqual(display["status"], ticket["status"])
        self.assertIn(display["stage"], (
            "understanding", "submitted", "reviewing_plan", "finalizing_plan",
            "ready_to_implement", "working", "checking", "preparing_delivery",
            "completed", "unknown",
        ))
        self.assertEqual(set(display["stage_label"]), {"zh-CN", "en-US"})
        self.assertEqual(set(display["status_label"]), {"zh-CN", "en-US"})
        # 证据包事实不存在时不得伪造验收记录
        self.assertNotIn("acceptance", ticket)

    def test_列表投影同样携带展示契约(self):
        cookie = self._cookie()
        self._create(cookie, "landing-display-2")
        status, _, body = _request(self.url + "api/v1/tickets", cookie=cookie)
        self.assertEqual(status, 200)
        tickets = json.loads(body)["tickets"]
        self.assertTrue(tickets)
        for ticket in tickets:
            self.assertIn("display", ticket)
            self.assertEqual(set(ticket["display"]["stage_label"]), {"zh-CN", "en-US"})

    def test_证据包存在时详情出现验收记录(self):
        cookie = self._cookie()
        created = self._create(cookie, "landing-acceptance-1")
        ticket_id = created["ticket"]["ticket_id"] if "ticket" in created else created["ticket_id"]
        ticket_dir = self._ticket_dir(ticket_id)
        pack = ticket_dir / "pack"
        pack.mkdir()
        (pack / "manifest.json").write_text(json.dumps({
            "pack_digest": "9f" * 32,
            "generated_at": "2026-10-20T00:00:00+00:00",
        }), encoding="utf-8")
        (pack / "signature.json").write_text(json.dumps({
            "algorithm": "ed25519",
            "signed_at": "2026-10-20T00:01:00+00:00",
            "key_fingerprint": "3ab1c0de",
            "public_key": "cd" * 32,
        }), encoding="utf-8")
        status, _, body = _request(
            self.url + f"api/v1/tickets/{ticket_id}", cookie=cookie)
        self.assertEqual(status, 200)
        acceptance = json.loads(body)["ticket"]["acceptance"]
        self.assertEqual(acceptance["pack_digest"], "9f" * 32)
        self.assertEqual(acceptance["signature"]["state"], "signed")
        self.assertEqual(acceptance["anchors"], [])
        self.assertNotIn(str(self.workspace), body)


if __name__ == "__main__":
    unittest.main()
