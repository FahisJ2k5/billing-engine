"""Every kind of bad input must be rejected with the right error code."""

from __future__ import annotations

import json
import unittest
from typing import Any

from billing_engine import calculate, from_mapping, parse_input
from billing_engine.errors import BillingError
from tests.helpers import base_input


def code_for(data: Any) -> str:
    """Run the full pipeline and return the error code it raises."""
    with unittest.TestCase().assertRaises(BillingError) as ctx:
        calculate(from_mapping(data))
    return ctx.exception.code


class InputShape(unittest.TestCase):
    def test_valid_input_passes(self) -> None:
        self.assertEqual(calculate(from_mapping(base_input())).summary.total, 10)

    def test_not_json(self) -> None:
        with self.assertRaises(BillingError) as ctx:
            parse_input("{not json")
        self.assertEqual(ctx.exception.code, "invalid_json")

    def test_top_level_must_be_an_object(self) -> None:
        self.assertEqual(code_for([]), "invalid_input")

    def test_missing_required_field(self) -> None:
        data = base_input()
        del data["readings"]
        self.assertEqual(code_for(data), "invalid_input")

    def test_unknown_field_is_rejected_so_typos_are_not_ignored(self) -> None:
        data = base_input()
        data["tax_rat"] = "0.1"
        self.assertEqual(code_for(data), "invalid_input")

    def test_money_must_not_be_a_json_float(self) -> None:
        data = base_input()
        data["tariffs"][0]["tiers"][0]["rate"] = 0.1
        self.assertEqual(code_for(data), "invalid_input")

    def test_booleans_are_not_numbers(self) -> None:
        data = base_input()
        data["tax_rate"] = True
        self.assertEqual(code_for(data), "invalid_input")

    def test_garbage_number(self) -> None:
        data = base_input()
        data["tariffs"][0]["tiers"][0]["rate"] = "abc"
        self.assertEqual(code_for(data), "invalid_input")

    def test_non_finite_number(self) -> None:
        data = base_input()
        data["tariffs"][0]["tiers"][0]["rate"] = "NaN"
        self.assertEqual(code_for(data), "invalid_input")

    def test_negative_rate(self) -> None:
        data = base_input()
        data["tariffs"][0]["tiers"][0]["rate"] = "-0.10"
        self.assertEqual(code_for(data), "invalid_input")

    def test_tax_rate_outside_zero_to_one(self) -> None:
        data = base_input()
        data["tax_rate"] = "1.5"
        self.assertEqual(code_for(data), "invalid_input")

    def test_bad_currency(self) -> None:
        data = base_input()
        data["currency"] = "usd"
        self.assertEqual(code_for(data), "invalid_input")

    def test_impossible_date(self) -> None:
        data = base_input()
        data["billing_period"]["start"] = "2026-02-30"
        self.assertEqual(code_for(data), "invalid_input")

    def test_date_must_use_one_format(self) -> None:
        data = base_input()
        data["billing_period"]["start"] = "20260101"
        self.assertEqual(code_for(data), "invalid_input")

    def test_taxable_must_be_boolean(self) -> None:
        data = base_input()
        data["adjustments"] = [{"description": "x", "amount": "1", "taxable": "yes"}]
        self.assertEqual(code_for(data), "invalid_input")

    def test_error_names_the_field(self) -> None:
        data = base_input()
        data["tariffs"][0]["tiers"][0]["rate"] = "abc"
        with self.assertRaises(BillingError) as ctx:
            from_mapping(data)
        self.assertEqual(ctx.exception.details["field"], "tariffs[0].tiers[0].rate")

    def test_error_serialises_to_json(self) -> None:
        with self.assertRaises(BillingError) as ctx:
            parse_input("[]")
        payload = json.loads(json.dumps(ctx.exception.to_dict()))
        self.assertEqual(payload["error"]["code"], "invalid_input")


class Period(unittest.TestCase):
    def test_end_before_start(self) -> None:
        data = base_input()
        data["billing_period"] = {"start": "2026-02-01", "end": "2026-01-01"}
        self.assertEqual(code_for(data), "invalid_period")

    def test_empty_period(self) -> None:
        data = base_input()
        data["billing_period"] = {"start": "2026-01-01", "end": "2026-01-01"}
        self.assertEqual(code_for(data), "invalid_period")

    def test_period_too_long(self) -> None:
        data = base_input()
        data["billing_period"] = {"start": "2026-01-01", "end": "2028-01-01"}
        self.assertEqual(code_for(data), "invalid_period")


class Readings(unittest.TestCase):
    def test_missing_closing_reading(self) -> None:
        data = base_input()
        data["readings"].pop()
        self.assertEqual(code_for(data), "invalid_reading")

    def test_missing_opening_reading(self) -> None:
        data = base_input()
        data["readings"].pop(0)
        self.assertEqual(code_for(data), "invalid_reading")

    def test_conflicting_readings_on_one_day(self) -> None:
        data = base_input()
        data["readings"].append({"meter_id": "M1", "date": "2026-02-01", "value": "1200"})
        self.assertEqual(code_for(data), "invalid_reading")

    def test_unknown_meter(self) -> None:
        data = base_input()
        data["readings"].append({"meter_id": "GHOST", "date": "2026-01-15", "value": "5"})
        self.assertEqual(code_for(data), "invalid_reading")

    def test_decrease_without_rollover(self) -> None:
        data = base_input()
        data["meters"] = [{"id": "M1"}]
        data["readings"][1]["value"] = "900"
        self.assertEqual(code_for(data), "invalid_reading")

    def test_reading_at_or_above_rollover(self) -> None:
        data = base_input()
        data["readings"][1]["value"] = "100000"
        self.assertEqual(code_for(data), "invalid_reading")

    def test_more_than_three_decimals(self) -> None:
        data = base_input()
        data["readings"][1]["value"] = "1100.0005"
        self.assertEqual(code_for(data), "invalid_reading")

    def test_two_meters_open_without_a_replacement_is_ambiguous(self) -> None:
        data = base_input()
        data["meters"].append({"id": "M2", "rollover_at": "100000"})
        data["readings"].append({"meter_id": "M2", "date": "2026-01-01", "value": "0"})
        self.assertEqual(code_for(data), "invalid_reading")


class Meters(unittest.TestCase):
    def test_duplicate_meter_id(self) -> None:
        data = base_input()
        data["meters"].append({"id": "M1"})
        self.assertEqual(code_for(data), "invalid_input")

    def test_no_meters(self) -> None:
        data = base_input()
        data["meters"] = []
        self.assertEqual(code_for(data), "invalid_input")


def with_replacement(**overrides: str) -> dict[str, Any]:
    data = base_input()
    data["meters"].append({"id": "M2", "rollover_at": "100000"})
    event = {
        "date": "2026-01-11",
        "old_meter_id": "M1",
        "old_final_reading": "1040",
        "new_meter_id": "M2",
        "new_initial_reading": "0",
    }
    event.update(overrides)
    data["meter_replacements"] = [event]
    data["readings"] = [
        {"meter_id": "M1", "date": "2026-01-01", "value": "1000"},
        {"meter_id": "M2", "date": "2026-02-01", "value": "60"},
    ]
    return data


class Replacements(unittest.TestCase):
    def test_valid_replacement_passes(self) -> None:
        invoice = calculate(from_mapping(with_replacement()))
        self.assertEqual(invoice.total_kwh, 100)

    def test_on_first_day(self) -> None:
        self.assertEqual(code_for(with_replacement(date="2026-01-01")), "invalid_event")

    def test_on_last_day(self) -> None:
        self.assertEqual(code_for(with_replacement(date="2026-02-01")), "invalid_event")

    def test_outside_the_period(self) -> None:
        self.assertEqual(code_for(with_replacement(date="2026-03-01")), "invalid_event")

    def test_unknown_new_meter(self) -> None:
        self.assertEqual(code_for(with_replacement(new_meter_id="GHOST")), "invalid_event")

    def test_meter_replacing_itself(self) -> None:
        self.assertEqual(code_for(with_replacement(new_meter_id="M1")), "invalid_event")

    def test_two_on_the_same_date(self) -> None:
        data = with_replacement()
        data["meter_replacements"].append(dict(data["meter_replacements"][0]))
        self.assertEqual(code_for(data), "invalid_event")

    def test_broken_chain(self) -> None:
        data = with_replacement()
        data["meters"].append({"id": "M3", "rollover_at": "100000"})
        data["meter_replacements"].append(
            {
                "date": "2026-01-21",
                "old_meter_id": "M1",  # M1 was already removed; M2 is in service
                "old_final_reading": "1050",
                "new_meter_id": "M3",
                "new_initial_reading": "0",
            }
        )
        self.assertEqual(code_for(data), "invalid_event")

    def test_old_meter_cannot_come_back(self) -> None:
        data = with_replacement()
        data["meter_replacements"].append(
            {
                "date": "2026-01-21",
                "old_meter_id": "M2",
                "old_final_reading": "30",
                "new_meter_id": "M1",
                "new_initial_reading": "1040",
            }
        )
        self.assertEqual(code_for(data), "invalid_event")

    def test_final_reading_below_start_without_rollover(self) -> None:
        data = with_replacement(old_final_reading="900")
        data["meters"][0] = {"id": "M1"}
        self.assertEqual(code_for(data), "invalid_reading")


class Tariffs(unittest.TestCase):
    def test_no_tariff_on_the_first_day(self) -> None:
        data = base_input()
        data["tariffs"][0]["effective_from"] = "2026-01-15"
        self.assertEqual(code_for(data), "tariff_error")

    def test_duplicate_tariff_id(self) -> None:
        data = base_input()
        data["tariffs"].append({**data["tariffs"][0], "effective_from": "2026-01-10"})
        self.assertEqual(code_for(data), "tariff_error")

    def test_two_tariffs_starting_the_same_day(self) -> None:
        data = base_input()
        data["tariffs"].append({**data["tariffs"][0], "id": "T2"})
        self.assertEqual(code_for(data), "tariff_error")

    def test_last_tier_must_be_open_ended(self) -> None:
        data = base_input()
        data["tariffs"][0]["tiers"] = [{"up_to_kwh": "100", "rate": "0.1"}]
        self.assertEqual(code_for(data), "tariff_error")

    def test_open_tier_must_be_last(self) -> None:
        data = base_input()
        data["tariffs"][0]["tiers"] = [{"rate": "0.1"}, {"up_to_kwh": "100", "rate": "0.2"}]
        self.assertEqual(code_for(data), "tariff_error")

    def test_tier_limits_must_increase(self) -> None:
        data = base_input()
        data["tariffs"][0]["tiers"] = [
            {"up_to_kwh": "200", "rate": "0.1"},
            {"up_to_kwh": "100", "rate": "0.2"},
            {"rate": "0.3"},
        ]
        self.assertEqual(code_for(data), "tariff_error")

    def test_no_tiers(self) -> None:
        data = base_input()
        data["tariffs"][0]["tiers"] = []
        self.assertEqual(code_for(data), "tariff_error")

    def test_no_tariffs(self) -> None:
        data = base_input()
        data["tariffs"] = []
        self.assertEqual(code_for(data), "tariff_error")


if __name__ == "__main__":
    unittest.main()
