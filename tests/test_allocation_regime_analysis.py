"""Tests for allocation_regime_analysis.py (MASTER-028)."""
import json
from pathlib import Path

from core.allocation_regime_analysis import analyse, generate, load_history, render_report


SAMPLE_ENTRIES = [
    {
        "timestamp": "2026-06-01T10:00:00+00:00",
        "recommended_splits": {"NovaBotV2": 90.0, "cash": 10.0},
        "regime_context": {"regime": "BULL", "confidence": 0.8, "input_source": "test"},
        "warnings": [],
    },
    {
        "timestamp": "2026-06-02T10:00:00+00:00",
        "recommended_splits": {"NovaBotV2": 50.0, "cash": 50.0},
        "regime_context": {"regime": "BEAR", "confidence": 0.7, "input_source": "test"},
        "warnings": ["low confidence"],
    },
    {
        "timestamp": "2026-06-03T10:00:00+00:00",
        "recommended_splits": {"NovaBotV2": 80.0, "cash": 20.0},
        "regime_context": {"regime": "BULL", "confidence": 0.9, "input_source": "test"},
        "warnings": [],
    },
]


def test_analyse_groups_by_regime():
    stats = analyse(SAMPLE_ENTRIES)
    regimes = {s.regime for s in stats}
    assert "BULL" in regimes
    assert "BEAR" in regimes


def test_analyse_counts():
    stats = analyse(SAMPLE_ENTRIES)
    bull = next(s for s in stats if s.regime == "BULL")
    assert bull.entry_count == 2
    assert bull.avg_equity_pct is not None


def test_render_report_contains_table():
    stats = analyse(SAMPLE_ENTRIES)
    report = render_report(stats, len(SAMPLE_ENTRIES))
    assert "BULL" in report
    assert "BEAR" in report
    assert "Regime-Based" in report


def test_generate_writes_file(tmp_path):
    hist_file = tmp_path / "allocation_history.json"
    hist_file.write_text(json.dumps(SAMPLE_ENTRIES), encoding="utf-8")
    out_file = tmp_path / "allocation_regime_analysis.md"
    out = generate(hist_file, out_file)
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "BULL" in text


def test_empty_history(tmp_path):
    hist_file = tmp_path / "allocation_history.json"
    hist_file.write_text("[]", encoding="utf-8")
    stats = analyse(load_history(hist_file))
    report = render_report(stats, 0)
    assert "Total history entries:** 0" in report


def test_no_broker_imports():
    import core.allocation_regime_analysis as m
    src = Path(m.__file__).read_text(encoding="utf-8")
    assert "ibapi" not in src
    assert "import broker" not in src.lower()
