"""Tests for allocation_regime_analysis.py (MASTER-028)."""
import json
from pathlib import Path

from core.allocation_regime_analysis import analyse, generate, load_history, render_report


# REPAIR-007: the real allocation_history.json schema written by
# core.allocation_history.append_allocation_history — top-level ``regime`` and an
# ``allocation`` dict {NovaBotV2, NovaBotV2Options, Cash}. (The old test fixture
# used a fictional recommended_splits/regime_context shape that never matched.)
SAMPLE_ENTRIES = [
    {
        "timestamp": "2026-06-01T10:00:00+00:00",
        "regime": "BULL",
        "confidence": 80,
        "allocation": {"NovaBotV2": 90, "NovaBotV2Options": 10, "Cash": 0},
        "input_source": "regime_aware",
        "reason": "Regime-aware allocation for verified-real regime 'BULL'",
        "allocation_version": "1.0",
    },
    {
        "timestamp": "2026-06-02T10:00:00+00:00",
        "regime": "BEAR",
        "confidence": 70,
        "allocation": {"NovaBotV2": 50, "NovaBotV2Options": 0, "Cash": 50},
        "input_source": "regime_aware",
        "reason": "Regime-aware allocation for verified-real regime 'BEAR'",
        "allocation_version": "1.0",
    },
    {
        "timestamp": "2026-06-03T10:00:00+00:00",
        "regime": "BULL",
        "confidence": 90,
        "allocation": {"NovaBotV2": 80, "NovaBotV2Options": 10, "Cash": 10},
        "input_source": "regime_aware",
        "reason": "Regime-aware allocation for verified-real regime 'BULL'",
        "allocation_version": "1.0",
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
