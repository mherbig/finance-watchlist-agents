# tests/test_portfolio.py
"""TDD-Tests fuer die Depot-Simulation (src/analysis/portfolio.py).

Keine Netzwerkaufrufe. Synthetische time_series und Log-Eintraege.
"""
from src.analysis import portfolio


# --------------------------------------------------------------------------
# position_size
# --------------------------------------------------------------------------
def test_position_size_basic():
    # risk 1000, distance |100-95| = 5 -> 200 units
    assert portfolio.position_size(1000.0, 100.0, 95.0) == 200.0


def test_position_size_rounds_to_4_decimals():
    # risk 100, distance 0.3 -> 333.3333...
    assert portfolio.position_size(100.0, 1.0, 0.7) == round(100.0 / 0.3, 4)


def test_position_size_none_on_missing():
    assert portfolio.position_size(1000.0, None, 95.0) is None
    assert portfolio.position_size(1000.0, 100.0, None) is None


def test_position_size_none_on_zero_distance():
    assert portfolio.position_size(1000.0, 100.0, 100.0) is None


# --------------------------------------------------------------------------
# resolve_trade
# --------------------------------------------------------------------------
def _bar(dt, o, h, l, c):
    return {"datetime": dt, "open": str(o), "high": str(h),
            "low": str(l), "close": str(c)}


def _ts(*bars):
    # newest-first, wie die Rohdaten.
    return list(reversed(list(bars)))


def test_resolve_long_hits_tp():
    log = {"date": "2026-01-01", "direction": "LONG", "entry": 100.0,
           "stop_loss": 95.0, "take_profit": 110.0, "horizon_days": 5}
    ts = _ts(
        _bar("2026-01-02", 100, 102, 99, 101),
        _bar("2026-01-03", 101, 111, 100, 110),  # high 111 >= TP 110
        _bar("2026-01-04", 110, 112, 108, 111),
    )
    out = portfolio.resolve_trade(log, ts)
    assert out["status"] == "tp"
    assert out["exit_price"] == 110.0
    assert out["exit_date"] == "2026-01-03"
    # realized_R = +1 * (110-100)/|100-95| = 10/5 = 2.0
    assert out["realized_R"] == 2.0


def test_resolve_long_hits_sl_first():
    log = {"date": "2026-01-01", "direction": "LONG", "entry": 100.0,
           "stop_loss": 95.0, "take_profit": 110.0, "horizon_days": 5}
    ts = _ts(
        _bar("2026-01-02", 100, 105, 94, 96),  # low 94 <= SL 95
        _bar("2026-01-03", 96, 111, 95, 110),
    )
    out = portfolio.resolve_trade(log, ts)
    assert out["status"] == "sl"
    assert out["exit_price"] == 95.0
    assert out["realized_R"] == -1.0


def test_resolve_short_hits_sl():
    log = {"date": "2026-01-01", "direction": "SHORT", "entry": 100.0,
           "stop_loss": 105.0, "take_profit": 90.0, "horizon_days": 5}
    ts = _ts(
        _bar("2026-01-02", 100, 106, 99, 104),  # high 106 >= SL 105
    )
    out = portfolio.resolve_trade(log, ts)
    assert out["status"] == "sl"
    assert out["exit_price"] == 105.0
    # realized_R = -1 * (105-100)/|100-105| = -1 * 5/5 = -1
    assert out["realized_R"] == -1.0


def test_resolve_short_hits_tp():
    log = {"date": "2026-01-01", "direction": "SHORT", "entry": 100.0,
           "stop_loss": 105.0, "take_profit": 90.0, "horizon_days": 5}
    ts = _ts(
        _bar("2026-01-02", 100, 101, 89, 92),  # low 89 <= TP 90
    )
    out = portfolio.resolve_trade(log, ts)
    assert out["status"] == "tp"
    assert out["exit_price"] == 90.0
    # realized_R = -1 * (90-100)/5 = -1 * -10/5 = 2.0
    assert out["realized_R"] == 2.0


def test_resolve_expired_uses_last_in_horizon_close():
    log = {"date": "2026-01-01", "direction": "LONG", "entry": 100.0,
           "stop_loss": 95.0, "take_profit": 130.0, "horizon_days": 2}
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 102),
        _bar("2026-01-03", 102, 106, 100, 104),  # last in-horizon close=104
        _bar("2026-01-04", 104, 108, 101, 107),  # exists past horizon -> expired
    )
    out = portfolio.resolve_trade(log, ts)
    assert out["status"] == "expired"
    assert out["exit_price"] == 104.0
    assert out["exit_date"] == "2026-01-03"
    # realized_R = (104-100)/5 = 0.8
    assert out["realized_R"] == 0.8


def test_resolve_open_when_not_enough_bars():
    log = {"date": "2026-01-01", "direction": "LONG", "entry": 100.0,
           "stop_loss": 95.0, "take_profit": 130.0, "horizon_days": 5}
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 102),
        _bar("2026-01-03", 102, 106, 100, 104),
    )
    out = portfolio.resolve_trade(log, ts)
    assert out["status"] == "open"
    assert out["realized_R"] is None
    assert out["exit_price"] is None


def test_resolve_only_bars_strictly_after_date():
    log = {"date": "2026-01-02", "direction": "LONG", "entry": 100.0,
           "stop_loss": 95.0, "take_profit": 110.0, "horizon_days": 5}
    ts = _ts(
        _bar("2026-01-01", 100, 120, 90, 110),  # before -> ignored
        _bar("2026-01-02", 100, 120, 90, 110),  # == date -> ignored
        _bar("2026-01-03", 100, 111, 99, 110),  # after -> TP
    )
    out = portfolio.resolve_trade(log, ts)
    assert out["status"] == "tp"
    assert out["exit_date"] == "2026-01-03"


def test_resolve_flat_is_none():
    log = {"date": "2026-01-01", "direction": "FLAT", "entry": None,
           "stop_loss": None, "take_profit": None, "horizon_days": 5}
    out = portfolio.resolve_trade(log, [])
    assert out["status"] == "none"
    assert out["realized_R"] is None


def test_resolve_missing_sl_is_none():
    log = {"date": "2026-01-01", "direction": "LONG", "entry": 100.0,
           "stop_loss": None, "take_profit": 110.0, "horizon_days": 5}
    out = portfolio.resolve_trade(log, [])
    assert out["status"] == "none"


# --------------------------------------------------------------------------
# simulate
# --------------------------------------------------------------------------
def _trade(symbol, direction, entry, sl, tp, status, exit_date, exit_price,
           realized_R, date, conviction=3, horizon_days=5, rr=2.0):
    return {
        "symbol": symbol, "display": symbol, "date": date,
        "direction": direction, "conviction": conviction,
        "entry": entry, "stop_loss": sl, "take_profit": tp, "rr": rr,
        "horizon_days": horizon_days,
        "status": status, "exit_date": exit_date,
        "exit_price": exit_price, "realized_R": realized_R,
    }


def test_simulate_synthetic_set():
    # One LONG hits TP (+2R), one SHORT hits SL (-1R), one open.
    trades = [
        _trade("AAA", "LONG", 100.0, 95.0, 110.0, "tp",
               "2026-01-05", 110.0, 2.0, date="2026-01-01"),
        _trade("BBB", "SHORT", 50.0, 55.0, 40.0, "sl",
               "2026-01-06", 55.0, -1.0, date="2026-01-02"),
        _trade("CCC", "LONG", 20.0, 18.0, 30.0, "open",
               None, None, None, date="2026-01-03"),
    ]
    res = portfolio.simulate(trades, start_equity=100_000.0, risk_pct=0.01)
    s = res["summary"]

    assert s["start_equity"] == 100_000.0
    assert s["closed_count"] == 2
    assert s["open_count"] == 1
    assert s["wins"] == 1
    assert s["losses"] == 1
    assert s["win_rate"] == 0.5

    # Event order by date:
    # AAA open 01-01: risk = 0.01*100000 = 1000
    # BBB open 01-02: risk = 0.01*100000 = 1000 (equity unchanged on open)
    # CCC open 01-03: open only, never closes
    # AAA close 01-05: pnl = 1000 * 2 = +2000 -> equity 102000
    # BBB close 01-06: pnl = 1000 * -1 = -1000 -> equity 101000
    assert s["total_pnl"] == 1000.0
    assert s["current_equity"] == 101_000.0
    assert round(s["return_pct"], 4) == 1.0  # +1%

    # closed entries
    closed = res["closed"]
    assert len(closed) == 2
    aaa = next(c for c in closed if c["symbol"] == "AAA")
    assert aaa["risk_amount"] == 1000.0
    assert aaa["pnl"] == 2000.0
    assert aaa["win"] is True
    bbb = next(c for c in closed if c["symbol"] == "BBB")
    assert bbb["pnl"] == -1000.0
    assert bbb["win"] is False

    # open entries with position size
    assert len(res["open"]) == 1
    ccc = res["open"][0]
    assert ccc["symbol"] == "CCC"
    assert ccc["risk_amount"] == 1000.0
    # units = 1000 / |20-18| = 500
    assert ccc["units"] == 500.0

    # equity_curve: start point + one per close event = 3 points
    assert len(res["equity_curve"]) == 3
    assert res["equity_curve"][0]["equity"] == 100_000.0
    assert res["equity_curve"][-1]["equity"] == 101_000.0

    # max_drawdown <= 0
    assert s["max_drawdown"] <= 0


def test_simulate_max_drawdown_negative_when_dips():
    # Win first (peak), then two losses -> drawdown below peak.
    trades = [
        _trade("AAA", "LONG", 100.0, 95.0, 110.0, "tp",
               "2026-01-02", 110.0, 2.0, date="2026-01-01"),
        _trade("BBB", "LONG", 100.0, 95.0, 110.0, "sl",
               "2026-01-03", 95.0, -1.0, date="2026-01-01"),
        _trade("CCC", "LONG", 100.0, 95.0, 110.0, "sl",
               "2026-01-04", 95.0, -1.0, date="2026-01-01"),
    ]
    res = portfolio.simulate(trades)
    assert res["summary"]["max_drawdown"] < 0


def test_simulate_empty():
    res = portfolio.simulate([])
    s = res["summary"]
    assert s["closed_count"] == 0
    assert s["open_count"] == 0
    assert s["win_rate"] == 0
    assert s["current_equity"] == 100_000.0
    assert s["max_drawdown"] <= 0
    assert len(res["equity_curve"]) == 1  # just the start point


def test_simulate_ignores_flat_and_missing_sl():
    trades = [
        _trade("FLAT1", "FLAT", None, None, None, "none",
               None, None, None, date="2026-01-01"),
    ]
    res = portfolio.simulate(trades)
    assert res["summary"]["open_count"] == 0
    assert res["summary"]["closed_count"] == 0
