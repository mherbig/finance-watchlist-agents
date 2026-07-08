# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projekt

Tägliche, agentengestützte Analyse einer 80-Symbol-Multi-Asset-Watchlist mit
statischem Dashboard (GitHub Pages aus `docs/`). Analyse-Entwürfe, keine
Anlageempfehlung. Sprache im Repo (Docstrings, Kommentare, UI): **Deutsch**.

## Befehle

```bash
pip install -r requirements.txt      # requests, python-dotenv, pytest
python -m pytest -q                  # gesamte Suite (muss grün sein vor jedem Commit)
python -m pytest tests/test_portfolio.py -q            # eine Datei
python -m pytest tests/test_signal.py -q -k "market"   # einzelne Tests per -k
```

Windows: Python heißt `python` (nicht `python3`). `.env` mit `TWELVEDATA_API_KEY`
im Root (siehe `.env.example`).

Pipeline (Reihenfolge relevant, alle Skripte von Repo-Root ausführen):

```bash
python scripts/build_watchlist.py      # symbol_map.RAW -> config/watchlist.json (nur nach Mapping-Änderung)
python scripts/fetch_all.py            # Rohdaten -> data/<safe>/raw-<datum>.json (~10 Min, Rate-Limit)
python scripts/build_reports.py        # -> docs/reports/<safe>/<datum>.json + index.json
python scripts/build_market_context.py # Leitmarkt-Trends + Vol-Regime -> docs/signals/market_context.json
python scripts/attach_signals.py signal_out   # LLM-Urteile + deterministische Level -> Reports + log.jsonl
python scripts/build_portfolio.py      # Forward-Test inkl. Risiko-Limits -> docs/signals/portfolio.json
python scripts/evaluate_signals.py     # Track-Record -> docs/signals/track_record.json
python scripts/replay_whatif.py        # Exit-Politik-Vergleich auf geloggten Signalen -> whatif.json
python scripts/make_sample_data.py     # synthetische Rohdaten (Dashboard ohne API-Key)
```

Dashboard lokal: `python -m http.server 8732 --directory docs` (fetch() braucht
einen Server, `file://` geht nicht). Preview-Config: `.claude/launch.json`.

## Architektur

Zwei getrennte Tages-Automatiken schreiben in dasselbe Repo:

1. **GitHub Actions** (`.github/workflows/daily.yml`, 22:30 UTC): deterministischer
   Kern ohne LLM — fetch → build_reports → build_portfolio + evaluate_signals →
   commit `docs/`.
2. **Lokale Claude-Code-Routine** (`daily-trade-signals`, ~23:00 lokal auf dem
   Always-on-PC): zusätzlich die LLM-Schicht — je Symbol ein Signal-Judge-Subagent
   (Anweisung: `prompts/signal-task.md`) schreibt `signal_out/<safe>.json`, dann
   attach_signals → build_portfolio → evaluate_signals → push.

Deshalb: **immer `git pull` vor Arbeiten/Pushen**; Konflikte entstehen praktisch
nur in generierten `docs/`-Dateien — dann Code mergen und die betroffene Datei per
Skript neu bauen (z. B. `build_portfolio.py` für `portfolio.json`), nicht von Hand.

Datenfluss (Schichten strikt getrennt):

```
symbol_map.py ──build_watchlist──> config/watchlist.json
      │  (display -> td_symbol/api_symbol, source: twelvedata|yahoo, safe_name)
fetch_all ──TwelveDataClient/YahooClient (Rate-Limit + Tages-Cache in .cache/)
      └──> data/<safe>/raw-<datum>.json      (gitignored, ein Vintage je Tag)
build_reports ── technical.py (SMA/RSI/MACD/ATR/Level, reine Funktion)
      └──> docs/reports/<safe>/<datum>.json  (erhält agent_analysis + signal!)
LLM-Judge ──> signal_out/<safe>.json  (nur direction/conviction/horizon/rationale)
attach_signals ── signal.py: Entry/SL/TP DETERMINISTISCH aus ATR + Levels
      └──> report.signal + docs/signals/log.jsonl (idempotent je (date, display))
build_portfolio ── portfolio.py: resolve_symbol_trades + simulate
      └──> docs/signals/portfolio.json ── evaluate_signals ──> track_record.json
docs/index.html + assets/app.js (Vanilla JS, kein Build-Schritt) rendert alles
```

## Fachliche Invarianten

- **Market-only-Entries** (seit 2026-07-02): Einstieg immer zum Tages-Schlusskurs,
  `entry = snapshot.price`; der LLM entscheidet nur OB (LONG/SHORT/FLAT), nie wo.
  `entry_type` ist konstant `"market"` (Alt-Feld). Kein Pullback/Limit.
- **Höchstens 1 offene Position je Symbol.** Gleichgerichtete Folgesignale werden
  gehalten; Gegenrichtung schließt am Flip-Tag ("flip"). FLAT schließt nur mit
  Konviktion ≥ `signals.flat_close_min_conviction` oder nach
  `signals.flat_close_consecutive` FLATs in Folge (Whipsaw-Hysterese).
- **Portfolio-Risiko-Limits** (alle in `config/settings.json` → `portfolio`,
  angewandt als Pre-Pass `apply_portfolio_caps` VOR simulate/Kurven):
  Heat-Cap `max_total_risk_pct`, Klassen-Cap `max_per_class`, Forex-Währungs-Cap
  `max_per_currency`, Kill-Switch `max_drawdown_stop_pct` (blockt nur NEUE
  Entries), Sizing `risk_pct_by_conviction`. Übersprungene Signale stehen mit
  Grund in `portfolio.json:skipped` — das ist Normalbetrieb, kein Fehler.
- **Kosten**: `costs.round_trip_pct` je Assetklasse (% vom Entry-Notional) wird
  beim Close vom P&L abgezogen; `summary.total_costs` weist sie aus.
- Dashboard-Chart zeigt drei Kurven: bewertet (mark-to-market), realisiert,
  Benchmark (Equal-Weight Buy & Hold ab Forward-Test-Start).
- SL/TP/Horizont-Auflösung scannt Bars **strikt nach** dem Signal-Datum; kein
  Same-Bar-Look-ahead. FLAT ist valide und häufig.
- **Nur finalisierte Bars lösen Exits aus**: der Bar des Abruftags
  (`provisional_date` = `raw["date"]`) ist vorläufig und wird von der
  Trade-Auflösung ausgeschlossen (Bewertung/current_price nutzt ihn weiter).
  Verhindert Exits, die der Folgetag revidieren würde.
- **Regelwerk eingefroren seit 2026-07-08** (`portfolio.ruleset_frozen_since`):
  KEINE rückwirkenden Regeländerungen mehr — die simulierte Historie muss ab
  jetzt stabil bleiben. Neue Regel-Ideen laufen über die What-if-Engine
  (`scripts/replay_whatif.py`) und werden nur nach expliziter Nutzer-Entscheidung
  übernommen (dann `ruleset_frozen_since` aktualisieren).
- Offene, nie gefüllte Alt-Pullbacks sind `pending` → **kein** unrealisierter P&L
  (Phantom-Gewinn-Schutz); Dashboard zeigt "⏳ wartet".
- `build_reports`/`attach_*` sind **idempotent** und erhalten bestehende
  `agent_analysis`-/`signal`-Blöcke; `log.jsonl` hat genau eine Zeile je (Symbol, Tag).
- `safe_name` (`/` → `-`) existiert doppelt: `src/data/symbol_map.py` und
  `safeName()` in `docs/assets/app.js` — Änderungen müssen synchron bleiben.
- Tiefe Agent-Analyse (6-Panel) wird NICHT täglich erneuert, nur Signale.

## Konventionen

- **TDD ist Pflicht** (Stil siehe `tests/`): Test zuerst, RED beobachten, dann
  implementieren. Reine Funktionen in `src/`, keine Netzwerkaufrufe in
  `src/analysis/`; CLIs in `scripts/` sind dünne Wrapper mit `sys.path.insert`.
- Docstrings/Kommentare deutsch, teils ASCII-Umschreibung (ue/oe/ae) — beim
  Editieren den Stil der Datei beibehalten.
- Frontend: Vanilla JS, HTML wird escaped (`escapeHtml`), Daten-Fetches mit
  `noCache()` (Cache-Busting), Zahlen via `fmtNum`/`fmtPct` (de-DE).
- Commits: nur `docs/` wird von den Automatiken committet; Code-Änderungen laufen
  über den Haupt-PC. Vor jedem Push: Tests grün + `git pull`.
