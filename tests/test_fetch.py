# tests/test_fetch.py
import json
from pathlib import Path
from src.data import fetch

class FakeClient:
    def __init__(self, fail_symbols=()):
        self.fail = set(fail_symbols)
        self.seen = set()
    def quote(self, symbol, exchange=None):
        self.seen.add(symbol)
        if symbol in self.fail:
            raise RuntimeError("unsupported")
        return {"price": 1.0, "change_pct": 0.5, "currency": "USD"}
    def time_series(self, symbol, interval="1day", outputsize=250, exchange=None):
        self.seen.add(symbol)
        return [{"datetime": "2026-06-26", "close": "1.0"}]

def _entry(display, td, ac, track, source="twelvedata", api_symbol=None):
    return {"display": display, "td_symbol": td, "asset_class": ac,
            "track": track, "exchange": None, "enabled": True,
            "source": source, "api_symbol": api_symbol or td}

def test_fetch_symbol_ok():
    rec = fetch.fetch_symbol(FakeClient(), _entry("EUR/USD", "EUR/USD", "forex", "technical"), "2026-06-26")
    assert rec["available"] is True
    assert rec["snapshot"]["price"] == 1.0
    assert len(rec["time_series"]) == 1
    assert rec["source"] == "twelvedata"
    assert rec["api_symbol"] == "EUR/USD"

def test_fetch_symbol_uses_api_symbol():
    # api_symbol differs from td_symbol -> client must be called with api_symbol
    e = _entry("GER40", "DAX", "index", "technical", source="yahoo", api_symbol="^GDAXI")
    client = FakeClient(fail_symbols={"DAX"})  # would fail if td_symbol used
    rec = fetch.fetch_symbol(client, e, "2026-06-26")
    assert rec["available"] is True
    assert rec["source"] == "yahoo"
    assert rec["api_symbol"] == "^GDAXI"

def test_fetch_symbol_unavailable():
    rec = fetch.fetch_symbol(FakeClient(fail_symbols={"UKX"}),
                             _entry("FTSE100", "UKX", "index", "technical", api_symbol="UKX"), "2026-06-26")
    assert rec["available"] is False
    assert "unsupported" in rec["error"]
    assert rec["error"].startswith("RuntimeError:")

def test_fetch_all_routes_by_source(tmp_path):
    wl = [_entry("EUR/USD", "EUR/USD", "forex", "technical", source="twelvedata"),
          _entry("GER40", "DAX", "index", "technical", source="yahoo", api_symbol="^GDAXI")]
    td = FakeClient()
    yh = FakeClient()
    cov = fetch.fetch_all(wl, {"twelvedata": td, "yahoo": yh}, tmp_path, "2026-06-26")
    assert cov["EUR/USD"] is True and cov["GER40"] is True
    # yahoo client got the yahoo symbol
    assert yh.seen == {"^GDAXI"}
    assert td.seen == {"EUR/USD"}
    f = tmp_path / "EUR-USD" / "raw-2026-06-26.json"
    assert f.exists()
    rec = json.loads(f.read_text(encoding="utf-8"))
    assert rec["snapshot"]["price"] == 1.0
    g = tmp_path / "GER40" / "raw-2026-06-26.json"
    assert json.loads(g.read_text(encoding="utf-8"))["source"] == "yahoo"


def test_fetch_all_adds_earnings_date_for_stocks(tmp_path):
    class YahooWithEarnings(FakeClient):
        def earnings_date(self, symbol):
            return "2026-07-28"
    clients = {"twelvedata": FakeClient(), "yahoo": YahooWithEarnings()}
    from src.data.fetch import fetch_all
    import json
    wl = [
        _entry("APPLE", "AAPL", "stock", "fundamental"),
        _entry("EUR/USD", "EUR/USD", "forex", "technical"),
    ]
    fetch_all(wl, clients, tmp_path, "2026-07-05")
    apple = json.loads((tmp_path / "APPLE" / "raw-2026-07-05.json").read_text(encoding="utf-8"))
    fx = json.loads((tmp_path / "EUR-USD" / "raw-2026-07-05.json").read_text(encoding="utf-8"))
    assert apple["earnings_date"] == "2026-07-28"
    assert "earnings_date" not in fx or fx["earnings_date"] is None
