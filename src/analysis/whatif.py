# src/analysis/whatif.py
"""What-if-Replay: geloggte Signale mit alternativen EXIT-Regeln neu aufloesen.

Zweck: Exit-Politik evidenzbasiert waehlen. Die Entry-Entscheidungen und die
Flip-Grenzen der BASELINE-Aufloesung (resolve_symbol_trades) bleiben fix; nur
die Exit-Mechanik innerhalb des Trade-Fensters variiert. Das ist eine bewusste
Vereinfachung: ein frueherer Policy-Exit koennte real ein frueheres Neu-Signal
erlauben — dieser Effekt wird hier NICHT modelliert.

Policy-Dict (alle Felder optional):
- ``trail_r``: Trailing-Stop bei Hoechstschluss - trail_r * R-Distanz.
- ``breakeven_after_r``: Stop auf Entry, sobald der Kurs breakeven_after_r * R
  in Gewinnrichtung gehandelt hat.
- ``use_tp2``: True -> take_profit_2 (Struktur-Level) statt take_profit.
- ``horizon_mult``: Faktor auf horizon_days (Time-Stop).

Stop-Updates gelten erst ab dem FOLGE-Bar (kein Same-Bar-Look-ahead); SL wird
vor TP geprueft (konservativ, wie der Baseline-Resolver). realized_R nutzt
immer die URSPRUENGLICHE R-Distanz |entry - stop_loss|.

Keine Netzwerkaufrufe.
"""
from __future__ import annotations

from .portfolio import _ascending_bars, _direction_sign


def rescan_exit(trade: dict, time_series: list, policy: dict | None) -> dict:
    """Loest EINEN Baseline-Trade mit einer alternativen Exit-Politik neu auf.

    ``trade``: Ergebnis von resolve_symbol_trades (braucht date, direction,
    entry, stop_loss, take_profit, horizon_days; bei Baseline-Flip auch
    exit_date als Fenster-Grenze). Pending/nicht gefuellte Trades werden
    unveraendert zurueckgegeben.
    """
    policy = policy or {}
    out = dict(trade)

    if trade.get("filled") is False or trade.get("status") in ("no_fill", "none"):
        return out
    direction = trade.get("direction")
    entry = trade.get("entry")
    stop = trade.get("stop_loss")
    if direction not in ("LONG", "SHORT") or entry is None or stop is None:
        return out

    entry = float(entry)
    stop = float(stop)
    r_dist = abs(entry - stop)
    if r_dist == 0:
        return out
    sign = _direction_sign(direction)

    target = trade.get("take_profit")
    if policy.get("use_tp2") and trade.get("take_profit_2") is not None:
        target = trade.get("take_profit_2")
    target = float(target) if target is not None else None

    horizon = int((trade.get("horizon_days") or 0)
                  * float(policy.get("horizon_mult", 1.0)))
    trail_r = policy.get("trail_r")
    be_after = policy.get("breakeven_after_r")

    # Flip-Grenze der Baseline: danach existiert der Trade nicht mehr.
    flip_date = (str(trade.get("exit_date"))
                 if trade.get("status") == "flip" and trade.get("exit_date")
                 else None)

    bars = [b for b in _ascending_bars(time_series)
            if b["date"] > str(trade.get("date"))]

    out.update(status="open", exit_date=None, exit_price=None, realized_R=None)
    sl_cur = stop
    best = None            # bester Schlusskurs in Gewinnrichtung
    scanned = 0
    last_close = None
    last_date = None

    for bar in bars:
        if flip_date is not None and bar["date"] > flip_date:
            break
        if horizon and scanned >= horizon:
            break
        scanned += 1
        last_close, last_date = bar["close"], bar["date"]

        # --- Exits mit dem AKTUELLEN Stop pruefen (SL vor TP) ---
        if direction == "LONG":
            if bar["low"] <= sl_cur:
                out.update(status="sl", exit_price=sl_cur, exit_date=bar["date"])
                break
            if target is not None and bar["high"] >= target:
                out.update(status="tp", exit_price=target, exit_date=bar["date"])
                break
        else:
            if bar["high"] >= sl_cur:
                out.update(status="sl", exit_price=sl_cur, exit_date=bar["date"])
                break
            if target is not None and bar["low"] <= target:
                out.update(status="tp", exit_price=target, exit_date=bar["date"])
                break

        # Flip-Tag erreicht ohne Treffer -> Flip am Close (wie Baseline).
        if flip_date is not None and bar["date"] == flip_date:
            out.update(status="flip", exit_price=bar["close"],
                       exit_date=bar["date"])
            break

        # --- Stop-Updates NACH dem Bar (gelten ab dem naechsten) ---
        if direction == "LONG":
            best = bar["close"] if best is None else max(best, bar["close"])
            if trail_r is not None:
                sl_cur = max(sl_cur, best - float(trail_r) * r_dist)
            if be_after is not None and bar["high"] >= entry + float(be_after) * r_dist:
                sl_cur = max(sl_cur, entry)
        else:
            best = bar["close"] if best is None else min(best, bar["close"])
            if trail_r is not None:
                sl_cur = min(sl_cur, best + float(trail_r) * r_dist)
            if be_after is not None and bar["low"] <= entry - float(be_after) * r_dist:
                sl_cur = min(sl_cur, entry)

    if out["status"] == "open" and horizon and scanned >= horizon \
            and last_close is not None:
        out.update(status="expired", exit_price=last_close, exit_date=last_date)

    if out["status"] in ("sl", "tp", "expired", "flip") \
            and out["exit_price"] is not None:
        out["realized_R"] = round(
            sign * (float(out["exit_price"]) - entry) / r_dist, 4)
    return out


def summarize(rows: list) -> dict:
    """Kennzahlen einer Policy: resolved/wins/win_rate/avg_R/total_R."""
    resolved = [r for r in rows if r.get("realized_R") is not None]
    wins = sum(1 for r in resolved if r["realized_R"] > 0)
    total = round(sum(r["realized_R"] for r in resolved), 4)
    return {
        "resolved": len(resolved),
        "wins": wins,
        "win_rate": round(wins / len(resolved), 4) if resolved else None,
        "avg_R": round(total / len(resolved), 4) if resolved else None,
        "total_R": total,
    }
