"""Tests fuer src/analysis/whatif.py (Exit-Politik-Replay auf Baseline-Trades)."""
from src.analysis import whatif


def _bar(dt, o, h, l, c):
    return {"datetime": dt, "open": str(o), "high": str(h),
            "low": str(l), "close": str(c)}


def _ts(*bars):
    # newest-first, wie die Rohdaten.
    return list(reversed(list(bars)))


def _base_trade(**over):
    t = {
        "symbol": "AAA", "display": "AAA", "date": "2026-01-01",
        "direction": "LONG", "conviction": 3, "entry": 100.0,
        "stop_loss": 95.0, "take_profit": 200.0, "rr": 2.0,
        "horizon_days": 20, "status": "open", "exit_date": None,
        "exit_price": None, "realized_R": None, "filled": True,
    }
    t.update(over)
    return t


def test_trailing_stop_locks_in_profit():
    # 1R-Trailing: Hoechstschluss 120 -> Stop 115; Rueckfall auf 114 -> Exit 115.
    t = _base_trade()
    ts = _ts(
        _bar("2026-01-02", 100, 111, 101, 110),   # danach Stop = 110-5 = 105
        _bar("2026-01-03", 110, 121, 118, 120),   # danach Stop = 120-5 = 115
        _bar("2026-01-04", 120, 120, 114, 116),   # low 114 <= 115 -> Exit 115
    )
    r = whatif.rescan_exit(t, ts, {"trail_r": 1.0})
    assert r["status"] == "sl"
    assert r["exit_price"] == 115.0
    assert r["exit_date"] == "2026-01-04"
    assert r["realized_R"] == 3.0     # (115-100)/5


def test_breakeven_after_1r_prevents_loss():
    # Nach +1R (High >= 105) Stop auf Entry; spaeterer Ruecklauf -> Exit 100, R=0.
    t = _base_trade()
    ts = _ts(
        _bar("2026-01-02", 100, 106, 100, 104),   # +1R erreicht -> Stop = 100
        _bar("2026-01-03", 104, 104, 99, 100),    # low 99 <= 100 -> Exit 100
    )
    r = whatif.rescan_exit(t, ts, {"breakeven_after_r": 1.0})
    assert r["status"] == "sl"
    assert r["exit_price"] == 100.0
    assert r["realized_R"] == 0.0


def test_no_same_bar_stop_update():
    # Der Bar, der +1R erreicht, darf den Breakeven-Stop NICHT schon selbst
    # ausloesen (Update erst NACH dem Bar).
    t = _base_trade()
    ts = _ts(
        _bar("2026-01-02", 100, 106, 99.5, 104),  # high 106 UND low 99.5>95
        _bar("2026-01-03", 104, 105, 103, 104),
    )
    r = whatif.rescan_exit(t, ts, {"breakeven_after_r": 1.0})
    assert r["status"] == "open"                  # kein Exit: 99.5 > 95 im Bar 1,
                                                  # BE-Stop gilt erst ab Bar 2


def test_flip_boundary_respected():
    # Baseline-Flip am 01-03 (Close 104): Policy ohne Treffer exitet dort.
    t = _base_trade(status="flip", exit_date="2026-01-03", exit_price=104.0,
                    realized_R=0.8)
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 102),
        _bar("2026-01-03", 102, 106, 100, 104),
        _bar("2026-01-04", 104, 200, 104, 199),   # nach Flip irrelevant
    )
    r = whatif.rescan_exit(t, ts, {"trail_r": 5.0})
    assert r["status"] == "flip"
    assert r["exit_date"] == "2026-01-03"
    assert r["exit_price"] == 104.0


def test_summarize_policies():
    rows = [
        {"realized_R": 2.0, "status": "tp"},
        {"realized_R": -1.0, "status": "sl"},
        {"realized_R": None, "status": "open"},
    ]
    s = whatif.summarize(rows)
    assert s["resolved"] == 2
    assert s["wins"] == 1
    assert s["win_rate"] == 0.5
    assert s["total_R"] == 1.0
    assert s["avg_R"] == 0.5
