import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('homepage analysis modules use compact header sizing and tighter explanatory copy', () => {
  const files = [
    '../components/GridForecast.jsx',
    '../components/PeakAnalysis.jsx',
    '../components/ChargingWindow.jsx',
    '../components/FcasAnalysis.jsx',
    '../components/RevenueStacking.jsx',
    '../components/InvestmentAnalysis.jsx',
    '../components/BessSimulator.jsx',
    '../components/CycleCost.jsx',
    '../components/ReportPreview.jsx',
  ];

  for (const relativePath of files) {
    const source = fs.readFileSync(path.resolve(__dirname, relativePath), 'utf8');
    assert.match(source, /text-2xl font-serif/);
  }

  const investmentSource = fs.readFileSync(path.resolve(__dirname, '../components/InvestmentAnalysis.jsx'), 'utf8');
  assert.match(investmentSource, /text-xs leading-5 text-\[var\(--color-muted\)\]/);
});
