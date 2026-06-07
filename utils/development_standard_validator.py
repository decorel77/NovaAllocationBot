"""Reporting-only validator for the NOVA development standard metadata."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping


PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
DEFAULT_STANDARD_PATH: Final[Path] = PROJECT_ROOT / "data" / "system" / "development_standard.json"

REQUIRED_STATUS_VALUES: Final[frozenset[str]] = frozenset(
    {"TODO", "IN_PROGRESS", "SPLIT", "BLOCKED", "DONE", "FUTURE", "ARCHIVED"}
)

REQUIRED_TRUE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "informational_only",
        "sequential_autocycle_enabled",
        "split_large_tasks_required",
        "human_commit_approval_required",
        "human_push_approval_required",
        "savegame_update_required",
        "guardrails_validation_required",
        "task_queue_validation_required",
        "full_test_suite_required",
        "dependency_tracking_required",
        "blocked_task_documentation_required",
    }
)

REQUIRED_FALSE_FIELDS: Final[frozenset[str]] = frozenset(
    {"runtime_effect", "cherry_picking_allowed"}
)

REQUIRED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "task_status_allowed_values",
        "task_id_prefix",
        "max_tasks_per_cycle",
        "authority_documents",
        "standard_deliverable_fields",
        "notes",
    }
) | REQUIRED_TRUE_FIELDS | REQUIRED_FALSE_FIELDS


@dataclass(frozen=True, slots=True)
class DevelopmentStandardReport:
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


def validate_development_standard_data(
    data: Mapping[str, Any],
    *,
    source: str = "<memory>",
) -> DevelopmentStandardReport:
    if not isinstance(data, Mapping):
        return DevelopmentStandardReport(
            valid=False,
            status="ERROR",
            source=source,
            errors=("development standard root must be a JSON object",),
        )

    errors: list[str] = []
    missing = sorted(REQUIRED_KEYS - set(data))
    extra = sorted(set(data) - REQUIRED_KEYS)
    if missing:
        errors.append("missing keys: " + ", ".join(missing))
    if extra:
        errors.append("unexpected keys: " + ", ".join(extra))

    for field in ("schema_version", "task_id_prefix"):
        if not _is_non_empty_string(data.get(field)):
            errors.append(f"{field} must be a non-empty string")

    if data.get("task_id_prefix") != "TASK-":
        errors.append("task_id_prefix must be TASK-")

    max_tasks = data.get("max_tasks_per_cycle")
    if not isinstance(max_tasks, int) or isinstance(max_tasks, bool) or max_tasks < 1:
        errors.append("max_tasks_per_cycle must be a positive integer")

    for field in sorted(REQUIRED_TRUE_FIELDS):
        if data.get(field) is not True:
            errors.append(f"{field} must be true")

    for field in sorted(REQUIRED_FALSE_FIELDS):
        if data.get(field) is not False:
            errors.append(f"{field} must be false")

    statuses = data.get("task_status_allowed_values")
    if not _is_non_empty_string_list(statuses):
        errors.append("task_status_allowed_values must be a non-empty list of strings")
    elif set(statuses) != REQUIRED_STATUS_VALUES:
        errors.append("task_status_allowed_values must match the required status set")

    for field in ("authority_documents", "standard_deliverable_fields", "notes"):
        if not _is_non_empty_string_list(data.get(field)):
            errors.append(f"{field} must be a non-empty list of strings")

    return DevelopmentStandardReport(
        valid=not errors,
        status="OK" if not errors else "ERROR",
        source=source,
        errors=tuple(errors),
    )


def load_and_validate_development_standard(
    path: Path | str = DEFAULT_STANDARD_PATH,
) -> DevelopmentStandardReport:
    standard_path = Path(path)
    try:
        data = json.loads(standard_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return DevelopmentStandardReport(
            valid=False,
            status="ERROR",
            source=str(standard_path),
            errors=("development standard file missing",),
        )
    except json.JSONDecodeError:
        return DevelopmentStandardReport(
            valid=False,
            status="ERROR",
            source=str(standard_path),
            errors=("development standard file is not valid JSON",),
        )
    return validate_development_standard_data(data, source=str(standard_path))


def _format_report(report: DevelopmentStandardReport) -> list[str]:
    lines = [
        f"validation_status={report.status}",
        f"development_standard_path={report.source}",
        "reporting_only=yes",
        "runtime_effect=false",
        "cherry_picking_allowed=false",
        "human_commit_approval_required=true",
        "human_push_approval_required=true",
        "blocked_task_documentation_required=true",
    ]
    if report.errors:
        lines.append("errors:")
        lines.extend(f"- {error}" for error in report.errors)
    return lines


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args:
        print("usage: python -m utils.development_standard_validator", file=sys.stderr)
        return 1

    report = load_and_validate_development_standard()
    print("\n".join(_format_report(report)))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
