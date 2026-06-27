# scripts/build_portfolio.py
"""Baut die Depot-Simulation aus dem Signal-Log und schreibt portfolio.json.

Liest docs/signals/log.jsonl. Fuer jeden Eintrag wird die neueste Rohdatei
data/<safe>/raw-*.json geladen (safe_name; data_dir aus settings.json), deren
time_series an portfolio.resolve_trade uebergeben und die aufgeloesten Trades
mit portfolio.simulate zu einer Depot-Simulation verdichtet. Ergebnis ->
docs/signals/portfolio.json.

Fehlt eine Rohdatei, wird der Trade ohne Zukunftsdaten aufgeloest (-> "open").
Keine Netzwerkaufrufe.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.analysis import portfolio  # noqa: E402
from src.data.symbol_map import safe_name  # noqa: E402


def _latest_raw_time_series(data_dir: Path, safe: str) -> list:
    """time_series der neuesten raw-*.json fuer ein Symbol, sonst leer."""
    sym_dir = data_dir / safe
    if not sym_dir.is_dir():
        return []
    files = sorted(sym_dir.glob("raw-*.json"))
    if not files:
        return []
    try:
        raw = json.loads(files[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    ts = raw.get("time_series")
    return ts if isinstance(ts, list) else []


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))
    data_dir = root / settings["data_dir"]
    log_path = root / "docs" / "signals" / "log.jsonl"
    out_path = root / "docs" / "signals" / "portfolio.json"

    if not log_path.exists():
        print(f"Kein Signal-Log gefunden ({log_path}). Nichts zu simulieren.")
        return

    ts_cache: dict[str, list] = {}
    trades = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            print(f"  WARN: ungueltige Log-Zeile uebersprungen: {line[:60]}")
            continue

        display = entry.get("display") or entry.get("symbol")
        safe = safe_name(str(display)) if display else None
        if safe is not None and safe not in ts_cache:
            ts_cache[safe] = _latest_raw_time_series(data_dir, safe)
        time_series = ts_cache.get(safe, [])

        trades.append(portfolio.resolve_trade(entry, time_series))

    result = portfolio.simulate(trades)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    s = result["summary"]
    print(
        f"portfolio.json geschrieben: Depot {s['current_equity']:.2f} $ "
        f"(Start {s['start_equity']:.0f} $, Rendite {s['return_pct']} %)."
    )
    print(
        f"  {s['closed_count']} abgeschlossen "
        f"({s['wins']}W/{s['losses']}L, Trefferquote {s['win_rate']}), "
        f"{s['open_count']} offen."
    )
    for o in result["open"][:3]:
        print(
            f"    OPEN {o['symbol']} {o['direction']} "
            f"entry={o['entry']} SL={o['stop_loss']} "
            f"risk={o['risk_amount']} units={o['units']}"
        )


if __name__ == "__main__":
    main()
