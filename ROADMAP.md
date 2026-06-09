# NovaAllocationBot Roadmap

## Status

NovaAllocationBot is a read-only, advisory-only NOVA ecosystem bot for capital and budget allocation recommendations.

Current status: SAFE_DRY_RUN / RECOMMENDATION_ONLY

No live trading, no broker access, no order execution, no money movement, and no downstream allocation export are allowed.

## Phase 1 — Foundation

- Project skeleton
- Read-only architecture
- Initial config and contracts
- Safety boundaries

Status: DONE

## Phase 2 — Snapshot and Health Reading

- Read NovaBotV2 snapshot
- Read NovaBotV2Options snapshot
- Evaluate bot health
- Produce local result snapshot

Status: DONE

## Phase 2.5 — Recommendation Engine

- Generate advisory allocation recommendations
- Maintain current 90% NovaBotV2 / 10% NovaBotV2Options baseline
- Store recommendation reason
- Keep recommendations advisory-only

Status: DONE

## Phase 3 — Market Regime Input

- Read MarketRegimeBot output
- Adjust advisory allocation recommendations based on regime context
- Preserve dry-run and advisory-only behavior

Status: IN PROGRESS

## Phase 4 — NovaBridge Integration

- Expose allocation snapshot to NovaBridge
- Provide safe display-only fields
- No execution authority

Status: TODO

## Phase 5 — Human Approval Workflow

- Define approval rules for future allocation changes
- Require explicit human approval before any downstream export

Status: TODO

## Phase 6 — Controlled Downstream Export

- Future-only phase
- Export approved allocation targets to downstream bots only after safety, approval, audit trail, and rollback mechanisms exist

Status: FUTURE

## Guardrails

- broker_access_allowed=false
- order_execution_allowed=false
- automatic_money_movement_allowed=false
- runtime_effect=false
- commit_requires_human_approval=true
- push_requires_human_approval=true

## Next Safe Task

Continue MarketRegimeBot integration and NovaBridge display integration while preserving advisory-only behavior.
