"""Fail-closed regression contract for the allocation recommendation engine (stream D).

Pins that a malformed ``bot_health`` (a non-dict top level, or a non-dict per-bot
entry) holds the **baseline** allocation and never raises — "missing or malformed
data must never increase a risky bucket above baseline". Previously such inputs
raised ``AttributeError`` in ``_health_entry``.

Hermeticity: imports only the pure ``core`` engine + stdlib. No broker, no
network, no I/O, no runtime read/write. Broker-free under
``python -S -m unittest tests.test_recommendation_failclosed_contract``.
"""
from __future__ import annotations

import unittest

from core.recommendation_engine import generate_allocation_recommendation as _gen

_MALFORMED = (None, "x", 123, [], (), {"NovaBotV2": None}, {"NovaBotV2": "bad"},
              {"NovaBotV2": 123}, {"NovaBotV2Options": None})


class RecommendationFailClosedTest(unittest.TestCase):
    def setUp(self) -> None:
        # An empty-but-valid health map holds the baseline allocation.
        self.baseline = _gen({}).recommended_allocation

    def test_malformed_health_holds_baseline_and_never_raises(self) -> None:
        for bad in _MALFORMED:
            with self.subTest(bot_health=bad):
                result = _gen(bad)  # must not raise
                self.assertEqual(result.recommended_allocation, self.baseline)

    def test_baseline_is_stock_heavy(self) -> None:
        # Sanity: the held baseline is the documented static 90/10-style split,
        # i.e. malformed input never tilts a risky bucket above the largest one.
        largest = max(self.baseline, key=self.baseline.get)
        self.assertEqual(largest, "NovaBotV2")


if __name__ == "__main__":
    unittest.main()
