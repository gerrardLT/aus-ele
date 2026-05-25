"""Unit tests for capacity data models and loader.

Tests cover:
- Pydantic model validation (CapacityProject, CapacityDataMetadata, CapacityDataSource)
- CapacityDataLoader with fallback mechanism
- get_region_summary() calculations
- Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

import json
import tempfile
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

import pytest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from models.capacity_models import (
    CapacityProject,
    CapacityDataMetadata,
    CapacityDataSource,
    CapacityDataLoader,
    CapacityDataLoadError,
)
from pydantic import ValidationError


# --- CapacityProject Tests ---


class TestCapacityProject:
    def test_valid_project(self):
        project = CapacityProject(
            region="SA1",
            project_name="Test Battery",
            capacity_mw=100,
            duration_hours=4,
            status="registered",
        )
        assert project.region == "SA1"
        assert project.capacity_mw == 100
        assert project.duration_hours == 4

    def test_energy_mwh_auto_calculated(self):
        project = CapacityProject(
            region="NSW1",
            project_name="Auto Calc",
            capacity_mw=200,
            duration_hours=2,
            status="planning",
        )
        assert project.energy_mwh == 400.0

    def test_energy_mwh_explicit(self):
        project = CapacityProject(
            region="VIC1",
            project_name="Explicit Energy",
            capacity_mw=300,
            duration_hours=2,
            energy_mwh=580,
            status="registered",
        )
        assert project.energy_mwh == 580

    def test_invalid_capacity_mw_zero(self):
        with pytest.raises(ValidationError):
            CapacityProject(
                region="SA1",
                project_name="Bad",
                capacity_mw=0,
                duration_hours=4,
                status="registered",
            )

    def test_invalid_capacity_mw_negative(self):
        with pytest.raises(ValidationError):
            CapacityProject(
                region="SA1",
                project_name="Bad",
                capacity_mw=-10,
                duration_hours=4,
                status="registered",
            )

    def test_invalid_duration_hours(self):
        with pytest.raises(ValidationError):
            CapacityProject(
                region="SA1",
                project_name="Bad",
                capacity_mw=100,
                duration_hours=0,
                status="registered",
            )

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            CapacityProject(
                region="SA1",
                project_name="Bad",
                capacity_mw=100,
                duration_hours=4,
                status="unknown",
            )

    def test_valid_statuses(self):
        for status in ["registered", "construction", "planning", "committed"]:
            project = CapacityProject(
                region="SA1",
                project_name=f"Status {status}",
                capacity_mw=100,
                duration_hours=4,
                status=status,
            )
            assert project.status == status

    def test_optional_fields_none(self):
        project = CapacityProject(
            region="WEM",
            project_name="Minimal",
            capacity_mw=50,
            duration_hours=2,
            status="planning",
        )
        assert project.expected_commissioning_date is None
        assert project.actual_commissioning_date is None
        assert project.owner is None
        assert project.technology is None

    def test_date_parsing(self):
        project = CapacityProject(
            region="SA1",
            project_name="Dated",
            capacity_mw=100,
            duration_hours=4,
            status="registered",
            expected_commissioning_date="2025-06-01",
            actual_commissioning_date="2025-05-15",
        )
        assert project.expected_commissioning_date == date(2025, 6, 1)
        assert project.actual_commissioning_date == date(2025, 5, 15)


# --- CapacityDataMetadata Tests ---


class TestCapacityDataMetadata:
    def test_valid_metadata(self):
        meta = CapacityDataMetadata(
            last_updated="2025-06-15T10:30:00+10:00",
            source="AEMO Report",
            version=3,
        )
        assert meta.version == 3
        assert meta.source == "AEMO Report"

    def test_invalid_version_zero(self):
        with pytest.raises(ValidationError):
            CapacityDataMetadata(
                last_updated="2025-06-15T10:30:00+10:00",
                source="Test",
                version=0,
            )


# --- CapacityDataSource Tests ---


class TestCapacityDataSource:
    def _make_source(self, projects=None):
        if projects is None:
            projects = [
                CapacityProject(
                    region="SA1",
                    project_name="Registered A",
                    capacity_mw=100,
                    duration_hours=2,
                    status="registered",
                ),
                CapacityProject(
                    region="SA1",
                    project_name="Pipeline B",
                    capacity_mw=200,
                    duration_hours=4,
                    status="construction",
                ),
                CapacityProject(
                    region="NSW1",
                    project_name="NSW Project",
                    capacity_mw=300,
                    duration_hours=2,
                    status="registered",
                ),
            ]
        return CapacityDataSource(
            metadata=CapacityDataMetadata(
                last_updated="2025-06-15T10:30:00+10:00",
                source="Test",
                version=1,
            ),
            projects=projects,
        )

    def test_get_region_summary_basic(self):
        source = self._make_source()
        summary = source.get_region_summary("SA1")
        assert summary["region"] == "SA1"
        assert summary["registered_mw"] == 100
        assert summary["pipeline_mw"] == 200
        assert summary["total_mw"] == 300
        assert summary["project_count"] == 2

    def test_get_region_summary_no_projects(self):
        source = self._make_source()
        summary = source.get_region_summary("TAS1")
        assert summary["registered_mw"] == 0
        assert summary["pipeline_mw"] == 0
        assert summary["total_mw"] == 0
        assert summary["project_count"] == 0

    def test_get_region_summary_all_registered(self):
        source = self._make_source()
        summary = source.get_region_summary("NSW1")
        assert summary["registered_mw"] == 300
        assert summary["pipeline_mw"] == 0


# --- CapacityDataLoader Tests ---


class TestCapacityDataLoader:
    def _write_json(self, path: Path, data: dict):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _valid_data(self):
        return {
            "metadata": {
                "last_updated": "2025-06-15T10:30:00+10:00",
                "source": "Test Source",
                "version": 1,
            },
            "projects": [
                {
                    "region": "SA1",
                    "project_name": "Test",
                    "capacity_mw": 100,
                    "duration_hours": 4,
                    "status": "registered",
                }
            ],
        }

    def test_load_primary_success(self, tmp_path):
        primary = tmp_path / "primary.json"
        backup = tmp_path / "backup.json"
        self._write_json(primary, self._valid_data())
        self._write_json(backup, self._valid_data())

        loader = CapacityDataLoader(data_path=primary, backup_path=backup)
        data = loader.load()
        assert len(data.projects) == 1
        assert data.projects[0].project_name == "Test"

    def test_fallback_to_backup(self, tmp_path):
        primary = tmp_path / "primary.json"
        backup = tmp_path / "backup.json"
        # Write invalid JSON to primary
        primary.write_text("not valid json", encoding="utf-8")
        self._write_json(backup, self._valid_data())

        loader = CapacityDataLoader(data_path=primary, backup_path=backup)
        data = loader.load()
        assert len(data.projects) == 1

    def test_fallback_primary_missing(self, tmp_path):
        primary = tmp_path / "nonexistent.json"
        backup = tmp_path / "backup.json"
        self._write_json(backup, self._valid_data())

        loader = CapacityDataLoader(data_path=primary, backup_path=backup)
        data = loader.load()
        assert len(data.projects) == 1

    def test_fallback_primary_invalid_schema(self, tmp_path):
        primary = tmp_path / "primary.json"
        backup = tmp_path / "backup.json"
        # Valid JSON but invalid schema (missing metadata)
        self._write_json(primary, {"projects": []})
        self._write_json(backup, self._valid_data())

        loader = CapacityDataLoader(data_path=primary, backup_path=backup)
        data = loader.load()
        assert len(data.projects) == 1

    def test_both_fail_raises_error(self, tmp_path):
        primary = tmp_path / "nonexistent1.json"
        backup = tmp_path / "nonexistent2.json"

        loader = CapacityDataLoader(data_path=primary, backup_path=backup)
        with pytest.raises(CapacityDataLoadError) as exc_info:
            loader.load()
        assert "primary" in str(exc_info.value).lower()
        assert "backup" in str(exc_info.value).lower()

    def test_caching(self, tmp_path):
        primary = tmp_path / "primary.json"
        backup = tmp_path / "backup.json"
        self._write_json(primary, self._valid_data())
        self._write_json(backup, self._valid_data())

        loader = CapacityDataLoader(data_path=primary, backup_path=backup)
        data1 = loader.load()
        # Modify file after first load
        primary.unlink()
        data2 = loader.load()
        # Should return cached data
        assert data1 is data2

    def test_force_reload(self, tmp_path):
        primary = tmp_path / "primary.json"
        backup = tmp_path / "backup.json"
        self._write_json(primary, self._valid_data())
        self._write_json(backup, self._valid_data())

        loader = CapacityDataLoader(data_path=primary, backup_path=backup)
        data1 = loader.load()

        # Update the file
        updated = self._valid_data()
        updated["projects"][0]["project_name"] = "Updated"
        self._write_json(primary, updated)

        data2 = loader.load(force_reload=True)
        assert data2.projects[0].project_name == "Updated"

    def test_invalidate_cache(self, tmp_path):
        primary = tmp_path / "primary.json"
        backup = tmp_path / "backup.json"
        self._write_json(primary, self._valid_data())
        self._write_json(backup, self._valid_data())

        loader = CapacityDataLoader(data_path=primary, backup_path=backup)
        loader.load()
        loader.invalidate_cache()
        assert loader._cached_data is None

    def test_get_region_summary_convenience(self, tmp_path):
        primary = tmp_path / "primary.json"
        backup = tmp_path / "backup.json"
        self._write_json(primary, self._valid_data())
        self._write_json(backup, self._valid_data())

        loader = CapacityDataLoader(data_path=primary, backup_path=backup)
        summary = loader.get_region_summary("SA1")
        assert summary["registered_mw"] == 100
        assert summary["project_count"] == 1

    def test_load_real_data_file(self):
        """Integration test: load the actual capacity_data.json file."""
        loader = CapacityDataLoader()
        data = loader.load()
        assert len(data.projects) > 0
        assert data.metadata.version >= 1
        assert data.metadata.source != ""
