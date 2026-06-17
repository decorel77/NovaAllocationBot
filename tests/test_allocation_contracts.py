import dataclasses
import unittest

from core.allocation_contracts import (
    AllocationPlan,
    AllocationRiskState,
    AllocationValidationError,
    BotAllocationTarget,
)
from workflow.allocation_cycle import build_default_allocation_plan, build_dry_run_decision


class AllocationContractTests(unittest.TestCase):
    def test_default_allocation_is_90_10_0_cash(self):
        plan = build_default_allocation_plan()
        allocations = {
            target.bot_name: target.target_percentage for target in plan.targets
        }
        self.assertEqual(allocations["NovaBotV2"], 90.0)
        self.assertEqual(allocations["NovaBotV2Options"], 10.0)
        self.assertEqual(allocations["NovaCryptoBot"], 0.0)
        self.assertEqual(allocations["CashReserve"], 0.0)
        self.assertEqual(plan.total_percentage(), 100.0)

    def test_allocation_total_must_equal_100(self):
        plan = AllocationPlan(
            targets=(
                BotAllocationTarget("NovaBotV2", 90.0),
                BotAllocationTarget("NovaBotV2Options", 5.0),
                BotAllocationTarget("NovaCryptoBot", 0.0),
                BotAllocationTarget("CashReserve", 0.0),
            )
        )
        with self.assertRaises(AllocationValidationError):
            plan.validate()

    def test_invalid_negative_percentages_are_rejected(self):
        target = BotAllocationTarget("NovaBotV2", -1.0)
        with self.assertRaises(AllocationValidationError):
            target.validate()

    def test_unknown_bots_are_rejected_unless_future_supported(self):
        with self.assertRaises(AllocationValidationError):
            BotAllocationTarget("NovaTacticalBot", 0.0).validate()
        BotAllocationTarget(
            "NovaTacticalBot", 0.0, future_supported=True
        ).validate()


class AllocationNoAuthorityContractTests(unittest.TestCase):
    """SAFE-ALLOC-001: prove the public-safe advisory envelope grants no money
    movement, no order execution, and no downstream authority."""

    UNSAFE_FLAGS = (
        "broker_execution_enabled",
        "order_placement_enabled",
        "money_movement_enabled",
        "writes_to_other_projects_enabled",
        "downstream_export_enabled",
    )

    def test_default_risk_state_is_fully_safe(self):
        rs = AllocationRiskState()
        self.assertTrue(rs.dry_run)
        self.assertEqual(rs.status, "SAFE_DRY_RUN")
        for flag in self.UNSAFE_FLAGS:
            self.assertFalse(getattr(rs, flag), flag)
        rs.validate()  # must not raise

    def test_validate_rejects_each_unsafe_flag(self):
        base = AllocationRiskState()
        for flag in self.UNSAFE_FLAGS:
            with self.subTest(flag=flag):
                with self.assertRaises(AllocationValidationError):
                    dataclasses.replace(base, **{flag: True}).validate()

    def test_validate_rejects_non_dry_run(self):
        with self.assertRaises(AllocationValidationError):
            dataclasses.replace(AllocationRiskState(), dry_run=False).validate()

    def test_produced_decision_grants_no_authority(self):
        decision = build_dry_run_decision()
        self.assertTrue(decision.dry_run)
        self.assertEqual(decision.status, "SAFE_DRY_RUN_DECISION")
        for flag in self.UNSAFE_FLAGS:
            self.assertFalse(getattr(decision.risk_state, flag), flag)
        # Recommendation-only, with downstream export explicitly disabled.
        self.assertTrue(decision.recommendation.get("recommendation_only"))
        self.assertFalse(decision.recommendation.get("downstream_export_enabled"))
        # validate() enforces all of the above and must pass.
        decision.validate()


if __name__ == "__main__":
    unittest.main()
