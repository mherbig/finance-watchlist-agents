# scripts/build_watchlist.py
"""Schreibt config/watchlist.json aus den Rohlisten in symbol_map."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.symbol_map import build_watchlist_entries  # noqa: E402

def main() -> None:
    out = Path(__file__).resolve().parents[1] / "config" / "watchlist.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    entries = build_watchlist_entries()
    out.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(entries)} Symbole -> {out}")

if __name__ == "__main__":
    main()
