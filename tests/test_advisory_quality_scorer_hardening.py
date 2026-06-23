"""Synthetic hardening tests for the advisory quality scorer (ALLOC-003D).

Extends ``tests/test_advisory_quality_scorer.py`` (which is fixture-driven) with
direct-input hardening: safe degradation, scoring boundaries, JSON
serializability, determinism, turnover edges, and a pinned record of the
*known* malformed-type gaps. **Tests + docs only — the scorer source is not
changed in this loop.**

What it pins
------------
* empty / ``None`` input degrades to UNKNOWN with null scores and the right
  MISSING reason codes (never a fabricated number), without crashing;
* scoring boundaries: zero forward return scores 0.0; an unknown decision yields
  a null score + ``UNKNOWN_DECISION``; scores round to 4 dp;
* an ``OutcomeScore`` is JSON-serializable via ``dataclasses.asdict``;
* identical inputs ⇒ identical output (determinism);
* ``turnover_warning`` edges: < 2 snapshots ⇒ None; strict ``>`` threshold;
  a missing ``weights`` key degrades to ``{}`` rather than crashing;
* KNOWN GAPS (documented, see ``docs/ADVISORY_QUALITY_SCORER_HARDENING_NOTES.md``):
  non-dict top-level input and non-dict ``freshness``/``forward_returns``/
  ``weights`` currently raise instead of failing closed. These are pinned with
  ``assertRaises`` so a future (reviewed) hardening card that makes them
  fail-closed will trip these markers and consciously update them.

Hermeticity: imports the stdlib (``dataclasses``, ``json``, ``unittest``) and the
pure module. No allocation/broker import, no runtime read
(``allocation_history.json`` is never touched). Broker-free under
``python -S -m unittest tests.test_advisory_quality_scorer_hardening``.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import asdict

from quality_metrics.advisory_quality_scorer import (
    REASON_MISSING_CONFIDENCE,
    REASON_MISSING_FORWARD_RETURN,
    REASON_MISSING_REGIME,
    REASON_UNKNOWN_DECISION,
    OutcomeScore,
    score_outcome,
    turnover_warning,
)


def _fresh(**overrides) -> dict:
    base = {
        "freshness": {"status": "FRESH"},
        "forward_returns": {"20d": 0.05},
        "decision": "ACCEPTED",
        "confidence": "HIGH",
        "realized_good": True,
        "signal_regime": "BULL",
        "evaluation_regime": "BULL",
        "risk_adjusted_score": 1.1,
    }
    base.update(overrides)
    return base


class ScorerSafeDegradationTest(unittest.TestCase):
    def test_empty_input_degrades_to_unknown(self) -> None:
        r = score_outcome({})
        self.assertFalse(r.fail_closed)
        self.assertIsNone(r.quality_score)
        self.assertEqual(r.calibration_bucket, "UNKNOWN")
        self.assertEqual(r.confidence_alignment, "UNKNOWN")
        self.assertIsNone(r.regime_mismatch_flag)
        for reason in (REASON_MISSING_FORWARD_RETURN, REASON_MISSING_CONFIDENCE, REASON_MISSING_REGIME):
            self.assertIn(reason, r.reason_codes)

    def test_none_input_degrades_like_empty(self) -> None:
        self.assertEqual(score_outcome(None), score_outcome({}))

    def test_missing_forward_returns_yields_null_score(self) -> None:
        r = score_outcome(_fresh(forward_returns={}))
        self.assertIsNone(r.quality_score)
        self.assertIn(REASON_MISSING_FORWARD_RETURN, r.reason_codes)

    def test_unexpected_confidence_value_is_neutral(self) -> None:
        r = score_outcome(_fresh(confidence="VERY_HIGH"))
        self.assertEqual(r.calibration_bucket, "NEUTRAL")
        self.assertEqual(r.confidence_alignment, "NEUTRAL")
        self.assertNotIn(REASON_MISSING_CONFIDENCE, r.reason_codes)

    def test_regime_from_equal_fields_is_not_mismatch(self) -> None:
        r = score_outcome(_fresh(signal_regime="X", evaluation_regime="X"))
        self.assertFalse(r.regime_mismatch_flag)
        self.assertNotIn(REASON_MISSING_REGIME, r.reason_codes)


class ScorerBoundaryTest(unittest.TestCase):
    def test_zero_forward_return_accepted_scores_zero(self) -> None:
        r = score_outcome(_fresh(forward_returns={"20d": 0.0}))
        self.assertEqual(r.quality_score, 0.0)

    def test_zero_forward_return_rejected_scores_zero(self) -> None:
        r = score_outcome(_fresh(decision="REJECTED", forward_returns={"20d": 0.0}))
        self.assertEqual(r.quality_score, 0.0)  # -0.0 == 0.0

    def test_unknown_decision_yields_null_score(self) -> None:
        r = score_outcome(_fresh(decision="HOLD"))
        self.assertIsNone(r.quality_score)
        self.assertIn(REASON_UNKNOWN_DECISION, r.reason_codes)

    def test_score_rounds_to_four_decimals(self) -> None:
        r = score_outcome(_fresh(forward_returns={"20d": 0.1234567}))
        self.assertEqual(r.quality_score, 12.3457)


class ScorerSerializationTest(unittest.TestCase):
    def test_outcome_score_is_json_serializable(self) -> None:
        for inp in ({}, None, _fresh(), _fresh(freshness={"status": "STALE"})):
            score = score_outcome(inp)
            self.assertIsInstance(score, OutcomeScore)
            encoded = json.dumps(asdict(score))  # must not raise
            loaded = json.loads(encoded)
            for key in ("fail_closed", "reason_codes", "quality_score",
                        "calibration_bucket", "confidence_alignment"):
                self.assertIn(key, loaded)


class ScorerDeterminismTest(unittest.TestCase):
    def test_identical_inputs_identical_output(self) -> None:
        for inp in (_fresh(), _fresh(decision="REJECTED", realized_good=False),
                    _fresh(freshness={"status": "MISSING"}), {}, None):
            self.assertEqual(score_outcome(inp), score_outcome(inp))


class TurnoverEdgeTest(unittest.TestCase):
    def test_insufficient_snapshots_returns_none(self) -> None:
        self.assertIsNone(turnover_warning([], 0.1))
        self.assertIsNone(turnover_warning([{"weights": {"A": 1.0}}], 0.1))

    def test_threshold_is_strict_greater_than(self) -> None:
        snaps = [{"weights": {"A": 0.5, "B": 0.5}}, {"weights": {"A": 0.6, "B": 0.4}}]
        self.assertFalse(turnover_warning(snaps, 0.2))  # turnover 0.2, not > 0.2
        self.assertTrue(turnover_warning(snaps, 0.1))

    def test_identical_weights_is_no_turnover(self) -> None:
        snaps = [{"weights": {"A": 0.5}}, {"weights": {"A": 0.5}}]
        self.assertFalse(turnover_warning(snaps, 0.0))

    def test_missing_weights_key_degrades_to_empty(self) -> None:
        # the first snapshot has no 'weights' key -> treated as {} -> no crash
        self.assertTrue(turnover_warning([{}, {"weights": {"A": 1.0}}], 0.5))


class ScorerKnownGapTest(unittest.TestCase):
    """Pins KNOWN malformed-type gaps (raise instead of fail-closed).

    Documented in ``docs/ADVISORY_QUALITY_SCORER_HARDENING_NOTES.md`` as a future,
    *reviewed* hardening card (code change out of scope for this tests/docs loop).
    A future fix that makes these fail closed will trip these markers and must
    consciously update them.
    """

    def test_non_dict_top_level_input_currently_raises(self) -> None:
        with self.assertRaises((ValueError, TypeError)):
            score_outcome("not-a-dict")
        with self.assertRaises((ValueError, TypeError)):
            score_outcome(5)

    def test_non_dict_freshness_currently_raises(self) -> None:
        with self.assertRaises(AttributeError):
            score_outcome({"freshness": "STALE"})

    def test_non_dict_forward_returns_currently_raises(self) -> None:
        with self.assertRaises(AttributeError):
            score_outcome({"freshness": {"status": "FRESH"}, "forward_returns": "nope",
                           "decision": "ACCEPTED"})

    def test_non_dict_snapshot_or_weights_currently_raises(self) -> None:
        with self.assertRaises(AttributeError):
            turnover_warning(["a", "b"], 0.1)
        with self.assertRaises(AttributeError):
            turnover_warning([{"weights": ["x"]}, {"weights": {"A": 1.0}}], 0.1)


if __name__ == "__main__":
    unittest.main()
