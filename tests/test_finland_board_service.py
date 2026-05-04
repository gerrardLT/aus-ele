import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from finland_board_contracts import FINLAND_BOARD_OVERVIEW_CARDS
from finland_board_service import (
    build_finland_board_chart_payload,
    build_finland_board_field_catalog_rows,
    build_finland_board_overview_payload,
    build_finland_board_readiness_payload,
    build_finland_board_table_payload,
)


def _point(timestamp_utc, timestamp_local, value):
    return {
        "timestamp_utc": timestamp_utc,
        "timestamp_local": timestamp_local,
        "value": value,
    }


class StubDatabase:
    def __init__(self):
        self.calls = []
        self.series_by_field = {
            "fcr_n_price_eur_mw": [
                _point("2026-04-01T00:00:00Z", "2026-04-01T03:00:00+03:00", 10.0),
                _point("2026-04-01T01:00:00Z", "2026-04-01T04:00:00+03:00", 14.0),
                _point("2026-04-02T00:00:00Z", "2026-04-02T03:00:00+03:00", 18.0),
            ],
            "afrr_act_up_eur_mwh": [
                _point("2026-04-01T00:00:00Z", "2026-04-01T03:00:00+03:00", 82.0),
                _point("2026-04-01T01:00:00Z", "2026-04-01T04:00:00+03:00", 86.0),
                _point("2026-04-02T00:00:00Z", "2026-04-02T03:00:00+03:00", 90.0),
            ],
            "mfrr_act_up_eur_mwh": [
                _point("2026-04-01T00:00:00Z", "2026-04-01T03:00:00+03:00", 94.0),
                _point("2026-04-01T01:00:00Z", "2026-04-01T04:00:00+03:00", 98.0),
            ],
            "imbalance_price_eur_mwh": [
                _point("2026-04-01T00:00:00Z", "2026-04-01T03:00:00+03:00", 105.0),
                _point("2026-04-01T01:00:00Z", "2026-04-01T04:00:00+03:00", 112.0),
                _point("2026-04-02T00:00:00Z", "2026-04-02T03:00:00+03:00", 95.0),
            ],
            "spot_price_fi_eur_mwh": [
                _point("2026-04-01T00:00:00Z", "2026-04-01T03:00:00+03:00", 75.0),
                _point("2026-04-01T01:00:00Z", "2026-04-01T04:00:00+03:00", 80.0),
                _point("2026-04-02T00:00:00Z", "2026-04-02T03:00:00+03:00", 70.0),
            ],
            "fcr_d_up_price_eur_mw": [
                _point("2026-04-01T00:00:00Z", "2026-04-01T03:00:00+03:00", 11.0),
            ],
            "fcr_d_down_price_eur_mw": [
                _point("2026-04-01T00:00:00Z", "2026-04-01T03:00:00+03:00", 8.0),
            ],
            "afrr_cap_up_eur_mw": [
                _point("2026-04-01T00:00:00Z", "2026-04-01T03:00:00+03:00", 13.0),
            ],
            "afrr_cap_down_eur_mw": [
                _point("2026-04-01T00:00:00Z", "2026-04-01T03:00:00+03:00", 9.0),
            ],
            "mfrr_cap_up_eur_mw": [
                _point("2026-04-01T00:00:00Z", "2026-04-01T03:00:00+03:00", 12.0),
            ],
            "mfrr_cap_down_eur_mw": [
                _point("2026-04-01T00:00:00Z", "2026-04-01T03:00:00+03:00", 7.0),
            ],
        }

    def fetch_finland_board_series(self, field_key, start=None, end=None, granularity=None):
        self.calls.append(
            {
                "field_key": field_key,
                "start": start,
                "end": end,
                "granularity": granularity,
            }
        )
        return list(self.series_by_field.get(field_key, []))


class FinlandBoardServiceTests(unittest.TestCase):
    def test_overview_card_contract_is_stable_and_registry_backed(self):
        self.assertEqual(
            [card["field_key"] for card in FINLAND_BOARD_OVERVIEW_CARDS],
            [
                "fcr_n_price_eur_mw",
                "afrr_act_up_eur_mwh",
                "mfrr_act_up_eur_mwh",
                "imbalance_price_eur_mwh",
                "spot_price_fi_eur_mwh",
                "join_completeness",
            ],
        )

    def test_overview_returns_six_cards(self):
        db = StubDatabase()
        payload = build_finland_board_overview_payload(
            db,
            start="2026-04-01T00:00:00Z",
            end="2026-04-02T00:00:00Z",
        )

        self.assertEqual(len(payload["cards"]), 6)
        self.assertEqual(
            [card["field_key"] for card in payload["cards"]],
            [card["field_key"] for card in FINLAND_BOARD_OVERVIEW_CARDS],
        )
        join_card = payload["cards"][-1]
        self.assertEqual(join_card["value"], 100.0)
        self.assertEqual(join_card["latest_coverage_utc"], "2026-04-02T00:00:00Z")

    def test_capacity_table_exposes_spot_join_column(self):
        payload = build_finland_board_table_payload(
            StubDatabase(),
            view="capacity_hourly",
            start="2026-04-01T00:00:00Z",
            end="2026-04-02T00:00:00Z",
            tz="Europe/Helsinki",
        )

        spot_column = next(column for column in payload["columns"] if column["field_key"] == "spot_price_fi_eur_mwh")
        self.assertEqual(spot_column["source_type"], "external_join")
        self.assertEqual(payload["rows"][0]["spot_price_fi_eur_mwh"], 75.0)

    def test_activation_view_fetches_spot_with_field_granularity(self):
        db = StubDatabase()

        payload = build_finland_board_table_payload(
            db,
            view="activation_15m",
            start="2026-04-01T00:00:00Z",
            end="2026-04-02T00:00:00Z",
            tz="Europe/Helsinki",
        )

        self.assertEqual(payload["rows"][0]["spot_price_fi_eur_mwh"], 75.0)
        spot_call = next(call for call in db.calls if call["field_key"] == "spot_price_fi_eur_mwh")
        activation_call = next(call for call in db.calls if call["field_key"] == "afrr_act_up_eur_mwh")
        self.assertEqual(spot_call["granularity"], "1h")
        self.assertEqual(activation_call["granularity"], "15m")

    def test_spread_chart_returns_difference_series_key(self):
        payload = build_finland_board_chart_payload(
            StubDatabase(),
            fields=["imbalance_price_eur_mwh", "spot_price_fi_eur_mwh"],
            mode="spread",
            start="2026-04-01T00:00:00Z",
            end="2026-04-02T00:00:00Z",
            granularity="1h",
        )

        self.assertEqual(payload["mode"], "spread")
        self.assertEqual(
            payload["series"][0]["field_key"],
            "imbalance_price_eur_mwh-minus-spot_price_fi_eur_mwh",
        )
        self.assertEqual(payload["series"][0]["points"][0]["value"], 30.0)

    def test_spread_mode_requires_exactly_two_fields(self):
        with self.assertRaises(ValueError):
            build_finland_board_chart_payload(
                StubDatabase(),
                fields=["imbalance_price_eur_mwh"],
                mode="spread",
                start="2026-04-01T00:00:00Z",
                end="2026-04-02T00:00:00Z",
                granularity="1h",
            )

    def test_chart_granularity_alias_is_normalized(self):
        payload = build_finland_board_chart_payload(
            StubDatabase(),
            fields=["spot_price_fi_eur_mwh"],
            mode="single",
            start="2026-04-01T00:00:00Z",
            end="2026-04-02T00:00:00Z",
            granularity="hour",
        )

        self.assertEqual(payload["granularity"], "1h")

    def test_field_catalog_rows_are_registry_backed(self):
        rows = build_finland_board_field_catalog_rows()

        spot_row = next(row for row in rows if row["field_key"] == "spot_price_fi_eur_mwh")
        self.assertEqual(spot_row["source_type"], "external_join")
        self.assertEqual(spot_row["source_name"], "Nord Pool")

    def test_readiness_payload_reuses_market_model_sources(self):
        payload = build_finland_board_readiness_payload(
            StubDatabase(),
            {
                "summary": {
                    "live_source_count": 2,
                    "configured_external_source_count": 1,
                },
                "sources": [
                    {"source_key": "fingrid", "status": "live"},
                    {
                        "source_key": "nord_pool",
                        "status": "configured",
                        "integration": {"readiness": "configured"},
                    },
                ],
                "metadata": {"warnings": ["planned_external_sources"]},
            },
        )

        self.assertEqual(payload["summary"]["live_source_count"], 2)
        self.assertEqual(payload["sources"][1]["integration"]["readiness"], "configured")
        self.assertIn("planned_external_sources", payload["warnings"])

    def test_daily_capacity_view_returns_daily_aggregated_rows(self):
        payload = build_finland_board_table_payload(
            StubDatabase(),
            view="daily_capacity",
            start="2026-04-01T00:00:00Z",
            end="2026-04-03T00:00:00Z",
            tz="Europe/Helsinki",
        )

        self.assertEqual(payload["granularity"], "day")
        self.assertEqual([row["date"] for row in payload["rows"]], ["2026-04-01", "2026-04-02"])
        self.assertNotIn("timestamp_helsinki", payload["rows"][0])
        self.assertEqual(payload["rows"][0]["fcr_n_price_eur_mw"], 12.0)
        self.assertEqual(payload["rows"][0]["spot_price_fi_eur_mwh"], 77.5)
        self.assertEqual(payload["rows"][1]["fcr_n_price_eur_mw"], 18.0)

    def test_daily_activation_view_returns_daily_aggregated_rows(self):
        payload = build_finland_board_table_payload(
            StubDatabase(),
            view="daily_activation",
            start="2026-04-01T00:00:00Z",
            end="2026-04-03T00:00:00Z",
            tz="Europe/Helsinki",
        )

        self.assertEqual(payload["granularity"], "day")
        self.assertEqual([row["date"] for row in payload["rows"]], ["2026-04-01", "2026-04-02"])
        self.assertEqual(payload["rows"][0]["afrr_act_up_eur_mwh"], 84.0)
        self.assertEqual(payload["rows"][0]["imbalance_price_eur_mwh"], 108.5)
        self.assertEqual(payload["rows"][1]["spot_price_fi_eur_mwh"], 70.0)

    def test_invalid_view_raises_key_error(self):
        with self.assertRaises(KeyError):
            build_finland_board_table_payload(
                StubDatabase(),
                view="unknown_view",
                start="2026-04-01T00:00:00Z",
                end="2026-04-02T00:00:00Z",
                tz="Europe/Helsinki",
            )

    def test_invalid_chart_mode_raises_value_error(self):
        with self.assertRaises(ValueError):
            build_finland_board_chart_payload(
                StubDatabase(),
                fields=["imbalance_price_eur_mwh"],
                mode="invalid",
                start="2026-04-01T00:00:00Z",
                end="2026-04-02T00:00:00Z",
                granularity="1h",
            )

    def test_non_tabular_views_raise_clear_error_in_table_builder(self):
        for view_key in ("summary_stats", "field_dictionary"):
            with self.assertRaises(ValueError):
                build_finland_board_table_payload(
                    StubDatabase(),
                    view=view_key,
                    start="2026-04-01T00:00:00Z",
                    end="2026-04-02T00:00:00Z",
                    tz="Europe/Helsinki",
                )


if __name__ == "__main__":
    unittest.main()
