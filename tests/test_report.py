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
    assert "disclaimer" not in rep


def test_build_report_unavailable():
    rep = build_report(_raw_unavailable(), "2026-06-26T22:31:00+00:00")

    assert rep["symbol"] == "BRENT"
    assert rep["available"] is False
    assert rep["technical"] is None
    assert rep["fundamental"] is None
    assert isinstance(rep["headline"], str)
    assert "disclaimer" not in rep


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
                     "generated_at", "available", "price", "change_pct", "trend",
                     "rsi", "bias", "headline", "has_agent_analysis", "agents_run",
                     "direction", "conviction", "has_signal"}
    assert set(row.keys()) == expected_keys
    assert row["has_agent_analysis"] is False
    assert row["agents_run"] == []
    assert row["has_signal"] is False
    assert row["direction"] is None
    assert row["conviction"] is None
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


def _agent_block():
    return {
        "generated_at": "2026-06-26T22:00:00Z",
        "model": "claude-opus-4-8",
        "track": "fundamental",
        "agents_run": ["market-researcher", "earnings-reviewer"],
        "summary": "Synthese.",
        "sections": [{"agent": "market-researcher", "title": "Markt", "body": "x"}],
        "disclaimer": "Entwurf zur Pruefung. Keine Anlageempfehlung.",
    }


def test_build_report_carries_prior_agent_analysis():
    prior = build_report(_raw_available(), "2026-06-26T22:31:00+00:00")
    prior["agent_analysis"] = _agent_block()

    rep = build_report(_raw_available(), "2026-06-27T22:31:00+00:00", prior=prior)
    # Agent-Analyse wird unveraendert uebernommen, Refresh ueberschreibt sie nicht
    assert rep["agent_analysis"] == _agent_block()
    # uebrige Felder werden frisch gebaut
    assert rep["generated_at"] == "2026-06-27T22:31:00+00:00"


def test_build_report_without_prior_has_no_agent_analysis():
    rep = build_report(_raw_available(), "2026-06-26T22:31:00+00:00")
    assert "agent_analysis" not in rep

    # prior ohne agent_analysis fuegt nichts hinzu
    rep2 = build_report(_raw_available(), "2026-06-26T22:31:00+00:00", prior=rep)
    assert "agent_analysis" not in rep2


def _signal_block():
    return {
        "generated_at": "2026-06-27T00:00:00+00:00",
        "model": "claude-opus-4-8",
        "direction": "LONG",
        "conviction": 4,
        "entry_type": "market",
        "horizon_days": 10,
        "rationale": "test",
        "entry": 100.0,
        "stop_loss": 96.4,
        "take_profit": 107.2,
        "take_profit_2": 110.0,
        "rr": 2.0,
    }


def test_build_report_carries_prior_signal():
    prior = build_report(_raw_available(), "2026-06-26T22:31:00+00:00")
    prior["signal"] = _signal_block()

    rep = build_report(_raw_available(), "2026-06-27T22:31:00+00:00", prior=prior)
    assert rep["signal"] == _signal_block()
    assert rep["generated_at"] == "2026-06-27T22:31:00+00:00"


def test_build_report_without_prior_has_no_signal():
    rep = build_report(_raw_available(), "2026-06-26T22:31:00+00:00")
    assert "signal" not in rep
    rep2 = build_report(_raw_available(), "2026-06-26T22:31:00+00:00", prior=rep)
    assert "signal" not in rep2


def test_build_index_exposes_signal_flags():
    rep = build_report(_raw_available(), "2026-06-26T22:31:00+00:00")
    rep["signal"] = _signal_block()
    plain = build_report(_raw_unavailable(), "2026-06-26T22:31:00+00:00")

    index = build_index([rep, plain])
    assert index[0]["has_signal"] is True
    assert index[0]["direction"] == "LONG"
    assert index[0]["conviction"] == 4
    assert index[1]["has_signal"] is False
    assert index[1]["direction"] is None
    assert index[1]["conviction"] is None


def test_build_index_exposes_agent_flags():
    rep = build_report(_raw_available(), "2026-06-26T22:31:00+00:00")
    rep["agent_analysis"] = _agent_block()
    plain = build_report(_raw_unavailable(), "2026-06-26T22:31:00+00:00")

    index = build_index([rep, plain])
    assert index[0]["has_agent_analysis"] is True
    assert index[0]["agents_run"] == ["market-researcher", "earnings-reviewer"]
    assert index[1]["has_agent_analysis"] is False
    assert index[1]["agents_run"] == []
