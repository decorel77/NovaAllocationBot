import contextlib
import io
import json
import unittest

from tools import allocation_autocycle


class AllocationCliTests(unittest.TestCase):
    def test_cli_once_returns_safe_status(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = allocation_autocycle.main(["--once"])
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "SAFE_DRY_RUN_DECISION")
        self.assertTrue(payload["dry_run"])
        self.assertTrue(payload["health_evaluated"])


if __name__ == "__main__":
    unittest.main()
