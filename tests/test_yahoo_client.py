from tests.conftest import FakeResponse, FakeSession
from src.data.yahoo_client import YahooClient

def _client(tmp_path, responses):
    sleeps = []
    c = YahooClient(
        cache_dir=tmp_path / "c", min_interval_s=1,
        session=FakeSession(responses), sleep=sleeps.append, today="2026-06-26",
    )
    return c, sleeps

def _chart(meta=None, timestamps=None, quote=None, error=None):
    return {"chart": {
        "error": error,
        "result": None if error else [{
            "meta": meta or {},
            "timestamp": timestamps or [],
            "indicators": {"quote": [quote or {}]},
        }],
    }}

def test_get_caches_second_call(tmp_path):
    payload = _chart(meta={"regularMarketPrice": 1.0}, timestamps=[1], quote={"close": [1.0]})
    c, _ = _client(tmp_path, [FakeResponse(payload)])
    a = c._get("^GDAXI")
    b = c._get("^GDAXI")  # darf nicht erneut HTTP rufen
    assert a == b
    assert len(c.session.calls) == 1

def test_get_url_encodes_caret(tmp_path):
    payload = _chart(meta={"regularMarketPrice": 1.0}, timestamps=[1], quote={"close": [1.0]})
    c, _ = _client(tmp_path, [FakeResponse(payload)])
    c._get("^GDAXI")
    url = c.session.calls[0][0]
    assert "%5EGDAXI" in url
    assert "^" not in url

def test_get_sends_user_agent_header(tmp_path):
    payload = _chart(meta={"regularMarketPrice": 1.0}, timestamps=[1], quote={"close": [1.0]})
    sess = FakeSession([FakeResponse(payload)])
    captured = {}
    orig = sess.get
    def spy(url, params=None, timeout=None, headers=None):
        captured["headers"] = headers
        return orig(url, params=params, timeout=timeout, headers=headers)
    sess.get = spy
    c = YahooClient(cache_dir=tmp_path / "c", session=sess, sleep=lambda s: None, today="2026-06-26")
    c._get("AAPL")
    assert captured["headers"]["User-Agent"].startswith("Mozilla")

def test_rate_limit_sleeps_between_distinct_calls(tmp_path):
    p1 = _chart(meta={"regularMarketPrice": 1.0}, timestamps=[1], quote={"close": [1.0]})
    p2 = _chart(meta={"regularMarketPrice": 2.0}, timestamps=[1], quote={"close": [2.0]})
    c, sleeps = _client(tmp_path, [FakeResponse(p1), FakeResponse(p2)])
    c._get("AAA")
    c._get("BBB")
    assert sleeps and sleeps[0] > 0

def test_get_raises_on_chart_error(tmp_path):
    payload = _chart(error={"code": "Not Found", "description": "no"})
    c, _ = _client(tmp_path, [FakeResponse(payload)])
    try:
        c._get("BADSYM")
        assert False, "sollte werfen"
    except RuntimeError as ex:
        assert "Yahoo Fehler" in str(ex)
        assert "Not Found" in str(ex)

def test_error_not_cached(tmp_path):
    bad = _chart(error={"code": "Not Found"})
    good = _chart(meta={"regularMarketPrice": 5.0}, timestamps=[1], quote={"close": [5.0]})
    c, _ = _client(tmp_path, [FakeResponse(bad), FakeResponse(good)])
    try:
        c._get("X")
    except RuntimeError:
        pass
    r = c._get("X")  # zweiter Versuch -> erneuter HTTP-Call
    assert r["meta"]["regularMarketPrice"] == 5.0
    assert len(c.session.calls) == 2

def test_quote_parses_price_change_currency(tmp_path):
    # Tagesaenderung aus den letzten zwei Tageskerzen (100 -> 110 = +10%).
    payload = _chart(
        meta={"regularMarketPrice": 110.0, "currency": "EUR"},
        timestamps=[1, 2], quote={"close": [100.0, 110.0]},
    )
    c, _ = _client(tmp_path, [FakeResponse(payload)])
    q = c.quote("ALV.DE")
    assert q["price"] == 110.0
    assert q["change_pct"] == 10.0
    assert q["currency"] == "EUR"

def test_quote_ignores_chart_previous_close(tmp_path):
    # Regression: bei range=1y ist chartPreviousClose der Schluss vor 1 Jahr.
    # change_pct MUSS aus den letzten zwei Tageskerzen kommen (+10%), nicht +120%.
    payload = _chart(
        meta={"regularMarketPrice": 110.0, "chartPreviousClose": 50.0, "currency": "USD"},
        timestamps=[1, 2], quote={"close": [100.0, 110.0]},
    )
    c, _ = _client(tmp_path, [FakeResponse(payload)])
    assert c.quote("X")["change_pct"] == 10.0

def test_quote_uses_meta_previous_close_when_present(tmp_path):
    payload = _chart(
        meta={"regularMarketPrice": 110.0, "previousClose": 100.0, "currency": "USD"},
        timestamps=[1, 2], quote={"close": [1.0, 2.0]},
    )
    c, _ = _client(tmp_path, [FakeResponse(payload)])
    assert c.quote("X")["change_pct"] == 10.0

def test_quote_change_pct_zero_when_prev_falsy(tmp_path):
    payload = _chart(
        meta={"regularMarketPrice": 110.0, "chartPreviousClose": 0, "currency": "USD"},
        timestamps=[1], quote={"close": [110.0]},
    )
    c, _ = _client(tmp_path, [FakeResponse(payload)])
    q = c.quote("X")
    assert q["change_pct"] == 0.0

def test_time_series_newest_first_and_date_conversion(tmp_path):
    # 2021-01-01 00:00:00 UTC = 1609459200 ; +1 day = 1609545600
    payload = _chart(
        meta={"regularMarketPrice": 2.0},
        timestamps=[1609459200, 1609545600],
        quote={"open": [1.0, 2.0], "high": [1.5, 2.5], "low": [0.5, 1.5],
               "close": [1.2, 2.2], "volume": [100, 200]},
    )
    c, _ = _client(tmp_path, [FakeResponse(payload)])
    ts = c.time_series("X")
    assert ts[0]["datetime"] == "2021-01-02"  # newest first
    assert ts[1]["datetime"] == "2021-01-01"
    assert ts[0]["close"] == "2.2"
    assert ts[0]["open"] == "2.0"
    assert isinstance(ts[0]["volume"], str)

def test_time_series_skips_null_close_bars(tmp_path):
    payload = _chart(
        meta={"regularMarketPrice": 2.0},
        timestamps=[1609459200, 1609545600, 1609632000],
        quote={"open": [1.0, None, 3.0], "high": [1.5, None, 3.5],
               "low": [0.5, None, 2.5], "close": [1.2, None, 3.2],
               "volume": [100, None, 300]},
    )
    c, _ = _client(tmp_path, [FakeResponse(payload)])
    ts = c.time_series("X")
    assert len(ts) == 2
    assert [b["close"] for b in ts] == ["3.2", "1.2"]  # null bar skipped, newest first

def test_time_series_trims_to_outputsize(tmp_path):
    n = 10
    payload = _chart(
        meta={"regularMarketPrice": 2.0},
        timestamps=[1609459200 + i * 86400 for i in range(n)],
        quote={"open": list(range(n)), "high": list(range(n)),
               "low": list(range(n)), "close": list(range(n)),
               "volume": list(range(n))},
    )
    c, _ = _client(tmp_path, [FakeResponse(payload)])
    ts = c.time_series("X", outputsize=3)
    assert len(ts) == 3
    # most recent 3 -> closes 9,8,7 newest-first
    assert [b["close"] for b in ts] == ["9", "8", "7"]
