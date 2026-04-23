import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveRootPage } from './pageRouter.js';

test('resolveRootPage switches to the Fingrid page on /fingrid paths', () => {
  assert.equal(resolveRootPage('/fingrid'), 'fingrid');
  assert.equal(resolveRootPage('/fingrid/317'), 'fingrid');
  assert.equal(resolveRootPage('/'), 'aemo');
});
