"""Recommendation-only allocation guidance from bot health summaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

CURRENT_ALLOCATION = {
    "NovaBotV2": 90,
    "NovaBotV2Options": 10,
    "NovaCryptoBot": 0,
    "CashReserve": 0,
}


@dataclass(frozen=True)
class AllocationRecommendation:
    current_allocation: dict[str, int]
    recommended_allocation: dict[str, int]
    recommendation_reason: tuple[str, ...]
    recommendation_only: bool = True
    downstream_export_enabled: bool = False

    def validate(self) -> None:
        if sum(self.recommended_allocation.values()) != 100:
            raise ValueError("Recommended allocation must total 100%.")
        if not self.recommendation_only:
            raise ValueError("Recommendation must remain advisory only.")
        if self.downstream_export_enabled:
            raise ValueError("Downstream export must remain disabled.")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


def generate_allocation_recommendation(
    bot_health: dict[str, dict[str, Any]],
    warnings: tuple[str, ...] | list[str] = (),
) -> AllocationRecommendation:
    stock = _health_entry(bot_health, "NovaBotV2")
    options = _health_entry(bot_health, "NovaBotV2Options")
    reasons: list[str] = []

    if options["status"] == "UNKNOWN":
        recommended = _with_fixed_future_allocations(100, 0)
        reasons.append("NovaBotV2Options health status unknown; recommend zero options allocation")
    elif stock["status"] == "UNKNOWN":
        recommended = _with_fixed_future_allocations(80, 20)
        reasons.append("NovaBotV2 health status unknown; keep options capped at 20%")
    elif stock["status"] == "HEALTHY" and options["status"] == "HEALTHY":
        recommended = _with_fixed_future_allocations(90, 10)
        reasons.append("Both active bots are healthy; keep current 90/10 allocation")
    elif stock["score"] >= 80 and options["score"] < 60:
        recommended = _with_fixed_future_allocations(95, 5)
        reasons.append("NovaBotV2 health score higher than NovaBotV2Options")
    elif stock["score"] < 60 and options["score"] >= 80:
        recommended = _with_fixed_future_allocations(80, 20)
        reasons.append("NovaBotV2Options health score higher than NovaBotV2")
    elif stock["score"] > options["score"]:
        recommended = _with_fixed_future_allocations(95, 5)
        reasons.append("NovaBotV2 health score higher than NovaBotV2Options")
    elif options["score"] > stock["score"]:
        recommended = _with_fixed_future_allocations(80, 20)
        reasons.append("NovaBotV2Options health score higher than NovaBotV2")
    else:
        recommended = _with_fixed_future_allocations(90, 10)
        reasons.append("Active bot health scores are balanced; keep current 90/10 allocation")

    if warnings:
        reasons.append("Snapshot warnings are present; recommendation remains advisory only")

    recommendation = AllocationRecommendation(
        current_allocation=dict(CURRENT_ALLOCATION),
        recommended_allocation=recommended,
        recommendation_reason=tuple(reasons),
    )
    recommendation.validate()
    return recommendation


def _health_entry(bot_health: dict[str, dict[str, Any]], bot_name: str) -> dict[str, Any]:
    entry = bot_health.get(bot_name, {})
    return {
        "score": int(entry.get("score", 0)),
        "status": str(entry.get("status", "UNKNOWN")).upper(),
    }


def _with_fixed_future_allocations(stock_pct: int, options_pct: int) -> dict[str, int]:
    allocation = {
        "NovaBotV2": stock_pct,
        "NovaBotV2Options": options_pct,
        "NovaCryptoBot": 0,
        "CashReserve": 0,
    }
    if sum(allocation.values()) != 100:
        raise ValueError("Recommendation rules produced a non-100% total.")
    return allocation
