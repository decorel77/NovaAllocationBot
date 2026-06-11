"""Single authoritative allocation for NovaAllocationBot (REPAIR-007).

The result_snapshot historically surfaced THREE different allocations (the static
plan, the health-based recommendation, and the regime-based allocation) with no
indication of which one a consumer should act on, and the regime block embedded a
regime that could disagree with the producer. This module collapses those inputs
into exactly ONE authoritative allocation and records the others as diagnostics.

Regime influence is only applied when the upstream MarketRegimeBot snapshot is
verified real (REPAIR-005 ``data_is_real`` contract, via
``RegimeReadResult.regime_is_real``) and meets the configured confidence
threshold. When the regime is fixture/unverified/stale, unavailable, or too low
confidence, the regime is REFUSED and the authoritative allocation falls back to
the health-based recommendation, with the refusal reason recorded.

ADVISORY_ONLY. Read-only. No broker, orders, money movement, or downstream export.
"""
from __future__ import annotations

from typing import Any

from config.allocation_config import ALLOCATION_CONTRACT_VERSION, REGIME_MIN_CONFIDENCE
from core.market_regime_adapter import RegimeReadResult

# The authoritative allocation is always expressed in this canonical 3-bucket
# scheme so a consumer never has to reconcile differing bucket names.
CANONICAL_BUCKETS = ("NovaBotV2", "NovaBotV2Options", "Cash")

_SAFETY_FLAGS = {
    "dry_run": True,
    "broker_execution_enabled": False,
    "order_placement_enabled": False,
    "money_movement_enabled": False,
    "live_trading_enabled": False,
    "allocation_export_enabled": False,
    "writes_to_other_projects_enabled": False,
}


def _to_canonical_scheme(allocation: dict[str, Any]) -> dict[str, int]:
    """Map any allocation onto {NovaBotV2, NovaBotV2Options, Cash} summing to 100.

    Cash absorbs CashReserve and any unsupported bucket (e.g. NovaCryptoBot) so
    the result always totals 100 without inventing exposure.
    """
    def _num(v: Any) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    nbv2 = _num(allocation.get("NovaBotV2"))
    nopt = _num(allocation.get("NovaBotV2Options"))
    cash = _num(allocation.get("Cash")) + _num(allocation.get("CashReserve"))
    # Fold any remaining buckets (unsupported) into Cash so the total stays 100.
    accounted = {"NovaBotV2", "NovaBotV2Options", "Cash", "CashReserve"}
    leftover = sum(_num(v) for k, v in allocation.items() if k not in accounted)
    cash += leftover
    result = {"NovaBotV2": int(round(nbv2)), "NovaBotV2Options": int(round(nopt)), "Cash": int(round(cash))}
    # Correct any rounding drift onto Cash so the canonical allocation totals 100.
    drift = 100 - sum(result.values())
    if drift:
        result["Cash"] += drift
    return result


def build_authoritative_allocation(
    *,
    recommendation: dict[str, Any],
    regime_result: RegimeReadResult,
    regime_allocation: dict[str, int],
) -> dict[str, Any]:
    """Return the single authoritative allocation + provenance.

    - regime verified real and confident -> authoritative = regime-aware allocation
    - regime unverified/stale/missing/low-confidence -> REFUSED, health-based
      recommendation, refusal reason recorded.
    """
    health_alloc = _to_canonical_scheme(dict(recommendation.get("recommended_allocation") or {}))
    warnings = list(regime_result.warnings)
    confidence_is_usable = regime_result.confidence >= REGIME_MIN_CONFIDENCE

    if regime_result.regime_is_real and confidence_is_usable:
        allocation = _to_canonical_scheme(dict(regime_allocation))
        source = "regime_aware"
        refused_regime_reason = None
        reason = (
            f"Regime-aware allocation for verified-real regime "
            f"'{regime_result.market_regime}' (confidence {regime_result.confidence}, "
            f"threshold {REGIME_MIN_CONFIDENCE}, data_is_real=true)."
        )
    else:
        allocation = health_alloc
        source = "health_based_regime_refused"
        if regime_result.regime_is_real:
            if "regime_low_confidence" not in warnings:
                warnings.append("regime_low_confidence")
            refused_regime_reason = (
                f"Regime '{regime_result.market_regime}' REFUSED: regime_low_confidence "
                f"(confidence {regime_result.confidence} < threshold "
                f"{REGIME_MIN_CONFIDENCE}). Falling back to health-based recommendation."
            )
            reason = "Health-based recommendation (regime confidence below threshold)."
        else:
            refused_regime_reason = (
                f"Regime '{regime_result.market_regime}' REFUSED: not verified real "
                f"({regime_result.reason}). Falling back to health-based recommendation."
            )
            reason = "Health-based recommendation (regime input was not verified real)."

    return {
        "allocation": allocation,
        "source": source,
        "regime": regime_result.market_regime,
        "regime_is_real": regime_result.regime_is_real,
        "regime_confidence": regime_result.confidence,
        "regime_min_confidence": REGIME_MIN_CONFIDENCE,
        "regime_warnings": warnings,
        "reason": reason,
        "refused_regime_reason": refused_regime_reason,
        "recommendation_only": True,
        "downstream_export_enabled": False,
        "allocation_version": ALLOCATION_CONTRACT_VERSION,
        "diagnostics_note": (
            "This is the single authoritative allocation. The 'plan', "
            "'recommendation', and 'regime_allocation' blocks are diagnostic inputs, "
            "not the decision."
        ),
        **_SAFETY_FLAGS,
    }
