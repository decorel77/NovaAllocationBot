# Current State

## NovaAllocationBot Phase 2.5 + Analytics Phase — 2026-06-09

**ALLOC-ANALYTICS-002 (MASTER-028) DONE:**
- `core/allocation_regime_analysis.py` — regime-based evaluation of allocation recommendations. Groups history by BULL/BEAR/NEUTRAL, computes avg splits per regime, outputs `data/reports/allocation_regime_analysis.md`.

---

## NovaAllocationBot Phase 2.5 - 2026-06-06

Status: PHASE_2_5_COMPLETE / SAFE_DRY_RUN / RECOMMENDATION_ONLY

NovaAllocationBot is a separate NOVA ecosystem project for capital and budget
allocation decisions. It currently has no live trading capability, no broker
execution, no order placement, no money movement, no downstream export, and no
writes to other bot repositories.

Phase 2.5 completed:
- Added `core/recommendation_engine.py` for recommendation-only allocation guidance.
- Uses existing health scores, health statuses, and warnings from Phase 2.
- Stores `current_allocation`, `recommended_allocation`, and
  `recommendation_reason` in the local result snapshot.
- Guarantees recommended allocation totals 100%.
- Keeps current allocation fixed at 90/10/0/0.

Current allocation behavior:
- NovaBotV2: 90%
- NovaBotV2Options: 10%
- NovaCryptoBot: 0%
- CashReserve: 0%
- Allocation percentages remain fixed in Phase 2.5.
- Recommendations remain advisory only.

Safety lock:
- This bot does not trade.
- Broker execution is disabled.
- Order placement is disabled.
- Money movement is disabled.
- Cross-repo writes are disabled.
- Downstream allocation export is disabled.
- NovaBridge orchestration is not implemented in this phase.
- Phase 3, 4, 5, 6, and 7 are not implemented.

---

## Guardrails Authority (added 2026-06-07)

Central guardrails authority standard applied to NovaAllocationBot.

| Artifact | Path |
|---|---|
| Guardrails document | `docs/architecture/guardrails.md` |
| Guardrails policy | `data/system/guardrails.json` |
| Guardrails validator | `utils/guardrails_validator.py` |
| Guardrails tests | `tests/test_guardrails.py` |

All guardrails fields confirmed: `runtime_effect=false`, `broker_access_allowed=false`,
`order_execution_allowed=false`, `automatic_money_movement_allowed=false`,
`commit_requires_human_approval=true`, `push_requires_human_approval=true`.

Future prompts may reference `docs/architecture/guardrails.md` and
`data/system/guardrails.json` as the safety authority for this repo.
