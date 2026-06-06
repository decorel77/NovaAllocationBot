"""Safe dry-run allocation workflow.

The cycle reads upstream bot result snapshots read-only, validates the fixed
Phase 2 target allocation, builds a Phase 2.5 recommendation-only allocation,
and writes only this project's local result snapshot.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.allocation_config import (
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
from core.health_evaluator import evaluate_all_snapshot_health
from core.recommendation_engine import generate_allocation_recommendation
from core.snapshot_reader import read_configured_snapshots

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "system" / "result_snapshot.json"


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
    bot_health = {
        bot_name: {
            "score": summary.health_score,
            "status": summary.health_status,
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
    result_path: Path = RESULT_SNAPSHOT_PATH,
) -> Path:
    resolved_path = result_path.resolve()
    project_root = PROJECT_ROOT.resolve()
    if project_root not in resolved_path.parents and resolved_path != project_root:
        raise ValueError("Refusing to write outside NovaAllocationBot project root.")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(decision.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result_path


def run_allocation_cycle(
    write_snapshot: bool = True,
    snapshot_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    decision = build_dry_run_decision(snapshot_paths=snapshot_paths)
    output_path = None
    if write_snapshot:
        output_path = str(write_result_snapshot(decision))
    return {
        "status": decision.status,
        "dry_run": decision.dry_run,
        "health_evaluated": decision.health_evaluated,
        "result_snapshot_path": output_path,
        "decision": decision.to_dict(),
    }
