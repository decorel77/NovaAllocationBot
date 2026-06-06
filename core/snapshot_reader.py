"""Read-only result snapshot loading for upstream NOVA bots."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.allocation_config import DEFAULT_SNAPSHOT_PATHS


@dataclass(frozen=True)
class BotSnapshotStatus:
    bot_name: str
    status: str | None = None
    dry_run: bool | None = None
    updated_at: str | None = None
    error_count: int = 0
    raw_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BotHealthSummary:
    bot_name: str
    health_score: int
    health_status: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SnapshotReadResult:
    bot_name: str
    path: str
    exists: bool
    valid: bool
    snapshot: BotSnapshotStatus | None = None
    warnings: tuple[str, ...] = ()


def read_configured_snapshots(
    snapshot_paths: dict[str, Path] | None = None,
) -> dict[str, SnapshotReadResult]:
    paths = snapshot_paths or DEFAULT_SNAPSHOT_PATHS
    return {bot_name: read_bot_snapshot(bot_name, path) for bot_name, path in paths.items()}


def read_bot_snapshot(bot_name: str, path: str | Path) -> SnapshotReadResult:
    snapshot_path = Path(path)
    if not snapshot_path.exists():
        return SnapshotReadResult(
            bot_name=bot_name,
            path=str(snapshot_path),
            exists=False,
            valid=False,
            warnings=(f"{bot_name} snapshot missing",),
        )

    try:
        text = snapshot_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return SnapshotReadResult(
            bot_name=bot_name,
            path=str(snapshot_path),
            exists=True,
            valid=False,
            warnings=(f"{bot_name} snapshot unreadable: {exc}",),
        )

    if not text:
        return SnapshotReadResult(
            bot_name=bot_name,
            path=str(snapshot_path),
            exists=True,
            valid=False,
            warnings=(f"{bot_name} snapshot empty",),
        )

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return SnapshotReadResult(
            bot_name=bot_name,
            path=str(snapshot_path),
            exists=True,
            valid=False,
            warnings=(f"{bot_name} snapshot invalid JSON",),
        )

    if not isinstance(payload, dict):
        return SnapshotReadResult(
            bot_name=bot_name,
            path=str(snapshot_path),
            exists=True,
            valid=False,
            warnings=(f"{bot_name} snapshot root is not an object",),
        )

    snapshot = BotSnapshotStatus(
        bot_name=bot_name,
        status=_extract_status(payload),
        dry_run=_extract_dry_run(payload),
        updated_at=_extract_updated_at(payload),
        error_count=_extract_error_count(payload),
        raw_fields=dict(payload),
    )
    return SnapshotReadResult(
        bot_name=bot_name,
        path=str(snapshot_path),
        exists=True,
        valid=True,
        snapshot=snapshot,
        warnings=(),
    )


def _extract_status(payload: dict[str, Any]) -> str | None:
    for key in ("status", "health_status", "worker_entrypoint_status", "final_status"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    worker = payload.get("worker_entrypoint")
    if isinstance(worker, dict):
        value = worker.get("status") or worker.get("final_status")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_dry_run(payload: dict[str, Any]) -> bool | None:
    for key in ("dry_run", "report_only", "paper_only"):
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _extract_updated_at(payload: dict[str, Any]) -> str | None:
    for key in (
        "completed_at",
        "updated_at",
        "generated_at_utc",
        "generated_at",
        "worker_entrypoint_timestamp",
        "started_at",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_error_count(payload: dict[str, Any]) -> int:
    candidates = [payload.get("errors"), payload.get("error_count")]
    cycle_report = payload.get("cycle_report")
    if isinstance(cycle_report, dict):
        candidates.append(cycle_report.get("errors"))
    worker = payload.get("worker_entrypoint")
    if isinstance(worker, dict):
        candidates.append(worker.get("errors"))

    for value in candidates:
        if isinstance(value, int):
            return max(value, 0)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            return len(value)
    return 0
