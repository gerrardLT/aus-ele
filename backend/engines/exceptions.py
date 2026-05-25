"""Custom exceptions for analysis engines."""


class DimensionMismatchError(Exception):
    """Raised when input data has incompatible dimensional units.

    For example, passing price statistics ($/MWh) into a revenue calculation
    that expects raw price series.
    """

    def __init__(
        self,
        *,
        expected_unit: str,
        received_unit: str,
        message: str | None = None,
    ):
        self.expected_unit = expected_unit
        self.received_unit = received_unit
        self.message = message or (
            f"维度不匹配：期望 {expected_unit}，收到 {received_unit}"
        )
        super().__init__(self.message)
