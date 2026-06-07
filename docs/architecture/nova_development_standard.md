# NOVA Development Standard

This document defines the uniform NOVA way of working for NovaAllocationBot. It
is a repo-owned template that may be copied and adapted to other non-live NOVA
apps.

This standard is informational and inert. It does not enable broker access,
execution logic, scheduler behavior, Telegram runtime behavior, live trading, or
automatic money movement.

## Source Authorities

- `data/system/task_queue.json` is the task authority.
- `docs/handover/savegame.md` is the repo handover and continuity log.
- `docs/architecture/guardrails.md` is the human-readable guardrails authority.
- `data/system/guardrails.json` is the machine-readable guardrails authority.

## Roadmap-Driven Development

Work starts from the roadmap and task queue, not from convenience. Every change
should map to a task entry, a small explicitly requested task, or a documented
blocker.

Tasks must remain scoped to their stated purpose. Unrelated refactors, runtime
workflow changes, and opportunistic cleanup are not part of a standard cycle.

## Sequential Autocycle Rules

Autocycles must read `data/system/task_queue.json`, select the lowest-numbered
safe `TODO` task, and work on that task only.

Cherry-picking easier later tasks is not allowed. If the selected task is too
large or unsafe, the cycle must split or block it instead of jumping ahead.

## Large Task Splitting

Large tasks must be split into clear subtasks using suffixes such as `A`, `B`,
and `C`.

The original task should remain visible until its subtasks are complete or a
blocker is documented. The first safe subtask should be completed immediately
when possible.

## Guardrails Authority

Every cycle must obey `docs/architecture/guardrails.md` and
`data/system/guardrails.json`.

Allowed work includes documentation, schemas, validators, tests, reports,
metadata, runtime status JSON, autocycle status JSON, cycle history JSON, and
read-only analytics.

Forbidden work includes broker imports, IBKR/TWS imports, order placement, live
trading, trading decision logic, scheduler activation, Telegram execution,
credentials, `.env`, and automatic money movement.

## Validators

Schema and policy files should have reporting-only validators when practical.
Validators must load local metadata, validate required fields and safety values,
print reporting output, and avoid broker, scheduler, Telegram runtime, `.env`,
credential, and execution imports.

## Tests

New schemas, validators, reports, and documentation-backed metadata should have
focused tests. Tests should prove valid files pass and unsafe modified data
fails. The full test suite should run before review whenever reasonable.

## Savegame Updates

Each completed, split, or blocked task must update
`docs/handover/savegame.md`. The entry should state what changed, what remains,
which validations ran, and which safety boundaries were preserved.

## Commit And Push Gates

Commits require explicit human approval. Pushes require explicit human approval.
Agents may prepare diffs, run validation, and report status, but must not commit
or push unless the current user request explicitly asks for it.

## Task Dependencies

Tasks that depend on blocked, split, or future work must document that
dependency. A dependent task should not silently assume unfinished runtime,
broker, scheduler, Telegram, or execution behavior exists.

## Blocked Task Policy

If a task requires forbidden work, mark or document it as blocked. The blocker
must identify the safety boundary and the likely files or systems that would be
touched. Do not skip to a later task in the same sequential cycle unless the
user explicitly starts a separate non-sequential task.

## Standard Deliverable Report

A standard NOVA task report should include:

- Selected task.
- Whether the task was completed, split, or blocked.
- Files changed.
- Exact tests and checks run with results.
- Validator output when a validator exists.
- Git status.
- Safety review.
- Commit message recommendation when no commit was requested.
