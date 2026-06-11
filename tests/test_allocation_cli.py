import contextlib
import io
import json
import unittest
from unittest import mock

from tools import allocation_autocycle


class AllocationCliTests(unittest.TestCase):
    def test_cli_once_returns_safe_status(self):
        output = io.StringIO()
        cycle_result = {
            "status": "SAFE_DRY_RUN_DECISION",
            "dry_run": True,
            "health_evaluated": True,
            "regime_allocation": {},
        }
        with mock.patch(
            "tools.allocation_autocycle.run_allocation_cycle",
            return_value=cycle_result,
        ) as run_cycle:
            with contextlib.redirect_stdout(output):
                exit_code = allocation_autocycle.main(["--once"])
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "SAFE_DRY_RUN_DECISION")
        self.assertTrue(payload["dry_run"])
        self.assertTrue(payload["health_evaluated"])
        run_cycle.assert_called_once_with(write_snapshot=True)


if __name__ == "__main__":
    unittest.main()
