"""Degradation model for battery capacity over time.

Supports two modes:
- "user-linear": Simple linear degradation using a user-provided annual rate.
- "dual-factor-default": Calendar + cyclic degradation aligned with existing server.py logic.
"""

from __future__ import annotations

from pydantic import BaseModel


class DegradationModel(BaseModel):
    """Battery degradation model used in investment analysis."""

    model_type: str  # "user-linear" | "dual-factor-default"
    annual_rate: float | None = None  # Present when user provides a rate
    parameters: dict = {}  # Model-specific parameters

    @classmethod
    def from_user_input(cls, degradation_rate: float | None) -> "DegradationModel":
        """Factory method to create a DegradationModel from user input.

        Args:
            degradation_rate: User-provided annual degradation rate (0-0.15),
                or None to use the dual-factor default model.

        Returns:
            A DegradationModel instance configured for the appropriate mode.

        Raises:
            ValueError: If degradation_rate is outside the valid range [0, 0.15].
        """
        if degradation_rate is not None:
            if not (0.0 <= degradation_rate <= 0.15):
                raise ValueError(
                    f"degradation_rate must be between 0 and 0.15, got {degradation_rate}"
                )
            return cls(model_type="user-linear", annual_rate=degradation_rate)
        return cls(
            model_type="dual-factor-default",
            parameters={"calendar": 0.015, "cyclic_per_cycle": 0.0000333},
        )

    def capacity_at_year(self, year: int, cycles_per_year: float) -> float:
        """Return the remaining capacity fraction (0-1) at the given year.

        Args:
            year: The year number (0 = start of life).
            cycles_per_year: Number of full equivalent cycles per year.

        Returns:
            Remaining capacity as a fraction between 0.0 and 1.0.
        """
        if self.model_type == "user-linear":
            return max(0.0, 1.0 - self.annual_rate * year)
        # dual-factor: calendar + cyclic degradation (aligned with existing server.py logic)
        calendar_loss = self.parameters["calendar"] * year
        cyclic_loss = self.parameters["cyclic_per_cycle"] * cycles_per_year * year
        return max(0.0, 1.0 - calendar_loss - cyclic_loss)
