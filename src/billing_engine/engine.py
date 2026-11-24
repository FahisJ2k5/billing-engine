"""The calculation pipeline.

    validate -> split into segments -> price each segment -> adjustments -> tax -> total

Each stage is a separate, individually tested function. This module only wires
them together and does the final summing.
"""

from __future__ import annotations

from decimal import Decimal

from billing_engine.models import BillingInput, Invoice, LineItem, Summary
from billing_engine.money import round_money
from billing_engine.pricing import price_segment
from billing_engine.timeline import build_segments
from billing_engine.validation import validate


def calculate(data: BillingInput) -> Invoice:
    """Produce an itemised invoice. Raises a BillingError subclass on bad input."""
    validate(data)
    segments = build_segments(data)
    period_days = (data.period_end - data.period_start).days

    lines: list[LineItem] = []
    for segment in segments:
        lines.extend(price_segment(segment, period_days))

    adjustment_lines = [
        LineItem(kind="adjustment", description=adj.description, amount=round_money(adj.amount))
        for adj in data.adjustments
    ]
    lines.extend(adjustment_lines)

    energy = _total(lines, "energy")
    fixed = _total(lines, "fixed")
    adjustments = _total(lines, "adjustment")

    # Tax applies to energy, fixed charges and taxable adjustments. The base never
    # goes below zero, so a large credit cannot produce a negative tax.
    taxable_adjustments = sum(
        (line.amount for line, adj in zip(adjustment_lines, data.adjustments) if adj.taxable),
        Decimal(0),
    )
    taxable_base = max(energy + fixed + taxable_adjustments, Decimal(0))
    tax = round_money(taxable_base * data.tax_rate)
    if data.tax_rate > 0:
        lines.append(
            LineItem(
                kind="tax",
                description=f"Tax at {data.tax_rate * 100:f}% on {taxable_base}",
                amount=tax,
            )
        )

    summary = Summary(
        energy=energy,
        fixed=fixed,
        adjustments=adjustments,
        taxable_base=taxable_base,
        tax_rate=data.tax_rate,
        tax=tax,
        total=energy + fixed + adjustments + tax,
    )
    return Invoice(
        customer_id=data.customer_id,
        currency=data.currency,
        period_start=data.period_start,
        period_end=data.period_end,
        segments=segments,
        lines=tuple(lines),
        summary=summary,
    )


def _total(lines: list[LineItem], kind: str) -> Decimal:
    return sum((line.amount for line in lines if line.kind == kind), Decimal(0))
