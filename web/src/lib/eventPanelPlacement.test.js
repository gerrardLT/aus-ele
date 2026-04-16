import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const componentsDir = path.resolve(__dirname, '..', 'components');
const appPath = path.resolve(__dirname, '..', 'App.jsx');

function countOccurrences(source, pattern) {
  return (source.match(pattern) || []).length;
}

test('app mounts one standalone GridForecast section and no top-level EventContextPanel', () => {
  const appSource = fs.readFileSync(appPath, 'utf8');
  assert.equal(countOccurrences(appSource, /<GridForecast\b/g), 1);
  assert.equal(countOccurrences(appSource, /<EventContextPanel\b/g), 0);

  for (const name of ['PeakAnalysis.jsx', 'FcasAnalysis.jsx', 'RevenueStacking.jsx', 'CycleCost.jsx']) {
    const source = fs.readFileSync(path.join(componentsDir, name), 'utf8');
    assert.equal(countOccurrences(source, /<EventContextPanel\b/g), 0, `${name} should not mount EventContextPanel`);
  }
});
