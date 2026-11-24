"""Exception types.

Every error this package raises on purpose derives from BillingError and carries
a stable, machine-readable ``code`` so callers (and the CLI) can react to the kind
of failure without parsing message text.
"""

from __future__ import annotations


class BillingError(Exception):
    """Base class for every error raised deliberately by this package."""

    code = "billing_error"

    def __init__(self, message: str, **details: object) -> None:
        super().__init__(message)
        self.message = message
        # Details are stored as text so the error can always be serialised to JSON.
        self.details: dict[str, str] = {key: str(value) for key, value in details.items()}

    def to_dict(self) -> dict[str, object]:
        """Structured form used for the CLI's error output."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": dict(self.details),
            }
        }


class InputFileError(BillingError):
    """The input file could not be read."""

    code = "input_file_error"


class OutputFileError(BillingError):
    """The result could not be written."""

    code = "output_file_error"


class InvalidJsonError(BillingError):
    """The input is not valid JSON."""

    code = "invalid_json"


class InputValidationError(BillingError):
    """The input is not shaped correctly: wrong type, missing field, unknown field."""

    code = "invalid_input"


class BillingPeriodError(BillingError):
    """The billing period is empty, reversed or unreasonably long."""

    code = "invalid_period"


class InvalidReadingError(BillingError):
    """A meter reading is missing, unexpected or physically impossible."""

    code = "invalid_reading"


class InvalidEventError(BillingError):
    """A mid-cycle event (such as a meter replacement) is inconsistent."""

    code = "invalid_event"


class TariffError(BillingError):
    """A tariff is malformed, or no tariff covers part of the billing period."""

    code = "tariff_error"
