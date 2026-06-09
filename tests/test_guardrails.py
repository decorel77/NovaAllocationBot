import inspect
import json
import subprocess
import sys
import unittest
from pathlib import Path

from utils import guardrails_validator as validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GUARDRAILS_PATH = PROJECT_ROOT / "data" / "system" / "guardrails.json"


class GuardrailsTests(unittest.TestCase):
    def _load_guardrails(self):
        return json.loads(GUARDRAILS_PATH.read_text(encoding="utf-8"))

    def test_valid_guardrails_file_passes(self):
        report = validator.load_and_validate_guardrails(GUARDRAILS_PATH)
        self.assertTrue(report.valid)
        self.assertEqual(report.status, "OK")
        self.assertEqual(report.errors, ())

    def test_forbidden_fields_remain_false(self):
        data = self._load_guardrails()
        for field in validator.FORBIDDEN_FALSE_FIELDS:
            with self.subTest(field=field):
                changed = dict(data)
                changed[field] = True
                report = validator.validate_guardrails_data(changed)
                self.assertFalse(report.valid)
                self.assertIn(f"{field} must be false", report.errors)

    def test_allowed_safe_fields_remain_true(self):
        data = self._load_guardrails()
        for field in validator.ALLOWED_TRUE_FIELDS:
            with self.subTest(field=field):
                changed = dict(data)
                changed[field] = False
                report = validator.validate_guardrails_data(changed)
                self.assertFalse(report.valid)
                self.assertIn(f"{field} must be true", report.errors)

    def test_runtime_effect_remains_false(self):
        data = self._load_guardrails()
        data["runtime_effect"] = True
        report = validator.validate_guardrails_data(data)
        self.assertFalse(report.valid)
        self.assertIn("runtime_effect must be false", report.errors)

    def test_informational_only_remains_true(self):
        data = self._load_guardrails()
        data["informational_only"] = False
        report = validator.validate_guardrails_data(data)
        self.assertFalse(report.valid)
        self.assertIn("informational_only must be true", report.errors)

    def test_commit_and_push_require_human_approval(self):
        data = self._load_guardrails()
        for field in ("commit_requires_human_approval", "push_requires_human_approval"):
            with self.subTest(field=field):
                changed = dict(data)
                changed[field] = False
                report = validator.validate_guardrails_data(changed)
                self.assertFalse(report.valid)
                self.assertIn(f"{field} must be true", report.errors)

    def test_validator_fails_on_unsafe_modified_data(self):
        data = self._load_guardrails()
        data["broker_access_allowed"] = True
        data["order_execution_allowed"] = True
        data["forbidden_work"] = ["broker imports"]
        report = validator.validate_guardrails_data(data)
        self.assertFalse(report.valid)
        self.assertIn("broker_access_allowed must be false", report.errors)
        self.assertIn("order_execution_allowed must be false", report.errors)
        self.assertIn("forbidden_work must match the permanent forbidden work set", report.errors)

    def test_validator_is_reporting_only(self):
        source = inspect.getsource(validator)
        forbidden_fragments = (
            "ib_insync",
            "placeOrder",
            "connect(",
            "telegram_notify",
            "dotenv",
            "allocation_cycle.run",
            "export_allocation",
        )
        self.assertFalse(any(fragment in source for fragment in forbidden_fragments))

    def test_cli_entrypoint_reports_current_guardrails(self):
        result = subprocess.run(
            [sys.executable, "-m", "utils.guardrails_validator"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("validation_status=OK", result.stdout)
        self.assertIn(f"guardrails_path={GUARDRAILS_PATH}", result.stdout)
        self.assertIn("reporting_only=yes", result.stdout)
        self.assertIn("runtime_effect=false", result.stdout)
        self.assertIn("broker_access_allowed=false", result.stdout)
        self.assertIn("order_execution_allowed=false", result.stdout)
        self.assertIn("commit_requires_human_approval=true", result.stdout)
        self.assertIn("push_requires_human_approval=true", result.stdout)


if __name__ == "__main__":
    unittest.main()
