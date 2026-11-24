"""Turning meter readings into kilowatt-hours."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from billing_engine.errors import InvalidReadingError
from billing_engine.money import round_kwh


def meter_consumption(
    opening: Decimal,
    closing: Decimal,
    rollover_at: Decimal | None,
    meter_id: str = "",
) -> Decimal:
    """Energy used between two readings of the same meter.

    A register counts up and wraps back to zero at ``rollover_at`` (for a
    five-digit register that is 100000). So a closing reading lower than the
    opening one means the register wrapped once. Without a declared
    ``rollover_at`` a decrease is an error rather than a guess.

    Limitation: equal readings mean zero use. A complete lap in one period
    cannot be distinguished from no use at all.
    """
    if closing >= opening:
        return closing - opening
    if rollover_at is None:
        raise InvalidReadingError(
            f"closing reading {closing} is lower than opening reading {opening} "
            f"for meter {meter_id!r}, and the meter has no rollover_at",
            meter_id=meter_id,
            opening=opening,
            closing=closing,
        )
    return closing + rollover_at - opening


def allocate_kwh(total: Decimal, day_counts: Sequence[int]) -> list[Decimal]:
    """Split ``total`` kWh across consecutive spans in proportion to their days.

    Each running total is rounded once (cumulative rounding), and each span gets
    the difference between neighbouring running totals. Because the sums
    telescope, the parts always add up to ``total`` exactly (for a ``total`` with
    at most three decimal places) and no energy is created or lost to rounding.
    """
    all_days = sum(day_counts)
    parts: list[Decimal] = []
    days_so_far = 0
    previous = Decimal(0)
    for days in day_counts:
        days_so_far += days
        running = round_kwh(total * days_so_far / all_days)
        parts.append(running - previous)
        previous = running
    return parts
