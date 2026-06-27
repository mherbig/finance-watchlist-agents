"""TDD-Tests fuer src/analysis/agent_analysis (validate + attach)."""
import pytest

from src.analysis.agent_analysis import validate_agent_analysis, attach


def _valid_analysis():
    return {
        "track": "fundamental",
        "agents_run": ["market-researcher", "earnings-reviewer"],
        "summary": "Kurze Synthese ohne Empfehlung.",
        "sections": [
            {"agent": "market-researcher", "title": "Markt & Sektor",
             "body": "Markdown-Text **fett**."},
        ],
    }


def _base_report():
    return {
        "symbol": "AAPL",
        "display": "APPLE",
        "asset_class": "stock",
        "headline": "unveraendert",
    }


# --- validate: gueltiger Fall ---------------------------------------------

def test_validate_accepts_valid():
    # darf nicht werfen
    validate_agent_analysis(_valid_analysis())


def test_validate_accepts_technical_track():
    d = _valid_analysis()
    d["track"] = "technical"
    validate_agent_analysis(d)


def test_validate_accepts_empty_sections_list():
    d = _valid_analysis()
    d["sections"] = []
    validate_agent_analysis(d)


# --- validate: ungueltige Faelle -------------------------------------------

def test_validate_rejects_bad_track():
    d = _valid_analysis()
    d["track"] = "quant"
    with pytest.raises(ValueError):
        validate_agent_analysis(d)


def test_validate_rejects_missing_track():
    d = _valid_analysis()
    del d["track"]
    with pytest.raises(ValueError):
        validate_agent_analysis(d)


def test_validate_rejects_agents_run_not_list():
    d = _valid_analysis()
    d["agents_run"] = "market-researcher"
    with pytest.raises(ValueError):
        validate_agent_analysis(d)


def test_validate_rejects_agents_run_empty():
    d = _valid_analysis()
    d["agents_run"] = []
    with pytest.raises(ValueError):
        validate_agent_analysis(d)


def test_validate_rejects_agents_run_non_str_item():
    d = _valid_analysis()
    d["agents_run"] = ["ok", 5]
    with pytest.raises(ValueError):
        validate_agent_analysis(d)


def test_validate_rejects_empty_summary():
    d = _valid_analysis()
    d["summary"] = ""
    with pytest.raises(ValueError):
        validate_agent_analysis(d)


def test_validate_rejects_non_str_summary():
    d = _valid_analysis()
    d["summary"] = 123
    with pytest.raises(ValueError):
        validate_agent_analysis(d)


def test_validate_rejects_sections_not_list():
    d = _valid_analysis()
    d["sections"] = {"agent": "x"}
    with pytest.raises(ValueError):
        validate_agent_analysis(d)


def test_validate_rejects_section_item_not_dict():
    d = _valid_analysis()
    d["sections"] = ["not-a-dict"]
    with pytest.raises(ValueError):
        validate_agent_analysis(d)


def test_validate_rejects_section_missing_field():
    d = _valid_analysis()
    d["sections"] = [{"agent": "x", "title": "T"}]  # body fehlt
    with pytest.raises(ValueError):
        validate_agent_analysis(d)


def test_validate_rejects_section_empty_field():
    d = _valid_analysis()
    d["sections"] = [{"agent": "x", "title": "", "body": "b"}]
    with pytest.raises(ValueError):
        validate_agent_analysis(d)


def test_validate_rejects_section_non_str_field():
    d = _valid_analysis()
    d["sections"] = [{"agent": "x", "title": "T", "body": 9}]
    with pytest.raises(ValueError):
        validate_agent_analysis(d)


# --- attach ----------------------------------------------------------------

def test_attach_sets_block_and_stamps():
    rep = _base_report()
    out = attach(rep, _valid_analysis(),
                 generated_at="2026-06-26T22:00:00Z", model="claude-opus-4-8")
    aa = out["agent_analysis"]
    assert aa["generated_at"] == "2026-06-26T22:00:00Z"
    assert aa["model"] == "claude-opus-4-8"
    assert "disclaimer" not in aa  # Disclaimer wird nicht mehr gestempelt
    assert aa["track"] == "fundamental"
    assert aa["agents_run"] == ["market-researcher", "earnings-reviewer"]
    assert aa["summary"] == "Kurze Synthese ohne Empfehlung."
    assert aa["sections"][0]["title"] == "Markt & Sektor"


def test_attach_returns_report_and_preserves_other_fields():
    rep = _base_report()
    out = attach(rep, _valid_analysis(),
                 generated_at="2026-06-26T22:00:00Z", model="claude-opus-4-8")
    assert out is rep  # selbe Referenz, in-place
    assert out["symbol"] == "AAPL"
    assert out["display"] == "APPLE"
    assert out["headline"] == "unveraendert"
    assert out["asset_class"] == "stock"


def test_attach_always_stamps_passed_values_over_existing():
    rep = _base_report()
    analysis = _valid_analysis()
    analysis["generated_at"] = "1999-01-01T00:00:00Z"
    analysis["model"] = "old-model"
    out = attach(rep, analysis,
                 generated_at="2026-06-26T22:00:00Z", model="claude-opus-4-8")
    assert out["agent_analysis"]["generated_at"] == "2026-06-26T22:00:00Z"
    assert out["agent_analysis"]["model"] == "claude-opus-4-8"


def test_attach_invalid_raises():
    rep = _base_report()
    bad = _valid_analysis()
    bad["track"] = "nope"
    with pytest.raises(ValueError):
        attach(rep, bad, generated_at="2026-06-26T22:00:00Z", model="m")
    # Report darf bei Fehler nicht angefasst werden
    assert "agent_analysis" not in rep
