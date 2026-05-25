import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('DataQualityBadge renders data grade and metadata helpers', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/DataQualityBadge.jsx'), 'utf8');
  assert.match(source, /formatDataGradeLabel/);
  assert.match(source, /formatCoverageModeLabel/);
  assert.match(source, /formatFreshnessLabel/);
  assert.match(source, /formatMetadataUnitLabel/);
  assert.match(source, /formatReadinessStatusLabel/);
  assert.match(source, /metadata\?\.interval_minutes/);
  assert.match(source, /normalizedTags/);
});

test('PageSection spans the full 12-column content grid', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/PageSection.jsx'), 'utf8');
  assert.match(source, /fullWidthInGrid \? 'col-span-12 ' : ''/);
  assert.match(source, /grid gap-4 border-t border-\[var\(--color-border\)\] pt-8 scroll-mt-24/);
});

test('App main workbench keeps metadata badge plus loading and retry branches', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  assert.match(source, /<DataQualityBadge metadata=\{chartMetadata\} lang=\{lang\}/);
  assert.match(source, /currentMarketStatusTags/);
  assert.match(source, /currentMarketTruthStrip/);
  assert.match(source, /t\.status\.loading/);
  assert.match(source, /t\.status\.retry/);
  assert.match(source, /t\.status\.error/);
});

test('App avoids rendering a duplicate primary market title below workspace nav', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  assert.match(source, /<PageWorkspaceNav/);
  assert.doesNotMatch(source, /<h1 className="text-2xl font-bold leading-tight md:text-3xl">\s*\{t\.header\.title1\}\s*\{t\.header\.title2\}\s*<\/h1>/);
});

test('AEMO workspace nav collapses to a button-only top strip without left-side hero copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  const navSource = fs.readFileSync(path.resolve(__dirname, '../components/PageWorkspaceNav.jsx'), 'utf8');

  assert.match(source, /<PageWorkspaceNav/);
  assert.match(source, /compact/);
  assert.match(source, /buttonOnly/);
  assert.doesNotMatch(source, /brand=\{t\.nav\.brand\}/);
  assert.doesNotMatch(source, /subtitle=\{t\.appShell\.primarySignalTitle/);
  assert.doesNotMatch(source, /title=\{t\.appShell\.recommendedPathLabel/);
  assert.doesNotMatch(source, /meta=\{lastUpdate/);
  assert.match(navSource, /buttonOnly = false/);
  assert.match(source, /className="col-span-12 mt-2 mb-2"/);
});

test('App keeps only language controls in workspace nav actions area', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  assert.doesNotMatch(source, /actions=\{/);
  assert.doesNotMatch(source, /handleSync/);
  assert.doesNotMatch(source, /<motion\.header/);
  assert.doesNotMatch(source, /onClick=\{\(\) => setLang\(lang === 'zh' \? 'en' : 'zh'\)\}/);
});

test('Fingrid page keeps a single header and focuses on charts plus passive status context', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.match(source, /<DataQualityBadge metadata=\{statusMetadata\} lang=\{lang\} \/>/);
  assert.match(source, /marketModelCopy\.noSignals/);
  assert.match(source, /PageSection/);
  assert.match(source, /id="price-trend"/);
  assert.match(source, /id="market-supporting-signals"/);
  assert.match(source, /setError\(String\(err\)\)/);
  assert.doesNotMatch(source, /PageWorkspaceNav/);
  assert.doesNotMatch(source, /copy\.stageContext/);
  assert.doesNotMatch(source, /copy\.stageTimeSeries/);
  assert.doesNotMatch(source, /copy\.stageOperations/);
  assert.doesNotMatch(source, /copy\.marketPulseTitle/);
});

test('Fingrid series chart preserves loading, error, and empty-data states', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridSeriesChart.jsx'), 'utf8');
  assert.match(source, /loadingChart/);
  assert.match(source, /if \(error\)/);
  assert.match(source, /emptyChart/);
  assert.equal(source.includes('No time-series data is available for the selected window.'), false);
});

test('WEM-facing modules preserve preview caveat signaling', () => {
  const fcasSource = fs.readFileSync(path.resolve(__dirname, '../components/FcasAnalysis.jsx'), 'utf8');
  const stackingSource = fs.readFileSync(path.resolve(__dirname, '../components/RevenueStacking.jsx'), 'utf8');
  const investmentSource = fs.readFileSync(path.resolve(__dirname, '../components/InvestmentAnalysis.jsx'), 'utf8');

  assert.match(fcasSource, /DataQualityBadge/);
  assert.match(fcasSource, /previewCaveat/);
  assert.match(fcasSource, /fcasWemScopeCaveat/);
  assert.match(stackingSource, /t\.stackNoPreviewData/);
  assert.match(stackingSource, /t\.stackPreviewNotInvestmentGrade/);
  assert.match(stackingSource, /stackWemScopeCaveat/);
  assert.match(investmentSource, /previewCaveat/);
  assert.match(investmentSource, /wemReadinessCaveat/);
  assert.match(investmentSource, /DataQualityBadge/);
});

test('CycleCost centralizes localized copy for legacy fallback, axes, and empty states', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/CycleCost.jsx'), 'utf8');

  assert.match(source, /t\.ccLegacyFallback/);
  assert.match(source, /t\.ccYAxis/);
  assert.match(source, /t\.ccTooltipDays/);
  assert.match(source, /t\.ccTooltipFrequency/);
  assert.match(source, /t\.ccTooltipSpread/);
  assert.match(source, /t\.noData/);
  assert.match(source, /regime_compact/);
  assert.equal(source.includes("lang === 'zh'"), false);
});

test('ChargingWindow centralizes localized empty-state copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/ChargingWindow.jsx'), 'utf8');

  assert.match(source, /t\.noData/);
  assert.match(source, /regime_compact/);
  assert.equal(source.includes("lang === 'zh'"), false);
});

test('ChargingWindow avoids raw arrow text that breaks JSX parsing', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/ChargingWindow.jsx'), 'utf8');

  assert.equal(source.includes('<span>-></span>'), false);
});

test('Developer portal centralizes language toggle copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/DeveloperPortalPage.jsx'), 'utf8');

  assert.match(source, /copy\.toggleLanguage/);
  assert.match(source, /copy\.portalReadoutTitle/);
  assert.match(source, /copy\.stageAccess/);
  assert.match(source, /copy\.stageEconomics/);
  assert.match(source, /copy\.stageLedger/);
  assert.match(source, /copy\.stageContracts/);
  assert.match(source, /copy\.stageGovernance/);
  assert.match(source, /copy\.governanceFreshness/);
  assert.match(source, /copy\.governanceDrift/);
  assert.match(source, /copy\.governanceSourceCatalog/);
  assert.match(source, /copy\.governanceSourceId/);
  assert.match(source, /copy\.governanceDatasetFamily/);
  assert.match(source, /copy\.governanceLineage/);
  assert.match(source, /copy\.contractCompact/);
  assert.match(source, /copy\.contractFull/);
  assert.match(source, /PageWorkspaceNav/);
  assert.match(source, /PageSection/);
  assert.match(source, /id="stage-access"/);
  assert.match(source, /id="stage-economics"/);
  assert.match(source, /id="stage-ledger"/);
  assert.match(source, /id="stage-contracts"/);
  assert.match(source, /id="stage-governance"/);
  assert.match(source, /regime_compact/);
  assert.match(source, /regime_layer/);
  assert.equal(source.includes("lang === 'zh' ? 'EN'"), false);
});

test('Grid forecast helpers avoid inline localized source-link and band labels', () => {
  const driversSource = fs.readFileSync(path.resolve(__dirname, '../components/GridForecastDrivers.jsx'), 'utf8');
  const cardsSource = fs.readFileSync(path.resolve(__dirname, '../components/GridForecastSummaryCards.jsx'), 'utf8');

  assert.equal(driversSource.includes("locale === 'zh' ?"), false);
  assert.equal(driversSource.includes('Source link'), false);
  assert.equal(cardsSource.includes("locale === 'zh'"), false);
});

test('Grid forecast workbench surfaces p4 governance copy without hardcoded labels', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/GridForecast.jsx'), 'utf8');

  assert.match(source, /governance/);
  assert.match(source, /forecastStatusTags/);
  assert.match(source, /wemOutlookCaveat/);
  assert.match(source, /<DataQualityBadge metadata=\{forecastStatusMetadata\} lang=\{locale\} tags=\{forecastStatusTags\}/);
  assert.match(source, /sectionCopy\.governanceTitle/);
  assert.match(source, /sectionCopy\.governanceFreshness/);
  assert.match(source, /sectionCopy\.governanceDrift/);
  assert.match(source, /sectionCopy\.governanceDisclaimer/);
  assert.equal(source.includes("lang === 'zh' ? 'P4"), false);
});

test('Grid forecast diagnostics panel consumes walk-forward and forecast value proxy fields', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/GridForecastDiagnosticsPanel.jsx'), 'utf8');

  assert.match(source, /backtest_window/);
  assert.match(source, /walk_forward_mode/);
  assert.match(source, /sample_points_evaluated/);
  assert.match(source, /overall_information_value_index/);
  assert.match(source, /weakest_regime/);
});

test('P3 decision panel consumes governance and source backtest fields', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/P3BessDecisionPanel.jsx'), 'utf8');
  const copySource = fs.readFileSync(path.resolve(__dirname, './p3Decision.js'), 'utf8');

  assert.match(source, /payload\.governance/);
  assert.match(source, /sourceBacktest/);
  assert.match(source, /timeline_points/);
  assert.match(source, /equivalent_cycles/);
  assert.match(source, /governance\.freshness/);
  assert.match(source, /governance\.drift/);
  assert.match(source, /governance\.disclaimer/);
  assert.match(source, /governance\.lineage/);
  assert.match(source, /copy\.decisionHeadline/);
  assert.match(source, /copy\.decisionWhy/);
  assert.match(source, /copy\.decisionEconomics/);
  assert.match(source, /copy\.decisionDiagnostics/);
  assert.match(source, /<DataQualityBadge/);
  assert.match(source, /payload\.readinessStatus/);
  assert.match(source, /payload\.coverageMode/);
  assert.match(source, /<details/);
  assert.match(copySource, /decisionHeadline/);
  assert.match(copySource, /decisionWhy/);
  assert.match(copySource, /decisionEconomics/);
  assert.match(copySource, /decisionDiagnostics/);
});

test('Fingrid summary cards centralize localized loading copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridSummaryCards.jsx'), 'utf8');

  assert.equal(source.includes("lang === 'zh'"), false);
  assert.equal(source.includes('Loading...'), false);
});

test('App centralizes section navigation and month label copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');

  assert.match(source, /PageWorkspaceNav/);
  assert.match(source, /t\.appShell\.sectionNav/);
  assert.match(source, /t\.appShell\.stageCurrentMarket/);
  assert.match(source, /t\.appShell\.stage24hOutlook/);
  assert.match(source, /t\.appShell\.stageBessDecision/);
  assert.match(source, /t\.appShell\.primarySignalTitle/);
  assert.match(source, /t\.appShell\.recommendedPathLabel/);
  assert.match(source, /t\.appShell\.monthLabels/);
  assert.match(source, /t\.appShell\.simulatorScopeNote/);
  assert.match(source, /t\.appShell\.investmentScopeNote/);
  assert.match(source, /id="stage-current-market"/);
  assert.match(source, /id="stage-24h-outlook"/);
  assert.match(source, /id="stage-bess-decision"/);
  assert.match(source, /translations\[lang\]\?\.status\?\.loadingSection/);
  assert.match(source, /aria-label=\{sectionNavCopy\.sectionNavigation\}/);
  assert.match(source, /aria-label=\{t\.appShell\.backToTop\}/);
  assert.match(source, /languageAriaLabel=\{t\.appShell\.toggleLanguage\}/);
  assert.match(source, /aria-label=\{t\.status\.retry\}/);
  assert.doesNotMatch(source, /syncTrigger/);
  assert.equal(source.includes("const sectionNavCopy = lang === 'zh'"), false);
  assert.equal(source.includes("const monthLabels = lang === 'zh'"), false);
  assert.equal(source.includes('Loading section...'), false);
  assert.equal(source.includes('Grid Forecast'), false);
  assert.equal(source.includes('Negative Price Time Dist.'), false);
  assert.equal(source.includes('Toggle navigation'), false);
  assert.equal(source.includes('Back to top'), false);
  assert.equal(source.includes('Trigger Background Data Sync'), false);
  assert.equal(source.includes('Toggle language'), false);
});

test('Current Market keeps intraday structure in the right content rail instead of a full-width block below', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');

  assert.match(source, /id="sec-overview"[\s\S]*id="sec-market-structure"/);
  assert.doesNotMatch(source, /<\/div>\s*<\/div>\s*<StageDetailGroup[\s\S]*id="sec-market-structure"/);
});

test('core analytics components avoid inline loading fallback strings', () => {
  const files = [
    '../components/ChargingWindow.jsx',
    '../components/BessSimulator.jsx',
    '../components/CycleCost.jsx',
    '../components/RevenueStacking.jsx',
    '../components/PeakAnalysis.jsx',
  ];

  for (const relativePath of files) {
    const source = fs.readFileSync(path.resolve(__dirname, relativePath), 'utf8');
    assert.equal(source.includes("|| 'Loading...'"), false, `${relativePath} should not hardcode loading fallback`);
  }
});

test('Revenue stacking centralizes preview and summary copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/RevenueStacking.jsx'), 'utf8');

  assert.match(source, /t\.stackPreviewNotInvestmentGrade/);
  assert.match(source, /t\.stackSummaryPeriods/);
  assert.match(source, /t\.stackSummaryArbitrageBase/);
  assert.match(source, /t\.stackSummaryFcasLayers/);
  assert.match(source, /t\.stackSummaryCombined/);
  assert.match(source, /t\.stackPreviewMode/);
  assert.match(source, /t\.stackPreviewDate/);
  assert.match(source, /t\.stackPreviewCombined/);
  assert.match(source, /t\.stackNoOverlap/);
  assert.match(source, /regime_compact/);
  assert.equal(source.includes('Not investment-grade'), false);
  assert.equal(source.includes('Preview Mode'), false);
  assert.equal(source.includes('Combined Stack'), false);
  assert.equal(source.includes('Arbitrage Base'), false);
  assert.equal(source.includes('FCAS Layers'), false);
  assert.equal(source.includes('No overlapping peak-analysis and FCAS preview dates were found for WEM.'), false);
});

test('Peak analysis centralizes eyebrow and event column labels', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/PeakAnalysis.jsx'), 'utf8');

  assert.match(source, /t\.eyebrow/);
  assert.match(source, /t\.eventsColumn/);
  assert.match(source, /regime_compact/);
  assert.equal(source.includes('STORAGE ARBITRAGE'), false);
  assert.equal(source.includes('>Events<'), false);
});

test('BESS simulator centralizes financial summary copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/BessSimulator.jsx'), 'utf8');

  assert.match(source, /t\.eyebrow/);
  assert.match(source, /t\.decisionReferenceTitle/);
  assert.match(source, /t\.decisionReferenceBody/);
  assert.match(source, /t\.capacityMwUnit/);
  assert.match(source, /t\.durationHoursUnit/);
  assert.match(source, /t\.wfGross/);
  assert.match(source, /t\.wfRte/);
  assert.match(source, /t\.wfAux/);
  assert.match(source, /t\.wfNetwork/);
  assert.match(source, /t\.wfMlf/);
  assert.match(source, /t\.wfAemoFee/);
  assert.match(source, /t\.wfDegradation/);
  assert.match(source, /t\.wfNet/);
  assert.match(source, /t\.pRte/);
  assert.match(source, /t\.pAux/);
  assert.match(source, /t\.pMlf/);
  assert.match(source, /t\.pCycles/);
  assert.match(source, /t\.pDegradation/);
  assert.match(source, /t\.pAemoFee/);
  assert.match(source, /regime_compact/);
  assert.doesNotMatch(source, /<P3BessDecisionPanel/);
  assert.equal(source.includes('FINANCIAL MODEL'), false);
  assert.equal(source.includes('Net $/MWh'), false);
  assert.equal(source.includes('Daily Revenue'), false);
  assert.equal(source.includes('Annual Revenue'), false);
  assert.equal(source.includes("|| 'Gross Spread'"), false);
  assert.equal(source.includes("|| 'RTE Loss'"), false);
  assert.equal(source.includes("|| 'Aux Power'"), false);
  assert.equal(source.includes("|| 'Network Fee'"), false);
  assert.equal(source.includes("|| 'MLF Loss'"), false);
  assert.equal(source.includes("|| 'AEMO Fee'"), false);
  assert.equal(source.includes("|| 'Degradation'"), false);
  assert.equal(source.includes("|| 'Net Profit'"), false);
  assert.equal(source.includes("|| 'Round-Trip Efficiency'"), false);
  assert.equal(source.includes("|| 'Auxiliary Load'"), false);
  assert.equal(source.includes("|| 'MLF Factor'"), false);
  assert.equal(source.includes("|| 'Daily Cycles'"), false);
  assert.equal(source.includes("|| 'Degradation Cost'"), false);
  assert.equal(source.includes("|| 'AEMO Participant Fee'"), false);
});

test('Investment analysis centralizes finance copy and consumes regime compact', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/InvestmentAnalysis.jsx'), 'utf8');

  assert.match(source, /copy\.eyebrow/);
  assert.match(source, /copy\.runAnalysis/);
  assert.match(source, /copy\.backtestObservedTitle/);
  assert.match(source, /copy\.regimeNarrativeTitle/);
  assert.match(source, /copy\.regimeNarrativeEmpty/);
  assert.match(source, /regime_compact/);
});

test('FCAS analysis centralizes preview, summary, and table copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/FcasAnalysis.jsx'), 'utf8');

  assert.match(source, /t\.fcasPreviewNotInvestmentGrade/);
  assert.match(source, /t\.fcasViabilityPositive/);
  assert.match(source, /t\.fcasViabilityNegative/);
  assert.match(source, /t\.fcasOppCost/);
  assert.match(source, /t\.fcasNetIncremental/);
  assert.match(source, /t\.fcasReserved/);
  assert.match(source, /t\.fcasBindings/);
  assert.match(source, /t\.fcasViability/);
  assert.match(source, /t\.fcasCoverageDays/);
  assert.match(source, /t\.fcasInvestmentGrade/);
  assert.match(source, /t\.fcasScarcity/);
  assert.match(source, /t\.fcasOpportunity/);
  assert.match(source, /t\.fcasQuality/);
  assert.equal(source.includes('Not investment-grade'), false);
  assert.equal(source.includes("|| 'Viable Services'"), false);
  assert.equal(source.includes("|| 'Opp. Cost'"), false);
  assert.equal(source.includes("|| 'Reserved MW'"), false);
  assert.equal(source.includes("|| 'Bindings'"), false);
  assert.equal(source.includes("|| 'Viability'"), false);
  assert.equal(source.includes('coverage_days='), false);
  assert.equal(source.includes('investment_grade='), false);
  assert.equal(source.includes('Scarcity '), false);
  assert.equal(source.includes('Opportunity '), false);
  assert.equal(source.includes('Quality '), false);
  assert.equal(source.includes('Loading FCAS data...'), false);
  assert.equal(source.includes('No FCAS Data Available'), false);
  assert.equal(source.includes('Run the relevant sync job to collect FCAS or ESS pricing data.'), false);
  assert.match(source, /regime_compact/);
});

test('App passes regime compact translation copy into forecast and FCAS modules', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');

  assert.match(source, /regimeCompactCopy=\{t\.regime_compact\}/);
});

test('App passes regime compact translation copy into peak analysis module', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');

  assert.match(source, /<PeakAnalysis[\s\S]*?t=\{\{\.\.\.t\.peak_analysis, loadingMsg: t\.loading_states\.peak\}\}[\s\S]*?regimeCompactCopy=\{t\.regime_compact\}/);
});

test('App passes regime compact translation copy into cycle cost and charging modules', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');

  assert.match(source, /<ChargingWindow[\s\S]*?t=\{\{\.\.\.t\.charging, \.\.\.t\.peak_analysis, loadingMsg: t\.loading_states\.charging\}\}[\s\S]*?regimeCompactCopy=\{t\.regime_compact\}/);
  assert.match(source, /<CycleCost[\s\S]*?t=\{\{\.\.\.t\.cycleCost, \.\.\.t\.peak_analysis, loadingMsg: t\.loading_states\.cycleCost\}\}[\s\S]*?regimeCompactCopy=\{t\.regime_compact\}/);
});

test('App passes regime compact translation copy into simulator and stacking modules', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');

  assert.match(source, /<BessSimulator[\s\S]*?t=\{\{\.\.\.t\.simulator, loadingMsg: t\.loading_states\.simulator\}\}[\s\S]*?regimeCompactCopy=\{t\.regime_compact\}/);
  assert.match(source, /<RevenueStacking[\s\S]*?t=\{\{\.\.\.t\.stacking, \.\.\.t\.peak_analysis, loadingMsg: t\.loading_states\.stacking\}\}[\s\S]*?regimeCompactCopy=\{t\.regime_compact\}/);
});

test('App wires regime compact copy through the main AEMO workbench modules', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');

  for (const componentName of [
    'GridForecast',
    'PeakAnalysis',
    'FcasAnalysis',
    'BessSimulator',
    'RevenueStacking',
    'ChargingWindow',
    'CycleCost',
    'InvestmentAnalysis',
  ]) {
    const pattern = new RegExp(`<${componentName}[\\s\\S]*?regimeCompactCopy=\\{t\\.regime_compact\\}`);
    assert.match(source, pattern);
  }
});

test('ChargingWindow centralizes radar labels and hints', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/ChargingWindow.jsx'), 'utf8');

  assert.match(source, /t\.cwEyebrow/);
  assert.match(source, /t\.cwHover/);
  assert.match(source, /t\.cwToSee/);
  assert.match(source, /t\.cwBestCharge/);
  assert.match(source, /t\.cwChargeHint/);
  assert.match(source, /t\.cwBestDischarge/);
  assert.match(source, /t\.cwDischargeHint/);
  assert.match(source, /t\.cwNegStats/);
  assert.equal(source.includes('Charging Window Radar'), false);
  assert.equal(source.includes('24-hour Price Clock - Optimal Charge & Discharge Windows'), false);
  assert.equal(source.includes('DUCK CURVE'), false);
  assert.equal(source.includes('HOVER'), false);
  assert.equal(source.includes('TO SEE'), false);
  assert.equal(source.includes('Best Charge Window (Lowest Prices)'), false);
  assert.equal(source.includes('Best Discharge Window (Highest Prices)'), false);
  assert.equal(source.includes('Negative Price Stats'), false);
});

test('CycleCost centralizes degradation and histogram copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/CycleCost.jsx'), 'utf8');

  assert.match(source, /t\.ccEyebrow/);
  assert.match(source, /t\.ccDegCost/);
  assert.match(source, /t\.ccUnitPerMwh/);
  assert.match(source, /t\.ccSliderMin/);
  assert.match(source, /t\.ccSliderMax/);
  assert.equal(source.includes('Cycle Cost vs Profitability'), false);
  assert.equal(source.includes('DEGRADATION'), false);
  assert.equal(source.includes('Cycle Degradation Cost'), false);
  assert.equal(source.includes('Worth Cycling'), false);
  assert.equal(source.includes('Hold - Not Worth It'), false);
  assert.equal(source.includes('Avg Spread'), false);
  assert.equal(source.includes('Max Spread'), false);
  assert.equal(source.includes('Total Days'), false);
  assert.equal(source.includes('Profitable - Cycle'), false);
  assert.equal(source.includes("|| 'Marginal'"), false);
  assert.equal(source.includes('Cost Line'), false);
});

test('Grid forecast driver and timeline panels avoid hardcoded helper labels', () => {
  const driversSource = fs.readFileSync(path.resolve(__dirname, '../components/GridForecastDrivers.jsx'), 'utf8');
  const timelineSource = fs.readFileSync(path.resolve(__dirname, '../components/GridForecastTimeline.jsx'), 'utf8');

  assert.equal(driversSource.includes('Key Drivers'), false);
  assert.equal(driversSource.includes("'signal'"), false);
  assert.equal(driversSource.includes("'source'"), false);
  assert.equal(timelineSource.includes('Future Windows'), false);
});

test('SummaryStats centralizes deep-dive unit copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/SummaryStats.jsx'), 'utf8');

  assert.match(source, /t\.deepDive/);
  assert.match(source, /t\.daysUnit/);
  assert.equal(source.includes('DEEP DIVE'), false);
  assert.equal(source.includes("|| 'Days'"), false);
});

test('Revenue stacking centralizes empty-state copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/RevenueStacking.jsx'), 'utf8');

  assert.match(source, /t\.noData/);
  assert.equal(source.includes("|| 'No Data'"), false);
});

test('Report preview centralizes report copy and loading state', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/ReportPreview.jsx'), 'utf8');

  assert.match(source, /t\.title/);
  assert.match(source, /t\.subtitle/);
  assert.match(source, /t\.loading/);
  assert.match(source, /REPORT_TYPES/);
  assert.equal(source.includes('Report Preview'), false);
  assert.equal(source.includes('Structured payload preview for commercial deliverables.'), false);
  assert.equal(source.includes('Loading report...'), false);
  assert.equal(source.includes('Monthly Market Report'), false);
  assert.equal(source.includes('Investment Memo Draft'), false);
});

test('Fingrid series chart avoids hardcoded title fallback', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridSeriesChart.jsx'), 'utf8');

  assert.match(source, /copy\?\.seriesTitle/);
  assert.equal(source.includes("|| 'Time Series'"), false);
});

test('Fingrid header and page centralize metadata and loading fallback copy', () => {
  const headerSource = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridHeader.jsx'), 'utf8');
  const pageSource = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');

  assert.match(headerSource, /copy\.defaultDatasetId/);
  assert.match(headerSource, /copy\.defaultUnit/);
  assert.match(headerSource, /copy\.defaultFrequency/);
  assert.equal(headerSource.includes("|| '317'"), false);
  assert.equal(headerSource.includes("|| 'EUR/MW'"), false);
  assert.equal(headerSource.includes("|| '1h'"), false);
  assert.match(pageSource, /loading=\{loading\}/);
  assert.equal(pageSource.includes("|| 'loading'"), false);
});
