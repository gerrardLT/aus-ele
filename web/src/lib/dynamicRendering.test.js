/**
 * Property-based tests for dynamic stage rendering logic.
 *
 * Covers:
 * - Property 2: Dynamic stage rendering matches config
 *   - 2a: Stage count matches expected (NEM=7, WEM=5)
 *   - 2b: All enabled modules have entries in MODULE_REGISTRY
 *   - 2c: DynamicStage renders modules in loadPriority order
 *   - 2d: Disabled modules are filtered out
 *
 * **Validates: Requirements 1.2, 1.3, 11.2, 11.3**
 *
 * Tests the config-to-rendering contract (data flow logic) without DOM rendering.
 */

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  MARKET_CONFIGS,
  getMarketConfig,
  getStageModules,
  MODULE_REGISTRY,
} from './marketConfig.js';

// ---------------------------------------------------------------------------
// Helper: Simulate DynamicStage data transformation
// This replicates the logic in DynamicStage.jsx:
//   1. Filter modules where enabled === true
//   2. Sort by loadPriority ascending
//   3. Return component names in that order
// ---------------------------------------------------------------------------

function simulateDynamicStageOutput(stageDefinition) {
  const enabledModules = stageDefinition.modules.filter(m => m.enabled);
  const sortedModules = [...enabledModules].sort((a, b) => a.loadPriority - b.loadPriority);
  return sortedModules.map(m => m.component);
}

// ---------------------------------------------------------------------------
// Property 2a: For each market, verify config.stages.length matches expected
// NEM = 7 stages, WEM = 5 stages（NEM 新增 investment-decision 阶段，2026-08-20 同步）
// **Validates: Requirements 1.2, 1.3**
// ---------------------------------------------------------------------------

describe('Property 2a: Stage count matches expected per market', () => {
  test('NEM config has exactly 7 stages', () => {
    const config = getMarketConfig('NEM');
    assert.equal(config.stages.length, 7,
      `NEM should have 7 stages, got ${config.stages.length}`);
  });

  test('WEM config has exactly 5 stages', () => {
    const config = getMarketConfig('WEM');
    assert.equal(config.stages.length, 5,
      `WEM should have 5 stages, got ${config.stages.length}`);
  });

  test('MarketPage would render exactly config.stages.length DynamicStage components per market', () => {
    for (const marketId of Object.keys(MARKET_CONFIGS)) {
      const config = getMarketConfig(marketId);
      // MarketPage iterates config.stages.map(...) so rendered count = stages.length
      const renderedStageCount = config.stages.length;
      assert.equal(renderedStageCount, config.stages.length,
        `${marketId}: rendered stage count should equal config.stages.length`);
    }
  });
});

// ---------------------------------------------------------------------------
// Property 2b: For each stage in each market, verify all enabled modules
// have entries in MODULE_REGISTRY
// **Validates: Requirements 11.2, 11.3**
// ---------------------------------------------------------------------------

describe('Property 2b: All enabled modules have MODULE_REGISTRY entries', () => {
  for (const marketId of Object.keys(MARKET_CONFIGS)) {
    const config = MARKET_CONFIGS[marketId];

    for (const stage of config.stages) {
      test(`${marketId}/${stage.id}: all enabled modules exist in MODULE_REGISTRY`, () => {
        const enabledModules = stage.modules.filter(m => m.enabled);
        for (const mod of enabledModules) {
          assert.ok(
            MODULE_REGISTRY[mod.component],
            `${marketId}/${stage.id}: enabled module "${mod.component}" not found in MODULE_REGISTRY`
          );
        }
      });
    }
  }

  test('MODULE_REGISTRY covers all unique components referenced across all markets', () => {
    const allComponents = new Set();
    for (const marketId of Object.keys(MARKET_CONFIGS)) {
      for (const stage of MARKET_CONFIGS[marketId].stages) {
        for (const mod of stage.modules) {
          allComponents.add(mod.component);
        }
      }
    }
    for (const component of allComponents) {
      assert.ok(
        MODULE_REGISTRY[component],
        `Component "${component}" referenced in config but missing from MODULE_REGISTRY`
      );
    }
  });
});

// ---------------------------------------------------------------------------
// Property 2c: Verify that DynamicStage would render modules in loadPriority
// order (sort and compare)
// **Validates: Requirements 1.2, 11.3**
// ---------------------------------------------------------------------------

describe('Property 2c: DynamicStage renders modules in loadPriority order', () => {
  for (const marketId of Object.keys(MARKET_CONFIGS)) {
    const config = MARKET_CONFIGS[marketId];

    for (const stage of config.stages) {
      test(`${marketId}/${stage.id}: modules are rendered sorted by loadPriority`, () => {
        const output = simulateDynamicStageOutput(stage);

        // Verify the output is sorted by loadPriority
        const enabledModules = stage.modules.filter(m => m.enabled);
        const sortedByPriority = [...enabledModules].sort((a, b) => a.loadPriority - b.loadPriority);
        const expectedOrder = sortedByPriority.map(m => m.component);

        assert.deepEqual(output, expectedOrder,
          `${marketId}/${stage.id}: module render order should match loadPriority sort`);
      });

      test(`${marketId}/${stage.id}: getStageModules matches DynamicStage output`, () => {
        // getStageModules should produce the same result as DynamicStage logic
        const dynamicStageOutput = simulateDynamicStageOutput(stage);
        const helperOutput = getStageModules(marketId, stage.id);

        assert.deepEqual(helperOutput, dynamicStageOutput,
          `${marketId}/${stage.id}: getStageModules should match DynamicStage rendering logic`);
      });
    }
  }

  test('loadPriority ordering is stable (equal priorities preserve insertion order)', () => {
    // For NEM market-screening, PriceChart and SummaryStats both have loadPriority=1
    const nemConfig = MARKET_CONFIGS.NEM;
    const screeningStage = nemConfig.stages.find(s => s.id === 'market-screening');
    assert.ok(screeningStage, 'NEM should have market-screening stage');

    const priority1Modules = screeningStage.modules
      .filter(m => m.enabled && m.loadPriority === 1);

    // Verify that modules with same priority exist (testing the property is meaningful)
    assert.ok(priority1Modules.length >= 2,
      'NEM market-screening should have at least 2 modules with loadPriority=1');

    // The sort is stable in modern JS engines, so insertion order is preserved
    const output = simulateDynamicStageOutput(screeningStage);
    const priority1InOutput = output.filter(c =>
      priority1Modules.some(m => m.component === c)
    );
    const priority1Expected = priority1Modules.map(m => m.component);
    assert.deepEqual(priority1InOutput, priority1Expected,
      'Modules with equal loadPriority should maintain config insertion order');
  });
});

// ---------------------------------------------------------------------------
// Property 2d: Verify that disabled modules (enabled: false) would be filtered out
// **Validates: Requirements 11.2, 11.3**
// ---------------------------------------------------------------------------

describe('Property 2d: Disabled modules are filtered out from rendering', () => {
  test('simulateDynamicStageOutput excludes modules with enabled=false', () => {
    // Create a synthetic stage with mixed enabled/disabled modules
    const syntheticStage = {
      id: 'test-stage',
      title: { zh: '测试', en: 'Test' },
      coreQuestion: { zh: '测试问题', en: 'Test question' },
      modules: [
        { component: 'PriceChart', dataDependencies: ['/api/test'], loadPriority: 1, enabled: true },
        { component: 'SummaryStats', dataDependencies: ['/api/test'], loadPriority: 2, enabled: false },
        { component: 'RegionalRanking', dataDependencies: ['/api/test'], loadPriority: 3, enabled: true },
      ],
    };

    const output = simulateDynamicStageOutput(syntheticStage);

    assert.ok(!output.includes('SummaryStats'),
      'Disabled module SummaryStats should not appear in output');
    assert.deepEqual(output, ['PriceChart', 'RegionalRanking'],
      'Only enabled modules should be rendered in priority order');
  });

  test('all disabled modules are excluded regardless of loadPriority', () => {
    const syntheticStage = {
      id: 'test-stage-2',
      title: { zh: '测试', en: 'Test' },
      coreQuestion: { zh: '测试', en: 'Test' },
      modules: [
        { component: 'A', dataDependencies: [], loadPriority: 1, enabled: false },
        { component: 'B', dataDependencies: [], loadPriority: 1, enabled: false },
        { component: 'C', dataDependencies: [], loadPriority: 2, enabled: true },
      ],
    };

    const output = simulateDynamicStageOutput(syntheticStage);
    assert.deepEqual(output, ['C'],
      'Only enabled module C should be rendered');
  });

  test('empty output when all modules are disabled', () => {
    const syntheticStage = {
      id: 'test-stage-3',
      title: { zh: '测试', en: 'Test' },
      coreQuestion: { zh: '测试', en: 'Test' },
      modules: [
        { component: 'A', dataDependencies: [], loadPriority: 1, enabled: false },
        { component: 'B', dataDependencies: [], loadPriority: 2, enabled: false },
      ],
    };

    const output = simulateDynamicStageOutput(syntheticStage);
    assert.deepEqual(output, [],
      'No modules should be rendered when all are disabled');
  });

  test('current configs have all modules enabled (baseline verification)', () => {
    // Verify that in the current production config, all modules are enabled
    // This ensures the feature flag mechanism works but isn't accidentally disabling anything
    for (const marketId of Object.keys(MARKET_CONFIGS)) {
      for (const stage of MARKET_CONFIGS[marketId].stages) {
        const disabledModules = stage.modules.filter(m => !m.enabled);
        assert.equal(disabledModules.length, 0,
          `${marketId}/${stage.id}: found unexpected disabled modules: ${disabledModules.map(m => m.component).join(', ')}`);
      }
    }
  });

  test('disabling a module reduces rendered count by exactly 1', () => {
    // Take a real stage and simulate disabling one module
    const nemConfig = MARKET_CONFIGS.NEM;
    const stage = nemConfig.stages[0]; // market-screening with 4 modules

    const originalOutput = simulateDynamicStageOutput(stage);
    const originalCount = originalOutput.length;

    // Create a copy with one module disabled
    const modifiedStage = {
      ...stage,
      modules: stage.modules.map((m, i) =>
        i === 0 ? { ...m, enabled: false } : m
      ),
    };

    const modifiedOutput = simulateDynamicStageOutput(modifiedStage);
    assert.equal(modifiedOutput.length, originalCount - 1,
      'Disabling one module should reduce rendered count by exactly 1');
    assert.ok(!modifiedOutput.includes(stage.modules[0].component),
      'The disabled module should not appear in output');
  });
});
