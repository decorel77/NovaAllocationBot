"""Allocation v2 design layer (QA-015).

DESIGN-ONLY / ADVISORY-ONLY. Nothing in this module is wired into the
production allocation cycle: ``workflow/allocation_cycle.py``, the published
``allocation_result.v2`` snapshot, and the REPAIR-007 authoritative allocation
are untouched (a test freezes this). The module exists so that the future
MarketRegimeBot ``regime_result.v3`` schema (the QA-012/QA-013 promotion path:
``model_version`` + hysteresis raw-vs-published state) can be consumed safely
the day it is promoted, without designing the consumer under time pressure.

Fail-closed rules, in order of authority:

  1. A payload that is not exactly a well-formed ``regime_result.v3`` envelope
     (missing fields, wrong schema, wrong producer, invalid types) is never
     usable; the proposal stays at the caller's baseline.
  2. ``data_is_real`` must be exactly ``True`` and the freshness window must
     be open; stale, future-dated, or unverified regimes are refused.
  3. An unknown ``model_version`` is refused outright. A known-but-research
     model (currently ``v2``) parses fine but does not steer the proposal
     unless the caller explicitly widens ``trusted_model_versions``.
  4. ``raw_regime`` vs published ``market_regime`` disagreement is resolved by
     adopting the MORE CONSERVATIVE regime (the one with the lower risky cap).
  5. No degraded input may ever increase the risky share of the proposal above
     the caller's baseline; refusal always returns the baseline unchanged.

Pure module: no IO, no network, no broker access, deterministic. Allocation
tables and timestamp parsing are reused from production by import (never
copied) so the design layer cannot drift from production math.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from config.allocation_config import REGIME_MIN_CONFIDENCE, REGIME_STALE_AFTER_HOURS
from core.authoritative_allocation import _to_canonical_scheme
from core.market_regime_adapter import _parse_timestamp
from core.regime_allocation_engine import REGIME_ALLOCATIONS

DESIGN_SCHEMA_VERSION = "allocation_proposal.v2_design"
SUPPORTED_REGIME_SCHEMA = "regime_result.v3"
EXPECTED_PRODUCER_ID = "MarketRegimeBot"

# Model versions this design layer recognises at all. Anything else fails
# closed: a silent model swap upstream must never steer an allocation.
TRUSTED_MODEL_VERSIONS = frozenset({"v1"})
RESEARCH_MODEL_VERSIONS = frozenset({"v2"})
KNOWN_MODEL_VERSIONS = TRUSTED_MODEL_VERSIONS | RESEARCH_MODEL_VERSIONS

# The four regimes the allocator maps. UNKNOWN (or any other label) is not an
# allocatable regime here: it fails closed to the baseline.
ALLOCATION_REGIMES = frozenset(REGIME_ALLOCATIONS)

# Production allocation table, reused by import so v2 cannot drift from v1.
V2_REGIME_ALLOCATIONS = REGIME_ALLOCATIONS

# Conservative cap on the risky share (everything except Cash) per regime.
# Derived from, and asserted against, the production table: a regime's own
# allocation always satisfies its cap, and disagreement resolution picks the
# regime with the LOWER cap.
MAX_RISKY_PCT_BY_REGIME = {
    regime: sum(pct for bucket, pct in allocation.items() if bucket != "Cash")
    for regime, allocation in REGIME_ALLOCATIONS.items()
}

REQUIRED_V3_FIELDS = (
    "schema_version",
    "producer_id",
    "model_version",
    "market_regime",
    "confidence",
    "raw_regime",
    "raw_confidence",
    "produced_at",
    "fresh_until",
    "data_is_real",
)


class AllocationV2DesignError(ValueError):
    """Raised when a v2 design proposal violates its own safety invariants."""


def risky_pct(allocation: Mapping[str, Any]) -> int:
    """Risky share of a canonical allocation: everything that is not Cash."""
    return sum(int(pct) for bucket, pct in allocation.items() if bucket != "Cash")


@dataclass(frozen=True)
class RegimeInputV3:
    """Validated, fail-closed view of a future ``regime_result.v3`` payload.

    ``usable`` is True only when every gate passed. A non-usable input still
    carries whatever fields could be read, for diagnostics only.
    """

    usable: bool
    refusal_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    schema_version: str | None = None
    producer_id: str | None = None
    model_version: str | None = None
    published_regime: str = "UNKNOWN"
    published_confidence: int = 0
    raw_regime: str = "UNKNOWN"
    raw_confidence: int = 0
    produced_at: str | None = None
    fresh_until: str | None = None
    data_is_real: bool = False
    input_source: str = "unknown"


def parse_regime_input_v3(
    payload: Any,
    now: datetime | None = None,
) -> RegimeInputV3:
    """Parse a candidate ``regime_result.v3`` payload, collecting ALL refusals.

    Every gate failure is recorded (not just the first) so a refused input is
    fully diagnosable. ``usable`` is True only with zero refusals.
    """
    now = now or datetime.now(timezone.utc)
    if not isinstance(payload, Mapping):
        return RegimeInputV3(
            usable=False,
            refusal_reasons=("payload_not_object",),
        )

    refusals: list[str] = []
    warnings: list[str] = []

    for field_name in REQUIRED_V3_FIELDS:
        if field_name not in payload:
            refusals.append(f"missing_field:{field_name}")

    schema_version = _opt_str(payload.get("schema_version"))
    if "schema_version" not in [r.split(":", 1)[-1] for r in refusals]:
        if schema_version != SUPPORTED_REGIME_SCHEMA:
            refusals.append(f"unsupported_schema:{schema_version!r}")

    producer_id = _opt_str(payload.get("producer_id"))
    if "producer_id" in payload and producer_id != EXPECTED_PRODUCER_ID:
        refusals.append(f"unexpected_producer:{producer_id!r}")

    model_version = _opt_str(payload.get("model_version"))
    if "model_version" in payload and model_version not in KNOWN_MODEL_VERSIONS:
        refusals.append(f"model_version_unknown:{model_version!r}")
    if model_version in RESEARCH_MODEL_VERSIONS:
        warnings.append("model_research_stage")

    published_regime = _regime_label(payload.get("market_regime"))
    if "market_regime" in payload and published_regime not in ALLOCATION_REGIMES:
        refusals.append(f"published_regime_invalid:{published_regime!r}")

    raw_regime = _regime_label(payload.get("raw_regime"))
    if "raw_regime" in payload and raw_regime not in ALLOCATION_REGIMES:
        refusals.append(f"raw_regime_invalid:{raw_regime!r}")

    published_confidence = _strict_confidence(payload.get("confidence"))
    if "confidence" in payload and published_confidence is None:
        refusals.append("confidence_invalid")
    raw_confidence = _strict_confidence(payload.get("raw_confidence"))
    if "raw_confidence" in payload and raw_confidence is None:
        refusals.append("raw_confidence_invalid")

    if payload.get("data_is_real") is not True:
        refusals.append("regime_not_real")

    produced_at = _opt_str(payload.get("produced_at"))
    fresh_until = _opt_str(payload.get("fresh_until"))
    refusals.extend(_freshness_refusals(produced_at, fresh_until, now))

    if (
        published_confidence is not None
        and published_confidence < REGIME_MIN_CONFIDENCE
    ):
        refusals.append(
            f"regime_low_confidence:{published_confidence}<{REGIME_MIN_CONFIDENCE}"
        )

    if (
        published_regime in ALLOCATION_REGIMES
        and raw_regime in ALLOCATION_REGIMES
        and published_regime != raw_regime
    ):
        warnings.append("raw_published_disagreement")

    source = _opt_str(payload.get("input_source"))
    return RegimeInputV3(
        usable=not refusals,
        refusal_reasons=tuple(dict.fromkeys(refusals)),
        warnings=tuple(dict.fromkeys(warnings)),
        schema_version=schema_version,
        producer_id=producer_id,
        model_version=model_version,
        published_regime=published_regime if published_regime else "UNKNOWN",
        published_confidence=published_confidence or 0,
        raw_regime=raw_regime if raw_regime else "UNKNOWN",
        raw_confidence=raw_confidence or 0,
        produced_at=produced_at,
        fresh_until=fresh_until,
        data_is_real=payload.get("data_is_real") is True,
        input_source=source or "unknown",
    )


@dataclass(frozen=True)
class AllocationV2Proposal:
    """Advisory allocation proposal. Never executed, never exported."""

    proposed_allocation: dict[str, int]
    baseline_allocation: dict[str, int]
    source: str
    reason: str
    effective_regime: str | None = None
    model_version: str | None = None
    regime_confidence: int = 0
    refusal_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    schema_version: str = DESIGN_SCHEMA_VERSION
    design_only: bool = True
    recommendation_only: bool = True
    dry_run: bool = True
    broker_execution_enabled: bool = False
    order_placement_enabled: bool = False
    money_movement_enabled: bool = False
    live_trading_enabled: bool = False
    allocation_export_enabled: bool = False
    downstream_export_enabled: bool = False
    writes_to_other_projects_enabled: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not (self.design_only and self.recommendation_only and self.dry_run):
            raise AllocationV2DesignError(
                "v2 proposal must remain design-only, advisory, dry-run."
            )
        for flag in (
            self.broker_execution_enabled,
            self.order_placement_enabled,
            self.money_movement_enabled,
            self.live_trading_enabled,
            self.allocation_export_enabled,
            self.downstream_export_enabled,
            self.writes_to_other_projects_enabled,
        ):
            if flag:
                raise AllocationV2DesignError("Unsafe flag enabled on v2 proposal.")
        for name, allocation in (
            ("proposed", self.proposed_allocation),
            ("baseline", self.baseline_allocation),
        ):
            if any(int(pct) < 0 for pct in allocation.values()):
                raise AllocationV2DesignError(f"Negative bucket in {name} allocation.")
            if sum(int(pct) for pct in allocation.values()) != 100:
                raise AllocationV2DesignError(f"{name} allocation must total 100.")
        if self.source == "regime_aware_v2_design":
            cap = MAX_RISKY_PCT_BY_REGIME.get(self.effective_regime or "")
            if cap is None:
                raise AllocationV2DesignError(
                    f"Steered proposal has no cap for regime {self.effective_regime!r}."
                )
            if risky_pct(self.proposed_allocation) > cap:
                raise AllocationV2DesignError(
                    f"Risky share exceeds {self.effective_regime} cap of {cap}."
                )
        else:
            # Any refused/untrusted path must hand back the baseline verbatim:
            # degraded input may never move the allocation, in either direction.
            if self.proposed_allocation != self.baseline_allocation:
                raise AllocationV2DesignError(
                    "Non-steered proposal must equal the baseline allocation."
                )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "design_only": self.design_only,
            "recommendation_only": self.recommendation_only,
            "dry_run": self.dry_run,
            "proposed_allocation": dict(self.proposed_allocation),
            "baseline_allocation": dict(self.baseline_allocation),
            "source": self.source,
            "reason": self.reason,
            "effective_regime": self.effective_regime,
            "model_version": self.model_version,
            "regime_confidence": self.regime_confidence,
            "refusal_reasons": list(self.refusal_reasons),
            "warnings": list(self.warnings),
            "broker_execution_enabled": self.broker_execution_enabled,
            "order_placement_enabled": self.order_placement_enabled,
            "money_movement_enabled": self.money_movement_enabled,
            "live_trading_enabled": self.live_trading_enabled,
            "allocation_export_enabled": self.allocation_export_enabled,
            "downstream_export_enabled": self.downstream_export_enabled,
            "writes_to_other_projects_enabled": self.writes_to_other_projects_enabled,
            "diagnostics": dict(self.diagnostics),
        }


def propose_allocation_v2(
    regime_input: RegimeInputV3,
    baseline_allocation: Mapping[str, Any],
    *,
    trusted_model_versions: frozenset[str] | set[str] = TRUSTED_MODEL_VERSIONS,
) -> AllocationV2Proposal:
    """Build the advisory v2 proposal from a parsed v3 regime input.

    ``baseline_allocation`` is what production would do anyway (typically the
    REPAIR-007 authoritative allocation). Every refusal path returns it
    unchanged, so this layer can only ever match production or be MORE
    conservative — never riskier on degraded input.
    """
    baseline = _to_canonical_scheme(dict(baseline_allocation))
    if sum(baseline.values()) != 100:
        raise AllocationV2DesignError("Baseline allocation must total 100.")

    if not regime_input.usable:
        proposal = AllocationV2Proposal(
            proposed_allocation=dict(baseline),
            baseline_allocation=dict(baseline),
            source="baseline_fail_closed",
            reason=(
                "Regime v3 input REFUSED ("
                + "; ".join(regime_input.refusal_reasons)
                + "). Holding baseline allocation."
            ),
            model_version=regime_input.model_version,
            regime_confidence=regime_input.published_confidence,
            refusal_reasons=regime_input.refusal_reasons,
            warnings=regime_input.warnings,
        )
        proposal.validate()
        return proposal

    if regime_input.model_version not in trusted_model_versions:
        proposal = AllocationV2Proposal(
            proposed_allocation=dict(baseline),
            baseline_allocation=dict(baseline),
            source="baseline_model_not_trusted",
            reason=(
                f"Regime model {regime_input.model_version!r} is known but not "
                "production-trusted (research-stage). Holding baseline "
                "allocation; diagnostics carry what it would have proposed."
            ),
            model_version=regime_input.model_version,
            regime_confidence=regime_input.published_confidence,
            warnings=regime_input.warnings,
            diagnostics={
                "untrusted_model_would_propose": dict(
                    V2_REGIME_ALLOCATIONS[regime_input.published_regime]
                ),
                "published_regime": regime_input.published_regime,
            },
        )
        proposal.validate()
        return proposal

    effective_regime = regime_input.published_regime
    warnings = list(regime_input.warnings)
    if regime_input.raw_regime != regime_input.published_regime:
        # Hysteresis disagreement: adopt whichever regime carries the lower
        # risky cap. Smoothing may delay risk-off, never risk-on.
        raw_cap = MAX_RISKY_PCT_BY_REGIME[regime_input.raw_regime]
        published_cap = MAX_RISKY_PCT_BY_REGIME[regime_input.published_regime]
        if raw_cap < published_cap:
            effective_regime = regime_input.raw_regime
        if "raw_published_disagreement" not in warnings:
            warnings.append("raw_published_disagreement")

    proposed = dict(V2_REGIME_ALLOCATIONS[effective_regime])
    proposal = AllocationV2Proposal(
        proposed_allocation=proposed,
        baseline_allocation=dict(baseline),
        source="regime_aware_v2_design",
        reason=(
            f"Advisory v2 proposal for regime '{effective_regime}' "
            f"(model {regime_input.model_version}, confidence "
            f"{regime_input.published_confidence}, raw '{regime_input.raw_regime}' "
            f"vs published '{regime_input.published_regime}')."
        ),
        effective_regime=effective_regime,
        model_version=regime_input.model_version,
        regime_confidence=regime_input.published_confidence,
        warnings=tuple(warnings),
    )
    proposal.validate()
    return proposal


def _opt_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _regime_label(value: Any) -> str:
    text = _opt_str(value)
    return text.upper() if text is not None else "UNKNOWN"


def _strict_confidence(value: Any) -> int | None:
    # bool is an int subclass; type() comparison rejects it, matching the
    # MarketRegimeBot hysteresis filter's strictness.
    if type(value) is not int or not 0 <= value <= 100:
        return None
    return value


def _freshness_refusals(
    produced_at_raw: str | None,
    fresh_until_raw: str | None,
    now: datetime,
) -> list[str]:
    if produced_at_raw is None or fresh_until_raw is None:
        return ["regime_timestamp_missing"]
    produced_at = _parse_timestamp(produced_at_raw)
    fresh_until = _parse_timestamp(fresh_until_raw)
    if produced_at is None or fresh_until is None:
        return ["regime_timestamp_unparseable"]
    refusals: list[str] = []
    if produced_at > now:
        refusals.append("regime_timestamp_future")
    elif now - produced_at > timedelta(hours=REGIME_STALE_AFTER_HOURS):
        refusals.append("regime_stale")
    if fresh_until < now and "regime_stale" not in refusals:
        refusals.append("regime_stale")
    return refusals
