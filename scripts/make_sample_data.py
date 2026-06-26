# scripts/make_sample_data.py
"""CLI: erzeugt synthetische, aber plausible Rohdaten je Watchlist-Symbol.

Macht das Dashboard OHNE API-Key betrachtbar. Schreibt Records in derselben Form
wie src/data/fetch.py (available=True) nach data/<safe_name>/raw-<heute>.json.
Pro Symbol deterministisch geseedet -> stabile Ergebnisse.
"""
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.symbol_map import safe_name, load_watchlist  # noqa: E402

N_BARS = 250

# Grobe Basispreis-Spannen je Assetklasse (plausibel, nicht echt).
BASE_RANGES = {
    "index": (3000.0, 20000.0),
    "forex": (0.6, 1.6),
    "crypto": (0.2, 60000.0),
    "energy": (2.0, 95.0),
    "metal": (25.0, 2400.0),
    "stock": (20.0, 500.0),
}


def _base_price(rng: random.Random, asset_class: str, display: str) -> float:
    lo, hi = BASE_RANGES.get(asset_class, (20.0, 500.0))
    if asset_class == "crypto":
        # Crypto stark spreizen: kleine Coins vs. BTC
        if display.startswith(("BTC", "ETH")):
            lo, hi = 1500.0, 60000.0
        else:
            lo, hi = 0.2, 600.0
    return rng.uniform(lo, hi)


def _build_series(display: str, asset_class: str, today: date) -> dict:
    rng = random.Random(hash(display) & 0xFFFFFFFF)
    price = _base_price(rng, asset_class, display)
    # taeglicher Drift + Volatilitaet (relativ)
    vol = rng.uniform(0.005, 0.02)
    drift = rng.uniform(-0.0005, 0.0008)

    closes = []
    for _ in range(N_BARS):
        step = drift + rng.gauss(0, vol)
        price = max(price * (1.0 + step), 1e-6)
        closes.append(price)

    bars = []  # oldest-first aufbauen, danach umdrehen
    for i, close in enumerate(closes):
        prev = closes[i - 1] if i > 0 else close
        open_ = prev
        intrabar = abs(rng.gauss(0, vol)) * close
        high = max(open_, close) + intrabar
        low = min(open_, close) - intrabar
        low = max(low, 1e-6)
        volume = int(rng.uniform(1_000, 5_000_000))
        bar_date = today - timedelta(days=(N_BARS - 1 - i))

        def fmt(x: float) -> str:
            # Forex/Crypto-Kleinpreise mehr Nachkommastellen
            return f"{x:.5f}" if x < 10 else f"{x:.2f}"

        bars.append({
            "datetime": bar_date.isoformat(),
            "open": fmt(open_),
            "high": fmt(high),
            "low": fmt(low),
            "close": fmt(close),
            "volume": str(volume),
        })

    bars.reverse()  # neueste zuerst (Form wie fetch.py)

    last_close = float(bars[0]["close"])
    prev_close = float(bars[1]["close"]) if len(bars) > 1 else last_close
    change_pct = (last_close - prev_close) / prev_close * 100.0 if prev_close else 0.0

    snapshot = {
        "price": last_close,
        "change_pct": round(change_pct, 4),
        "currency": "USD",
    }
    return {"time_series": bars, "snapshot": snapshot}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))
    data_dir = root / settings["data_dir"]
    today = date.today()
    today_iso = today.isoformat()

    wl = load_watchlist(root / "config" / "watchlist.json")

    written = 0
    for entry in wl:
        display = entry["display"]
        asset_class = entry["asset_class"]
        series = _build_series(display, asset_class, today)
        rec = {
            "display": display,
            "td_symbol": entry["td_symbol"],
            "asset_class": asset_class,
            "track": entry["track"],
            "date": today_iso,
            "available": True,
            "error": None,
            "snapshot": series["snapshot"],
            "time_series": series["time_series"],
        }
        d = data_dir / safe_name(display)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"raw-{today_iso}.json").write_text(
            json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
        written += 1

    print(f"{written} Symbole mit synthetischen Rohdaten geschrieben (raw-{today_iso}.json).")


if __name__ == "__main__":
    main()
