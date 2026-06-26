# tests/test_symbol_map.py
from src.data import symbol_map as sm

def test_track_for_stock_is_fundamental():
    assert sm.track_for("stock") == "fundamental"

def test_track_for_forex_is_technical():
    assert sm.track_for("forex") == "technical"

def test_safe_name_replaces_slash():
    assert sm.safe_name("EUR/USD") == "EUR-USD"
    assert sm.safe_name("AAPL") == "AAPL"

def test_build_watchlist_has_all_symbols():
    entries = sm.build_watchlist_entries()
    # 9 idx + 28 fx + 11 crypto + 2 energy + 4 metal + 20 us + 6 eu = 80
    assert len(entries) == 80

def test_build_watchlist_maps_known_tickers():
    by_display = {e["display"]: e for e in sm.build_watchlist_entries()}
    assert by_display["MICRON"]["td_symbol"] == "MU"
    assert by_display["GOOGLE"]["td_symbol"] == "GOOGL"
    assert by_display["XAU"]["td_symbol"] == "XAU/USD"
    assert by_display["EUR/USD"]["td_symbol"] == "EUR/USD"

def test_build_watchlist_tracks_correct():
    by_display = {e["display"]: e for e in sm.build_watchlist_entries()}
    assert by_display["APPLE"]["track"] == "fundamental"
    assert by_display["BTC/USD"]["track"] == "technical"

def test_build_watchlist_entry_shape():
    e = sm.build_watchlist_entries()[0]
    assert set(e) == {"display", "td_symbol", "asset_class", "track", "exchange", "enabled"}

import json as _json

def test_load_watchlist_filters_disabled(tmp_path):
    p = tmp_path / "wl.json"
    p.write_text(_json.dumps([
        {"display": "A", "td_symbol": "A", "asset_class": "stock",
         "track": "fundamental", "exchange": None, "enabled": True},
        {"display": "B", "td_symbol": "B", "asset_class": "stock",
         "track": "fundamental", "exchange": None, "enabled": False},
    ]), encoding="utf-8")
    wl = sm.load_watchlist(p)
    assert [e["display"] for e in wl] == ["A"]

def test_load_watchlist_rejects_missing_field(tmp_path):
    p = tmp_path / "wl.json"
    p.write_text(_json.dumps([{"display": "A", "enabled": True}]), encoding="utf-8")
    try:
        sm.load_watchlist(p)
        assert False, "sollte ValueError werfen"
    except ValueError:
        pass

def test_committed_watchlist_matches_builder():
    import json as _json
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "config" / "watchlist.json"
    on_disk = _json.loads(p.read_text(encoding="utf-8"))
    assert on_disk == sm.build_watchlist_entries()
