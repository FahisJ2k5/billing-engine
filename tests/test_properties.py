"""Invariant tests: statements that must hold for *any* valid input.

These use seeded random inputs from the standard library, so they are
repeatable. (The Hypothesis library does this better, with automatic shrinking
of failing cases, and could replace this later; it is not installed here.)
"""

from __future__ import annotations

import random
import unittest
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from billing_engine import calculate, from_mapping
from billing_engine.consumption import allocate_kwh

CASES = 300


def random_input(rng: random.Random) -> dict[str, Any]:
    start = date(2026, 1, 1) + timedelta(days=rng.randrange(0, 300))
    days = rng.randrange(2, 90)
    end = start + timedelta(days=days)

    tariffs: list[dict[str, Any]] = [
        {
            "id": "T0",
            "effective_from": "2020-01-01",
            "daily_fixed_charge": f"{rng.randrange(0, 300) / 100:.2f}",
            "tiers": [
                {"up_to_kwh": str(rng.randrange(50, 300)), "rate": f"{rng.randrange(1, 40) / 100:.2f}"},
                {"rate": f"{rng.randrange(1, 80) / 100:.2f}"},
            ],
        }
    ]
    if rng.random() < 0.5:
        change = start + timedelta(days=rng.randrange(1, days))
        tariffs.append(
            {
                "id": "T1",
                "effective_from": change.isoformat(),
                "tiers": [{"rate": f"{rng.randrange(1, 60) / 100:.2f}"}],
            }
        )

    opening = rng.randrange(0, 99000)
    data: dict[str, Any] = {
        "customer_id": "PROP",
        "tax_rate": f"{rng.randrange(0, 25) / 100:.2f}",
        "billing_period": {"start": start.isoformat(), "end": end.isoformat()},
        "tariffs": tariffs,
        "meters": [{"id": "A", "rollover_at": "100000"}],
        "adjustments": [],
    }

    if rng.random() < 0.5:  # one meter replacement
        swap = start + timedelta(days=rng.randrange(1, days))
        used_before = rng.randrange(0, 900)
        data["meters"].append({"id": "B", "rollover_at": "100000"})
        data["meter_replacements"] = [
            {
                "date": swap.isoformat(),
                "old_meter_id": "A",
                "old_final_reading": str((opening + used_before) % 100000),
                "new_meter_id": "B",
                "new_initial_reading": str(rng.randrange(0, 50)),
            }
        ]
        data["readings"] = [
            {"meter_id": "A", "date": start.isoformat(), "value": str(opening)},
            {"meter_id": "B", "date": end.isoformat(), "value": str(rng.randrange(50, 1000))},
        ]
    else:
        data["readings"] = [
            {"meter_id": "A", "date": start.isoformat(), "value": str(opening)},
            {"meter_id": "A", "date": end.isoformat(), "value": str((opening + rng.randrange(0, 900)) % 100000)},
        ]

    for _ in range(rng.randrange(0, 3)):
        data["adjustments"].append(
            {
                "description": "adj",
                "amount": f"{rng.randrange(-500, 500) / 100:.2f}",
                "taxable": rng.random() < 0.5,
            }
        )
    return data


class Invariants(unittest.TestCase):
    def setUp(self) -> None:
        self.rng = random.Random(20260124)  # fixed seed: failures reproduce exactly

    def invoices(self) -> list[Any]:
        return [calculate(from_mapping(random_input(self.rng))) for _ in range(CASES)]

    def test_segments_tile_the_period_exactly(self) -> None:
        for invoice in self.invoices():
            cursor = invoice.period_start
            for segment in invoice.segments:
                self.assertEqual(segment.start, cursor)
                self.assertGreater(segment.end, segment.start)
                cursor = segment.end
            self.assertEqual(cursor, invoice.period_end)

    def test_segment_energy_is_never_negative(self) -> None:
        for invoice in self.invoices():
            for segment in invoice.segments:
                self.assertGreaterEqual(segment.kwh, 0)

    def test_total_is_exactly_the_sum_of_the_lines(self) -> None:
        for invoice in self.invoices():
            self.assertEqual(sum((line.amount for line in invoice.lines), Decimal(0)), invoice.summary.total)

    def test_every_amount_is_a_whole_number_of_cents(self) -> None:
        cent = Decimal("0.01")
        for invoice in self.invoices():
            for line in invoice.lines:
                self.assertEqual(line.amount, line.amount.quantize(cent))

    def test_energy_lines_account_for_every_kwh(self) -> None:
        for invoice in self.invoices():
            priced = sum((line.quantity or Decimal(0) for line in invoice.lines if line.kind == "energy"), Decimal(0))
            self.assertEqual(priced, invoice.total_kwh)

    def test_tax_is_never_negative(self) -> None:
        for invoice in self.invoices():
            self.assertGreaterEqual(invoice.summary.tax, 0)

    def test_calculation_is_deterministic(self) -> None:
        data = random_input(self.rng)
        first = calculate(from_mapping(data)).to_dict()
        second = calculate(from_mapping(data)).to_dict()
        self.assertEqual(first, second)

    def test_a_replacement_never_changes_the_energy_a_meter_measured(self) -> None:
        # Splitting a period at any day never creates or destroys kWh.
        for _ in range(CASES):
            total = Decimal(self.rng.randrange(0, 5_000_000)) / 1000
            parts = [self.rng.randrange(1, 40) for _ in range(self.rng.randrange(1, 6))]
            self.assertEqual(sum(allocate_kwh(total, parts), Decimal(0)), total)


if __name__ == "__main__":
    unittest.main()
