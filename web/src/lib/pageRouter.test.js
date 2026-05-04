import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveRootPage } from './pageRouter.js';

test('resolveRootPage switches to the Fingrid page on /fingrid paths', () => {
  assert.equal(resolveRootPage('/fingrid'), 'fingrid');
  assert.equal(resolveRootPage('/fingrid/317'), 'fingrid');
  assert.equal(resolveRootPage('/'), 'aemo');
});

test('resolveRootPage switches to the Finland page on /finland paths', () => {
  assert.equal(resolveRootPage('/finland'), 'finland');
  assert.equal(resolveRootPage('/finland?window=7d'), 'finland');
  assert.equal(resolveRootPage('/finland/board'), 'finland');
});
