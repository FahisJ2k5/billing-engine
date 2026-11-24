"""Golden tests: each example input must produce the invoice worked out by hand."""

from __future__ import annotations

import json
import unittest
from decimal import Decimal

from billing_engine import calculate, load_input
from tests.helpers import EXAMPLES


class GoldenExamples(unittest.TestCase):
    def test_every_example_has_an_expected_file(self) -> None:
        inputs = sorted(p.name for p in EXAMPLES.glob("*.json"))
        expected = sorted(p.name for p in (EXAMPLES / "expected").glob("*.json"))
        self.assertEqual(inputs, expected)
        self.assertGreaterEqual(len(inputs), 5)

    def test_examples_match_hand_computed_invoices(self) -> None:
        for path in sorted(EXAMPLES.glob("*.json")):
            with self.subTest(example=path.name):
                want = json.loads((EXAMPLES / "expected" / path.name).read_text(encoding="utf-8"))
                invoice = calculate(load_input(path))

                self.assertEqual(invoice.total_kwh, Decimal(want["total_kwh"]))
                self.assertEqual([s.kwh for s in invoice.segments], [Decimal(k) for k in want["segment_kwh"]])
                self.assertEqual([line.amount for line in invoice.lines], [Decimal(a) for a in want["line_amounts"]])

                summary = invoice.summary
                for key, value in want["summary"].items():
                    self.assertEqual(getattr(summary, key), Decimal(value), msg=key)

    def test_total_equals_sum_of_lines(self) -> None:
        for path in sorted(EXAMPLES.glob("*.json")):
            with self.subTest(example=path.name):
                invoice = calculate(load_input(path))
                self.assertEqual(sum((line.amount for line in invoice.lines), Decimal(0)), invoice.summary.total)

    def test_output_is_valid_json_with_text_numbers(self) -> None:
        invoice = calculate(load_input(EXAMPLES / "01-simple.json"))
        data = json.loads(json.dumps(invoice.to_dict()))
        self.assertEqual(data["summary"]["total"], "47.30")
        self.assertEqual(data["billing_period"]["days"], 31)
        self.assertIsInstance(data["lines"][0]["amount"], str)


if __name__ == "__main__":
    unittest.main()
