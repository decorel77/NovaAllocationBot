"""Regime-based allocation engine for NovaAllocationBot Phase 3.

Maps market regime from MarketRegimeBot to recommended allocation percentages.
Read-only and dry-run. No broker, order, or trading logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config.allocation_config import ALLOCATION_CONTRACT_VERSION
from core.market_regime_adapter import RegimeReadResult

REGIME_ALLOCATIONS: dict[str, dict[str, int]] = {
    "BULL": {"NovaBotV2": 90, "NovaBotV2Options": 10, "Cash": 0},
    "SIDEWAYS": {"NovaBotV2": 80, "NovaBotV2Options": 10, "Cash": 10},
    "BEAR": {"NovaBotV2": 70, "NovaBotV2Options": 5, "Cash": 25},
    "HIGH_VOLATILITY": {"NovaBotV2": 50, "NovaBotV2Options": 0, "Cash": 50},
}

FALLBACK_ALLOCATION: dict[str, int] = {"NovaBotV2": 90, "NovaBotV2Options": 10, "Cash": 0}


@dataclass(frozen=True)
class RegimeAllocationResult:
    project: str = "NovaAllocationBot"
    status: str = "SAFE_DRY_RUN_ALLOCATION"
    input_source: str = "fallback"
    market_regime: str = "UNKNOWN"
    confidence: int = 0
    recommended_allocation: dict[str, int] = field(default_factory=dict)
    reason: str = ""
    dry_run: bool = True
    broker_execution_enabled: bool = False
    order_placement_enabled: bool = False
    money_movement_enabled: bool = False
    live_trading_enabled: bool = False
    allocation_export_enabled: bool = False
    writes_to_other_projects_enabled: bool = False
    warnings: tuple[str, ...] = ()
    allocation_version: str = ALLOCATION_CONTRACT_VERSION

    def validate(self) -> None:
        assert self.dry_run, "Must remain dry-run"
        assert not self.broker_execution_enabled
        assert not self.order_placement_enabled
        assert not self.money_movement_enabled
        assert not self.live_trading_enabled
        assert not self.allocation_export_enabled
        assert not self.writes_to_other_projects_enabled
        total = sum(self.recommended_allocation.values())
        assert total == 100, f"Allocation must total 100%, got {total}"

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "project": self.project,
            "status": self.status,
            "input_source": self.input_source,
            "market_regime": self.market_regime,
            "confidence": self.confidence,
            "recommended_allocation": dict(self.recommended_allocation),
            "reason": self.reason,
            "dry_run": self.dry_run,
            "broker_execution_enabled": self.broker_execution_enabled,
            "order_placement_enabled": self.order_placement_enabled,
            "money_movement_enabled": self.money_movement_enabled,
            "live_trading_enabled": self.live_trading_enabled,
            "allocation_export_enabled": self.allocation_export_enabled,
            "writes_to_other_projects_enabled": self.writes_to_other_projects_enabled,
            "warnings": list(self.warnings),
            "allocation_version": self.allocation_version,
        }


def build_regime_allocation(regime_result: RegimeReadResult) -> RegimeAllocationResult:
    if regime_result.is_fallback or regime_result.market_regime not in REGIME_ALLOCATIONS:
        allocation = dict(FALLBACK_ALLOCATION)
        reason = regime_result.reason or "Fallback: regime unavailable"
        if not reason.lower().startswith("fallback"):
            reason = f"Fallback: {reason}"
    else:
        allocation = dict(REGIME_ALLOCATIONS[regime_result.market_regime])
        reason = regime_result.reason

    return RegimeAllocationResult(
        input_source=regime_result.input_source,
        market_regime=regime_result.market_regime,
        confidence=regime_result.confidence,
        recommended_allocation=allocation,
        reason=reason,
        warnings=regime_result.warnings,
    )
