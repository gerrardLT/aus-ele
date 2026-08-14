// web/src/pages/LegalPage.jsx
// 法务合规页（P1-5，2026-08-14）：/legal/terms | /legal/privacy | /legal/disclaimer
// 核心为免责声明：非投资建议 + derived 数据口径 + AEMO 数据来源声明。
// zh/en 双语内联（篇幅大且低频，不入 translations.js）。

const CONTENT = {
  terms: {
    zh: {
      title: '服务条款',
      sections: [
        ['1. 服务说明', '本平台（AEMO Intelligence）提供澳洲 NEM/WEM 电力市场数据分析、储能收益判断与 AI 编排分析服务。平台为邀请制，账户与工作空间由管理员创建与授权。'],
        ['2. 账户与授权', '用户须妥善保管账户凭据与 API Key；API Key 泄露导致的损失由用户自行承担。工作空间内的数据访问受角色权限控制（owner/admin/analyst/viewer）。'],
        ['3. 配额与用量', '各套餐含 Agent 运行与 API 调用日配额。当前为软配额（超额标记不阻断）；支付功能就绪后将启用硬配额。平台保留调整配额策略的权利，调整前将提前告知。'],
        ['4. 数据与知识产权', '市场数据来源于 AEMO 等官方公开渠道，其版权归原机构所有。平台加工产生的派生指标、基准与方法论归平台所有。'],
        ['5. 免责与责任限制', '平台输出不构成投资建议（详见免责声明）。因数据源故障、政策变化或不可抗力导致的分析偏差，平台不承担直接损失责任。'],
        ['6. 条款变更', '条款更新将在平台内公示；继续使用视为接受变更后的条款。'],
      ],
    },
    en: {
      title: 'Terms of Service',
      sections: [
        ['1. Service', 'AEMO Intelligence provides Australian NEM/WEM electricity market analytics, storage revenue assessment and AI orchestrated analysis. The platform is invite-only; accounts and workspaces are created and authorized by administrators.'],
        ['2. Accounts & authorization', 'Users must safeguard credentials and API keys; losses from leaked keys are the user\'s responsibility. Data access within a workspace is role-controlled (owner/admin/analyst/viewer).'],
        ['3. Quotas & usage', 'Each plan includes daily Agent-run and API quotas. Quotas are currently soft (flagged, not blocked); hard enforcement applies once payments launch. Quota policies may change with prior notice.'],
        ['4. Data & IP', 'Market data originates from official public sources such as AEMO; copyright remains with the originating institutions. Derived metrics, benchmarks and methodology are the platform\'s intellectual property.'],
        ['5. Liability', 'Outputs are not investment advice (see Disclaimer). The platform is not liable for direct losses caused by data-source failures, policy changes or force majeure.'],
        ['6. Changes', 'Updated terms are posted on the platform; continued use constitutes acceptance.'],
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
        ['5. 用户权利', '可申请导出或删除账户数据；登出后访问令牌即失效。'],
      ],
    },
    en: {
      title: 'Privacy Policy',
      sections: [
        ['1. Data collected', 'Registration email, display name, workspace membership, Agent query text and execution records, API usage metering.'],
        ['2. Usage', 'Service delivery, metering and quota management, service improvement. Query text is used only for service operation and quality analysis, never for advertising.'],
        ['3. Sharing', 'User data is never sold. Market data comes from public sources such as AEMO.'],
        ['4. Storage & security', 'Credentials stored hashed; access tokens are time-limited and revocable; API keys stored hashed, plaintext shown only once at creation.'],
        ['5. Rights', 'Users may request export or deletion of account data; tokens are invalidated on logout.'],
      ],
    },
  },
  disclaimer: {
    zh: {
      title: '免责声明',
      sections: [
        ['1. 非投资建议', '本平台全部输出（含 AI 编排分析、投资测算 NPV/IRR、决策建议）仅为信息与分析参考，不构成投资、交易或运营建议。投资决策须由持牌专业人士评估后自行作出，风险自负。'],
        ['2. 数据口径', '平台部分指标为派生口径（data_grade=derived），由官方公开数据加工而来，与官方统计可能存在差异。所有输出均标注数据等级与覆盖边界，请以标注为准。'],
        ['3. 数据来源', '市场数据来源于 AEMO（Australian Energy Market Operator）等官方公开渠道，版权归原机构所有。平台不保证数据的实时性、完整性与准确性。'],
        ['4. 预测与情景', '预测、情景模拟与蒙特卡洛分布基于历史数据与假设参数，不代表未来实际表现。政策变化（如 AEMC 规则修订、CIS 调整）可能显著改变结论。'],
        ['5. 收益基准', '收益基准（benchmark）为理想算子口径，系统性区别于实际资产收益，不得与第三方指数绝对值直接对比。'],
      ],
    },
    en: {
      title: 'Disclaimer',
      sections: [
        ['1. Not investment advice', 'All outputs (including AI orchestrated analysis, NPV/IRR estimates and decision suggestions) are for information and analysis only and do not constitute investment, trading or operational advice. Investment decisions must be made independently with licensed professionals, at your own risk.'],
        ['2. Data caliber', 'Some metrics are derived (data_grade=derived), computed from official public data and may differ from official statistics. All outputs carry data-grade and coverage annotations; defer to those annotations.'],
        ['3. Data sources', 'Market data originates from official public sources such as AEMO (Australian Energy Market Operator); copyright remains with the originating institutions. The platform does not guarantee timeliness, completeness or accuracy.'],
        ['4. Forecasts & scenarios', 'Forecasts, scenario simulations and Monte Carlo distributions are based on historical data and assumptions and do not represent future performance. Policy changes (e.g., AEMC rule changes, CIS adjustments) may materially alter conclusions.'],
        ['5. Revenue benchmarks', 'Revenue benchmarks use an ideal-operator caliber and systematically differ from actual asset revenue; they must not be compared by absolute value against third-party indices.'],
      ],
    },
  },
};

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

function currentTopic() {
  const path = globalThis.location.pathname || '';
  if (path.includes('/legal/privacy')) return 'privacy';
  if (path.includes('/legal/disclaimer')) return 'disclaimer';
  return 'terms';
}

export default function LegalPage() {
  const lang = readLang();
  const zh = lang === 'zh';
  const topic = currentTopic();
  const content = CONTENT[topic][zh ? 'zh' : 'en'];

  const tabs = [
    { id: 'terms', path: '/legal/terms', label: zh ? '服务条款' : 'Terms' },
    { id: 'privacy', path: '/legal/privacy', label: zh ? '隐私政策' : 'Privacy' },
    { id: 'disclaimer', path: '/legal/disclaimer', label: zh ? '免责声明' : 'Disclaimer' },
  ];

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
          <a href="/" className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)] hover:text-[var(--color-text)]">
            ← AEMO Intelligence
          </a>
          <nav className="flex gap-1">
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
              <p className="text-xs leading-relaxed text-[var(--color-muted)]">{body}</p>
            </section>
          ))}
        </div>
        <p className="mt-8 text-[10px] text-[var(--color-muted)]">
          {zh ? '最后更新：2026-08-14' : 'Last updated: 2026-08-14'}
        </p>
      </main>
    </div>
  );
}
