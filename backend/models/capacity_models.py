"""Capacity data models and loader for BESS saturation tracking.

Provides Pydantic models for validating capacity data from the JSON data source,
and a loader class with validation and fallback mechanisms.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Literal

from pydantic import BaseModel, Field
from datetime import date, datetime

logger = logging.getLogger(__name__)

# Default data file paths (relative to project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DATA_PATH = _PROJECT_ROOT / "data" / "capacity_data.json"
DEFAULT_BACKUP_PATH = _PROJECT_ROOT / "data" / "capacity_data_backup.json"


class CapacityProject(BaseModel):
    """A single BESS project entry in the capacity data source.

    Fields align with AEMO Generation Information Report structure.
    """

    region: str = Field(..., description="NEM region (NSW1, QLD1, VIC1, SA1, TAS1) or 'WEM'")
    project_name: str
    capacity_mw: float = Field(gt=0)
    duration_hours: float = Field(gt=0)
    energy_mwh: Optional[float] = None
    status: Literal["registered", "construction", "planning", "committed"]
    expected_commissioning_date: Optional[date] = None
    actual_commissioning_date: Optional[date] = None
    owner: Optional[str] = None
    technology: Optional[str] = None

    def model_post_init(self, __context) -> None:
        if self.energy_mwh is None:
            self.energy_mwh = self.capacity_mw * self.duration_hours


class CapacityDataMetadata(BaseModel):
    """Metadata about the capacity data source."""

    last_updated: datetime
    source: str
    version: int = Field(ge=1)


class CapacityDataSource(BaseModel):
    """Top-level capacity data model containing metadata and project list."""

    metadata: CapacityDataMetadata
    projects: list[CapacityProject]

    def get_region_summary(self, region: str) -> dict:
        """Calculate capacity summary for a specific region.

        Args:
            region: NEM region code (e.g. 'SA1') or 'WEM'.

        Returns:
            Dictionary with region capacity breakdown:
            - region: the queried region
            - registered_mw: total MW of registered projects
            - pipeline_mw: total MW of non-registered projects (construction/planning/committed)
            - total_mw: registered + pipeline
            - project_count: number of projects in the region
        """
        region_projects = [p for p in self.projects if p.region == region]
        registered = sum(
            p.capacity_mw for p in region_projects if p.status == "registered"
        )
        pipeline = sum(
            p.capacity_mw for p in region_projects if p.status != "registered"
        )
        return {
            "region": region,
            "registered_mw": registered,
            "pipeline_mw": pipeline,
            "total_mw": registered + pipeline,
            "project_count": len(region_projects),
        }


class CapacityDataLoader:
    """Loads and validates capacity data with fallback mechanism.

    Attempts to load from the primary data file. If validation fails,
    falls back to the backup file. If both fail, raises an error.

    Requirements:
        4.2 - Data validation on load
        4.3 - Fallback to previous valid version on error
    """

    def __init__(
        self,
        data_path: Optional[Path] = None,
        backup_path: Optional[Path] = None,
    ):
        self.data_path = data_path or DEFAULT_DATA_PATH
        self.backup_path = backup_path or DEFAULT_BACKUP_PATH
        self._cached_data: Optional[CapacityDataSource] = None

    def load(self, force_reload: bool = False) -> CapacityDataSource:
        """Load and validate capacity data.

        Tries primary file first, falls back to backup on failure.

        Args:
            force_reload: If True, bypass cache and reload from disk.

        Returns:
            Validated CapacityDataSource instance.

        Raises:
            CapacityDataLoadError: If both primary and backup files fail validation.
        """
        if self._cached_data is not None and not force_reload:
            return self._cached_data

        primary_err: Optional[Exception] = None

        # Try primary file
        try:
            data = self._load_and_validate(self.data_path)
            self._cached_data = data
            return data
        except Exception as exc:
            primary_err = exc
            logger.warning(
                "Failed to load primary capacity data from %s: %s. "
                "Falling back to backup.",
                self.data_path,
                exc,
            )

        # Try backup file
        try:
            data = self._load_and_validate(self.backup_path)
            self._cached_data = data
            logger.info(
                "Successfully loaded capacity data from backup: %s",
                self.backup_path,
            )
            return data
        except Exception as backup_err:
            logger.error(
                "Failed to load backup capacity data from %s: %s",
                self.backup_path,
                backup_err,
            )
            raise CapacityDataLoadError(
                f"Failed to load capacity data from both primary ({self.data_path}) "
                f"and backup ({self.backup_path}). "
                f"Primary error: {primary_err}. Backup error: {backup_err}."
            ) from backup_err

    def _load_and_validate(self, path: Path) -> CapacityDataSource:
        """Load JSON file and validate with Pydantic.

        Args:
            path: Path to the JSON data file.

        Returns:
            Validated CapacityDataSource.

        Raises:
            FileNotFoundError: If the file does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
            pydantic.ValidationError: If the data fails schema validation.
        """
        if not path.exists():
            raise FileNotFoundError(f"Capacity data file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        return CapacityDataSource.model_validate(raw_data)

    def get_region_summary(self, region: str) -> dict:
        """Convenience method to get region summary from loaded data.

        Args:
            region: NEM region code or 'WEM'.

        Returns:
            Region capacity summary dictionary.
        """
        data = self.load()
        return data.get_region_summary(region)

    def invalidate_cache(self) -> None:
        """Clear the cached data, forcing a reload on next access."""
        self._cached_data = None


class CapacityDataLoadError(Exception):
    """Raised when capacity data cannot be loaded from any source."""

    pass
