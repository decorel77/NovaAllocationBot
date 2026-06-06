"""Deterministic health scoring for read-only bot snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config.allocation_config import SNAPSHOT_STALE_AFTER_HOURS
from core.snapshot_reader import BotHealthSummary, SnapshotReadResult

GOOD_STATUS_VALUES = {
    "done",
    "ready",
    "ok",
    "healthy",
    "dry_run_complete",
    "safe_dry_run_decision",
    "ready_for_phase_3",
    "ready_for_phase_5",
    "ready_for_phase_7",
}


def evaluate_snapshot_health(
    read_result: SnapshotReadResult,
    now: datetime | None = None,
    stale_after_hours: int = SNAPSHOT_STALE_AFTER_HOURS,
) -> BotHealthSummary:
    now = now or datetime.now(timezone.utc)
    warnings = list(read_result.warnings)

    if not read_result.exists or not read_result.valid or read_result.snapshot is None:
        return BotHealthSummary(
            bot_name=read_result.bot_name,
            health_score=0,
            health_status="UNKNOWN",
            warnings=tuple(warnings),
        )

    snapshot = read_result.snapshot
    score = 70

    if snapshot.dry_run is True:
        score += 10
    elif snapshot.dry_run is False:
        score -= 20

    if snapshot.status is None:
        score -= 15
        warnings.append(f"{snapshot.bot_name} status unknown")
    elif snapshot.status.strip().lower() in GOOD_STATUS_VALUES:
        score += 10
    else:
        score -= 10

    if snapshot.updated_at is None:
        score -= 15
        warnings.append(f"{snapshot.bot_name} update timestamp missing")
    elif _is_stale(snapshot.updated_at, now, stale_after_hours):
        score -= 25
        warnings.append(f"{snapshot.bot_name} snapshot stale")
    else:
        score += 10

    if snapshot.error_count > 0:
        score -= min(snapshot.error_count * 10, 30)
        warnings.append(f"{snapshot.bot_name} snapshot reports errors")

    score = max(0, min(100, score))
    return BotHealthSummary(
        bot_name=snapshot.bot_name,
        health_score=score,
        health_status=_status_for_score(score),
        warnings=tuple(warnings),
    )


def evaluate_all_snapshot_health(
    read_results: dict[str, SnapshotReadResult],
    now: datetime | None = None,
) -> dict[str, BotHealthSummary]:
    return {
        bot_name: evaluate_snapshot_health(read_result, now=now)
        for bot_name, read_result in read_results.items()
    }


def _is_stale(timestamp: str, now: datetime, stale_after_hours: int) -> bool:
    parsed = _parse_timestamp(timestamp)
    if parsed is None:
        return True
    return now - parsed > timedelta(hours=stale_after_hours)


def _parse_timestamp(timestamp: str) -> datetime | None:
    normalized = timestamp.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _status_for_score(score: int) -> str:
    if score >= 80:
        return "HEALTHY"
    if score >= 60:
        return "WARNING"
    if score >= 30:
        return "DEGRADED"
    return "UNKNOWN"
