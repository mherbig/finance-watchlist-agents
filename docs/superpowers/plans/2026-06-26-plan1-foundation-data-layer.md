# Plan 1 — Fundament & Datenschicht — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repo-Gerüst, vollständige Watchlist-Config und eine getestete Datenschicht (Twelve Data + SEC EDGAR), die für jedes Symbol Rohdaten holt, cached und einen Tier-Abdeckungsbericht erzeugt.

**Architecture:** Reine Python-Datenschicht ohne Agents. `symbol_map` definiert Mapping/Klassifikation und baut `config/watchlist.json`. `twelvedata_client` holt rate-limitiert + gecacht Kurse/Zeitreihen. `public_sources` holt SEC-Filings. `fetch` orchestriert den Roh-Abzug pro Symbol nach `data/<SYMBOL>/raw-<datum>.json` und liefert eine Coverage-Map (welche Symbole der API-Tier unterstützt).

**Tech Stack:** Python 3.12 (`python` / `py`), pytest, requests, python-dotenv. Tests mocken HTTP — keine echten API-Calls in Unit-Tests. Ein optionaler Integrations-Smoke-Test ist per `TWELVEDATA_API_KEY` gegated.

> **Roadmap (Folgepläne, separat):**
> - **Plan 2 — Analyse & Agents:** technischer Precompute + zwei-spuriger Orchestrator (Technical/Macro-Agent + 6 Fundamental-Agents) → `docs/reports/*`.
> - **Plan 3 — Dashboard:** statische `docs/index.html`, liest `reports/index.json`.
> - **Plan 4 — Cloud-Routine & GitHub-Deploy:** privates Repo, Pages, Schedule-Cron, Secrets, Push (braucht `gh` oder manuelles Repo-Anlegen).

---

## File Structure

- `requirements.txt` — Python-Abhängigkeiten
- `.gitignore` — `.env`, `__pycache__`, `data/`, Caches
- `.env.example` — `TWELVEDATA_API_KEY=`
- `README.md` — Kurzbeschreibung + Setup
- `config/settings.json` — Laufzeit-Defaults (Cache-Pfad, Rate-Limit)
- `config/watchlist.json` — generiert aus `symbol_map`
- `src/__init__.py`, `src/data/__init__.py`
- `src/data/symbol_map.py` — RAW-Listen, MAPPING, Klassifikation, `build_watchlist_entries`, `load_watchlist`, `safe_name`
- `src/data/twelvedata_client.py` — `TwelveDataClient` (quote, time_series, Cache, Rate-Limit)
- `src/data/public_sources.py` — `sec_recent_filings`
- `src/data/fetch.py` — `fetch_symbol`, `fetch_all`
- `scripts/build_watchlist.py` — schreibt `config/watchlist.json`
- `scripts/fetch_all.py` — CLI: Roh-Abzug + Coverage-Report
- `tests/conftest.py`, `tests/test_symbol_map.py`, `tests/test_twelvedata_client.py`, `tests/test_public_sources.py`, `tests/test_fetch.py`

---

## Task 0: Projekt-Gerüst

**Files:**
- Create: `requirements.txt`, `.gitignore`, `.env.example`, `README.md`, `config/settings.json`, `src/__init__.py`, `src/data/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: requirements.txt**

```
requests>=2.31
python-dotenv>=1.0
pytest>=8.0
```

- [ ] **Step 2: .gitignore**

```
.env
__pycache__/
*.pyc
.pytest_cache/
/data/
.cache/
```

- [ ] **Step 3: .env.example**

```
TWELVEDATA_API_KEY=
```

- [ ] **Step 4: config/settings.json**

```json
{
  "cache_dir": ".cache",
  "data_dir": "data",
  "reports_dir": "docs/reports",
  "twelvedata": { "min_interval_seconds": 8, "time_series_outputsize": 250 },
  "fundamental_cadence": "daily",
  "run_time_utc": "22:30"
}
```

- [ ] **Step 5: README.md** (Kurzfassung)

```markdown
# Finance Watchlist Agents

Tägliche, agentengestützte Analyse einer Multi-Asset-Watchlist (Indizes, Forex,
Crypto, Rohstoffe, Aktien). Ergebnisse als statisches Dashboard. **Analyse, kein
Kauf — Entwürfe zur menschlichen Prüfung, keine Anlageempfehlung.**

## Setup
1. `python -m venv .venv && .venv\Scripts\activate`
2. `pip install -r requirements.txt`
3. `.env` aus `.env.example` anlegen, `TWELVEDATA_API_KEY` eintragen
4. `python scripts/build_watchlist.py` → erzeugt `config/watchlist.json`
5. `python scripts/fetch_all.py` → Rohdaten + Coverage-Report

Design/Pläne: `docs/superpowers/`.
```

- [ ] **Step 6: Leere Paket-Dateien**

`src/__init__.py`, `src/data/__init__.py`, `tests/__init__.py` als leere Dateien anlegen.

- [ ] **Step 7: Abhängigkeiten installieren**

Run: `python -m pip install -r requirements.txt`
Expected: erfolgreich, `pytest` verfügbar.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .gitignore .env.example README.md config/settings.json src tests
git commit -m "chore: project scaffolding for data layer"
```

---

## Task 1: symbol_map — Klassifikation & `safe_name`

**Files:**
- Create: `src/data/symbol_map.py`
- Test: `tests/test_symbol_map.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_symbol_map.py
from src.data import symbol_map as sm

def test_track_for_stock_is_fundamental():
    assert sm.track_for("stock") == "fundamental"

def test_track_for_forex_is_technical():
    assert sm.track_for("forex") == "technical"

def test_safe_name_replaces_slash():
    assert sm.safe_name("EUR/USD") == "EUR-USD"
    assert sm.safe_name("AAPL") == "AAPL"
```

- [ ] **Step 2: Run → fail**

Run: `python -m pytest tests/test_symbol_map.py -v`
Expected: FAIL (`module has no attribute 'track_for'`).

- [ ] **Step 3: Implement**

```python
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
```

- [ ] **Step 4: Run → pass**

Run: `python -m pytest tests/test_symbol_map.py -v`
Expected: PASS (3 Tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/symbol_map.py tests/test_symbol_map.py
git commit -m "feat: asset-class track resolution and safe_name"
```

---

## Task 2: symbol_map — RAW-Listen, MAPPING, `build_watchlist_entries`

**Files:**
- Modify: `src/data/symbol_map.py`
- Test: `tests/test_symbol_map.py`

- [ ] **Step 1: Failing test (anhängen)**

```python
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
```

- [ ] **Step 2: Run → fail**

Run: `python -m pytest tests/test_symbol_map.py -v`
Expected: FAIL (`no attribute 'build_watchlist_entries'`).

- [ ] **Step 3: Implement (an `symbol_map.py` anhängen)**

```python
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

def build_watchlist_entries() -> list[dict]:
    entries: list[dict] = []
    for asset_class, displays in RAW.items():
        for display in displays:
            entries.append({
                "display": display,
                "td_symbol": td_symbol_for(display),
                "asset_class": asset_class,
                "track": track_for(asset_class),
                "exchange": EXCHANGE.get(display),
                "enabled": True,
            })
    return entries
```

- [ ] **Step 4: Run → pass**

Run: `python -m pytest tests/test_symbol_map.py -v`
Expected: PASS (alle Tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/symbol_map.py tests/test_symbol_map.py
git commit -m "feat: watchlist raw lists, mapping and entry builder"
```

---

## Task 3: symbol_map — `load_watchlist` + Generator-Script

**Files:**
- Modify: `src/data/symbol_map.py`
- Create: `scripts/build_watchlist.py`
- Test: `tests/test_symbol_map.py`

- [ ] **Step 1: Failing test (anhängen)**

```python
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
```

- [ ] **Step 2: Run → fail**

Run: `python -m pytest tests/test_symbol_map.py -v`
Expected: FAIL (`no attribute 'load_watchlist'`).

- [ ] **Step 3: Implement (`load_watchlist` an `symbol_map.py` anhängen)**

```python
_REQUIRED = {"display", "td_symbol", "asset_class", "track", "exchange", "enabled"}

def load_watchlist(path: str | Path) -> list[dict]:
    """Liest watchlist.json, validiert Felder, gibt nur aktive Eintraege zurueck."""
    entries = json.loads(Path(path).read_text(encoding="utf-8"))
    for e in entries:
        missing = _REQUIRED - set(e)
        if missing:
            raise ValueError(f"Watchlist-Eintrag {e.get('display','?')}: fehlende Felder {missing}")
    return [e for e in entries if e.get("enabled")]
```

- [ ] **Step 4: Generator-Script**

```python
# scripts/build_watchlist.py
"""Schreibt config/watchlist.json aus den Rohlisten in symbol_map."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.symbol_map import build_watchlist_entries  # noqa: E402

def main() -> None:
    out = Path(__file__).resolve().parents[1] / "config" / "watchlist.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    entries = build_watchlist_entries()
    out.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{len(entries)} Symbole -> {out}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run Tests + Generator**

Run: `python -m pytest tests/test_symbol_map.py -v`
Expected: PASS.
Run: `python scripts/build_watchlist.py`
Expected: `80 Symbole -> .../config/watchlist.json`, Datei existiert.

- [ ] **Step 6: Commit**

```bash
git add src/data/symbol_map.py scripts/build_watchlist.py config/watchlist.json tests/test_symbol_map.py
git commit -m "feat: watchlist loader and config generator"
```

---

## Task 4: TwelveDataClient — Cache + Rate-Limit-Core

**Files:**
- Create: `src/data/twelvedata_client.py`
- Test: `tests/conftest.py`, `tests/test_twelvedata_client.py`

- [ ] **Step 1: Test-Fixtures**

```python
# tests/conftest.py
class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
    def json(self):
        return self._payload
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

class FakeSession:
    """Gibt vorgegebene Antworten zurueck und zaehlt Aufrufe."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self._responses.pop(0)
```

- [ ] **Step 2: Failing test**

```python
# tests/test_twelvedata_client.py
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
```

- [ ] **Step 3: Run → fail**

Run: `python -m pytest tests/test_twelvedata_client.py -v`
Expected: FAIL (Modul/Klasse fehlt).

- [ ] **Step 4: Implement**

```python
# src/data/twelvedata_client.py
"""Rate-limitierter, gecachter Twelve-Data-Client."""
from __future__ import annotations
import json
import time
import hashlib
from pathlib import Path

BASE_URL = "https://api.twelvedata.com"

class TwelveDataClient:
    def __init__(self, api_key, cache_dir, min_interval_s=8,
                 session=None, sleep=time.sleep, clock=time.monotonic, today=None):
        import requests
        from datetime import date
        self.api_key = api_key
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_s = min_interval_s
        self.session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._last_call = None
        self.today = today or date.today().isoformat()

    def _cache_path(self, endpoint, params):
        key = endpoint + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        h = hashlib.sha1(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{self.today}_{endpoint}_{h}.json"

    def _get(self, endpoint, params):
        cp = self._cache_path(endpoint, params)
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8"))
        if self._last_call is not None:
            elapsed = self._clock() - self._last_call
            if elapsed < self.min_interval_s:
                self._sleep(self.min_interval_s - elapsed)
        q = dict(params)
        q["apikey"] = self.api_key
        resp = self.session.get(f"{BASE_URL}/{endpoint}", params=q, timeout=30)
        resp.raise_for_status()
        self._last_call = self._clock()
        data = resp.json()
        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(f"Twelve Data Fehler: {data.get('message')}")
        cp.write_text(json.dumps(data), encoding="utf-8")
        return data
```

Hinweis: `_clock` default `time.monotonic`; im Test sorgt `min_interval_s=8` mit echtem `monotonic` dafür, dass `elapsed < 8` → `sleep` aufgerufen wird (gemockt, kein echtes Warten).

- [ ] **Step 5: Run → pass**

Run: `python -m pytest tests/test_twelvedata_client.py -v`
Expected: PASS (3 Tests).

- [ ] **Step 6: Commit**

```bash
git add src/data/twelvedata_client.py tests/conftest.py tests/test_twelvedata_client.py
git commit -m "feat: TwelveDataClient with on-disk cache and rate limiting"
```

---

## Task 5: TwelveDataClient — `quote` & `time_series`

**Files:**
- Modify: `src/data/twelvedata_client.py`
- Test: `tests/test_twelvedata_client.py`

- [ ] **Step 1: Failing test (anhängen)**

```python
def test_quote_returns_parsed(tmp_path):
    payload = {"symbol": "AAPL", "close": "201.5", "percent_change": "1.2",
               "currency": "USD"}
    c, _ = _client(tmp_path, [FakeResponse(payload)])
    q = c.quote("AAPL")
    assert q["price"] == 201.5
    assert q["change_pct"] == 1.2
    assert q["currency"] == "USD"

def test_time_series_returns_values(tmp_path):
    payload = {"values": [{"datetime": "2026-06-26", "close": "10"},
                          {"datetime": "2026-06-25", "close": "9"}]}
    c, _ = _client(tmp_path, [FakeResponse(payload)])
    ts = c.time_series("AAPL", outputsize=2)
    assert [v["close"] for v in ts] == ["10", "9"]
```

- [ ] **Step 2: Run → fail**

Run: `python -m pytest tests/test_twelvedata_client.py -v`
Expected: FAIL (`no attribute 'quote'`).

- [ ] **Step 3: Implement (an Klasse anhängen)**

```python
    def quote(self, symbol, exchange=None):
        params = {"symbol": symbol}
        if exchange:
            params["exchange"] = exchange
        d = self._get("quote", params)
        return {
            "price": float(d["close"]),
            "change_pct": float(d.get("percent_change", 0) or 0),
            "currency": d.get("currency"),
        }

    def time_series(self, symbol, interval="1day", outputsize=250, exchange=None):
        params = {"symbol": symbol, "interval": interval, "outputsize": outputsize}
        if exchange:
            params["exchange"] = exchange
        d = self._get("time_series", params)
        return d.get("values", [])
```

- [ ] **Step 4: Run → pass**

Run: `python -m pytest tests/test_twelvedata_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/data/twelvedata_client.py tests/test_twelvedata_client.py
git commit -m "feat: quote and time_series endpoints"
```

---

## Task 6: public_sources — SEC EDGAR Filings

**Files:**
- Create: `src/data/public_sources.py`
- Test: `tests/test_public_sources.py`

- [ ] **Step 1: Failing test**

```python
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
```

- [ ] **Step 2: Run → fail**

Run: `python -m pytest tests/test_public_sources.py -v`
Expected: FAIL (Modul fehlt).

- [ ] **Step 3: Implement**

```python
# src/data/public_sources.py
"""Oeffentliche Quellen: SEC EDGAR Filings (nur US-Aktien mit CIK)."""
from __future__ import annotations

SEC_HEADERS = {"User-Agent": "finance-watchlist-agents michiherbig@googlemail.com"}

def sec_recent_filings(cik, session=None, limit=5):
    """Letzte Filings via data.sec.gov. cik: 10-stellig zero-padded oder None."""
    if not cik:
        return []
    import requests
    session = session or requests.Session()
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    resp = session.get(url, headers=SEC_HEADERS, timeout=30)
    resp.raise_for_status()
    recent = resp.json().get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    docs = recent.get("primaryDocument", [])
    accs = recent.get("accessionNumber", [])
    out = []
    for i in range(min(limit, len(forms))):
        out.append({"form": forms[i], "date": dates[i],
                    "doc": docs[i] if i < len(docs) else None,
                    "accession": accs[i] if i < len(accs) else None})
    return out
```

Hinweis: `FakeSession.get` muss optionales `headers`-Argument schlucken — in `conftest.py` Signatur auf `get(self, url, params=None, timeout=None, headers=None)` erweitern, falls noch nicht vorhanden.

- [ ] **Step 4: conftest anpassen**

`FakeSession.get` Signatur erweitern:

```python
    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append((url, params))
        return self._responses.pop(0)
```

- [ ] **Step 5: Run → pass**

Run: `python -m pytest tests/test_public_sources.py tests/test_twelvedata_client.py -v`
Expected: PASS (alle).

- [ ] **Step 6: Commit**

```bash
git add src/data/public_sources.py tests/test_public_sources.py tests/conftest.py
git commit -m "feat: SEC EDGAR recent filings fetch"
```

---

## Task 7: fetch — `fetch_symbol` & `fetch_all` + Coverage

**Files:**
- Create: `src/data/fetch.py`
- Test: `tests/test_fetch.py`

- [ ] **Step 1: Failing test**

```python
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
```

- [ ] **Step 2: Run → fail**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: FAIL (Modul fehlt).

- [ ] **Step 3: Implement**

```python
# src/data/fetch.py
"""Roh-Abzug pro Symbol + Coverage-Report."""
from __future__ import annotations
import json
from pathlib import Path
from .symbol_map import safe_name

def fetch_symbol(client, entry, today):
    """Holt Quote + Zeitreihe fuer ein Symbol. Faengt Tier-Luecken ab."""
    rec = {"display": entry["display"], "td_symbol": entry["td_symbol"],
           "asset_class": entry["asset_class"], "track": entry["track"],
           "date": today, "available": True, "error": None,
           "snapshot": None, "time_series": []}
    try:
        rec["snapshot"] = client.quote(entry["td_symbol"], exchange=entry.get("exchange"))
        rec["time_series"] = client.time_series(entry["td_symbol"], exchange=entry.get("exchange"))
    except Exception as ex:  # Tier-/Symbol-Luecke -> markieren, nicht abbrechen
        rec["available"] = False
        rec["error"] = str(ex)
    return rec

def fetch_all(watchlist, client, out_dir, today):
    """Schreibt data/<safe>/raw-<today>.json je Symbol, liefert Coverage-Map."""
    out_dir = Path(out_dir)
    coverage = {}
    for entry in watchlist:
        rec = fetch_symbol(client, entry, today)
        coverage[entry["display"]] = rec["available"]
        d = out_dir / safe_name(entry["display"])
        d.mkdir(parents=True, exist_ok=True)
        (d / f"raw-{today}.json").write_text(
            json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    return coverage
```

- [ ] **Step 4: Run → pass**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: PASS (3 Tests).

- [ ] **Step 5: Commit**

```bash
git add src/data/fetch.py tests/test_fetch.py
git commit -m "feat: per-symbol raw fetch with coverage tracking"
```

---

## Task 8: CLI `fetch_all.py` + Coverage-Report

**Files:**
- Create: `scripts/fetch_all.py`

- [ ] **Step 1: Implement**

```python
# scripts/fetch_all.py
"""CLI: laedt .env, baut Client, holt Rohdaten, druckt Coverage-Report."""
import json
import os
import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402
from src.data.symbol_map import load_watchlist  # noqa: E402
from src.data.twelvedata_client import TwelveDataClient  # noqa: E402
from src.data.fetch import fetch_all  # noqa: E402

def main() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    key = os.environ.get("TWELVEDATA_API_KEY")
    if not key:
        print("FEHLER: TWELVEDATA_API_KEY fehlt (.env).")
        sys.exit(1)
    settings = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))
    today = date.today().isoformat()
    wl = load_watchlist(root / "config" / "watchlist.json")
    client = TwelveDataClient(
        api_key=key, cache_dir=root / settings["cache_dir"],
        min_interval_s=settings["twelvedata"]["min_interval_seconds"], today=today)
    coverage = fetch_all(wl, client, root / settings["data_dir"], today)
    ok = [d for d, v in coverage.items() if v]
    bad = [d for d, v in coverage.items() if not v]
    print(f"\nCoverage {today}: {len(ok)}/{len(coverage)} verfuegbar")
    if bad:
        print("NICHT verfuegbar (Tier/Symbol pruefen): " + ", ".join(bad))

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Integrations-Smoke (manuell, mit echtem Key)**

Run: `python scripts/fetch_all.py`
Expected: Coverage-Report; identifiziert Symbole, die der Tier nicht liefert (Risiko #2/#3 aus der Spec aufgelöst). **Kein Test-Commit nötig**, nur Diagnose.

- [ ] **Step 3: Commit**

```bash
git add scripts/fetch_all.py
git commit -m "feat: fetch_all CLI with coverage report"
```

---

## Task 9: Gesamtlauf & Abschluss

- [ ] **Step 1: Voller Testlauf**

Run: `python -m pytest -v`
Expected: alle Tests PASS.

- [ ] **Step 2: Coverage-Befund dokumentieren**

Den Coverage-Report aus Task 8 in `docs/superpowers/notes-coverage.md` festhalten (welche Indizes/Rohstoffe der Tier liefert). Falls Symbole fehlen: `MAPPING` korrigieren oder `enabled:false` in `watchlist.json` via Regenerieren.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/notes-coverage.md
git commit -m "docs: record Twelve Data tier coverage findings"
```

---

## Self-Review (durchgeführt)

- **Spec-Abdeckung:** Datenschicht, Symbol-Mapping (Spec §5), Twelve-Data-Client mit Rate-Limit/Cache (§10), öffentliche Quellen/SEC (§6), Coverage/Tier-Risiko (§11.2/11.3) — alle abgedeckt. Agents/Reports/Dashboard/Routine bewusst in Plan 2–4.
- **Platzhalter:** keine — jeder Code-Step zeigt vollständigen Code, jeder Run-Step erwartetes Ergebnis.
- **Typ-Konsistenz:** `TwelveDataClient.quote`→`{price,change_pct,currency}` wird in `fetch_symbol.snapshot` genutzt; `safe_name` einheitlich in `fetch_all` und Tests; `load_watchlist`-Feldnamen == `build_watchlist_entries`-Ausgabe.
