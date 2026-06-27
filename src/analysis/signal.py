# src/analysis/signal.py
"""Deterministische SL/TP/Entry-Kernlogik fuer die Trading-Signal-Schicht.

Die qualitative AGENTEN-JUDGMENT (direction, conviction, entry_type, horizon,
rationale) ist die Eingabe. Die konkreten Zahlen (entry, stop_loss, take_profit,
take_profit_2, rr) werden hier rein deterministisch aus ATR und den
Support-/Resistance-Levels berechnet. Keine Netzwerkaufrufe.
"""
from __future__ import annotations

# ATR-Multiplikator fuer den Volatilitaets-Stop.
K_SL = 1.8
# Konviktion (1..5) -> Ziel-Chance/Risiko-Verhaeltnis (R:R) fuer take_profit.
R_TARGET = {1: 1.5, 2: 1.5, 3: 1.5, 4: 2.0, 5: 2.5}

_DIRECTIONS = {"LONG", "SHORT", "FLAT"}
_ENTRY_TYPES = {"market", "pullback"}

_NONE_LEVELS = {
    "entry": None,
    "stop_loss": None,
    "take_profit": None,
    "take_profit_2": None,
    "rr": None,
}


def _is_nonempty_str(x: object) -> bool:
    return isinstance(x, str) and x.strip() != ""


def validate_decision(d: dict) -> None:
    """Wirft ValueError, wenn der Agenten-Entscheidungsblock ungueltig ist."""
    if not isinstance(d, dict):
        raise ValueError("decision muss ein dict sein")

    direction = d.get("direction")
    if direction not in _DIRECTIONS:
        raise ValueError(
            f"direction muss in {sorted(_DIRECTIONS)} sein, war {direction!r}")

    conviction = d.get("conviction")
    # bool ist Subklasse von int -> ausschliessen.
    if isinstance(conviction, bool) or not isinstance(conviction, int) \
            or not (1 <= conviction <= 5):
        raise ValueError(
            f"conviction muss int 1..5 sein, war {conviction!r}")

    entry_type = d.get("entry_type")
    if entry_type not in _ENTRY_TYPES:
        raise ValueError(
            f"entry_type muss in {sorted(_ENTRY_TYPES)} sein, war {entry_type!r}")

    horizon = d.get("horizon_days")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon <= 0:
        raise ValueError(
            f"horizon_days muss int > 0 sein, war {horizon!r}")

    if not _is_nonempty_str(d.get("rationale")):
        raise ValueError("rationale muss ein nicht-leerer String sein")


def _round_price(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def _split_levels(levels: list[dict] | None) -> tuple[list[float], list[float]]:
    """Liefert (supports, resistances) als sortierte Preislisten."""
    supports: list[float] = []
    resistances: list[float] = []
    for lvl in levels or []:
        if not isinstance(lvl, dict):
            continue
        price = lvl.get("price")
        if price is None:
            continue
        if lvl.get("type") == "support":
            supports.append(float(price))
        elif lvl.get("type") == "resistance":
            resistances.append(float(price))
    return sorted(supports), sorted(resistances)


def _levels_for_entry(price, atr, supports, resistances, direction, entry,
                      rt) -> dict:
    """Stop/Target-Rechnung fuer einen GEGEBENEN Entry-Preis.

    Liefert ein Roh-Dict (ungerundet) mit entry/stop_loss/take_profit/
    take_profit_2/rr. Reine Funktion der Eingaben.
    """
    if direction == "LONG":
        atr_stop = entry - K_SL * atr
        below_entry = [s for s in supports if s < entry]
        stop_loss = atr_stop
        if below_entry:
            sup = max(below_entry)
            struct = sup - 0.1 * atr
            if atr_stop <= struct < entry:
                stop_loss = struct
        risk = entry - stop_loss
        take_profit = entry + rt * risk
        above = [r for r in resistances if r > entry]
        take_profit_2 = min(above) if above else None
    else:  # SHORT
        atr_stop = entry + K_SL * atr
        above_entry = [r for r in resistances if r > entry]
        stop_loss = atr_stop
        if above_entry:
            res = min(above_entry)
            struct = res + 0.1 * atr
            if entry < struct <= atr_stop:
                stop_loss = struct
        risk = stop_loss - entry
        take_profit = entry - rt * risk
        below = [s for s in supports if s < entry]
        take_profit_2 = max(below) if below else None

    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "take_profit_2": take_profit_2,
        "rr": rt,
    }


def _is_degenerate(direction, price, take_profit) -> bool:
    """Pullback-Entartung: TP liegt bereits am/jenseits des aktuellen Preises.

    LONG: take_profit <= price; SHORT: take_profit >= price.
    """
    if direction == "LONG":
        return take_profit <= price
    return take_profit >= price


def compute_levels(price, atr, levels, direction, conviction, entry_type) -> dict:
    """Berechnet entry/stop_loss/take_profit/take_profit_2/rr deterministisch.

    Gibt fuer FLAT, fehlenden Preis oder fehlenden ATR ein All-None-Dict zurueck.

    Pullback-Schutz: Ein Pullback-Entry muss ein BESSERER Preis als der aktuelle
    sein, dessen TP in Handelsrichtung noch JENSEITS des aktuellen Preises liegt.
    Ist das berechnete Pullback-Setup entartet (LONG ``tp<=price`` bzw. SHORT
    ``tp>=price``), wird auf einen Market-Entry (entry=price) zurueckgefallen.
    Das Feld ``effective_entry_type`` im Ergebnis nennt den tatsaechlich
    verwendeten Entry-Typ ("market" oder "pullback").
    """
    if direction == "FLAT" or price is None or not atr:
        return dict(_NONE_LEVELS)

    price = float(price)
    atr = float(atr)
    supports, resistances = _split_levels(levels)
    rt = R_TARGET[conviction]

    # --- Entry-Preis bestimmen ---
    if entry_type == "pullback":
        if direction == "LONG":
            below = [s for s in supports if s < price]
            entry = max(below) if below else price - 0.5 * atr
        else:  # SHORT
            above = [r for r in resistances if r > price]
            entry = min(above) if above else price + 0.5 * atr
    else:  # market
        entry = price

    raw = _levels_for_entry(price, atr, supports, resistances, direction,
                            entry, rt)
    effective_entry_type = entry_type

    # --- Pullback-Entartung -> Market-Fallback ---
    if entry_type == "pullback" and _is_degenerate(direction, price,
                                                    raw["take_profit"]):
        raw = _levels_for_entry(price, atr, supports, resistances, direction,
                                price, rt)
        effective_entry_type = "market"

    return {
        "entry": _round_price(raw["entry"]),
        "stop_loss": _round_price(raw["stop_loss"]),
        "take_profit": _round_price(raw["take_profit"]),
        "take_profit_2": _round_price(raw["take_profit_2"]),
        "rr": round(rt, 2),
        "effective_entry_type": effective_entry_type,
    }


def build_signal(decision: dict, technical: dict | None, snapshot: dict | None,
                 generated_at: str, model: str) -> dict:
    """Validiert die Entscheidung und baut den vollstaendigen Signal-Block."""
    validate_decision(decision)

    price = snapshot.get("price") if isinstance(snapshot, dict) else None
    atr = technical.get("atr14") if isinstance(technical, dict) else None
    levels = technical.get("levels", []) if isinstance(technical, dict) else []

    lv = compute_levels(
        price, atr, levels,
        decision["direction"], decision["conviction"], decision["entry_type"],
    )

    # Wenn compute_levels einen entarteten Pullback auf Market zurueckgefallen
    # ist, spiegelt der gespeicherte Block den TATSAECHLICHEN Entry-Typ wider,
    # damit die Forward-Test-Aufloesung den Fill korrekt (sofort) modelliert.
    effective_entry_type = lv.get("effective_entry_type") or decision["entry_type"]

    return {
        "generated_at": generated_at,
        "model": model,
        "direction": decision["direction"],
        "conviction": decision["conviction"],
        "entry_type": effective_entry_type,
        "horizon_days": decision["horizon_days"],
        "rationale": decision["rationale"],
        "entry": lv["entry"],
        "stop_loss": lv["stop_loss"],
        "take_profit": lv["take_profit"],
        "take_profit_2": lv["take_profit_2"],
        "rr": lv["rr"],
    }


def attach_signal(report: dict, signal: dict) -> dict:
    """Setzt report['signal'] = signal und gibt den Report zurueck."""
    report["signal"] = signal
    return report
