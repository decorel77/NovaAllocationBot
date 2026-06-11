"""REPAIR-007 tests: single authoritative allocation + refuse unverified regime.

Covers:
  - market_regime_adapter consumes the REPAIR-005 data_is_real flag,
  - build_authoritative_allocation uses the regime only when verified real and
    otherwise refuses it and falls back to the health-based recommendation,
  - the allocation cycle surfaces exactly one authoritative_allocation block.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from config.allocation_config import REGIME_MIN_CONFIDENCE
from core.authoritative_allocation import build_authoritative_allocation
from core.market_regime_adapter import RegimeReadResult, read_market_regime_snapshot
from workflow import allocation_cycle


def _write(d: Path, data: dict) -> Path:
    p = d / "result_snapshot.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


_RECOMMENDATION = {
    "recommended_allocation": {"NovaBotV2": 80, "NovaBotV2Options": 20, "CashReserve": 0, "NovaCryptoBot": 0},
}


class AdapterRealnessTests(unittest.TestCase):
    NOW = datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc)

    def test_real_snapshot_marked_real(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), {"market_regime": "SIDEWAYS", "confidence": 71,
                                 "data_is_real": True, "input_source": "yfinance",
                                 "produced_at": "2026-06-11T10:00:00+00:00",
                                 "fresh_until": "2026-06-11T14:00:00+00:00"})
            r = read_market_regime_snapshot(p, now=self.NOW)
        self.assertTrue(r.data_is_real)
        self.assertTrue(r.regime_is_real)
        self.assertNotIn("regime_unverified", r.warnings)

    def test_unverified_snapshot_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), {"market_regime": "BULL", "confidence": 80,
                                 "data_is_real": False, "input_source": "explicit",
                                 "produced_at": "2026-06-11T10:00:00+00:00",
                                 "fresh_until": "2026-06-11T14:00:00+00:00"})
            r = read_market_regime_snapshot(p, now=self.NOW)
        self.assertFalse(r.data_is_real)
        self.assertFalse(r.regime_is_real)
        self.assertIn("regime_unverified", r.warnings)

    def test_missing_data_is_real_is_unverified(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), {"market_regime": "BULL", "confidence": 80,
                                 "produced_at": "2026-06-11T10:00:00+00:00",
                                 "fresh_until": "2026-06-11T14:00:00+00:00"})
            r = read_market_regime_snapshot(p, now=self.NOW)
        self.assertFalse(r.data_is_real)
        self.assertFalse(r.regime_is_real)

    def test_stale_real_snapshot_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), {"market_regime": "BULL", "confidence": 80,
                                 "data_is_real": True, "input_source": "yfinance",
                                 "produced_at": "2026-06-09T10:00:00+00:00",
                                 "fresh_until": "2026-06-10T14:00:00+00:00"})
            r = read_market_regime_snapshot(p, now=self.NOW)
        self.assertFalse(r.data_is_real)
        self.assertFalse(r.regime_is_real)
        self.assertIn("regime_stale", r.warnings)


class AuthoritativeAllocationTests(unittest.TestCase):
    def _real_regime(self, confidence: int = 71) -> RegimeReadResult:
        return RegimeReadResult(
            market_regime="SIDEWAYS", confidence=confidence, input_source="MarketRegimeBot",
            reason="real", is_fallback=False, data_is_real=True,
        )

    def _unverified_regime(self) -> RegimeReadResult:
        return RegimeReadResult(
            market_regime="BULL", confidence=80, input_source="MarketRegimeBot",
            reason="UNVERIFIED", is_fallback=False, data_is_real=False,
            warnings=("regime_unverified",),
        )

    def test_real_regime_drives_allocation(self):
        out = build_authoritative_allocation(
            recommendation=_RECOMMENDATION,
            regime_result=self._real_regime(),
            regime_allocation={"NovaBotV2": 80, "NovaBotV2Options": 10, "Cash": 10},
        )
        self.assertEqual(out["source"], "regime_aware")
        self.assertEqual(out["allocation"], {"NovaBotV2": 80, "NovaBotV2Options": 10, "Cash": 10})
        self.assertIsNone(out["refused_regime_reason"])
        self.assertTrue(out["regime_is_real"])

    def test_unverified_regime_refused(self):
        out = build_authoritative_allocation(
            recommendation=_RECOMMENDATION,
            regime_result=self._unverified_regime(),
            regime_allocation={"NovaBotV2": 90, "NovaBotV2Options": 10, "Cash": 0},
        )
        self.assertEqual(out["source"], "health_based_regime_refused")
        # falls back to health recommendation, normalised to canonical scheme
        self.assertEqual(out["allocation"], {"NovaBotV2": 80, "NovaBotV2Options": 20, "Cash": 0})
        self.assertIsNotNone(out["refused_regime_reason"])
        self.assertFalse(out["regime_is_real"])

    def test_real_fresh_confidence_0_is_refused(self):
        out = build_authoritative_allocation(
            recommendation=_RECOMMENDATION,
            regime_result=self._real_regime(confidence=0),
            regime_allocation={"NovaBotV2": 70, "NovaBotV2Options": 5, "Cash": 25},
        )
        self.assertEqual(out["source"], "health_based_regime_refused")
        self.assertEqual(out["allocation"], {"NovaBotV2": 80, "NovaBotV2Options": 20, "Cash": 0})
        self.assertIn("regime_low_confidence", out["regime_warnings"])
        self.assertEqual(out["regime_min_confidence"], REGIME_MIN_CONFIDENCE)
        self.assertIn("regime_low_confidence", out["refused_regime_reason"])

    def test_real_fresh_confidence_59_is_refused(self):
        out = build_authoritative_allocation(
            recommendation=_RECOMMENDATION,
            regime_result=self._real_regime(confidence=59),
            regime_allocation={"NovaBotV2": 70, "NovaBotV2Options": 5, "Cash": 25},
        )
        self.assertEqual(out["source"], "health_based_regime_refused")
        self.assertEqual(out["allocation"], {"NovaBotV2": 80, "NovaBotV2Options": 20, "Cash": 0})
        self.assertIn("regime_low_confidence", out["regime_warnings"])
        self.assertEqual(out["regime_min_confidence"], REGIME_MIN_CONFIDENCE)

    def test_real_fresh_confidence_60_is_accepted(self):
        out = build_authoritative_allocation(
            recommendation=_RECOMMENDATION,
            regime_result=self._real_regime(confidence=60),
            regime_allocation={"NovaBotV2": 70, "NovaBotV2Options": 5, "Cash": 25},
        )
        self.assertEqual(out["source"], "regime_aware")
        self.assertEqual(out["allocation"], {"NovaBotV2": 70, "NovaBotV2Options": 5, "Cash": 25})
        self.assertNotIn("regime_low_confidence", out["regime_warnings"])
        self.assertEqual(out["regime_min_confidence"], REGIME_MIN_CONFIDENCE)

    def test_real_fresh_confidence_100_is_accepted(self):
        out = build_authoritative_allocation(
            recommendation=_RECOMMENDATION,
            regime_result=self._real_regime(confidence=100),
            regime_allocation={"NovaBotV2": 50, "NovaBotV2Options": 0, "Cash": 50},
        )
        self.assertEqual(out["source"], "regime_aware")
        self.assertEqual(out["allocation"], {"NovaBotV2": 50, "NovaBotV2Options": 0, "Cash": 50})
        self.assertIn(f"threshold {REGIME_MIN_CONFIDENCE}", out["reason"])

    def test_low_confidence_reason_distinct_from_unverified(self):
        out = build_authoritative_allocation(
            recommendation=_RECOMMENDATION,
            regime_result=self._real_regime(confidence=59),
            regime_allocation={"NovaBotV2": 70, "NovaBotV2Options": 5, "Cash": 25},
        )
        self.assertIn("regime_low_confidence", out["refused_regime_reason"])
        self.assertNotIn("not verified real", out["refused_regime_reason"])

    def test_allocation_totals_100_and_safe(self):
        for regime in (self._real_regime(), self._unverified_regime()):
            out = build_authoritative_allocation(
                recommendation=_RECOMMENDATION, regime_result=regime,
                regime_allocation={"NovaBotV2": 70, "NovaBotV2Options": 5, "Cash": 25},
            )
            self.assertEqual(sum(out["allocation"].values()), 100)
            for flag in ("broker_execution_enabled", "order_placement_enabled",
                         "money_movement_enabled", "live_trading_enabled",
                         "allocation_export_enabled", "writes_to_other_projects_enabled"):
                self.assertFalse(out[flag])


class CycleAuthoritativeTests(unittest.TestCase):
    def test_cycle_surfaces_authoritative_regime_aware_when_real(self):
        with tempfile.TemporaryDirectory() as d:
            regime_path = _write(Path(d), {"market_regime": "BULL", "confidence": 80,
                                           "data_is_real": True, "input_source": "yfinance",
                                           "produced_at": "2099-01-01T10:00:00+00:00",
                                           "fresh_until": "2099-01-01T14:00:00+00:00"})
            result = allocation_cycle.run_allocation_cycle(
                write_snapshot=False, regime_snapshot_path=regime_path,
            )
        auth = result["authoritative_allocation"]
        self.assertEqual(auth["source"], "regime_aware")
        self.assertEqual(auth["allocation"], {"NovaBotV2": 90, "NovaBotV2Options": 10, "Cash": 0})
        self.assertEqual(sum(auth["allocation"].values()), 100)

    def test_cycle_refuses_unverified_regime(self):
        with tempfile.TemporaryDirectory() as d:
            regime_path = _write(Path(d), {"market_regime": "BULL", "confidence": 80,
                                           "data_is_real": False, "input_source": "explicit",
                                           "produced_at": "2099-01-01T10:00:00+00:00",
                                           "fresh_until": "2099-01-01T14:00:00+00:00"})
            result = allocation_cycle.run_allocation_cycle(
                write_snapshot=False, regime_snapshot_path=regime_path,
            )
        auth = result["authoritative_allocation"]
        self.assertEqual(auth["source"], "health_based_regime_refused")
        self.assertIsNotNone(auth["refused_regime_reason"])


if __name__ == "__main__":
    unittest.main()
