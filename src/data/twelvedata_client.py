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
