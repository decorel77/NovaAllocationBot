"""Pure, broker-free advisory quality scorer (recommendation / reporting only).

Task: ALLOC-003D (gated on ALLOC-003A/B/C, all DONE). A deterministic,
stdlib-only implementation of the advisory quality-metrics contract
(``docs/contracts/advisory_quality_metrics_contract.md``). It turns one synthetic
signal-outcome record into per-outcome quality metrics, and a stream of synthetic
recommendation snapshots into a turnover warning — **failing closed** to
``UNKNOWN`` / withheld values when an input is missing or stale. It is advisory /
reporting only: it sizes nothing, moves no money, and changes no allocation.

Inputs (synthetic, caller-supplied)
-----------------------------------
A signal-outcome record shaped like the ALLOC-003A/B fixtures
(``advisory_quality_examples.json`` / ``advisory_quality_cases.json``). The
003A records carry the minimal fields; the 003B records add ``confidence`` /
``predicted_good`` / ``realized_good`` / ``signal_regime`` / ``evaluation_regime``
/ ``regime_mismatch``. Missing optional fields degrade the dependent metric to
``UNKNOWN`` — never a fabricated number.

Outputs (``OutcomeScore``)
--------------------------
``fail_closed``, ``reason_codes``, ``quality_score``, ``risk_adjusted_score``,
``calibration_bucket``, ``confidence_alignment``, ``stale_data_penalty``,
``missed_opportunity_flag``, ``regime_mismatch_flag``. Plus a module-level
``turnover_warning(snapshots, threshold)``.

Safety / hermeticity
--------------------
Imports only the stdlib (``dataclasses``, ``typing``). No allocation/broker/live
import, no numpy/pandas, no network, no file I/O, no runtime read (never reads
``allocation_history.json``). Deterministic: identical inputs ⇒ identical output.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

# Reason codes (machine-stable).
REASON_STALE_INPUT = "STALE_INPUT"
REASON_MISSING_INPUT = "MISSING_INPUT"
REASON_MISSING_FORWARD_RETURN = "MISSING_FORWARD_RETURN"
REASON_UNKNOWN_DECISION = "UNKNOWN_DECISION"
REASON_MISSING_CONFIDENCE = "MISSING_CONFIDENCE"
REASON_MISSING_REGIME = "MISSING_REGIME"
REASON_MALFORMED_INPUT = "MALFORMED_INPUT"

_ACCEPTED = "ACCEPTED"
_NON_ACTED = {"REJECTED", "SKIPPED"}
_SCORE_DP = 4


@dataclass(frozen=True)
class OutcomeScore:
    fail_closed: bool
    reason_codes: Tuple[str, ...]
    quality_score: Optional[float]
    risk_adjusted_score: Optional[float]
    calibration_bucket: str
    confidence_alignment: str
    stale_data_penalty: float
    missed_opportunity_flag: bool
    regime_mismatch_flag: Optional[bool]


def _dedup(seq: Sequence[str]) -> Tuple[str, ...]:
    out: List[str] = []
    for s in seq:
        if s not in out:
            out.append(s)
    return tuple(out)


def score_outcome(outcome: dict) -> OutcomeScore:
    """Score one synthetic signal-outcome record (recommendation-only).

    Fails closed on malformed *types* rather than crashing: a non-mapping
    top-level input, or a non-mapping ``freshness`` / ``forward_returns`` field,
    is treated as untrusted (``MALFORMED_INPUT``) and degrades to UNKNOWN /
    withheld values — never a fabricated number and never an exception.
    """
    reasons: List[str] = []

    # Top-level type guard. ``None`` is a legitimate "absent" signal (degrades
    # like ``{}``); any other non-mapping is malformed and flagged.
    if isinstance(outcome, dict):
        o = dict(outcome)
    else:
        o = {}
        if outcome is not None:
            reasons.append(REASON_MALFORMED_INPUT)

    # Freshness type guard. A present-but-non-dict freshness means we cannot
    # verify the data is fresh, so we fail closed (withhold the score) rather
    # than assume it is fresh.
    freshness_raw = o.get("freshness")
    malformed_freshness = freshness_raw is not None and not isinstance(freshness_raw, dict)
    freshness = freshness_raw.get("status") if isinstance(freshness_raw, dict) else None
    fail_closed = freshness in ("STALE", "MISSING") or malformed_freshness
    stale_penalty = 1.0 if fail_closed else 0.0
    if freshness == "STALE":
        reasons.append(REASON_STALE_INPUT)
    elif freshness == "MISSING":
        reasons.append(REASON_MISSING_INPUT)
    if malformed_freshness:
        reasons.append(REASON_MALFORMED_INPUT)

    # Forward-returns type guard. A present-but-non-dict value is treated as a
    # missing forward return (null score) and flagged.
    fr_raw = o.get("forward_returns")
    if isinstance(fr_raw, dict):
        fr = fr_raw
    else:
        fr = {}
        if fr_raw is not None:
            reasons.append(REASON_MALFORMED_INPUT)
    fr20 = fr.get("20d")
    decision = o.get("decision")

    quality_score: Optional[float]
    if fail_closed:
        quality_score = None
    elif fr20 is None:
        quality_score = None
        reasons.append(REASON_MISSING_FORWARD_RETURN)
    elif decision == _ACCEPTED:
        quality_score = round(fr20 * 100, _SCORE_DP)          # acting well when forward positive
    elif decision in _NON_ACTED:
        quality_score = round(-fr20 * 100, _SCORE_DP)         # rejecting a loser scores positive
    else:
        quality_score = None
        reasons.append(REASON_UNKNOWN_DECISION)

    risk_adjusted_score = None if fail_closed else o.get("risk_adjusted_score")

    confidence = o.get("confidence")
    realized_good = o.get("realized_good")
    confidence_known = (not fail_closed) and confidence is not None and realized_good is not None
    if confidence is None and not fail_closed:
        reasons.append(REASON_MISSING_CONFIDENCE)

    if not confidence_known:
        calibration_bucket = "UNKNOWN"
        confidence_alignment = "UNKNOWN"
    elif confidence == "HIGH":
        calibration_bucket = "WELL_CALIBRATED" if realized_good else "OVERCONFIDENT"
        confidence_alignment = "ALIGNED" if realized_good else "MISALIGNED"
    elif confidence == "LOW":
        calibration_bucket = "UNDERCONFIDENT" if realized_good else "WELL_CALIBRATED"
        confidence_alignment = "ALIGNED" if not realized_good else "MISALIGNED"
    else:  # MEDIUM / other
        calibration_bucket = "NEUTRAL"
        confidence_alignment = "NEUTRAL"

    if "regime_mismatch" in o:
        regime_mismatch_flag: Optional[bool] = bool(o["regime_mismatch"])
    elif o.get("signal_regime") is not None and o.get("evaluation_regime") is not None:
        regime_mismatch_flag = o["signal_regime"] != o["evaluation_regime"]
    else:
        regime_mismatch_flag = None
        reasons.append(REASON_MISSING_REGIME)

    missed_opportunity_flag = bool(o.get("missed_opportunity", False))

    return OutcomeScore(
        fail_closed=fail_closed,
        reason_codes=_dedup(reasons),
        quality_score=quality_score,
        risk_adjusted_score=risk_adjusted_score,
        calibration_bucket=calibration_bucket,
        confidence_alignment=confidence_alignment,
        stale_data_penalty=stale_penalty,
        missed_opportunity_flag=missed_opportunity_flag,
        regime_mismatch_flag=regime_mismatch_flag,
    )


def _as_dict(value: object) -> dict:
    """Coerce a non-mapping value to ``{}`` (malformed-input safe degradation)."""
    return value if isinstance(value, dict) else {}


def _num(value: object) -> float:
    """Coerce a weight to a float; non-numeric ⇒ 0.0 (malformed-input safe)."""
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def turnover_warning(snapshots: Sequence[dict], threshold: float) -> Optional[bool]:
    """Stream-level turnover warning. < 2 snapshots ⇒ None (fail closed).

    Fails closed on malformed types: a non-dict snapshot or a non-dict
    ``weights`` value is coerced to ``{}`` rather than crashing.
    """
    snaps = list(snapshots) if isinstance(snapshots, (list, tuple)) else []
    if len(snaps) < 2:
        return None
    w0 = _as_dict(_as_dict(snaps[-2]).get("weights"))
    w1 = _as_dict(_as_dict(snaps[-1]).get("weights"))
    names = set(w0) | set(w1)
    t = sum(abs(_num(w1.get(n)) - _num(w0.get(n))) for n in names)
    return t > threshold
