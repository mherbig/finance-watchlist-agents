# Finance Watchlist Agents — Design Spec

**Datum:** 2026-06-26
**Status:** Genehmigt (Brainstorming abgeschlossen, bereit für Implementierungsplan)
**Working dir:** `C:\Users\herbi\Documents\_Claude_Cowork\financial-services`

## 1. Ziel

Ein System, das eine selbst gewählte Watchlist aus ~70 Symbolen (Indizes, Forex,
Crypto, Energie, Metalle, US-/EU-Aktien) **regelmäßig (täglich nach Börsenschluss)**
automatisch analysiert — durch mehrere Claude-Agents „im Zusammenspiel" — und die
Ergebnisse in einem **Dashboard** darstellt.

Leitprinzip (übernommen aus `anthropics/financial-services`): **Analyse, kein Kauf.**
Jedes Ergebnis ist ein **Entwurf zur menschlichen Prüfung**, keine Anlageempfehlung,
keine Order, keine Transaktion.

## 2. Getroffene Entscheidungen

| Thema | Entscheidung |
|---|---|
| Runtime | **Weg B** — geplante Cloud-Routine (Schedule-Skill / Cron) |
| Agent-Strategie | **Zwei Spuren**: Fundamental-Agents für Aktien, Technical/Macro-Agent für den Rest |
| Fundamental-Agents | Market Researcher, Earnings Reviewer, Model Builder, Valuation Reviewer, Pitch, Meeting Prep |
| Datenquellen | Öffentlich (SEC EDGAR, News) + **Twelve Data API** (Key vorhanden) |
| Takt | Täglich nach Börsenschluss (~22:30 UTC, ein fixer Lauf) |
| Speicher/Brücke | **Privates GitHub-Repo** (Cloud schreibt → Pages rendert) |
| Dashboard | **GitHub Pages** (öffentliche URL), optionaler Frontend-PIN |
| Secret-Handling | API-Key + GitHub-Push-Token als Cloud-Secrets; lokal `.env` (gitignored) |

## 3. Architektur & Datenfluss

```
Cloud-Routine (täglich ~22:30 UTC)
   └─ /analyze-watchlist  (treibt src/orchestrator.py)
        ├─ Daten-Schicht:  Twelve Data + SEC-EDGAR + News
        ├─ Spur A (technical):  Indizes/Forex/Crypto/Energie/Metalle
        ├─ Spur B (fundamental): 26 Aktien (US+EU)
        ├─ schreibt docs/reports/<SYMBOL>/<datum>.json + docs/reports/index.json
        └─ git commit && git push
              └─ GitHub Pages → Dashboard-URL (öffentlich, optional PIN)
```

Vier Schichten, je mit klarer Verantwortung und definiertem Interface:

1. **Config** — *was* analysiert wird (Watchlist, Settings).
2. **Daten-Schicht** — *Rohdaten* beschaffen (Twelve Data, öffentliche Quellen). Output: `data/<SYMBOL>/raw-<datum>.json`.
3. **Agent-Schicht** — *Analyse* erzeugen (zwei Spuren). Output: `docs/reports/<SYMBOL>/<datum>.json` + `.md`.
4. **Dashboard** — *Darstellung* (liest nur die Report-JSONs).

## 4. Repo-Struktur

```
financial-services/                 (Git-Repo, privat)
├── .env.example                    TWELVEDATA_API_KEY=…   (echte .env gitignored)
├── .gitignore
├── README.md
├── config/
│   ├── watchlist.json              alle Symbole: Anzeige, TD-Kürzel, Assetklasse, Spur, an/aus
│   └── settings.json               Laufzeit, Caps, Pages an/aus, PIN-Hash, Fundamental-Takt
├── src/
│   ├── data/
│   │   ├── twelvedata_client.py    quote/time_series/indicators/fundamentals, Rate-Limit + Cache
│   │   ├── public_sources.py       SEC-EDGAR-Filings, News
│   │   └── symbol_map.py           Anzeigename → TD-Symbol + Assetklasse + Spur
│   ├── analysis/
│   │   ├── technical.py            deterministische Indikatoren/Level (Spur A Precompute)
│   │   └── schema.py               Report-JSON-Schema + Validierung
│   └── orchestrator.py             Hauptlauf
├── agents/
│   ├── fundamental/                6 Agents (Apache-2.0, vendored aus anthropics/financial-services)
│   └── technical-macro.md          eigener Technical/Macro-Analyst-Agent
├── commands/
│   └── analyze-watchlist.md        /analyze-watchlist
├── data/<SYMBOL>/raw-<datum>.json  Roh-Cache
└── docs/                           ← GitHub-Pages-Wurzel (Pages: main /docs)
    ├── index.html
    ├── assets/  app.js · style.css
    └── reports/
        ├── index.json
        └── <SYMBOL>/<datum>.json (+ .md)
```

## 5. Watchlist & Symbol-Mapping

### Assetklassen → Spur
- **technical:** index, forex, crypto, energy, metal
- **fundamental:** stock (US + EU)

### Watchlist-Eintrag (Schema)
```json
{
  "display": "EUR/USD",
  "td_symbol": "EUR/USD",
  "asset_class": "forex",
  "track": "technical",
  "exchange": null,
  "enabled": true
}
```

### Vollständige Symbol-Liste (Quelle: Nutzer)
- **Indizes:** GER40, FTSE100, NQ100, WS30, S&P500, ASX200, FRA40, Nikkei225, HK50
- **Forex:** AUD/CAD, AUD/CHF, AUD/JPY, AUD/NZD, AUD/USD, CAD/CHF, CAD/JPY, CHF/JPY,
  EUR/AUD, EUR/CAD, EUR/CHF, EUR/GBP, EUR/JPY, EUR/NZD, EUR/USD, GBP/AUD, GBP/CAD,
  GBP/CHF, GBP/JPY, GBP/NZD, GBP/USD, NZD/CAD, NZD/CHF, NZD/JPY, NZD/USD, USD/CAD,
  USD/CHF, USD/JPY
- **Crypto:** ADA/USD, BNB/USD, BTC/USD, ETH/USD, LTC/USD, SOL/USD, XRP/USD, DOGE/USD,
  XMR/USD, DASH/USD, NEO/USD
- **Energie:** BRENT, NATGAS
- **Metalle:** XAG, XAU, XPT, XPD
- **US-Aktien:** QCOM, JPM, MICRON, AMD, INTEL, ATNT, FERRARI, PFIZER, TSLA, VISA, ZM,
  META, MSFT, NETFLIX, NVIDIA, ALIBABA, AMAZON, APPLE, BOA, GOOGLE
- **EU-Aktien:** AIR, ALLI, BAYER, IBER, LVMH, VOWGE

### Mapping-Auszug (beim Bau gegen Twelve Data verifizieren)
| Anzeige | TD-Symbol | | Anzeige | TD-Symbol |
|---|---|---|---|---|
| MICRON | MU | | NETFLIX | NFLX |
| INTEL | INTC | | NVIDIA | NVDA |
| ATNT | T | | ALIBABA | BABA |
| FERRARI | RACE | | AMAZON | AMZN |
| VISA | V | | APPLE | AAPL |
| BOA | BAC | | GOOGLE | GOOGL |
| ALLI | ALV.DE | | BAYER | BAYN.DE |
| IBER | IBE.MC | | LVMH | MC.PA |
| VOWGE | VOW3.DE | | AIR | AIR.PA |
| GER40 | DAX | | NQ100 | NDX |
| WS30 | DJI | | S&P500 | SPX |
| FRA40 | CAC40 | | Nikkei225 | N225 |
| HK50 | HSI | | FTSE100 | (verifizieren) |
| ASX200 | (verifizieren) | | XAU | XAU/USD |
| XAG | XAG/USD | | XPT | XPT/USD |
| XPD | XPD/USD | | | |

## 6. Zwei Analyse-Spuren

### Spur A — Technical/Macro (alle Nicht-Aktien)
1. **Deterministischer Precompute** (`src/analysis/technical.py`) aus Twelve-Data-Zeitreihe:
   Trend (MA 20/50/200), RSI(14), MACD, ATR/Volatilität, Schlüssel-Level (jüngste
   Hochs/Tiefs), Abstand 52W-Hoch/Tief, Tages-/Wochenänderung.
2. **Technical/Macro-Agent** macht daraus eine strukturierte Einschätzung: Bias
   (bullish/neutral/bearish — als *Analyse*, keine Order), Schlüssel-Level, Katalysatoren,
   „worauf zu achten ist", kurze Makro-/News-Einordnung.

### Spur B — Fundamental (26 Aktien)
Daten: Twelve-Data-Quote + Fundamentals + Earnings-Kalender, SEC-EDGAR-Filings, News.
Agents im Zusammenspiel:
- **Market Researcher** → Sektor-/Peer-Kontext
- **Earnings Reviewer** → *Earnings-gated*: nur bei kürzlichen Earnings; was die These ändert
- **Model Builder** → leichtes DCF + Comps → Fair-Value-Range als JSON
- **Valuation Reviewer** → Plausibilitäts-Check gegen Comps/Methodik
- **Pitch / Meeting Prep** → kompaktes Briefing-Pack je Aktie

## 7. Report-Schema (Vertrag Routine ↔ Dashboard)

`docs/reports/<SYMBOL>/<datum>.json`:
```json
{
  "symbol": "AAPL",
  "display": "APPLE",
  "asset_class": "stock",
  "track": "fundamental",
  "date": "2026-06-26",
  "generated_at": "2026-06-26T22:31:00Z",
  "snapshot": { "price": 0, "change_pct": 0, "currency": "USD" },
  "technical": {
    "trend": "up|down|side", "rsi": 0, "macd": "…",
    "levels": [{"type":"support|resistance","price":0}],
    "atr": 0, "bias": "bullish|neutral|bearish"
  },
  "fundamental": {
    "market_research": "…md…",
    "earnings": { "has_recent": false, "summary": "", "thesis_change": "" },
    "model": { "method": "DCF", "fair_value_low": 0, "fair_value_high": 0,
               "key_assumptions": [], "comps": [] },
    "valuation_review": "…",
    "briefing": "…"
  },
  "headline": "Ein-Zeilen-Take (Entwurf, keine Empfehlung)",
  "flags": ["earnings_upcoming"],
  "disclaimer": "Entwurf zur menschlichen Prüfung. Keine Anlageempfehlung."
}
```
`fundamental` entfällt bei technical-Symbolen. `docs/reports/index.json`: Array mit
Kurzfassung aller Symbole (symbol, display, asset_class, snapshot, headline, bias,
date) fürs Grid.

## 8. Dashboard (`docs/index.html`)

Eigenständig (Vanilla JS + minimal CSS, keine Build-Tools). Lädt `reports/index.json`.
- **Grid**, gruppiert nach Assetklasse (Indizes, Forex, Crypto, Energie, Metalle,
  US-Aktien, EU-Aktien): Symbol, Preis, Tages-%, Trend-Chip, RSI, Ein-Zeilen-Take.
- **Detail** (Klick): Snapshot, technische Lesart, (bei Aktien) Fundamental-Sektionen,
  Level, Flags, **Datums-Historie**-Dropdown (lädt ältere `<datum>.json`).
- **Disclaimer-Banner** dauerhaft sichtbar.
- **Optionaler PIN-Gate**: JS-Prompt gegen Hash. *Explizit nur Obfuskation, keine
  echte Sicherheit* (Pages-Seite ist öffentlich erreichbar).
- „Zuletzt aktualisiert"-Zeitstempel.

## 9. Zeitplan & Lauf (Weg B)

Geplante Cloud-Routine (Schedule-Skill → Cron), **täglich ~22:30 UTC**: nach US-Schluss;
EU-/Asien-Tageskerzen sind zu, FX/Crypto als Tages-Snapshot. Routine:
1. Repo auschecken, `.env`/Secrets laden
2. `/analyze-watchlist` → Daten holen → beide Spuren → Reports schreiben → `index.json` bauen
3. `git commit && git push` → Pages publiziert automatisch

Benötigte Cloud-Secrets: `TWELVEDATA_API_KEY`, GitHub-Push-Token (mit Repo-Schreibrecht).

## 10. Kosten & Limits
- Technical-Spur billig (meist deterministisch + 1 Agent-Pass).
- Fundamental nur 26 Aktien, Earnings-gated; per `settings.json` auf **wöchentlich** drosselbar.
- Twelve-Data-Client: Rate-Limit-bewusst (Free: 8/min, 800/Tag), On-Disk-Cache.
- Fehlt Daten im Tier (Indizes/Rohstoffe oft Paid): Symbol als „Daten nicht verfügbar"
  markieren statt Lauf abzubrechen.

## 11. Offene Risiken & Verifikation (zuerst, vor dem Vollausbau)
1. **Riskantester Punkt:** Kann die Cloud-Routine unser Command ausführen **und** nach
   GitHub pushen (Push-Token im Cloud-Lauf)? → Mini-Lauf als erster Verifikations-Spike.
2. **Twelve-Data-Tier**: deckt Indizes/Rohstoffe ab? → früh per Test-Call prüfen.
3. **Index-Symbol-Mapping** korrekt? → gegen API testen.
4. „Nach Schluss" heterogen → ein fixer UTC-Zeitpunkt als bewusster Kompromiss.
5. **PIN** auf öffentlicher Pages-Seite = Obfuskation, keine Sicherheit (dokumentieren).

## 12. Setup-Schritte (durch Nutzer/zu genehmigen)
- Privates GitHub-Repo anlegen + initialen Push.
- Twelve-Data-Key in lokale `.env` + als Cloud-Secret.
- GitHub-Push-Token als Cloud-Secret.
- GitHub Pages aktivieren (main /docs).

## 13. Bewusst ausgeschlossen (YAGNI)
- Keine Order-Ausführung, kein Auto-Trading, keine Brokerage-Anbindung.
- Keine Kauf-/Verkaufs-Empfehlungen — nur Analyse-Entwürfe.
- Kein eigener Server/Backend (statisches Pages-Dashboard genügt).
- Keine Echtzeit-/Intraday-Streams — ein Tageslauf.
```
