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

# Ob ein spaeteres FLAT-Signal eine offene Position schliesst (Bias-Flip auf
# FLAT). True = FLAT zaehlt als Gegen-Signal; False = nur die echte
# Gegenrichtung schliesst.
FLAT_CLOSES = True


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


def _ascending_bars(time_series: list) -> list:
    """time_series (neueste zuerst, String-OHLC) -> aufsteigende Floatbars.

    Liefert ``[{date, open, high, low, close}]`` sortiert aeltest -> neuest.
    Unvollstaendige Bars werden uebersprungen.
    """
    if not isinstance(time_series, list):
        return []
    bars = []
    for b in time_series:
        if not isinstance(b, dict):
            continue
        dt = b.get("datetime") or b.get("date")
        if dt is None:
            continue
        try:
            bars.append({
                "date": str(dt),
                "open": float(b["open"]),
                "high": float(b["high"]),
                "low": float(b["low"]),
                "close": float(b["close"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    bars.sort(key=lambda x: x["date"])
    return bars


def _is_actionable(sig: dict) -> bool:
    """LONG/SHORT mit gesetztem entry UND stop_loss -> handelbar."""
    return (sig.get("direction") in ("LONG", "SHORT")
            and sig.get("entry") is not None
            and sig.get("stop_loss") is not None)


def _opposes(open_direction: str, sig_direction: str, flat_closes: bool) -> bool:
    """Ob ``sig_direction`` die offene Position bias-flippt.

    Gegenrichtung schliesst immer; FLAT nur wenn ``flat_closes``.
    """
    if open_direction == "LONG":
        if sig_direction == "SHORT":
            return True
    elif open_direction == "SHORT":
        if sig_direction == "LONG":
            return True
    if sig_direction == "FLAT" and flat_closes:
        return True
    return False


def resolve_symbol_trades(signals: list, time_series: list,
                          flat_closes: bool = FLAT_CLOSES) -> list:
    """Loest die taegliche Signalfolge EINES Symbols zu Trades auf.

    ``signals``: alle Log-Eintraege eines Symbols (unsortiert erlaubt).
    ``time_series``: dessen taegliche Bars, neueste zuerst (String-OHLC).

    Simuliert hoechstens EINE offene Position gleichzeitig. Pro offener
    Position ist der Exit das FRUEHESTE aus:

    1. SL/TP intrabar (wie ``resolve_trade``),
    2. Bias-Flip: das frueheste spaetere Signal mit Gegenrichtung
       (FLAT zaehlt nur bei ``flat_closes``) -> Close am Flip-Datum
       (oder letzter Close davor, falls kein Bar), Status "flip",
    3. Horizont/Time-Stop -> "expired" am letzten In-Horizont-Bar,
    4. sonst "open".

    Nach einem Exit kann das ausloesende (Flip-)Signal bzw. das naechste
    handelbare Signal eine neue Position eroeffnen.
    """
    sigs = sorted(
        (s for s in signals if isinstance(s, dict)),
        key=lambda s: str(s.get("date")),
    )
    bars = _ascending_bars(time_series)

    trades: list[dict] = []
    i = 0
    n = len(sigs)
    while i < n:
        sig = sigs[i]
        if not _is_actionable(sig):
            i += 1
            continue

        direction = sig["direction"]
        entry = float(sig["entry"])
        stop_loss = float(sig["stop_loss"])
        take_profit = sig.get("take_profit")
        take_profit = float(take_profit) if take_profit is not None else None
        horizon = sig.get("horizon_days") or 0
        entry_date = str(sig.get("date"))
        # Entry-Typ entscheidet ueber das Fill-Modell. Fehlt das Feld (Alt-Logs)
        # -> "market" (sofortiger Fill am Signal-Datum), rueckwaertskompatibel.
        entry_type = sig.get("entry_type") or "market"

        # Frueheste spaetere Gegen-Signal-Position bestimmen.
        flip_date = None
        flip_index = None
        for j in range(i + 1, n):
            cand = sigs[j]
            cdate = str(cand.get("date"))
            if cdate <= entry_date:
                continue
            if _opposes(direction, cand.get("direction"), flat_closes):
                flip_date = cdate
                flip_index = j
                break

        trade = {
            "symbol": sig.get("symbol"),
            "display": sig.get("display"),
            "direction": direction,
            "conviction": sig.get("conviction"),
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "horizon_days": horizon,
            "date": entry_date,
            "status": "open",
            "exit_date": None,
            "exit_price": None,
            "realized_R": None,
        }
        if "take_profit_2" in sig:
            trade["take_profit_2"] = sig.get("take_profit_2")
        if "rr" in sig:
            trade["rr"] = sig.get("rr")

        future = [b for b in bars if b["date"] > entry_date]

        resolved_status = None
        exit_date = None
        exit_price = None
        last_in_horizon_close = None
        last_in_horizon_date = None
        bars_scanned = 0
        horizon_stopped = False
        # Fill-Modell: market ist sofort gefuellt (Fill am Signal-Datum); ein
        # Pullback bleibt PENDING, bis ein Bar STRIKT NACH dem Signal-Datum
        # durch den Entry handelt. SL/TP gelten erst auf Bars STRIKT NACH dem
        # Fill-Bar (kein Same-Bar-Look-ahead).
        filled = entry_type != "pullback"

        for bar in future:
            # Bars NACH dem Flip-Datum sind irrelevant: bis dahin haette ein
            # Flip laengst geschlossen.
            if flip_date is not None and bar["date"] > flip_date:
                break
            # Horizont (ab Signal-Datum, fuer die gesamte Trade-Lebenszeit aus
            # Pending + Open) ausgeschoepft -> Time-Stop hat Vorrang.
            if horizon and bars_scanned >= horizon:
                horizon_stopped = True
                break
            bars_scanned += 1
            last_in_horizon_close = bar["close"]
            last_in_horizon_date = bar["date"]

            if not filled:
                # Position noch PENDING: prueft NUR, ob dieser Bar den Entry
                # erreicht. SL/TP erst ab dem naechsten Bar.
                if direction == "LONG":
                    if bar["low"] <= entry:
                        filled = True
                else:  # SHORT
                    if bar["high"] >= entry:
                        filled = True
                # Auch am Flip-Datum: wird der Pullback hier nicht gefuellt und
                # ist es das Flip-Datum, war es nie ein echter Trade -> no_fill.
                if not filled and flip_date is not None and bar["date"] == flip_date:
                    resolved_status = "no_fill"
                    break
                # Fill-Bar selbst NICHT auf SL/TP pruefen -> naechster Bar.
                continue

            # --- gefuellt: SL/TP INTRABAR pruefen, auch am Flip-Datum ---
            if direction == "LONG":
                if bar["low"] <= stop_loss:
                    resolved_status = "sl"
                    exit_price = stop_loss
                    exit_date = bar["date"]
                    break
                if take_profit is not None and bar["high"] >= take_profit:
                    resolved_status = "tp"
                    exit_price = take_profit
                    exit_date = bar["date"]
                    break
            else:  # SHORT
                if bar["high"] >= stop_loss:
                    resolved_status = "sl"
                    exit_price = stop_loss
                    exit_date = bar["date"]
                    break
                if take_profit is not None and bar["low"] <= take_profit:
                    resolved_status = "tp"
                    exit_price = take_profit
                    exit_date = bar["date"]
                    break

            # Flip-Datum ohne SL/TP-Treffer erreicht -> Bias-Flip am Close.
            if flip_date is not None and bar["date"] == flip_date:
                resolved_status = "flip"
                exit_date = flip_date
                exit_price = bar["close"]
                break

        # Flip waehrend noch PENDING (Flip-Datum hatte keinen Bar, oder Schleife
        # endete vor dem Flip) -> der Trade war nie real -> no_fill.
        if resolved_status is None and not filled and flip_date is not None \
                and not horizon_stopped:
            resolved_status = "no_fill"

        if resolved_status is None and filled and flip_date is not None \
                and not horizon_stopped:
            # Flip-Datum hat keinen Bar (Wochenende/Luecke) und der Horizont kam
            # nicht zuvor: am letzten Bar-Close davor schliessen.
            on_or_before = [b for b in bars if b["date"] <= flip_date]
            if on_or_before:
                resolved_status = "flip"
                exit_date = flip_date
                exit_price = on_or_before[-1]["close"]

        if resolved_status is None:
            if not filled:
                # Pullback nie erreicht. Reicht das Fenster ueber den Horizont
                # (genug Bars vorhanden) -> nie gehandelt -> "no_fill". Sonst zu
                # wenige Bars -> noch "open" (koennte spaeter fuellen).
                if horizon and len(future) >= horizon:
                    resolved_status = "no_fill"
            elif horizon and len(future) >= horizon \
                    and last_in_horizon_close is not None:
                # Kein SL/TP, kein Flip-Close. Horizont ausgeschoepft -> expired.
                resolved_status = "expired"
                exit_price = last_in_horizon_close
                exit_date = last_in_horizon_date

        if resolved_status is not None:
            trade["status"] = resolved_status
            trade["exit_date"] = exit_date
            trade["exit_price"] = exit_price
            trade["realized_R"] = _realized_r(direction, exit_price, entry,
                                              stop_loss)
        # Ob die Position je gefuellt wurde. Market ist sofort gefuellt; ein
        # Pullback nur, wenn ein Bar durch den Entry gehandelt hat. Wichtig fuer
        # offene Positionen: ein noch nicht gefuellter Pullback ("open", aber
        # pending) ist NICHT im Markt -> kein unrealisierter P&L.
        trade["filled"] = bool(filled)
        trades.append(trade)

        # Ein durch einen Flip ausgeloestes no_fill (Pullback wurde vor dem
        # Gegensignal nie gefuellt -> Trade nie real): das Gegensignal selbst
        # darf danach eine neue Position eroeffnen.
        flip_cancelled = (trade["status"] == "no_fill"
                          and flip_index is not None)

        # Invariante: HOECHSTENS EINE offene Position pro Symbol. Eine Position
        # ohne Exit (exit_date is None), die NICHT durch einen Flip storniert
        # wurde, blieb open/pending bis ans Ende der Daten. Spaetere GLEICH-
        # gerichtete Signale werden gehalten (kein zweiter Trade); ein spaeteres
        # Gegen-/FLAT-Signal waere bereits als flip_date geschlossen worden. Es
        # darf also keine neue, NEBENLAEUFIGE Position eroeffnet werden ->
        # Schleife beenden.
        if exit_date is None and trade["status"] != "flip" \
                and not flip_cancelled:
            break

        # Weiter nach dem Exit: das Flip-Signal (oder das naechste Signal nach
        # dem Exit-/Storno-Datum) darf eine neue Position eroeffnen.
        if (trade["status"] == "flip" or flip_cancelled) \
                and flip_index is not None:
            i = flip_index
        else:
            # Naechstes Signal, dessen Datum strikt nach dem Exit-Datum liegt.
            boundary = exit_date
            nxt = i + 1
            while nxt < n and str(sigs[nxt].get("date")) <= str(boundary):
                nxt += 1
            if nxt <= i:
                nxt = i + 1
            i = nxt

    return trades


def _is_tradeable(t: dict) -> bool:
    # "no_fill"/"none" sind KEINE Trades (nie gefuellt) -> aus der Simulation
    # ausgeschlossen (Wins/Losses/Win-Rate/closed_count/Equity-Kurve).
    return (t.get("direction") in ("LONG", "SHORT")
            and t.get("stop_loss") is not None
            and t.get("status") not in ("no_fill", "none"))


def _unrealized_pct(direction, entry, current_price):
    """Unrealisierter Stand in % einer offenen Position zum aktuellen Kurs.

    LONG:  (current - entry) / entry * 100
    SHORT: (entry - current) / entry * 100  (Gewinn faellt mit dem Kurs)

    None, wenn entry/current_price fehlen oder entry == 0.
    """
    if entry is None or current_price is None:
        return None
    entry = float(entry)
    if entry == 0:
        return None
    sign = _direction_sign(direction)
    return round(sign * (float(current_price) - entry) / entry * 100, 4)


def simulate(trades: list, start_equity: float = 100_000.0,
             risk_pct: float = 0.01, current_prices: dict | None = None) -> dict:
    """Event-Simulation ueber aufgeloeste/offene Trades.

    Nur Trades mit Richtung LONG/SHORT und Stop-Loss sind handelbar. Pro Trade
    ein OPEN-Event am Signal-Datum und (falls aufgeloest) ein CLOSE-Event am
    Exit-Datum. Events stabil nach Datum sortiert. Auf OPEN wird das Risiko
    (risk_pct*equity) und die Stueckzahl gesperrt; auf CLOSE wird
    pnl = risk_amount * realized_R verbucht.

    ``current_prices`` (optional): Mapping symbol/display -> aktueller Kurs
    (neuester Tagesschluss). Jede offene Position erhaelt daraus
    ``current_price`` und ``unrealized_pct``; ohne Eintrag bleiben beide None.
    """
    prices = current_prices or {}
    tradeable = [t for t in trades if _is_tradeable(t)]
    no_fill_count = sum(1 for t in trades if t.get("status") == "no_fill")

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
        current_price = prices.get(t.get("symbol"))
        if current_price is None:
            current_price = prices.get(t.get("display"))
        # Pending = noch nicht gefuellter Pullback (filled explizit False). Fehlt
        # das Feld (Alt-Trades), gilt die Position als gefuellt. Fuer pending
        # Positionen gibt es KEINEN unrealisierten Stand (Phantom-Gewinn-Schutz).
        pending = t.get("filled") is False
        unrealized_pct = (None if pending else
                          _unrealized_pct(t.get("direction"), t.get("entry"),
                                          current_price))
        # Unrealisierter P&L in Geld: units * (Kurs - Entry) * Richtung.
        # Nur fuer gefuellte Positionen mit Kurs UND Stueckzahl bewertbar.
        units = lock.get("units")
        unrealized_pnl = None
        if not pending and current_price is not None and units is not None \
                and t.get("entry") is not None:
            sign = _direction_sign(t.get("direction"))
            unrealized_pnl = round(
                sign * (float(current_price) - float(t.get("entry")))
                * float(units), 4)
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
            "pending": pending,
            "current_price": current_price,
            "unrealized_pct": unrealized_pct,
            "unrealized_pnl": unrealized_pnl,
        })

    closed_count = len(closed)
    wins = sum(1 for c in closed if c["win"])
    losses = sum(1 for c in closed if not c["win"])
    total_pnl = round(sum(c["pnl"] for c in closed), 4)
    win_rate = round(wins / closed_count, 4) if closed_count else 0
    return_pct = round((equity - start_equity) / start_equity * 100, 4) \
        if start_equity else 0

    # Mark-to-Market: realisierte Equity + offene Positionen zum letzten
    # Schlusskurs bewertet ("wo stuende das Depot, wenn alle Trades live
    # ausgefuehrt waeren"). Pending/kurslose Positionen zaehlen nicht.
    unrealized_total = round(sum(o["unrealized_pnl"] for o in open_list
                                 if o.get("unrealized_pnl") is not None), 4)
    marked_equity = round(equity + unrealized_total, 4)
    marked_return_pct = round(
        (marked_equity - start_equity) / start_equity * 100, 4) \
        if start_equity else 0

    summary = {
        "start_equity": round(float(start_equity), 4),
        "current_equity": round(equity, 4),
        "return_pct": return_pct,
        "open_count": len(open_list),
        "no_fill_count": no_fill_count,
        "closed_count": closed_count,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "max_drawdown": round(max_drawdown, 4),
        "unrealized_pnl": unrealized_total,
        "marked_equity": marked_equity,
        "marked_return_pct": marked_return_pct,
    }

    return {
        "summary": summary,
        "equity_curve": equity_curve,
        "closed": closed,
        "open": open_list,
    }
