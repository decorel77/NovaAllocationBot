"""Typed allocation contracts for NovaAllocationBot.

These models are intentionally local and dry-run friendly. They do not import
broker, order, or trading modules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from config.allocation_config import KNOWN_BOTS


class AllocationValidationError(ValueError):
    """Raised when an allocation contract violates safety rules."""


@dataclass(frozen=True)
class BotAllocationTarget:
    bot_name: str
    target_percentage: float
    future_supported: bool = False
    notes: str = ""

    def validate(self) -> None:
        if self.bot_name not in KNOWN_BOTS and not self.future_supported:
            raise AllocationValidationError(
                f"Unknown bot '{self.bot_name}' must be marked future_supported."
            )
        if self.target_percentage < 0:
            raise AllocationValidationError(
                f"Negative allocation rejected for '{self.bot_name}'."
            )
        if self.target_percentage > 100:
            raise AllocationValidationError(
                f"Allocation over 100% rejected for '{self.bot_name}'."
            )


@dataclass(frozen=True)
class AllocationRiskState:
    dry_run: bool = True
    broker_execution_enabled: bool = False
    order_placement_enabled: bool = False
    money_movement_enabled: bool = False
    writes_to_other_projects_enabled: bool = False
    downstream_export_enabled: bool = False
    status: str = "SAFE_DRY_RUN"
    notes: tuple[str, ...] = (
        "No broker execution.",
        "No order placement.",
        "No money movement.",
        "No writes to other bot repositories.",
        "No downstream allocation export.",
    )

    def validate(self) -> None:
        if not self.dry_run:
            raise AllocationValidationError("Allocation cycle must remain dry-run.")
        unsafe_flags = {
            "broker_execution_enabled": self.broker_execution_enabled,
            "order_placement_enabled": self.order_placement_enabled,
            "money_movement_enabled": self.money_movement_enabled,
            "writes_to_other_projects_enabled": self.writes_to_other_projects_enabled,
            "downstream_export_enabled": self.downstream_export_enabled,
        }
        enabled = [name for name, value in unsafe_flags.items() if value]
        if enabled:
            raise AllocationValidationError(
                "Unsafe allocation risk flags enabled: " + ", ".join(enabled)
            )


@dataclass(frozen=True)
class AllocationInputSnapshot:
    source: str = "read_only_project_snapshots"
    available_capital_label: str = "MOCK_CAPITAL_ONLY"
    generated_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    bot_health: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class AllocationPlan:
    targets: tuple[BotAllocationTarget, ...]
    cash_reserve_minimum_percentage: float = 0.0

    def validate(self) -> None:
        if self.cash_reserve_minimum_percentage < 0:
            raise AllocationValidationError("Cash reserve minimum cannot be negative.")
        for target in self.targets:
            target.validate()
        total = self.total_percentage()
        if round(total, 6) != 100.0:
            raise AllocationValidationError(
                f"Allocation total must equal 100%, got {total:.6f}%."
            )
        cash_target = next(
            (
                target.target_percentage
                for target in self.targets
                if target.bot_name == "CashReserve"
            ),
            0.0,
        )
        if cash_target < self.cash_reserve_minimum_percentage:
            raise AllocationValidationError(
                "CashReserve allocation is below configured minimum."
            )

    def total_percentage(self) -> float:
        return sum(target.target_percentage for target in self.targets)


@dataclass(frozen=True)
class AllocationDecision:
    status: str
    plan: AllocationPlan
    risk_state: AllocationRiskState
    input_snapshot: AllocationInputSnapshot
    bot_health: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    recommendation: dict[str, Any] = field(default_factory=dict)
    health_evaluated: bool = False
    dry_run: bool = True
    message: str = "Dry-run allocation decision generated."

    def validate(self) -> None:
        self.risk_state.validate()
        self.plan.validate()
        if not self.dry_run:
            raise AllocationValidationError("Allocation decision must be dry-run.")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)
