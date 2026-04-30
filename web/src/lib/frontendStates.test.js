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
  assert.match(source, /formatFreshnessLabel/);
  assert.match(source, /formatMetadataUnitLabel/);
  assert.match(source, /metadata\?\.interval_minutes/);
});

test('App main workbench keeps metadata badge plus loading and retry branches', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  assert.match(source, /<DataQualityBadge metadata=\{chartMetadata\} lang=\{lang\}/);
  assert.match(source, /t\.status\.loading/);
  assert.match(source, /t\.status\.retry/);
  assert.match(source, /t\.status\.error/);
});

test('Fingrid page surfaces metadata badge and Finland empty-state context', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.match(source, /<DataQualityBadge metadata=\{statusMetadata\} lang=\{lang\} \/>/);
  assert.match(source, /marketModelCopy\.noSignals/);
  assert.match(source, /copy\.stageContext/);
  assert.match(source, /copy\.stageTimeSeries/);
  assert.match(source, /copy\.stageOperations/);
  assert.match(source, /copy\.marketPulseTitle/);
  assert.match(source, /PageWorkspaceNav/);
  assert.match(source, /PageSection/);
  assert.match(source, /id="stage-context"/);
  assert.match(source, /id="stage-time-series"/);
  assert.match(source, /id="stage-operations"/);
  assert.match(source, /setError\(String\(err\)\)/);
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
  assert.match(stackingSource, /t\.stackNoPreviewData/);
  assert.match(stackingSource, /t\.stackPreviewNotInvestmentGrade/);
  assert.match(investmentSource, /previewCaveat/);
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
  assert.equal(source.includes("lang === 'zh'"), false);
});

test('ChargingWindow centralizes localized empty-state copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/ChargingWindow.jsx'), 'utf8');

  assert.match(source, /t\.noData/);
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
  assert.match(source, /PageWorkspaceNav/);
  assert.match(source, /PageSection/);
  assert.match(source, /id="stage-access"/);
  assert.match(source, /id="stage-economics"/);
  assert.match(source, /id="stage-ledger"/);
  assert.equal(source.includes("lang === 'zh' ? 'EN'"), false);
});

test('Grid forecast helpers avoid inline localized source-link and band labels', () => {
  const driversSource = fs.readFileSync(path.resolve(__dirname, '../components/GridForecastDrivers.jsx'), 'utf8');
  const cardsSource = fs.readFileSync(path.resolve(__dirname, '../components/GridForecastSummaryCards.jsx'), 'utf8');

  assert.equal(driversSource.includes("locale === 'zh' ?"), false);
  assert.equal(driversSource.includes('Source link'), false);
  assert.equal(cardsSource.includes("locale === 'zh'"), false);
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
  assert.match(source, /t\.appShell\.stageOverview/);
  assert.match(source, /t\.appShell\.stageOpportunities/);
  assert.match(source, /t\.appShell\.stageInvestment/);
  assert.match(source, /t\.appShell\.primarySignalTitle/);
  assert.match(source, /t\.appShell\.recommendedPathLabel/);
  assert.match(source, /t\.appShell\.monthLabels/);
  assert.match(source, /t\.appShell\.simulatorScopeNote/);
  assert.match(source, /t\.appShell\.investmentScopeNote/);
  assert.match(source, /id="stage-overview"/);
  assert.match(source, /id="stage-opportunities"/);
  assert.match(source, /id="stage-investment"/);
  assert.match(source, /translations\[lang\]\?\.status\?\.loadingSection/);
  assert.match(source, /aria-label=\{sectionNavCopy\.sectionNavigation\}/);
  assert.match(source, /aria-label=\{t\.appShell\.backToTop\}/);
  assert.match(source, /title=\{t\.appShell\.syncTrigger\}/);
  assert.match(source, /languageAriaLabel=\{t\.appShell\.toggleLanguage\}/);
  assert.match(source, /aria-label=\{t\.status\.retry\}/);
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
  assert.equal(source.includes('STORAGE ARBITRAGE'), false);
  assert.equal(source.includes('>Events<'), false);
});

test('BESS simulator centralizes financial summary copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/BessSimulator.jsx'), 'utf8');

  assert.match(source, /t\.eyebrow/);
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
  assert.match(pageSource, /copy\.statusValues\.loading/);
  assert.equal(pageSource.includes("|| 'loading'"), false);
});
