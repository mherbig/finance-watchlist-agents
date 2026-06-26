# tests/test_fetch.py
import json
from pathlib import Path
from src.data import fetch

class FakeClient:
    def __init__(self, fail_symbols=()):
        self.fail = set(fail_symbols)
    def quote(self, symbol, exchange=None):
        if symbol in self.fail:
            raise RuntimeError("unsupported")
        return {"price": 1.0, "change_pct": 0.5, "currency": "USD"}
    def time_series(self, symbol, interval="1day", outputsize=250, exchange=None):
        return [{"datetime": "2026-06-26", "close": "1.0"}]

def _entry(display, td, ac, track):
    return {"display": display, "td_symbol": td, "asset_class": ac,
            "track": track, "exchange": None, "enabled": True}

def test_fetch_symbol_ok():
    rec = fetch.fetch_symbol(FakeClient(), _entry("EUR/USD", "EUR/USD", "forex", "technical"), "2026-06-26")
    assert rec["available"] is True
    assert rec["snapshot"]["price"] == 1.0
    assert len(rec["time_series"]) == 1

def test_fetch_symbol_unavailable():
    rec = fetch.fetch_symbol(FakeClient(fail_symbols={"UKX"}), _entry("FTSE100", "UKX", "index", "technical"), "2026-06-26")
    assert rec["available"] is False
    assert "unsupported" in rec["error"]

def test_fetch_all_writes_and_coverage(tmp_path):
    wl = [_entry("EUR/USD", "EUR/USD", "forex", "technical"),
          _entry("FTSE100", "UKX", "index", "technical")]
    cov = fetch.fetch_all(wl, FakeClient(fail_symbols={"UKX"}), tmp_path, "2026-06-26")
    assert cov["EUR/USD"] is True and cov["FTSE100"] is False
    f = tmp_path / "EUR-USD" / "raw-2026-06-26.json"
    assert f.exists()
    assert json.loads(f.read_text(encoding="utf-8"))["snapshot"]["price"] == 1.0
