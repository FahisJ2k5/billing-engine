"""Reads and validates the JSON input.

Validation is strict on purpose: unknown fields, wrong types, floats where text
is expected and impossible dates are all rejected with a precise message that
names the offending field. Money is accepted only as a string ("0.18") or an
integer, never as a JSON float, because floats are already inexact when parsed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from billing_engine.errors import (
    InputFileError,
    InputValidationError,
    InvalidJsonError,
)
from billing_engine.models import (
    Adjustment,
    BillingInput,
    Meter,
    MeterReplacement,
    Reading,
    Tariff,
    Tier,
)

_CURRENCY = re.compile(r"^[A-Z]{3}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_input(path: Path) -> BillingInput:
    """Read a JSON file and return validated input."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputFileError(f"cannot read {path}: {exc.strerror or exc}", path=path) from exc
    return parse_input(text)


def parse_input(text: str) -> BillingInput:
    """Parse JSON text and return validated input."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidJsonError(f"input is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})") from exc
    return from_mapping(raw)


def from_mapping(raw: object) -> BillingInput:
    """Validate an already-decoded JSON value."""
    data = _mapping(raw, "input")
    _only_keys(
        data,
        "input",
        required={"customer_id", "billing_period", "tariffs", "meters", "readings"},
        optional={"currency", "tax_rate", "meter_replacements", "adjustments"},
    )

    period = _mapping(data["billing_period"], "billing_period")
    _only_keys(period, "billing_period", required={"start", "end"})

    currency = data.get("currency", "USD")
    if not isinstance(currency, str) or not _CURRENCY.match(currency):
        raise InputValidationError("currency must be a three-letter upper-case code", field="currency")

    tax_rate = _decimal(data.get("tax_rate", "0"), "tax_rate")
    if not Decimal(0) <= tax_rate <= Decimal(1):
        raise InputValidationError("tax_rate must be between 0 and 1", field="tax_rate", value=tax_rate)

    return BillingInput(
        customer_id=_string(data["customer_id"], "customer_id"),
        currency=currency,
        period_start=_date(period["start"], "billing_period.start"),
        period_end=_date(period["end"], "billing_period.end"),
        tax_rate=tax_rate,
        tariffs=tuple(_tariff(item, f"tariffs[{i}]") for i, item in enumerate(_list(data["tariffs"], "tariffs"))),
        meters=tuple(_meter(item, f"meters[{i}]") for i, item in enumerate(_list(data["meters"], "meters"))),
        readings=tuple(_reading(item, f"readings[{i}]") for i, item in enumerate(_list(data["readings"], "readings"))),
        replacements=tuple(
            _replacement(item, f"meter_replacements[{i}]")
            for i, item in enumerate(_list(data.get("meter_replacements", []), "meter_replacements"))
        ),
        adjustments=tuple(
            _adjustment(item, f"adjustments[{i}]")
            for i, item in enumerate(_list(data.get("adjustments", []), "adjustments"))
        ),
    )


# ------------------------------------------------------------------ builders


def _tariff(raw: object, where: str) -> Tariff:
    item = _mapping(raw, where)
    _only_keys(item, where, required={"id", "effective_from", "tiers"}, optional={"daily_fixed_charge"})
    tiers = tuple(_tier(t, f"{where}.tiers[{i}]") for i, t in enumerate(_list(item["tiers"], f"{where}.tiers")))
    fixed = _decimal(item.get("daily_fixed_charge", "0"), f"{where}.daily_fixed_charge", minimum=Decimal(0))
    return Tariff(
        id=_string(item["id"], f"{where}.id"),
        effective_from=_date(item["effective_from"], f"{where}.effective_from"),
        tiers=tiers,
        daily_fixed_charge=fixed,
    )


def _tier(raw: object, where: str) -> Tier:
    item = _mapping(raw, where)
    _only_keys(item, where, required={"rate"}, optional={"up_to_kwh"})
    limit = item.get("up_to_kwh")
    return Tier(
        up_to_kwh=None if limit is None else _decimal(limit, f"{where}.up_to_kwh", minimum=Decimal(0)),
        rate=_decimal(item["rate"], f"{where}.rate", minimum=Decimal(0)),
    )


def _meter(raw: object, where: str) -> Meter:
    item = _mapping(raw, where)
    _only_keys(item, where, required={"id"}, optional={"rollover_at"})
    rollover = item.get("rollover_at")
    return Meter(
        id=_string(item["id"], f"{where}.id"),
        rollover_at=None if rollover is None else _decimal(rollover, f"{where}.rollover_at", positive=True),
    )


def _reading(raw: object, where: str) -> Reading:
    item = _mapping(raw, where)
    _only_keys(item, where, required={"meter_id", "date", "value"})
    return Reading(
        meter_id=_string(item["meter_id"], f"{where}.meter_id"),
        date=_date(item["date"], f"{where}.date"),
        value=_decimal(item["value"], f"{where}.value", minimum=Decimal(0)),
    )


def _replacement(raw: object, where: str) -> MeterReplacement:
    item = _mapping(raw, where)
    _only_keys(
        item,
        where,
        required={"date", "old_meter_id", "old_final_reading", "new_meter_id", "new_initial_reading"},
    )
    return MeterReplacement(
        date=_date(item["date"], f"{where}.date"),
        old_meter_id=_string(item["old_meter_id"], f"{where}.old_meter_id"),
        old_final_reading=_decimal(item["old_final_reading"], f"{where}.old_final_reading", minimum=Decimal(0)),
        new_meter_id=_string(item["new_meter_id"], f"{where}.new_meter_id"),
        new_initial_reading=_decimal(item["new_initial_reading"], f"{where}.new_initial_reading", minimum=Decimal(0)),
    )


def _adjustment(raw: object, where: str) -> Adjustment:
    item = _mapping(raw, where)
    _only_keys(item, where, required={"description", "amount"}, optional={"taxable"})
    taxable = item.get("taxable", False)
    if not isinstance(taxable, bool):
        raise InputValidationError("taxable must be true or false", field=f"{where}.taxable")
    return Adjustment(
        description=_string(item["description"], f"{where}.description"),
        amount=_decimal(item["amount"], f"{where}.amount"),
        taxable=taxable,
    )


# ------------------------------------------------------------ type primitives


def _mapping(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise InputValidationError(f"{where} must be a JSON object", field=where)
    return value


def _list(value: object, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise InputValidationError(f"{where} must be a list", field=where)
    return value


def _only_keys(
    data: Mapping[str, Any],
    where: str,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    missing = sorted(required - data.keys())
    if missing:
        raise InputValidationError(f"{where} is missing required field(s): {', '.join(missing)}", field=where)
    unknown = sorted(set(data.keys()) - allowed)
    if unknown:
        raise InputValidationError(f"{where} has unknown field(s): {', '.join(unknown)}", field=where)


def _string(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InputValidationError(f"{where} must be a non-empty string", field=where)
    return value


def _date(value: object, where: str) -> date:
    if not isinstance(value, str):
        raise InputValidationError(f"{where} must be a date string like 2026-01-31", field=where)
    # Python 3.11+ accepts more ISO forms than 3.10 does. Insist on one shape so the
    # same input behaves the same on every supported Python version.
    if not _ISO_DATE.match(value):
        raise InputValidationError(f"{where} must be written as YYYY-MM-DD, got {value!r}", field=where)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InputValidationError(f"{where} is not a valid date: {value!r}", field=where) from exc


def _decimal(
    value: object,
    where: str,
    *,
    minimum: Decimal | None = None,
    positive: bool = False,
) -> Decimal:
    # bool is a subclass of int, so it must be excluded explicitly.
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (str, int)):
        raise InputValidationError(
            f'{where} must be a decimal number written as a string (for example "0.18") or an integer',
            field=where,
        )
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise InputValidationError(f"{where} is not a valid number: {value!r}", field=where) from exc
    if not number.is_finite():
        raise InputValidationError(f"{where} must be a finite number", field=where)
    if positive and number <= 0:
        raise InputValidationError(f"{where} must be greater than zero", field=where, value=number)
    if minimum is not None and number < minimum:
        raise InputValidationError(f"{where} must be at least {minimum}", field=where, value=number)
    return number
