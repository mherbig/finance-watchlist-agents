# tests/test_public_sources.py
from tests.conftest import FakeResponse, FakeSession
from src.data import public_sources as ps

def test_recent_filings_parses(monkeypatch):
    submissions = {"filings": {"recent": {
        "form": ["10-Q", "8-K"],
        "filingDate": ["2026-05-01", "2026-04-15"],
        "primaryDocument": ["q.htm", "k.htm"],
        "accessionNumber": ["0000-1", "0000-2"],
    }}}
    sess = FakeSession([FakeResponse(submissions)])
    out = ps.sec_recent_filings(cik="0000320193", session=sess, limit=2)
    assert out[0]["form"] == "10-Q"
    assert out[0]["date"] == "2026-05-01"
    assert len(out) == 2

def test_recent_filings_none_cik_returns_empty():
    assert ps.sec_recent_filings(cik=None, session=None) == []
