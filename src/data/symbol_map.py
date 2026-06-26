# src/data/symbol_map.py
"""Watchlist-Klassifikation und Symbol-Mapping (Anzeige -> Twelve Data)."""
from __future__ import annotations
import json
from pathlib import Path

ASSET_TRACK = {
    "index": "technical", "forex": "technical", "crypto": "technical",
    "energy": "technical", "metal": "technical", "stock": "fundamental",
}

def track_for(asset_class: str) -> str:
    try:
        return ASSET_TRACK[asset_class]
    except KeyError:
        raise ValueError(f"Unbekannte Assetklasse: {asset_class!r}")

def safe_name(symbol: str) -> str:
    """Dateisystem-sicherer Name (EUR/USD -> EUR-USD)."""
    return symbol.replace("/", "-")
