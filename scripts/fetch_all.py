# scripts/fetch_all.py
"""CLI: laedt .env, baut Client, holt Rohdaten, druckt Coverage-Report."""
import json
import os
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402
from src.data.symbol_map import load_watchlist  # noqa: E402
from src.data.twelvedata_client import TwelveDataClient  # noqa: E402
from src.data.fetch import fetch_all  # noqa: E402

def main() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    key = os.environ.get("TWELVEDATA_API_KEY")
    if not key:
        print("FEHLER: TWELVEDATA_API_KEY fehlt (.env).")
        sys.exit(1)
    settings = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))
    today = date.today().isoformat()
    wl = load_watchlist(root / "config" / "watchlist.json")
    client = TwelveDataClient(
        api_key=key, cache_dir=root / settings["cache_dir"],
        min_interval_s=settings["twelvedata"]["min_interval_seconds"], today=today)
    coverage = fetch_all(wl, client, root / settings["data_dir"], today)
    ok = [d for d, v in coverage.items() if v]
    bad = [d for d, v in coverage.items() if not v]
    print(f"\nCoverage {today}: {len(ok)}/{len(coverage)} verfuegbar")
    if bad:
        print("NICHT verfuegbar (Tier/Symbol pruefen): " + ", ".join(bad))

if __name__ == "__main__":
    main()
