"""Plain data types shared by the rest of the package.

Everything is a frozen dataclass: once built, nothing changes, so every step of
the calculation can be reasoned about (and tested) in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from billing_engine.money import to_text

# ---------------------------------------------------------------- input side


@dataclass(frozen=True)
class Tier:
    """One band of a tiered energy price. ``up_to_kwh`` is None for the last band."""

    up_to_kwh: Decimal | None
    rate: Decimal


@dataclass(frozen=True)
class Tariff:
    id: str
    effective_from: date
    tiers: tuple[Tier, ...]
    daily_fixed_charge: Decimal


@dataclass(frozen=True)
class Meter:
    id: str
    rollover_at: Decimal | None


@dataclass(frozen=True)
class Reading:
    meter_id: str
    date: date
    value: Decimal


@dataclass(frozen=True)
class MeterReplacement:
    """Old meter removed and new meter installed at the start of ``date``."""

    date: date
    old_meter_id: str
    old_final_reading: Decimal
    new_meter_id: str
    new_initial_reading: Decimal


@dataclass(frozen=True)
class Adjustment:
    description: str
    amount: Decimal
    taxable: bool


@dataclass(frozen=True)
class BillingInput:
    customer_id: str
    currency: str
    period_start: date
    period_end: date  # exclusive: the first day of the next period
    tax_rate: Decimal
    tariffs: tuple[Tariff, ...]
    meters: tuple[Meter, ...]
    readings: tuple[Reading, ...]
    replacements: tuple[MeterReplacement, ...]
    adjustments: tuple[Adjustment, ...]


# --------------------------------------------------------------- output side


@dataclass(frozen=True)
class Segment:
    """A run of days with one meter in service and one tariff in force."""

    start: date
    end: date  # exclusive
    meter_id: str
    tariff: Tariff
    kwh: Decimal

    @property
    def days(self) -> int:
        return (self.end - self.start).days

    def to_dict(self) -> dict[str, object]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "days": self.days,
            "meter_id": self.meter_id,
            "tariff_id": self.tariff.id,
            "kwh": to_text(self.kwh),
        }


@dataclass(frozen=True)
class LineItem:
    """One row of the invoice. Together the rows are the audit trail."""

    kind: str  # "energy", "fixed", "adjustment" or "tax"
    description: str
    amount: Decimal
    segment_start: date | None = None
    segment_end: date | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    rate: Decimal | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "description": self.description,
            "segment_start": None if self.segment_start is None else self.segment_start.isoformat(),
            "segment_end": None if self.segment_end is None else self.segment_end.isoformat(),
            "quantity": None if self.quantity is None else to_text(self.quantity),
            "unit": self.unit,
            "rate": None if self.rate is None else to_text(self.rate),
            "amount": to_text(self.amount),
        }


@dataclass(frozen=True)
class Summary:
    energy: Decimal
    fixed: Decimal
    adjustments: Decimal
    taxable_base: Decimal
    tax_rate: Decimal
    tax: Decimal
    total: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "energy": to_text(self.energy),
            "fixed": to_text(self.fixed),
            "adjustments": to_text(self.adjustments),
            "taxable_base": to_text(self.taxable_base),
            "tax_rate": to_text(self.tax_rate),
            "tax": to_text(self.tax),
            "total": to_text(self.total),
        }


@dataclass(frozen=True)
class Invoice:
    customer_id: str
    currency: str
    period_start: date
    period_end: date
    segments: tuple[Segment, ...]
    lines: tuple[LineItem, ...]
    summary: Summary

    @property
    def total_kwh(self) -> Decimal:
        return sum((segment.kwh for segment in self.segments), Decimal(0))

    def to_dict(self) -> dict[str, object]:
        return {
            "customer_id": self.customer_id,
            "currency": self.currency,
            "billing_period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
                "days": (self.period_end - self.period_start).days,
            },
            "consumption": {
                "total_kwh": to_text(self.total_kwh),
                "segments": [segment.to_dict() for segment in self.segments],
            },
            "lines": [line.to_dict() for line in self.lines],
            "summary": self.summary.to_dict(),
        }
