"""种子管理员初始化脚本（邀请制闭环第一把钥匙，2026-08-14）。

用法（在 backend 目录下，或确保 backend 在 sys.path）：
    python -m scripts.seed_admin --email admin@example.com [--password 'xxx'] \
        [--org '组织名'] [--workspace main]

- 未提供 --password 时自动生成 16 位随机强密码并打印（请自行保管）。
- 幂等：邮箱已存在时只重置密码，不重复建组织/工作空间。
- 完成后管理员可登录 /login，在账户中心创建邀请链接发展成员。
"""

from __future__ import annotations

import argparse
import secrets
import string
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (str(BACKEND_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from tests.support import ensure_repo_import_paths  # noqa: E402

    ensure_repo_import_paths()  # 加载 .env（DATABASE_URL 等）
except Exception:  # noqa: BLE001
    # 退化：直接从 repo 根 .env 读取环境变量
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        import os

        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

from brand import BRAND_NAME_ZH  # noqa: E402
from database import DatabaseManager  # noqa: E402
from access_control import (  # noqa: E402
    seed_organization,
    seed_organization_membership,
    seed_principal,
    seed_workspace,
    seed_workspace_membership,
    set_principal_password,
)


def _random_password(length: int = 16) -> str:
    """生成随机强密码：大小写+数字+符号，保证各类至少 1 个。"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#$%^&*" for c in pw)):
            return pw


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize seed admin (invite-only bootstrap)")
    parser.add_argument("--email", required=True, help="管理员登录邮箱")
    parser.add_argument("--password", default=None, help="初始密码（缺省自动生成；建议改用 --password-stdin，避免进 shell history）")
    parser.add_argument("--password-stdin", dest="password_stdin", action="store_true",
                        help="从标准输入读取密码（不回显）")
    parser.add_argument("--org", default=BRAND_NAME_ZH, help="组织名")
    parser.add_argument("--workspace", default="main", help="工作空间名")
    args = parser.parse_args()

    email = args.email.strip().lower()
    if args.password_stdin:
        import getpass

        password = getpass.getpass("初始密码（不回显）: ").strip()
        if len(password) < 8:
            print("[error] 密码至少 8 位")
            return 1
    else:
        password = args.password or _random_password()

    db = DatabaseManager(None)
    existing = db.fetch_principal_by_email(email)

    if existing:
        # 幂等：已存在则只重置密码
        set_principal_password(db, principal_id=existing["principal_id"], password=password)
        print(f"[ok] principal already exists ({existing['principal_id']}), password reset.")
    else:
        org = seed_organization(db, name=args.org)
        ws = seed_workspace(db, organization_id=org["organization_id"], name=args.workspace)
        principal = seed_principal(db, email=email, display_name="Admin")
        seed_workspace_membership(db, workspace_id=ws["workspace_id"],
                                  principal_id=principal["principal_id"], role="owner")
        seed_organization_membership(db, organization_id=org["organization_id"],
                                     principal_id=principal["principal_id"], role="org_owner")
        set_principal_password(db, principal_id=principal["principal_id"], password=password)
        print(f"[ok] seeded: org={org['organization_id']} ws={ws['workspace_id']} principal={principal['principal_id']}")

    print()
    print("=== 种子管理员凭据（只显示一次，请妥善保管） ===")
    print(f"  登录页:  /login")
    print(f"  邮箱:    {email}")
    print(f"  初始密码: {password}")
    print("登录后请在 账户中心 > 成员管理 创建邀请链接发展成员。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
