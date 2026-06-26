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
