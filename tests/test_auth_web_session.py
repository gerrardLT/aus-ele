"""web-session 引导端点门控矩阵测试（2026-08-09 同源门控策略）。

覆盖：同站点 Origin/Referer 放行、localhost 开发来源、生产直连不同端口、
显式共享密钥、允许名单、跨站与无来源 fail-closed（403）。
"""

import os
import sys
import types
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from fastapi import HTTPException

from routes import auth_routes


def _fake_request(headers=None):
    return types.SimpleNamespace(headers=headers or {})


_ISSUED = {"token": "tok_bootstrap", "token_type": "Bearer", "expires_in": 3600}


class WebSessionGateTests(unittest.TestCase):
    def setUp(self):
        self._env_patch = mock.patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        # 确保测试起点不带相关 env
        os.environ.pop("AUS_ELE_WEB_BOOTSTRAP_SECRET", None)
        os.environ.pop("AUS_ELE_WEB_ALLOWED_ORIGINS", None)
        self.addCleanup(self._env_patch.stop)

    def _call(self, headers=None, secret_header=None):
        """以打桩的 db/签发函数调用端点，返回签发结果。"""
        all_headers = dict(headers or {})
        if secret_header is not None:
            all_headers["x-bootstrap-secret"] = secret_header
        fake_db = mock.MagicMock()
        with mock.patch("deps.get_db", return_value=fake_db), mock.patch(
            "access_control.issue_access_token", return_value=dict(_ISSUED)
        ) as issue_mock:
            result = auth_routes.create_web_session(
                request=_fake_request(all_headers),
                x_bootstrap_secret=all_headers.get("x-bootstrap-secret"),
            )
        return result, issue_mock

    def _expect_denied(self, headers=None, secret_header=None):
        with self.assertRaises(HTTPException) as ctx:
            self._call(headers=headers, secret_header=secret_header)
        self.assertEqual(ctx.exception.status_code, 403)

    # ── 同站点门控：放行 ────────────────────────────────────────────────
    def test_dev_proxy_origin_issues_token(self):
        """vite dev 代理形态：Origin=localhost:5174，Host 被改写为 127.0.0.1:8085。"""
        result, issue_mock = self._call(
            headers={"origin": "http://localhost:5174", "host": "127.0.0.1:8085"}
        )
        self.assertEqual(result["token"], "tok_bootstrap")
        issue_mock.assert_called_once()

    def test_production_direct_port_origin_issues_token(self):
        """生产直连形态：Origin 无端口，Host 带 :8085，同主机名即放行。"""
        result, issue_mock = self._call(
            headers={"origin": "http://35.72.12.242", "host": "35.72.12.242:8085"}
        )
        self.assertEqual(result["token"], "tok_bootstrap")
        issue_mock.assert_called_once()

    def test_referer_fallback_issues_token(self):
        result, issue_mock = self._call(
            headers={"referer": "http://localhost:5174/agent", "host": "127.0.0.1:8085"}
        )
        self.assertEqual(result["token"], "tok_bootstrap")
        issue_mock.assert_called_once()

    def test_loopback_origin_allowed(self):
        result, _ = self._call(
            headers={"origin": "http://127.0.0.1:5174", "host": "backend:8085"}
        )
        self.assertEqual(result["token"], "tok_bootstrap")

    # ── 显式共享密钥 ────────────────────────────────────────────────────
    def test_matching_secret_issues_without_origin(self):
        os.environ["AUS_ELE_WEB_BOOTSTRAP_SECRET"] = "shared-secret"
        result, issue_mock = self._call(headers={}, secret_header="shared-secret")
        self.assertEqual(result["token"], "tok_bootstrap")
        issue_mock.assert_called_once()

    def test_secret_mismatch_but_same_site_still_allowed(self):
        """密钥不匹配时回落同站点门控，不因密钥错而拒绝合法 web UI。"""
        os.environ["AUS_ELE_WEB_BOOTSTRAP_SECRET"] = "shared-secret"
        result, _ = self._call(
            headers={"origin": "http://localhost:5174", "host": "127.0.0.1:8085"},
            secret_header="wrong-secret",
        )
        self.assertEqual(result["token"], "tok_bootstrap")

    # ── 显式允许名单 ────────────────────────────────────────────────────
    def test_allowed_origins_env_issues_token(self):
        os.environ["AUS_ELE_WEB_ALLOWED_ORIGINS"] = "https://dash.example.com"
        result, _ = self._call(
            headers={"origin": "https://dash.example.com", "host": "api.internal:8085"}
        )
        self.assertEqual(result["token"], "tok_bootstrap")

    # ── Fail-closed：拒绝 ───────────────────────────────────────────────
    def test_cross_site_origin_denied(self):
        self._expect_denied(
            headers={"origin": "http://evil.example.com", "host": "35.72.12.242:8085"}
        )

    def test_no_origin_no_secret_denied(self):
        """无 Origin/Referer 且未配置密钥（或密钥不匹配）→ 403。"""
        self._expect_denied(headers={"host": "127.0.0.1:8085"})

    def test_secret_mismatch_cross_site_denied(self):
        os.environ["AUS_ELE_WEB_BOOTSTRAP_SECRET"] = "shared-secret"
        self._expect_denied(
            headers={"origin": "http://evil.example.com", "host": "35.72.12.242:8085"},
            secret_header="wrong-secret",
        )

    def test_malformed_origin_denied(self):
        self._expect_denied(
            headers={"origin": "not a url", "host": "127.0.0.1:8085"}
        )


if __name__ == "__main__":
    unittest.main()
