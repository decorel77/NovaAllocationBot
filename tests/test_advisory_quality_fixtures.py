"""Static schema-conformance test for the ALLOC-003B advisory quality cases.

Task: ALLOC-003B, validating the synthetic fixture
``tests/fixtures/quality_metrics/advisory_quality_cases.json`` against
``docs/contracts/advisory_quality_metrics_contract.md`` (extending ALLOC-003A).

What it pins
------------
* synthetic / advisory markers (``recommendation_only = true``);
* the twelve ALLOC-003B case ids are all present;
* required fields + enums per outcome (source / decision / freshness / confidence);
* fail-closed: STALE *and* MISSING upstream snapshots withhold every outcome
  metric (forward returns, drawdown, risk-adjusted score are ``null``);
* ``missed_opportunity`` is only ever set on a non-accepted signal;
* ``regime_mismatch`` is exactly ``signal_regime != evaluation_regime``;
* the turnover-warning snapshot pair exceeds the documented warning threshold;
* a leak scan over string values finds no account/path/secret token.

Safety / hermeticity
--------------------
Imports **no** allocation/broker module — only the stdlib (``json``, ``re``,
``unittest``, ``pathlib``). Reads one committed synthetic fixture, writes
nothing, touches no runtime/generated data (``allocation_history.json`` is never
read). Broker-free under
``python -S -m unittest tests.test_advisory_quality_fixtures``.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "quality_metrics" / "advisory_quality_cases.json"

_SOURCES = {"NOVABOTV2", "OPTIONS", "ALLOCATION"}
_DECISIONS = {"ACCEPTED", "REJECTED", "SKIPPED"}
_FRESH_STATUS = {"FRESH", "STALE", "MISSING", "UNKNOWN"}
_REQUIRED_OUTCOME_FIELDS = (
    "source", "signal_id", "case_id", "decision", "reason_code", "confidence",
    "predicted_good", "realized_good", "forward_returns", "drawdown_after_pct",
    "missed_opportunity", "risk_adjusted_score", "signal_regime",
    "evaluation_regime", "regime_mismatch", "freshness", "synthetic",
)
_EXPECTED_OUTCOME_CASES = {
    "accepted_good", "accepted_bad", "rejected_good", "rejected_bad",
    "missed_opportunity", "stale_upstream", "missing_upstream", "low_confidence",
    "high_confidence_correct", "high_confidence_wrong", "regime_mismatch",
}

_LEAK_PATTERNS = (
    re.compile(r"U\d{6,}"),
    re.compile(r"\b\d{8,}\b"),
    re.compile(r"[A-Za-z]:\\"),
    re.compile(r"/Users/"),
    re.compile(r"/home/"),
    re.compile(r"ib_insync"),
    re.compile(r"placeOrder"),
    re.compile(r"api_key", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"\.env\b"),
)


def _load() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _string_values(node) -> list[str]:
    out: list[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            out.extend(_string_values(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_string_values(v))
    return out


def _turnover(w0: dict, w1: dict) -> float:
    names = set(w0) | set(w1)
    return sum(abs(w1.get(n, 0.0) - w0.get(n, 0.0)) for n in names)


class AdvisoryQualityCasesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _load()
        self.outcomes = self.data["signal_outcomes"]
        self.snapshots = self.data["allocation_recommendation_snapshots"]
        self.confidence_levels = set(self.data["confidence_levels"])

    def test_fixture_is_marked_synthetic_and_advisory(self) -> None:
        self.assertIs(self.data.get("synthetic"), True)
        self.assertIs(self.data.get("data_is_real"), False)
        self.assertIs(self.data.get("recommendation_only"), True)
        self.assertEqual(self.data.get("schema"), "advisory_quality_cases.v1")

    def test_all_twelve_case_ids_present(self) -> None:
        outcome_cases = {o["case_id"] for o in self.outcomes}
        self.assertEqual(outcome_cases, _EXPECTED_OUTCOME_CASES)
        snapshot_cases = {s["case_id"] for s in self.snapshots}
        self.assertIn("turnover_warning", snapshot_cases)
        self.assertEqual(len(_EXPECTED_OUTCOME_CASES) + 1, 12)

    def test_outcome_required_fields_and_enums(self) -> None:
        for o in self.outcomes:
            with self.subTest(case=o["case_id"]):
                for field in _REQUIRED_OUTCOME_FIELDS:
                    self.assertIn(field, o, f"missing {field}")
                self.assertIn(o["source"], _SOURCES)
                self.assertIn(o["decision"], _DECISIONS)
                self.assertIn(o["freshness"]["status"], _FRESH_STATUS)
                self.assertIn(o["confidence"], self.confidence_levels)
                self.assertIsInstance(o["missed_opportunity"], bool)
                self.assertIsInstance(o["regime_mismatch"], bool)
                self.assertIs(o["synthetic"], True)

    def test_stale_and_missing_withhold_outcome_metrics(self) -> None:
        for o in self.outcomes:
            if o["freshness"]["status"] in {"STALE", "MISSING"}:
                with self.subTest(case=o["case_id"]):
                    self.assertIsNone(o["risk_adjusted_score"])
                    self.assertIsNone(o["drawdown_after_pct"])
                    self.assertTrue(all(v is None for v in o["forward_returns"].values()),
                                    "stale/missing upstream must withhold every forward return")

    def test_missed_opportunity_only_on_non_accepted(self) -> None:
        for o in self.outcomes:
            if o["missed_opportunity"]:
                with self.subTest(case=o["case_id"]):
                    self.assertNotEqual(o["decision"], "ACCEPTED")

    def test_regime_mismatch_is_consistent(self) -> None:
        for o in self.outcomes:
            with self.subTest(case=o["case_id"]):
                self.assertEqual(o["regime_mismatch"],
                                 o["signal_regime"] != o["evaluation_regime"])
        # at least one explicit mismatch case
        self.assertTrue(any(o["regime_mismatch"] for o in self.outcomes))

    def test_turnover_warning_snapshot_exceeds_threshold(self) -> None:
        threshold = self.data["turnover_warning_threshold"]
        pair = [s for s in self.snapshots if s["case_id"] == "turnover_warning"]
        self.assertGreaterEqual(len(pair), 2)
        t = _turnover(pair[-2]["weights"], pair[-1]["weights"])
        self.assertGreater(t, threshold, "turnover-warning pair must exceed the warning threshold")

    def test_no_leak_tokens_in_string_values(self) -> None:
        # Scan the data records (not the envelope meta-note prose), matching the
        # ALLOC-003A convention.
        payload = {"signal_outcomes": self.outcomes,
                   "allocation_recommendation_snapshots": self.snapshots}
        for value in _string_values(payload):
            for pat in _LEAK_PATTERNS:
                self.assertIsNone(pat.search(value),
                                  f"leak token {pat.pattern!r} found in value {value!r}")


if __name__ == "__main__":
    unittest.main()
