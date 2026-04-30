# P0 Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first end-to-end P0 data foundation for the repo: AEMO-first canonical data contracts, adapter registry upgrades, initial fundamentals/grid-state/settlement dataset families, unified API metadata, and frontend consumption constraints.

**Architecture:** Extend the existing lightweight canonical schema and connector registry rather than replacing them. Keep raw-source semantics at adapter boundaries, standardize canonical dataset families plus metadata in backend contracts, then expose those contracts incrementally through backend APIs and frontend metadata helpers.

**Tech Stack:** Python, FastAPI, existing backend modules, unittest/pytest, React, existing frontend metadata utilities

---

## File Structure

### Existing files to extend

- `backend/canonical_market_schema.py`
  - Expand from row mappers into a canonical dataset-family contract layer.
- `backend/connector_framework.py`
  - Evolve connector specs into adapter-aware, dataset-family-aware registry entries.
- `backend/result_metadata.py`
  - Add richer metadata contract fields needed by P0.
- `backend/server.py`
  - Add canonical metadata wiring and one or more P0-oriented serving endpoints.
- `web/src/lib/resultMetadata.js`
  - Add frontend-safe readers for expanded metadata contract.
- `web/src/translations.js`
  - Add i18n-safe copy keys for new grade / freshness / coverage / contract states.
- `tests/test_canonical_market_schema.py`
  - Expand backend canonical contract coverage.
- `tests/test_connector_framework.py`
  - Expand adapter contract coverage.
- `tests/test_result_metadata.py`
  - Expand metadata contract coverage and API integration assertions.

### New backend files to create

- `backend/canonical_dataset_registry.py`
  - Central registry for dataset families, observation kinds, and scope rules.
- `backend/aemo_p0_datasets.py`
  - AEMO-first canonical adapters for fundamentals, grid-state, and settlement datasets.

### New frontend/test files to create

- `tests/test_aemo_p0_datasets.py`
  - Unit tests for AEMO-first canonical dataset builders.
- `tests/test_p0_contract_routes.py`
  - Focused API tests for new P0 serving endpoints / contract helpers.
- `web/src/lib/resultMetadataP0.test.js`
  - Frontend parsing tests for new metadata contract helpers.

---

## Task 1: Canonical dataset family and metadata contract

**Files:**
- Create: `backend/canonical_dataset_registry.py`
- Modify: `backend/canonical_market_schema.py`
- Modify: `backend/result_metadata.py`
- Test: `tests/test_canonical_market_schema.py`
- Test: `tests/test_result_metadata.py`

- [ ] **Step 1: Write the failing backend tests for canonical dataset families**

```python
def test_dataset_family_registry_contains_required_p0_families():
    from canonical_dataset_registry import DATASET_FAMILY_REGISTRY

    assert "load_forecast" in DATASET_FAMILY_REGISTRY
    assert "load_actual" in DATASET_FAMILY_REGISTRY
    assert "wind_forecast" in DATASET_FAMILY_REGISTRY
    assert "solar_actual" in DATASET_FAMILY_REGISTRY
    assert "constraint" in DATASET_FAMILY_REGISTRY
    assert "settlement" in DATASET_FAMILY_REGISTRY


def test_build_result_metadata_supports_grade_lineage_and_contract_fields():
    from result_metadata import build_result_metadata

    payload = build_result_metadata(
        market="NEM",
        region_or_zone="NSW1",
        timezone="Australia/Sydney",
        currency="AUD",
        unit="MW",
        interval_minutes=30,
        data_grade="preview",
        data_quality_score=0.87,
        coverage={"coverage_ratio": 0.92},
        freshness={"last_updated_at": "2026-04-30T00:00:00Z"},
        source_name="AEMO",
        source_version="p0_test_v1",
        methodology_version="p0_contract_v1",
        warnings=["source_partial"],
        dataset_family="load_forecast",
        observation_kind="forecast",
        lineage={"source_id": "aemo_operational_demand"},
        grade="preview",
    )

    assert payload["dataset_family"] == "load_forecast"
    assert payload["observation_kind"] == "forecast"
    assert payload["lineage"]["source_id"] == "aemo_operational_demand"
    assert payload["grade"] == "preview"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_canonical_market_schema.py tests/test_result_metadata.py -q
```

Expected:

- FAIL because `canonical_dataset_registry` does not exist yet
- FAIL because `build_result_metadata` does not yet accept `dataset_family`, `observation_kind`, `lineage`, or `grade`

- [ ] **Step 3: Implement the minimal canonical dataset registry**

```python
# backend/canonical_dataset_registry.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetFamilySpec:
    family: str
    observation_kind: str
    default_unit: str | None = None
    scope_type: str = "region"
    supports_counterpart: bool = False


DATASET_FAMILY_REGISTRY = {
    "load_forecast": DatasetFamilySpec("load_forecast", "forecast", "MW", "region", True),
    "load_actual": DatasetFamilySpec("load_actual", "actual", "MW", "region", True),
    "wind_forecast": DatasetFamilySpec("wind_forecast", "forecast", "MW", "region", True),
    "wind_actual": DatasetFamilySpec("wind_actual", "actual", "MW", "region", True),
    "solar_forecast": DatasetFamilySpec("solar_forecast", "forecast", "MW", "region", True),
    "solar_actual": DatasetFamilySpec("solar_actual", "actual", "MW", "region", True),
    "rooftop_pv": DatasetFamilySpec("rooftop_pv", "actual", "MW", "region", False),
    "outage": DatasetFamilySpec("outage", "event", None, "region", False),
    "unit_availability": DatasetFamilySpec("unit_availability", "state", "MW", "region", False),
    "interconnector_flow": DatasetFamilySpec("interconnector_flow", "actual", "MW", "interconnector", False),
    "reserve_requirement": DatasetFamilySpec("reserve_requirement", "state", "MW", "region", False),
    "reserve_shortfall": DatasetFamilySpec("reserve_shortfall", "event", "MW", "region", False),
    "weather": DatasetFamilySpec("weather", "actual", None, "region", False),
    "constraint": DatasetFamilySpec("constraint", "state", None, "region", False),
    "settlement": DatasetFamilySpec("settlement", "settlement", "AUD", "region", False),
}


def get_dataset_family_spec(family: str) -> DatasetFamilySpec:
    try:
        return DATASET_FAMILY_REGISTRY[family]
    except KeyError as exc:
        raise KeyError(f"Unknown dataset family: {family}") from exc
```

- [ ] **Step 4: Extend canonical schema and metadata contract**

```python
# backend/result_metadata.py
def build_result_metadata(
    *,
    market: str,
    region_or_zone: str,
    timezone: str,
    currency: str,
    unit: str,
    interval_minutes: int | None,
    data_grade: str,
    data_quality_score: float | None,
    coverage: dict[str, Any] | None,
    freshness: dict[str, Any] | None,
    source_name: str,
    source_version: str,
    methodology_version: str,
    warnings: list[str] | None = None,
    dataset_family: str | None = None,
    observation_kind: str | None = None,
    lineage: dict[str, Any] | None = None,
    grade: str | None = None,
) -> dict[str, Any]:
    return {
        "market": market,
        "region_or_zone": region_or_zone,
        "timezone": timezone,
        "currency": currency,
        "unit": unit,
        "interval_minutes": interval_minutes,
        "data_grade": data_grade,
        "data_quality_score": data_quality_score,
        "coverage": dict(coverage) if coverage else {},
        "freshness": dict(freshness) if freshness else {},
        "source_name": source_name,
        "source_version": source_version,
        "methodology_version": methodology_version,
        "warnings": list(warnings) if warnings else [],
        "dataset_family": dataset_family,
        "observation_kind": observation_kind,
        "lineage": dict(lineage) if lineage else {},
        "grade": grade or data_grade,
    }
```

```python
# backend/canonical_market_schema.py
def build_series_contract(
    *,
    dataset_family: str,
    observation_kind: str,
    market: str,
    country: str,
    region_or_zone: str,
    interval_minutes: int | None,
    unit: str | None,
    points: list[dict],
    source_name: str,
    source_version: str,
    ingested_at: str,
    coverage: dict | None = None,
    freshness: dict | None = None,
    quality: dict | None = None,
    warnings: list[str] | None = None,
    lineage: dict | None = None,
    counterpart_series_id: str | None = None,
) -> dict:
    return {
        "dataset_family": dataset_family,
        "observation_kind": observation_kind,
        "market": market,
        "country": country,
        "region_or_zone": region_or_zone,
        "interval_minutes": interval_minutes,
        "unit": unit,
        "points": list(points),
        "coverage": dict(coverage or {}),
        "freshness": dict(freshness or {}),
        "quality": dict(quality or {}),
        "warnings": list(warnings or []),
        "lineage": dict(lineage or {}),
        "counterpart_series_id": counterpart_series_id,
        "source_name": source_name,
        "source_version": source_version,
        "ingested_at": ingested_at,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/test_canonical_market_schema.py tests/test_result_metadata.py -q
```

Expected:

- PASS for new registry and metadata assertions
- Existing metadata tests still PASS

- [ ] **Step 6: Commit**

```bash
git add backend/canonical_dataset_registry.py backend/canonical_market_schema.py backend/result_metadata.py tests/test_canonical_market_schema.py tests/test_result_metadata.py
git commit -m "feat: add canonical dataset family contract"
```

---

## Task 2: Connector framework and AEMO-first adapter contract

**Files:**
- Modify: `backend/connector_framework.py`
- Create: `backend/aemo_p0_datasets.py`
- Test: `tests/test_connector_framework.py`
- Test: `tests/test_aemo_p0_datasets.py`

- [ ] **Step 1: Write the failing tests for connector dataset-family contracts**

```python
def test_connector_specs_include_dataset_family_and_observation_kind():
    from connector_framework import get_connector_spec

    spec = get_connector_spec("aemo_nem_operational_demand")
    assert spec.dataset_family == "load_actual"
    assert spec.observation_kind == "actual"
    assert spec.adapter == "build_aemo_load_actual_series"


def test_aemo_load_actual_series_builds_canonical_contract():
    from aemo_p0_datasets import build_aemo_load_actual_series

    payload = build_aemo_load_actual_series(
        rows=[{"interval_start": "2026-04-30T00:00:00Z", "interval_end": "2026-04-30T00:30:00Z", "value": 8450.0}],
        region="NSW1",
        ingested_at="2026-04-30T01:00:00Z",
    )

    assert payload["dataset_family"] == "load_actual"
    assert payload["observation_kind"] == "actual"
    assert payload["region_or_zone"] == "NSW1"
    assert payload["unit"] == "MW"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_connector_framework.py tests/test_aemo_p0_datasets.py -q
```

Expected:

- FAIL because `aemo_p0_datasets.py` does not exist
- FAIL because connector specs do not yet carry `dataset_family`, `observation_kind`, or `adapter`

- [ ] **Step 3: Extend connector specs and add AEMO-first canonical adapter builders**

```python
# backend/connector_framework.py
@dataclass(frozen=True)
class ConnectorSpec:
    source_id: str
    market: str
    entrypoint: str
    run_modes: tuple[str, ...]
    backfill_policy: str
    rate_limit: str
    schema_mapping: str
    quality_checks: tuple[str, ...]
    dataset_family: str
    observation_kind: str
    adapter: str
    notes: str = ""
```

```python
# backend/aemo_p0_datasets.py
from canonical_market_schema import build_series_contract


def build_aemo_load_actual_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    points = [
        {
            "interval_start_utc": row["interval_start"],
            "interval_end_utc": row["interval_end"],
            "value": row["value"],
        }
        for row in rows
    ]
    return build_series_contract(
        dataset_family="load_actual",
        observation_kind="actual",
        market="NEM",
        country="Australia",
        region_or_zone=region,
        interval_minutes=30,
        unit="MW",
        points=points,
        source_name="AEMO",
        source_version="aemo_operational_demand_v1",
        ingested_at=ingested_at,
        coverage={"actual_intervals": len(points)},
        freshness={"last_updated_at": ingested_at},
        quality={"completeness": 1.0 if points else 0.0},
        lineage={"source_id": "aemo_nem_operational_demand"},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/test_connector_framework.py tests/test_aemo_p0_datasets.py -q
```

Expected:

- PASS for extended connector contract
- PASS for first AEMO canonical series builder

- [ ] **Step 5: Commit**

```bash
git add backend/connector_framework.py backend/aemo_p0_datasets.py tests/test_connector_framework.py tests/test_aemo_p0_datasets.py
git commit -m "feat: add aemo p0 connector adapter contracts"
```

---

## Task 3: AEMO-first fundamentals, grid-state, and settlement dataset builders

**Files:**
- Modify: `backend/aemo_p0_datasets.py`
- Modify: `backend/canonical_dataset_registry.py`
- Test: `tests/test_aemo_p0_datasets.py`

- [ ] **Step 1: Write the failing tests for additional dataset families**

```python
def test_build_aemo_constraint_series_marks_input_layer_not_regime():
    from aemo_p0_datasets import build_aemo_constraint_series

    payload = build_aemo_constraint_series(
        rows=[{
            "constraint_id": "N::TEST",
            "binding_flag": True,
            "shadow_price": 1450.0,
            "effective_start": "2026-04-30T00:00:00Z",
            "effective_end": "2026-04-30T00:05:00Z",
        }],
        region="NSW1",
        ingested_at="2026-04-30T01:00:00Z",
    )

    assert payload["dataset_family"] == "constraint"
    assert payload["observation_kind"] == "state"
    assert "regime" not in payload


def test_build_aemo_settlement_series_includes_lineage_and_quality():
    from aemo_p0_datasets import build_aemo_settlement_series

    payload = build_aemo_settlement_series(
        rows=[{
            "interval_start": "2026-04-30T00:00:00Z",
            "interval_end": "2026-04-30T00:30:00Z",
            "value": 120.5,
            "component": "energy",
            "finality": "prelim",
        }],
        region="NSW1",
        ingested_at="2026-04-30T01:00:00Z",
    )

    assert payload["dataset_family"] == "settlement"
    assert payload["observation_kind"] == "settlement"
    assert payload["lineage"]["source_id"] == "aemo_settlement"
    assert payload["quality"]["finality"] == "prelim"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_aemo_p0_datasets.py -q
```

Expected:

- FAIL because `build_aemo_constraint_series` and `build_aemo_settlement_series` do not exist yet

- [ ] **Step 3: Implement minimal builders for grid-state and settlement families**

```python
# backend/aemo_p0_datasets.py
def build_aemo_constraint_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    points = [
        {
            "constraint_id": row["constraint_id"],
            "interval_start_utc": row["effective_start"],
            "interval_end_utc": row["effective_end"],
            "binding_flag": bool(row["binding_flag"]),
            "shadow_price": row["shadow_price"],
        }
        for row in rows
    ]
    return build_series_contract(
        dataset_family="constraint",
        observation_kind="state",
        market="NEM",
        country="Australia",
        region_or_zone=region,
        interval_minutes=5,
        unit=None,
        points=points,
        source_name="AEMO",
        source_version="aemo_constraint_v1",
        ingested_at=ingested_at,
        coverage={"actual_intervals": len(points)},
        freshness={"last_updated_at": ingested_at},
        quality={"completeness": 1.0 if points else 0.0},
        lineage={"source_id": "aemo_constraint"},
    )


def build_aemo_settlement_series(*, rows: list[dict], region: str, ingested_at: str) -> dict:
    points = [
        {
            "interval_start_utc": row["interval_start"],
            "interval_end_utc": row["interval_end"],
            "value": row["value"],
            "component": row["component"],
        }
        for row in rows
    ]
    finality = rows[0]["finality"] if rows else "unknown"
    return build_series_contract(
        dataset_family="settlement",
        observation_kind="settlement",
        market="NEM",
        country="Australia",
        region_or_zone=region,
        interval_minutes=30,
        unit="AUD",
        points=points,
        source_name="AEMO",
        source_version="aemo_settlement_v1",
        ingested_at=ingested_at,
        coverage={"actual_intervals": len(points)},
        freshness={"last_updated_at": ingested_at},
        quality={"completeness": 1.0 if points else 0.0, "finality": finality},
        lineage={"source_id": "aemo_settlement"},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/test_aemo_p0_datasets.py -q
```

Expected:

- PASS for load actual, constraint, and settlement canonical builders

- [ ] **Step 5: Commit**

```bash
git add backend/aemo_p0_datasets.py backend/canonical_dataset_registry.py tests/test_aemo_p0_datasets.py
git commit -m "feat: add aemo p0 dataset builders"
```

---

## Task 4: Backend serving contract and API integration

**Files:**
- Modify: `backend/server.py`
- Modify: `backend/result_metadata.py`
- Test: `tests/test_p0_contract_routes.py`
- Test: `tests/test_result_metadata.py`

- [ ] **Step 1: Write the failing API tests for P0 serving contract**

```python
def test_p0_dataset_contract_response_contains_required_metadata(client):
    response = client.get("/api/p0/datasets/load-actual?market=NEM&region=NSW1")
    payload = response.json()

    assert response.status_code == 200
    assert payload["metadata"]["dataset_family"] == "load_actual"
    assert payload["metadata"]["observation_kind"] == "actual"
    assert "lineage" in payload["metadata"]
    assert "grade" in payload["metadata"]


def test_existing_analysis_endpoints_keep_metadata_grade_alias():
    payload = server._attach_price_trend_metadata({"data": []}, region="NSW1")
    assert payload["metadata"]["grade"] == payload["metadata"]["data_grade"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest tests/test_p0_contract_routes.py tests/test_result_metadata.py -q
```

Expected:

- FAIL because `/api/p0/datasets/load-actual` does not exist yet
- FAIL if legacy metadata helpers do not yet include `dataset_family` / `observation_kind` / `grade`

- [ ] **Step 3: Add minimal P0 serving endpoint and metadata wiring**

```python
# backend/server.py
@app.get("/api/p0/datasets/load-actual", response_model=LooseObjectPayload)
def get_p0_load_actual_dataset(
    market: str = Query(...),
    region: str = Query(...),
):
    # Temporary AEMO-first serving implementation.
    payload = build_aemo_load_actual_series(
        rows=[],
        region=region,
        ingested_at=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    payload["metadata"] = build_result_metadata(
        market=market,
        region_or_zone=region,
        timezone=_region_timezone(region),
        currency="AUD",
        unit="MW",
        interval_minutes=30,
        data_grade="preview",
        data_quality_score=None,
        coverage=payload.get("coverage"),
        freshness=payload.get("freshness"),
        source_name=payload["source_name"],
        source_version=payload["source_version"],
        methodology_version="p0_dataset_contract_v1",
        warnings=payload.get("warnings", []),
        dataset_family=payload["dataset_family"],
        observation_kind=payload["observation_kind"],
        lineage=payload.get("lineage", {}),
        grade="preview",
    )
    return payload
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python -m pytest tests/test_p0_contract_routes.py tests/test_result_metadata.py -q
```

Expected:

- PASS for new P0 route contract
- PASS for legacy metadata compatibility assertions

- [ ] **Step 5: Commit**

```bash
git add backend/server.py backend/result_metadata.py tests/test_p0_contract_routes.py tests/test_result_metadata.py
git commit -m "feat: expose p0 dataset serving contract"
```

---

## Task 5: Frontend metadata consumption and guardrails

**Files:**
- Modify: `web/src/lib/resultMetadata.js`
- Modify: `web/src/translations.js`
- Create: `web/src/lib/resultMetadataP0.test.js`

- [ ] **Step 1: Write the failing frontend tests for P0 metadata helpers**

```javascript
import { getResultMetadata, getDataGradeCaveat, formatDatasetFamilyLabel } from './resultMetadata';

test('reads dataset family and lineage from metadata payload', () => {
  const metadata = getResultMetadata({
    metadata: {
      dataset_family: 'load_actual',
      observation_kind: 'actual',
      grade: 'preview',
      lineage: { source_id: 'aemo_nem_operational_demand' },
    },
  });

  expect(metadata.dataset_family).toBe('load_actual');
  expect(metadata.observation_kind).toBe('actual');
  expect(metadata.lineage.source_id).toBe('aemo_nem_operational_demand');
});

test('formats dataset family labels without hardcoding page-specific copy', () => {
  expect(formatDatasetFamilyLabel('load_actual', 'en')).toBe('Load Actual');
  expect(formatDatasetFamilyLabel('load_actual', 'zh')).toBe('负荷实绩');
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
npm --prefix web test -- --runInBand resultMetadataP0.test.js
```

Expected:

- FAIL because `dataset_family`, `observation_kind`, `lineage`, and `formatDatasetFamilyLabel` are not implemented yet

- [ ] **Step 3: Extend frontend metadata readers and i18n-safe labels**

```javascript
// web/src/lib/resultMetadata.js
export function getResultMetadata(payload = {}) {
  const metadata = payload?.metadata || {};
  return {
    market: metadata.market || '',
    region_or_zone: metadata.region_or_zone || '',
    timezone: metadata.timezone || '',
    currency: metadata.currency || '',
    unit: metadata.unit || '',
    interval_minutes: metadata.interval_minutes ?? null,
    data_grade: metadata.data_grade || 'unknown',
    grade: metadata.grade || metadata.data_grade || 'unknown',
    dataset_family: metadata.dataset_family || '',
    observation_kind: metadata.observation_kind || '',
    lineage: metadata.lineage || {},
    data_quality_score: metadata.data_quality_score ?? null,
    source_name: metadata.source_name || '',
    source_version: metadata.source_version || '',
    methodology_version: metadata.methodology_version || '',
    freshness: metadata.freshness || {},
    coverage: metadata.coverage || {},
    warnings: metadata.warnings || [],
  };
}

export function formatDatasetFamilyLabel(family = '', lang = 'en') {
  const normalizedLang = lang === 'zh' ? 'zh' : 'en';
  const labels = {
    load_actual: { zh: '负荷实绩', en: 'Load Actual' },
    load_forecast: { zh: '负荷预测', en: 'Load Forecast' },
    constraint: { zh: '约束输入', en: 'Constraint Input' },
    settlement: { zh: '结算输入', en: 'Settlement Input' },
  };
  return (labels[family] || { zh: family || '未知数据集', en: family || 'Unknown Dataset' })[normalizedLang];
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
npm --prefix web test -- --runInBand resultMetadataP0.test.js
```

Expected:

- PASS for dataset family, observation kind, lineage, and label formatting

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/resultMetadata.js web/src/translations.js web/src/lib/resultMetadataP0.test.js
git commit -m "feat: add frontend p0 metadata guardrails"
```

---

## Task 6: End-to-end verification and documentation sync

**Files:**
- Modify: `docs/商业化改造执行任务书.md`
- Modify: `docs/superpowers/specs/2026-04-30-p0-data-foundation-design.md`
- Test: `tests/test_p0_contract_routes.py`
- Test: `tests/test_aemo_p0_datasets.py`
- Test: `tests/test_result_metadata.py`
- Test: `web/src/lib/resultMetadataP0.test.js`

- [ ] **Step 1: Write the final verification checklist into docs before closing implementation**

```markdown
## P0 first-pass completion checklist

- Canonical dataset family registry added
- AEMO-first adapters added for load actual, constraint, settlement
- API metadata includes dataset_family, observation_kind, lineage, grade
- Frontend metadata readers consume canonical contract
- Preview-grade caveats remain visible in UI and API responses
```

- [ ] **Step 2: Run backend verification**

Run:

```bash
python -m pytest tests/test_canonical_market_schema.py tests/test_connector_framework.py tests/test_aemo_p0_datasets.py tests/test_p0_contract_routes.py tests/test_result_metadata.py -q
```

Expected:

- PASS for all backend P0 contract tests

- [ ] **Step 3: Run frontend verification**

Run:

```bash
npm --prefix web test -- --runInBand resultMetadataP0.test.js
```

Expected:

- PASS for frontend metadata contract tests

- [ ] **Step 4: Commit**

```bash
git add docs/商业化改造执行任务书.md docs/superpowers/specs/2026-04-30-p0-data-foundation-design.md
git commit -m "docs: record p0 data foundation rollout status"
```

---

## Self-Review

### Spec coverage

- `P0 canonical schema`: Covered by Task 1
- `AEMO-first adapters`: Covered by Tasks 2 and 3
- `API contract`: Covered by Task 4
- `Frontend consumption constraints`: Covered by Task 5
- `Verification and rollout sync`: Covered by Task 6

### Placeholder scan

- No `TBD`, `TODO`, or deferred placeholder steps remain in the plan

### Type consistency

- Canonical metadata fields use one naming set throughout:
  - `dataset_family`
  - `observation_kind`
  - `lineage`
  - `grade`
- Dataset builders consistently return `build_series_contract(...)` payloads

