"""Static schema-conformance test for the advisory quality-metrics contract.

Task: ALLOC-003A, validating the synthetic fixture
``tests/fixtures/quality_metrics/advisory_quality_examples.json`` against
``docs/contracts/advisory_quality_metrics_contract.md``.

What it pins
------------
* required fields + enums per signal-outcome record and per recommendation
  snapshot;
* the deterministic ``acceptance_rate``, ``turnover`` and
  ``staleness.fresh_share`` recomputed here as pure reference oracles and
  matched to the declared aggregate;
* fail-closed: a STALE signal withholds its outcome metrics (forward returns,
  drawdown, risk-adjusted score are ``null`` — never a fabricated number);
* ``missed_opportunity`` is only ever set on a non-accepted signal;
* the contract's advisory-only truth label (``recommendation_only = true``);
* a leak scan over string *values* finds no account/path/secret token.

Safety / hermeticity
--------------------
This test imports **no** allocation/broker module — only the stdlib (``json``,
``re``, ``unittest``, ``pathlib``). It reads one committed synthetic fixture,
writes nothing, and touches no runtime/generated data
(``data/system/allocation_history.json`` is never read). Broker-free under
``python -S -m unittest tests.test_advisory_quality_metrics_contract``.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "quality_metrics" / "advisory_quality_examples.json"

_SOURCES = {"NOVABOTV2", "OPTIONS", "ALLOCATION"}
_DECISIONS = {"ACCEPTED", "REJECTED", "SKIPPED"}
_FRESH_STATUS = {"FRESH", "STALE", "MISSING", "UNKNOWN"}
_REQUIRED_OUTCOME_FIELDS = (
    "source", "signal_id", "decision", "reason_code", "forward_returns",
    "drawdown_after_pct", "missed_opportunity", "risk_adjusted_score",
    "freshness", "synthetic",
)

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


def _acceptance_rate(outcomes: list[dict]):
    total = len(outcomes)
    if total == 0:
        return None  # fail closed: never 0
    accepted = sum(1 for o in outcomes if o["decision"] == "ACCEPTED")
    return accepted / total


def _turnover(snapshots: list[dict]):
    if len(snapshots) < 2:
        return None  # fail closed
    w0, w1 = snapshots[-2]["weights"], snapshots[-1]["weights"]
    names = set(w0) | set(w1)
    return sum(abs(w1.get(n, 0.0) - w0.get(n, 0.0)) for n in names)


def _fresh_share(outcomes: list[dict]):
    total = len(outcomes)
    if total == 0:
        return None  # fail closed
    fresh = sum(1 for o in outcomes if o["freshness"]["status"] == "FRESH")
    return fresh / total


class AdvisoryQualityMetricsContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _load()
        self.outcomes = self.data["signal_outcomes"]
        self.snapshots = self.data["allocation_recommendation_snapshots"]
        self.aggregate = self.data["aggregate"]

    def test_fixture_is_marked_synthetic_and_advisory(self) -> None:
        self.assertTrue(self.data.get("synthetic") is True)
        self.assertTrue(self.data.get("data_is_real") is False)
        self.assertIs(self.data.get("recommendation_only"), True)
        self.assertIs(self.aggregate.get("recommendation_only"), True)

    def test_outcome_required_fields_and_enums(self) -> None:
        for o in self.outcomes:
            with self.subTest(signal_id=o.get("signal_id", "<no-id>")):
                for field in _REQUIRED_OUTCOME_FIELDS:
                    self.assertIn(field, o, f"missing {field}")
                self.assertIn(o["source"], _SOURCES)
                self.assertIn(o["decision"], _DECISIONS)
                self.assertIn(o["freshness"]["status"], _FRESH_STATUS)
                self.assertIsInstance(o["missed_opportunity"], bool)
                self.assertIs(o["synthetic"], True)

    def test_acceptance_rate_oracle(self) -> None:
        self.assertAlmostEqual(
            self.aggregate["acceptance_rate"], _acceptance_rate(self.outcomes), places=9)
        self.assertEqual(self.aggregate["signals_accepted"],
                         sum(1 for o in self.outcomes if o["decision"] == "ACCEPTED"))
        self.assertEqual(self.aggregate["total"], len(self.outcomes))

    def test_turnover_oracle(self) -> None:
        self.assertAlmostEqual(self.aggregate["turnover"], _turnover(self.snapshots), places=9)

    def test_fresh_share_oracle(self) -> None:
        self.assertAlmostEqual(
            self.aggregate["staleness"]["fresh_share"], _fresh_share(self.outcomes), places=9)

    def test_stale_signal_withholds_outcome_metrics(self) -> None:
        # Fail-closed: a STALE signal must not carry a fabricated outcome number.
        for o in self.outcomes:
            if o["freshness"]["status"] == "STALE":
                with self.subTest(signal_id=o["signal_id"]):
                    self.assertIsNone(o["risk_adjusted_score"])
                    self.assertIsNone(o["drawdown_after_pct"])
                    self.assertTrue(
                        all(v is None for v in o["forward_returns"].values()),
                        "stale signal must withhold every forward return (UNKNOWN)",
                    )

    def test_missed_opportunity_only_on_non_accepted(self) -> None:
        for o in self.outcomes:
            if o["missed_opportunity"]:
                with self.subTest(signal_id=o["signal_id"]):
                    self.assertNotEqual(
                        o["decision"], "ACCEPTED",
                        "missed_opportunity is meaningless for an accepted signal",
                    )

    def test_unknown_metrics_carry_no_number(self) -> None:
        # calibration / recommendation_quality are UNKNOWN here (no paired
        # realized outcome) and must not smuggle a score in.
        for key in ("calibration", "recommendation_quality"):
            with self.subTest(metric=key):
                block = self.aggregate[key]
                self.assertEqual(block.get("status"), "UNKNOWN")
                self.assertNotIn("score", block)

    def test_no_leak_tokens_in_string_values(self) -> None:
        payload = {
            "signal_outcomes": self.outcomes,
            "allocation_recommendation_snapshots": self.snapshots,
            "aggregate": self.aggregate,
        }
        for value in _string_values(payload):
            for pat in _LEAK_PATTERNS:
                self.assertIsNone(
                    pat.search(value),
                    f"leak token {pat.pattern!r} found in value {value!r}",
                )


if __name__ == "__main__":
    unittest.main()
