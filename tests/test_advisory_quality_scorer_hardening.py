"""Synthetic hardening tests for the advisory quality scorer (ALLOC-003D).

Extends ``tests/test_advisory_quality_scorer.py`` (which is fixture-driven) with
direct-input hardening: safe degradation, scoring boundaries, JSON
serializability, determinism, turnover edges, and the malformed-*type* fail-closed
behavior. The previously-documented malformed-type gaps are now **fixed** in the
scorer source (this loop): a non-dict top-level input, a non-dict
``freshness``/``forward_returns``, or a non-dict snapshot/``weights`` no longer
raises — it degrades to UNKNOWN / withheld values, never a fabricated number.

What it pins
------------
* empty / ``None`` input degrades to UNKNOWN with null scores and the right
  MISSING reason codes (never a fabricated number), without crashing;
* scoring boundaries: zero forward return scores 0.0; an unknown decision yields
  a null score + ``UNKNOWN_DECISION``; scores round to 4 dp;
* an ``OutcomeScore`` is JSON-serializable via ``dataclasses.asdict``;
* identical inputs ⇒ identical output (determinism), incl. malformed inputs;
* ``turnover_warning`` edges: < 2 snapshots ⇒ None; strict ``>`` threshold;
  a missing ``weights`` key degrades to ``{}`` rather than crashing;
* MALFORMED TYPES NOW FAIL CLOSED (see
  ``docs/ADVISORY_QUALITY_SCORER_HARDENING_NOTES.md``): a non-dict top-level
  input and a non-dict ``freshness``/``forward_returns``/snapshot/``weights``
  degrade safely (``MALFORMED_INPUT`` reason code; freshness fails closed) and
  never raise.

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
    REASON_MALFORMED_INPUT,
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


class ScorerMalformedTypeTest(unittest.TestCase):
    """Malformed *types* now fail closed instead of raising (ALLOC-003D fix).

    Documented in ``docs/ADVISORY_QUALITY_SCORER_HARDENING_NOTES.md``. A non-dict
    top-level input and a non-dict ``freshness``/``forward_returns``/snapshot/
    ``weights`` degrade safely (``MALFORMED_INPUT`` reason; freshness fails
    closed) and never raise. None of these change a well-formed result — they
    only make the scorer *more* fail-closed.
    """

    def test_non_dict_top_level_input_degrades_to_unknown(self) -> None:
        for bad in ("not-a-dict", 5, ["a"], 3.14):
            r = score_outcome(bad)  # must not raise
            self.assertIsInstance(r, OutcomeScore)
            self.assertIsNone(r.quality_score)
            self.assertEqual(r.calibration_bucket, "UNKNOWN")
            self.assertEqual(r.confidence_alignment, "UNKNOWN")
            self.assertIn(REASON_MALFORMED_INPUT, r.reason_codes)

    def test_none_top_level_is_not_flagged_malformed(self) -> None:
        # ``None`` is a legitimate "absent" signal, not malformed garbage.
        self.assertNotIn(REASON_MALFORMED_INPUT, score_outcome(None).reason_codes)
        self.assertEqual(score_outcome(None), score_outcome({}))

    def test_non_dict_freshness_fails_closed(self) -> None:
        r = score_outcome({"freshness": "STALE"})  # string, not a dict -> untrusted
        self.assertTrue(r.fail_closed)
        self.assertEqual(r.stale_data_penalty, 1.0)
        self.assertIsNone(r.quality_score)
        self.assertIsNone(r.risk_adjusted_score)
        self.assertIn(REASON_MALFORMED_INPUT, r.reason_codes)

    def test_non_dict_forward_returns_is_missing_forward_return(self) -> None:
        r = score_outcome({"freshness": {"status": "FRESH"}, "forward_returns": "nope",
                           "decision": "ACCEPTED"})  # must not raise
        self.assertFalse(r.fail_closed)
        self.assertIsNone(r.quality_score)
        self.assertIn(REASON_MISSING_FORWARD_RETURN, r.reason_codes)
        self.assertIn(REASON_MALFORMED_INPUT, r.reason_codes)

    def test_non_dict_snapshot_degrades_without_crashing(self) -> None:
        # both snapshots coerce to {} -> no weights -> zero turnover -> not > 0.1
        self.assertFalse(turnover_warning(["a", "b"], 0.1))

    def test_non_dict_weights_degrades_without_crashing(self) -> None:
        # malformed prior weights ([...]) coerce to {}; current {"A": 1.0}
        self.assertTrue(turnover_warning([{"weights": ["x"]}, {"weights": {"A": 1.0}}], 0.1))

    def test_non_numeric_weight_value_degrades_to_zero(self) -> None:
        # a string weight is coerced to 0.0 rather than crashing the subtraction
        snaps = [{"weights": {"A": "oops"}}, {"weights": {"A": 1.0}}]
        self.assertTrue(turnover_warning(snaps, 0.5))

    def test_malformed_inputs_are_json_serializable_and_deterministic(self) -> None:
        for bad in ("not-a-dict", {"freshness": "STALE"},
                    {"freshness": {"status": "FRESH"}, "forward_returns": "nope",
                     "decision": "ACCEPTED"}):
            r1 = score_outcome(bad)
            r2 = score_outcome(bad)
            self.assertEqual(r1, r2)                       # deterministic
            json.dumps(asdict(r1))                         # JSON-serializable (no raise)


if __name__ == "__main__":
    unittest.main()
