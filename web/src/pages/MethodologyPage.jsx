// web/src/pages/MethodologyPage.jsx
// 方法论白皮书页（R6.1，2026-09-06）：/methodology，公开可达（与 /pricing、/legal 同级）。
//
// 定价页 Pro 套餐承诺了「方法论白皮书」，但产品里此前不存在这份东西 —— 那是一句没有
// 出处的承诺。本页就是出处：内容真源是 docs/architecture/NEM-BESS收益基准方法论.md
// （bess_benchmark_v1）与 backend/engines/benchmark_engine.py 的常量。
//
// 写作纪律与 LegalPage 相同，并多一条：
// 1. 只写系统当前真的在做的事 —— 每一句都对应一个可验证的实现（engine 常量 / 登记表 / 测试）；
// 2. caveat 四条必须与 benchmark_engine.py 的 BENCHMARK_CAVEATS **逐字一致**（不是意译）：
//    methodologyReachability.test.js 会从后端源码提取这四条，对页面源码逐条断言；
// 3. 参考资产三参数（100 MW / 200 MWh / RTE 0.85）必须与 data/assumptions_registry.json
//    的 benchmark_reference_battery 条目一致，登记表改了页面没改 = 硬门变红；
// 4. 品牌名一律取自 lib/brand.js，本页不出现硬编码产品名。

import { brandEyebrow } from '../lib/brand.js';
import { useEffect } from 'react';

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

// 逐字同步自 backend/engines/benchmark_engine.py 的 BENCHMARK_CAVEATS（zh）。
// en 为站点侧翻译；对外口径以中文源为准，两列不得各改各的。
const CAVEATS = [
  '理想日内循环套利：每日最高价/最低价各取电池时长对应时段数放电/充电（2h 电池每日一次满充放），时间粒度按数据实际推断',
  '不含 FCAS / 容量 / CIS 等其他价值流',
  '不含网络费与市场费',
  'derived 口径，禁止与 Modo 等第三方指数绝对值直接对比',
];

const CONTENT = {
  zh: {
    title: 'NEM BESS 收益基准指数 · 方法论白皮书',
    meta: 'methodology_version = bess_benchmark_v1 · 更新于 2026-09-06',
    intro: '本文是 NEM BESS 收益基准指数的正式方法论。实现见 backend/engines/benchmark_engine.py，API 入口为 GET /api/benchmark/nem-bess-index 与 /api/benchmark/nem-bess-region-compare，对话入口为 Agent 工具 bess_revenue_benchmark。任何口径变更必须同步本文并升级 methodology_version。',
    sections: [
      ['1. 本白皮书回答什么', [
        '回答的问题：「一个参考储能资产在某区域的市场收益能力是多少、趋势如何。」',
        '用途：市场进入判断的收益锚定、投资测算的市场对照、收益异动归因。',
        '数据等级：derived（派生口径，非观测收入）—— 指数由公开结算价按固定公式推导，不是任何真实资产的记账收益。',
        '明确禁止：与 Modo、Aurora 等第三方收益指数的绝对值直接对比。只允许比方向与量级，理由见第 6 节的偏差分析。',
      ]],
      ['2. 参考资产定义', [
        '功率 100 MW；容量 200 MWh（2 小时）；往返效率 RTE 0.85。',
        '三个参数登记于 data/assumptions_registry.json 的 benchmark_reference_battery 条目；实现侧从登记表读取，登记表不可用时回落同值默认，行为不变。参数变更必须走登记表纪律（同步记录 modified_by 与 last_calibrated）。',
        '运行假设：理想算子 —— 完美 foresight，无投标摩擦、无竞争、无停运。',
        '参考资产量级与 Modo 指数参考资产一致（2h 电网级储能），保证量纲可比。',
      ]],
      ['3. 计算口径：理想日内循环套利', [
        '对窗口内每个自然日独立计算：将该日全部结算价排序；放电取最高价 cycle_intervals 个时段，充电取最低价同样数量时段；cycle_intervals = round(电池时长 / 时段长度)（2h 电池在 5 分钟粒度下为 24 个时段，30 分钟粒度下为 4 个时段）。',
        '日放电能量 = min(时段数 × 功率 × 时段长度, 电池容量)；充电能量 = 放电能量 / RTE。',
        '日净收入 = 放电能量 × 放电均价 − 充电能量 × 充电均价。',
        '非负钳制：净收入为负的日视为不循环（理想算子不亏损运行），计 0。',
        '月度净收入 = 当月各日之和；年化指数 index = 月度净收入 / 功率 × 12 / 1000，单位 kAUD/MW/年。',
        '口径特征：每日一次满充放，不做多循环/跨日优化 —— 对 2h 电池等价性差异很小，换来算法透明可复现；不含 FCAS / 容量 / CIS / 任何合约收入；不含网络费、市场费、退化成本。',
      ]],
      ['4. 数据源与粒度', [
        '数据源：AEMO 结算价（trading_price_<year> 分年表，region_id + rrp_aud_mwh）。',
        '粒度从数据推断：interval_hours = 24 / 日均数据点数，库内可达 5 分钟粒度；循环时段数与完整性分母随粒度联动。',
        '窗口：滚动 12 个完整自然月（默认），当前未完结月永远排除。',
        '完整性：月度完整性 = 实际点数 / 期望点数；≥95% 视为完整月，latest 与区域对比只取完整月；<90% 打 incomplete_month 告警；无数据月打 no_data。',
        '容错：跨年表自动拼接；缺失年表跳过并由完整性告警兜底，不抛裸 SQL 错误。',
      ]],
      ['5. 覆盖边界（随每次输出强制暴露）', [
        '输出强制携带 coverage_mode（arbitrage-only, FCAS not included）、caveats、metadata.data_grade=derived 与完整性字段 —— 调用方拿到的每个结果都自带这组边界，不存在「裸数值」出口。',
        'caveat 固定四条：',
      ]],
      ['6. 已知偏差与第三方校准记录', [
        '偏差来源（我们 vs 第三方实际收益指数）：偏高 —— 理想算子（完美 foresight + 无竞争压价 + 无停运，实际资产做不到）；偏低 —— 只含套利（第三方实际收益含 FCAS/合约等残余价值流）；中性 —— 参考资产同量级（2h 电池口径一致）。',
        '校准记录（每月至少一条，对外可信度证据链）：',
        '使用规则：对外引用时只允许表述为「与 Modo 指数方向一致，绝对值因理想算子口径系统性偏高」，不得给出换算系数。',
      ]],
      ['7. 版本与维护', [
        'methodology_version = bess_benchmark_v1；口径变更 → 升版本号 + 更新本文 + 假设登记表同步。',
        '校准记录每月追加；参考资产参数变更走假设登记库纪律。',
        '相关测试：tests/test_benchmark_engine.py（公式 / 完整性 / 窗口 / 区域对比 13 用例）。',
      ]],
    ],
    caveatsHeading: '固定 caveats（与实现逐字一致）',
    calibrationHeading: '校准记录表',
    calibrationHead: ['日期', '对象', '我们', '第三方（Modo）', '结论'],
    calibrationRows: [
      ['2026-08-13', 'NSW1 压缩趋势 2025-11 → 2026-06', '297 → 50 kAUD/MW/年（−83%）', '$148k（2024）→ $29k（2026-05）/MW/年（−80%）', '方向与压缩幅度一致'],
      ['2026-08-13', 'NSW1 2026-06 vs Modo 2026-05', '50.03 kAUD/MW/年', '$29k/MW/年', '绝对值偏高约 1.7×，归因理想算子（无竞争/摩擦），量级同阶'],
      ['2026-08-13', 'SA1 2026-06 尖峰', '410 kAUD/MW/年', '无对应公开值', '待补（SA 高波动区域特征，留档观察）'],
    ],
  },
  en: {
    title: 'NEM BESS Revenue Benchmark Index · Methodology Whitepaper',
    meta: 'methodology_version = bess_benchmark_v1 · Updated 2026-09-06',
    intro: 'This is the formal methodology for the NEM BESS Revenue Benchmark Index. Implementation: backend/engines/benchmark_engine.py; API entry points GET /api/benchmark/nem-bess-index and /api/benchmark/nem-bess-region-compare; conversational entry point the bess_revenue_benchmark agent tool. Any change to the calculation basis must update this page and bump methodology_version.',
    sections: [
      ['1. What this whitepaper answers', [
        'The question: "What is the market revenue capability of a reference storage asset in a given region, and how does it trend?"',
        'Use cases: revenue anchoring for market-entry decisions, market comparison for investment models, attribution of revenue anomalies.',
        'Data grade: derived (derived basis, not observed revenue) — the index is derived from public settlement prices via a fixed formula, not the booked revenue of any real asset.',
        'Explicitly prohibited: direct absolute-value comparison with third-party revenue indices (Modo, Aurora, etc.). Direction and order of magnitude only; see the bias analysis in section 6.',
      ]],
      ['2. Reference asset definition', [
        'Power 100 MW; energy 200 MWh (2-hour); round-trip efficiency 0.85.',
        'The three parameters are registered in data/assumptions_registry.json (benchmark_reference_battery); the implementation reads them from the registry and falls back to identical defaults if the registry is unavailable. Parameter changes must follow the registry discipline (recording modified_by and last_calibrated).',
        'Operating assumption: an ideal operator — perfect foresight, no bidding friction, no competition, no outages.',
        'The reference asset matches the scale of the Modo index reference asset (2h grid-scale storage), keeping units comparable.',
      ]],
      ['3. Calculation basis: ideal daily-cycle arbitrage', [
        'Each calendar day in the window is computed independently: sort that day\'s settlement prices; discharge over the cycle_intervals most expensive intervals, charge over an equal number of cheapest intervals; cycle_intervals = round(battery duration / interval length) (24 intervals for a 2h battery at 5-minute granularity, 4 at 30-minute granularity).',
        'Daily discharged energy = min(intervals × power × interval length, battery energy); charged energy = discharged energy / RTE.',
        'Daily net revenue = discharged energy × average discharge price − charged energy × average charge price.',
        'Non-negative clamp: a day with negative net revenue is treated as a non-cycling day (an ideal operator does not run at a loss) and counted as 0.',
        'Monthly net revenue = sum over days; annualised index = monthly net revenue / power × 12 / 1000, in kAUD/MW/year.',
        'Basis characteristics: one full charge/discharge cycle per day, no multi-cycling or cross-day optimisation — for a 2h battery the equivalence gap is small, in exchange for a transparent, reproducible algorithm; excludes FCAS / capacity / CIS / any contract revenue; excludes network charges, market fees and degradation costs.',
      ]],
      ['4. Data source and granularity', [
        'Data source: AEMO settlement prices (per-year trading_price_<year> tables, region_id + rrp_aud_mwh).',
        'Granularity is inferred from the data: interval_hours = 24 / average daily data points; the database carries 5-minute granularity where available; cycle interval counts and completeness denominators follow the inferred granularity.',
        'Window: rolling 12 complete calendar months (default); the current unfinished month is always excluded.',
        'Completeness: monthly completeness = actual points / expected points; ≥95% counts as a complete month, and latest and region comparison use complete months only; <90% raises an incomplete_month warning; months with no data raise no_data.',
        'Fault tolerance: cross-year tables are stitched automatically; a missing year table is skipped with a completeness warning instead of a raw SQL error.',
      ]],
      ['5. Coverage boundary (exposed with every response)', [
        'Every output carries coverage_mode (arbitrage-only, FCAS not included), caveats, metadata.data_grade=derived and completeness fields — there is no "bare number" exit: every caller sees this boundary alongside the result.',
        'The four fixed caveats:',
      ]],
      ['6. Known bias and third-party calibration record', [
        'Bias sources (us vs third-party realised revenue indices): high — the ideal operator (perfect foresight, no competition-driven price erosion, no outages; real assets cannot do this); low — arbitrage only (third-party realised revenue includes residual value streams such as FCAS and contracts); neutral — matching reference asset scale (same 2h basis).',
        'Calibration record (at least one entry per month, the credibility evidence chain):',
        'Usage rule: external references may only state "directionally consistent with the Modo index, systematically higher in absolute value due to the ideal-operator basis", and must not quote a conversion factor.',
      ]],
      ['7. Versioning and maintenance', [
        'methodology_version = bess_benchmark_v1; any change to the calculation basis bumps the version, updates this page and syncs the assumptions registry.',
        'Calibration records are appended monthly; reference asset parameter changes follow the assumptions registry discipline.',
        'Related tests: tests/test_benchmark_engine.py (formula / completeness / window / region comparison, 13 cases).',
      ]],
    ],
    caveatsHeading: 'Fixed caveats (verbatim from the implementation)',
    calibrationHeading: 'Calibration record',
    calibrationHead: ['Date', 'Subject', 'Ours', 'Third party (Modo)', 'Conclusion'],
    calibrationRows: [
      ['2026-08-13', 'NSW1 compression trend 2025-11 → 2026-06', '297 → 50 kAUD/MW/year (−83%)', '$148k (2024) → $29k (2026-05)/MW/year (−80%)', 'Direction and compression magnitude consistent'],
      ['2026-08-13', 'NSW1 2026-06 vs Modo 2026-05', '50.03 kAUD/MW/year', '$29k/MW/year', 'Absolute value ~1.7× higher, attributed to the ideal operator (no competition/friction); same order of magnitude'],
      ['2026-08-13', 'SA1 2026-06 spike', '410 kAUD/MW/year', 'No public counterpart', 'Pending (SA high-volatility regional signature, logged for observation)'],
    ],
  },
};

export default function MethodologyPage() {
  const lang = readLang();
  const zh = lang === 'zh';
  const t = zh ? CONTENT.zh : CONTENT.en;

  // P2-3 Onboarding 信号：查看方法论白皮书（2026-09-06）
  useEffect(() => {
    import('../lib/onboarding.js').then((m) => m.markOnboardingStep('methodology')).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
          <a href="/" className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)] hover:text-[var(--color-text)]">
            ← {brandEyebrow(zh)}
          </a>
          <a href="/pricing" className="text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">
            {zh ? '定价' : 'Pricing'}
          </a>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-12">
        <div className="mb-10">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{brandEyebrow(zh)}</div>
          <h1 className="mt-2 font-serif text-3xl text-[var(--color-text)]">{t.title}</h1>
          <p className="mt-2 font-mono text-xs text-[var(--color-muted)]">{t.meta}</p>
          <p className="mt-4 text-sm leading-relaxed text-[var(--color-text)]">{t.intro}</p>
        </div>

        {t.sections.map(([heading, paragraphs]) => (
          <section key={heading} className="mb-10">
            <h2 className="mb-3 font-serif text-xl text-[var(--color-text)]">{heading}</h2>
            <ul className="space-y-2">
              {paragraphs.map((p) => (
                <li key={p} className="flex items-start gap-2 text-sm leading-relaxed text-[var(--color-text)]">
                  <span className="mt-1 text-[var(--color-muted)]">·</span>
                  <span>{p}</span>
                </li>
              ))}
            </ul>
            {heading.startsWith('5.') && (
              <ol className="mt-4 space-y-2 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
                {CAVEATS.map((c, i) => (
                  <li key={c} className="flex items-start gap-2 text-sm leading-relaxed text-[var(--color-text)]">
                    <span className="font-semibold text-[var(--color-primary)]">{i + 1}.</span>
                    <span>{c}</span>
                  </li>
                ))}
              </ol>
            )}
            {heading.startsWith('6.') && (
              <div className="mt-4">
                <h3 className="mb-2 text-sm font-semibold text-[var(--color-text)]">{t.calibrationHeading}</h3>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="border-b border-[var(--color-border)] text-left text-[var(--color-muted)]">
                        {t.calibrationHead.map((h) => (
                          <th key={h} className="px-2 py-2 font-semibold">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="text-[var(--color-text)]">
                      {t.calibrationRows.map((row) => (
                        <tr key={row[1]} className="border-b border-[var(--color-border)]">
                          {row.map((cell, i) => (
                            <td key={i} className="px-2 py-2 align-top">{cell}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </section>
        ))}

        <div className="mt-8 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs text-[var(--color-muted)]">
          <a href="/pricing" className="hover:text-[var(--color-text)]">{zh ? '定价与套餐' : 'Pricing & plans'}</a>
          <a href="/legal/disclaimer" className="hover:text-[var(--color-text)]">{zh ? '免责声明' : 'Disclaimer'}</a>
          <a href="/legal/terms" className="hover:text-[var(--color-text)]">{zh ? '服务条款' : 'Terms'}</a>
        </div>
      </main>
    </div>
  );
}
