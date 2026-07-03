# Architektur-Review: Schwächen & priorisierte Verbesserungen

Stand: 2026-07-02. Befunde aus einer Struktur-Kartierung des Repos; jede Position
wurde am Code verifiziert. (Hinweis: `docs/` ist zugleich der öffentliche
Pages-Web-Root — diese Datei ist damit öffentlich einsehbar, wie auch
`docs/superpowers/`.)

## P1 — Korrektheit & Betriebssicherheit

1. **Kein Test-Lauf in CI.** `.github/workflows/daily.yml` führt die Pipeline aus,
   aber nichts führt `pytest` bei Push aus. Ein kaputter Commit fällt erst beim
   nächsten Tageslauf (oder gar nicht) auf.
   → Kleiner Workflow `test.yml`: `on: [push, pull_request]`, Python 3.12,
   `pip install -r requirements.txt && python -m pytest -q`. Geringster Aufwand,
   größter Nutzen.

2. **Zwei Automatiken, ein Zielordner, kein Konfliktprotokoll.** GitHub Actions
   (22:30 UTC) und die lokale LLM-Routine (~23:00 lokal) pushen beide generierte
   `docs/`-Dateien; ein Merge-Konflikt in `portfolio.json` ist bereits real
   aufgetreten. Das Auflösungsrezept (generierte Datei per Skript neu bauen)
   lebt nur als Konvention in CLAUDE.md.
   → Kurzfristig: Routine-Prompt um explizite Konfliktanweisung ergänzen
   (bei Konflikt in `docs/signals/*`: `build_portfolio.py`/`evaluate_signals.py`
   erneut ausführen, dann `git add docs/ && git commit`). Mittelfristig: nur EINE
   Automatik schreiben lassen (Actions rein deterministisch belassen, lokale
   Routine pusht nur `signal_out`-Ergebnisse) oder Push-Zeiten weiter entzerren.

3. **Stilles Auslassen fehlerhafter LLM-Urteile.** `attach_signals.py` überspringt
   ungültige `signal_out/<safe>.json` nur mit WARN — das Symbol hat dann an dem Tag
   still kein Signal, `log.jsonl` bekommt keine Zeile, niemand merkt es strukturell.
   → Am Ende hart prüfen: Anzahl angehängter Signale == Anzahl aktivierter Symbole,
   sonst Exit-Code ≠ 0 (die Routine meldet den Fehler dann statt zu pushen).

## P2 — Wartbarkeit & Hygiene

4. **Dupliziertes Log-Parsing.** `build_portfolio.py` und `evaluate_signals.py`
   enthalten wortgleiche Blöcke (log.jsonl lesen, je Symbol gruppieren,
   `flat_closes` aus Settings, Rohdatei-Lookup). Drift-Risiko bei jeder Änderung.
   → Gemeinsames Modul `src/analysis/signal_log.py` (laden/gruppieren/auflösen);
   beide CLIs werden dünn.

5. **Unbegrenztes lokales Datenwachstum.** `.cache/` sammelt ~140 Dateien/Tag
   (nach 5 Tagen: 700 Dateien, 14 MB), `data/<safe>/` einen raw-Vintage je Tag und
   Symbol (18 MB nach 5 Tagen). Beides gitignored, aber der Always-on-PC läuft
   unbeaufsichtigt weiter.
   → Aufräumschritt in `fetch_all.py`: Cache-Dateien und raw-Vintages älter als
   N Tage (z. B. 14) löschen. Der Forward-Test braucht nur den neuesten Vintage.

6. **PAT klartext in `.git/config` (Remote-URL).** Funktioniert, aber der Token
   erscheint in `git remote -v`, Backups und Fehlermeldungen.
   → Windows Credential Manager (`git config credential.helper manager`) und
   Remote-URL ohne Einbettung; Token einmalig beim ersten Push hinterlegen.

7. **`app.js` als 700-Zeilen-Monolith mit Positions-Kopplung.** Tabellenzellen
   werden per Spaltenindex aufgebaut/gelesen; das Einfügen der «Eröffnet»-Spalte
   hat bestehende Auswertungen bereits einmal verschoben (t[5]→t[6]-Fehlklasse).
   Kein Frontend-Test.
   → Zeilen-Rendering auf benannte Zellobjekte umstellen (ein Array
   `columns = [{key, label, render}]` als einzige Quelle für Header + Zellen);
   optional in 2–3 Module aufteilen (grid/detail/portfolio). Kein Framework nötig.

## P3 — Struktur & Klarheit

8. **`docs/` vermischt Web-Root, generierte Daten und interne Planungsdokumente.**
   `docs/superpowers/` (Spec/Plan, ~42 KB) und diese Datei sind öffentlich; alles
   Generierte (reports/, signals/) liegt neben handgepflegtem Frontend (assets/).
   → Bewusste Entscheidung dokumentieren oder trennen: Planung nach `research/`
   bzw. Repo-Root, generierte Daten klar als solche markieren. (Wenn später
   Cloudflare Access + privates Repo kommen, entfällt der Öffentlichkeits-Aspekt.)

9. **`safe_name`-Logik doppelt (Python + JS).** `symbol_map.safe_name` und
   `app.js:safeName` müssen manuell synchron gehalten werden (nur `/`→`-`, aber
   implizit auch: keine sonstigen Sonderzeichen in Display-Namen wie `S&P500`).
   → Mindestens: Test, der für alle Watchlist-Displays prüft, dass `safe_name`
   dateisystem-sicher und kollisionsfrei ist; Kommentar-Querverweise bestehen schon.

10. **`research/backtest.py` ist toter/unklarer Code** ohne Tests und ohne
    Anbindung an die Pipeline.
    → Entweder als Experiment kennzeichnen (README-Zeile) oder entfernen.

11. **Kein Lint/Format-Tooling.** Der Code ist konsistent (PEP-8-nah, deutsche
    Docstrings), aber nichts erzwingt das.
    → `ruff` (check + format) in requirements-dev und den Test-Workflow aus P1
    einhängen; Konfiguration minimal halten.

## Bewusste Grenzen (kein Handlungsbedarf)

- Tiefe 6-Panel-Agent-Analyse wird nicht täglich erneuert — nur Signale
  (separates Vorhaben "wöchentliche Analyse-Routine").
- Pullback-Fill-Logik im Portfolio-Resolver bleibt als getestete Alt-Logik,
  obwohl neue Signale sie nie auslösen (Market-only seit 2026-07-02).
- Forward-Test-Kennzahlen sind erst nach den ersten echten Closes aussagekräftig;
  die ersten Closes einmal manuell gegenprüfen (Entry erreicht → dann SL/TP?).
