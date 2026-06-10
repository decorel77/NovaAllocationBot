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
from pathlib import Path

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
    def test_real_snapshot_marked_real(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), {"market_regime": "SIDEWAYS", "confidence": 71,
                                 "data_is_real": True, "input_source": "yfinance"})
            r = read_market_regime_snapshot(p)
        self.assertTrue(r.data_is_real)
        self.assertTrue(r.regime_is_real)
        self.assertNotIn("regime_unverified", r.warnings)

    def test_unverified_snapshot_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), {"market_regime": "BULL", "confidence": 80,
                                 "data_is_real": False, "input_source": "explicit"})
            r = read_market_regime_snapshot(p)
        self.assertFalse(r.data_is_real)
        self.assertFalse(r.regime_is_real)
        self.assertIn("regime_unverified", r.warnings)

    def test_missing_data_is_real_is_unverified(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(Path(d), {"market_regime": "BULL", "confidence": 80})
            r = read_market_regime_snapshot(p)
        self.assertFalse(r.data_is_real)
        self.assertFalse(r.regime_is_real)


class AuthoritativeAllocationTests(unittest.TestCase):
    def _real_regime(self) -> RegimeReadResult:
        return RegimeReadResult(
            market_regime="SIDEWAYS", confidence=71, input_source="MarketRegimeBot",
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
                                           "data_is_real": True, "input_source": "yfinance"})
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
                                           "data_is_real": False, "input_source": "explicit"})
            result = allocation_cycle.run_allocation_cycle(
                write_snapshot=False, regime_snapshot_path=regime_path,
            )
        auth = result["authoritative_allocation"]
        self.assertEqual(auth["source"], "health_based_regime_refused")
        self.assertIsNotNone(auth["refused_regime_reason"])


if __name__ == "__main__":
    unittest.main()
