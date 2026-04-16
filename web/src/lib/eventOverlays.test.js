import test from 'node:test';
import assert from 'node:assert/strict';

import { buildOverlayNotice, coverageText, describeEventEvidence, metaForState } from './eventOverlays.js';

test('buildOverlayNotice reports missing verified coverage explicitly', () => {
  const notice = buildOverlayNotice({
    metadata: {
      coverage_quality: 'none',
      no_verified_event_explanation: true,
    },
    daily_rollup: [],
    events: [],
  });

  assert.equal(notice.variant, 'neutral');
  assert.equal(notice.hasEvents, false);
  assert.match(notice.title, /No verified event explanation/i);
  assert.match(notice.message, /selected window/i);
});

test('buildOverlayNotice highlights partial or core event coverage and top states', () => {
  const notice = buildOverlayNotice({
    metadata: {
      coverage_quality: 'core_only',
      no_verified_event_explanation: false,
    },
    daily_rollup: [
      {
        date: '2026-04-14',
        event_count: 2,
        highest_severity: 'high',
        top_states: [
          { key: 'reserve_tightness', severity: 'high', count: 2 },
          { key: 'network_stress', severity: 'medium', count: 1 },
        ],
      },
    ],
    events: [
      { event_id: 'ev-1' },
      { event_id: 'ev-2' },
    ],
  });

  assert.equal(notice.variant, 'warning');
  assert.equal(notice.hasEvents, true);
  assert.equal(notice.coverageQuality, 'core_only');
  assert.equal(notice.topStates[0].key, 'reserve_tightness');
  assert.match(notice.message, /core coverage only/i);
});

test('event overlay copy can be localized to Chinese', () => {
  const notice = buildOverlayNotice({
    metadata: {
      coverage_quality: 'core_only',
      no_verified_event_explanation: false,
    },
    daily_rollup: [
      {
        date: '2026-04-14',
        event_count: 1,
        highest_severity: 'high',
        top_states: [{ key: 'network_stress', severity: 'high', count: 1 }],
      },
    ],
    events: [{ event_id: 'ev-1' }],
  }, 'zh');

  assert.equal(coverageText('core_only', 'zh'), '核心覆盖');
  assert.equal(metaForState('network_stress', 'zh').label, '网络压力');
  assert.equal(notice.title, '存在事件解释');
  assert.match(notice.message, /核心覆盖/);
});

test('describeEventEvidence builds Chinese explanation while preserving original official text', () => {
  const event = {
    source: 'nem_market_notice',
    title: '[EventId:202604131535_NRM_QLD1_NSW1_started] NEGRES CONSTRAINT NRM_QLD1_NSW1 started operating from 13 April 2026 15:35',
    summary: 'ACTUAL NEGATIVE SETTLEMENT RESIDUES - QLD to NSW - 13 April 2026.\nThe negative residue constraint set commenced operating.',
    effective_start: '2026-04-13 15:35:25',
    effective_end: '2026-04-13 16:15:40',
    published_at: '2026-04-13 15:35:25',
    raw_class: 'SETTLEMENTS RESIDUE',
    region_scope: ['NSW1', 'QLD1'],
    asset_scope: [],
    normalized_states: ['network_stress', 'security_intervention'],
  };

  const rendered = describeEventEvidence(event, 'zh');

  assert.equal(rendered.sourceLabel, 'AEMO 市场公告');
  assert.match(rendered.title, /网络压力/);
  assert.match(rendered.title, /安全干预/);
  assert.match(rendered.summary, /影响区域/);
  assert.match(rendered.summary, /NSW1/);
  assert.equal(rendered.hasOfficialOriginal, true);
  assert.match(rendered.officialOriginalText, /NEGRES CONSTRAINT/);
  assert.match(rendered.officialOriginalText, /ACTUAL NEGATIVE SETTLEMENT RESIDUES/);
  assert.equal(rendered.originalTitle, event.title);
  assert.equal(rendered.originalSummary, event.summary);
});
