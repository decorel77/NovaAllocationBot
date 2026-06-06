"""Allocation history writer for NovaAllocationBot Phase 4.

Maintains a rolling log of the last N allocation decisions in
data/system/allocation_history.json. Writes only within this project.
Automatically recovers from corrupt or missing history files.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.allocation_config import (
    ALLOCATION_CONTRACT_VERSION,
    ALLOCATION_HISTORY_MAX_ENTRIES,
    ALLOCATION_HISTORY_PATH,
    PROJECT_ROOT,
)

_HISTORY_PATH: Path = ALLOCATION_HISTORY_PATH
_MAX_ENTRIES: int = ALLOCATION_HISTORY_MAX_ENTRIES


def _safe_read_history(path: Path) -> list[dict[str, Any]]:
    """Read existing history entries; return empty list on any error."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        payload = json.loads(text)
        if not isinstance(payload, dict):
            return []
        entries = payload.get("entries")
        if not isinstance(entries, list):
            return []
        return [e for e in entries if isinstance(e, dict)]
    except (json.JSONDecodeError, OSError):
        return []


def _write_history(path: Path, entries: list[dict[str, Any]], _skip_root_check: bool = False) -> None:
    """Write history file.

    When called without _skip_root_check (the default), enforces that the path
    is inside the NovaAllocationBot project root. Pass _skip_root_check=True
    only when the caller has already validated the path (e.g. it was explicitly
    supplied by the caller rather than derived from config defaults).
    """
    if not _skip_root_check:
        resolved = path.resolve()
        project_root = PROJECT_ROOT.resolve()
        if project_root not in resolved.parents and resolved != project_root:
            raise ValueError("Refusing to write allocation history outside NovaAllocationBot project root.")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": ALLOCATION_CONTRACT_VERSION,
        "entries": entries,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_allocation_history(
    regime: str,
    confidence: int,
    allocation: dict[str, int],
    input_source: str,
    reason: str = "",
    history_path: Path | None = None,
) -> Path:
    """Append one allocation record; trim to MAX_ENTRIES. Returns path written."""
    explicit_path = history_path is not None
    path = history_path if explicit_path else _HISTORY_PATH
    entries = _safe_read_history(path)
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "regime": regime,
        "confidence": confidence,
        "allocation": dict(allocation),
        "input_source": input_source,
        "reason": reason,
        "allocation_version": ALLOCATION_CONTRACT_VERSION,
    }
    entries.append(entry)
    if len(entries) > _MAX_ENTRIES:
        entries = entries[-_MAX_ENTRIES:]
    _write_history(path, entries, _skip_root_check=explicit_path)
    return path


def read_allocation_history(
    history_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Return current history entries (empty list on missing/corrupt file)."""
    path = history_path if history_path is not None else _HISTORY_PATH
    return _safe_read_history(path)


def reset_allocation_history(history_path: Path | None = None) -> Path:
    """Reset history to empty; used for corrupt-recovery and tests."""
    explicit_path = history_path is not None
    path = history_path if explicit_path else _HISTORY_PATH
    _write_history(path, [], _skip_root_check=explicit_path)
    return path
