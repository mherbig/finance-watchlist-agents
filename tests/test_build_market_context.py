"""Tests fuer die Kontext-Aggregation in scripts/build_market_context.py."""
import importlib.util
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "build_market_context", _root / "scripts" / "build_market_context.py")
build_market_context = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_market_context)


def _raw(display, closes, asset_class="index"):
    import datetime
    start = datetime.date(2025, 6, 2)
    bars = []
    for i, c in enumerate(closes):
        day = start + datetime.timedelta(days=i)
        bars.append({"datetime": day.isoformat(), "open": str(c),
                     "high": str(c * 1.01), "low": str(c * 0.99),
                     "close": str(c), "volume": "1000"})
    return {"display": display, "asset_class": asset_class,
            "available": True, "time_series": list(reversed(bars))}


def test_context_contains_anchors_and_vol_regime():
    records = {
        "S&P500": _raw("S&P500", [float(100 + i) for i in range(60)]),
        "BTC/USD": _raw("BTC/USD", [float(300 - i) for i in range(60)],
                        asset_class="crypto"),
    }
    ctx = build_market_context._build_context(records)
    assert ctx["anchors"]["S&P500"]["trend"] == "up"
    assert ctx["anchors"]["BTC/USD"]["trend"] == "down"
    assert "change_pct" in ctx["anchors"]["S&P500"]
    assert ctx["vol_regime"]["median_atr_pct"] > 0
    assert ctx["vol_regime"]["symbols"] == 2


def test_context_skips_missing_series():
    records = {"S&P500": {"display": "S&P500", "available": False,
                          "time_series": []}}
    ctx = build_market_context._build_context(records)
    assert ctx["anchors"] == {}
    assert ctx["vol_regime"]["symbols"] == 0
