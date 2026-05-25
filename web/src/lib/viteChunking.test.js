import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('vite config assigns dedicated manual chunks for chart and framework vendors', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../../vite.config.js'), 'utf8');

  assert.match(source, /manualChunks\(id\)/);
  assert.match(source, /id\.includes\('recharts'\)/);
  assert.match(source, /return 'charts-vendor'/);
  assert.match(source, /id\.includes\('react'\) \|\| id\.includes\('scheduler'\)/);
  assert.match(source, /return 'react-vendor'/);
});
