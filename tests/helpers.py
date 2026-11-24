"""Shared helpers for the test suite."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

_BASE: dict[str, Any] = {
    "customer_id": "TEST",
    "currency": "USD",
    "tax_rate": "0",
    "billing_period": {"start": "2026-01-01", "end": "2026-02-01"},
    "tariffs": [
        {
            "id": "T1",
            "effective_from": "2025-01-01",
            "daily_fixed_charge": "0",
            "tiers": [{"rate": "0.10"}],
        }
    ],
    "meters": [{"id": "M1", "rollover_at": "100000"}],
    "readings": [
        {"meter_id": "M1", "date": "2026-01-01", "value": "1000"},
        {"meter_id": "M1", "date": "2026-02-01", "value": "1100"},
    ],
}


def base_input() -> dict[str, Any]:
    """A fresh, valid input (100 kWh at a flat 0.10) that tests can modify."""
    return copy.deepcopy(_BASE)
