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
# resolve_symbol_trades — bias-flip exit
# --------------------------------------------------------------------------
def _sig(date, direction, entry=None, sl=None, tp=None, *, conviction=3,
         horizon_days=5, display="AAA", symbol="AAA", tp2=None, rr=2.0,
         entry_type="market"):
    s = {"date": date, "symbol": symbol, "display": display,
         "direction": direction, "conviction": conviction, "entry": entry,
         "stop_loss": sl, "take_profit": tp, "horizon_days": horizon_days,
         "rr": rr, "entry_type": entry_type}
    if tp2 is not None:
        s["take_profit_2"] = tp2
    return s


def test_flip_long_then_short_closes_at_flip_close():
    # LONG opens 01-01; SHORT signal on 01-03 flips it; no SL/TP hit before.
    signals = [
        _sig("2026-01-01", "LONG", 100.0, 95.0, 130.0, horizon_days=20),
        _sig("2026-01-03", "SHORT", 90.0, 95.0, 80.0, horizon_days=20),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 102),
        _bar("2026-01-03", 102, 106, 100, 104),  # flip day close=104
        _bar("2026-01-04", 104, 108, 101, 107),
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    long_trade = trades[0]
    assert long_trade["status"] == "flip"
    assert long_trade["exit_date"] == "2026-01-03"
    assert long_trade["exit_price"] == 104.0
    # realized_R = (104-100)/|100-95| = 0.8
    assert long_trade["realized_R"] == 0.8


def test_flip_to_flat_closes_when_flat_closes_true():
    signals = [
        _sig("2026-01-01", "LONG", 100.0, 95.0, 130.0, horizon_days=20),
        _sig("2026-01-03", "FLAT", None, None, None, horizon_days=20),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 102),
        _bar("2026-01-03", 102, 106, 100, 104),
        _bar("2026-01-04", 104, 108, 101, 107),
    )
    trades = portfolio.resolve_symbol_trades(signals, ts, flat_closes=True)
    assert trades[0]["status"] == "flip"
    assert trades[0]["exit_date"] == "2026-01-03"
    assert trades[0]["exit_price"] == 104.0


def test_flip_to_flat_ignored_when_flat_closes_false():
    # FLAT does not close; trade keeps scanning -> expired at horizon end.
    signals = [
        _sig("2026-01-01", "LONG", 100.0, 95.0, 130.0, horizon_days=2),
        _sig("2026-01-03", "FLAT", None, None, None, horizon_days=2),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 102),
        _bar("2026-01-03", 102, 106, 100, 104),
        _bar("2026-01-04", 104, 108, 101, 107),  # past horizon -> expired at 01-03
    )
    trades = portfolio.resolve_symbol_trades(signals, ts, flat_closes=False)
    assert trades[0]["status"] == "expired"
    assert trades[0]["exit_date"] == "2026-01-03"
    assert trades[0]["exit_price"] == 104.0


def test_sl_before_flip_wins():
    # SL on 01-02 happens before the SHORT flip on 01-03.
    signals = [
        _sig("2026-01-01", "LONG", 100.0, 95.0, 130.0, horizon_days=20),
        _sig("2026-01-03", "SHORT", 90.0, 95.0, 80.0, horizon_days=20),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 105, 94, 96),  # low 94 <= SL 95
        _bar("2026-01-03", 96, 106, 100, 104),
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert trades[0]["status"] == "sl"
    assert trades[0]["exit_date"] == "2026-01-02"
    assert trades[0]["exit_price"] == 95.0


def test_sl_on_flip_date_wins_over_flip():
    # SL is touched intraday on the SAME day as the opposing signal. The daily
    # signal is computed after the close, so the intraday SL happens first and
    # must win over the bias-flip.
    signals = [
        _sig("2026-01-01", "LONG", 100.0, 95.0, 130.0, horizon_days=20),
        _sig("2026-01-03", "SHORT", 90.0, 95.0, 80.0, horizon_days=20),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 102),
        _bar("2026-01-03", 102, 106, 94, 96),  # flip day, but low 94 <= SL 95
        _bar("2026-01-04", 96, 108, 101, 107),
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert trades[0]["status"] == "sl"
    assert trades[0]["exit_date"] == "2026-01-03"
    assert trades[0]["exit_price"] == 95.0
    assert trades[0]["realized_R"] == -1.0


def test_tp_before_flip_wins():
    signals = [
        _sig("2026-01-01", "LONG", 100.0, 95.0, 110.0, horizon_days=20),
        _sig("2026-01-03", "SHORT", 90.0, 95.0, 80.0, horizon_days=20),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 111, 99, 110),  # high 111 >= TP 110
        _bar("2026-01-03", 110, 112, 108, 111),
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert trades[0]["status"] == "tp"
    assert trades[0]["exit_date"] == "2026-01-02"
    assert trades[0]["exit_price"] == 110.0


def test_same_direction_signal_does_not_reset_position():
    # Second LONG on 01-03 must NOT change entry/SL/TP of the open position.
    signals = [
        _sig("2026-01-01", "LONG", 100.0, 95.0, 130.0, horizon_days=20),
        _sig("2026-01-03", "LONG", 200.0, 190.0, 260.0, horizon_days=20),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 102),
        _bar("2026-01-03", 102, 106, 100, 104),
        _bar("2026-01-04", 104, 108, 94, 96),  # low 94 <= original SL 95
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert trades[0]["entry"] == 100.0
    assert trades[0]["stop_loss"] == 95.0
    assert trades[0]["status"] == "sl"
    assert trades[0]["exit_price"] == 95.0


def test_reentry_after_flip_opens_new_position():
    # LONG closes via flip to SHORT on 01-03, and the SHORT opens a new trade.
    signals = [
        _sig("2026-01-01", "LONG", 100.0, 95.0, 130.0, horizon_days=20),
        _sig("2026-01-03", "SHORT", 104.0, 110.0, 90.0, horizon_days=20),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 102),
        _bar("2026-01-03", 102, 106, 100, 104),  # flip close 104
        _bar("2026-01-04", 104, 108, 101, 107),  # SHORT: high 108 >= SL 110? no
        _bar("2026-01-05", 107, 111, 100, 102),  # high 111 >= SL 110 -> sl
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert len(trades) == 2
    assert trades[0]["status"] == "flip"
    assert trades[1]["direction"] == "SHORT"
    assert trades[1]["date"] == "2026-01-03"
    assert trades[1]["entry"] == 104.0
    assert trades[1]["status"] == "sl"
    assert trades[1]["exit_price"] == 110.0


def test_no_future_bars_is_open():
    signals = [_sig("2026-01-01", "LONG", 100.0, 95.0, 130.0, horizon_days=5)]
    trades = portfolio.resolve_symbol_trades(signals, [])
    assert len(trades) == 1
    assert trades[0]["status"] == "open"
    assert trades[0]["exit_price"] is None
    assert trades[0]["realized_R"] is None


def test_single_signal_resolves_like_resolve_trade():
    signals = [_sig("2026-01-01", "LONG", 100.0, 95.0, 110.0, horizon_days=5)]
    ts = _ts(
        _bar("2026-01-02", 100, 102, 99, 101),
        _bar("2026-01-03", 101, 111, 100, 110),  # TP
        _bar("2026-01-04", 110, 112, 108, 111),
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert trades[0]["status"] == "tp"
    assert trades[0]["exit_price"] == 110.0
    assert trades[0]["exit_date"] == "2026-01-03"
    assert trades[0]["realized_R"] == 2.0


def test_flip_date_no_bar_uses_prior_close():
    # Flip signal on 01-04 (a missing bar / weekend); use most recent prior close.
    signals = [
        _sig("2026-01-01", "LONG", 100.0, 95.0, 130.0, horizon_days=20),
        _sig("2026-01-04", "SHORT", 90.0, 95.0, 80.0, horizon_days=20),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 102),
        _bar("2026-01-03", 102, 106, 100, 103),  # prior bar close=103
        _bar("2026-01-05", 103, 108, 101, 107),  # next bar after flip date
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert trades[0]["status"] == "flip"
    assert trades[0]["exit_date"] == "2026-01-04"
    assert trades[0]["exit_price"] == 103.0


def test_actionable_after_non_actionable_first_signal():
    # First signal FLAT (not actionable) -> no open; later LONG opens.
    signals = [
        _sig("2026-01-01", "FLAT", None, None, None, horizon_days=20),
        _sig("2026-01-02", "LONG", 100.0, 95.0, 110.0, horizon_days=20),
    ]
    ts = _ts(
        _bar("2026-01-03", 100, 111, 99, 110),  # TP
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert len(trades) == 1
    assert trades[0]["direction"] == "LONG"
    assert trades[0]["status"] == "tp"


# --------------------------------------------------------------------------
# resolve_symbol_trades — at-most-one-open-position invariant (60-vs-30 bug)
# --------------------------------------------------------------------------
def test_two_consecutive_long_signals_unresolved_is_one_open_trade():
    # THE 60-vs-30 bug: day1 LONG never resolves (no bar after day2), then a
    # day2 LONG arrives. The open position must HOLD, not open a second trade.
    signals = [
        _sig("2026-01-01", "LONG", 100.0, 95.0, 130.0, horizon_days=20),
        _sig("2026-01-02", "LONG", 100.0, 95.0, 130.0, horizon_days=20),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 102),  # only one bar, none after day2
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert len(trades) == 1
    assert trades[0]["status"] == "open"
    assert trades[0]["entry"] == 100.0
    assert trades[0]["stop_loss"] == 95.0


def test_three_consecutive_long_signals_unresolved_is_one_open_trade():
    signals = [
        _sig("2026-01-01", "LONG", 100.0, 95.0, 130.0, horizon_days=20),
        _sig("2026-01-02", "LONG", 100.0, 95.0, 130.0, horizon_days=20),
        _sig("2026-01-03", "LONG", 100.0, 95.0, 130.0, horizon_days=20),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 102),
        _bar("2026-01-03", 102, 106, 100, 104),
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert len(trades) == 1
    assert trades[0]["status"] == "open"


def test_unresolved_long_then_short_flips_then_one_open():
    # day1 LONG never resolves before day2; day2 SHORT flips it closed, then
    # the SHORT opens (and stays open). At most one open position at the end.
    signals = [
        _sig("2026-01-01", "LONG", 100.0, 95.0, 130.0, horizon_days=20),
        _sig("2026-01-02", "SHORT", 102.0, 110.0, 80.0, horizon_days=20),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 102),  # flip day close=102, no bar after
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    # day1 LONG flips closed at the day2 bar (it was filled/market).
    assert trades[0]["direction"] == "LONG"
    assert trades[0]["status"] == "flip"
    assert trades[0]["exit_date"] == "2026-01-02"
    # day2 SHORT opens; with no bar after day2 it stays open.
    short_trades = [t for t in trades if t["direction"] == "SHORT"]
    assert len(short_trades) == 1
    assert short_trades[0]["status"] == "open"
    # invariant: at most one open position at the end.
    assert sum(1 for t in trades if t["status"] == "open") <= 1


def test_long_tp_before_day2_then_day2_opens_sequentially():
    # day1 LONG fills + hits TP on a bar before day2; THEN day2 LONG opens a
    # new position sequentially (not concurrently). One open at the end.
    signals = [
        _sig("2026-01-01", "LONG", 100.0, 95.0, 104.0, horizon_days=20),
        _sig("2026-01-03", "LONG", 110.0, 105.0, 130.0, horizon_days=20),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 105, 99, 104),  # high 105 >= TP 104 -> tp, before day2
        _bar("2026-01-03", 104, 108, 101, 107),  # day2 opens here
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert len(trades) == 2
    assert trades[0]["status"] == "tp"
    assert trades[0]["exit_date"] == "2026-01-02"
    assert trades[1]["date"] == "2026-01-03"
    assert trades[1]["entry"] == 110.0
    assert trades[1]["status"] == "open"
    assert sum(1 for t in trades if t["status"] == "open") <= 1


def test_simulate_open_count_one_per_symbol_all_open():
    # Build the all-open 2-day scenario for many symbols and confirm
    # open_count == number of symbols (not 2x).
    n_symbols = 30
    ts = _ts(_bar("2026-01-02", 100, 105, 99, 102))  # no bar after day2
    all_trades = []
    for k in range(n_symbols):
        sym = f"S{k:03d}"
        signals = [
            _sig("2026-01-01", "LONG", 100.0, 95.0, 130.0, horizon_days=20,
                 symbol=sym, display=sym),
            _sig("2026-01-02", "LONG", 100.0, 95.0, 130.0, horizon_days=20,
                 symbol=sym, display=sym),
        ]
        all_trades.extend(portfolio.resolve_symbol_trades(signals, ts))
    res = portfolio.simulate(all_trades)
    assert res["summary"]["open_count"] == n_symbols


# --------------------------------------------------------------------------
# resolve_symbol_trades — entry-fill modeling (phantom-win regression)
# --------------------------------------------------------------------------
def test_pullback_short_entry_above_price_never_filled_is_no_fill():
    # THE phantom-win bug: SHORT pullback, entry above price, TP basically at
    # the current price. Future bars never trade UP to the entry, so the
    # position is never filled -> "no_fill", no P&L.
    signals = [
        _sig("2026-01-01", "SHORT", entry=66276.0, sl=70281.0, tp=60269.0,
             horizon_days=3, entry_type="pullback"),
    ]
    # Enough bars to exhaust the horizon; high never reaches the entry (66276),
    # so the SHORT is never filled even though TP sits at the current price.
    ts = _ts(
        _bar("2026-01-02", 60200, 60500, 59900, 60100),  # high never >= 66276
        _bar("2026-01-03", 60100, 60400, 59800, 60000),
        _bar("2026-01-04", 60000, 60300, 59700, 59950),
        _bar("2026-01-05", 59950, 60200, 59600, 59800),  # past horizon
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert trades[0]["status"] == "no_fill"
    assert trades[0]["realized_R"] is None
    assert trades[0]["exit_price"] is None


def test_pullback_long_fills_then_hits_tp():
    # LONG pullback, entry below price. A later bar dips to entry (fill), then a
    # subsequent bar hits TP -> "tp", realized_R = +R.
    signals = [
        _sig("2026-01-01", "LONG", entry=98.0, sl=94.0, tp=104.0,
             horizon_days=20, entry_type="pullback"),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 101, 99, 100),     # no fill (low 99 > 98)
        _bar("2026-01-03", 100, 100, 97, 99),      # low 97 <= 98 -> FILL here
        _bar("2026-01-04", 99, 105, 98, 104),      # high 105 >= TP 104 -> tp
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert trades[0]["status"] == "tp"
    assert trades[0]["exit_price"] == 104.0
    assert trades[0]["exit_date"] == "2026-01-04"
    # realized_R = (104-98)/|98-94| = 6/4 = 1.5
    assert trades[0]["realized_R"] == 1.5


def test_pullback_no_same_bar_sl_tp_as_fill():
    # The fill bar itself must NOT be checked for SL/TP (no same-bar look-ahead).
    # Bar 01-03 fills (low<=entry) AND its high >= TP, but TP must only count on
    # a STRICTLY later bar.
    signals = [
        _sig("2026-01-01", "LONG", entry=98.0, sl=94.0, tp=104.0,
             horizon_days=20, entry_type="pullback"),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 101, 99, 100),
        _bar("2026-01-03", 99, 105, 97, 100),   # fills (97<=98) AND high 105>=104
        _bar("2026-01-04", 100, 101, 99, 100),  # nothing -> still open after fill
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    # TP on the fill bar is ignored; later bars don't hit TP/SL -> open.
    assert trades[0]["status"] == "open"
    assert trades[0]["realized_R"] is None


def test_pullback_not_reached_within_horizon_is_no_fill():
    signals = [
        _sig("2026-01-01", "LONG", entry=90.0, sl=86.0, tp=100.0,
             horizon_days=2, entry_type="pullback"),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 101, 95, 99),   # low 95 > entry 90 -> no fill
        _bar("2026-01-03", 99, 100, 94, 98),    # low 94 > 90 -> no fill
        _bar("2026-01-04", 98, 99, 89, 90),     # dips to 89 but past horizon
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert trades[0]["status"] == "no_fill"
    assert trades[0]["realized_R"] is None


def test_market_entry_hits_tp_unchanged():
    # market entry fills immediately at the signal date; SL/TP on later bars.
    signals = [
        _sig("2026-01-01", "LONG", entry=100.0, sl=95.0, tp=110.0,
             horizon_days=5, entry_type="market"),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 102, 99, 101),
        _bar("2026-01-03", 101, 111, 100, 110),  # high 111 >= TP 110 -> tp
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert trades[0]["status"] == "tp"
    assert trades[0]["exit_price"] == 110.0
    assert trades[0]["realized_R"] == 2.0


def test_pending_pullback_flip_before_fill_is_no_fill():
    # A flip signal arrives while the pullback is still PENDING (unfilled).
    # The trade was never real -> cancelled as "no_fill".
    signals = [
        _sig("2026-01-01", "LONG", entry=90.0, sl=86.0, tp=100.0,
             horizon_days=20, entry_type="pullback"),
        _sig("2026-01-03", "SHORT", entry=100.0, sl=105.0, tp=90.0,
             horizon_days=20, entry_type="market"),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 101, 95, 99),   # never dips to 90
        _bar("2026-01-03", 99, 102, 96, 100),   # flip day; entry never reached
        _bar("2026-01-04", 100, 103, 99, 102),
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert trades[0]["status"] == "no_fill"
    assert trades[0]["realized_R"] is None
    # the SHORT (market) opens after the cancel
    assert any(t["direction"] == "SHORT" for t in trades)


def test_default_entry_type_market_backward_compat():
    # Log entries without entry_type default to "market" (immediate fill).
    sig = {"date": "2026-01-01", "symbol": "AAA", "display": "AAA",
           "direction": "LONG", "conviction": 3, "entry": 100.0,
           "stop_loss": 95.0, "take_profit": 110.0, "horizon_days": 5}
    ts = _ts(
        _bar("2026-01-02", 100, 111, 99, 110),  # high 111 >= TP -> tp
    )
    trades = portfolio.resolve_symbol_trades([sig], ts)
    assert trades[0]["status"] == "tp"


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


def test_simulate_excludes_no_fill_from_stats():
    # no_fill trades are NOT trades: excluded from wins/closed_count/win_rate
    # and the equity curve. One real TP win + one no_fill.
    trades = [
        _trade("AAA", "LONG", 100.0, 95.0, 110.0, "tp",
               "2026-01-05", 110.0, 2.0, date="2026-01-01"),
        _trade("NOF", "SHORT", 66276.0, 70281.0, 60269.0, "no_fill",
               None, None, None, date="2026-01-02"),
    ]
    res = portfolio.simulate(trades)
    s = res["summary"]
    assert s["closed_count"] == 1   # only the real TP
    assert s["wins"] == 1
    assert s["win_rate"] == 1.0
    assert s["open_count"] == 0     # no_fill is NOT open either
    assert s.get("no_fill_count") == 1
    # equity curve: start + one close = 2 points (no_fill contributes nothing)
    assert len(res["equity_curve"]) == 2
    # no_fill must not appear in closed or open lists
    assert all(c["symbol"] != "NOF" for c in res["closed"])
    assert all(o["symbol"] != "NOF" for o in res["open"])


def test_simulate_ignores_flat_and_missing_sl():
    trades = [
        _trade("FLAT1", "FLAT", None, None, None, "none",
               None, None, None, date="2026-01-01"),
    ]
    res = portfolio.simulate(trades)
    assert res["summary"]["open_count"] == 0
    assert res["summary"]["closed_count"] == 0


def test_simulate_open_unrealized_pct_from_current_prices():
    # Offene Positionen erhalten current_price + unrealized_pct aus
    # current_prices. LONG: (akt-entry)/entry*100; SHORT: (entry-akt)/entry*100.
    trades = [
        _trade("LNG", "LONG", 100.0, 95.0, 110.0, "open",
               None, None, None, date="2026-01-01"),
        _trade("SHT", "SHORT", 200.0, 210.0, 180.0, "open",
               None, None, None, date="2026-01-02"),
    ]
    res = portfolio.simulate(trades, current_prices={"LNG": 105.0, "SHT": 190.0})
    by = {o["symbol"]: o for o in res["open"]}
    assert by["LNG"]["current_price"] == 105.0
    assert by["LNG"]["unrealized_pct"] == 5.0   # (105-100)/100*100
    assert by["SHT"]["current_price"] == 190.0
    assert by["SHT"]["unrealized_pct"] == 5.0   # (200-190)/200*100 (SHORT im Plus)


def test_simulate_open_unrealized_pct_short_in_loss():
    # SHORT, Kurs steigt ueber Entry -> unrealized_pct negativ.
    trades = [
        _trade("SHT", "SHORT", 200.0, 210.0, 180.0, "open",
               None, None, None, date="2026-01-02"),
    ]
    res = portfolio.simulate(trades, current_prices={"SHT": 206.0})
    o = res["open"][0]
    assert o["current_price"] == 206.0
    assert o["unrealized_pct"] == -3.0   # (200-206)/200*100


def test_simulate_open_unrealized_pct_missing_price_is_none():
    # Ohne current_prices (oder fehlendem Symbol) bleiben die Felder None.
    trades = [
        _trade("LNG", "LONG", 100.0, 95.0, 110.0, "open",
               None, None, None, date="2026-01-01"),
    ]
    res = portfolio.simulate(trades)
    o = res["open"][0]
    assert o["current_price"] is None
    assert o["unrealized_pct"] is None


# --- Phantom-Win-Regression: pending Pullback zeigt KEINEN unrealisierten P&L ---

def test_resolve_open_unfilled_pullback_marks_filled_false():
    # LONG-Pullback, Entry unter Kurs, nie erreicht, Horizont NICHT
    # ausgeschoepft -> status "open" (koennte spaeter fuellen), aber die Position
    # ist NICHT im Markt -> filled == False (pending).
    signals = [
        _sig("2026-01-01", "LONG", entry=90.0, sl=86.0, tp=100.0,
             horizon_days=20, entry_type="pullback"),
    ]
    ts = _ts(
        _bar("2026-01-02", 100, 101, 95, 99),   # low 95 > 90 -> kein Fill
        _bar("2026-01-03", 99, 100, 96, 98),    # low 96 > 90 -> kein Fill
    )
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert trades[0]["status"] == "open"
    assert trades[0]["filled"] is False


def test_resolve_market_open_marks_filled_true():
    # Market-Entry ist sofort gefuellt -> filled True, auch wenn noch offen.
    signals = [
        _sig("2026-01-01", "LONG", entry=100.0, sl=95.0, tp=200.0,
             horizon_days=20, entry_type="market"),
    ]
    ts = _ts(_bar("2026-01-02", 100, 101, 99, 100))
    trades = portfolio.resolve_symbol_trades(signals, ts)
    assert trades[0]["status"] == "open"
    assert trades[0]["filled"] is True


def test_simulate_pending_pullback_has_no_unrealized_pct():
    # Kernfix: eine offene, noch NICHT gefuellte Pullback-Position (filled False)
    # ist kein echter Trade -> pending True, KEIN unrealized_pct (Phantom-Gewinn).
    pending = {
        "symbol": "PB", "display": "PB", "date": "2026-01-01",
        "direction": "LONG", "conviction": 3, "entry": 90.0,
        "stop_loss": 86.0, "take_profit": 100.0, "rr": 2.0,
        "horizon_days": 20, "status": "open", "exit_date": None,
        "exit_price": None, "realized_R": None, "filled": False,
    }
    res = portfolio.simulate([pending], current_prices={"PB": 110.0})
    o = res["open"][0]
    assert o["pending"] is True
    assert o["current_price"] == 110.0   # Kurs darf informativ bleiben
    assert o["unrealized_pct"] is None    # aber KEIN Phantom-P&L


def test_simulate_filled_open_shows_unrealized_pct_and_pending_false():
    filled = {
        "symbol": "MK", "display": "MK", "date": "2026-01-01",
        "direction": "LONG", "conviction": 3, "entry": 100.0,
        "stop_loss": 95.0, "take_profit": 200.0, "rr": 2.0,
        "horizon_days": 20, "status": "open", "exit_date": None,
        "exit_price": None, "realized_R": None, "filled": True,
    }
    res = portfolio.simulate([filled], current_prices={"MK": 110.0})
    o = res["open"][0]
    assert o["pending"] is False
    assert o["unrealized_pct"] == 10.0
