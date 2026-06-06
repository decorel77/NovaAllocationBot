"""Safe dry-run allocation workflow.

Phase 2: reads upstream bot snapshots, validates fixed allocation, builds
recommendation-only allocation.
Phase 3: reads MarketRegimeBot regime snapshot and produces regime-based
allocation output. All operations remain read-only and dry-run.
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
from core.allocation_history import append_allocation_history
from core.health_evaluator import evaluate_all_snapshot_health
from core.market_regime_adapter import read_market_regime_snapshot
from core.recommendation_engine import generate_allocation_recommendation
from core.regime_allocation_engine import build_regime_allocation
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
    regime_allocation_dict: dict[str, Any] | None = None,
) -> Path:
    resolved_path = result_path.resolve()
    project_root = PROJECT_ROOT.resolve()
    if project_root not in resolved_path.parents and resolved_path != project_root:
        raise ValueError("Refusing to write outside NovaAllocationBot project root.")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    payload = decision.to_dict()
    if regime_allocation_dict is not None:
        payload["regime_allocation"] = regime_allocation_dict
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
) -> dict[str, Any]:
    decision = build_dry_run_decision(snapshot_paths=snapshot_paths)
    regime_result = read_market_regime_snapshot(regime_snapshot_path)
    regime_allocation = build_regime_allocation(regime_result)
    regime_allocation_dict = regime_allocation.to_dict()
    output_path = None
    if write_snapshot:
        output_path = str(write_result_snapshot(decision, regime_allocation_dict=regime_allocation_dict))
        append_allocation_history(
            regime=regime_allocation.market_regime,
            confidence=regime_allocation.confidence,
            allocation=dict(regime_allocation.recommended_allocation),
            input_source=regime_allocation.input_source,
            reason=regime_allocation.reason,
            history_path=history_path,
        )
    return {
        "status": decision.status,
        "dry_run": decision.dry_run,
        "health_evaluated": decision.health_evaluated,
        "result_snapshot_path": output_path,
        "decision": decision.to_dict(),
        "regime_allocation": regime_allocation_dict,
    }
