"""Reference-oracle tests for advisory quality scoring.

Task: ALLOC-003C, exercising the scoring rules of
``docs/contracts/advisory_quality_metrics_contract.md`` over the ALLOC-003B
synthetic fixtures ``tests/fixtures/quality_metrics/advisory_quality_cases.json``.

The scorer is embodied here as a pure, deterministic in-test reference oracle
(mirroring the benchmark / perf-ledger contract tests). The production scorer
module is ``ALLOC-003D`` (``core/advisory_quality_metrics.py``), which is SAFE
but gated on ``ALLOC-003A/B/C`` being DONE; this card pins the contract it must
satisfy without prematurely creating the module.

Scored outputs per outcome: ``quality_score`` (decision quality given the
realized outcome), ``risk_adjusted_score`` (pass-through, withheld when stale),
``calibration_bucket``, ``stale_data_penalty``, ``missed_opportunity_flag``, plus
aggregate ``turnover_warning`` and fail-closed ``reason_codes``.

Safety / hermeticity
--------------------
Imports **no** allocation/broker module — only the stdlib (``json``,
``unittest``, ``pathlib``). Reads one committed synthetic fixture, writes
nothing, touches no runtime/generated data. Broker-free under
``python -S -m unittest tests.test_advisory_quality_metrics``.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "quality_metrics" / "advisory_quality_cases.json"

# Reason codes (fail-closed).
REASON_STALE_INPUT = "STALE_INPUT"
REASON_MISSING_INPUT = "MISSING_INPUT"


# --- reference oracle (the scoring contract, in code) ------------------------

def score_outcome(o: dict) -> dict:
    """Pure decision-quality scorer for one synthetic outcome record."""
    status = "OK"
    reasons: list[str] = []
    freshness = o["freshness"]["status"]

    if freshness == "STALE":
        status, stale_penalty = "FAIL_CLOSED", 1.0
        reasons.append(REASON_STALE_INPUT)
    elif freshness == "MISSING":
        status, stale_penalty = "FAIL_CLOSED", 1.0
        reasons.append(REASON_MISSING_INPUT)
    else:
        stale_penalty = 0.0

    if status == "FAIL_CLOSED":
        # Outcome metrics are withheld — never a fabricated number.
        return {
            "status": status,
            "reason_codes": tuple(reasons),
            "quality_score": None,
            "risk_adjusted_score": None,
            "calibration_bucket": "UNKNOWN",
            "stale_data_penalty": stale_penalty,
            "missed_opportunity_flag": bool(o["missed_opportunity"]),
        }

    fr20 = o["forward_returns"]["20d"]
    if o["decision"] == "ACCEPTED":
        quality_score = round(fr20 * 100, 4)          # acting well when forward is positive
    else:  # REJECTED / SKIPPED: rejecting a loser is good, rejecting a winner is bad
        quality_score = round(-fr20 * 100, 4)

    # Calibration: confidence vs whether it turned out good.
    conf, realized_good = o["confidence"], o["realized_good"]
    if realized_good is None:
        calibration_bucket = "UNKNOWN"
    elif conf == "HIGH":
        calibration_bucket = "WELL_CALIBRATED" if realized_good else "OVERCONFIDENT"
    elif conf == "LOW":
        calibration_bucket = "UNDERCONFIDENT" if realized_good else "WELL_CALIBRATED"
    else:
        calibration_bucket = "NEUTRAL"

    return {
        "status": status,
        "reason_codes": tuple(reasons),
        "quality_score": quality_score,
        "risk_adjusted_score": o["risk_adjusted_score"],
        "calibration_bucket": calibration_bucket,
        "stale_data_penalty": stale_penalty,
        "missed_opportunity_flag": bool(o["missed_opportunity"]),
    }


def turnover_warning(snapshots: list, threshold: float):
    pair = [s for s in snapshots if s.get("case_id") == "turnover_warning"]
    if len(pair) < 2:
        return None  # fail closed: insufficient snapshots
    w0, w1 = pair[-2]["weights"], pair[-1]["weights"]
    names = set(w0) | set(w1)
    t = sum(abs(w1.get(n, 0.0) - w0.get(n, 0.0)) for n in names)
    return t > threshold


class AdvisoryQualityScoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        self.by_case = {o["case_id"]: o for o in self.data["signal_outcomes"]}

    def _score(self, case_id):
        return score_outcome(self.by_case[case_id])

    def test_accepted_good_scores_positive(self) -> None:
        r = self._score("accepted_good")
        self.assertEqual(r["status"], "OK")
        self.assertGreater(r["quality_score"], 0)
        self.assertEqual(r["calibration_bucket"], "WELL_CALIBRATED")

    def test_accepted_bad_scores_negative(self) -> None:
        r = self._score("accepted_bad")
        self.assertLess(r["quality_score"], 0)

    def test_rejected_good_is_a_miss(self) -> None:
        r = self._score("rejected_good")
        self.assertLess(r["quality_score"], 0)  # rejecting a winner
        self.assertTrue(r["missed_opportunity_flag"])

    def test_rejected_bad_scores_positive(self) -> None:
        r = self._score("rejected_bad")
        self.assertGreater(r["quality_score"], 0)  # avoided a loser
        self.assertFalse(r["missed_opportunity_flag"])

    def test_missed_opportunity_flag(self) -> None:
        r = self._score("missed_opportunity")
        self.assertTrue(r["missed_opportunity_flag"])
        self.assertLess(r["quality_score"], 0)

    def test_stale_upstream_fails_closed(self) -> None:
        r = self._score("stale_upstream")
        self.assertEqual(r["status"], "FAIL_CLOSED")
        self.assertIsNone(r["quality_score"])
        self.assertIsNone(r["risk_adjusted_score"])
        self.assertEqual(r["stale_data_penalty"], 1.0)
        self.assertIn(REASON_STALE_INPUT, r["reason_codes"])
        self.assertEqual(r["calibration_bucket"], "UNKNOWN")

    def test_missing_upstream_fails_closed(self) -> None:
        r = self._score("missing_upstream")
        self.assertEqual(r["status"], "FAIL_CLOSED")
        self.assertIsNone(r["quality_score"])
        self.assertIn(REASON_MISSING_INPUT, r["reason_codes"])

    def test_low_confidence_correct_is_underconfident(self) -> None:
        r = self._score("low_confidence")
        self.assertEqual(r["calibration_bucket"], "UNDERCONFIDENT")

    def test_high_confidence_correct_is_well_calibrated(self) -> None:
        r = self._score("high_confidence_correct")
        self.assertEqual(r["calibration_bucket"], "WELL_CALIBRATED")

    def test_high_confidence_wrong_is_overconfident(self) -> None:
        r = self._score("high_confidence_wrong")
        self.assertEqual(r["calibration_bucket"], "OVERCONFIDENT")
        self.assertEqual(r["stale_data_penalty"], 0.0)

    def test_regime_mismatch_outcome_still_scored(self) -> None:
        # regime mismatch is FRESH, so it is scored (and was a loser here).
        r = self._score("regime_mismatch")
        self.assertEqual(r["status"], "OK")
        self.assertLess(r["quality_score"], 0)

    def test_turnover_warning_flag(self) -> None:
        warn = turnover_warning(self.data["allocation_recommendation_snapshots"],
                                self.data["turnover_warning_threshold"])
        self.assertTrue(warn)

    def test_determinism(self) -> None:
        for case_id in self.by_case:
            with self.subTest(case=case_id):
                self.assertEqual(self._score(case_id), self._score(case_id))


if __name__ == "__main__":
    unittest.main()
