from tests.conftest import FakeResponse, FakeSession
from src.data.twelvedata_client import TwelveDataClient

def _client(tmp_path, responses):
    sleeps = []
    c = TwelveDataClient(
        api_key="k", cache_dir=tmp_path / "c", min_interval_s=8,
        session=FakeSession(responses), sleep=sleeps.append, today="2026-06-26",
    )
    return c, sleeps

def test_get_caches_second_call(tmp_path):
    c, _ = _client(tmp_path, [FakeResponse({"price": "1.0"})])
    a = c._get("quote", {"symbol": "EUR/USD"})
    b = c._get("quote", {"symbol": "EUR/USD"})  # darf nicht erneut HTTP rufen
    assert a == b == {"price": "1.0"}
    assert len(c.session.calls) == 1

def test_rate_limit_sleeps_between_distinct_calls(tmp_path):
    c, sleeps = _client(tmp_path, [FakeResponse({"a": 1}), FakeResponse({"b": 2})])
    c._get("quote", {"symbol": "AAA"})
    c._get("quote", {"symbol": "BBB"})
    assert sleeps and sleeps[0] > 0  # vor zweitem Call gewartet

def test_get_raises_on_api_error(tmp_path):
    c, _ = _client(tmp_path, [FakeResponse({"status": "error", "message": "nope"})])
    try:
        c._get("quote", {"symbol": "X"})
        assert False, "sollte werfen"
    except RuntimeError as ex:
        assert "nope" in str(ex)
