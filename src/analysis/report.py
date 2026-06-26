# src/analysis/report.py
"""Baut Per-Symbol-Reports (Spec §7) und die kompakte index.json-Zeile."""
from __future__ import annotations

from .technical import compute_technical

DISCLAIMER = "Entwurf zur Prüfung. Keine Anlageempfehlung."


def _headline(technical: dict | None, available: bool) -> str:
    """Deterministischer, kurzer deutscher Take. Keine Empfehlung."""
    if not available or technical is None:
        return "Daten nicht verfügbar – keine Analyse."
    trend = technical.get("trend", "side")
    rsi = technical.get("rsi14")
    rsi_str = "n/v" if rsi is None else f"{rsi:.0f}"
    return f"Trend {trend}, RSI {rsi_str} – Beobachtung, keine Empfehlung."


def build_report(raw: dict, generated_at: str, prior: dict | None = None) -> dict:
    """Erzeugt den Per-Symbol-Report gemaess Spec §7.

    Wenn ``prior`` (der zuvor geschriebene Report) ein ``agent_analysis``-Feld
    enthaelt, wird dieser Block unveraendert uebernommen, damit ein
    Daten-Refresh die qualitative Agenten-Analyse nicht ueberschreibt.
    """
    available = bool(raw.get("available"))
    technical = compute_technical(raw.get("time_series") or []) if available else None
    snapshot = raw.get("snapshot")

    report = {
        "symbol": raw.get("td_symbol"),
        "display": raw.get("display"),
        "asset_class": raw.get("asset_class"),
        "track": raw.get("track"),
        "date": raw.get("date"),
        "generated_at": generated_at,
        "available": available,
        "snapshot": dict(snapshot) if isinstance(snapshot, dict) else snapshot,
        "technical": technical,
        "fundamental": None,  # Platzhalter fuer die kuenftige Fundamental-Spur
        "headline": _headline(technical, available),
        "flags": [],
        "disclaimer": DISCLAIMER,
    }

    if isinstance(prior, dict) and prior.get("agent_analysis"):
        report["agent_analysis"] = prior["agent_analysis"]

    return report


def build_index(reports: list[dict]) -> list[dict]:
    """Eine kompakte Zeile je Report fuer das Grid (None-safe)."""
    rows = []
    for rep in reports:
        snapshot = rep.get("snapshot") or {}
        technical = rep.get("technical") or {}
        price = snapshot.get("price") if isinstance(snapshot, dict) else None
        change_pct = snapshot.get("change_pct") if isinstance(snapshot, dict) else None
        agent = rep.get("agent_analysis")
        has_agent = isinstance(agent, dict) and bool(agent)
        agents_run = agent.get("agents_run", []) if has_agent else []
        rows.append({
            "symbol": rep.get("symbol"),
            "display": rep.get("display"),
            "asset_class": rep.get("asset_class"),
            "track": rep.get("track"),
            "date": rep.get("date"),
            "available": rep.get("available"),
            "price": price,
            "change_pct": change_pct,
            "trend": technical.get("trend") if technical else None,
            "rsi": technical.get("rsi14") if technical else None,
            "bias": technical.get("bias") if technical else None,
            "headline": rep.get("headline"),
            "has_agent_analysis": has_agent,
            "agents_run": agents_run if isinstance(agents_run, list) else [],
        })
    return rows
