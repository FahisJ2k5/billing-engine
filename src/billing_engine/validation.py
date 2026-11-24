"""Domain checks that go beyond the shape of the JSON.

parsing.py guarantees every field has the right type. This module checks that
the pieces make sense *together*: the period is sane, tariffs are well formed
and cover the period, and the meter replacements form one unbroken chain.
"""

from __future__ import annotations

from billing_engine.errors import (
    BillingPeriodError,
    InputValidationError,
    InvalidEventError,
    InvalidReadingError,
    TariffError,
)
from billing_engine.models import BillingInput, Tariff

MAX_PERIOD_DAYS = 366


def validate(data: BillingInput) -> None:
    """Raise a BillingError subclass if the input is inconsistent."""
    _check_period(data)
    _check_meters(data)
    for tariff in data.tariffs:
        check_tariff(tariff)
    _check_tariff_set(data)
    _check_readings_reference_known_meters(data)
    _check_replacements(data)


def check_tariff(tariff: Tariff) -> None:
    """A tariff needs ascending tier limits and a final, open-ended tier.

    Requiring the last tier to be open-ended guarantees every kilowatt-hour
    falls into some tier, so no energy can silently go unpriced.
    """
    if not tariff.tiers:
        raise TariffError(f"tariff {tariff.id!r} has no tiers", tariff_id=tariff.id)

    previous_limit = None
    for index, tier in enumerate(tariff.tiers):
        is_last = index == len(tariff.tiers) - 1
        if tier.up_to_kwh is None:
            if not is_last:
                raise TariffError(
                    f"tariff {tariff.id!r}: only the last tier may omit up_to_kwh",
                    tariff_id=tariff.id,
                    tier=index + 1,
                )
            continue
        if is_last:
            raise TariffError(
                f"tariff {tariff.id!r}: the last tier must omit up_to_kwh so it covers all remaining energy",
                tariff_id=tariff.id,
            )
        if tier.up_to_kwh <= 0 or (previous_limit is not None and tier.up_to_kwh <= previous_limit):
            raise TariffError(
                f"tariff {tariff.id!r}: up_to_kwh values must be positive and strictly increasing",
                tariff_id=tariff.id,
                tier=index + 1,
            )
        previous_limit = tier.up_to_kwh


def _check_period(data: BillingInput) -> None:
    days = (data.period_end - data.period_start).days
    if days <= 0:
        raise BillingPeriodError(
            "billing_period.end must be after billing_period.start",
            start=data.period_start,
            end=data.period_end,
        )
    if days > MAX_PERIOD_DAYS:
        raise BillingPeriodError(
            f"billing period is {days} days long; the maximum is {MAX_PERIOD_DAYS}",
            days=days,
        )


def _check_meters(data: BillingInput) -> None:
    if not data.meters:
        raise InputValidationError("at least one meter is required", field="meters")
    seen: set[str] = set()
    for meter in data.meters:
        if meter.id in seen:
            raise InputValidationError(f"duplicate meter id {meter.id!r}", field="meters")
        seen.add(meter.id)


def _check_tariff_set(data: BillingInput) -> None:
    if not data.tariffs:
        raise TariffError("at least one tariff is required")
    ids: set[str] = set()
    starts = set()
    for tariff in data.tariffs:
        if tariff.id in ids:
            raise TariffError(f"duplicate tariff id {tariff.id!r}", tariff_id=tariff.id)
        if tariff.effective_from in starts:
            raise TariffError(
                f"two tariffs take effect on {tariff.effective_from}",
                effective_from=tariff.effective_from,
            )
        ids.add(tariff.id)
        starts.add(tariff.effective_from)
    if min(starts) > data.period_start:
        raise TariffError(
            "no tariff is in force on the first day of the billing period",
            period_start=data.period_start,
            earliest_tariff=min(starts),
        )


def _check_readings_reference_known_meters(data: BillingInput) -> None:
    known = {meter.id for meter in data.meters}
    for reading in data.readings:
        if reading.meter_id not in known:
            raise InvalidReadingError(
                f"reading refers to unknown meter {reading.meter_id!r}",
                meter_id=reading.meter_id,
            )


def _check_replacements(data: BillingInput) -> None:
    known = {meter.id for meter in data.meters}
    ordered = sorted(data.replacements, key=lambda r: r.date)

    dates = [r.date for r in ordered]
    if len(dates) != len(set(dates)):
        raise InvalidEventError("two meter replacements happen on the same date")

    for event in ordered:
        if not data.period_start < event.date < data.period_end:
            raise InvalidEventError(
                "a meter replacement must happen after the first day and before the end of the billing period",
                date=event.date,
                period_start=data.period_start,
                period_end=data.period_end,
            )
        for meter_id in (event.old_meter_id, event.new_meter_id):
            if meter_id not in known:
                raise InvalidEventError(f"replacement refers to unknown meter {meter_id!r}", meter_id=meter_id)
        if event.old_meter_id == event.new_meter_id:
            raise InvalidEventError(f"meter {event.old_meter_id!r} cannot replace itself", meter_id=event.old_meter_id)

    # The replacements must form a chain: each one removes the meter that the
    # previous one installed, and no meter is installed twice.
    if ordered:
        current = ordered[0].old_meter_id
        used = {current}
        for event in ordered:
            if event.old_meter_id != current:
                raise InvalidEventError(
                    f"on {event.date} meter {event.old_meter_id!r} is removed, "
                    f"but meter {current!r} is the one in service",
                    date=event.date,
                )
            if event.new_meter_id in used:
                raise InvalidEventError(
                    f"meter {event.new_meter_id!r} was already in service earlier in this period",
                    date=event.date,
                )
            used.add(event.new_meter_id)
            current = event.new_meter_id
