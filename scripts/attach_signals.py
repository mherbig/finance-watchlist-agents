# scripts/attach_signals.py
"""CLI: haengt deterministische Signal-Bloecke an bestehende Reports an.

Liest ein Verzeichnis mit Agenten-Entscheidungs-JSONs (Default: argv[1], sonst
``signal_out/``). Jede Datei heisst ``<safe_name>.json`` und hat die Form::

    {"display", "safe_name", "direction", "conviction", "entry_type",
     "horizon_days", "rationale"}

Fuer jede Datei wird der neueste Report unter docs/reports/<safe_name>/*.json
geladen, build_signal() (deterministische SL/TP/Entry-Rechnung aus
technical/snapshot des Reports) aufgerufen, attach_signal() angehaengt und
zurueckgeschrieben. Zusaetzlich wird je Signal eine JSON-Zeile an
docs/signals/log.jsonl angehaengt. Danach wird docs/reports/index.json aus
ALLEN Reports neu gebaut.

Keine Netzwerkaufrufe.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.analysis.report import build_index  # noqa: E402
from src.analysis.signal import attach_signal, build_signal  # noqa: E402


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _latest_report(symbol_dir: Path) -> Path | None:
    files = sorted(symbol_dir.glob("*.json"))
    return files[-1] if files else None


def _load_all_reports(reports_dir: Path) -> list[dict]:
    reports = []
    for symbol_dir in sorted(p for p in reports_dir.iterdir() if p.is_dir()):
        for path in sorted(symbol_dir.glob("*.json")):
            try:
                reports.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError) as exc:
                print(f"  WARN: Report {path} nicht lesbar: {exc}")
    return reports


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))
    reports_dir = root / settings["reports_dir"]

    signal_out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else (root / "signal_out")
    if not signal_out_dir.is_absolute():
        signal_out_dir = root / signal_out_dir

    if not signal_out_dir.is_dir():
        print(f"Signal-Output-Verzeichnis fehlt: {signal_out_dir}")
        sys.exit(1)

    model = os.environ.get("AGENT_MODEL", "claude-opus-4-8")
    generated_at = _now_utc_iso()

    signals_dir = root / "docs" / "signals"
    signals_dir.mkdir(parents=True, exist_ok=True)
    log_path = signals_dir / "log.jsonl"

    signal_files = sorted(signal_out_dir.glob("*.json"))
    attached = 0
    log_lines: list[str] = []

    for sf in signal_files:
        safe = sf.stem
        symbol_dir = reports_dir / safe
        if not symbol_dir.is_dir():
            print(f"  WARN: kein Report-Verzeichnis fuer {safe!r} ({sf.name}) – uebersprungen")
            continue

        report_path = _latest_report(symbol_dir)
        if report_path is None:
            print(f"  WARN: keine Report-Datei in {symbol_dir} – uebersprungen")
            continue

        try:
            decision = json.loads(sf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  WARN: {sf.name} nicht lesbar ({exc}) – uebersprungen")
            continue

        report = json.loads(report_path.read_text(encoding="utf-8"))
        try:
            signal = build_signal(
                decision,
                report.get("technical"),
                report.get("snapshot"),
                generated_at=generated_at,
                model=model,
            )
        except ValueError as exc:
            print(f"  WARN: {sf.name} ungueltig ({exc}) – uebersprungen")
            continue

        attach_signal(report, signal)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        attached += 1
        print(f"  OK: signal an {report_path.relative_to(root)} angehaengt "
              f"({signal['direction']} conv {signal['conviction']}, "
              f"SL {signal['stop_loss']} TP {signal['take_profit']} R:R {signal['rr']})")

        log_lines.append(json.dumps({
            "date": report.get("date"),
            "symbol": report.get("symbol"),
            "display": decision.get("display") or report.get("display"),
            "direction": signal["direction"],
            "conviction": signal["conviction"],
            "entry": signal["entry"],
            "stop_loss": signal["stop_loss"],
            "take_profit": signal["take_profit"],
            "take_profit_2": signal["take_profit_2"],
            "rr": signal["rr"],
            "horizon_days": signal["horizon_days"],
            "generated_at": generated_at,
        }, ensure_ascii=False))

    if log_lines:
        with log_path.open("a", encoding="utf-8") as fh:
            for line in log_lines:
                fh.write(line + "\n")

    # index.json aus ALLEN Reports neu bauen, damit Signal-Chips erscheinen.
    all_reports = _load_all_reports(reports_dir)
    index = build_index(all_reports)
    (reports_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{attached} von {len(signal_files)} Signal-Dateien angehaengt; "
          f"{len(log_lines)} Log-Zeilen geschrieben; "
          f"index.json aus {len(all_reports)} Reports neu gebaut")


if __name__ == "__main__":
    main()
