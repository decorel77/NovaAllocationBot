"""Tests for the pure advisory quality scorer module (ALLOC-003D).

Exercises ``quality_metrics.advisory_quality_scorer`` over the committed synthetic
fixtures ``tests/fixtures/quality_metrics/advisory_quality_cases.json`` (003B) and
``tests/fixtures/quality_metrics/advisory_quality_examples.json`` (003A).

What it pins
------------
* per-outcome quality scoring (decision quality vs realized outcome);
* calibration bucket + confidence alignment (and UNKNOWN when the 003A records
  omit confidence);
* fail-closed: STALE / MISSING upstream ⇒ ``fail_closed`` with null quality /
  risk-adjusted score + ``stale_data_penalty`` 1.0 + the right reason code;
* ``missed_opportunity_flag`` and ``regime_mismatch_flag`` (None when the 003A
  records omit regime fields);
* stream-level ``turnover_warning`` (True above threshold, False below, None on
  insufficient snapshots);
* determinism; advisory-only (no allocation/runtime read).

Safety / hermeticity
--------------------
Imports the stdlib (``json``, ``unittest``, ``pathlib``) and the pure module
under test. No allocation/broker import, no runtime read (``allocation_history.json``
is never touched). Broker-free under
``python -S -m unittest tests.test_advisory_quality_scorer``.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from quality_metrics.advisory_quality_scorer import (
    REASON_STALE_INPUT, REASON_MISSING_INPUT, REASON_MISSING_CONFIDENCE,
    REASON_MISSING_REGIME, score_outcome, turnover_warning,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CASES = _REPO_ROOT / "tests" / "fixtures" / "quality_metrics" / "advisory_quality_cases.json"
_EXAMPLES = _REPO_ROOT / "tests" / "fixtures" / "quality_metrics" / "advisory_quality_examples.json"


class ScorerCasesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = json.loads(_CASES.read_text(encoding="utf-8"))
        self.by_case = {o["case_id"]: o for o in self.data["signal_outcomes"]}

    def _s(self, case_id):
        return score_outcome(self.by_case[case_id])

    def test_accepted_good(self) -> None:
        r = self._s("accepted_good")
        self.assertFalse(r.fail_closed)
        self.assertGreater(r.quality_score, 0)
        self.assertEqual(r.calibration_bucket, "WELL_CALIBRATED")
        self.assertEqual(r.confidence_alignment, "ALIGNED")
        self.assertFalse(r.regime_mismatch_flag)

    def test_accepted_bad_medium_confidence_is_neutral(self) -> None:
        r = self._s("accepted_bad")
        self.assertLess(r.quality_score, 0)
        self.assertEqual(r.calibration_bucket, "NEUTRAL")
        self.assertEqual(r.confidence_alignment, "NEUTRAL")

    def test_rejected_good_is_a_miss(self) -> None:
        r = self._s("rejected_good")
        self.assertLess(r.quality_score, 0)
        self.assertTrue(r.missed_opportunity_flag)

    def test_rejected_bad_scores_positive(self) -> None:
        r = self._s("rejected_bad")
        self.assertGreater(r.quality_score, 0)
        self.assertFalse(r.missed_opportunity_flag)

    def test_missed_opportunity_low_conf_good(self) -> None:
        r = self._s("missed_opportunity")
        self.assertTrue(r.missed_opportunity_flag)
        self.assertLess(r.quality_score, 0)
        self.assertEqual(r.calibration_bucket, "UNDERCONFIDENT")
        self.assertEqual(r.confidence_alignment, "MISALIGNED")

    def test_stale_upstream_fails_closed(self) -> None:
        r = self._s("stale_upstream")
        self.assertTrue(r.fail_closed)
        self.assertIsNone(r.quality_score)
        self.assertIsNone(r.risk_adjusted_score)
        self.assertEqual(r.stale_data_penalty, 1.0)
        self.assertIn(REASON_STALE_INPUT, r.reason_codes)
        self.assertEqual(r.calibration_bucket, "UNKNOWN")
        self.assertEqual(r.confidence_alignment, "UNKNOWN")

    def test_missing_upstream_fails_closed(self) -> None:
        r = self._s("missing_upstream")
        self.assertTrue(r.fail_closed)
        self.assertIn(REASON_MISSING_INPUT, r.reason_codes)

    def test_low_confidence_correct(self) -> None:
        r = self._s("low_confidence")
        self.assertEqual(r.calibration_bucket, "UNDERCONFIDENT")
        self.assertEqual(r.confidence_alignment, "MISALIGNED")
        self.assertGreater(r.quality_score, 0)

    def test_high_confidence_correct(self) -> None:
        r = self._s("high_confidence_correct")
        self.assertEqual(r.calibration_bucket, "WELL_CALIBRATED")
        self.assertEqual(r.confidence_alignment, "ALIGNED")

    def test_high_confidence_wrong(self) -> None:
        r = self._s("high_confidence_wrong")
        self.assertEqual(r.calibration_bucket, "OVERCONFIDENT")
        self.assertEqual(r.confidence_alignment, "MISALIGNED")
        self.assertEqual(r.stale_data_penalty, 0.0)

    def test_regime_mismatch_flag(self) -> None:
        r = self._s("regime_mismatch")
        self.assertTrue(r.regime_mismatch_flag)
        self.assertFalse(r.fail_closed)

    def test_turnover_warning_true_above_threshold(self) -> None:
        warn = turnover_warning(self.data["allocation_recommendation_snapshots"],
                                self.data["turnover_warning_threshold"])
        self.assertTrue(warn)

    def test_determinism(self) -> None:
        for cid in self.by_case:
            with self.subTest(case=cid):
                self.assertEqual(self._s(cid), self._s(cid))


class ScorerExamplesTest(unittest.TestCase):
    """The 003A records omit confidence/regime — those metrics fail closed to UNKNOWN."""

    def setUp(self) -> None:
        self.data = json.loads(_EXAMPLES.read_text(encoding="utf-8"))
        self.by_id = {o["signal_id"]: o for o in self.data["signal_outcomes"]}

    def test_minimal_record_scores_but_calibration_unknown(self) -> None:
        r = score_outcome(self.by_id["S-1"])  # ACCEPTED, FRESH, no confidence/regime
        self.assertFalse(r.fail_closed)
        self.assertGreater(r.quality_score, 0)
        self.assertEqual(r.calibration_bucket, "UNKNOWN")
        self.assertEqual(r.confidence_alignment, "UNKNOWN")
        self.assertIsNone(r.regime_mismatch_flag)
        self.assertIn(REASON_MISSING_CONFIDENCE, r.reason_codes)
        self.assertIn(REASON_MISSING_REGIME, r.reason_codes)

    def test_stale_example_fails_closed(self) -> None:
        r = score_outcome(self.by_id["S-3"])  # STALE
        self.assertTrue(r.fail_closed)
        self.assertIsNone(r.quality_score)

    def test_turnover_below_threshold_is_false(self) -> None:
        warn = turnover_warning(self.data["allocation_recommendation_snapshots"], 0.30)
        self.assertFalse(warn)  # 003A snapshots turnover 0.2 < 0.30

    def test_single_snapshot_is_none(self) -> None:
        self.assertIsNone(turnover_warning(self.data["allocation_recommendation_snapshots"][:1], 0.30))


if __name__ == "__main__":
    unittest.main()
