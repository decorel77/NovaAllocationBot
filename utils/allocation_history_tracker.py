"""
Allocation recommendation history tracker for NovaAllocationBot.

Appends each allocation recommendation to data/reports/allocation_history.json
as a time-series log. Enables regime-based evaluation and drift detection.

Entry schema (v1.0):
  timestamp           — ISO-8601 UTC
  recommended_splits  — dict[str, float]  (bot_name → percentage 0-100)
  regime_context      — dict with regime, confidence, input_source
  warnings            — list[str]
  schema_version      — "1.0"

Read-only analytics. No broker. No execution. Writes to data/reports/ only.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_DEFAULT_REPORTS_DIR = Path(__file__).resolve().parents[1] / "data" / "reports"
_HISTORY_FILE = _DEFAULT_REPORTS_DIR / "allocation_history.json"

# Read source for existing entries (data/system/allocation_history.json)
_SYSTEM_HISTORY_FILE = Path(__file__).resolve().parents[1] / "data" / "system" / "allocation_history.json"

SCHEMA_VERSION = "1.0"


@dataclass
class RegimeContext:
    regime: str
    confidence: float
    input_source: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AllocationHistoryEntry:
    recommended_splits: dict[str, float]
    regime_context: RegimeContext
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    warnings: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class AllocationHistoryTracker:
    """Appends AllocationHistoryEntry records to data/reports/allocation_history.json."""

    def __init__(self, history_file: Optional[Path] = None) -> None:
        self._file = history_file or _HISTORY_FILE
        self._file.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: AllocationHistoryEntry) -> None:
        """Append a new entry to the history file."""
        entries = self._load()
        entries.append(entry.to_dict())
        self._save(entries)

    def read_all(self) -> list[dict]:
        """Return all entries (oldest first)."""
        return self._load()

    def latest(self) -> Optional[dict]:
        entries = self._load()
        return entries[-1] if entries else None

    def entry_count(self) -> int:
        return len(self._load())

    def _load(self) -> list[dict]:
        if not self._file.exists():
            return []
        with open(self._file, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
        # Legacy: {entries: [...]}
        return data.get("entries", [])

    def _save(self, entries: list[dict]) -> None:
        with open(self._file, "w", encoding="utf-8") as fh:
            json.dump(entries, fh, indent=2)


def entry_from_system_record(record: dict) -> AllocationHistoryEntry:
    """Build an AllocationHistoryEntry from a data/system/allocation_history.json record."""
    allocation = record.get("allocation", {})
    # Convert integer percentages to floats
    splits = {k: float(v) for k, v in allocation.items()}

    regime_ctx = RegimeContext(
        regime=record.get("regime", "UNKNOWN"),
        confidence=float(record.get("confidence", 0.0)),
        input_source=record.get("input_source", ""),
    )

    warnings: list[str] = []
    if not allocation:
        warnings.append("Empty allocation record — no splits available.")
    if regime_ctx.regime == "UNKNOWN":
        warnings.append("Regime not recorded for this allocation.")

    return AllocationHistoryEntry(
        timestamp=record.get("timestamp", datetime.now(timezone.utc).isoformat()),
        recommended_splits=splits,
        regime_context=regime_ctx,
        warnings=warnings,
    )


def migrate_from_system_history(
    tracker: Optional[AllocationHistoryTracker] = None,
    source_file: Optional[Path] = None,
) -> int:
    """Read data/system/allocation_history.json and write to tracker.

    Returns the number of entries migrated. Safe to call multiple times —
    checks existing entry count and only migrates new records.
    """
    src = source_file or _SYSTEM_HISTORY_FILE
    if not src.exists():
        return 0

    with open(src, encoding="utf-8") as fh:
        data = json.load(fh)

    records = data if isinstance(data, list) else data.get("entries", [])
    t = tracker or AllocationHistoryTracker()
    existing = t.entry_count()
    new_records = records[existing:]

    for record in new_records:
        t.append(entry_from_system_record(record))

    return len(new_records)
