import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('App mounts a report preview section', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  assert.match(source, /ReportPreview/);
  assert.match(source, /sec-reports/);
});

test('ReportPreview consumes structured report payload fields', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/ReportPreview.jsx'), 'utf8');
  assert.match(source, /report_type/);
  assert.match(source, /sections/);
  assert.match(source, /executive_summary|summary/);
});
