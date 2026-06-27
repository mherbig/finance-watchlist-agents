# src/analysis/agent_analysis.py
"""Qualitative Agenten-Analyse je Symbol: validieren + an Report anhaengen.

Der Block ist ein Entwurf zur menschlichen Pruefung, ohne Anlageempfehlung.
Keine Netzwerkaufrufe.
"""
from __future__ import annotations

_VALID_TRACKS = {"fundamental", "technical"}
_SECTION_FIELDS = ("agent", "title", "body")


def _is_nonempty_str(x: object) -> bool:
    return isinstance(x, str) and x.strip() != ""


def validate_agent_analysis(d: dict) -> None:
    """Wirft ValueError, wenn der Agenten-Analyse-Block ungueltig ist.

    Geprueft werden track, agents_run, summary und sections. generated_at,
    model und disclaimer werden hier NICHT verlangt (die stempelt attach()).
    """
    if not isinstance(d, dict):
        raise ValueError("agent_analysis muss ein dict sein")

    track = d.get("track")
    if track not in _VALID_TRACKS:
        raise ValueError(
            f"track muss in {sorted(_VALID_TRACKS)} sein, war {track!r}")

    agents_run = d.get("agents_run")
    if not isinstance(agents_run, list) or not agents_run:
        raise ValueError("agents_run muss eine nicht-leere Liste sein")
    if not all(_is_nonempty_str(a) for a in agents_run):
        raise ValueError("agents_run muss nur nicht-leere Strings enthalten")

    if not _is_nonempty_str(d.get("summary")):
        raise ValueError("summary muss ein nicht-leerer String sein")

    sections = d.get("sections")
    if not isinstance(sections, list):
        raise ValueError("sections muss eine Liste sein")
    for i, sec in enumerate(sections):
        if not isinstance(sec, dict):
            raise ValueError(f"sections[{i}] muss ein dict sein")
        for field in _SECTION_FIELDS:
            if not _is_nonempty_str(sec.get(field)):
                raise ValueError(
                    f"sections[{i}].{field} muss ein nicht-leerer String sein")


def attach(report: dict, analysis: dict, generated_at: str, model: str) -> dict:
    """Validiert analysis und setzt report['agent_analysis'] mit Stempelung.

    generated_at und model werden immer mit den uebergebenen Werten gestempelt
    (vorhandene Werte in analysis werden ueberschrieben). Andere Report-Felder
    bleiben unangetastet. Gibt den (in-place geaenderten) Report zurueck.
    """
    validate_agent_analysis(analysis)

    block = dict(analysis)
    block["generated_at"] = generated_at
    block["model"] = model

    report["agent_analysis"] = block
    return report
