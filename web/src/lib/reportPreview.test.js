import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('report preview is registered for dynamic mounting in the decision stage', () => {
  // 2026-08-20：App.jsx 直挂改为 ModuleRenderer lazy 注册 + marketConfig 阶段配置
  const rendererSource = fs.readFileSync(path.resolve(__dirname, '../components/funnel/ModuleRenderer.jsx'), 'utf8');
  const configSource = fs.readFileSync(path.resolve(__dirname, './marketConfig.js'), 'utf8');
  assert.match(rendererSource, /ReportPreview: lazy\(/);
  assert.match(configSource, /component: 'ReportPreview'/);
});

test('ReportPreview consumes structured report payload fields', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/ReportPreview.jsx'), 'utf8');
  assert.match(source, /report_type/);
  assert.match(source, /sections/);
  assert.match(source, /executive_summary|summary/);
});
