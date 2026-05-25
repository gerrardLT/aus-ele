import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('homepage workspace uses tightened vertical spacing around primary charts and support sections', () => {
  const appSource = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  const simulatorSource = fs.readFileSync(path.resolve(__dirname, '../components/BessSimulator.jsx'), 'utf8');
  const stackingSource = fs.readFileSync(path.resolve(__dirname, '../components/RevenueStacking.jsx'), 'utf8');

  assert.match(appSource, /grid grid-cols-12 gap-8/);
  assert.match(appSource, /h-\[440px\] md:h-\[460px\]/);
  assert.match(appSource, /mt-10 rounded-3xl/);
  assert.match(simulatorSource, /h-\[360px\] md:h-\[380px\]/);
  assert.match(stackingSource, /h-\[380px\] md:h-\[400px\]/);
});
