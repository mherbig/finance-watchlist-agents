"""TDD-Tests fuer src/analysis/report.build_report / build_index."""
from src.analysis.report import build_report, build_index


def _raw_available():
    closes = [float(100 + i) for i in range(60)]
    bars = []
    for i, c in enumerate(closes):
        bars.append({
            "datetime": f"2026-01-{i + 1:02d}",
            "open": str(c), "high": str(c + 1), "low": str(c - 1),
            "close": str(c), "volume": "1000",
        })
    time_series = list(reversed(bars))
    return {
        "display": "APPLE", "td_symbol": "AAPL", "asset_class": "stock",
        "track": "fundamental", "date": "2026-06-26", "available": True,
        "error": None,
        "snapshot": {"price": 159.0, "change_pct": 0.63, "currency": "USD"},
        "time_series": time_series,
    }


def _raw_unavailable():
    return {
        "display": "BRENT", "td_symbol": "BRENT", "asset_class": "energy",
        "track": "technical", "date": "2026-06-26", "available": False,
        "error": "RuntimeError: no data",
        "snapshot": None, "time_series": [],
    }


def test_build_report_available_stock():
    rep = build_report(_raw_available(), "2026-06-26T22:31:00+00:00")

    assert rep["symbol"] == "AAPL"
    assert rep["display"] == "APPLE"
    assert rep["asset_class"] == "stock"
    assert rep["track"] == "fundamental"
    assert rep["date"] == "2026-06-26"
    assert rep["generated_at"] == "2026-06-26T22:31:00+00:00"
    assert rep["available"] is True
    assert rep["snapshot"]["price"] == 159.0
    assert rep["technical"] is not None
    assert rep["technical"]["trend"] in ("up", "down", "side")
    assert rep["fundamental"] is None
    assert isinstance(rep["headline"], str) and rep["headline"]
    assert rep["flags"] == []
    assert "Keine Anlageempfehlung" in rep["disclaimer"]


def test_build_report_unavailable():
    rep = build_report(_raw_unavailable(), "2026-06-26T22:31:00+00:00")

    assert rep["symbol"] == "BRENT"
    assert rep["available"] is False
    assert rep["technical"] is None
    assert rep["fundamental"] is None
    assert isinstance(rep["headline"], str)
    assert "Keine Anlageempfehlung" in rep["disclaimer"]


def test_build_report_headline_handles_none_rsi():
    raw = _raw_available()
    raw["time_series"] = raw["time_series"][:3]  # zu wenige Bars -> rsi None
    rep = build_report(raw, "2026-06-26T22:31:00+00:00")
    assert rep["technical"]["rsi14"] is None
    assert isinstance(rep["headline"], str) and rep["headline"]


def test_build_index_rows():
    reps = [
        build_report(_raw_available(), "2026-06-26T22:31:00+00:00"),
        build_report(_raw_unavailable(), "2026-06-26T22:31:00+00:00"),
    ]
    index = build_index(reps)
    assert len(index) == 2

    row = index[0]
    expected_keys = {"symbol", "display", "asset_class", "track", "date",
                     "available", "price", "change_pct", "trend", "rsi",
                     "bias", "headline"}
    assert set(row.keys()) == expected_keys
    assert row["display"] == "APPLE"
    assert row["price"] == 159.0
    assert row["trend"] in ("up", "down", "side")

    # unavailable row ist None-safe
    urow = index[1]
    assert urow["available"] is False
    assert urow["price"] is None
    assert urow["trend"] is None
    assert urow["rsi"] is None
    assert urow["bias"] is None
