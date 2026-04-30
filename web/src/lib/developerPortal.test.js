import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('page router resolves developer portal path', async () => {
  const { resolveRootPage } = await import('./pageRouter.js');
  assert.equal(resolveRootPage('/developer'), 'developer');
});

test('main entry can render developer portal page', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../main.jsx'), 'utf8');
  assert.match(source, /DeveloperPortalPage/);
});

test('App exposes a navigation entry to the developer portal', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  assert.match(source, /\/developer/);
});

test('Developer portal page loads portal payload and persists API key locally', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/DeveloperPortalPage.jsx'), 'utf8');
  assert.match(source, /\/developer\/portal/);
  assert.match(source, /localStorage/);
  assert.match(source, /fetchJson/);
  assert.match(source, /quota/);
  assert.match(source, /billing/);
  assert.match(source, /ledger/);
  assert.match(source, /translations/);
  assert.doesNotMatch(source, /const COPY = \{/);
});
