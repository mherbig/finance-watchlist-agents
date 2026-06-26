# src/data/fetch.py
"""Roh-Abzug pro Symbol + Coverage-Report."""
from __future__ import annotations
import json
from pathlib import Path
from .symbol_map import safe_name

def fetch_symbol(client, entry, today):
    """Holt Quote + Zeitreihe fuer ein Symbol. Faengt Tier-Luecken ab."""
    rec = {"display": entry["display"], "td_symbol": entry["td_symbol"],
           "asset_class": entry["asset_class"], "track": entry["track"],
           "date": today, "available": True, "error": None,
           "snapshot": None, "time_series": []}
    try:
        rec["snapshot"] = client.quote(entry["td_symbol"], exchange=entry.get("exchange"))
        rec["time_series"] = client.time_series(entry["td_symbol"], exchange=entry.get("exchange"))
    except Exception as ex:  # Tier-/Symbol-Luecke -> markieren, nicht abbrechen
        rec["available"] = False
        rec["error"] = f"{type(ex).__name__}: {ex}"
    return rec

def fetch_all(watchlist, client, out_dir, today):
    """Schreibt data/<safe>/raw-<today>.json je Symbol, liefert Coverage-Map."""
    out_dir = Path(out_dir)
    coverage = {}
    for entry in watchlist:
        rec = fetch_symbol(client, entry, today)
        coverage[entry["display"]] = rec["available"]
        d = out_dir / safe_name(entry["display"])
        d.mkdir(parents=True, exist_ok=True)
        (d / f"raw-{today}.json").write_text(
            json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    return coverage
