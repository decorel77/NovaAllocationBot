import unittest

from core.allocation_contracts import (
    AllocationPlan,
    AllocationValidationError,
    BotAllocationTarget,
)
from workflow.allocation_cycle import build_default_allocation_plan


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


if __name__ == "__main__":
    unittest.main()
