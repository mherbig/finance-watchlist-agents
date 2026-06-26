# scripts/build_reports.py
"""CLI: liest die neuesten Rohdaten je Symbol, baut Reports + index.json.

Liest data/<safe_name>/raw-<datum>.json (neuestes Datum je Symbol), schreibt
docs/reports/<safe_name>/<datum>.json und docs/reports/index.json.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.data.symbol_map import safe_name, load_watchlist  # noqa: E402
from src.analysis.report import build_report, build_index  # noqa: E402


def _latest_raw(symbol_dir: Path) -> Path | None:
    """Neueste raw-<datum>.json in einem Symbol-Verzeichnis (lexikografisch = chronologisch)."""
    files = sorted(symbol_dir.glob("raw-*.json"))
    return files[-1] if files else None


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = json.loads((root / "config" / "settings.json").read_text(encoding="utf-8"))
    data_dir = root / settings["data_dir"]
    reports_dir = root / settings["reports_dir"]

    generated_at = datetime.now(timezone.utc).isoformat()
    wl = load_watchlist(root / "config" / "watchlist.json")

    reports = []
    written = 0
    available_count = 0

    for entry in wl:
        sname = safe_name(entry["display"])
        symbol_dir = data_dir / sname
        if not symbol_dir.is_dir():
            continue
        raw_path = _latest_raw(symbol_dir)
        if raw_path is None:
            continue
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        report = build_report(raw, generated_at)
        reports.append(report)

        out_dir = reports_dir / sname
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{report['date']}.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        written += 1
        if report["available"]:
            available_count += 1

    index = build_index(reports)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{written} Reports geschrieben, {available_count} verfuegbar -> {reports_dir}")
    print(f"index.json: {len(index)} Zeilen")


if __name__ == "__main__":
    main()
