# scripts/recompute_signals.py
"""One-off: Signal-Bloecke aus GESPEICHERTEN Entscheidungen neu berechnen.

Kein LLM, keine Netzwerkaufrufe. Fuer jeden neuesten Report unter
docs/reports/<safe>/<latest>.json mit einem ``signal``-Block werden die
qualitativen Entscheidungsfelder {direction, conviction, entry_type,
horizon_days, rationale} entnommen und mit dem KORRIGIERTEN build_signal()
(fixed compute_levels) gegen die aktuellen technical/snapshot-Daten des Reports
neu berechnet. Der ``signal``-Block wird ueberschrieben (generated_at = jetzt
UTC, model aus AGENT_MODEL, Default "claude-opus-4-8").

Danach:
  - docs/signals/log.jsonl wird VON GRUND AUF neu gebaut (eine Zeile je Symbol
    mit Signal, date = report.date, inkl. entry_type),
  - docs/reports/index.json wird neu gebaut (build_index),
  - build_portfolio + evaluate_signals werden ausgefuehrt,
  - die neue Portfolio-Zusammenfassung wird ausgegeben.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.analysis.report import build_index  # noqa: E402
from src.analysis.signal import build_signal  # noqa: E402

import build_portfolio  # noqa: E402  (scripts/ liegt auf dem Pfad)
import evaluate_signals  # noqa: E402


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _latest_report(symbol_dir: Path) -> Path | None:
    files = sorted(symbol_dir.glob("*.json"))
    return files[-1] if files else None


# Felder, die eine echte Agenten-Entscheidung ausmachen.
_DECISION_FIELDS = ("direction", "conviction", "horizon_days", "rationale")


def main() -> None:
    # scripts/ auf den Pfad, damit build_portfolio/evaluate_signals importierbar.
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    root = Path(__file__).resolve().parents[1]
    settings = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))
    reports_dir = root / settings["reports_dir"]

    model = os.environ.get("AGENT_MODEL", "claude-opus-4-8")
    generated_at = _now_utc_iso()

    rebuilt = 0
    skipped = 0
    log_lines: list[str] = []
    # index.json wird – wie build_reports.py – aus EINEM Report je Symbol (dem
    # neuesten) gebaut, nicht aus allen historischen Datumsdateien.
    latest_reports: list[dict] = []

    for symbol_dir in sorted(p for p in reports_dir.iterdir() if p.is_dir()):
        report_path = _latest_report(symbol_dir)
        if report_path is None:
            continue
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  WARN: {report_path} nicht lesbar ({exc}) – uebersprungen")
            continue

        # Jeder neueste Report kommt in den Index (mit/ohne Signal).
        latest_reports.append(report)

        sig = report.get("signal")
        if not isinstance(sig, dict):
            continue

        # Gespeicherte Entscheidung extrahieren. Fehlt etwas -> ueberspringen.
        decision = {f: sig.get(f) for f in _DECISION_FIELDS}
        if any(decision[f] is None for f in _DECISION_FIELDS):
            print(f"  WARN: {report_path.relative_to(root)} ohne vollstaendige "
                  f"Entscheidung – uebersprungen")
            skipped += 1
            continue

        try:
            new_signal = build_signal(
                decision,
                report.get("technical"),
                report.get("snapshot"),
                generated_at=generated_at,
                model=model,
            )
        except ValueError as exc:
            print(f"  WARN: {report_path.relative_to(root)} ungueltig ({exc}) "
                  f"– uebersprungen")
            skipped += 1
            continue

        report["signal"] = new_signal
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        rebuilt += 1

        # Log-Zeile (eine je Symbol mit Signal). FLAT-Signale ebenfalls loggen
        # (entry/SL/TP None) – konsistent mit attach_signals.
        log_lines.append(json.dumps({
            "date": report.get("date"),
            "symbol": report.get("symbol"),
            "display": report.get("display") or report.get("symbol"),
            "direction": new_signal["direction"],
            "conviction": new_signal["conviction"],
            "entry_type": new_signal["entry_type"],
            "entry": new_signal["entry"],
            "stop_loss": new_signal["stop_loss"],
            "take_profit": new_signal["take_profit"],
            "take_profit_2": new_signal["take_profit_2"],
            "rr": new_signal["rr"],
            "horizon_days": new_signal["horizon_days"],
            "generated_at": generated_at,
        }, ensure_ascii=False))

    # log.jsonl VON GRUND AUF neu schreiben.
    signals_dir = root / "docs" / "signals"
    signals_dir.mkdir(parents=True, exist_ok=True)
    log_path = signals_dir / "log.jsonl"
    log_path.write_text(
        ("\n".join(log_lines) + "\n") if log_lines else "", encoding="utf-8")

    # index.json neu bauen (ein Report je Symbol, wie build_reports.py).
    index = build_index(latest_reports)
    (reports_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{rebuilt} Signal-Bloecke neu berechnet, {skipped} uebersprungen; "
          f"log.jsonl ({len(log_lines)} Zeilen) und index.json "
          f"({len(latest_reports)} Reports) neu gebaut.")

    # Depot + Track-Record neu aufbauen.
    print("--- build_portfolio ---")
    build_portfolio.main()
    print("--- evaluate_signals ---")
    evaluate_signals.main()

    # Neue Portfolio-Zusammenfassung ausgeben.
    portfolio_path = signals_dir / "portfolio.json"
    if portfolio_path.exists():
        result = json.loads(portfolio_path.read_text(encoding="utf-8"))
        print("--- portfolio summary ---")
        print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
        closed = result.get("closed", [])
        print(f"closed trades: {len(closed)}")
        for c in closed:
            print(f"  {c.get('symbol')} {c.get('direction')} "
                  f"{c.get('status')} R={c.get('realized_R')}")


if __name__ == "__main__":
    main()
