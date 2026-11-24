"""Rounding policy and number formatting.

All money and energy arithmetic uses ``decimal.Decimal``. Binary floats cannot
represent values such as 0.1 exactly, which is unacceptable for billing.

Rounding policy, applied in exactly these places and nowhere else:
  * every money line item is rounded to whole cents, exact halves away from zero
  * kWh quantities are rounded to 0.001 kWh (one watt-hour)
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
KWH_STEP = Decimal("0.001")


def round_money(value: Decimal) -> Decimal:
    """Round to whole cents. An exact half rounds away from zero (2.325 -> 2.33)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def round_kwh(value: Decimal) -> Decimal:
    """Round to 0.001 kWh."""
    return value.quantize(KWH_STEP, rounding=ROUND_HALF_UP)


def has_at_most_places(value: Decimal, step: Decimal) -> bool:
    """True when ``value`` is an exact multiple of ``step`` (for example 0.001)."""
    try:
        return value == value.quantize(step)
    except InvalidOperation:
        return False


def to_text(value: Decimal) -> str:
    """Plain decimal text, never scientific notation (Decimal('1E+1') -> '10')."""
    return format(value, "f")
