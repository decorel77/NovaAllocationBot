"""Safe dry-run allocation workflow.

Phase 2: reads upstream bot snapshots, validates fixed allocation, builds
recommendation-only allocation.
Phase 3: reads MarketRegimeBot regime snapshot and produces regime-based
allocation output. All operations remain read-only and dry-run.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config.allocation_config import (
    ALLOCATION_SNAPSHOT_FRESH_HOURS,
    DEFAULT_ALLOCATION_PERCENTAGES,
    DEFAULT_CASH_RESERVE_MINIMUM_PERCENTAGE,
    DEFAULT_SNAPSHOT_PATHS,
)
from core.allocation_contracts import (
    AllocationDecision,
    AllocationInputSnapshot,
    AllocationPlan,
    AllocationRiskState,
    BotAllocationTarget,
)
from core.allocation_compliance import build_allocation_compliance
from core.allocation_history import append_allocation_history
from core.authoritative_allocation import build_authoritative_allocation
from core.health_evaluator import evaluate_all_snapshot_health
from core.market_regime_adapter import read_market_regime_snapshot
from core.recommendation_engine import generate_allocation_recommendation
from core.regime_allocation_engine import build_regime_allocation
from core.snapshot_reader import BotHealthSummary, SnapshotReadResult, read_configured_snapshots

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "system" / "result_snapshot.json"
PRODUCER_ID = "NovaAllocationBot"
RESULT_SCHEMA_VERSION = "allocation_result.v2"


def build_default_allocation_plan() -> AllocationPlan:
    targets = tuple(
        BotAllocationTarget(bot_name=name, target_percentage=percentage)
        for name, percentage in DEFAULT_ALLOCATION_PERCENTAGES.items()
    )
    plan = AllocationPlan(
        targets=targets,
        cash_reserve_minimum_percentage=DEFAULT_CASH_RESERVE_MINIMUM_PERCENTAGE,
    )
    plan.validate()
    return plan


def build_dry_run_decision(
    snapshot_paths: dict[str, Path] | None = None,
) -> AllocationDecision:
    read_results = read_configured_snapshots(snapshot_paths or DEFAULT_SNAPSHOT_PATHS)
    health_results = evaluate_all_snapshot_health(read_results)
    return _build_dry_run_decision_from_health(read_results, health_results)


def _build_dry_run_decision_from_health(
    read_results: dict[str, SnapshotReadResult],
    health_results: dict[str, BotHealthSummary],
) -> AllocationDecision:
    bot_health = {
        bot_name: {
            "score": summary.health_score,
            "status": summary.health_status,
            "live_trading_active": (
                None
                if read_results[bot_name].snapshot is None
                else read_results[bot_name].snapshot.live_trading_active
            ),
        }
        for bot_name, summary in health_results.items()
    }
    warnings = tuple(
        warning
        for summary in health_results.values()
        for warning in summary.warnings
    )
    recommendation = generate_allocation_recommendation(
        bot_health=bot_health,
        warnings=warnings,
    )
    decision = AllocationDecision(
        status="SAFE_DRY_RUN_DECISION",
        plan=build_default_allocation_plan(),
        risk_state=AllocationRiskState(),
        input_snapshot=AllocationInputSnapshot(bot_health=bot_health),
        bot_health=bot_health,
        warnings=warnings,
        recommendation=recommendation.to_dict(),
        health_evaluated=True,
    )
    decision.validate()
    return decision


def write_result_snapshot(
    decision: AllocationDecision,
    result_path: Path | None = None,
    regime_allocation_dict: dict[str, Any] | None = None,
    compliance_dict: dict[str, Any] | None = None,
    authoritative_allocation_dict: dict[str, Any] | None = None,
    envelope_dict: dict[str, Any] | None = None,
) -> Path:
    result_path = result_path or RESULT_SNAPSHOT_PATH
    resolved_path = result_path.resolve()
    project_root = PROJECT_ROOT.resolve()
    if project_root not in resolved_path.parents and resolved_path != project_root:
        raise ValueError("Refusing to write outside NovaAllocationBot project root.")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    payload = decision.to_dict()
    if envelope_dict is not None:
        payload.update(envelope_dict)
    if regime_allocation_dict is not None:
        payload["regime_allocation"] = regime_allocation_dict
    if compliance_dict is not None:
        payload["allocation_compliance"] = compliance_dict
    if authoritative_allocation_dict is not None:
        # REPAIR-007: the single authoritative allocation. plan / recommendation /
        # regime_allocation remain only as labelled diagnostic inputs.
        payload["authoritative_allocation"] = authoritative_allocation_dict
    result_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result_path


def run_allocation_cycle(
    write_snapshot: bool = True,
    snapshot_paths: dict[str, Path] | None = None,
    regime_snapshot_path: Path | None = None,
    history_path: Path | None = None,
    current_values: dict[str, float | None] | None = None,
    produced_at: datetime | None = None,
) -> dict[str, Any]:
    produced_at_utc = _coerce_utc(produced_at)
    read_results = read_configured_snapshots(snapshot_paths or DEFAULT_SNAPSHOT_PATHS)
    health_results = evaluate_all_snapshot_health(read_results, now=produced_at_utc)
    decision = _build_dry_run_decision_from_health(read_results, health_results)
    regime_result = read_market_regime_snapshot(regime_snapshot_path, now=produced_at_utc)
    regime_allocation = build_regime_allocation(regime_result)
    regime_allocation_dict = regime_allocation.to_dict()

    # REPAIR-007: collapse plan / recommendation / regime into one authoritative
    # allocation. The regime only steers the decision when verified real.
    authoritative = build_authoritative_allocation(
        recommendation=decision.recommendation,
        regime_result=regime_result,
        regime_allocation=dict(regime_allocation.recommended_allocation),
    )

    # Compliance is measured against the authoritative allocation, not a separate
    # regime block, so the snapshot is internally consistent.
    compliance = build_allocation_compliance(
        target_allocation=dict(authoritative["allocation"]),
        current_values=current_values,
    )
    compliance_dict = compliance.to_dict()
    envelope = build_result_snapshot_envelope(
        produced_at=produced_at_utc,
        read_results=read_results,
        health_results=health_results,
        decision=decision,
        regime_result=regime_result,
        authoritative_allocation=authoritative,
    )
    output_path = None
    if write_snapshot:
        output_path = str(write_result_snapshot(
            decision,
            regime_allocation_dict=regime_allocation_dict,
            compliance_dict=compliance_dict,
            authoritative_allocation_dict=authoritative,
            envelope_dict=envelope,
        ))
        append_allocation_history(
            regime=regime_result.market_regime,
            confidence=regime_result.confidence,
            allocation=dict(authoritative["allocation"]),
            input_source=authoritative["source"],
            reason=authoritative["reason"],
            history_path=history_path,
        )
    return {
        "status": decision.status,
        "dry_run": decision.dry_run,
        "health_evaluated": decision.health_evaluated,
        "result_snapshot_path": output_path,
        "decision": decision.to_dict(),
        "snapshot_envelope": envelope,
        "regime_allocation": regime_allocation_dict,
        "allocation_compliance": compliance_dict,
        "authoritative_allocation": authoritative,
    }


def build_result_snapshot_envelope(
    *,
    produced_at: datetime,
    read_results: dict[str, SnapshotReadResult],
    health_results: dict[str, BotHealthSummary],
    decision: AllocationDecision,
    regime_result: Any,
    authoritative_allocation: dict[str, Any],
) -> dict[str, Any]:
    fresh_until = produced_at + timedelta(hours=ALLOCATION_SNAPSHOT_FRESH_HOURS)
    warnings: list[str] = list(decision.warnings)
    reasons: list[str] = []

    if not regime_result.regime_is_real:
        reasons.append(
            f"MarketRegimeBot input not real/fresh: {regime_result.reason}"
        )
    if authoritative_allocation.get("source") != "regime_aware":
        refused = authoritative_allocation.get("refused_regime_reason")
        if refused:
            reasons.append(str(refused))
    warnings.extend(str(w) for w in getattr(regime_result, "warnings", ()))
    warnings.extend(str(w) for w in authoritative_allocation.get("regime_warnings", ()))

    for bot_name in ("NovaBotV2", "NovaBotV2Options"):
        read_result = read_results.get(bot_name)
        summary = health_results.get(bot_name)
        if read_result is None or not read_result.exists:
            reasons.append(f"{bot_name} snapshot missing")
            continue
        if not read_result.valid or read_result.snapshot is None:
            reasons.append(f"{bot_name} snapshot invalid")
            continue
        if summary is None or summary.health_status != "HEALTHY":
            status = "UNKNOWN" if summary is None else summary.health_status
            reasons.append(f"{bot_name} snapshot health not real/fresh enough: {status}")
        if summary is not None:
            for warning in summary.warnings:
                if _input_warning_is_untrusted(warning):
                    reasons.append(f"{bot_name} input warning: {warning}")

    realness_reasons = tuple(dict.fromkeys(reasons))
    envelope_warnings = tuple(dict.fromkeys(warnings + list(realness_reasons)))
    return {
        "producer_id": PRODUCER_ID,
        "schema_version": RESULT_SCHEMA_VERSION,
        "produced_at": produced_at.isoformat(),
        "fresh_until": fresh_until.isoformat(),
        "data_is_real": not realness_reasons,
        "data_is_real_reasons": list(realness_reasons),
        "input_warnings": list(envelope_warnings),
    }


def _input_warning_is_untrusted(warning: str) -> bool:
    lowered = warning.lower()
    markers = (
        "missing",
        "unreadable",
        "empty",
        "invalid",
        "corrupt",
        "stale",
        "unknown",
        "timestamp",
        "unverified",
        "contradiction",
        "reports errors",
    )
    return any(marker in lowered for marker in markers)


def _coerce_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
