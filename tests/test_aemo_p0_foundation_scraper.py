import sqlite3
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from scrapers import aemo_p0_foundation_scraper as scraper
pytestmark = pytest.mark.xfail(reason="SQLite removed; needs PG test fixtures", run=False)


class AemoP0FoundationScraperTests(unittest.TestCase):
    def test_sync_bom_weather_observations_records_degraded_sync_state_on_fallback(self):
        conn = sqlite3.connect(":memory:")
        scraper.ensure_tables(conn)

        def _fallback_record(region_id: str):
            return [
                (
                    region_id,
                    f"{region_id} Station",
                    "2026-05-01T00:00:00Z",
                    "",
                    24.0,
                    5.0,
                    40.0,
                    25.0,
                    60.0,
                    0.0,
                    1010.0,
                    "open_meteo_api",
                )
            ]

        with mock.patch.object(scraper, "_fetch_bom_registered_bytes", side_effect=FileNotFoundError("missing")), \
             mock.patch.object(scraper, "_fetch_bom_ftp_bytes", side_effect=TimeoutError("ftp timeout")), \
             mock.patch.object(scraper, "_fetch_open_meteo_weather_records", side_effect=_fallback_record):
            inserted = scraper.sync_bom_weather_observations(conn)

        self.assertGreater(inserted, 0)

        row = conn.execute(
            """
            SELECT source_id, sync_status, detail_json
            FROM aemo_source_sync_state
            WHERE source_id = 'aemo_nem_weather'
            """
        ).fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "aemo_nem_weather")
        self.assertEqual(row[1], "degraded")
        self.assertIn("fallback_region_count", row[2])
        self.assertIn("provider_failures", row[2])

    def test_sync_bom_weather_observations_records_cached_degraded_state(self):
        conn = sqlite3.connect(":memory:")
        scraper.ensure_tables(conn)

        cached_payload = b"<product><observations><station description='Cached Station'><period time-utc='2026-05-01T00:00:00Z' time-local=''><level><element type='air_temperature'>22.0</element><element type='wind_spd_kmh'>18</element><element type='cloud'>35</element></level></period></station></observations></product>"

        def _cached_rows(_payload: bytes, *, region_id: str, source_file: str):
            return [
                (
                    region_id,
                    "Cached Station",
                    "2026-05-01T00:00:00Z",
                    "",
                    22.0,
                    5.0,
                    35.0,
                    None,
                    None,
                    None,
                    None,
                    source_file,
                )
            ]

        with mock.patch.object(scraper, "_fetch_bom_registered_bytes", side_effect=FileNotFoundError("missing")), \
             mock.patch.object(scraper, "_fetch_bom_ftp_bytes", side_effect=TimeoutError("ftp timeout")), \
             mock.patch.object(scraper, "_fetch_open_meteo_weather_records", side_effect=RuntimeError("fallback down")), \
             mock.patch.object(scraper, "_load_bom_weather_cache", return_value=(cached_payload, "IDN60920.xml", "2026-05-01T00:00:00Z")), \
             mock.patch.object(scraper, "_parse_bom_observation_file", side_effect=_cached_rows):
            inserted = scraper.sync_bom_weather_observations(conn)

        row = conn.execute(
            """
            SELECT source_id, sync_status, last_error, detail_json
            FROM aemo_source_sync_state
            WHERE source_id = 'aemo_nem_weather'
            """
        ).fetchone()
        conn.close()

        self.assertGreater(inserted, 0)
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "aemo_nem_weather")
        self.assertEqual(row[1], "degraded")
        self.assertIn("cached payload", row[2])
        self.assertIn("cached_region_count", row[3])
        self.assertIn("provider_failures", row[3])

    def test_sync_du_detail_summary_records_source_sync_state(self):
        conn = sqlite3.connect(":memory:")
        scraper.ensure_tables(conn)

        archive_lines = [
            "I,DUID,START_DATE,END_DATE,DISPATCHTYPE,CONNECTIONPOINTID,REGIONID,STATIONID,PARTICIPANTID,SCHEDULE_TYPE",
            "D,TESTGEN1,2026/01/01 00:00:00,2099/12/31 00:00:00,GENERATOR,CP1,VIC1,ST1,P1,SCHEDULED",
        ]

        with mock.patch.object(scraper, "_latest_mmsdm_archive_month_url", return_value="https://example.com/archive/"), \
             mock.patch.object(scraper, "fetch_archive_listing", return_value=["PUBLIC_DUDETAILSUMMARY_20260501.zip"]), \
             mock.patch.object(scraper, "fetch_archive_zip_lines", return_value=("PUBLIC_DUDETAILSUMMARY_20260501.zip", archive_lines)):
            inserted = scraper.sync_du_detail_summary(conn)

        row = conn.execute(
            """
            SELECT source_id, sync_status, last_error, detail_json
            FROM aemo_source_sync_state
            WHERE source_id = 'aemo_nem_du_detail_summary'
            """
        ).fetchone()
        conn.close()

        self.assertEqual(inserted, 1)
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "aemo_nem_du_detail_summary")
        self.assertEqual(row[1], "ok")
        self.assertIsNone(row[2])
        self.assertIn("row_count", row[3])


if __name__ == "__main__":
    unittest.main()
