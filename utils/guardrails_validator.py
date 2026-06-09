"""Reporting-only validator for NovaAllocationBot guardrails metadata."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DEFAULT_GUARDRAILS_PATH: Final[Path] = PROJECT_ROOT / "data" / "system" / "guardrails.json"

FORBIDDEN_FALSE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "runtime_effect",
        "broker_access_allowed",
        "order_execution_allowed",
        "trading_logic_modification_allowed",
        "scheduler_modification_allowed",
        "telegram_execution_allowed",
        "tws_ibkr_modification_allowed",
        "credential_access_allowed",
        "env_file_access_allowed",
        "automatic_money_movement_allowed",
    }
)

ALLOWED_TRUE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "informational_only",
        "runtime_persistence_allowed",
        "report_generation_allowed",
        "schema_creation_allowed",
        "validator_creation_allowed",
        "test_creation_allowed",
        "commit_requires_human_approval",
        "push_requires_human_approval",
    }
)

REQUIRED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "allowed_work",
        "forbidden_work",
        "authority_document",
        "notes",
    }
) | FORBIDDEN_FALSE_FIELDS | ALLOWED_TRUE_FIELDS

REQUIRED_ALLOWED_WORK: Final[frozenset[str]] = frozenset(
    {
        "runtime status JSON",
        "autocycle status JSON",
        "cycle history JSON",
        "reports",
        "schemas",
        "validators",
        "tests",
        "documentation",
        "read-only analytics",
    }
)

REQUIRED_FORBIDDEN_WORK: Final[frozenset[str]] = frozenset(
    {
        "broker imports",
        "IBKR/TWS imports",
        "order placement",
        "live trading",
        "trading decision logic",
        "scheduler activation",
        "Telegram execution",
        "credentials",
        ".env",
        "automatic money movement",
    }
)


@dataclass(frozen=True, slots=True)
class GuardrailsReport:
    valid: bool
    status: str
    source: str
    errors: tuple[str, ...]


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_non_empty_string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
    )


def validate_guardrails_data(data: Mapping[str, Any], *, source: str = "<memory>") -> GuardrailsReport:
    if not isinstance(data, Mapping):
        return GuardrailsReport(
            valid=False, status="ERROR", source=source,
            errors=("guardrails root must be a JSON object",),
        )

    errors: list[str] = []
    missing = sorted(REQUIRED_KEYS - set(data))
    extra = sorted(set(data) - REQUIRED_KEYS)
    if missing:
        errors.append("missing keys: " + ", ".join(missing))
    if extra:
        errors.append("unexpected keys: " + ", ".join(extra))

    for field in ("schema_version", "authority_document"):
        if not _is_non_empty_string(data.get(field)):
            errors.append(f"{field} must be a non-empty string")

    for field in sorted(FORBIDDEN_FALSE_FIELDS):
        if data.get(field) is not False:
            errors.append(f"{field} must be false")

    for field in sorted(ALLOWED_TRUE_FIELDS):
        if data.get(field) is not True:
            errors.append(f"{field} must be true")

    allowed_work = data.get("allowed_work")
    if not _is_non_empty_string_list(allowed_work):
        errors.append("allowed_work must be a non-empty list of strings")
    elif set(allowed_work) != REQUIRED_ALLOWED_WORK:
        errors.append("allowed_work must match the approved safe work set")

    forbidden_work = data.get("forbidden_work")
    if not _is_non_empty_string_list(forbidden_work):
        errors.append("forbidden_work must be a non-empty list of strings")
    elif set(forbidden_work) != REQUIRED_FORBIDDEN_WORK:
        errors.append("forbidden_work must match the permanent forbidden work set")

    if not _is_non_empty_string_list(data.get("notes")):
        errors.append("notes must be a non-empty list of strings")

    return GuardrailsReport(
        valid=not errors,
        status="OK" if not errors else "ERROR",
        source=source,
        errors=tuple(errors),
    )


def load_and_validate_guardrails(path: Path | str = DEFAULT_GUARDRAILS_PATH) -> GuardrailsReport:
    guardrails_path = Path(path)
    try:
        data = json.loads(guardrails_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return GuardrailsReport(
            valid=False, status="ERROR", source=str(guardrails_path),
            errors=("guardrails file missing",),
        )
    except json.JSONDecodeError:
        return GuardrailsReport(
            valid=False, status="ERROR", source=str(guardrails_path),
            errors=("guardrails file is not valid JSON",),
        )
    return validate_guardrails_data(data, source=str(guardrails_path))


def _format_report(report: GuardrailsReport) -> list[str]:
    lines = [
        f"validation_status={report.status}",
        f"guardrails_path={report.source}",
        "reporting_only=yes",
        "runtime_effect=false",
        "broker_access_allowed=false",
        "order_execution_allowed=false",
        "commit_requires_human_approval=true",
        "push_requires_human_approval=true",
    ]
    if report.errors:
        lines.append("errors:")
        lines.extend(f"- {error}" for error in report.errors)
    return lines


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        print("usage: python -m utils.guardrails_validator", file=sys.stderr)
        return 1
    report = load_and_validate_guardrails()
    print("\n".join(_format_report(report)))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
