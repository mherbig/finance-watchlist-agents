"""TDD-Tests fuer src/analysis/technical.compute_technical."""
from src.analysis.technical import compute_technical


def _series_from_closes(closes):
    """Baut eine rohe time_series (neueste zuerst, String-Werte) aus Closes (aelteste zuerst)."""
    bars = []
    for i, c in enumerate(closes):
        bars.append({
            "datetime": f"2026-01-{i + 1:02d}",
            "open": str(c),
            "high": str(c + 1),
            "low": str(c - 1),
            "close": str(c),
            "volume": "1000",
        })
    # neueste zuerst
    return list(reversed(bars))


def test_strict_rising_series_is_up_trend_and_rsi_extreme():
    closes = [float(x) for x in range(100, 360)]  # streng steigend, 260 Bars
    ts = _series_from_closes(closes)
    out = compute_technical(ts)

    assert out["last_close"] == 359.0
    assert out["change_pct"] > 0
    assert out["trend"] == "up"
    # streng steigend -> RSI sehr hoch (>70) -> bias laut Spec NICHT bullish
    assert out["rsi14"] is not None
    assert out["rsi14"] > 90
    assert out["bias"] == "neutral"
    # SMAs vorhanden (genug Bars) und geordnet last > sma20 > sma50 > sma200
    assert out["sma20"] is not None and out["sma50"] is not None and out["sma200"] is not None
    assert out["last_close"] > out["sma20"] > out["sma50"] > out["sma200"]
    # MACD vorhanden
    assert out["macd"] is not None
    assert set(out["macd"].keys()) == {"macd", "signal", "hist"}
    # ATR vorhanden, da high/low present und >=15 Bars
    assert out["atr14"] is not None
    # 52w high/low
    assert out["high_52w"] == 359.0
    assert out["pct_from_high"] <= 0.0  # last == high -> 0 oder leicht negativ
    # Levels
    types = {lvl["type"] for lvl in out["levels"]}
    assert types == {"resistance", "support"}


def test_gentle_uptrend_with_pullback_is_bullish():
    # langfristiger Aufwaertstrend, aber zuletzt leichte Konsolidierung -> RSI < 70
    closes = [float(100 + i) for i in range(240)]
    # letzte 14 Bars: kleine Auf-/Ab-Bewegung um das Niveau, netto leicht hoch
    base = closes[-1]
    pullback = [base + d for d in [0.5, -0.3, 0.4, -0.2, 0.3, -0.1, 0.2,
                                   -0.1, 0.15, -0.05, 0.1, 0.0, 0.05, 0.1]]
    closes = closes + pullback
    ts = _series_from_closes(closes)
    out = compute_technical(ts)

    assert out["trend"] == "up"
    assert out["rsi14"] is not None
    assert out["rsi14"] < 70
    assert out["bias"] == "bullish"


def test_gentle_downtrend_with_bounce_is_bearish():
    closes = [float(360 - i) for i in range(240)]
    base = closes[-1]
    bounce = [base + d for d in [-0.5, 0.3, -0.4, 0.2, -0.3, 0.1, -0.2,
                                 0.1, -0.15, 0.05, -0.1, 0.0, -0.05, -0.1]]
    closes = closes + bounce
    ts = _series_from_closes(closes)
    out = compute_technical(ts)

    assert out["trend"] == "down"
    assert out["rsi14"] is not None
    assert out["rsi14"] > 30
    assert out["bias"] == "bearish"
    assert out["last_close"] < out["sma20"] < out["sma50"]


def test_flat_series_is_side_and_rsi_neutral():
    closes = [100.0] * 60
    ts = _series_from_closes(closes)
    out = compute_technical(ts)

    assert out["trend"] == "side"
    assert out["bias"] == "neutral"
    assert out["change_pct"] == 0.0
    # flach: keine Gewinne/Verluste -> RSI None oder ~50
    assert out["rsi14"] is None or 40 <= out["rsi14"] <= 60
    # SMAs gleich dem Niveau
    assert out["sma20"] == 100.0
    assert out["sma50"] == 100.0


def test_two_bars_change_pct_and_smas_none():
    ts = _series_from_closes([100.0, 110.0])
    out = compute_technical(ts)

    assert out["last_close"] == 110.0
    assert abs(out["change_pct"] - 10.0) < 1e-9
    assert out["sma20"] is None
    assert out["sma50"] is None
    assert out["sma200"] is None
    assert out["rsi14"] is None
    assert out["macd"] is None
    assert out["atr14"] is None
    assert out["trend"] == "side"
    assert out["bias"] == "neutral"


def test_single_bar_no_crash():
    ts = _series_from_closes([100.0])
    out = compute_technical(ts)
    assert out["last_close"] == 100.0
    assert out["change_pct"] == 0.0
    assert out["sma20"] is None


def test_empty_list_no_crash():
    out = compute_technical([])
    assert out["last_close"] is None or out["last_close"] == 0.0
    assert out["change_pct"] == 0.0
    assert out["sma20"] is None
    assert out["trend"] == "side"
    assert out["bias"] == "neutral"
    assert out["levels"] == [] or len(out["levels"]) == 2


def test_atr_none_when_no_high_low():
    closes = [float(x) for x in range(100, 140)]
    ts = _series_from_closes(closes)
    for bar in ts:
        bar.pop("high", None)
        bar.pop("low", None)
    out = compute_technical(ts)
    assert out["atr14"] is None
    # restliche Felder weiterhin berechenbar
    assert out["rsi14"] is not None


# --- C2 Weekly-Trend + C6 Volumen-Ratio -------------------------------------

def _series_weekly(closes_per_week, start="2025-01-06"):
    """Ein Bar je Woche (Montage), Closes aelteste zuerst, neueste zuerst raus."""
    import datetime
    d = datetime.date.fromisoformat(start)
    bars = []
    for i, c in enumerate(closes_per_week):
        day = d + datetime.timedelta(weeks=i)
        bars.append({"datetime": day.isoformat(), "open": str(c),
                     "high": str(c + 1), "low": str(c - 1), "close": str(c),
                     "volume": "1000"})
    return list(reversed(bars))


def test_weekly_trend_up_on_rising_weeks():
    ts = _series_weekly([float(100 + i) for i in range(30)])
    out = compute_technical(ts)
    assert out["weekly"]["trend"] == "up"
    assert out["weekly"]["weeks"] >= 20


def test_weekly_trend_down_on_falling_weeks():
    ts = _series_weekly([float(200 - i * 2) for i in range(30)])
    out = compute_technical(ts)
    assert out["weekly"]["trend"] == "down"


def test_weekly_trend_side_with_too_few_weeks():
    ts = _series_weekly([100.0, 101.0, 102.0])
    out = compute_technical(ts)
    assert out["weekly"]["trend"] == "side"


def test_volume_ratio_vs_prior_20_bars():
    closes = [100.0] * 25
    ts = _series_from_closes(closes)          # volume je Bar "1000"
    ts[0] = dict(ts[0], volume="3000")        # neuester Bar: 3x Volumen
    out = compute_technical(ts)
    assert out["volume_ratio"] == 3.0


def test_volume_ratio_none_without_volume():
    closes = [100.0] * 25
    ts = [{k: v for k, v in b.items() if k != "volume"}
          for b in _series_from_closes(closes)]
    out = compute_technical(ts)
    assert out["volume_ratio"] is None
