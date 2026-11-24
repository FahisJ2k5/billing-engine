"""Command-line interface: ``billing-engine calculate input.json``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from billing_engine.engine import calculate
from billing_engine.errors import BillingError, OutputFileError
from billing_engine.parsing import load_input


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="billing-engine",
        description="Calculate an itemised utility invoice from meter readings and events.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    calc = commands.add_parser("calculate", help="read an input JSON file and produce an invoice")
    calc.add_argument("input", type=Path, help="path to the input JSON file")
    calc.add_argument("-o", "--output", type=Path, help="write the invoice here instead of to standard output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Return 0 on success, 1 when the input is rejected. Errors are printed as JSON on stderr."""
    args = build_parser().parse_args(argv)
    try:
        invoice = calculate(load_input(args.input))
        text = json.dumps(invoice.to_dict(), indent=2) + "\n"
        if args.output is None:
            sys.stdout.write(text)
        else:
            try:
                args.output.write_text(text, encoding="utf-8")
            except OSError as exc:
                raise OutputFileError(f"cannot write {args.output}: {exc.strerror or exc}") from exc
    except BillingError as exc:
        print(json.dumps(exc.to_dict(), indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
