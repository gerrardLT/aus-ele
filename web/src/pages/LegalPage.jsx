// web/src/pages/LegalPage.jsx
// 法务合规页（P1-5，2026-08-14；R2.4 补全，2026-09-06）：
//   /legal/terms | /legal/privacy | /legal/disclaimer | /legal/dpa | /legal/aup | /legal/cookies
// 核心为免责声明：非投资建议 + derived 数据口径 + AEMO 数据来源与非背书声明。
// zh/en 双语内联（篇幅大且低频，不入 translations.js）。
//
// 三条写作纪律（本轮踩过的坑都在这里锁住）：
// 1. **只写系统当前真的在做的事**。每一条法务陈述都要能在代码里找到对应实现；找不到实现
//    的句子一律不写（隐私页第 5 条就是因此改成生成的，见下）。
// 2. **不伪造可核验的法律事实**：运营主体名称与 ABN/ACN 未登记时渲染成「正在办理登记」，
//    绝不填一个看起来像那么回事的 11 位数字。
// 3. 品牌名一律取自 lib/brand.js，本页不出现硬编码产品名（曾用名是唯一的例外，且它本身
//    也是常量层导出的数组）。
//
// 例外：隐私页第 5 条（用户权利）**不内联**，由 lib/dataRights 生成 —— 那句的真假取决于
// R1.7 自助端点是否在线，而端点带 feature flag；写死字面量会在「上线前」与「被回滚后」
// 两个窗口里各构成一次不实陈述。

import { privacyRightsCopy } from '../lib/dataRights.js';
import {
  aemoNonAffiliation,
  brandEyebrow,
  brandLockup,
  contactHref,
  FORMER_BRAND_NAMES,
  legalEntity,
  legalEntityStatement,
} from '../lib/brand.js';

// 下面三个小助手存在的唯一理由：法务文本里「管辖法域」和「联系渠道」这两件事的真值取决于
// 配置，而配置缺失时必须说没有的那句。把它们抽成函数而不是在 11 处模板里各写一遍三元，
// 是为了让「未配置时的说法」只有一份定义 —— 否则同一页会出现两种不同的兜底文案。
function governingLaw(zh) {
  const configured = legalEntity(import.meta.env).jurisdiction;
  if (configured) return configured;
  return zh ? '新南威尔士州（澳洲东部时间，UTC+10/+11）' : 'New South Wales, Australia (AEST/AEDT)';
}

function contactChannel(zh) {
  const href = contactHref(import.meta.env, '/help');
  if (href !== '/help') return href.replace('mailto:', '');
  return zh ? '登录后在「帮助与反馈」页提交' : 'submit a request on the Help & feedback page after signing in';
}


const CONTENT = {
  terms: {
    zh: {
      title: '服务条款',
      sections: [
        ['1. 服务说明与运营主体', (isZh) => `${legalEntityStatement(import.meta.env, isZh)}${brandLockup(true)}（${brandLockup(false)}）提供澳洲 NEM/WEM 电力市场数据分析、储能收益判断与 AI 决策引擎服务。公测期内开放自助注册，免费套餐含每日 Agent 运行与 API 配额；本节曾在自助注册上线前写为「平台为邀请制」，该表述已废止。`],
        ['2. 品牌与曾用名', (isZh) => `本服务以「${brandLockup(true)}」名义提供。2026-09-06 之前的界面、邮件与导出报告页脚中可能出现另一称谓（${FORMER_BRAND_NAMES.join('、')}），该称谓仅为当时的界面用名，不构成服务主体标识；服务主体以第 1 条为准。改名不改变本条款的连续性，历史版本条款继续适用于其有效期内产生的用量。`],
        ['3. 账户与授权', '用户须妥善保管账户凭据与 API Key；API Key 泄露导致的损失由用户自行承担。工作空间内的数据访问受角色权限控制（owner/admin/analyst/viewer）。你不得将账户或 API Key 出借、转让或与未授权方共享。'],
        ['4. 配额与用量', '各套餐含 Agent 运行与 API 调用日配额。当前为软配额（超额标记不阻断）；支付功能就绪后将启用硬配额。平台保留调整配额策略的权利，调整前将提前告知。'],
        ['5. 数据与知识产权', '市场数据来源于 AEMO、Fingrid 等官方公开渠道，其版权与使用条件归原机构所有，本产品的加工不产生对原始数据的任何权利。本产品加工产生的派生指标、基准与方法论归平台所有；你可以为内部研究与投资决策使用输出结果，但不得对外转售、再分发或声称其为官方发布。'],
        ['6. 与 AEMO 等数据源的关系', (isZh) => aemoNonAffiliation(isZh)],
        ['7. 免责与责任限制', '平台输出不构成投资建议（详见免责声明）。因数据源故障、政策变化或不可抗力导致的分析偏差，平台不承担直接损失责任。'],
        ['8. 可接受使用', '使用本服务须遵守《可接受使用政策》（/legal/aup），包括对自动化调用、数据再分发与输出对外表述方式的约束。'],
        ['9. 隐私与数据处理', '个人信息的收集与处理见《隐私政策》（/legal/privacy）；作为数据处理者时的角色与义务见《数据处理附录》（/legal/dpa）；本地存储与第三方资源加载见《Cookie 与同类技术》（/legal/cookies）。'],
        ['10. 管辖法域与争议', (isZh) => `本条款适用${governingLaw(isZh)}法律，争议提交该法域有管辖权的法院。公测期内出现争议的，双方同意先行通过协商解决。`],
        ['11. 条款变更与联系', (isZh) => `条款更新将在本页公示并在登录时提示；继续使用视为接受变更后的条款。联系渠道：${contactChannel(isZh)}。`],
      ],
    },
    en: {
      title: 'Terms of Service',
      sections: [
        ['1. Service & operator', (isZh) => `${legalEntityStatement(import.meta.env, isZh)} ${brandLockup(false)} provides Australian NEM/WEM electricity market analytics, storage revenue assessment and an AI Decision Engine. Self-service registration is open during public beta; the free plan includes daily Agent-run and API quotas. This clause previously described the platform as invite-only - that wording is retired.`],
        ['2. Brand and former name', (isZh) => `The Service is offered as ${brandLockup(true)} (${brandLockup(false)}). Interfaces, emails and exported report headers dated before 2026-09-06 may carry a former designation (${FORMER_BRAND_NAMES.join(', ')}); it was a UI label only and does not identify the service provider, which is as stated in clause 1. The rename does not break the continuity of these terms.`],
        ['3. Accounts & authorization', 'Users must safeguard credentials and API keys; losses from leaked keys are the user\'s responsibility. Data access within a workspace is role-controlled (owner/admin/analyst/viewer). Accounts and API keys must not be shared, lent or transferred.'],
        ['4. Quotas & usage', 'Each plan includes daily Agent-run and API quotas. Quotas are currently soft (flagged, not blocked); hard enforcement applies once payments launch. Quota policies may change with prior notice.'],
        ['5. Data & IP', 'Market data originates from official public sources such as AEMO and Fingrid; their copyright and licence terms remain with the originating institutions, and our processing creates no rights in the underlying data. Derived metrics, benchmarks and methodology belong to the platform. You may use outputs for internal research and investment decisions, but must not resell or redistribute them or present them as official releases.'],
        ['6. Relationship with AEMO and other sources', (isZh) => aemoNonAffiliation(isZh)],
        ['7. Liability', 'Outputs are not investment advice (see Disclaimer). The platform is not liable for direct losses caused by data-source failures, policy changes or force majeure.'],
        ['8. Acceptable use', 'Use of the Service is subject to the Acceptable Use Policy (/legal/aup), covering automated call volumes, data redistribution and how outputs may be described externally.'],
        ['9. Privacy & data processing', 'See the Privacy Policy (/legal/privacy) for what we collect, the Data Processing Addendum (/legal/dpa) for controller/processor roles, and Cookies & similar technologies (/legal/cookies) for local storage and third-party resource loading.'],
        ['10. Governing law', (isZh) => `These terms are governed by the laws of ${governingLaw(isZh)}, and disputes are submitted to the courts of that jurisdiction. During public beta both parties agree to attempt resolution by negotiation first.`],
        ['11. Changes & contact', (isZh) => `Updated terms are posted on this page and surfaced at sign-in; continued use constitutes acceptance. ${isZh ? '联系渠道：' : 'Contact: '}${contactChannel(isZh)}.`],
      ],
    },
  },

  privacy: {
    zh: {
      title: '隐私政策',
      sections: [
        ['1. 收集的信息', '注册邮箱、显示名、工作空间归属、Agent 查询文本与运行记录、API 调用计量。'],
        ['2. 用途', '提供服务、用量计量与配额管理、服务质量改进。查询文本仅用于服务运行与质量分析，不用于广告。'],
        ['3. 数据共享', '不向第三方出售用户数据。市场数据来源于 AEMO 等公开渠道。'],
        ['4. 存储与安全', '账户凭据以哈希存储；访问令牌有时效且可撤销；API Key 以哈希存储，明文仅创建时展示一次。'],
        // 第 5 条按端点在线状态生成（见文件头）。刻意写成箭头函数而不是在模块顶层求值：
        // import.meta.env 在模块 import 期求值会让配置改动必须重新构建，而这段文案恰恰
        // 需要跟着 flag 走。
        ['5. 用户权利', (isZh) => privacyRightsCopy(import.meta.env, isZh)],
      ],
    },
    en: {
      title: 'Privacy Policy',
      sections: [
        ['1. Data collected', 'Registration email, display name, workspace membership, Agent query text and execution records, API usage metering.'],
        ['2. Usage', 'Service delivery, metering and quota management, service improvement. Query text is used only for service operation and quality analysis, never for advertising.'],
        ['3. Sharing', 'User data is never sold. Market data comes from public sources such as AEMO.'],
        ['4. Storage & security', 'Credentials stored hashed; access tokens are time-limited and revocable; API keys stored hashed, plaintext shown only once at creation.'],
        ['5. Rights', (isZh) => privacyRightsCopy(import.meta.env, isZh)],
      ],
    },
  },
  disclaimer: {
    zh: {
      title: '免责声明',
      sections: [
        ['1. 非投资建议', '本平台全部输出（含 AI 决策引擎、投资测算 NPV/IRR、决策建议）仅为信息与分析参考，不构成投资、交易或运营建议。投资决策须由持牌专业人士评估后自行作出，风险自负。'],
        ['2. 数据口径', '平台部分指标为派生口径（data_grade=derived），由官方公开数据加工而来，与官方统计可能存在差异。所有输出均标注数据等级与覆盖边界，请以标注为准。'],
        ['3. 数据来源', '市场数据来源于 AEMO（Australian Energy Market Operator）等官方公开渠道，版权归原机构所有。平台不保证数据的实时性、完整性与准确性。'],
        ['4. 预测与情景', '预测、情景模拟与蒙特卡洛分布基于历史数据与假设参数，不代表未来实际表现。政策变化（如 AEMC 规则修订、CIS 调整）可能显著改变结论。'],
        ['5. 收益基准', '收益基准（benchmark）为理想算子口径，系统性区别于实际资产收益，不得与第三方指数绝对值直接对比。'],
      ],
    },
    en: {
      title: 'Disclaimer',
      sections: [
        ['1. Not investment advice', 'All outputs (including AI Decision Engine, NPV/IRR estimates and decision suggestions) are for information and analysis only and do not constitute investment, trading or operational advice. Investment decisions must be made independently with licensed professionals, at your own risk.'],
        ['2. Data caliber', 'Some metrics are derived (data_grade=derived), computed from official public data and may differ from official statistics. All outputs carry data-grade and coverage annotations; defer to those annotations.'],
        ['3. Data sources', 'Market data originates from official public sources such as AEMO (Australian Energy Market Operator); copyright remains with the originating institutions. The platform does not guarantee timeliness, completeness or accuracy.'],
        ['4. Forecasts & scenarios', 'Forecasts, scenario simulations and Monte Carlo distributions are based on historical data and assumptions and do not represent future performance. Policy changes (e.g., AEMC rule changes, CIS adjustments) may materially alter conclusions.'],
        ['5. Revenue benchmarks', 'Revenue benchmarks use an ideal-operator caliber and systematically differ from actual asset revenue; they must not be compared by absolute value against third-party indices.'],
      ],
    },
  },

  // ── R2.4 新增三份文件（2026-09-06）────────────────────────────────────────
  // 写作标准与本文件头一致：**每一句都能在代码里找到实现，找不到的写成「已知缺口」**。
  // 法务与代码分叉的时间越长，越没人记得哪一侧是对的。
  dpa: {
    zh: {
      title: '数据处理附录（DPA）',
      sections: [
        ['1. 角色', '对账户与用量数据（第 2 条 a–c 项），本产品运营方决定处理目的与手段，是数据控制者（GDPR 语境为 controller，澳洲《隐私法》语境为 APP entity）。对工作空间内的业务数据（第 2 条 d 项），运营方按客户（组织/工作空间 owner）的指示处理，是处理者（processor）。'],
        ['2. 数据类别与处理目的', 'a) 账户数据：注册邮箱、显示名、密码哈希、邮箱验证状态、组织与工作空间归属、成员角色 —— 用于身份认证与授权。b) 凭据与会话：访问/刷新令牌的哈希与过期时间、API Key 哈希（明文仅创建时展示一次）、Web 会话 —— 用于会话管理与撤销。c) 用量与配额：Agent 运行计数、API 调用计量、作业队列记录 —— 用于配额管理与容量规划（当前为软配额，超额只标记不阻断）。d) 业务数据：Agent 查询文本与执行轨迹、保存的报告与视图、工作空间内的分析输入与结果快照、用户反馈 —— 用于提供服务与可复现性。e) 本地偏好：语言、主题、引导进度存在你的浏览器 localStorage，不经服务端存储（见 /legal/cookies）。'],
        ['3. 处理依据', '对 a)–c) 项，处理为履行服务合同所必需；对 d) 项，按控制者（客户）的指示处理；对日志与安全遥测，基于防止滥用与保障服务安全这一正当利益，不用于用户画像或广告。'],
        ['4. 子处理者', '当前没有第三方 SaaS 子处理者：应用、PostgreSQL、Redis 与产物文件存储均为运营方自有部署。两处例外的第三方网络请求须明示：(i) 页面字体由 Google Fonts CDN 加载，这会使你的 IP 与 User-Agent 送达 Google；(ii) 使用社交登录时，授权流程发生在你与 Google/GitHub 之间（见 /legal/cookies 第 5 条）。如后续引入分析或错误上报服务，将在本条公示后再启用，不追溯启用。'],
        ['5. 安全措施', '口令使用 PBKDF2-HMAC-SHA256 迭代 600,000 次散列（旧参数账户在下一次成功登录时透明升级为当前值）；访问令牌与 API Key 只存哈希、带过期时间且可撤销；撤销同时覆盖会话与令牌两套清单并即时生效；匿名访客身份不具备任何写端点权限；组织与工作空间为双层隔离，跨组织读取需显式归属校验；限流与在途作业计数状态存于服务端共享存储，多进程部署下语义一致。'],
        ['6. 保留与删除', '账户删除请求受理后立即撤销全部会话与令牌，并在 30 天宽限期届满后物理清除：逐表删除该身份在 19 张表中的行，并删除其导出产物文件（含同名元数据文件）；清除由每小时执行一次的周期任务完成，执行结果写入审计流水。宽限期内重新登录可在「账户中心 → 数据与隐私」撤销删除请求。'],
        ['7. 删除的边界（诚实披露）', '以下副本不在自动删除链内，需要时可按第 11 条提出人工请求：(i) 数据库定期备份中的历史快照，按其自身的备份保留周期过期；(ii) 他人工作空间内由你参与的协作产物（保存的报告、Agent 轨迹摘要），这些数据的控制权归该工作空间的成员；(iii) 服务器访问日志中按 IP 聚合的请求记录。我们不声称「即时彻底清除一切痕迹」。'],
        ['8. 跨境传输与数据存放地', '业务数据存储于运营方控制的部署主机，市场数据本身为各机构公开数据。存放法域、机房与运维方名单可按第 11 条联系渠道索取；如你的组织对数据驻留有合同级要求，请在投产使用前提出。'],
        ['9. 数据主体请求', '导出与删除可由已登录用户在账户中心自助完成（端点未启用时通过联系渠道提出）；更正与限制处理请求通过联系渠道提出，我们在 30 天内答复。身份不可核验时（例如用非注册邮箱来信）会先要求验证。'],
        ['10. 已知缺口（公测期）', '以下能力尚未实现，如实列出而不是在文件里假装具备：双因素认证（TOTP）未提供；未指定 GDPR 欧盟代表与数据保护官；无面向客户的独立数据驻留区域选项；备份恢复演练尚未形成对外可查的记录。'],
        ['11. 联系与生效', () => `本附录是服务条款的组成部分。数据处理相关事宜联系：${contactChannel(true)}。生效日期：2026-09-06。`],
      ],
    },
    en: {
      title: 'Data Processing Addendum',
      sections: [
        ['1. Roles', 'For account and usage data (clause 2a-2c) the operator determines purposes and means and is the controller (APP entity under the Australian Privacy Act). For workspace business data (clause 2d) the operator processes on the instructions of the customer (the organisation / workspace owner) and is a processor.'],
        ['2. Data categories & purposes', 'a) Account: registration email, display name, password hash, email-verification state, organisation/workspace membership and roles - authentication and authorization. b) Credentials & sessions: hashed access/refresh tokens with expiry, hashed API keys (plaintext shown once), web sessions - session management and revocation. c) Metering: Agent run counts, API usage units, job-queue records - quotas and capacity planning (quotas are currently soft). d) Business data: Agent query text and execution traces, saved reports and views, analysis inputs and result snapshots, user feedback - service delivery and reproducibility. e) Local preferences: language, theme and onboarding progress live in your browser localStorage, not server-side (see /legal/cookies).'],
        ['3. Lawful basis', 'Clauses 2a-2c are necessary to perform the contract; 2d is processed on the controller\'s instructions; logging and security telemetry rely on the legitimate interest of preventing abuse and keeping the service secure, never on profiling or advertising.'],
        ['4. Sub-processors', 'There are no third-party SaaS sub-processors: the app, PostgreSQL, Redis and artifact storage all run on the operator\'s own deployment. Two third-party network interactions are disclosed explicitly: (i) UI fonts load from the Google Fonts CDN, exposing your IP and User-Agent to Google; (ii) social login redirects you between your identity provider (Google/GitHub) and us (clause 5 of /legal/cookies). Any future analytics or error-reporting service will be listed here before it is enabled, never retroactively.'],
        ['5. Security measures', 'Passwords are hashed with PBKDF2-HMAC-SHA256 at 600,000 iterations, with transparent re-hashing of legacy accounts on next successful login; access tokens and API keys are stored as hashes, expire and are revocable; revocation covers both sessions and tokens and takes effect immediately; the anonymous visitor identity has no write-endpoint privileges; organisations and workspaces are two-level isolated with explicit ownership checks; rate-limit and in-flight job state lives in shared server-side storage so it stays consistent across processes.'],
        ['6. Retention & deletion', 'A deletion request immediately revokes all sessions and tokens, then after a 30-day grace period physically purges the identity\'s rows across 19 tables and deletes its exported artifact files (including metadata sidecars). An hourly scheduled job performs the sweep and writes an audit record. Signing in again within the grace period allows cancelling the request under Account -> Data & privacy.'],
        ['7. Limits of deletion (honest disclosure)', 'These copies are outside the automated purge and can be requested manually under clause 11: (i) historical snapshots inside scheduled database backups, which expire on their own retention schedule; (ii) collaborative artefacts inside other people\'s workspaces (saved reports, Agent trace summaries) controlled by those members; (iii) IP-aggregated request records in server access logs. We do not claim instantaneous erasure of every trace.'],
        ['8. Transfers & data location', 'Business data is stored on hosts controlled by the operator; the underlying market data is public. Hosting jurisdiction, facility and operator list are available on request via clause 11; if your organisation needs contractual data-residence terms, raise them before production use.'],
        ['9. Data subject requests', 'Export and deletion are self-service for signed-in users (or via the contact channel while the endpoints are disabled); rectification and restriction requests go through the contact channel and are answered within 30 days. Unverifiable requests (e.g. email from a non-registered address) are met with a verification step.'],
        ['10. Known gaps during public beta', 'Not implemented, listed rather than glossed over: no two-factor authentication (TOTP); no designated EU representative or DPO; no customer-selectable data-residence region; backup-restore drills are not yet documented externally.'],
        ['11. Contact & effective date', () => `This addendum forms part of the Terms of Service. Data processing enquiries: ${contactChannel(false)}. Effective 2026-09-06.`],
      ],
    },
  },

  aup: {
    zh: {
      title: '可接受使用政策',
      sections: [
        ['1. 适用范围', '本政策适用于通过网页、API 与 AI 决策引擎对本产品的全部访问，包括匿名访客态。与服务条款冲突时，以本政策中更具体的限制为准。'],
        ['2. 账户与凭据', '不得以规避配额为目的注册多个账户；不得共享账户或 API Key；不得在请求中提交他人的个人数据或凭据。发现凭据泄露请立即在账户中心撤销并重新签发。'],
        ['3. 调用与自动化', '自动化调用必须使用带 API Key 的请求并遵守响应中的配额与限流提示；不得绕过限流、重放已撤销的令牌、探测未公开端点，或对本平台及上游数据源实施爬虫式批量抓取以构建镜像服务。'],
        ['4. 数据使用与再分发', '允许：为内部研究、尽职调查与投资决策使用输出；引用你自己的导出结果。禁止：转售或公开再分发原始/导出数据集、去除数据等级与来源标注、把派生指标（data_grade=derived）表述为官方统计、把本产品输出当作官方数据源内容发布。'],
        ['5. 对外表述', (isZh) => `不得以任何方式暗示获得数据源机构的授权或背书。${aemoNonAffiliation(isZh)} 面向第三方提供投资建议时，须同时披露本产品的输出不构成投资建议。`],
        ['6. 内容与隔离边界', '不得利用查询输入上传、嵌入或传播恶意代码、侵权内容或超出法律允许范围的个人信息；不得试图绕过组织与工作空间隔离读取未授权数据（该边界在服务端强制，不以界面可见性为准）。'],
        ['7. 违规处置', '视情节采取：限流收紧、作业排队降级、会话撤销、API Key 吊销、工作空间/组织暂停，直至账户删除。处置结果与理由会通知到注册邮箱（公测期由人工复核后执行）；你可以按第 8 条申诉。'],
        ['8. 申诉与变更', (isZh) => `如认为处置有误，请通过 ${contactChannel(isZh)} 提交申诉，我们复核后答复。本政策更新将在本页公示，生效前不追溯适用于已发生的行为。`],
      ],
    },
    en: {
      title: 'Acceptable Use Policy',
      sections: [
        ['1. Scope', 'This policy covers all access to the Service through the web app, the API and the AI Decision Engine, including anonymous visitor sessions. Where it conflicts with the Terms of Service, the more specific restriction here applies.'],
        ['2. Accounts & credentials', 'Do not register additional accounts to evade quotas; do not share accounts or API keys; do not submit other people\'s personal data or credentials in requests. If a credential leaks, revoke it in the Account Center and issue a new one.'],
        ['3. Calls & automation', 'Automated calls must use an API key and honour the quota and rate-limit signals in responses. Do not bypass rate limits, replay revoked tokens, probe undocumented endpoints, or scrape this platform or its upstream sources to build a mirror service.'],
        ['4. Data use & redistribution', 'Permitted: using outputs for internal research, diligence and investment decisions; citing your own exports. Prohibited: reselling or republishing raw/exported datasets, stripping data-grade or provenance annotations, presenting derived metrics (data_grade=derived) as official statistics, or publishing our outputs as if they were official source material.'],
        ['5. External representation', (isZh) => `Nothing may imply endorsement or authorisation by the data sources. ${aemoNonAffiliation(isZh)} When giving investment advice to third parties based on our output, disclose that our output is not investment advice.`],
        ['6. Content & isolation boundaries', 'Do not use query inputs to upload or propagate malicious code, infringing content, or personal data beyond what the law permits; do not attempt to read data outside your organisation/workspace - that boundary is enforced server-side and does not depend on what the UI shows.'],
        ['7. Enforcement', 'Depending on severity: tighter rate limits, job-queue downgrades, session revocation, API key revocation, workspace/organisation suspension, up to account deletion. Actions and reasons are notified to the registered email (reviewed manually during public beta); you may appeal under clause 8.'],
        ['8. Appeals & changes', (isZh) => `If you believe an action was wrong, appeal via ${contactChannel(isZh)}. Updates are posted on this page and are not applied retroactively to conduct that predates them.`],
      ],
    },
  },

  cookies: {
    zh: {
      title: 'Cookie 与同类技术',
      sections: [
        ['1. 结论先说', '本产品不下发任何 Cookie（后端全文没有一处 Set-Cookie），也不使用第三方广告、跟踪或社交插件 Cookie。你在这个站点上的活动不会被跨站跟踪标识符记录。'],
        ['2. 我们实际用的是什么', '登录凭据（访问令牌与刷新令牌）存在浏览器的 localStorage，键名 aus_auth_v1，随每个 API 请求以 Authorization 头发出。'],
        ['3. 为什么不是 httpOnly Cookie', '这是已知权衡而不是疏漏：localStorage 无法防御 XSS（页面脚本可读令牌），但也就此免除了 CSRF 面与 SameSite/域配置的复杂度；我们把它登记为待改造项（迁移到 httpOnly Cookie 需同步引入 CSRF 防护）。在改造完成前，请不要在不受信任的浏览器扩展或共享机器上保持登录。'],
        ['4. 本地存储清单', '除 aus_auth_v1 外还有：app_lang（界面语言）、app_theme（明暗主题）、app_autonomy_tier（Agent 自主等级）、aus_tour_v1 与 aus_onboarding_v1_*（新手引导进度）、aus_saved_views_v1（自建视图）、tab_{market}（上次打开的标签页）、developer_portal_api_key（仅临时缓存你自己刚创建的 Key）。这些数据只存在于你的浏览器，清除站点数据即一并删除。'],
        ['5. 社交登录（如已启用）', '使用 Google 登录时跳转到 accounts.google.com，我们请求 openid、email、profile 三个权限，收到的是账户标识符、邮箱、显示名与头像地址；使用 GitHub 登录时跳转到 github.com 授权页，我们请求 read:user 与 user:email，因为 GitHub 账户的主邮箱可能被设为私有，需要再从 /user/emails 取「主且已验证」的那一条。授权期间你与身份提供方之间的交互不受我们控制，其条款与隐私政策由该提供方适用。两种情况下我们都不请求任何写入你账户数据的权限。'],
        ['6. 第三方资源加载', '页面样式表引用 Google Fonts（fonts.googleapis.com 与 fonts.gstatic.com）。加载时 Google 会收到你的 IP、User-Agent 与 Referer。除该字体请求与上一节的登录跳转外，页面上没有任何第三方脚本或插件。'],
        ['7. 分析与错误上报', '当前未启用任何产品分析或会话回放工具。若后续启用，本页将先说明采集范围、保留期与关闭方式，再上线采集；会话回放只会在全文本与输入框遮蔽开启后启用。'],
        ['8. 管理与撤回', '在浏览器设置中清除本站点站点数据即可删除全部本地凭据与偏好（等效于退出登录，且服务端令牌本身已带过期时间）。你的浏览器与服务端都不存在需要额外撤回的跟踪 Cookie。'],
      ],
    },
    en: {
      title: 'Cookies & similar technologies',
      sections: [
        ['1. Short answer', 'The Service sets no cookies at all (there is not a single Set-Cookie in the backend) and uses no third-party advertising, tracking or social-plugin cookies. Your activity here is not tied to a cross-site tracking identifier.'],
        ['2. What we actually use', 'Sign-in credentials (access and refresh tokens) are stored in browser localStorage under aus_auth_v1 and sent as an Authorization header on each API request.'],
        ['3. Why not httpOnly cookies', 'This is a known trade-off, not an oversight: localStorage is exposed to XSS (page scripts can read the token) but also removes the CSRF surface and SameSite/domain configuration risk. It is logged as a planned change - moving to httpOnly cookies requires CSRF protection at the same time. Until then, do not stay signed in on shared machines or browsers with untrusted extensions.'],
        ['4. Local storage inventory', 'Besides aus_auth_v1: app_lang (UI language), app_theme (light/dark), app_autonomy_tier (Agent autonomy level), aus_tour_v1 and aus_onboarding_v1_* (tour progress), aus_saved_views_v1 (your saved views), tab_{market} (last open tab) and developer_portal_api_key (a temporary cache of a key you just created). All of it lives only in your browser.'],
        ['5. Social login (when enabled)', 'Google sign-in redirects to accounts.google.com; we request the openid, email and profile scopes and receive an account identifier, email, display name and avatar URL. GitHub sign-in redirects to github.com; we request read:user and user:email because a GitHub primary email may be set private, so we read the "primary and verified" entry from /user/emails. Your interaction with the identity provider during that redirect is governed by their terms and privacy policy. Neither flow asks for permission to write to your account.'],
        ['6. Third-party resource loads', 'The stylesheet references Google Fonts (fonts.googleapis.com and fonts.gstatic.com), which receive your IP, User-Agent and Referer. Apart from that font request and the login redirects above, the page loads no third-party scripts or plugins.'],
        ['7. Analytics & error reporting', 'No product analytics or session replay is enabled today. If introduced, this page will document the collected scope, retention and opt-out before any collection starts; session replay would only be enabled with full text and input masking on.'],
        ['8. Control & withdrawal', 'Clearing site data in your browser removes all local credentials and preferences (equivalent to signing out; server-side tokens expire on their own regardless). There is no tracking cookie left behind that would need a separate withdrawal.'],
      ],
    },
  },
};

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

// 路由末段就是文档 key（main.jsx 只按首段 'legal' 分到本页），所以新增一份文件只要往
// TOPICS 里加一项 —— 若继续往 currentTopic 里堆 if，症状是「页面能打开但永远显示条款」，
// 没有任何报错，属于最容易漏上线的那类静默失败。
const TOPICS = ['terms', 'privacy', 'disclaimer', 'dpa', 'aup', 'cookies'];

const TAB_LABELS = {
  terms: ['服务条款', 'Terms'],
  privacy: ['隐私政策', 'Privacy'],
  disclaimer: ['免责声明', 'Disclaimer'],
  dpa: ['数据处理附录', 'DPA'],
  aup: ['可接受使用', 'AUP'],
  cookies: ['Cookie 与本地存储', 'Cookies'],
};

function currentTopic() {
  const path = (globalThis.location.pathname || '').replace(/\/+$/, '');
  const last = path.split('/').pop();
  return TOPICS.includes(last) ? last : 'terms';
}

export default function LegalPage() {
  const lang = readLang();
  const zh = lang === 'zh';
  const topic = currentTopic();
  const content = CONTENT[topic][zh ? 'zh' : 'en'];

  const tabs = TOPICS.map((id) => ({
    id,
    path: `/legal/${id}`,
    label: zh ? TAB_LABELS[id][0] : TAB_LABELS[id][1],
  }));

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-6 py-4">
          <a href="/" className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)] hover:text-[var(--color-text)]">
            ← {brandEyebrow(zh)}
          </a>
          {/* 六份文件在窄屏会挤出横向滚动，flex-wrap 让它换行而不是缩字号。 */}
          <nav className="flex flex-wrap gap-1">
            {tabs.map((t) => (
              <a
                key={t.id}
                href={t.path}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                  topic === t.id
                    ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                    : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'
                }`}
              >
                {t.label}
              </a>
            ))}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-6 py-10">
        <h1 className="mb-6 font-serif text-2xl text-[var(--color-text)]">{content.title}</h1>
        <div className="space-y-6">
          {content.sections.map(([heading, body]) => (
            <section key={heading} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
              <h2 className="mb-2 text-sm font-semibold text-[var(--color-text)]">{heading}</h2>
              {/* body 允许是函数：隐私页第 5 条要按 flag 现算（见文件头）。函数体不走
                  React child 渲染路径，因此必须在这里显式求值 —— 直接把函数交给 {body}
                  会抛「Functions are not valid as a React child」。 */}
              <p className="text-xs leading-relaxed text-[var(--color-muted)]">
                {typeof body === 'function' ? body(zh) : body}
              </p>
            </section>
          ))}
        </div>
        <p className="mt-8 text-[10px] text-[var(--color-muted)]">
          {zh ? '最后更新：2026-09-06' : 'Last updated: 2026-09-06'}
        </p>
      </main>
    </div>
  );
}
