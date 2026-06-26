# tests/test_symbol_map.py
from src.data import symbol_map as sm

def test_track_for_stock_is_fundamental():
    assert sm.track_for("stock") == "fundamental"

def test_track_for_forex_is_technical():
    assert sm.track_for("forex") == "technical"

def test_safe_name_replaces_slash():
    assert sm.safe_name("EUR/USD") == "EUR-USD"
    assert sm.safe_name("AAPL") == "AAPL"
