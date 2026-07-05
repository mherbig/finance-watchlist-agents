"""Rate-limitierter, gecachter Yahoo-Finance-Client (zweite Datenquelle).

Liefert denselben Kontrakt wie der TwelveDataClient:
- quote() -> {price, change_pct, currency}
- time_series() -> Liste neueste-zuerst, String-Werte, Keys datetime/open/high/low/close/volume
"""
from __future__ import annotations
import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote as _urlquote

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
USER_AGENT = "Mozilla/5.0"


class YahooClient:
    def __init__(self, cache_dir, min_interval_s=1,
                 session=None, sleep=time.sleep, clock=time.monotonic, today=None):
        import requests
        from datetime import date
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_s = min_interval_s
        self.session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._last_call = None
        self.today = today or date.today().isoformat()

    def _cache_path(self, symbol):
        h = hashlib.sha1(symbol.encode()).hexdigest()[:16]
        return self.cache_dir / f"{self.today}_chart_{h}.json"

    def _get(self, symbol):
        cp = self._cache_path(symbol)
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8"))
        if self._last_call is not None:
            elapsed = self._clock() - self._last_call
            if elapsed < self.min_interval_s:
                self._sleep(self.min_interval_s - elapsed)
        encoded = _urlquote(symbol, safe="")
        url = f"{BASE_URL}/{encoded}?range=1y&interval=1d"
        resp = self.session.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        self._last_call = self._clock()
        data = resp.json()
        chart = data.get("chart", {})
        error = chart.get("error")
        if error is not None:
            raise RuntimeError(f"Yahoo Fehler: {error}")
        result = chart["result"][0]
        cp.write_text(json.dumps(result), encoding="utf-8")
        return result

    def earnings_date(self, symbol):
        """Naechster Earnings-Termin als ISO-Datum — strikt best-effort.

        Yahoo quoteSummary (calendarEvents) ist gelegentlich gesperrt
        (Crumb/Consent); JEDER Fehler liefert None statt einer Exception,
        damit der Fetch nie an Earnings-Daten scheitert. Gecacht je Tag.
        """
        cp = self.cache_dir / f"{self.today}_earnings_{hashlib.sha1(symbol.encode()).hexdigest()[:16]}.json"
        try:
            if cp.exists():
                return json.loads(cp.read_text(encoding="utf-8")).get("date")
            if self._last_call is not None:
                elapsed = self._clock() - self._last_call
                if elapsed < self.min_interval_s:
                    self._sleep(self.min_interval_s - elapsed)
            encoded = _urlquote(symbol, safe="")
            url = ("https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
                   f"{encoded}?modules=calendarEvents")
            resp = self.session.get(url, headers={"User-Agent": USER_AGENT},
                                    timeout=30)
            self._last_call = self._clock()
            data = resp.json()
            qs = data.get("quoteSummary", {})
            if qs.get("error") is not None or not qs.get("result"):
                raise ValueError("kein calendarEvents-Resultat")
            dates = (qs["result"][0].get("calendarEvents", {})
                     .get("earnings", {}).get("earningsDate", []))
            raws = [d.get("raw") for d in dates if isinstance(d, dict)
                    and d.get("raw")]
            if not raws:
                raise ValueError("keine earningsDate")
            iso = datetime.fromtimestamp(min(raws), tz=timezone.utc).date().isoformat()
            cp.write_text(json.dumps({"date": iso}), encoding="utf-8")
            return iso
        except Exception:
            try:
                cp.write_text(json.dumps({"date": None}), encoding="utf-8")
            except OSError:
                pass
            return None

    def quote(self, symbol, exchange=None):
        result = self._get(symbol)
        meta = result["meta"]
        price = float(meta["regularMarketPrice"])
        # Tagesaenderung aus den letzten zwei Tageskerzen (konsistent mit
        # time_series/technical). NICHT meta.chartPreviousClose: das ist bei
        # range=1y der Schluss VOR dem Jahresfenster -> ergaebe die Jahresaenderung.
        prev = meta.get("previousClose")
        if not prev:
            ts = self.time_series(symbol, outputsize=2)
            if len(ts) >= 2 and ts[1]["close"]:
                prev = float(ts[1]["close"])
        change_pct = round((price - float(prev)) / float(prev) * 100, 4) if prev else 0.0
        return {
            "price": price,
            "change_pct": change_pct,
            "currency": meta.get("currency"),
        }

    def time_series(self, symbol, interval="1day", outputsize=250, exchange=None):
        result = self._get(symbol)
        timestamps = result.get("timestamp", []) or []
        q = result.get("indicators", {}).get("quote", [{}])[0]
        opens = q.get("open", [])
        highs = q.get("high", [])
        lows = q.get("low", [])
        closes = q.get("close", [])
        volumes = q.get("volume", [])
        bars = []  # oldest-first (wie Yahoo)
        for i, ts in enumerate(timestamps):
            close = closes[i] if i < len(closes) else None
            if close is None:  # Null-Bar ueberspringen
                continue
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            bars.append({
                "datetime": dt,
                "open": str(opens[i]) if i < len(opens) and opens[i] is not None else "",
                "high": str(highs[i]) if i < len(highs) and highs[i] is not None else "",
                "low": str(lows[i]) if i < len(lows) and lows[i] is not None else "",
                "close": str(close),
                "volume": str(volumes[i]) if i < len(volumes) and volumes[i] is not None else "",
            })
        bars.reverse()  # neueste zuerst
        return bars[:outputsize]
