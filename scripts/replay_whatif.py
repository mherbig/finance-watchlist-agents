# scripts/replay_whatif.py
"""CLI: What-if-Replay — geloggte Signale mit alternativen Exit-Regeln.

Loest das Signal-Log wie build_portfolio zur Baseline auf und scannt dann
jeden gefuellten Trade mit mehreren Exit-Politiken neu (src/analysis/whatif).
Druckt eine Vergleichstabelle und schreibt docs/signals/whatif.json.

Je mehr Forward-Test-Tage im Log liegen, desto aussagekraeftiger. Keine
Netzwerkaufrufe.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.analysis import portfolio, whatif  # noqa: E402
from src.data.symbol_map import safe_name  # noqa: E402

POLICIES = {
    "baseline": {},
    "breakeven_1R": {"breakeven_after_r": 1.0},
    "trail_1R": {"trail_r": 1.0},
    "trail_1.5R": {"trail_r": 1.5},
    "be1_trail1.5": {"breakeven_after_r": 1.0, "trail_r": 1.5},
    "tp2_struktur": {"use_tp2": True},
    "horizon_x2": {"horizon_mult": 2.0},
}


def _latest_raw(data_dir: Path, safe: str) -> dict:
    sym_dir = data_dir / safe
    if not sym_dir.is_dir():
        return {}
    files = sorted(sym_dir.glob("raw-*.json"))
    if not files:
        return {}
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))
    data_dir = root / settings["data_dir"]
    log_path = root / "docs" / "signals" / "log.jsonl"
    if not log_path.exists():
        print("Kein Signal-Log gefunden. Nichts zu vergleichen.")
        return

    sig_cfg = settings.get("signals", {})
    flat_closes = bool(sig_cfg.get("flat_closes_position", portfolio.FLAT_CLOSES))
    flat_min_conviction = int(sig_cfg.get("flat_close_min_conviction",
                                          portfolio.FLAT_MIN_CONVICTION))
    flat_consecutive = int(sig_cfg.get("flat_close_consecutive",
                                       portfolio.FLAT_CONSECUTIVE))

    groups: dict[str, list] = {}
    order: list[str] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = entry.get("symbol") or entry.get("display")
        if key is None:
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(entry)

    # Baseline-Trades + zugehoerige Serien.
    baseline: list[tuple[dict, list]] = []   # (trade, time_series)
    for key in order:
        symbol_signals = groups[key]
        display = symbol_signals[0].get("display") or key
        raw = _latest_raw(data_dir, safe_name(str(display)))
        ts = raw.get("time_series") or []
        for t in portfolio.resolve_symbol_trades(
                symbol_signals, ts, flat_closes=flat_closes,
                flat_min_conviction=flat_min_conviction,
                flat_consecutive=flat_consecutive,
                provisional_date=raw.get("date")):
            if t.get("filled") is not False \
                    and t.get("status") not in ("no_fill", "none"):
                baseline.append((t, ts))

    results = {}
    for name, policy in POLICIES.items():
        rows = [whatif.rescan_exit(t, ts, policy) for t, ts in baseline]
        results[name] = whatif.summarize(rows)

    print(f"What-if ueber {len(baseline)} Baseline-Trades "
          f"({sum(1 for t, _ in baseline if t.get('status') != 'open')} bereits beendet):")
    print(f"{'Policy':<15}{'resolved':>9}{'Winrate':>9}{'O R':>8}{'Summe R':>9}")
    for name, s in results.items():
        wr = "-" if s["win_rate"] is None else f"{s['win_rate']:.0%}"
        ar = "-" if s["avg_R"] is None else f"{s['avg_R']:+.2f}"
        print(f"{name:<15}{s['resolved']:>9}{wr:>9}{ar:>8}{s['total_R']:>+9.2f}")

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trades": len(baseline),
        "policies": results,
    }
    out_path = root / "docs" / "signals" / "whatif.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(f"-> {out_path.relative_to(root)}")


if __name__ == "__main__":
    main()
