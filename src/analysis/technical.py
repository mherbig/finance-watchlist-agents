# src/analysis/technical.py
"""Deterministischer Precompute (Spur A): Indikatoren & Level aus einer Zeitreihe.

Reine Funktion ohne Seiteneffekte. Eingabe ist die rohe `time_series` aus der
Daten-Schicht (neueste zuerst, String-Werte, mindestens `close` je Bar; optional
`high`/`low`). Intern wird oldest-first gerechnet.
"""
from __future__ import annotations


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sma(values, period):
    """Simple Moving Average der letzten `period` Werte (oldest-first Liste)."""
    if len(values) < period:
        return None
    return round(sum(values[-period:]) / period, 4)


def _ema_series(values, period):
    """EMA als Liste gleicher Laenge (oldest-first). Seed = SMA der ersten `period`."""
    if len(values) < period:
        return None
    k = 2.0 / (period + 1.0)
    ema = sum(values[:period]) / period
    out = [None] * (period - 1)
    out.append(ema)
    for v in values[period:]:
        ema = (v - ema) * k + ema
        out.append(ema)
    return out


def _rsi14(closes):
    """Standard-RSI(14) mit einfachem Durchschnitt der Gains/Losses. <15 Bars -> None."""
    if len(closes) < 15:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    window = deltas[-14:]
    gains = [d for d in window if d > 0]
    losses = [-d for d in window if d < 0]
    avg_gain = sum(gains) / 14.0
    avg_loss = sum(losses) / 14.0
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else None
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def _macd(closes):
    """MACD = EMA12 - EMA26, Signal = EMA9 des MACD, Hist = MACD - Signal. <26 Bars -> None."""
    if len(closes) < 26:
        return None
    ema12 = _ema_series(closes, 12)
    ema26 = _ema_series(closes, 26)
    macd_line = []
    for a, b in zip(ema12, ema26):
        macd_line.append(None if (a is None or b is None) else a - b)
    valid = [m for m in macd_line if m is not None]
    if len(valid) < 9:
        return None
    signal_series = _ema_series(valid, 9)
    if signal_series is None or signal_series[-1] is None:
        return None
    macd_val = valid[-1]
    signal_val = signal_series[-1]
    return {
        "macd": round(macd_val, 4),
        "signal": round(signal_val, 4),
        "hist": round(macd_val - signal_val, 4),
    }


def _atr14(highs, lows, closes):
    """ATR(14) als einfacher Durchschnitt der True Range. Braucht high&low und >=15 Bars."""
    if highs is None or lows is None:
        return None
    if len(closes) < 15:
        return None
    trs = []
    for i in range(1, len(closes)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]
        if high is None or low is None:
            return None
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if len(trs) < 14:
        return None
    return round(sum(trs[-14:]) / 14.0, 4)


def _weekly_block(bars: list[dict]) -> dict:
    """Wochentrend aus Tagesbars (oldest-first): letzter Close je ISO-Woche.

    up:   letzter Wochenschluss > SMA10(Wochen) und SMA10 steigend
    down: letzter Wochenschluss < SMA10(Wochen) und SMA10 fallend
    sonst side (auch bei < 12 Wochen Daten).
    """
    import datetime
    weekly: dict[tuple, float] = {}
    order: list[tuple] = []
    for b in bars:
        dt = str(b.get("datetime") or "")[:10]
        c = _to_float(b.get("close"))
        if c is None or len(dt) != 10:
            continue
        try:
            iso = datetime.date.fromisoformat(dt).isocalendar()
        except ValueError:
            continue
        key = (iso[0], iso[1])
        if key not in weekly:
            order.append(key)
        weekly[key] = c  # letzter Close der Woche gewinnt (oldest-first)
    closes = [weekly[k] for k in order]
    n = len(closes)
    trend = "side"
    if n >= 12:
        sma_now = _sma(closes, 10)
        sma_prev = _sma(closes[:-1], 10)
        last = closes[-1]
        if sma_now is not None and sma_prev is not None:
            if last > sma_now and sma_now > sma_prev:
                trend = "up"
            elif last < sma_now and sma_now < sma_prev:
                trend = "down"
    return {"trend": trend, "weeks": n,
            "last_close": closes[-1] if closes else None}


def _volume_ratio(bars: list[dict]):
    """Letztes Volumen / Schnitt der 20 VORHERIGEN Bars (None ohne Daten)."""
    vols = [_to_float(b.get("volume")) for b in bars]
    vols = [v for v in vols if v is not None and v > 0]
    if len(vols) < 2:
        return None
    prior = vols[-21:-1] if len(vols) > 20 else vols[:-1]
    avg = sum(prior) / len(prior) if prior else None
    if not avg:
        return None
    return round(vols[-1] / avg, 2)


def compute_technical(time_series: list[dict]) -> dict:
    """Berechnet Indikatoren/Level aus der rohen time_series (neueste zuerst)."""
    # oldest-first arbeiten
    bars = list(reversed(time_series or []))

    closes = [_to_float(b.get("close")) for b in bars]
    closes = [c for c in closes if c is not None]

    has_hl = bool(bars) and all(("high" in b and "low" in b) for b in bars)
    highs = [_to_float(b.get("high")) for b in bars] if has_hl else None
    lows = [_to_float(b.get("low")) for b in bars] if has_hl else None

    last_close = closes[-1] if closes else None
    if len(closes) >= 2 and closes[-2] != 0:
        change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100.0
    else:
        change_pct = 0.0

    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    rsi14 = _rsi14(closes)
    macd = _macd(closes)
    atr14 = _atr14(highs, lows, closes)

    # 52-Wochen-Fenster (letzte min(252, len) Bars)
    if closes:
        window = closes[-min(252, len(closes)):]
        high_52w = max(window)
        low_52w = min(window)
        pct_from_high = round((last_close - high_52w) / high_52w * 100.0, 2) if high_52w else 0.0
        pct_from_low = round((last_close - low_52w) / low_52w * 100.0, 2) if low_52w else 0.0
    else:
        high_52w = None
        low_52w = None
        pct_from_high = 0.0
        pct_from_low = 0.0

    # Trend
    if last_close is not None and sma20 is not None and sma50 is not None and last_close > sma20 > sma50:
        trend = "up"
    elif last_close is not None and sma20 is not None and sma50 is not None and last_close < sma20 < sma50:
        trend = "down"
    else:
        trend = "side"

    # Bias
    if trend == "up" and (rsi14 is None or rsi14 < 70):
        bias = "bullish"
    elif trend == "down" and (rsi14 is None or rsi14 > 30):
        bias = "bearish"
    else:
        bias = "neutral"

    # Level: Hoch/Tief der letzten 20 Bars
    levels = []
    if closes:
        last20 = closes[-min(20, len(closes)):]
        levels = [
            {"type": "resistance", "price": round(max(last20), 4)},
            {"type": "support", "price": round(min(last20), 4)},
        ]

    return {
        "last_close": last_close,
        "change_pct": change_pct,
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "rsi14": rsi14,
        "macd": macd,
        "atr14": atr14,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "pct_from_high": pct_from_high,
        "pct_from_low": pct_from_low,
        "trend": trend,
        "bias": bias,
        "levels": levels,
        "weekly": _weekly_block(bars),
        "volume_ratio": _volume_ratio(bars),
    }
