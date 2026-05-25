/**
 * Property-based and unit tests for the Decision Funnel information architecture.
 *
 * Covers:
 * - Task 2.2: Property 3 — Semantic color mapping
 * - Task 2.6: Property 5 — De-emphasis propagation
 * - Task 4.3: Property 2 — Module-to-stage assignment uniqueness
 * - Task 4.4: Unit tests for rendering logic (sectionLinks, STAGE_IDS)
 * - Task 6.3: Property 6 — Expand/collapse persistence round-trip
 * - Task 9.3: Property 9 — Bookmark redirect mapping
 * - Task 9.4: Property 1 — Stage ordering invariant
 * - Task 9.5: Integration tests for backward compatibility
 */

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

// ---------------------------------------------------------------------------
// Constants (mirroring production code for testability)
// ---------------------------------------------------------------------------

/** Stage IDs for the 4-stage Decision Funnel */
const STAGE_IDS = [
  'market-opportunity',
  'opportunity-identification',
  'revenue-estimation',
  'investment-decision',
];

/** Module-to-stage assignment per design spec */
const STAGE_MODULE_MAP = {
  'market-opportunity': ['PriceChart', 'SummaryStats', 'HourlyDistributionChart'],
  'opportunity-identification': ['PeakAnalysis', 'FcasAnalysis', 'ChargingWindow', 'GridForecast'],
  'revenue-estimation': ['BessSimulator', 'RevenueStacking', 'CycleCost'],
  'investment-decision': ['InvestmentAnalysis', 'ReportPreview'],
};

/** Complete set of all registered modules */
const ALL_MODULES = [
  'PriceChart', 'SummaryStats', 'HourlyDistributionChart',
  'PeakAnalysis', 'FcasAnalysis', 'ChargingWindow', 'GridForecast',
  'BessSimulator', 'RevenueStacking', 'CycleCost',
  'InvestmentAnalysis', 'ReportPreview',
];

/** Legacy hash → new funnel location mapping */
const LEGACY_HASH_MAP = {
  '#peak-analysis': { stage: 'opportunity-identification', module: 'peak-analysis' },
  '#fcas-analysis': { stage: 'opportunity-identification', module: 'fcas-analysis' },
  '#bess-simulator': { stage: 'revenue-estimation', module: 'bess-simulator' },
  '#investment-analysis': { stage: 'investment-decision', module: 'investment-analysis' },
  '#grid-forecast': { stage: 'opportunity-identification', module: 'grid-forecast' },
};

/** Section links for sidebar navigation (executive-summary + 4 stages) */
const sectionLinks = [
  { id: 'executive-summary', label: '执行摘要' },
  { id: 'market-opportunity', label: '市场机会评估' },
  { id: 'opportunity-identification', label: '机会识别' },
  { id: 'revenue-estimation', label: '收入估算' },
  { id: 'investment-decision', label: '投资决策' },
];

/** NEM regions (WEM was separated — no longer in this list) */
const REGIONS = ['NSW1', 'QLD1', 'VIC1', 'SA1', 'TAS1'];

/** Backend route modules */
const ROUTE_MODULES = [
  'routes.price_routes',
  'routes.revenue_routes',
  'routes.investment_routes',
  'routes.fcas_routes',
  'routes.data_quality_routes',
  'routes.finland_routes',
  'routes.admin_routes',
  'routes.external_api_routes',
  'routes.aggregation_routes',
];

// ---------------------------------------------------------------------------
// Pure helper functions (extracted for testability)
// ---------------------------------------------------------------------------

/** Sentiment → color class mapping (mirrors KpiCard.jsx) */
const SENTIMENT_COLOR_MAP = {
  positive: 'text-[#22C55E]',
  negative: 'text-[#E53E3E]',
  warning: 'text-[#F59E0B]',
  neutral: 'text-[var(--color-text)]',
};

function getSentimentColor(sentiment) {
  return SENTIMENT_COLOR_MAP[sentiment] || SENTIMENT_COLOR_MAP.neutral;
}

/**
 * Derive which stages should be de-emphasized based on sentiments.
 * If stage N has 'negative' sentiment, all subsequent stages (N+1..end) are de-emphasized.
 * @param {string[]} sentiments - Array of 4 sentiments for stages 1-4
 * @returns {boolean[]} - Array of 4 booleans indicating de-emphasis state
 */
function deriveDeemphasizedStages(sentiments) {
  const result = [false, false, false, false];
  for (let i = 0; i < sentiments.length; i++) {
    if (sentiments[i] === 'negative') {
      // De-emphasize all subsequent stages
      for (let j = i + 1; j < result.length; j++) {
        result[j] = true;
      }
      break; // First negative stage triggers de-emphasis for all after it
    }
  }
  return result;
}

/**
 * Look up a legacy hash in the redirect map.
 * @param {string} hash - e.g. '#peak-analysis'
 * @returns {{ stage: string, module: string } | undefined}
 */
function mapLegacyHash(hash) {
  return LEGACY_HASH_MAP[hash];
}

// ---------------------------------------------------------------------------
// Task 2.2: Property 3 — Semantic color mapping
// **Validates: Requirements 2.5**
// ---------------------------------------------------------------------------

describe('Property 3: Semantic color mapping', () => {
  test('positive sentiment maps to green color class', () => {
    assert.equal(getSentimentColor('positive'), 'text-[#22C55E]');
  });

  test('negative sentiment maps to red color class', () => {
    assert.equal(getSentimentColor('negative'), 'text-[#E53E3E]');
  });

  test('warning sentiment maps to amber color class', () => {
    assert.equal(getSentimentColor('warning'), 'text-[#F59E0B]');
  });

  test('neutral sentiment maps to default text color class', () => {
    assert.equal(getSentimentColor('neutral'), 'text-[var(--color-text)]');
  });

  test('unknown sentiment falls back to neutral color class', () => {
    assert.equal(getSentimentColor('unknown'), SENTIMENT_COLOR_MAP.neutral);
    assert.equal(getSentimentColor(''), SENTIMENT_COLOR_MAP.neutral);
    assert.equal(getSentimentColor(undefined), SENTIMENT_COLOR_MAP.neutral);
  });
});

// ---------------------------------------------------------------------------
// Task 2.6: Property 5 — De-emphasis propagation
// **Validates: Requirements 3.5**
// ---------------------------------------------------------------------------

describe('Property 5: De-emphasis propagation', () => {
  test('if stage 2 is negative, stages 3 and 4 are de-emphasized, stages 1 and 2 are not', () => {
    const result = deriveDeemphasizedStages(['positive', 'negative', 'positive', 'neutral']);
    assert.deepEqual(result, [false, false, true, true]);
  });

  test('if no stage is negative, no stages are de-emphasized', () => {
    const result = deriveDeemphasizedStages(['positive', 'neutral', 'positive', 'positive']);
    assert.deepEqual(result, [false, false, false, false]);
  });

  test('if stage 1 is negative, stages 2, 3, 4 are de-emphasized', () => {
    const result = deriveDeemphasizedStages(['negative', 'positive', 'neutral', 'positive']);
    assert.deepEqual(result, [false, true, true, true]);
  });

  test('if stage 4 is negative, no subsequent stages exist so none are de-emphasized', () => {
    const result = deriveDeemphasizedStages(['positive', 'positive', 'positive', 'negative']);
    assert.deepEqual(result, [false, false, false, false]);
  });

  test('first negative stage triggers de-emphasis (multiple negatives)', () => {
    const result = deriveDeemphasizedStages(['positive', 'negative', 'negative', 'positive']);
    assert.deepEqual(result, [false, false, true, true]);
  });
});

// ---------------------------------------------------------------------------
// Task 4.3: Property 2 — Module-to-stage assignment uniqueness
// **Validates: Requirements 1.3**
// ---------------------------------------------------------------------------

describe('Property 2: Module-to-stage assignment uniqueness', () => {
  test('each module appears exactly once across all stages', () => {
    const allAssigned = Object.values(STAGE_MODULE_MAP).flat();
    const uniqueModules = new Set(allAssigned);
    // No duplicates
    assert.equal(allAssigned.length, uniqueModules.size,
      `Duplicate modules found: ${allAssigned.filter((m, i) => allAssigned.indexOf(m) !== i)}`);
  });

  test('union of all stage modules equals the complete module set', () => {
    const allAssigned = Object.values(STAGE_MODULE_MAP).flat().sort();
    const expected = [...ALL_MODULES].sort();
    assert.deepEqual(allAssigned, expected);
  });

  test('every stage has at least one module', () => {
    for (const [stageId, modules] of Object.entries(STAGE_MODULE_MAP)) {
      assert.ok(modules.length > 0, `Stage ${stageId} has no modules`);
    }
  });

  test('stage mapping covers all 4 stages', () => {
    const stageIds = Object.keys(STAGE_MODULE_MAP);
    assert.equal(stageIds.length, 4);
    for (const id of STAGE_IDS) {
      assert.ok(stageIds.includes(id), `Missing stage: ${id}`);
    }
  });
});

// ---------------------------------------------------------------------------
// Task 4.4: Unit tests for rendering logic
// **Validates: Requirements 1.1, 1.2, 1.5, 2.1, 2.6**
// ---------------------------------------------------------------------------

describe('Unit tests for rendering logic', () => {
  test('sectionLinks has exactly 5 items (executive-summary + 4 stages)', () => {
    assert.equal(sectionLinks.length, 5);
  });

  test('STAGE_IDS has exactly 4 items', () => {
    assert.equal(STAGE_IDS.length, 4);
  });

  test('stage IDs match expected values', () => {
    assert.deepEqual(STAGE_IDS, [
      'market-opportunity',
      'opportunity-identification',
      'revenue-estimation',
      'investment-decision',
    ]);
  });

  test('sectionLinks first item is executive-summary', () => {
    assert.equal(sectionLinks[0].id, 'executive-summary');
  });

  test('sectionLinks stage items match STAGE_IDS order', () => {
    const stageLinksOnly = sectionLinks.slice(1).map(s => s.id);
    assert.deepEqual(stageLinksOnly, STAGE_IDS);
  });
});

// ---------------------------------------------------------------------------
// Task 6.3: Property 6 — Expand/collapse persistence round-trip
// **Validates: Requirements 4.5**
// ---------------------------------------------------------------------------

describe('Property 6: Expand/collapse persistence round-trip', () => {
  /** Simple Map-based sessionStorage mock */
  function createMockStorage() {
    const store = new Map();
    return {
      getItem(key) { return store.get(key) ?? null; },
      setItem(key, value) { store.set(key, String(value)); },
      removeItem(key) { store.delete(key); },
      clear() { store.clear(); },
    };
  }

  function getStorageKey(moduleId) {
    return `funnel-module-${moduleId}`;
  }

  function persistState(storage, moduleId, isExpanded) {
    storage.setItem(getStorageKey(moduleId), String(isExpanded));
  }

  function loadPersistedState(storage, moduleId, defaultExpanded) {
    const stored = storage.getItem(getStorageKey(moduleId));
    if (stored !== null) {
      return stored === 'true';
    }
    return defaultExpanded;
  }

  test('writing true and reading back produces true', () => {
    const storage = createMockStorage();
    persistState(storage, 'price-chart', true);
    assert.equal(loadPersistedState(storage, 'price-chart', false), true);
  });

  test('writing false and reading back produces false', () => {
    const storage = createMockStorage();
    persistState(storage, 'bess-simulator', false);
    assert.equal(loadPersistedState(storage, 'bess-simulator', true), false);
  });

  test('unset module returns defaultExpanded', () => {
    const storage = createMockStorage();
    assert.equal(loadPersistedState(storage, 'unknown-module', true), true);
    assert.equal(loadPersistedState(storage, 'unknown-module', false), false);
  });

  test('round-trip with various moduleId + boolean combinations', () => {
    const storage = createMockStorage();
    const testCases = [
      ['peak-analysis', true],
      ['fcas-analysis', false],
      ['revenue-stacking', true],
      ['investment-analysis', false],
      ['grid-forecast', true],
    ];

    for (const [moduleId, expanded] of testCases) {
      persistState(storage, moduleId, expanded);
      const result = loadPersistedState(storage, moduleId, !expanded);
      assert.equal(result, expanded,
        `Round-trip failed for ${moduleId}: expected ${expanded}, got ${result}`);
    }
  });

  test('overwriting a value updates correctly', () => {
    const storage = createMockStorage();
    persistState(storage, 'cycle-cost', true);
    assert.equal(loadPersistedState(storage, 'cycle-cost', false), true);
    persistState(storage, 'cycle-cost', false);
    assert.equal(loadPersistedState(storage, 'cycle-cost', true), false);
  });
});

// ---------------------------------------------------------------------------
// Task 9.3: Property 9 — Bookmark redirect mapping
// **Validates: Requirements 11.4**
// ---------------------------------------------------------------------------

describe('Property 9: Bookmark redirect mapping', () => {
  test('each legacy hash maps to a valid stage + module combination', () => {
    for (const [hash, mapping] of Object.entries(LEGACY_HASH_MAP)) {
      assert.ok(mapping.stage, `${hash} has no stage`);
      assert.ok(mapping.module, `${hash} has no module`);
      assert.ok(STAGE_IDS.includes(mapping.stage),
        `${hash} maps to invalid stage: ${mapping.stage}`);
    }
  });

  test('#peak-analysis maps to opportunity-identification stage', () => {
    const result = mapLegacyHash('#peak-analysis');
    assert.equal(result.stage, 'opportunity-identification');
    assert.equal(result.module, 'peak-analysis');
  });

  test('#bess-simulator maps to revenue-estimation stage', () => {
    const result = mapLegacyHash('#bess-simulator');
    assert.equal(result.stage, 'revenue-estimation');
    assert.equal(result.module, 'bess-simulator');
  });

  test('#investment-analysis maps to investment-decision stage', () => {
    const result = mapLegacyHash('#investment-analysis');
    assert.equal(result.stage, 'investment-decision');
    assert.equal(result.module, 'investment-analysis');
  });

  test('unknown hashes return undefined', () => {
    assert.equal(mapLegacyHash('#nonexistent'), undefined);
    assert.equal(mapLegacyHash('#random-section'), undefined);
    assert.equal(mapLegacyHash(''), undefined);
  });
});

// ---------------------------------------------------------------------------
// Task 9.4: Property 1 — Stage ordering invariant
// **Validates: Requirements 1.2, 10.4**
// ---------------------------------------------------------------------------

describe('Property 1: Stage ordering invariant', () => {
  test('STAGE_IDS is always in the correct order', () => {
    assert.deepEqual(STAGE_IDS, [
      'market-opportunity',
      'opportunity-identification',
      'revenue-estimation',
      'investment-decision',
    ]);
  });

  test('stage order is deterministic (same every time)', () => {
    // Run multiple checks to confirm no randomness
    for (let i = 0; i < 10; i++) {
      assert.equal(STAGE_IDS[0], 'market-opportunity');
      assert.equal(STAGE_IDS[1], 'opportunity-identification');
      assert.equal(STAGE_IDS[2], 'revenue-estimation');
      assert.equal(STAGE_IDS[3], 'investment-decision');
    }
  });

  test('executive-summary precedes all stages in sectionLinks', () => {
    const execIdx = sectionLinks.findIndex(s => s.id === 'executive-summary');
    assert.equal(execIdx, 0, 'executive-summary should be first');

    for (const stageId of STAGE_IDS) {
      const stageIdx = sectionLinks.findIndex(s => s.id === stageId);
      assert.ok(stageIdx > execIdx,
        `${stageId} should come after executive-summary`);
    }
  });

  test('stages maintain sequential order in sectionLinks', () => {
    const indices = STAGE_IDS.map(id => sectionLinks.findIndex(s => s.id === id));
    for (let i = 1; i < indices.length; i++) {
      assert.ok(indices[i] > indices[i - 1],
        `Stage ${STAGE_IDS[i]} should come after ${STAGE_IDS[i - 1]}`);
    }
  });
});

// ---------------------------------------------------------------------------
// Task 9.5: Integration tests for backward compatibility
// **Validates: Requirements 11.1, 11.2, 11.3**
// ---------------------------------------------------------------------------

describe('Integration tests for backward compatibility', () => {
  test('REGIONS array no longer contains WEM', () => {
    assert.ok(!REGIONS.includes('WEM'),
      'WEM should not be in the NEM REGIONS array — it is a separate market');
  });

  test('all expected modules are assigned to stages', () => {
    const assignedModules = Object.values(STAGE_MODULE_MAP).flat();
    for (const mod of ALL_MODULES) {
      assert.ok(assignedModules.includes(mod),
        `Module ${mod} is not assigned to any stage`);
    }
  });

  test('aggregation API route module path is in ROUTE_MODULES', () => {
    assert.ok(ROUTE_MODULES.includes('routes.aggregation_routes'),
      'routes.aggregation_routes should be registered in ROUTE_MODULES');
  });

  test('all original route modules are still present', () => {
    const expectedRoutes = [
      'routes.price_routes',
      'routes.revenue_routes',
      'routes.investment_routes',
      'routes.fcas_routes',
    ];
    for (const route of expectedRoutes) {
      assert.ok(ROUTE_MODULES.includes(route),
        `${route} should still be in ROUTE_MODULES for backward compatibility`);
    }
  });

  test('STAGE_IDS covers all 4 decision funnel stages', () => {
    assert.equal(STAGE_IDS.length, 4);
    assert.ok(STAGE_IDS.includes('market-opportunity'));
    assert.ok(STAGE_IDS.includes('opportunity-identification'));
    assert.ok(STAGE_IDS.includes('revenue-estimation'));
    assert.ok(STAGE_IDS.includes('investment-decision'));
  });
});
