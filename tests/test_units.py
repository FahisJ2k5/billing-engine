"""Unit tests for the small pure functions."""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from billing_engine.consumption import allocate_kwh, meter_consumption
from billing_engine.errors import InvalidReadingError
from billing_engine.models import Segment, Tariff, Tier
from billing_engine.money import has_at_most_places, round_kwh, round_money, to_text
from billing_engine.pricing import price_segment

D = Decimal


class Rounding(unittest.TestCase):
    def test_exact_half_rounds_away_from_zero(self) -> None:
        self.assertEqual(round_money(D("2.325")), D("2.33"))
        self.assertEqual(round_money(D("-2.325")), D("-2.33"))
        self.assertEqual(round_money(D("2.324")), D("2.32"))

    def test_decimal_avoids_the_float_trap(self) -> None:
        self.assertNotEqual(0.1 + 0.2, 0.3)
        self.assertEqual(D("0.1") + D("0.2"), D("0.3"))

    def test_kwh_rounds_to_watt_hours(self) -> None:
        self.assertEqual(round_kwh(D("1.0005")), D("1.001"))

    def test_places_and_text(self) -> None:
        self.assertTrue(has_at_most_places(D("5.123"), D("0.001")))
        self.assertFalse(has_at_most_places(D("5.1234"), D("0.001")))
        self.assertEqual(to_text(D("1E+1")), "10")


class MeterConsumption(unittest.TestCase):
    def test_plain_difference(self) -> None:
        self.assertEqual(meter_consumption(D("100"), D("350"), None), D("250"))

    def test_zero_use(self) -> None:
        self.assertEqual(meter_consumption(D("100"), D("100"), D("1000")), D("0"))

    def test_rollover(self) -> None:
        self.assertEqual(meter_consumption(D("99900"), D("150"), D("100000")), D("250"))

    def test_decrease_without_rollover_is_an_error(self) -> None:
        with self.assertRaises(InvalidReadingError) as ctx:
            meter_consumption(D("500"), D("100"), None, "M1")
        self.assertEqual(ctx.exception.code, "invalid_reading")


class Allocation(unittest.TestCase):
    def test_parts_always_sum_to_the_total(self) -> None:
        for total in (D("100"), D("100.001"), D("0.007"), D("12345.678")):
            for days in ([10, 21], [1, 1, 1], [7, 7, 7, 10], [30]):
                with self.subTest(total=total, days=days):
                    self.assertEqual(sum(allocate_kwh(total, days), D(0)), total)

    def test_proportional_split(self) -> None:
        self.assertEqual(allocate_kwh(D("310"), [16, 15]), [D("160.000"), D("150.000")])

    def test_no_part_is_negative(self) -> None:
        for part in allocate_kwh(D("0.001"), [1, 1, 1, 1]):
            self.assertGreaterEqual(part, 0)


def _segment(kwh: str, days: int, tariff: Tariff) -> Segment:
    start = date(2026, 1, 1)
    return Segment(start, date.fromordinal(start.toordinal() + days), "M1", tariff, D(kwh))


TIERED = Tariff(
    "T",
    date(2025, 1, 1),
    (Tier(D("100"), D("0.10")), Tier(D("300"), D("0.14")), Tier(None, D("0.20"))),
    D("0.25"),
)


class Pricing(unittest.TestCase):
    def test_full_period_uses_tier_limits_as_written(self) -> None:
        lines = price_segment(_segment("400", 31, TIERED), 31)
        energy = [line for line in lines if line.kind == "energy"]
        self.assertEqual([line.quantity for line in energy], [D("100"), D("200"), D("100")])
        self.assertEqual([line.amount for line in energy], [D("10.00"), D("28.00"), D("20.00")])

    def test_partial_segment_scales_the_tier_limits(self) -> None:
        # 15 of 30 days: limits halve to 50 and 150 kWh.
        lines = price_segment(_segment("120", 15, TIERED), 30)
        energy = [line for line in lines if line.kind == "energy"]
        self.assertEqual([line.quantity for line in energy], [D("50.000"), D("70.000")])

    def test_tier_quantities_add_up_to_the_segment_energy(self) -> None:
        for kwh in ("0", "0.001", "99.999", "100", "250.5", "10000"):
            with self.subTest(kwh=kwh):
                lines = price_segment(_segment(kwh, 17, TIERED), 31)
                used = sum((line.quantity or D(0) for line in lines if line.kind == "energy"), D(0))
                self.assertEqual(used, D(kwh))

    def test_zero_energy_produces_no_energy_lines(self) -> None:
        lines = price_segment(_segment("0", 10, TIERED), 31)
        self.assertEqual([line.kind for line in lines], ["fixed"])

    def test_fixed_charge_is_daily_and_rounded_once(self) -> None:
        lines = price_segment(_segment("0", 31, TIERED), 31)
        self.assertEqual(lines[0].amount, D("7.75"))

    def test_no_fixed_line_when_the_charge_is_zero(self) -> None:
        free = Tariff("F", date(2025, 1, 1), (Tier(None, D("0.10")),), D("0"))
        lines = price_segment(_segment("10", 5, free), 31)
        self.assertEqual([line.kind for line in lines], ["energy"])


if __name__ == "__main__":
    unittest.main()
