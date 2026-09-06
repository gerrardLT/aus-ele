"""后端品牌常量层（R2.1，2026-09-06 公测产品化改造）。

与前端 ``web/src/lib/brand.js`` 是同一套名字的两个投影，两边的邮件主题前缀必须逐字相同
（``tests/test_brand_consistency.py`` 与 ``web/src/lib/brandConsistency.test.js`` 各自锁一边）。

为什么后端也要一层常量而不是直接改字符串：旧品牌名 "AEMO Intelligence" 在后端有 14 处，
其中三处是**会发出去给用户看**的 —— 密码重置邮件主题、定时报告邮件主题、seed_admin 的默认
组织名。邮件主题里带着一个第三方监管/数据机构的缩写，等于每一封外发邮件都在替我们重复
那个法务问题；这三处是本轮改名的实际收益所在，其余 docstring/日志属于一致性。

改名纪律（Spec R2.7）：
1. **区分产品品牌名与数据源名** —— "AEMO" 作为数据源名必须原样保留（``tests/
   test_agent_orchestrator.py:548`` 也硬断言 system prompt 含 "AEMO"）；
2. **审计日志 action 名一律不改**（``access_token.issued`` 等是结构化 action，与品牌零耦合）；
3. **历史数据不改写**：``organization.name`` 既有值、``saved_report`` / ``agent_execution_log``
   历史 payload 里的旧品牌名保持原样 —— 改写会破坏报告可复现性与 lineage。改名零数据迁移，
   历史名视为历史快照。
"""

BRAND_NAME_ZH = "天枢"
BRAND_NAME_EN = "Tianshu"

#: 中英并列的展示名（日志 banner、报告页眉）。
BRAND_DISPLAY = f"{BRAND_NAME_ZH} {BRAND_NAME_EN}"

#: 邮件主题前缀。**改动这一项会同时改变用户收件箱里的发件人识别**，与前端镜像常量一起改。
EMAIL_SUBJECT_PREFIX = f"[{BRAND_NAME_ZH}]"

#: 产品品类描述（seed 脚本、报告页脚等需要一句话说明「这是什么」的地方）。
BRAND_TAGLINE_ZH = "澳洲电力市场与储能决策平台"

#: 非背书声明。邮件脚注与导出产物页脚共用；与前端 ``aemoNonAffiliation()`` 同义。
AEMO_NON_AFFILIATION_ZH = (
    "本产品与 Australian Energy Market Operator (AEMO) 无从属、授权或背书关系；"
    "AEMO 为本产品分析的公开数据来源之一。"
)


def brand_name(zh: bool = True) -> str:
    """按语言返回品牌名。后端默认中文（邮件正文当前只有中文模板）。"""
    return BRAND_NAME_ZH if zh else BRAND_NAME_EN


def subject(text: str, *, zh: bool = True) -> str:
    """给用户发出的邮件主题统一加品牌前缀。

    集中在这里而不是各路由自己拼方括号：前缀格式一旦分叉，用户邮箱里的会话就会散成两组，
    而这是那种只能靠重新发一轮邮件才能修的错。
    """
    return f"{EMAIL_SUBJECT_PREFIX} {text}"
