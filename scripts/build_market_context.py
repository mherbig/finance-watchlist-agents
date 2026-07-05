# scripts/build_market_context.py
"""CLI: baut den taeglichen Markt-Kontext fuer die Signal-Judges.

Liest die neuesten Rohdaten der Anker-Symbole (S&P500, GER40, BTC/USD, XAU,
EUR/USD) plus aller Watchlist-Symbole (Vol-Regime) und schreibt
docs/signals/market_context.json. Die Judges lesen die Datei als kompakten
Makro-Ueberblick (Trend der Leitmaerkte + Volatilitaets-Regime).

Rein deterministisch aus vorhandenen Rohdaten. Keine Netzwerkaufrufe.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.analysis.technical import compute_technical  # noqa: E402
from src.data.symbol_map import safe_name, load_watchlist  # noqa: E402

# Leitmaerkte: Aktien USA/EU, Krypto, Gold, USD-Proxy.
ANCHORS = ["S&P500", "GER40", "NQ100", "BTC/USD", "XAU", "EUR/USD"]


def _build_context(records: dict) -> dict:
    """Kontext-Dict aus display -> Roh-Record (mit time_series)."""
    anchors = {}
    atr_pcts = []
    for display, raw in records.items():
        ts = raw.get("time_series")
        if not isinstance(ts, list) or not ts:
            continue
        t = compute_technical(ts)
        last = t.get("last_close")
        if t.get("atr14") and last:
            atr_pcts.append(t["atr14"] / last * 100.0)
        if display in ANCHORS or len(records) <= len(ANCHORS):
            anchors[display] = {
                "trend": t.get("trend"),
                "weekly_trend": (t.get("weekly") or {}).get("trend"),
                "change_pct": round(t.get("change_pct") or 0.0, 2),
                "rsi14": t.get("rsi14"),
            }
    atr_pcts.sort()
    n = len(atr_pcts)
    median = atr_pcts[n // 2] if n else None
    return {
        "anchors": anchors,
        "vol_regime": {
            "symbols": n,
            "median_atr_pct": round(median, 3) if median is not None else None,
        },
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))
    data_dir = root / settings["data_dir"]

    records: dict = {}
    for e in load_watchlist(root / "config" / "watchlist.json"):
        display = e["display"]
        sym_dir = data_dir / safe_name(display)
        if not sym_dir.is_dir():
            continue
        files = sorted(sym_dir.glob("raw-*.json"))
        if not files:
            continue
        try:
            records[display] = json.loads(files[-1].read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

    ctx = _build_context(records)
    ctx["generated_at"] = datetime.now(timezone.utc).isoformat()

    out = root / "docs" / "signals" / "market_context.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ctx, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print(f"Markt-Kontext ({len(ctx['anchors'])} Anker, "
          f"{ctx['vol_regime']['symbols']} Symbole) -> {out.relative_to(root)}")


if __name__ == "__main__":
    main()
