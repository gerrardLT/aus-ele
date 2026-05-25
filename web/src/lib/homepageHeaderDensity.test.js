import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('homepage uses compact section headers and condensed decorative copy', () => {
  const appSource = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  const sectionSource = fs.readFileSync(path.resolve(__dirname, '../components/PageSection.jsx'), 'utf8');

  assert.match(appSource, /compactHeader/);
  assert.match(appSource, /text-xs leading-5 text-white\/50/);
  assert.match(appSource, /md:overflow-hidden md:text-ellipsis md:whitespace-nowrap/);
  assert.match(sectionSource, /compactHeader = false/);
  assert.match(sectionSource, /md:overflow-hidden md:text-ellipsis md:whitespace-nowrap/);
});
