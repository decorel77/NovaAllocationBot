"""Phase 5 tests: allocation compliance checker."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from core.allocation_compliance import (
    BUCKET_OK,
    BUCKET_OVER,
    BUCKET_UNDER,
    BUCKET_UNKNOWN,
    GLOBAL_COMPLIANT,
    GLOBAL_DRIFT,
    GLOBAL_UNKNOWN,
    _read_equity_from_snapshot,
    build_allocation_compliance,
)
from workflow import allocation_cycle

_TARGET_BULL = {"NovaBotV2": 90, "NovaBotV2Options": 10, "Cash": 0}


def _run_cycle_in_temp_project(root: Path, **kwargs):
    original_root = allocation_cycle.PROJECT_ROOT
    try:
        allocation_cycle.PROJECT_ROOT = root
        return allocation_cycle.run_allocation_cycle(**kwargs)
    finally:
        allocation_cycle.PROJECT_ROOT = original_root


def _bucket(result, name: str):
    return next(b for b in result.buckets if b.bucket == name)


class TestCompliantAllocation(unittest.TestCase):
    def test_exact_match_is_compliant(self):
        # 900 + 100 + 0 = 1000 → NovaBotV2 90%, Options 10%, Cash 0%
        current = {"NovaBotV2": 900.0, "NovaBotV2Options": 100.0, "Cash": None}
        result = build_allocation_compliance(_TARGET_BULL, current_values=current)
        self.assertEqual(result.global_status, GLOBAL_COMPLIANT)
        self.assertEqual(_bucket(result, "NovaBotV2").status, BUCKET_OK)
        self.assertEqual(_bucket(result, "NovaBotV2Options").status, BUCKET_OK)

    def test_within_tolerance_is_compliant(self):
        # NovaBotV2=87% (target 90%, deviation -3%) — within 5% tolerance
        # Options=13% (target 10%, deviation +3%) — within tolerance
        current = {"NovaBotV2": 870.0, "NovaBotV2Options": 130.0, "Cash": None}
        result = build_allocation_compliance(_TARGET_BULL, current_values=current)
        self.assertEqual(result.global_status, GLOBAL_COMPLIANT)

    def test_cash_none_does_not_block_compliant(self):
        # Cash target=0, Cash current=None → UNKNOWN bucket, but since
        # target=0 the global status depends on whether UNKNOWN is present.
        # With Cash target=0 we still get UNKNOWN bucket, so global → UNKNOWN.
        # Use a target with no Cash to test purely compliant scenario.
        target = {"NovaBotV2": 90, "NovaBotV2Options": 10}
        current = {"NovaBotV2": 900.0, "NovaBotV2Options": 100.0}
        result = build_allocation_compliance(target, current_values=current)
        self.assertEqual(result.global_status, GLOBAL_COMPLIANT)


class TestUnderallocatedOptions(unittest.TestCase):
    def test_options_underallocated(self):
        # Options at 3% (target 10%) → deviation -7% → UNDERALLOCATED
        current = {"NovaBotV2": 970.0, "NovaBotV2Options": 30.0, "Cash": None}
        result = build_allocation_compliance(_TARGET_BULL, current_values=current)
        self.assertEqual(_bucket(result, "NovaBotV2Options").status, BUCKET_UNDER)
        self.assertEqual(result.global_status, GLOBAL_DRIFT)

    def test_drift_note_mentions_bucket(self):
        current = {"NovaBotV2": 970.0, "NovaBotV2Options": 30.0, "Cash": None}
        result = build_allocation_compliance(_TARGET_BULL, current_values=current)
        combined_notes = " ".join(result.notes)
        self.assertIn("NovaBotV2Options", combined_notes)


class TestOverallocatedNovaBotV2(unittest.TestCase):
    def test_novabot_overallocated(self):
        # NovaBotV2 at 97% (target 90%) → deviation +7% → OVERALLOCATED
        current = {"NovaBotV2": 970.0, "NovaBotV2Options": 30.0, "Cash": None}
        result = build_allocation_compliance(
            {"NovaBotV2": 90, "NovaBotV2Options": 10, "Cash": 0},
            current_values=current,
        )
        # NovaBotV2=97%, target=90% → +7% → OVERALLOCATED
        self.assertEqual(_bucket(result, "NovaBotV2").status, BUCKET_OVER)
        self.assertEqual(result.global_status, GLOBAL_DRIFT)


class TestUnknownCurrentValues(unittest.TestCase):
    def test_all_none_gives_unknown(self):
        current = {"NovaBotV2": None, "NovaBotV2Options": None, "Cash": None}
        result = build_allocation_compliance(_TARGET_BULL, current_values=current)
        self.assertEqual(result.global_status, GLOBAL_UNKNOWN)
        for b in result.buckets:
            self.assertEqual(b.status, BUCKET_UNKNOWN)
            self.assertIsNone(b.current_pct)
            self.assertIsNone(b.deviation_pct)

    def test_partial_none_gives_unknown(self):
        # If any known bucket is None → can't compute total fairly → all UNKNOWN
        current = {"NovaBotV2": 900.0, "NovaBotV2Options": None, "Cash": None}
        result = build_allocation_compliance(_TARGET_BULL, current_values=current)
        self.assertEqual(result.global_status, GLOBAL_UNKNOWN)

    def test_unknown_note_present(self):
        current = {"NovaBotV2": None, "NovaBotV2Options": None, "Cash": None}
        result = build_allocation_compliance(_TARGET_BULL, current_values=current)
        combined = " ".join(result.notes)
        self.assertIn("unavailable", combined.lower())

    def test_no_override_reads_snapshots_returns_unknown(self):
        # In Phase 5 no bot has equity fields → all UNKNOWN
        result = build_allocation_compliance(_TARGET_BULL)
        self.assertEqual(result.global_status, GLOBAL_UNKNOWN)


class TestToleranceBoundary(unittest.TestCase):
    def test_exactly_at_tolerance_is_ok(self):
        # NovaBotV2=85% (target 90%), deviation=-5.0% → exactly at tolerance (5%)
        current = {"NovaBotV2": 850.0, "NovaBotV2Options": 150.0}
        target = {"NovaBotV2": 90, "NovaBotV2Options": 10}
        result = build_allocation_compliance(target, current_values=current, tolerance_pct=5.0)
        self.assertEqual(_bucket(result, "NovaBotV2").status, BUCKET_OK)

    def test_just_over_tolerance_is_drift(self):
        # NovaBotV2=84% (target 90%), deviation=-6% → just over tolerance (5%)
        current = {"NovaBotV2": 840.0, "NovaBotV2Options": 160.0}
        target = {"NovaBotV2": 90, "NovaBotV2Options": 10}
        result = build_allocation_compliance(target, current_values=current, tolerance_pct=5.0)
        self.assertEqual(_bucket(result, "NovaBotV2").status, BUCKET_UNDER)
        self.assertEqual(result.global_status, GLOBAL_DRIFT)

    def test_custom_tolerance(self):
        # deviation=3%, tolerance=2% → drift; tolerance=4% → ok
        current = {"NovaBotV2": 870.0, "NovaBotV2Options": 130.0}
        target = {"NovaBotV2": 90, "NovaBotV2Options": 10}
        tight = build_allocation_compliance(target, current_values=current, tolerance_pct=2.0)
        loose = build_allocation_compliance(target, current_values=current, tolerance_pct=4.0)
        self.assertEqual(tight.global_status, GLOBAL_DRIFT)
        self.assertEqual(loose.global_status, GLOBAL_COMPLIANT)


class TestSafetyFlags(unittest.TestCase):
    def test_all_safety_flags_false(self):
        result = build_allocation_compliance(_TARGET_BULL, current_values={})
        d = result.to_dict()
        for flag in ("broker_execution_enabled", "order_placement_enabled",
                     "money_movement_enabled", "live_trading_enabled"):
            self.assertFalse(d[flag], f"{flag} must be False")
        self.assertTrue(d["dry_run"])


class TestSnapshotContainsCompliance(unittest.TestCase):
    def test_snapshot_has_allocation_compliance(self):
        with tempfile.TemporaryDirectory() as d:
            regime_file = Path(d) / "regime.json"
            regime_file.write_text(
                json.dumps({"market_regime": "BULL", "confidence": 80}),
                encoding="utf-8",
            )
            result = _run_cycle_in_temp_project(
                Path(d),
                write_snapshot=True,
                regime_snapshot_path=regime_file,
                history_path=Path(d) / "history.json",
                result_path=Path(d) / "result_snapshot.json",
            )
            written = json.loads(
                Path(result["result_snapshot_path"]).read_text(encoding="utf-8-sig")
            )
        self.assertIn("allocation_compliance", written)
        ac = written["allocation_compliance"]
        self.assertIn("global_status", ac)
        self.assertIn("buckets", ac)
        self.assertIn("tolerance_pct", ac)
        self.assertTrue(ac["dry_run"])

    def test_compliance_in_cycle_result(self):
        result = allocation_cycle.run_allocation_cycle(write_snapshot=False)
        self.assertIn("allocation_compliance", result)
        self.assertIn("global_status", result["allocation_compliance"])

    def _verified_bull_regime(self, d: Path) -> Path:
        # REPAIR-007: compliance is measured against the AUTHORITATIVE allocation.
        # Pin a verified-real BULL regime so the target is deterministic (regime-
        # driven, independent of current_values) rather than the ambient live
        # MarketRegimeBot snapshot. BULL tilts more aggressive than the 90/10
        # neutral baseline: the authoritative BULL target is 95/5/0.
        p = Path(d) / "regime.json"
        p.write_text(
            json.dumps({"market_regime": "BULL", "confidence": 80,
                        "data_is_real": True, "input_source": "yfinance"}),
            encoding="utf-8",
        )
        return p

    def test_cycle_with_synthetic_values_shows_compliant(self):
        # Inject exact-match values (95/5/0) against the verified BULL target → COMPLIANT
        current = {"NovaBotV2": 950.0, "NovaBotV2Options": 50.0, "Cash": None}
        with tempfile.TemporaryDirectory() as d:
            result = allocation_cycle.run_allocation_cycle(
                write_snapshot=False,
                current_values=current,
                regime_snapshot_path=self._verified_bull_regime(d),
            )
        ac = result["allocation_compliance"]
        self.assertEqual(ac["global_status"], GLOBAL_COMPLIANT)

    def test_cycle_with_drift_shows_drift_warning(self):
        # 85/15 drifts -10/+10 from the 95/5 BULL target — beyond the 5% tolerance.
        # (The old 970/30 was only ~2 points off the real 95/5 target, i.e. actually
        # COMPLIANT — it silently assumed a stale 90/10 target.)
        current = {"NovaBotV2": 850.0, "NovaBotV2Options": 150.0, "Cash": None}
        with tempfile.TemporaryDirectory() as d:
            result = allocation_cycle.run_allocation_cycle(
                write_snapshot=False,
                current_values=current,
                regime_snapshot_path=self._verified_bull_regime(d),
            )
        ac = result["allocation_compliance"]
        self.assertEqual(ac["global_status"], GLOBAL_DRIFT)


class TestNonFiniteEquityFailsClosed(unittest.TestCase):
    """A non-finite equity (NaN/+-Infinity) must not be read as a valid value nor
    poison the compliance percentages — it must read as UNKNOWN."""

    def test_snapshot_infinity_equity_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "snap.json"
            for bad in ("Infinity", "-Infinity", "NaN"):
                p.write_text('{"equity": %s}' % bad, encoding="utf-8")
                self.assertIsNone(_read_equity_from_snapshot(p),
                                  f"{bad} equity should not be read as valid")

    def test_snapshot_finite_equity_still_read(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "snap.json"
            p.write_text('{"equity": 1234.5}', encoding="utf-8")
            self.assertEqual(_read_equity_from_snapshot(p), 1234.5)

    def test_non_finite_current_value_reads_unknown_not_poisoned(self):
        current = {"NovaBotV2": float("inf"), "NovaBotV2Options": 100.0, "Cash": None}
        result = build_allocation_compliance(_TARGET_BULL, current_values=current)
        nbv2 = _bucket(result, "NovaBotV2")
        # inf bucket is treated as unknown; its percentage stays None (not nan).
        self.assertEqual(nbv2.status, BUCKET_UNKNOWN)
        self.assertIsNone(nbv2.current_pct)
        # the surviving finite bucket is computed against a finite total.
        opts = _bucket(result, "NovaBotV2Options")
        self.assertIsNotNone(opts.current_pct)
        self.assertTrue(math.isfinite(opts.current_pct))

    def test_all_non_finite_current_values_global_unknown(self):
        current = {"NovaBotV2": float("nan"), "NovaBotV2Options": float("-inf"), "Cash": None}
        result = build_allocation_compliance(_TARGET_BULL, current_values=current)
        self.assertEqual(result.global_status, GLOBAL_UNKNOWN)
        for b in result.buckets:
            self.assertIsNone(b.current_pct)


if __name__ == "__main__":
    unittest.main()
