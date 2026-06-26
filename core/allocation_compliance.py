"""Allocation compliance checker for NovaAllocationBot Phase 5.

Compares recommended target allocation (%) against current portfolio values.
Produces per-bucket and global compliance status. Dry-run only — no trades,
no broker calls, no money movement.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.allocation_config import APPS_ROOT, COMPLIANCE_TOLERANCE_PCT

# Fields searched (in order) when reading equity from a bot snapshot.
_EQUITY_FIELD_NAMES = (
    "equity",
    "account_value",
    "net_liquidation",
    "portfolio_value",
    "current_value",
    "paper_pnl",
)

# Buckets that map directly to an upstream bot snapshot.
_BOT_SNAPSHOT_MAP: dict[str, Path] = {
    "NovaBotV2": APPS_ROOT / "NovaBotV2" / "data" / "system" / "result_snapshot.json",
    "NovaBotV2Options": APPS_ROOT / "NovaBotV2Options" / "data" / "system" / "result_snapshot.json",
}

# Status constants.
BUCKET_OK = "OK"
BUCKET_UNDER = "UNDERALLOCATED"
BUCKET_OVER = "OVERALLOCATED"
BUCKET_UNKNOWN = "UNKNOWN"

GLOBAL_COMPLIANT = "COMPLIANT"
GLOBAL_DRIFT = "DRIFT_WARNING"
GLOBAL_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class BucketComplianceResult:
    bucket: str
    target_pct: float
    current_pct: float | None
    deviation_pct: float | None
    status: str


@dataclass(frozen=True)
class AllocationComplianceResult:
    global_status: str
    tolerance_pct: float
    buckets: tuple[BucketComplianceResult, ...]
    dry_run: bool = True
    broker_execution_enabled: bool = False
    order_placement_enabled: bool = False
    money_movement_enabled: bool = False
    live_trading_enabled: bool = False
    source: str = "synthetic_fixture"
    notes: tuple[str, ...] = ()

    def validate(self) -> None:
        assert self.dry_run
        assert not self.broker_execution_enabled
        assert not self.order_placement_enabled
        assert not self.money_movement_enabled
        assert not self.live_trading_enabled

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "global_status": self.global_status,
            "tolerance_pct": self.tolerance_pct,
            "dry_run": self.dry_run,
            "broker_execution_enabled": self.broker_execution_enabled,
            "order_placement_enabled": self.order_placement_enabled,
            "money_movement_enabled": self.money_movement_enabled,
            "live_trading_enabled": self.live_trading_enabled,
            "source": self.source,
            "notes": list(self.notes),
            "buckets": [
                {
                    "bucket": b.bucket,
                    "target_pct": b.target_pct,
                    "current_pct": b.current_pct,
                    "deviation_pct": b.deviation_pct,
                    "status": b.status,
                }
                for b in self.buckets
            ],
        }


def _read_equity_from_snapshot(path: Path) -> float | None:
    """Try to extract a numeric equity-like value from a bot snapshot."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    for key in _EQUITY_FIELD_NAMES:
        value = payload.get(key)
        # A non-finite equity (NaN/+-Infinity, parsed by json.loads from a bot
        # snapshot) satisfies ``value > 0`` (inf > 0 is True) and would poison the
        # compliance percentages with nan once divided by the (now-infinite) total.
        # Reject non-finite so the bucket reads as missing (UNKNOWN) — fail closed.
        if isinstance(value, (int, float)) and math.isfinite(value) and value > 0:
            return float(value)
    return None


def read_current_values(
    snapshot_map: dict[str, Path] | None = None,
    override: dict[str, float | None] | None = None,
) -> dict[str, float | None]:
    """Return current equity values per allocation bucket.

    `override` bypasses snapshot reading — used in tests and synthetic fixtures.
    Unknown buckets (Cash, future bots) always return None.
    """
    if override is not None:
        return dict(override)
    paths = snapshot_map if snapshot_map is not None else _BOT_SNAPSHOT_MAP
    values: dict[str, float | None] = {}
    for bucket, path in paths.items():
        values[bucket] = _read_equity_from_snapshot(path)
    return values


def _classify_bucket(
    deviation_pct: float | None,
    tolerance: float,
) -> str:
    if deviation_pct is None:
        return BUCKET_UNKNOWN
    if abs(deviation_pct) <= tolerance:
        return BUCKET_OK
    return BUCKET_UNDER if deviation_pct < 0 else BUCKET_OVER


def build_allocation_compliance(
    target_allocation: dict[str, int],
    current_values: dict[str, float | None] | None = None,
    tolerance_pct: float = COMPLIANCE_TOLERANCE_PCT,
    snapshot_map: dict[str, Path] | None = None,
) -> AllocationComplianceResult:
    """Compare target allocation % against current values.

    `current_values` maps bucket → absolute value (any currency-agnostic unit).
    Pass None to read from bot snapshots (Phase 5: returns UNKNOWN for all,
    since no live equity data exists yet).
    """
    if current_values is None:
        current_values = read_current_values(snapshot_map=snapshot_map)

    def _finite_or_none(v: float | None) -> float | None:
        # A non-finite (NaN/+-Infinity) or non-numeric value passed via the public
        # ``current_values`` param must not poison the total / per-bucket
        # percentages — fail closed to None (UNKNOWN) for that bucket.
        if isinstance(v, (int, float)) and math.isfinite(v):
            return v
        return None

    # Fill in None for buckets not present in current_values (e.g. Cash).
    all_current: dict[str, float | None] = {
        b: _finite_or_none(current_values.get(b)) for b in target_allocation
    }

    known_values = {b: v for b, v in all_current.items() if v is not None}
    total = sum(known_values.values()) if known_values else None

    bucket_results: list[BucketComplianceResult] = []
    for bucket, target_pct in target_allocation.items():
        raw = all_current.get(bucket)
        if raw is None or total is None or total == 0:
            bucket_results.append(BucketComplianceResult(
                bucket=bucket,
                target_pct=float(target_pct),
                current_pct=None,
                deviation_pct=None,
                status=BUCKET_UNKNOWN,
            ))
        else:
            current_pct = raw / total * 100.0
            deviation_pct = current_pct - float(target_pct)
            status = _classify_bucket(deviation_pct, tolerance_pct)
            bucket_results.append(BucketComplianceResult(
                bucket=bucket,
                target_pct=float(target_pct),
                current_pct=round(current_pct, 4),
                deviation_pct=round(deviation_pct, 4),
                status=status,
            ))

    # Only buckets with a non-zero target are "significant" for global status.
    # Zero-target unknown buckets (e.g. Cash=None when target=0) do not block
    # a COMPLIANT verdict for the rest of the portfolio.
    significant_statuses = {
        b.status for b in bucket_results if b.target_pct > 0
    }
    if BUCKET_UNKNOWN in significant_statuses:
        global_status = GLOBAL_UNKNOWN
    elif significant_statuses <= {BUCKET_OK}:
        global_status = GLOBAL_COMPLIANT
    else:
        global_status = GLOBAL_DRIFT

    has_live_data = any(v is not None for v in all_current.values())
    source = "bot_snapshots" if has_live_data else "synthetic_fixture"
    notes: list[str] = []
    if global_status == GLOBAL_UNKNOWN:
        notes.append("Current values unavailable; compliance cannot be determined.")
    if global_status == GLOBAL_DRIFT:
        drifted = [b.bucket for b in bucket_results if b.status in (BUCKET_UNDER, BUCKET_OVER)]
        notes.append(f"Drift detected in: {', '.join(drifted)}")

    return AllocationComplianceResult(
        global_status=global_status,
        tolerance_pct=tolerance_pct,
        buckets=tuple(bucket_results),
        source=source,
        notes=tuple(notes),
    )
