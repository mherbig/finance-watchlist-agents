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
