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

# --- Rohlisten (Quelle: Nutzer-Watchlist) ---
RAW: dict[str, list[str]] = {
    "index": ["GER40", "FTSE100", "NQ100", "WS30", "S&P500", "ASX200",
              "FRA40", "Nikkei225", "HK50"],
    "forex": ["AUD/CAD", "AUD/CHF", "AUD/JPY", "AUD/NZD", "AUD/USD", "CAD/CHF",
              "CAD/JPY", "CHF/JPY", "EUR/AUD", "EUR/CAD", "EUR/CHF", "EUR/GBP",
              "EUR/JPY", "EUR/NZD", "EUR/USD", "GBP/AUD", "GBP/CAD", "GBP/CHF",
              "GBP/JPY", "GBP/NZD", "GBP/USD", "NZD/CAD", "NZD/CHF", "NZD/JPY",
              "NZD/USD", "USD/CAD", "USD/CHF", "USD/JPY"],
    "crypto": ["ADA/USD", "BNB/USD", "BTC/USD", "ETH/USD", "LTC/USD", "SOL/USD",
               "XRP/USD", "DOGE/USD", "XMR/USD", "DASH/USD", "NEO/USD"],
    "energy": ["BRENT", "NATGAS"],
    "metal": ["XAG", "XAU", "XPT", "XPD"],
    "stock": ["QCOM", "JPM", "MICRON", "AMD", "INTEL", "ATNT", "FERRARI",
              "PFIZER", "TSLA", "VISA", "ZM", "META", "MSFT", "NETFLIX",
              "NVIDIA", "ALIBABA", "AMAZON", "APPLE", "BOA", "GOOGLE",
              "AIR", "ALLI", "BAYER", "IBER", "LVMH", "VOWGE"],
}

# --- Anzeige -> Twelve-Data-Symbol (nur wo abweichend) ---
# UNSICHER markierte Indizes/Energie werden vom Coverage-Probe (Task 6) geprueft.
MAPPING: dict[str, str] = {
    # US-Aktien
    "MICRON": "MU", "INTEL": "INTC", "ATNT": "T", "FERRARI": "RACE",
    "PFIZER": "PFE", "VISA": "V", "NETFLIX": "NFLX", "NVIDIA": "NVDA",
    "ALIBABA": "BABA", "AMAZON": "AMZN", "APPLE": "AAPL", "BOA": "BAC",
    "GOOGLE": "GOOGL",
    # EU-Aktien
    "AIR": "AIR", "ALLI": "ALV", "BAYER": "BAYN", "IBER": "IBE",
    "LVMH": "MC", "VOWGE": "VOW3",
    # Indizes (UNSICHER -> Probe)
    "GER40": "DAX", "FTSE100": "UKX", "NQ100": "NDX", "WS30": "DJI",
    "S&P500": "SPX", "ASX200": "AS51", "FRA40": "CAC40", "Nikkei225": "N225",
    "HK50": "HSI",
    # Metalle
    "XAG": "XAG/USD", "XAU": "XAU/USD", "XPT": "XPT/USD", "XPD": "XPD/USD",
    # Energie (UNSICHER -> Probe)
    "BRENT": "BRENT", "NATGAS": "NATGAS",
}

# Boersenplatz fuer EU-Aktien (Twelve Data `exchange`-Parameter)
EXCHANGE: dict[str, str] = {
    "AIR": "Euronext Paris", "ALLI": "XETRA", "BAYER": "XETRA",
    "IBER": "BME", "LVMH": "Euronext Paris", "VOWGE": "XETRA",
}

def td_symbol_for(display: str) -> str:
    return MAPPING.get(display, display)

# --- Anzeige -> Yahoo-Finance-Symbol (zweite Datenquelle) ---
# Diese 17 Instrumente liefert der Twelve-Data-Free-Tarif nicht (Indizes/Energie
# brauchen einen Pro-Plan, EU-Aktien liefern 404). Yahoo deckt sie ab.
YAHOO_SYMBOL: dict[str, str] = {
    "GER40": "^GDAXI", "FTSE100": "^FTSE", "NQ100": "^NDX", "WS30": "^DJI",
    "S&P500": "^GSPC", "ASX200": "^AXJO", "FRA40": "^FCHI", "Nikkei225": "^N225",
    "HK50": "^HSI",
    "BRENT": "BZ=F", "NATGAS": "NG=F",
    "AIR": "AIR.PA", "ALLI": "ALV.DE", "BAYER": "BAYN.DE", "IBER": "IBE.MC",
    "LVMH": "MC.PA", "VOWGE": "VOW3.DE",
}

def _source_for(display: str, asset_class: str) -> str:
    """Indizes/Energie und EU-Aktien -> Yahoo, alles andere -> Twelve Data."""
    if asset_class in {"index", "energy"}:
        return "yahoo"
    if asset_class == "stock" and display in EXCHANGE:  # EU-Aktien
        return "yahoo"
    return "twelvedata"

def build_watchlist_entries() -> list[dict]:
    entries: list[dict] = []
    for asset_class, displays in RAW.items():
        for display in displays:
            source = _source_for(display, asset_class)
            api_symbol = YAHOO_SYMBOL[display] if source == "yahoo" else td_symbol_for(display)
            entries.append({
                "display": display,
                "td_symbol": td_symbol_for(display),
                "asset_class": asset_class,
                "track": track_for(asset_class),
                "exchange": EXCHANGE.get(display),
                "enabled": True,
                "source": source,
                "api_symbol": api_symbol,
            })
    return entries

_REQUIRED = {"display", "td_symbol", "asset_class", "track", "exchange",
             "enabled", "source", "api_symbol"}

def load_watchlist(path: str | Path) -> list[dict]:
    """Liest watchlist.json, validiert Felder, gibt nur aktive Eintraege zurueck."""
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    for e in entries:
        missing = _REQUIRED - set(e)
        if missing:
            raise ValueError(f"Watchlist-Eintrag {e.get('display','?')}: fehlende Felder {missing}")
    return [e for e in entries if e.get("enabled")]
