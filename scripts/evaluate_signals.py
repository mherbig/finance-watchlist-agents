# scripts/evaluate_signals.py
"""Forward-Test-Evaluator fuer geloggte Signale.

Liest docs/signals/log.jsonl. Fuer jedes Signal wird die neueste Rohdatei
data/<safe>/raw-*.json geladen und deren ``time_series`` (taegliche Bars,
neueste zuerst) ueber portfolio.resolve_trade STRIKT NACH dem Signal-Datum
ausgewertet:

- LONG:  Bar-low  <= stop_loss   -> "sl"
         sonst Bar-high >= take_profit -> "tp"
- SHORT: Bar-high >= stop_loss   -> "sl"
         sonst Bar-low  <= take_profit -> "tp"

Wird innerhalb von ``horizon_days`` Bars keins getroffen -> "expired"
(realized R aus dem letzten Close). Sind noch keine Bars nach dem Signal-Datum
vorhanden (oder fehlt die Rohdatei), bleibt das Signal "open".

realized_R = sign * (exit - entry) / abs(entry - stop_loss)
(sign = +1 LONG, -1 SHORT).

Schreibt docs/signals/track_record.json mit Einzelergebnissen + Aggregaten.
Keine Netzwerkaufrufe. Bei Tag 1 (alles open) -> Hinweis ausgeben.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.analysis import portfolio  # noqa: E402
from src.data.symbol_map import safe_name  # noqa: E402

# resolve_symbol_trades-Status -> Track-Record-Outcome.
_STATUS_TO_OUTCOME = {
    "tp": "tp", "sl": "sl", "expired": "expired", "flip": "flip",
    "open": "open", "none": "open",
}


def _latest_raw_report(symbol_dir: Path) -> dict | None:
    files = sorted(symbol_dir.glob("raw-*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _resolve_symbol(symbol_signals, time_series, flat_closes,
                    flat_min_conviction=portfolio.FLAT_MIN_CONVICTION,
                    flat_consecutive=portfolio.FLAT_CONSECUTIVE) -> dict:
    """Loest die Signalfolge eines Symbols auf und indexiert nach Entry-Datum.

    Liefert ``{entry_date: {outcome, exit_price, exit_date, realized_R}}`` fuer
    jede eroeffnete Position. Signale, die keine Position eroeffnet haben (FLAT,
    fehlende SL/TP oder absorbierte Gleichrichtungs-Signale), bleiben "open".
    """
    resolved = portfolio.resolve_symbol_trades(
        symbol_signals, time_series or [], flat_closes=flat_closes,
        flat_min_conviction=flat_min_conviction,
        flat_consecutive=flat_consecutive)
    by_date: dict[str, dict] = {}
    for t in resolved:
        by_date[str(t.get("date"))] = {
            "outcome": _STATUS_TO_OUTCOME.get(t["status"], "open"),
            "exit_price": t["exit_price"],
            "exit_date": t["exit_date"],
            "realized_R": t["realized_R"],
        }
    return by_date


_OPEN_EV = {"outcome": "open", "exit_price": None, "exit_date": None,
            "realized_R": None}


def _aggregate(results) -> dict:
    total = len(results)
    open_n = sum(1 for r in results if r["outcome"] == "open")
    resolved = [r for r in results
                if r["outcome"] in ("tp", "sl", "expired", "flip")]
    tp = sum(1 for r in resolved if r["outcome"] == "tp")
    sl = sum(1 for r in resolved if r["outcome"] == "sl")
    expired = sum(1 for r in resolved if r["outcome"] == "expired")
    flip = sum(1 for r in resolved if r["outcome"] == "flip")

    rs = [r["realized_R"] for r in resolved if r["realized_R"] is not None]
    avg_R = round(sum(rs) / len(rs), 4) if rs else None
    hit_rate = round(tp / len(resolved), 4) if resolved else None

    by_conviction: dict[str, dict] = {}
    by_asset: dict[str, dict] = {}
    for r in results:
        conv = str(r.get("conviction"))
        bc = by_conviction.setdefault(conv, {"total": 0, "tp": 0, "sl": 0,
                                             "expired": 0, "flip": 0,
                                             "open": 0, "rs": []})
        bc["total"] += 1
        bc[r["outcome"]] = bc.get(r["outcome"], 0) + 1
        if r["realized_R"] is not None:
            bc["rs"].append(r["realized_R"])

        ac = r.get("asset_class") or "unknown"
        ba = by_asset.setdefault(ac, {"total": 0, "tp": 0, "sl": 0,
                                      "expired": 0, "flip": 0,
                                      "open": 0, "rs": []})
        ba["total"] += 1
        ba[r["outcome"]] = ba.get(r["outcome"], 0) + 1
        if r["realized_R"] is not None:
            ba["rs"].append(r["realized_R"])

    def _finish(d):
        out = {}
        for key, v in d.items():
            rs_ = v.pop("rs")
            v["avg_R"] = round(sum(rs_) / len(rs_), 4) if rs_ else None
            out[key] = v
        return out

    return {
        "total": total,
        "open": open_n,
        "resolved": len(resolved),
        "tp": tp,
        "sl": sl,
        "expired": expired,
        "flip": flip,
        "hit_rate": hit_rate,
        "avg_R": avg_R,
        "by_conviction": _finish(by_conviction),
        "by_asset_class": _finish(by_asset),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))
    data_dir = root / settings["data_dir"]
    reports_dir = root / settings["reports_dir"]
    log_path = root / "docs" / "signals" / "log.jsonl"
    out_path = root / "docs" / "signals" / "track_record.json"

    if not log_path.exists():
        print(f"Kein Signal-Log gefunden ({log_path}). Nichts auszuwerten.")
        return

    sig_cfg = settings.get("signals", {})
    flat_closes = bool(sig_cfg.get("flat_closes_position", portfolio.FLAT_CLOSES))
    flat_min_conviction = int(sig_cfg.get("flat_close_min_conviction",
                                          portfolio.FLAT_MIN_CONVICTION))
    flat_consecutive = int(sig_cfg.get("flat_close_consecutive",
                                       portfolio.FLAT_CONSECUTIVE))

    # Log-Zeilen je Symbol gruppieren (Erstsichtungs-Reihenfolge erhalten).
    groups: dict[str, list] = {}
    order: list[str] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            sig = json.loads(line)
        except json.JSONDecodeError:
            print(f"  WARN: ungueltige Log-Zeile uebersprungen: {line[:60]}")
            continue
        key = sig.get("symbol") or sig.get("display")
        if key is None:
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(sig)

    results = []
    raw_cache: dict[str, dict | None] = {}
    asset_cache: dict[str, str | None] = {}
    for key in order:
        symbol_signals = groups[key]
        display = symbol_signals[0].get("display") or symbol_signals[0].get("symbol")
        safe = safe_name(str(display)) if display else None
        time_series = None
        asset_class = None
        if safe is not None:
            if safe not in raw_cache:
                sym_dir = data_dir / safe
                raw = _latest_raw_report(sym_dir) if sym_dir.is_dir() else None
                raw_cache[safe] = raw
                # asset_class kommt aus dem Roh-Report (oder dem Report-Verz.).
                ac = (raw or {}).get("asset_class")
                if ac is None:
                    rep_dir = reports_dir / safe
                    if rep_dir.is_dir():
                        rep_files = sorted(rep_dir.glob("*.json"))
                        if rep_files:
                            try:
                                ac = json.loads(
                                    rep_files[-1].read_text(encoding="utf-8")
                                ).get("asset_class")
                            except (json.JSONDecodeError, OSError):
                                ac = None
                asset_cache[safe] = ac
            raw = raw_cache[safe]
            time_series = (raw or {}).get("time_series")
            asset_class = asset_cache.get(safe)

        # Einmalige Symbol-Aufloesung; Ergebnis je Entry-Datum.
        ev_by_date = _resolve_symbol(symbol_signals, time_series, flat_closes,
                                     flat_min_conviction, flat_consecutive)
        for sig in symbol_signals:
            ev = ev_by_date.get(str(sig.get("date")), _OPEN_EV)
            results.append({
                "date": sig.get("date"),
                "symbol": sig.get("symbol"),
                "display": sig.get("display") or sig.get("symbol"),
                "asset_class": asset_class,
                "direction": sig.get("direction"),
                "conviction": sig.get("conviction"),
                "entry": sig.get("entry"),
                "stop_loss": sig.get("stop_loss"),
                "take_profit": sig.get("take_profit"),
                "horizon_days": sig.get("horizon_days"),
                **ev,
            })

    aggregates = _aggregate(results)
    from datetime import datetime, timezone
    track_record = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "signals": results,
        "aggregates": aggregates,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(track_record, indent=2, ensure_ascii=False), encoding="utf-8")

    if aggregates["resolved"] == 0:
        print(f"{aggregates['total']} Signale ausgewertet – noch keine aufgeloesten Signale "
              f"(alle 'open'). track_record.json geschrieben.")
    else:
        print(f"{aggregates['total']} Signale: {aggregates['resolved']} aufgeloest "
              f"(TP {aggregates['tp']} / SL {aggregates['sl']} / expired {aggregates['expired']}), "
              f"Trefferquote {aggregates['hit_rate']}, Ø R {aggregates['avg_R']}. "
              f"track_record.json geschrieben.")


if __name__ == "__main__":
    main()
