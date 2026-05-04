import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from canonical_dataset_registry import DATASET_FAMILY_REGISTRY
from canonical_market_schema import (
    build_series_contract,
    map_fingrid_timeseries_row,
    map_nem_trading_price_row,
    map_wem_ess_market_row,
)
from fingrid.catalog import get_dataset_config
from fingrid.schemas import normalize_fingrid_row


class CanonicalMarketSchemaTests(unittest.TestCase):
    def test_dataset_family_registry_contains_required_p0_families(self):
        self.assertIn("load_forecast", DATASET_FAMILY_REGISTRY)
        self.assertIn("load_actual", DATASET_FAMILY_REGISTRY)
        self.assertIn("wind_forecast", DATASET_FAMILY_REGISTRY)
        self.assertIn("solar_actual", DATASET_FAMILY_REGISTRY)
        self.assertIn("constraint", DATASET_FAMILY_REGISTRY)
        self.assertIn("settlement", DATASET_FAMILY_REGISTRY)

    def test_maps_nem_trading_price_row_to_canonical_schema(self):
        row = map_nem_trading_price_row(
            {
                "settlement_date": "2026-04-01 00:05:00",
                "region_id": "NSW1",
                "rrp_aud_mwh": 132.45,
            },
            ingested_at="2026-04-27T08:00:00Z",
        )

        self.assertEqual(
            row,
            {
                "market": "NEM",
                "country": "Australia",
                "region_or_zone": "NSW1",
                "interval_start_utc": "2026-03-31T13:05:00Z",
                "interval_end_utc": "2026-03-31T13:10:00Z",
                "interval_minutes": 5,
                "product_type": "electricity",
                "service_type": "energy_spot",
                "currency": "AUD",
                "unit": "AUD/MWh",
                "value": 132.45,
                "source_name": "AEMO NEM",
                "source_version": "trading_price_v1",
                "ingested_at": "2026-04-27T08:00:00Z",
            },
        )

    def test_maps_wem_ess_market_row_to_canonical_schema(self):
        row = map_wem_ess_market_row(
            {
                "dispatch_interval": "2026-04-13 08:00:00",
                "energy_price": 87.3,
            },
            ingested_at="2026-04-27T08:00:00Z",
        )

        self.assertEqual(
            row,
            {
                "market": "WEM",
                "country": "Australia",
                "region_or_zone": "WEM",
                "interval_start_utc": "2026-04-13T00:00:00Z",
                "interval_end_utc": "2026-04-13T00:05:00Z",
                "interval_minutes": 5,
                "product_type": "electricity",
                "service_type": "energy_spot",
                "currency": "AUD",
                "unit": "AUD/MWh",
                "value": 87.3,
                "source_name": "AEMO WEM",
                "source_version": "wem_ess_market_price_v1",
                "ingested_at": "2026-04-27T08:00:00Z",
            },
        )

    def test_maps_fingrid_timeseries_row_to_canonical_schema(self):
        dataset = get_dataset_config("317")
        normalized_row = normalize_fingrid_row(
            dataset,
            {
                "startTime": "2026-01-01T00:00:00Z",
                "endTime": "2026-01-01T01:00:00Z",
                "value": 42.5,
                "updatedAt": "2026-01-01T00:05:00Z",
                "quality": "confirmed",
            },
            ingested_at="2026-04-27T08:00:00Z",
        )

        row = map_fingrid_timeseries_row(dataset, normalized_row)

        self.assertEqual(
            row,
            {
                "market": "Fingrid",
                "country": "Finland",
                "region_or_zone": "FI",
                "interval_start_utc": "2026-01-01T00:00:00Z",
                "interval_end_utc": "2026-01-01T01:00:00Z",
                "interval_minutes": 60,
                "product_type": "ancillary_service",
                "service_type": "reserve_capacity_price",
                "currency": "EUR",
                "unit": "EUR/MW",
                "value": 42.5,
                "source_name": "Fingrid",
                "source_version": "dataset_317_v1",
                "ingested_at": "2026-04-27T08:00:00Z",
            },
        )

    def test_build_series_contract_returns_canonical_dataset_payload(self):
        payload = build_series_contract(
            dataset_family="load_forecast",
            observation_kind="forecast",
            market="NEM",
            country="Australia",
            region_or_zone="NSW1",
            interval_minutes=30,
            unit="MW",
            points=[{"interval_start_utc": "2026-04-30T00:00:00Z", "value": 8450.0}],
            source_name="AEMO",
            source_version="p0_test_v1",
            ingested_at="2026-04-30T01:00:00Z",
            coverage={"coverage_ratio": 0.92},
            freshness={"last_updated_at": "2026-04-30T01:00:00Z"},
            quality={"completeness": 0.92},
            warnings=["source_partial"],
            lineage={"source_id": "aemo_operational_demand"},
            counterpart_series_id="series-load-actual-nsw1",
        )

        self.assertEqual(payload["dataset_family"], "load_forecast")
        self.assertEqual(payload["observation_kind"], "forecast")
        self.assertEqual(payload["lineage"]["source_id"], "aemo_operational_demand")
        self.assertEqual(payload["counterpart_series_id"], "series-load-actual-nsw1")


if __name__ == "__main__":
    unittest.main()
