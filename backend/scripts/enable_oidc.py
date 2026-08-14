"""OIDC SSO 开通脚本（P1-7，2026-08-14）。

用法（需 backend 可导入 + 数据库环境变量就绪，容器内或本地均可）：
    python -m scripts.enable_oidc --org org_xxx --provider google \
        --client-id <CLIENT_ID> --client-secret <CLIENT_SECRET> [--scopes openid,email,profile]

前置条件（外部操作，脚本无法代办）：
1. 在 Google Cloud Console / Azure AD 注册 OAuth 应用，获得 client_id/client_secret
2. 应用的重定向 URI 加上本站 /api/auth/oidc/callback

开通后登录页「企业 SSO 登录」即可用（组织 ID + provider）。
幂等：同一组织同一 provider_key 重复执行仅更新凭据。
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (str(BACKEND_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from tests.support import ensure_repo_import_paths  # noqa: E402

    ensure_repo_import_paths()
except Exception:  # noqa: BLE001
    import os

    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

from database import DatabaseManager  # noqa: E402

# 常用 IdP 的 issuer / discovery 默认值
_KNOWN_PROVIDERS = {
    "google": {
        "issuer": "https://accounts.google.com",
        "discovery_url": "https://accounts.google.com/.well-known/openid-configuration",
        "scopes": ["openid", "email", "profile"],
    },
    "microsoft": {
        # common 端点；单租户可替换为 https://login.microsoftonline.com/<tenant-id>/v2.0
        "issuer": "https://login.microsoftonline.com/common/v2.0",
        "discovery_url": "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
        "scopes": ["openid", "email", "profile"],
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Enable OIDC SSO for an organization")
    parser.add_argument("--org", required=True, help="组织 ID（org_xxx）")
    parser.add_argument("--provider", required=True, help="provider key：google / microsoft / 自定义")
    parser.add_argument("--client-id", required=True, dest="client_id")
    parser.add_argument("--client-secret", required=True, dest="client_secret")
    parser.add_argument("--issuer", default=None)
    parser.add_argument("--discovery-url", default=None, dest="discovery_url")
    parser.add_argument("--scopes", default=None, help="逗号分隔，缺省 openid,email,profile")
    args = parser.parse_args()

    db = DatabaseManager(None)
    if not db.fetch_organization(args.org):
        print(f"[error] organization not found: {args.org}")
        return 1

    known = _KNOWN_PROVIDERS.get(args.provider.lower(), {})
    scopes = (
        [s.strip() for s in args.scopes.split(",") if s.strip()]
        if args.scopes
        else known.get("scopes", ["openid", "email", "profile"])
    )

    existing = db.fetch_oidc_provider_by_key(args.org, args.provider)
    provider_id = existing["provider_id"] if existing else f"oid_{uuid.uuid4().hex[:12]}"

    import datetime

    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = db.upsert_oidc_provider(
        {
            "provider_id": provider_id,
            "organization_id": args.org,
            "provider_key": args.provider,
            "issuer": args.issuer or known.get("issuer", ""),
            "discovery_url": args.discovery_url or known.get("discovery_url", ""),
            "client_id": args.client_id,
            "client_secret_encrypted": args.client_secret,
            "scopes_json": scopes,
            "enabled": 1,
            "created_at": existing.get("created_at") or now_iso,
            "updated_at": now_iso,
        }
    )
    print(f"[ok] OIDC provider enabled: {record['provider_id']} ({args.provider} @ {args.org})")
    print("登录页「企业 SSO 登录」填入组织 ID 与 provider 即可使用。")
    print("提醒：请确认 IdP 应用的重定向 URI 已包含本站 /api/auth/oidc/callback。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
