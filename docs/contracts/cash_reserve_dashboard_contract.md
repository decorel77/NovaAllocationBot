# NovaAllocationBot — Cash Reserve Dashboard Contract

Status: contract/design document (docs-only); recommendation-only
Scope: define the public-safe cash-reserve fields the dashboard may show — recommendation, variance, reason, UNKNOWN states — without implying a compliance claim or any automatic action
Implementation status: this document changes no percentage value, moves no money, wires no dashboard, reads no real allocation history, and touches no runtime data. It is a contract; it carries no capital authority.

Card: ALLOC-002 (§4 EPIC-06) from the NovaGPT Vault roadmap. Companion to `allocation_snapshot_contract.md` and the producer-side cash-reserve source contract (`ALLOC-DQ-001` in the NovaGPT Vault).

## Principle

The dashboard shows a **recommendation**, never an instruction. Nothing in this contract enables money movement, position sizing, or automatic capital steering — those remain HUMAN_GATED (ALLOC-006/007).

## Public-safe fields (allowlist / deny-by-default)

| Field | Meaning | Notes |
|---|---|---|
| `recommended_cash_reserve_pct` | the recommended cash-reserve percentage | **recommendation only**; not an applied/enforced value |
| `current_cash_reserve_pct` | observed current reserve (if provided, public-safe) | display only |
| `variance` | recommended − current (or `UNKNOWN`) | descriptive gap, not an action |
| `reason` | short, machine-stable rationale | no instruction language |
| `recommendation_only` | constant `true` | the contract's truth label |
| `produced_at` / `fresh_until` | provenance/freshness | fail-closed when absent |
| `status` | `OK` / `STALE` / `INSUFFICIENT` / `UNKNOWN` | see below |

## Forbidden fields (deny-by-default)

Never include: account numbers, real balances/positions, order data, broker ids, capital totals, secrets, file paths, or any `*_apply`/`*_enforce`/execution flag. Anything not on the allowlist is dropped.

## States (fail closed)

| Status | When | Rule |
|---|---|---|
| `OK` | recommendation present, fresh, provenance complete | only when all hold |
| `STALE` | past `fresh_until` / old `produced_at` | old ⇒ STALE, never OK |
| `INSUFFICIENT` | not enough basis to recommend | show INSUFFICIENT, withhold a number |
| `UNKNOWN` | missing/malformed/unreadable | **absence ⇒ UNKNOWN, never a fabricated reserve** |

## Hard boundaries

1. **No money movement / no capital steering.** Display only; applying a reserve is ALLOC-006/007 (HUMAN_GATED).
2. **No percentage change.** This contract does not set or modify any allocation/risk percentage.
3. **Recommendation-only label is constant.** `recommendation_only = true` always.
4. **No real wiring here.** Real source wiring is HUMAN_GATED; this is the contract only.

## Validation (docs-only / synthetic)

- Totals/unknown/provenance cases: complete recommendation ⇒ `OK`; missing provenance ⇒ `UNKNOWN`; stale ⇒ `STALE`.
- Leak scan: no forbidden field appears even on malformed input.
- No real `allocation_history.json` is read; no behaviour is exercised.

## Safety confirmation

This contract was written from the existing allocation contract docs and the producer-side cash-reserve contract only. It changed no percentage, moved no money, read/modified no runtime/generated data (`data/system/allocation_history.json` was left untouched and unstaged), and touched no `.env`/secret, broker, or order path. It is recommendation-only; this document grants no authority and lifts no gate.
