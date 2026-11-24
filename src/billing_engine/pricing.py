"""Pricing one segment.

Tier allowances (``up_to_kwh``) in a tariff are per full billing period. A
segment covers only part of the period, so its allowances are scaled by
``segment days / period days`` and rounded to 0.001 kWh. Rounding the
*boundaries* (not the quantities) keeps every tier quantity a clean multiple of
0.001 kWh and makes the tiers add up to the segment's energy exactly.
"""

from __future__ import annotations

from decimal import Decimal

from billing_engine.models import LineItem, Segment
from billing_engine.money import round_kwh, round_money


def price_segment(segment: Segment, period_days: int) -> list[LineItem]:
    """Energy lines (one per tier used) followed by the fixed charge line."""
    lines = _energy_lines(segment, period_days)
    fixed = _fixed_line(segment)
    if fixed is not None:
        lines.append(fixed)
    return lines


def _energy_lines(segment: Segment, period_days: int) -> list[LineItem]:
    lines: list[LineItem] = []
    priced_up_to = Decimal(0)

    for number, tier in enumerate(segment.tariff.tiers, start=1):
        if tier.up_to_kwh is None:
            ceiling = segment.kwh
        else:
            scaled_limit = round_kwh(tier.up_to_kwh * segment.days / period_days)
            ceiling = min(segment.kwh, scaled_limit)

        quantity = ceiling - priced_up_to
        if quantity <= 0:
            continue
        lines.append(
            LineItem(
                kind="energy",
                description=f"Energy tier {number} (meter {segment.meter_id}, tariff {segment.tariff.id})",
                amount=round_money(quantity * tier.rate),
                segment_start=segment.start,
                segment_end=segment.end,
                quantity=quantity,
                unit="kWh",
                rate=tier.rate,
            )
        )
        priced_up_to = ceiling
    return lines


def _fixed_line(segment: Segment) -> LineItem | None:
    charge = segment.tariff.daily_fixed_charge
    if charge == 0:
        return None
    return LineItem(
        kind="fixed",
        description=f"Fixed daily charge (tariff {segment.tariff.id})",
        amount=round_money(charge * segment.days),
        segment_start=segment.start,
        segment_end=segment.end,
        quantity=Decimal(segment.days),
        unit="day",
        rate=charge,
    )
