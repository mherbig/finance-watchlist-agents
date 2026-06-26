# scripts/attach_agent_analysis.py
"""CLI: haengt Agenten-Analyse-Bloecke an bestehende Reports an.

Liest ein Verzeichnis mit Agenten-Output-JSONs (Default: argv[1], sonst
``agent_out/``). Jede Datei heisst ``<safe_name>.json`` und hat die Form::

    {"display", "safe_name", "track", "agents_run", "summary", "sections"}

Fuer jede Datei wird der neueste Report unter docs/reports/<safe_name>/*.json
geladen, attach() aufgerufen und zurueckgeschrieben. Anschliessend wird
docs/reports/index.json aus ALLEN Report-Dateien neu gebaut (ohne die Reports
aus Rohdaten zu regenerieren), damit die Badges erscheinen.

Keine Netzwerkaufrufe.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.analysis import agent_analysis  # noqa: E402
from src.analysis.report import build_index  # noqa: E402


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _latest_report(symbol_dir: Path) -> Path | None:
    """Neuester <datum>.json-Report in einem Symbol-Verzeichnis."""
    files = sorted(symbol_dir.glob("*.json"))
    return files[-1] if files else None


def _load_all_reports(reports_dir: Path) -> list[dict]:
    """Laedt alle Report-Dateien (docs/reports/<safe>/<date>.json), ohne index.json."""
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

    agent_out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else (root / "agent_out")
    if not agent_out_dir.is_absolute():
        agent_out_dir = root / agent_out_dir

    if not agent_out_dir.is_dir():
        print(f"Agent-Output-Verzeichnis fehlt: {agent_out_dir}")
        sys.exit(1)

    model = os.environ.get("AGENT_MODEL", "claude-opus-4-8")
    generated_at = _now_utc_iso()

    agent_files = sorted(agent_out_dir.glob("*.json"))
    attached = 0

    for af in agent_files:
        safe = af.stem
        symbol_dir = reports_dir / safe
        if not symbol_dir.is_dir():
            print(f"  WARN: kein Report-Verzeichnis fuer {safe!r} ({af.name}) – uebersprungen")
            continue

        report_path = _latest_report(symbol_dir)
        if report_path is None:
            print(f"  WARN: keine Report-Datei in {symbol_dir} – uebersprungen")
            continue

        try:
            payload = json.loads(af.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  WARN: {af.name} nicht lesbar ({exc}) – uebersprungen")
            continue

        analysis = {
            "track": payload.get("track"),
            "agents_run": payload.get("agents_run"),
            "summary": payload.get("summary"),
            "sections": payload.get("sections"),
        }

        report = json.loads(report_path.read_text(encoding="utf-8"))
        try:
            agent_analysis.attach(report, analysis, generated_at=generated_at, model=model)
        except ValueError as exc:
            print(f"  WARN: {af.name} ungueltig ({exc}) – uebersprungen")
            continue

        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        attached += 1
        print(f"  OK: agent_analysis an {report_path.relative_to(root)} angehaengt")

    # index.json aus ALLEN Reports neu bauen, damit Badges erscheinen.
    all_reports = _load_all_reports(reports_dir)
    index = build_index(all_reports)
    (reports_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{attached} von {len(agent_files)} Agent-Output-Dateien angehaengt; "
          f"index.json aus {len(all_reports)} Reports neu gebaut")


if __name__ == "__main__":
    main()
