"""TDD-Tests fuer src/analysis/signal.py (deterministische SL/TP/Entry-Kernlogik).

Keine Netzwerkaufrufe. Die Agenten-JUDGMENT (direction/conviction/...) ist Eingabe;
die Zahlen werden deterministisch aus ATR + Support/Resistance berechnet.
"""
import pytest

from src.analysis.signal import (
    K_SL,
    R_TARGET,
    attach_signal,
    build_signal,
    compute_levels,
    validate_decision,
)


def _levels(supports, resistances):
    out = []
    for p in supports:
        out.append({"type": "support", "price": p})
    for p in resistances:
        out.append({"type": "resistance", "price": p})
    return out


# --- validate_decision ---------------------------------------------------

def _good_decision(**over):
    d = {
        "direction": "LONG",
        "conviction": 3,
        "entry_type": "market",
        "horizon_days": 10,
        "rationale": "Setup sieht gut aus.",
    }
    d.update(over)
    return d


def test_validate_decision_accepts_good():
    validate_decision(_good_decision())  # darf nicht werfen


@pytest.mark.parametrize("bad", [
    {"direction": "BUY"},
    {"direction": None},
    {"conviction": 0},
    {"conviction": 6},
    {"conviction": 3.0} if False else {"conviction": "3"},
    {"entry_type": "limit"},
    {"horizon_days": 0},
    {"horizon_days": -5},
    {"horizon_days": "10"},
    {"rationale": ""},
    {"rationale": "   "},
    {"rationale": None},
])
def test_validate_decision_rejects_bad_field(bad):
    with pytest.raises(ValueError):
        validate_decision(_good_decision(**bad))


# --- compute_levels: LONG ------------------------------------------------

def test_long_market_structure_stop():
    # price 100, atr 2. support bei 98 nahe genug -> Struktur-Stop sup-0.1*atr
    # atr_stop = 100 - 1.8*2 = 96.4. sup=98. sup-0.1*atr = 97.8.
    # 96.4 <= 97.8 < 100 -> stop = 97.8 (enger als ATR-Stop).
    r = compute_levels(100.0, 2.0, _levels([98.0], [110.0]),
                       "LONG", 3, "market")
    assert r["entry"] == 100.0
    assert r["stop_loss"] == 97.8
    risk = 100.0 - 97.8
    assert r["take_profit"] == round(100.0 + R_TARGET[3] * risk, 4)
    assert r["take_profit_2"] == 110.0
    assert r["rr"] == R_TARGET[3]


def test_long_market_atr_stop_no_nearby_support():
    # keine Support unter entry -> ATR-Stop
    r = compute_levels(100.0, 2.0, _levels([], [110.0]),
                       "LONG", 2, "market")
    atr_stop = round(100.0 - K_SL * 2.0, 4)
    assert r["entry"] == 100.0
    assert r["stop_loss"] == atr_stop  # 96.4
    risk = 100.0 - atr_stop
    assert r["take_profit"] == round(100.0 + R_TARGET[2] * risk, 4)
    assert r["take_profit_2"] == 110.0
    assert r["rr"] == R_TARGET[2]


def test_long_market_far_support_uses_atr_stop():
    # support 90 ist weiter weg als ATR-Stop 96.4 -> sup-0.1atr=89.8 < atr_stop,
    # Bedingung atr_stop <= struct < entry verletzt -> ATR-Stop bleibt.
    r = compute_levels(100.0, 2.0, _levels([90.0], [110.0]),
                       "LONG", 3, "market")
    assert r["stop_loss"] == round(100.0 - K_SL * 2.0, 4)  # 96.4


def test_long_pullback_entry_at_support():
    # pullback: entry = naechste Support unter price (max support < price) = 98
    r = compute_levels(100.0, 2.0, _levels([98.0, 90.0], [110.0]),
                       "LONG", 4, "pullback")
    assert r["entry"] == 98.0
    # atr_stop = 98 - 3.6 = 94.4. sup unter entry(98): max(90) = 90.
    # sup-0.1atr = 89.8. 94.4 <= 89.8? nein -> ATR-Stop 94.4.
    assert r["stop_loss"] == 94.4


def test_long_pullback_no_support_below_uses_price_minus_half_atr():
    # keine Support unter price -> entry = price - 0.5*atr = 100 - 1 = 99
    r = compute_levels(100.0, 2.0, _levels([], [110.0]),
                       "LONG", 3, "pullback")
    assert r["entry"] == 99.0


# --- compute_levels: SHORT -----------------------------------------------

def test_short_market_structure_stop():
    # price 100, atr 2. resistance 102 nahe. atr_stop = 100 + 3.6 = 103.6.
    # res = min(res > entry) = 102. res+0.1atr = 102.2.
    # entry(100) < 102.2 <= 103.6 -> stop = 102.2.
    r = compute_levels(100.0, 2.0, _levels([90.0], [102.0]),
                       "SHORT", 3, "market")
    assert r["entry"] == 100.0
    assert r["stop_loss"] == 102.2
    risk = 102.2 - 100.0
    assert r["take_profit"] == round(100.0 - R_TARGET[3] * risk, 4)
    assert r["take_profit_2"] == 90.0  # max(support < entry)
    assert r["rr"] == R_TARGET[3]


def test_short_market_atr_stop_no_nearby_resistance():
    r = compute_levels(100.0, 2.0, _levels([90.0], []),
                       "SHORT", 2, "market")
    atr_stop = round(100.0 + K_SL * 2.0, 4)  # 103.6
    assert r["stop_loss"] == atr_stop
    risk = atr_stop - 100.0
    assert r["take_profit"] == round(100.0 - R_TARGET[2] * risk, 4)
    assert r["take_profit_2"] == 90.0


def test_short_pullback_entry_at_resistance():
    # pullback: entry = naechste resistance ueber price (min res > price) = 102
    r = compute_levels(100.0, 2.0, _levels([90.0], [102.0, 110.0]),
                       "SHORT", 3, "pullback")
    assert r["entry"] == 102.0


def test_short_pullback_no_resistance_uses_price_plus_half_atr():
    r = compute_levels(100.0, 2.0, _levels([90.0], []),
                       "SHORT", 3, "pullback")
    assert r["entry"] == 101.0  # 100 + 0.5*2


# --- compute_levels: FLAT / leere Faelle ---------------------------------

def test_flat_all_none():
    r = compute_levels(100.0, 2.0, _levels([98.0], [110.0]),
                       "FLAT", 3, "market")
    assert r == {"entry": None, "stop_loss": None, "take_profit": None,
                 "take_profit_2": None, "rr": None}


def test_missing_atr_all_none():
    for atr in (None, 0, 0.0):
        r = compute_levels(100.0, atr, _levels([98.0], [110.0]),
                           "LONG", 3, "market")
        assert r == {"entry": None, "stop_loss": None, "take_profit": None,
                     "take_profit_2": None, "rr": None}


def test_missing_price_all_none():
    r = compute_levels(None, 2.0, _levels([98.0], [110.0]),
                       "LONG", 3, "market")
    assert all(v is None for v in r.values())


def test_conviction_5_rr_25():
    r = compute_levels(100.0, 2.0, _levels([], [110.0]),
                       "LONG", 5, "market")
    assert r["rr"] == 2.5
    assert R_TARGET[5] == 2.5


def test_no_resistance_take_profit_2_none():
    r = compute_levels(100.0, 2.0, _levels([], []),
                       "LONG", 3, "market")
    assert r["take_profit_2"] is None


# --- build_signal --------------------------------------------------------

def test_build_signal_long():
    decision = _good_decision(direction="LONG", conviction=4, entry_type="market")
    technical = {"atr14": 2.0, "levels": _levels([98.0], [110.0])}
    snapshot = {"price": 100.0}
    sig = build_signal(decision, technical, snapshot,
                       generated_at="2026-06-27T00:00:00+00:00", model="claude-opus-4-8")
    assert sig["generated_at"] == "2026-06-27T00:00:00+00:00"
    assert sig["model"] == "claude-opus-4-8"
    assert sig["direction"] == "LONG"
    assert sig["conviction"] == 4
    assert sig["entry_type"] == "market"
    assert sig["horizon_days"] == 10
    assert sig["rationale"] == "Setup sieht gut aus."
    assert sig["entry"] == 100.0
    assert isinstance(sig["stop_loss"], (int, float))
    assert isinstance(sig["take_profit"], (int, float))
    assert sig["rr"] == R_TARGET[4]


def test_build_signal_guards_none_technical_snapshot():
    decision = _good_decision(direction="LONG")
    sig = build_signal(decision, None, None,
                       generated_at="2026-06-27T00:00:00+00:00", model="m")
    assert sig["entry"] is None
    assert sig["stop_loss"] is None
    assert sig["take_profit"] is None
    assert sig["rr"] is None


def test_build_signal_validates():
    with pytest.raises(ValueError):
        build_signal({"direction": "BUY"}, None, None,
                     generated_at="x", model="m")


def test_build_signal_flat_all_none():
    decision = _good_decision(direction="FLAT")
    technical = {"atr14": 2.0, "levels": _levels([98.0], [110.0])}
    snapshot = {"price": 100.0}
    sig = build_signal(decision, technical, snapshot,
                       generated_at="t", model="m")
    assert sig["direction"] == "FLAT"
    assert sig["entry"] is None and sig["stop_loss"] is None


# --- attach_signal -------------------------------------------------------

def test_attach_signal_sets_only_signal_field():
    report = {"symbol": "AAPL", "technical": {"x": 1}, "snapshot": {"price": 1}}
    sig = {"direction": "LONG"}
    out = attach_signal(report, sig)
    assert out is report
    assert report["signal"] == sig
    # andere Felder unangetastet
    assert report["symbol"] == "AAPL"
    assert report["technical"] == {"x": 1}
