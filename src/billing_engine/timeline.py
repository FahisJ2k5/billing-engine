"""Splitting the billing period into segments.

A *segment* is a run of days during which exactly one meter is in service and
exactly one tariff is in force. The period is cut at every meter replacement
and every tariff change, so each segment can be priced independently.

Assumption (documented in the README): without interval data we cannot know
*when* energy was used, so usage within one meter's time in service is spread
evenly across its days.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from billing_engine.consumption import allocate_kwh, meter_consumption
from billing_engine.errors import InvalidReadingError
from billing_engine.models import BillingInput, Meter, Segment, Tariff
from billing_engine.money import has_at_most_places


@dataclass(frozen=True)
class MeterSpan:
    """The time one meter spent in service during the period, and what it measured."""

    meter_id: str
    start: date
    end: date  # exclusive
    kwh: Decimal


def tariff_in_force(tariffs: list[Tariff], day: date) -> Tariff:
    """The tariff with the latest ``effective_from`` on or before ``day``."""
    current = None
    for tariff in sorted(tariffs, key=lambda t: t.effective_from):
        if tariff.effective_from <= day:
            current = tariff
    assert current is not None  # validate() guarantees a tariff covers the first day
    return current


def meter_spans(data: BillingInput) -> list[MeterSpan]:
    """One span per meter that was in service, with its consumption."""
    meters = {meter.id: meter for meter in data.meters}
    replacements = sorted(data.replacements, key=lambda r: r.date)

    current_id = replacements[0].old_meter_id if replacements else _meter_with_opening_reading(data)
    current_opening = _reading_at(data, current_id, data.period_start, "opening")
    _check_register(meters[current_id], current_opening, "opening reading")
    span_start = data.period_start

    spans: list[MeterSpan] = []
    for event in replacements:
        _check_register(meters[event.old_meter_id], event.old_final_reading, "final reading")
        _check_register(meters[event.new_meter_id], event.new_initial_reading, "initial reading")
        spans.append(
            MeterSpan(
                current_id,
                span_start,
                event.date,
                meter_consumption(
                    current_opening,
                    event.old_final_reading,
                    meters[current_id].rollover_at,
                    current_id,
                ),
            )
        )
        current_id = event.new_meter_id
        current_opening = event.new_initial_reading
        span_start = event.date

    closing = _reading_at(data, current_id, data.period_end, "closing")
    _check_register(meters[current_id], closing, "closing reading")
    spans.append(
        MeterSpan(
            current_id,
            span_start,
            data.period_end,
            meter_consumption(current_opening, closing, meters[current_id].rollover_at, current_id),
        )
    )
    return spans


def build_segments(data: BillingInput) -> tuple[Segment, ...]:
    """Cut the period at every meter and tariff event and share out the kWh."""
    spans = meter_spans(data)
    tariffs = list(data.tariffs)

    cuts = {data.period_start, data.period_end}
    cuts.update(span.start for span in spans)
    cuts.update(t.effective_from for t in tariffs if data.period_start < t.effective_from < data.period_end)
    ordered = sorted(cuts)

    # Pieces of time: (start, end, index of the meter span it falls in, tariff)
    pieces: list[tuple[date, date, int, Tariff]] = []
    for start, end in zip(ordered, ordered[1:]):
        index = next(i for i, span in enumerate(spans) if span.start <= start < span.end)
        pieces.append((start, end, index, tariff_in_force(tariffs, start)))

    segments: list[Segment] = []
    for index, span in enumerate(spans):
        mine = [piece for piece in pieces if piece[2] == index]
        shares = allocate_kwh(span.kwh, [(end - start).days for start, end, _, _ in mine])
        for (start, end, _, tariff), kwh in zip(mine, shares):
            segments.append(Segment(start, end, span.meter_id, tariff, kwh))
    return tuple(sorted(segments, key=lambda s: s.start))


# ------------------------------------------------------------------- helpers


def _meter_with_opening_reading(data: BillingInput) -> str:
    ids = {r.meter_id for r in data.readings if r.date == data.period_start}
    if len(ids) != 1:
        raise InvalidReadingError(
            "without meter replacements, exactly one meter must have a reading on the first day of the "
            f"billing period; found {len(ids)}",
            period_start=data.period_start,
        )
    return next(iter(ids))


def _reading_at(data: BillingInput, meter_id: str, day: date, label: str) -> Decimal:
    values = {r.value for r in data.readings if r.meter_id == meter_id and r.date == day}
    if not values:
        raise InvalidReadingError(
            f"missing {label} reading for meter {meter_id!r} on {day}",
            meter_id=meter_id,
            date=day,
        )
    if len(values) > 1:
        raise InvalidReadingError(
            f"conflicting {label} readings for meter {meter_id!r} on {day}",
            meter_id=meter_id,
            date=day,
        )
    return next(iter(values))


def _check_register(meter: Meter, value: Decimal, label: str) -> None:
    """A reading must be a plausible register value for this meter."""
    if not has_at_most_places(value, Decimal("0.001")):
        raise InvalidReadingError(
            f"{label} for meter {meter.id!r} has more than three decimal places",
            meter_id=meter.id,
            value=value,
        )
    if meter.rollover_at is not None and value >= meter.rollover_at:
        raise InvalidReadingError(
            f"{label} {value} for meter {meter.id!r} is not below its rollover value {meter.rollover_at}",
            meter_id=meter.id,
            value=value,
        )
