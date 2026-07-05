# src/data/fetch.py
"""Roh-Abzug pro Symbol + Coverage-Report."""
from __future__ import annotations
import json
from pathlib import Path
from .symbol_map import safe_name, YAHOO_SYMBOL

def fetch_symbol(client, entry, today):
    """Holt Quote + Zeitreihe fuer ein Symbol. Faengt Tier-Luecken ab.

    Nutzt `api_symbol` (Yahoo- oder Twelve-Data-Symbol je nach `source`).
    """
    api_symbol = entry["api_symbol"]
    rec = {"display": entry["display"], "td_symbol": entry["td_symbol"],
           "api_symbol": api_symbol, "source": entry["source"],
           "asset_class": entry["asset_class"], "track": entry["track"],
           "date": today, "available": True, "error": None,
           "snapshot": None, "time_series": []}
    try:
        rec["snapshot"] = client.quote(api_symbol, exchange=entry.get("exchange"))
        rec["time_series"] = client.time_series(api_symbol, exchange=entry.get("exchange"))
    except Exception as ex:  # Tier-/Symbol-Luecke -> markieren, nicht abbrechen
        rec["available"] = False
        rec["error"] = f"{type(ex).__name__}: {ex}"
    return rec

def fetch_all(watchlist, clients, out_dir, today):
    """Schreibt data/<safe>/raw-<today>.json je Symbol, liefert Coverage-Map.

    `clients` ist ein Dict {source: client_instance}.
    """
    out_dir = Path(out_dir)
    coverage = {}
    for entry in watchlist:
        client = clients[entry["source"]]
        rec = fetch_symbol(client, entry, today)
        # Earnings-Termin (nur Aktien, best-effort via Yahoo; None bei Fehlern).
        if entry.get("asset_class") == "stock":
            yc = clients.get("yahoo")
            if yc is not None and hasattr(yc, "earnings_date"):
                ysym = YAHOO_SYMBOL.get(entry["display"], entry["td_symbol"])
                rec["earnings_date"] = yc.earnings_date(ysym)
        coverage[entry["display"]] = rec["available"]
        d = out_dir / safe_name(entry["display"])
        d.mkdir(parents=True, exist_ok=True)
        (d / f"raw-{today}.json").write_text(
            json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    return coverage
