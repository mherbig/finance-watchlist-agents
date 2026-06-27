"""Tests fuer die Idempotenz-Helfer in scripts/attach_signals.py."""
import importlib.util
import json
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "attach_signals", _root / "scripts" / "attach_signals.py")
attach_signals = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(attach_signals)


def test_merge_log_replaces_same_date_and_display():
    existing = [
        '{"date": "2026-06-26", "display": "AAA", "direction": "LONG"}',
        '{"date": "2026-06-27", "display": "AAA", "direction": "LONG"}',
    ]
    new = ['{"date": "2026-06-27", "display": "AAA", "direction": "SHORT"}']
    merged = attach_signals._merge_log(existing, new)
    keys = [(json.loads(l)["date"], json.loads(l)["display"]) for l in merged]
    # genau eine (2026-06-27, AAA) Zeile, und es ist die neue SHORT-Zeile
    assert keys.count(("2026-06-27", "AAA")) == 1
    assert keys.count(("2026-06-26", "AAA")) == 1  # andere Tage bleiben erhalten
    new27 = [l for l in merged if json.loads(l)["date"] == "2026-06-27"][0]
    assert json.loads(new27)["direction"] == "SHORT"


def test_merge_log_no_existing_returns_new():
    new = ['{"date": "2026-06-27", "display": "BBB", "direction": "FLAT"}']
    assert attach_signals._merge_log([], new) == new


def test_merge_log_ignores_blank_and_bad_lines():
    existing = ["", "   ", "not-json"]
    new = ['{"date": "2026-06-27", "display": "CCC", "direction": "LONG"}']
    assert attach_signals._merge_log(existing, new) == new
