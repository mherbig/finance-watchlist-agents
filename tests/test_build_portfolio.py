"""Tests fuer die Hilfsfunktionen in scripts/build_portfolio.py."""
import importlib.util
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "build_portfolio", _root / "scripts" / "build_portfolio.py")
build_portfolio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_portfolio)


def test_latest_close_returns_most_recent_close():
    # time_series neueste zuerst -> latest close ist der vom juengsten Datum.
    ts = [
        {"datetime": "2026-01-03", "open": "1", "high": "2",
         "low": "0.5", "close": "1.5"},
        {"datetime": "2026-01-02", "open": "1", "high": "2",
         "low": "0.5", "close": "1.2"},
    ]
    assert build_portfolio._latest_close(ts) == 1.5


def test_latest_close_unsorted_input():
    # Reihenfolge egal: es zaehlt das juengste Datum.
    ts = [
        {"datetime": "2026-01-01", "open": "1", "high": "2",
         "low": "0.5", "close": "1.0"},
        {"datetime": "2026-01-05", "open": "1", "high": "2",
         "low": "0.5", "close": "1.9"},
        {"datetime": "2026-01-03", "open": "1", "high": "2",
         "low": "0.5", "close": "1.5"},
    ]
    assert build_portfolio._latest_close(ts) == 1.9


def test_latest_close_empty_or_none_is_none():
    assert build_portfolio._latest_close([]) is None
    assert build_portfolio._latest_close(None) is None
