"""Backtest-Prototyp (C): prueft das ATR/Trend-Swing-Regelwerk auf Tagesbasis.

Kein Look-ahead: Signal am Schluss von Bar t -> Ausfuehrung Open t+1.
SL/TP intrabar ueber High/Low. Risiko 1% Kapital/Trade. Vergleich vs Buy & Hold.
Reine Diagnose - keine Anlageempfehlung, keine Order.
"""
from __future__ import annotations
import json
import urllib.parse
import urllib.request
import numpy as np
import pandas as pd

# --- Regelwerk-Parameter (hier tweaken) ---
SMA_FAST, SMA_SLOW, SMA_REGIME = 20, 50, 200
RSI_LEN = 14
ATR_LEN = 14
SL_ATR, TP_ATR = 1.5, 2.5          # SL = 1.5*ATR, TP = 2.5*ATR  -> R:R ~1.67
RSI_LONG = (40, 70)                 # Long nur in diesem RSI-Fenster
RSI_SHORT = (30, 60)
MAX_HOLD = 20                       # Zeit-Stop in Bars
RISK_FRAC = 0.01                    # 1% Kapital Risiko je Trade
INIT_EQUITY = 10_000.0

SYMBOLS = {                         # Anzeigename -> Yahoo-Symbol
    "GER40": "^GDAXI",
    "EUR/USD": "EURUSD=X",
    "BTC/USD": "BTC-USD",
}
ROUND_TRIP_COST = {                 # Friktion (Spread+Gebuehr) je Round-Trip, % vom Preis
    "GER40": 0.04, "EUR/USD": 0.02, "BTC/USD": 0.20,
}


def fetch_yahoo(symbol: str, rng: str = "10y") -> pd.DataFrame:
    enc = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}?range={rng}&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    res = data["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame({
        "ts": res["timestamp"],
        "open": q.get("open"), "high": q.get("high"),
        "low": q.get("low"), "close": q.get("close"),
    })
    df["date"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.date
    df = df.dropna(subset=["close"]).reset_index(drop=True)
    for col in ("open", "high", "low"):           # FX-Luecken: auf close zurueckfallen
        df[col] = df[col].fillna(df["close"])
    return df


def indicators(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"]
    df["sma_fast"] = c.rolling(SMA_FAST).mean()
    df["sma_slow"] = c.rolling(SMA_SLOW).mean()
    df["sma_reg"] = c.rolling(SMA_REGIME).mean()
    # RSI (Wilder)
    delta = c.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    ag = gain.ewm(alpha=1 / RSI_LEN, adjust=False).mean()
    al = loss.ewm(alpha=1 / RSI_LEN, adjust=False).mean()
    rs = ag / al.replace(0, np.nan)
    df["rsi"] = 100 - 100 / (1 + rs)
    # MACD 12/26/9
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9, adjust=False).mean()
    df["hist"] = macd - sig
    df["hist_prev"] = df["hist"].shift(1)
    # ATR (Wilder)
    pc = c.shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / ATR_LEN, adjust=False).mean()
    # Signale (auf Bar-Schluss)
    up = c > df["sma_reg"]
    dn = c < df["sma_reg"]
    cross_up = (df["hist"] > 0) & (df["hist_prev"] <= 0)
    cross_dn = (df["hist"] < 0) & (df["hist_prev"] >= 0)
    df["long_sig"] = up & cross_up & df["rsi"].between(*RSI_LONG)
    df["short_sig"] = dn & cross_dn & df["rsi"].between(*RSI_SHORT)
    return df


def backtest(df: pd.DataFrame, cost_pct: float) -> dict:
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    lo = df["low"].to_numpy(); c = df["close"].to_numpy()
    atr = df["atr"].to_numpy()
    long_sig = df["long_sig"].to_numpy(); short_sig = df["short_sig"].to_numpy()
    cross_up = ((df["hist"] > 0) & (df["hist_prev"] <= 0)).to_numpy()
    cross_dn = ((df["hist"] < 0) & (df["hist_prev"] >= 0)).to_numpy()

    start = SMA_REGIME + 1
    pos = None
    rs = []  # R-Multiples
    for i in range(start, len(df)):
        # 1) Einstieg (flat) auf Open[i] aus Signal[i-1]
        if pos is None and not np.isnan(atr[i - 1]):
            if long_sig[i - 1]:
                e = o[i]; risk = SL_ATR * atr[i - 1]
                pos = {"d": 1, "e": e, "sl": e - risk, "tp": e + TP_ATR * atr[i - 1],
                       "risk": risk, "held": 0}
            elif short_sig[i - 1]:
                e = o[i]; risk = SL_ATR * atr[i - 1]
                pos = {"d": -1, "e": e, "sl": e + risk, "tp": e - TP_ATR * atr[i - 1],
                       "risk": risk, "held": 0}
        if pos is None:
            continue
        # 2) Intrabar SL/TP auf Bar i
        exit_px = None
        if pos["d"] == 1:
            if lo[i] <= pos["sl"]:
                exit_px = pos["sl"]
            elif h[i] >= pos["tp"]:
                exit_px = pos["tp"]
        else:
            if h[i] >= pos["sl"]:
                exit_px = pos["sl"]
            elif lo[i] <= pos["tp"]:
                exit_px = pos["tp"]
        # 3) sonst: Gegensignal / Zeit-Stop auf Close[i]
        pos["held"] += 1
        if exit_px is None:
            flip = cross_dn[i] if pos["d"] == 1 else cross_up[i]
            if flip or pos["held"] >= MAX_HOLD:
                exit_px = c[i]
        if exit_px is not None:
            r = pos["d"] * (exit_px - pos["e"]) / pos["risk"]
            cost_r = (cost_pct / 100.0) * pos["e"] / pos["risk"]   # Friktion in R
            rs.append(r - cost_r)
            pos = None

    rs = np.array(rs)
    n = len(rs)
    if n == 0:
        return {"trades": 0}
    wins = rs[rs > 0]; losses = rs[rs <= 0]
    eq = INIT_EQUITY; curve = [eq]
    for r in rs:
        eq *= (1 + RISK_FRAC * r)
        curve.append(eq)
    curve = np.array(curve)
    peak = np.maximum.accumulate(curve)
    max_dd = ((curve - peak) / peak).min()
    bh = c[-1] / c[SMA_REGIME] - 1.0
    return {
        "trades": n,
        "win_rate": len(wins) / n,
        "avg_R": rs.mean(),
        "profit_factor": (wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf"),
        "total_return": curve[-1] / INIT_EQUITY - 1.0,
        "max_dd": max_dd,
        "buy_hold": bh,
    }


def main() -> None:
    rows = []
    for name, ysym in SYMBOLS.items():
        df = indicators(fetch_yahoo(ysym))
        m = backtest(df, ROUND_TRIP_COST[name])
        m["symbol"] = name
        m["bars"] = len(df)
        rows.append(m)
    print(f"\n{'Symbol':9} {'Bars':>5} {'Trades':>6} {'Win%':>6} {'AvgR':>6} "
          f"{'PF':>5} {'Return':>8} {'MaxDD':>7} {'Buy&Hold':>9}")
    print("-" * 78)
    for m in rows:
        if m["trades"] == 0:
            print(f"{m['symbol']:9} {m['bars']:>5}   keine Trades")
            continue
        print(f"{m['symbol']:9} {m['bars']:>5} {m['trades']:>6} "
              f"{m['win_rate']*100:>5.1f} {m['avg_R']:>6.2f} {m['profit_factor']:>5.2f} "
              f"{m['total_return']*100:>7.1f}% {m['max_dd']*100:>6.1f}% {m['buy_hold']*100:>8.1f}%")
    print("\nLesart: AvgR = Erwartungswert je Trade (in R). PF>1 & AvgR>0 = positiver "
          "Erwartungswert. Return/MaxDD bei 1% Risiko/Trade. Vergleich Buy&Hold gleicher Zeitraum.")


if __name__ == "__main__":
    main()
