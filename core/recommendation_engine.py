"""Recommendation-only allocation guidance from bot health summaries."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from config.allocation_config import DEFAULT_ALLOCATION_PERCENTAGES

CURRENT_ALLOCATION = {
    bot_name: int(percentage)
    for bot_name, percentage in DEFAULT_ALLOCATION_PERCENTAGES.items()
}
BASELINE_STOCK_PCT = CURRENT_ALLOCATION["NovaBotV2"]
BASELINE_OPTIONS_PCT = CURRENT_ALLOCATION["NovaBotV2Options"]


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

    # Rule table for active-bot health recommendations:
    # - Any UNKNOWN active-bot input: hold configured baseline. Missing data must
    #   never increase another risky bucket above baseline.
    # - HEALTHY / HEALTHY: hold configured baseline.
    # - Clear non-UNKNOWN imbalance: tilt only between known active-bot inputs.
    # - Warnings do not change allocation; they add advisory context only.
    if stock["status"] == "UNKNOWN" or options["status"] == "UNKNOWN":
        recommended = _baseline_allocation()
        reasons.append("insufficient data - holding baseline allocation")
    elif stock["status"] == "HEALTHY" and options["status"] == "HEALTHY":
        recommended = _baseline_allocation()
        reasons.append(
            "Both active bots are healthy; keep current baseline allocation"
        )
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
        recommended = _baseline_allocation()
        reasons.append(
            "Active bot health scores are balanced; keep current baseline allocation"
        )

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


def _baseline_allocation() -> dict[str, int]:
    return dict(CURRENT_ALLOCATION)


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
