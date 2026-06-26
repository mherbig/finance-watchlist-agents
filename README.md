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
