# scripts/evaluate_signals.py
"""Forward-Test-Evaluator fuer geloggte Signale.

Liest docs/signals/log.jsonl. Fuer jedes Signal wird der neueste Report des
Symbols geladen und dessen ``time_series`` (taegliche Bars, neueste zuerst)
STRIKT NACH dem Signal-Datum durchlaufen (aelteste -> neueste):

- LONG:  Bar-low  <= stop_loss   -> "sl"
         sonst Bar-high >= take_profit -> "tp"
- SHORT: Bar-high >= stop_loss   -> "sl"
         sonst Bar-low  <= take_profit -> "tp"

Wird innerhalb von ``horizon_days`` Bars keins getroffen -> "expired"
(realized R aus dem letzten Close). Sind noch keine Bars nach dem Signal-Datum
vorhanden (oder fehlt time_series), bleibt das Signal "open".

realized_R = sign * (exit - entry) / abs(entry - stop_loss)
(sign = +1 LONG, -1 SHORT).

Schreibt docs/signals/track_record.json mit Einzelergebnissen + Aggregaten.
Keine Netzwerkaufrufe. Bei Tag 1 (alles open) -> Hinweis ausgeben.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.symbol_map import safe_name  # noqa: E402


def _latest_report(symbol_dir: Path) -> dict | None:
    files = sorted(symbol_dir.glob("*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


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
    denom = abs(entry - stop_loss)
    if denom == 0:
        return None
    sign = 1.0 if direction == "LONG" else -1.0
    return round(sign * (exit_price - entry) / denom, 4)


def _evaluate_one(sig, report) -> dict:
    """Liefert {outcome, exit_price, exit_date, bars_used, realized_R}."""
    direction = sig.get("direction")
    entry = sig.get("entry")
    stop_loss = sig.get("stop_loss")
    take_profit = sig.get("take_profit")
    horizon = sig.get("horizon_days") or 0

    result = {
        "outcome": "open",
        "exit_price": None,
        "exit_date": None,
        "bars_used": 0,
        "realized_R": None,
    }

    # FLAT oder fehlende Zahlen -> nicht auswertbar, bleibt open.
    if direction not in ("LONG", "SHORT") or entry is None or stop_loss is None \
            or take_profit is None:
        return result

    time_series = (report or {}).get("time_series")
    bars = _bars_after(time_series, sig.get("date"))
    if not bars:
        return result  # noch keine Bars nach Signal -> open

    window = bars[:horizon]  # nur die ersten horizon Bars zaehlen
    hit = False
    for bar in window:
        result["bars_used"] += 1
        if direction == "LONG":
            if bar["low"] <= stop_loss:
                result.update(outcome="sl", exit_price=stop_loss, exit_date=bar["datetime"])
                hit = True
                break
            if bar["high"] >= take_profit:
                result.update(outcome="tp", exit_price=take_profit, exit_date=bar["datetime"])
                hit = True
                break
        else:  # SHORT
            if bar["high"] >= stop_loss:
                result.update(outcome="sl", exit_price=stop_loss, exit_date=bar["datetime"])
                hit = True
                break
            if bar["low"] <= take_profit:
                result.update(outcome="tp", exit_price=take_profit, exit_date=bar["datetime"])
                hit = True
                break

    if not hit:
        # Kein SL/TP getroffen. Deckt das Fenster den vollen Horizont ab
        # (>= horizon Bars vorhanden) -> "expired" mit realized R aus letztem
        # Close. Sonst zu wenige Bars -> bleibt "open".
        if len(bars) >= horizon and window:
            last = window[-1]
            result.update(outcome="expired", exit_price=last["close"],
                          exit_date=last["datetime"])

    if result["outcome"] in ("sl", "tp", "expired"):
        result["realized_R"] = _realized_r(direction, result["exit_price"], entry, stop_loss)
    return result


def _aggregate(results, reports_by_symbol) -> dict:
    total = len(results)
    open_n = sum(1 for r in results if r["outcome"] == "open")
    resolved = [r for r in results if r["outcome"] in ("tp", "sl", "expired")]
    tp = sum(1 for r in resolved if r["outcome"] == "tp")
    sl = sum(1 for r in resolved if r["outcome"] == "sl")
    expired = sum(1 for r in resolved if r["outcome"] == "expired")

    rs = [r["realized_R"] for r in resolved if r["realized_R"] is not None]
    avg_R = round(sum(rs) / len(rs), 4) if rs else None
    hit_rate = round(tp / len(resolved), 4) if resolved else None

    by_conviction: dict[str, dict] = {}
    by_asset: dict[str, dict] = {}
    for r in results:
        conv = str(r.get("conviction"))
        bc = by_conviction.setdefault(conv, {"total": 0, "tp": 0, "sl": 0,
                                             "expired": 0, "open": 0, "rs": []})
        bc["total"] += 1
        bc[r["outcome"]] = bc.get(r["outcome"], 0) + 1
        if r["realized_R"] is not None:
            bc["rs"].append(r["realized_R"])

        ac = r.get("asset_class") or "unknown"
        ba = by_asset.setdefault(ac, {"total": 0, "tp": 0, "sl": 0,
                                      "expired": 0, "open": 0, "rs": []})
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
        "hit_rate": hit_rate,
        "avg_R": avg_R,
        "by_conviction": _finish(by_conviction),
        "by_asset_class": _finish(by_asset),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))
    reports_dir = root / settings["reports_dir"]
    log_path = root / "docs" / "signals" / "log.jsonl"
    out_path = root / "docs" / "signals" / "track_record.json"

    if not log_path.exists():
        print(f"Kein Signal-Log gefunden ({log_path}). Nichts auszuwerten.")
        return

    results = []
    report_cache: dict[str, dict | None] = {}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            sig = json.loads(line)
        except json.JSONDecodeError:
            print(f"  WARN: ungueltige Log-Zeile uebersprungen: {line[:60]}")
            continue

        display = sig.get("display") or sig.get("symbol")
        safe = safe_name(str(display)) if display else None
        report = None
        if safe is not None:
            if safe not in report_cache:
                sym_dir = reports_dir / safe
                report_cache[safe] = _latest_report(sym_dir) if sym_dir.is_dir() else None
            report = report_cache[safe]

        ev = _evaluate_one(sig, report)
        results.append({
            "date": sig.get("date"),
            "symbol": sig.get("symbol"),
            "display": display,
            "asset_class": (report or {}).get("asset_class"),
            "direction": sig.get("direction"),
            "conviction": sig.get("conviction"),
            "entry": sig.get("entry"),
            "stop_loss": sig.get("stop_loss"),
            "take_profit": sig.get("take_profit"),
            "horizon_days": sig.get("horizon_days"),
            **ev,
        })

    aggregates = _aggregate(results, report_cache)
    track_record = {
        "generated_at": None,
        "signals": results,
        "aggregates": aggregates,
    }
    from datetime import datetime, timezone
    track_record["generated_at"] = datetime.now(timezone.utc).isoformat()

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
