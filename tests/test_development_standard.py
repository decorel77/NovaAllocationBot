import inspect
import json
import subprocess
import sys
import unittest
from pathlib import Path

from utils import development_standard_validator as validator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STANDARD_PATH = PROJECT_ROOT / "data" / "system" / "development_standard.json"


class DevelopmentStandardTests(unittest.TestCase):
    def _load_standard(self):
        return json.loads(STANDARD_PATH.read_text(encoding="utf-8"))

    def test_valid_development_standard_passes(self):
        report = validator.load_and_validate_development_standard(STANDARD_PATH)

        self.assertTrue(report.valid)
        self.assertEqual(report.status, "OK")
        self.assertEqual(report.errors, ())

    def test_required_fields_are_present(self):
        data = self._load_standard()

        for field in validator.REQUIRED_KEYS:
            with self.subTest(field=field):
                changed = dict(data)
                del changed[field]

                report = validator.validate_development_standard_data(changed)

                self.assertFalse(report.valid)
                self.assertTrue(any(field in error for error in report.errors))

    def test_task_status_set_is_locked(self):
        data = self._load_standard()
        data["task_status_allowed_values"] = ["TODO", "DONE"]

        report = validator.validate_development_standard_data(data)

        self.assertFalse(report.valid)
        self.assertIn("task_status_allowed_values must match the required status set", report.errors)

    def test_approval_gates_remain_true(self):
        data = self._load_standard()

        for field in ("human_commit_approval_required", "human_push_approval_required"):
            with self.subTest(field=field):
                changed = dict(data)
                changed[field] = False

                report = validator.validate_development_standard_data(changed)

                self.assertFalse(report.valid)
                self.assertIn(f"{field} must be true", report.errors)

    def test_no_cherry_picking(self):
        data = self._load_standard()
        data["cherry_picking_allowed"] = True

        report = validator.validate_development_standard_data(data)

        self.assertFalse(report.valid)
        self.assertIn("cherry_picking_allowed must be false", report.errors)

    def test_split_large_tasks_required(self):
        data = self._load_standard()
        data["split_large_tasks_required"] = False

        report = validator.validate_development_standard_data(data)

        self.assertFalse(report.valid)
        self.assertIn("split_large_tasks_required must be true", report.errors)

    def test_blocked_task_documentation_required(self):
        data = self._load_standard()
        data["blocked_task_documentation_required"] = False

        report = validator.validate_development_standard_data(data)

        self.assertFalse(report.valid)
        self.assertIn("blocked_task_documentation_required must be true", report.errors)

    def test_validator_fails_unsafe_modified_data(self):
        data = self._load_standard()
        data["runtime_effect"] = True
        data["human_commit_approval_required"] = False
        data["cherry_picking_allowed"] = True

        report = validator.validate_development_standard_data(data)

        self.assertFalse(report.valid)
        self.assertIn("runtime_effect must be false", report.errors)
        self.assertIn("human_commit_approval_required must be true", report.errors)
        self.assertIn("cherry_picking_allowed must be false", report.errors)

    def test_validator_is_reporting_only(self):
        source = inspect.getsource(validator)

        forbidden_fragments = (
            "ib_insync",
            "placeOrder",
            "connect(",
            "telegram_notify",
            "telegram_command_listener",
            "telegram_queue_consumer",
            "dotenv",
        )
        self.assertFalse(any(fragment in source for fragment in forbidden_fragments))

    def test_cli_entrypoint_reports_current_standard(self):
        result = subprocess.run(
            [sys.executable, "-m", "utils.development_standard_validator"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("validation_status=OK", result.stdout)
        self.assertIn(f"development_standard_path={STANDARD_PATH}", result.stdout)
        self.assertIn("reporting_only=yes", result.stdout)
        self.assertIn("runtime_effect=false", result.stdout)
        self.assertIn("cherry_picking_allowed=false", result.stdout)
        self.assertIn("human_commit_approval_required=true", result.stdout)
        self.assertIn("human_push_approval_required=true", result.stdout)


if __name__ == "__main__":
    unittest.main()
