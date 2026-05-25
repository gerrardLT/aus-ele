/**
 * Property-based structural tests for marketConfig.js
 *
 * Covers:
 * - Property 1: Stage config structural validity
 * - Property 18: Module config structural completeness
 *
 * **Validates: Requirements 1.1, 1.4, 1.5, 11.1, 11.4**
 */

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  MARKET_CONFIGS,
  getMarketConfig,
  getStageDefinitions,
  MODULE_REGISTRY,
} from './marketConfig.js';

// ---------------------------------------------------------------------------
// Property 1: Stage config structural validity
// For any market config, all stages have valid id, title (zh/en),
// coreQuestion (zh/en), and non-empty modules array.
// **Validates: Requirements 1.1, 1.4, 1.5**
// ---------------------------------------------------------------------------

describe('Property 1: Stage config structural validity', () => {
  const marketIds = Object.keys(MARKET_CONFIGS);

  test('all markets have stages defined as non-empty arrays', () => {
    for (const marketId of marketIds) {
      const config = MARKET_CONFIGS[marketId];
      assert.ok(Array.isArray(config.stages), `${marketId} stages should be an array`);
      assert.ok(config.stages.length > 0, `${marketId} stages should not be empty`);
    }
  });

  test('every stage has a valid id (non-empty string)', () => {
    for (const marketId of marketIds) {
      for (const stage of MARKET_CONFIGS[marketId].stages) {
        assert.equal(typeof stage.id, 'string', `${marketId} stage id should be a string`);
        assert.ok(stage.id.length > 0, `${marketId} stage id should not be empty`);
      }
    }
  });

  test('every stage has title with zh and en fields (non-empty strings)', () => {
    for (const marketId of marketIds) {
      for (const stage of MARKET_CONFIGS[marketId].stages) {
        assert.ok(stage.title, `${marketId}/${stage.id} should have title`);
        assert.equal(typeof stage.title.zh, 'string',
          `${marketId}/${stage.id} title.zh should be a string`);
        assert.ok(stage.title.zh.length > 0,
          `${marketId}/${stage.id} title.zh should not be empty`);
        assert.equal(typeof stage.title.en, 'string',
          `${marketId}/${stage.id} title.en should be a string`);
        assert.ok(stage.title.en.length > 0,
          `${marketId}/${stage.id} title.en should not be empty`);
      }
    }
  });

  test('every stage has coreQuestion with zh and en fields (non-empty strings)', () => {
    for (const marketId of marketIds) {
      for (const stage of MARKET_CONFIGS[marketId].stages) {
        assert.ok(stage.coreQuestion, `${marketId}/${stage.id} should have coreQuestion`);
        assert.equal(typeof stage.coreQuestion.zh, 'string',
          `${marketId}/${stage.id} coreQuestion.zh should be a string`);
        assert.ok(stage.coreQuestion.zh.length > 0,
          `${marketId}/${stage.id} coreQuestion.zh should not be empty`);
        assert.equal(typeof stage.coreQuestion.en, 'string',
          `${marketId}/${stage.id} coreQuestion.en should be a string`);
        assert.ok(stage.coreQuestion.en.length > 0,
          `${marketId}/${stage.id} coreQuestion.en should not be empty`);
      }
    }
  });

  test('every stage has a non-empty modules array', () => {
    for (const marketId of marketIds) {
      for (const stage of MARKET_CONFIGS[marketId].stages) {
        assert.ok(Array.isArray(stage.modules),
          `${marketId}/${stage.id} modules should be an array`);
        assert.ok(stage.modules.length > 0,
          `${marketId}/${stage.id} modules should not be empty`);
      }
    }
  });

  test('stage ids are unique within each market', () => {
    for (const marketId of marketIds) {
      const ids = MARKET_CONFIGS[marketId].stages.map(s => s.id);
      const uniqueIds = new Set(ids);
      assert.equal(ids.length, uniqueIds.size,
        `${marketId} has duplicate stage ids: ${ids.filter((id, i) => ids.indexOf(id) !== i)}`);
    }
  });
});

// ---------------------------------------------------------------------------
// Property 18: Module config structural completeness
// For any module entry in any stage, it has component (string),
// dataDependencies (array), loadPriority (number), enabled (boolean).
// **Validates: Requirements 11.1, 11.4**
// ---------------------------------------------------------------------------

describe('Property 18: Module config structural completeness', () => {
  const marketIds = Object.keys(MARKET_CONFIGS);

  test('every module has component as a non-empty string', () => {
    for (const marketId of marketIds) {
      for (const stage of MARKET_CONFIGS[marketId].stages) {
        for (const mod of stage.modules) {
          assert.equal(typeof mod.component, 'string',
            `${marketId}/${stage.id} module component should be a string`);
          assert.ok(mod.component.length > 0,
            `${marketId}/${stage.id} module component should not be empty`);
        }
      }
    }
  });

  test('every module has dataDependencies as an array', () => {
    for (const marketId of marketIds) {
      for (const stage of MARKET_CONFIGS[marketId].stages) {
        for (const mod of stage.modules) {
          assert.ok(Array.isArray(mod.dataDependencies),
            `${marketId}/${stage.id}/${mod.component} dataDependencies should be an array`);
        }
      }
    }
  });

  test('every module has loadPriority as a positive number', () => {
    for (const marketId of marketIds) {
      for (const stage of MARKET_CONFIGS[marketId].stages) {
        for (const mod of stage.modules) {
          assert.equal(typeof mod.loadPriority, 'number',
            `${marketId}/${stage.id}/${mod.component} loadPriority should be a number`);
          assert.ok(mod.loadPriority > 0,
            `${marketId}/${stage.id}/${mod.component} loadPriority should be positive`);
        }
      }
    }
  });

  test('every module has enabled as a boolean', () => {
    for (const marketId of marketIds) {
      for (const stage of MARKET_CONFIGS[marketId].stages) {
        for (const mod of stage.modules) {
          assert.equal(typeof mod.enabled, 'boolean',
            `${marketId}/${stage.id}/${mod.component} enabled should be a boolean`);
        }
      }
    }
  });

  test('all module components referenced in stages exist in MODULE_REGISTRY', () => {
    for (const marketId of marketIds) {
      for (const stage of MARKET_CONFIGS[marketId].stages) {
        for (const mod of stage.modules) {
          assert.ok(MODULE_REGISTRY[mod.component],
            `${marketId}/${stage.id}: component "${mod.component}" not found in MODULE_REGISTRY`);
        }
      }
    }
  });

  test('dataDependencies entries are non-empty strings starting with /', () => {
    for (const marketId of marketIds) {
      for (const stage of MARKET_CONFIGS[marketId].stages) {
        for (const mod of stage.modules) {
          for (const dep of mod.dataDependencies) {
            assert.equal(typeof dep, 'string',
              `${marketId}/${stage.id}/${mod.component} dependency should be a string`);
            assert.ok(dep.startsWith('/'),
              `${marketId}/${stage.id}/${mod.component} dependency "${dep}" should start with /`);
          }
        }
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Additional structural tests: stage counts and helper functions
// **Validates: Requirements 1.1, 1.4**
// ---------------------------------------------------------------------------

describe('Market stage count verification', () => {
  test('NEM has exactly 7 stages', () => {
    assert.equal(MARKET_CONFIGS.NEM.stages.length, 7);
  });

  test('WEM has exactly 5 stages', () => {
    assert.equal(MARKET_CONFIGS.WEM.stages.length, 5);
  });

  test('NEM stages are in expected order', () => {
    const nemStageIds = MARKET_CONFIGS.NEM.stages.map(s => s.id);
    assert.deepEqual(nemStageIds, [
      'market-screening',
      'revenue-deep-dive',
      'saturation-competition',
      'investment-outlook',
      'co-optimized-backtest',
      'financial-modeling',
      'investment-decision',
    ]);
  });

  test('WEM stages are in expected order', () => {
    const wemStageIds = MARKET_CONFIGS.WEM.stages.map(s => s.id);
    assert.deepEqual(wemStageIds, [
      'market-screening',
      'revenue-deep-dive',
      'saturation-competition',
      'co-optimized-backtest',
      'investment-decision',
    ]);
  });
});

describe('getStageDefinitions helper', () => {
  test('getStageDefinitions(NEM) returns 7 entries', () => {
    const stages = getStageDefinitions('NEM');
    assert.equal(stages.length, 7);
  });

  test('getStageDefinitions(WEM) returns 5 entries', () => {
    const stages = getStageDefinitions('WEM');
    assert.equal(stages.length, 5);
  });

  test('getStageDefinitions entries have id, number, title, coreQuestion', () => {
    const stages = getStageDefinitions('NEM');
    for (const stage of stages) {
      assert.equal(typeof stage.id, 'string');
      assert.equal(typeof stage.number, 'number');
      assert.ok(stage.title);
      assert.ok(stage.coreQuestion);
      assert.equal(typeof stage.title.zh, 'string');
      assert.equal(typeof stage.title.en, 'string');
      assert.equal(typeof stage.coreQuestion.zh, 'string');
      assert.equal(typeof stage.coreQuestion.en, 'string');
    }
  });

  test('getStageDefinitions numbers are sequential starting from 1', () => {
    const stages = getStageDefinitions('NEM');
    for (let i = 0; i < stages.length; i++) {
      assert.equal(stages[i].number, i + 1);
    }
  });

  test('getStageDefinitions defaults to NEM when given unknown market', () => {
    const stages = getStageDefinitions('UNKNOWN');
    assert.equal(stages.length, 7); // Same as NEM
  });
});

describe('getMarketConfig helper', () => {
  test('getMarketConfig(NEM) returns NEM config', () => {
    const config = getMarketConfig('NEM');
    assert.equal(config.id, 'NEM');
  });

  test('getMarketConfig(WEM) returns WEM config', () => {
    const config = getMarketConfig('WEM');
    assert.equal(config.id, 'WEM');
  });

  test('getMarketConfig defaults to NEM for unknown market', () => {
    const config = getMarketConfig('UNKNOWN');
    assert.equal(config.id, 'NEM');
  });
});
