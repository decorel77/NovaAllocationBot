# NovaAllocationBot Savegame

## 2026-06-07 — Guardrails Authority Standard Applied

Added central guardrails authority standard (adapted from NovaBotV2Options).
All guardrail tests pass. Validator confirms all safety fields correct.

### Files created

| File | Description |
|---|---|
| `docs/architecture/guardrails.md` | Central guardrails authority document |
| `data/system/guardrails.json` | Machine-readable policy — all safety fields locked |
| `utils/__init__.py` | utils package marker |
| `utils/guardrails_validator.py` | Offline reporting-only validator |
| `tests/test_guardrails.py` | 9 guardrails tests (all pass) |

### Safety confirmation

No broker, trading, Telegram runtime, scheduler, credential, or execution
changes. Allocation recommendations remain advisory only. All safety locks
preserved. `runtime_effect=false`, `automatic_money_movement_allowed=false`,
`commit_requires_human_approval=true`.

---

## 2026-06-06 - Phase 2.5 Recommendation-Only Engine Completed

NovaAllocationBot now generates advisory allocation recommendations from the
read-only health scores collected for NovaBotV2 and NovaBotV2Options.

Completed in Phase 2.5:
- Created `core/recommendation_engine.py`.
- Added deterministic recommendations for healthy/healthy, healthy/warning,
  healthy/unknown, and warning/healthy active bot combinations.
- Extended the local dry-run result snapshot with recommendation metadata.
- Kept current allocation fixed at 90% NovaBotV2, 10% NovaBotV2Options, 0%
  NovaCryptoBot, and 0% CashReserve.
- Confirmed recommendations always total 100%.

Explicit non-goals still enforced:
- No live trading.
- No broker execution.
- No order placement.
- No money movement.
- No downstream allocation export.
- No writes to NovaBotV2, NovaBotV2Options, NovaBridge, or future bot repos.
- No Phase 3, 4, 5, 6, or 7 implementation.

Next planned phases remain tracked in `data/system/task_queue.json`.

---

## 2026-06-07 — NOVA Development Standard Applied

Added NOVA development standard documentation, schema, validator, and tests
(adapted from NovaBotV2Options). Validator confirms status=OK. All new tests pass.
No code, broker, scheduler, Telegram, credentials, or execution changes.

### Files created

| File | Description |
|---|---|
| docs/architecture/nova_development_standard.md | NOVA development standard documentation |
| data/system/development_standard.json | Machine-readable development standard schema |
| utils/development_standard_validator.py | Reporting-only validator |
| 	ests/test_development_standard.py | 10 tests covering valid, invalid, and safety checks |

### Validations run

- python -m unittest tests.test_development_standard — OK
- python -m utils.development_standard_validator — validation_status=OK
- python -m json.tool data\system\development_standard.json — OK
- python -m json.tool data\system\task_queue.json — OK
- python -m unittest discover tests — all tests pass
- git diff --check — no whitespace errors

### Safety review

- No broker imports. No IBKR/TWS. No order placement. No live trading.
- No scheduler activation. No Telegram execution. No .env. No credentials.
- Validator is reporting-only. No runtime effect. No automatic money movement.

### Commit/push status

No commit. No push. Awaiting explicit human approval.
