"""The command-line interface, tested end to end."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from billing_engine.cli import main
from tests.helpers import EXAMPLES


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Cli(unittest.TestCase):
    def test_prints_the_invoice_to_stdout(self) -> None:
        code, out, err = run("calculate", str(EXAMPLES / "01-simple.json"))
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(json.loads(out)["summary"]["total"], "47.30")

    def test_writes_to_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "invoice.json"
            code, out, _ = run("calculate", str(EXAMPLES / "03-rollover.json"), "-o", str(target))
            self.assertEqual(code, 0)
            self.assertEqual(out, "")
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["summary"]["total"], "30.00")

    def test_missing_input_file(self) -> None:
        code, out, err = run("calculate", "does-not-exist.json")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(json.loads(err)["error"]["code"], "input_file_error")

    def test_invalid_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "bad.json"
            bad.write_text("{oops", encoding="utf-8")
            code, _, err = run("calculate", str(bad))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(err)["error"]["code"], "invalid_json")

    def test_business_rule_failure_exits_one_with_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            data = json.loads((EXAMPLES / "01-simple.json").read_text(encoding="utf-8"))
            data["billing_period"] = {"start": "2026-02-01", "end": "2026-01-01"}
            bad = Path(folder) / "reversed.json"
            bad.write_text(json.dumps(data), encoding="utf-8")
            code, _, err = run("calculate", str(bad))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(err)["error"]["code"], "invalid_period")

    def test_unwritable_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "missing-folder" / "invoice.json"
            code, _, err = run("calculate", str(EXAMPLES / "01-simple.json"), "-o", str(target))
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(err)["error"]["code"], "output_file_error")


if __name__ == "__main__":
    unittest.main()
