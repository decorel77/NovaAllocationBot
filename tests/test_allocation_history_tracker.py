"""Tests for AllocationHistoryTracker (ALLOC-ANALYTICS-001)."""
import json
from pathlib import Path

import pytest

from utils.allocation_history_tracker import (
    AllocationHistoryEntry,
    AllocationHistoryTracker,
    RegimeContext,
    entry_from_system_record,
    migrate_from_system_history,
)


def _tracker(tmp_path: Path) -> AllocationHistoryTracker:
    return AllocationHistoryTracker(history_file=tmp_path / "allocation_history.json")


def _entry(regime: str = "BULL", splits: dict | None = None) -> AllocationHistoryEntry:
    return AllocationHistoryEntry(
        recommended_splits=splits or {"NovaBotV2": 90.0, "NovaBotV2Options": 10.0},
        regime_context=RegimeContext(regime=regime, confidence=80.0, input_source="test"),
    )


def test_append_creates_file(tmp_path: Path) -> None:
    t = _tracker(tmp_path)
    t.append(_entry())
    assert (tmp_path / "allocation_history.json").exists()


def test_append_writes_list(tmp_path: Path) -> None:
    t = _tracker(tmp_path)
    t.append(_entry())
    data = json.loads((tmp_path / "allocation_history.json").read_text())
    assert isinstance(data, list)
    assert len(data) == 1


def test_multiple_appends(tmp_path: Path) -> None:
    t = _tracker(tmp_path)
    t.append(_entry("BULL"))
    t.append(_entry("BEAR"))
    assert t.entry_count() == 2


def test_entry_schema_version(tmp_path: Path) -> None:
    t = _tracker(tmp_path)
    t.append(_entry())
    entry = t.read_all()[0]
    assert entry["schema_version"] == "1.0"


def test_entry_has_required_fields(tmp_path: Path) -> None:
    t = _tracker(tmp_path)
    t.append(_entry())
    e = t.read_all()[0]
    assert "timestamp" in e
    assert "recommended_splits" in e
    assert "regime_context" in e
    assert "warnings" in e


def test_recommended_splits_stored(tmp_path: Path) -> None:
    t = _tracker(tmp_path)
    t.append(_entry(splits={"NovaBotV2": 70.0, "NovaBotV2Options": 5.0, "Cash": 25.0}))
    e = t.read_all()[0]
    assert e["recommended_splits"]["NovaBotV2"] == 70.0
    assert e["recommended_splits"]["Cash"] == 25.0


def test_regime_context_stored(tmp_path: Path) -> None:
    t = _tracker(tmp_path)
    t.append(_entry("BEAR"))
    e = t.read_all()[0]
    assert e["regime_context"]["regime"] == "BEAR"
    assert e["regime_context"]["confidence"] == 80.0


def test_latest_returns_last(tmp_path: Path) -> None:
    t = _tracker(tmp_path)
    t.append(_entry("BULL"))
    t.append(_entry("BEAR"))
    assert t.latest()["regime_context"]["regime"] == "BEAR"


def test_latest_none_when_empty(tmp_path: Path) -> None:
    t = _tracker(tmp_path)
    assert t.latest() is None


def test_entry_from_system_record() -> None:
    record = {
        "allocation": {"NovaBotV2": 90, "NovaBotV2Options": 10},
        "confidence": 80,
        "input_source": "MarketRegimeBot",
        "regime": "BULL",
        "timestamp": "2026-06-06T18:00:00+00:00",
    }
    entry = entry_from_system_record(record)
    assert entry.regime_context.regime == "BULL"
    assert entry.recommended_splits["NovaBotV2"] == 90.0
    assert entry.warnings == []


def test_migrate_from_system_history(tmp_path: Path) -> None:
    src = tmp_path / "system_history.json"
    records = [
        {
            "allocation": {"NovaBotV2": 90, "NovaBotV2Options": 10},
            "confidence": 80,
            "input_source": "test",
            "regime": "BULL",
            "timestamp": "2026-06-01T00:00:00+00:00",
        },
        {
            "allocation": {"NovaBotV2": 70, "NovaBotV2Options": 5, "Cash": 25},
            "confidence": 70,
            "input_source": "test",
            "regime": "BEAR",
            "timestamp": "2026-06-02T00:00:00+00:00",
        },
    ]
    src.write_text(json.dumps(records), encoding="utf-8")
    t = _tracker(tmp_path)
    migrated = migrate_from_system_history(tracker=t, source_file=src)
    assert migrated == 2
    assert t.entry_count() == 2


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    src = tmp_path / "system_history.json"
    src.write_text(json.dumps([{
        "allocation": {"NovaBotV2": 90},
        "confidence": 80,
        "input_source": "test",
        "regime": "BULL",
        "timestamp": "2026-06-01T00:00:00+00:00",
    }]), encoding="utf-8")
    t = _tracker(tmp_path)
    migrate_from_system_history(tracker=t, source_file=src)
    migrated_again = migrate_from_system_history(tracker=t, source_file=src)
    assert migrated_again == 0
    assert t.entry_count() == 1


def test_no_broker_imports() -> None:
    import importlib
    mod = importlib.import_module("utils.allocation_history_tracker")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "ib_insync" not in src
    assert "ibapi" not in src
