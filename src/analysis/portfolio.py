# src/analysis/portfolio.py
"""Depot-/Portfolio-Simulation fuer geloggte Signale.

Drei reine Funktionen, keine Netzwerkaufrufe:

- ``position_size`` — Stueckzahl aus Risiko-Betrag und SL-Abstand.
- ``resolve_trade`` — loest ein geloggtes Signal anhand der taeglichen
  Rohdaten (time_series, neueste zuerst) zu tp/sl/expired/open/none auf.
- ``simulate`` — Event-Simulation ueber alle Trades; liefert summary,
  equity_curve, closed und open Listen.

R-Definition: realized_R = direction_sign * (exit - entry) / abs(entry - stop_loss)
mit direction_sign +1 fuer LONG, -1 fuer SHORT.
"""
from __future__ import annotations


def position_size(risk_amount, entry, stop_loss):
    """Stueckzahl = risk_amount / |entry - stop_loss|.

    None, wenn entry/stop_loss fehlen oder der Abstand 0 ist.
    """
    if entry is None or stop_loss is None:
        return None
    distance = abs(float(entry) - float(stop_loss))
    if distance == 0:
        return None
    return round(float(risk_amount) / distance, 4)


def _direction_sign(direction):
    return 1.0 if direction == "LONG" else -1.0


def _bars_after(time_series, signal_date):
    """Bars STRIKT nach signal_date, sortiert aeltest -> neuest.

    time_series-Bars sind dicts mit datetime/open/high/low/close (Strings).
    """
    if not isinstance(time_series, list):
        return []
    bars = []
    for b in time_series:
        if not isinstance(b, dict):
            continue
        dt = b.get("datetime")
        if dt is None or signal_date is None or str(dt) <= str(signal_date):
            continue
        try:
            bars.append({
                "datetime": str(dt),
                "high": float(b["high"]),
                "low": float(b["low"]),
                "close": float(b["close"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    bars.sort(key=lambda x: x["datetime"])
    return bars


def _realized_r(direction, exit_price, entry, stop_loss):
    if entry is None or stop_loss is None or exit_price is None:
        return None
    denom = abs(float(entry) - float(stop_loss))
    if denom == 0:
        return None
    sign = _direction_sign(direction)
    return round(sign * (float(exit_price) - float(entry)) / denom, 4)


def resolve_trade(log_entry: dict, time_series: list) -> dict:
    """Loest ein geloggtes Signal anhand der taeglichen Bars auf.

    Scannt Bars STRIKT NACH ``log_entry['date']`` (aeltest -> neuest) bis zu
    ``horizon_days`` Bars:

    - LONG:  low <= stop_loss -> "sl" (exit=stop_loss); sonst
             high >= take_profit -> "tp" (exit=take_profit).
    - SHORT: high >= stop_loss -> "sl"; sonst low <= take_profit -> "tp".

    Kein Treffer und genug Bars ueber den Horizont hinaus -> "expired"
    (exit = letzter Close im Horizont). Zu wenige Bars -> "open".
    FLAT oder fehlendes entry/stop_loss -> "none".

    Liefert ``{...log_entry, status, exit_date, exit_price, realized_R}``.
    """
    direction = log_entry.get("direction")
    entry = log_entry.get("entry")
    stop_loss = log_entry.get("stop_loss")
    take_profit = log_entry.get("take_profit")
    horizon = log_entry.get("horizon_days") or 0

    base = dict(log_entry)
    base.update(status="none", exit_date=None, exit_price=None, realized_R=None)

    # FLAT oder fehlende Pflichtzahlen -> nicht handelbar.
    if direction not in ("LONG", "SHORT") or entry is None or stop_loss is None \
            or take_profit is None:
        return base

    entry = float(entry)
    stop_loss = float(stop_loss)
    take_profit = float(take_profit)

    bars = _bars_after(time_series, log_entry.get("date"))
    if not bars:
        base["status"] = "open"
        return base

    window = bars[:horizon]
    for bar in window:
        if direction == "LONG":
            if bar["low"] <= stop_loss:
                base.update(status="sl", exit_price=stop_loss,
                            exit_date=bar["datetime"])
                break
            if bar["high"] >= take_profit:
                base.update(status="tp", exit_price=take_profit,
                            exit_date=bar["datetime"])
                break
        else:  # SHORT
            if bar["high"] >= stop_loss:
                base.update(status="sl", exit_price=stop_loss,
                            exit_date=bar["datetime"])
                break
            if bar["low"] <= take_profit:
                base.update(status="tp", exit_price=take_profit,
                            exit_date=bar["datetime"])
                break

    if base["status"] == "none":
        # Kein SL/TP getroffen. Reicht das Fenster ueber den Horizont
        # (genug Bars vorhanden) -> "expired" mit Close der letzten
        # In-Horizont-Bar. Sonst zu wenige Bars -> "open".
        if len(bars) >= horizon and window:
            last = window[-1]
            base.update(status="expired", exit_price=last["close"],
                        exit_date=last["datetime"])
        else:
            base["status"] = "open"

    if base["status"] in ("sl", "tp", "expired"):
        base["realized_R"] = _realized_r(direction, base["exit_price"],
                                          entry, stop_loss)
    return base


def _is_tradeable(t: dict) -> bool:
    return t.get("direction") in ("LONG", "SHORT") and t.get("stop_loss") is not None


def simulate(trades: list, start_equity: float = 100_000.0,
             risk_pct: float = 0.01) -> dict:
    """Event-Simulation ueber aufgeloeste/offene Trades.

    Nur Trades mit Richtung LONG/SHORT und Stop-Loss sind handelbar. Pro Trade
    ein OPEN-Event am Signal-Datum und (falls aufgeloest) ein CLOSE-Event am
    Exit-Datum. Events stabil nach Datum sortiert. Auf OPEN wird das Risiko
    (risk_pct*equity) und die Stueckzahl gesperrt; auf CLOSE wird
    pnl = risk_amount * realized_R verbucht.
    """
    tradeable = [t for t in trades if _is_tradeable(t)]

    # Events bauen: (date, order, kind, trade). order haelt stabile
    # Sortierung bei gleichem Datum.
    events = []
    for i, t in enumerate(tradeable):
        events.append((str(t.get("date")), i, "open", t))
        if t.get("status") in ("sl", "tp", "expired") and t.get("exit_date"):
            events.append((str(t.get("exit_date")), i, "close", t))
    # Stabile Sortierung nach Datum; bei gleichem Datum OPEN vor CLOSE und in
    # Eingangsreihenfolge.
    kind_rank = {"open": 0, "close": 1}
    events.sort(key=lambda e: (e[0], kind_rank[e[2]], e[1]))

    equity = float(start_equity)
    locked: dict[int, dict] = {}  # trade-index -> {risk_amount, units}

    # Startpunkt der Equity-Kurve.
    start_date = "start"
    open_dates = [str(t.get("date")) for t in tradeable if t.get("date")]
    if open_dates:
        start_date = min(open_dates)
    equity_curve = [{"date": start_date, "equity": round(equity, 4)}]

    closed = []
    peak = equity
    max_drawdown = 0.0

    for _date, idx, kind, t in events:
        if kind == "open":
            risk_amount = round(risk_pct * equity, 4)
            units = position_size(risk_amount, t.get("entry"), t.get("stop_loss"))
            locked[idx] = {"risk_amount": risk_amount, "units": units}
        else:  # close
            lock = locked.get(idx, {"risk_amount": round(risk_pct * equity, 4),
                                    "units": None})
            risk_amount = lock["risk_amount"]
            realized_r = t.get("realized_R")
            pnl = round(risk_amount * (realized_r or 0.0), 4)
            equity = round(equity + pnl, 4)

            peak = max(peak, equity)
            drawdown = equity - peak  # <= 0
            max_drawdown = min(max_drawdown, drawdown)

            closed.append({
                "symbol": t.get("symbol"),
                "display": t.get("display"),
                "direction": t.get("direction"),
                "conviction": t.get("conviction"),
                "entry": t.get("entry"),
                "stop_loss": t.get("stop_loss"),
                "take_profit": t.get("take_profit"),
                "exit_date": t.get("exit_date"),
                "exit_price": t.get("exit_price"),
                "realized_R": realized_r,
                "risk_amount": risk_amount,
                "pnl": pnl,
                "win": pnl > 0,
                "status": t.get("status"),
            })
            equity_curve.append({"date": str(t.get("exit_date")),
                                 "equity": round(equity, 4)})

    # Offene handelbare Trades (kein CLOSE-Event).
    open_list = []
    for idx, t in enumerate(tradeable):
        if t.get("status") in ("sl", "tp", "expired"):
            continue
        lock = locked.get(idx, {})
        open_list.append({
            "symbol": t.get("symbol"),
            "display": t.get("display"),
            "date": t.get("date"),
            "direction": t.get("direction"),
            "conviction": t.get("conviction"),
            "entry": t.get("entry"),
            "stop_loss": t.get("stop_loss"),
            "take_profit": t.get("take_profit"),
            "rr": t.get("rr"),
            "risk_amount": lock.get("risk_amount"),
            "units": lock.get("units"),
            "horizon_days": t.get("horizon_days"),
        })

    closed_count = len(closed)
    wins = sum(1 for c in closed if c["win"])
    losses = sum(1 for c in closed if not c["win"])
    total_pnl = round(sum(c["pnl"] for c in closed), 4)
    win_rate = round(wins / closed_count, 4) if closed_count else 0
    return_pct = round((equity - start_equity) / start_equity * 100, 4) \
        if start_equity else 0

    summary = {
        "start_equity": round(float(start_equity), 4),
        "current_equity": round(equity, 4),
        "return_pct": return_pct,
        "open_count": len(open_list),
        "closed_count": closed_count,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "max_drawdown": round(max_drawdown, 4),
    }

    return {
        "summary": summary,
        "equity_curve": equity_curve,
        "closed": closed,
        "open": open_list,
    }
