"""注册密码策略（R1.1，2026-09-06）。

为什么策略只作用在注册端点：既有三条设密入口（邀请接受 / 自助改密 / 密码重置）的
pydantic 校验都是 ``min_length=8``，且各自有测试断言锁住文案。把它们一并抬到 12 位
会在同一 commit 里同时动代码与既有测试，破坏归因（AGENTS.md 纪律）。注册是**新增账户**
的唯一入口，在这里把住源头即可阻止弱密码继续流入；存量弱密码由 P0.6 的哈希强度升级
与后续引导覆盖。这一不一致是**已知并刻意保留**的，不是遗漏。

不引入 zxcvbn 之类的库：公测期不加新依赖（镜像与 CI 20min build 成本），且字典顺序
判定已经能挡住绝大多数真实弱密码。判定是**保守下界** —— 只拒绝明显弱的，不误伤
长口令短语。
"""

from __future__ import annotations

import re

from fastapi import HTTPException

from env_flags import env_int

# 参数登记：data/assumptions_registry.json → registration_password_policy
DEFAULT_MIN_LENGTH = 12
# 上界不是排版问题：PBKDF2 代价与密码长度线性相关，不设上限等于给人免费放大
# 每次登录/注册的哈希成本（也放大 600k 迭代带来的开销）。
DEFAULT_MAX_LENGTH = 256

# 常见弱密码（小写比对）。刻意只收「确定弱」的条目，避免把用户的正常词判成弱密码。
COMMON_PASSWORDS = frozenset(
    {
        "password", "password1", "password123", "passw0rd", "p@ssw0rd",
        "123456", "1234567", "12345678", "123456789", "1234567890",
        "qwerty", "qwerty123", "abc123", "abcd1234", "iloveyou",
        "letmein", "welcome", "welcome1", "admin", "admin123",
        "monkey", "dragon", "master", "sunshine", "princess",
        "football", "baseball", "trustno1", "whatever", "starwars",
        "donald", "clarence", "changeme", "test1234", "as123456",
        "a1b2c3d4", "1q2w3e4r", "1qaz2wsx", "zaq12wsx", "pass",
        "11111111", "00000000", "aaaaaaaa", "12121212", "123123123",
        "aemonode", "aemo1234", "tianshu", "dubhe",
    }
)

# 纯字母词干（去掉数字与符号后的形态）。有了这一层，"Password123!" 才真的被拦住：
# 只做整串小写比对的话，人类最常用的「单词 + 年份/符号」变体全都放行，那这份名单的
# 实际保护力接近零。仍然要求长度 < 16 才判弱 —— 20 位的 "password..." 复合串已经不是
# 同一个攻击成本量级，不该被同一条规则误伤。
COMMON_WORD_STEMS = frozenset(
    {
        "password", "passwd", "passwrd", "pass", "qwerty", "welcome", "admin",
        "letmein", "iloveyou", "dragon", "monkey", "master", "sunshine",
        "princess", "football", "baseball", "trustno1", "whatever", "starwars",
        "changeme", "abc", "abcd", "test", "login", "secret", "hello",
        "aemo", "tianshu", "dubhe",
    }
)

_STEM_STRIP_RE = re.compile(r"[^a-z]")

# 整串里出现这些键盘行即判弱（含变体如 qwertyuiop12）。误伤面很小：正常口令短语里
# 几乎不会完整出现一行键盘序。
_KEYBOARD_ROWS = (
    "qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890",
)

_REPEATED_CHAR_RE = re.compile(r"^(.)\1*$")


def min_length() -> int:
    """调用时读环境变量，而不是 import 时定死（测试可在 patch.dict 后直接生效）。"""
    return env_int("AUS_ELE_PASSWORD_MIN_LENGTH", DEFAULT_MIN_LENGTH, floor=DEFAULT_MIN_LENGTH)


def max_length() -> int:
    return env_int("AUS_ELE_PASSWORD_MAX_LENGTH", DEFAULT_MAX_LENGTH, floor=DEFAULT_MAX_LENGTH)


def _character_classes(password: str) -> int:
    classes = 0
    if re.search(r"[a-z]", password):
        classes += 1
    if re.search(r"[A-Z]", password):
        classes += 1
    if re.search(r"\d", password):
        classes += 1
    if re.search(r"[^a-zA-Z0-9]", password):
        classes += 1
    return classes


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _contains_user_token(password: str, tokens: list[str]) -> bool:
    """密码是否包含用户的邮箱本地段/域名/显示名。

    只有长度 >= 4 的片段才参与比对：两段（如 ``hi``）会在无数正常密码里意外命中，
    判定太宽会变成「按不住弱密码、反而拦住强密码」。
    """
    candidate = _normalized(password)
    if not candidate:
        return False
    for token in tokens:
        needle = _normalized(token)
        if len(needle) >= 4 and needle in candidate:
            return True
    return False


def _is_keyboard_sequence(password: str) -> bool:
    """串里完整出现一行键盘序（正序或逆序），例如 ``qwertyuiop12``。"""
    value = password.lower()
    for row in _KEYBOARD_ROWS:
        if row in value or row[::-1] in value:
            return True
    return False


def _stem(password: str) -> str:
    """去掉所有非字母字符后的小写形态：``Password123!`` → ``password``。"""
    return _STEM_STRIP_RE.sub("", password.lower())


def evaluate_password(*, password: str, email: str = "", display_name: str = "") -> list[str]:
    """返回不合规原因列表；空列表 = 通过。

    单独暴露这个纯函数（而不是只给 assert）是为了让前端能拿到同一份判定做即时提示，
    避免「后端拒了、文案对不上」。
    """
    reasons: list[str] = []
    value = password or ""
    if len(value) < min_length():
        reasons.append(f"密码至少 {min_length()} 位")
    if len(value) > max_length():
        reasons.append(f"密码不能超过 {max_length()} 位")
    if value and _REPEATED_CHAR_RE.match(value):
        reasons.append("密码不能由同一字符重复构成")
    if _is_keyboard_sequence(value):
        reasons.append("密码不能使用键盘连续序列")
    if value.lower() in COMMON_PASSWORDS or (len(value) < 16 and _stem(value) in COMMON_WORD_STEMS):
        reasons.append("密码过于常见")
    if _character_classes(value) < 2:
        # 这一条同时涵盖了「纯数字串」：12 位的 123456789012 与 20 位的纯数字都只有
        # 一类字符，一律被拒。曾经另有一条 ``纯数字密码至少 16 位`` 的规则，它隐含
        # 「≥16 位纯数字可通过」，与本条直接矛盾且永远不可达（纯数字必然 <2 类）——
        # 留着只会让读代码的人以为存在一条「长数字口令」的豁免通道。
        reasons.append("密码需至少包含两类字符（字母/数字/符号）")
    tokens: list[str] = []
    if email and "@" in email:
        local, _, domain = email.partition("@")
        tokens.extend([local, domain.split(".", 1)[0] if domain else ""])
    if display_name:
        tokens.append(display_name)
    if _contains_user_token(value, tokens):
        reasons.append("密码不能包含你的邮箱或姓名")
    return reasons


def assert_registration_password(*, password: str, email: str = "", display_name: str = "") -> str:
    """注册端点的强制校验；不合规 → 422。

    detail 用结构化 ``{"errors": [...]}``：注册表单需要一次性显示全部原因，
    逐条 422 往返会把 UX 变成猜谜。HTTPException 的 detail 允许任意可序列化对象。
    """
    reasons = evaluate_password(password=password, email=email, display_name=display_name)
    if reasons:
        raise HTTPException(status_code=422, detail={"errors": reasons, "code": "weak_password"})
    return password
