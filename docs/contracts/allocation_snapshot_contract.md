# NovaAllocationBot — Allocation Snapshot Contract

**Contract version:** 2.0
**Effective from:** Phase 4  
**Status:** Active

---

## Purpose

This contract defines the structure and validation rules for the
`regime_allocation` block written by NovaAllocationBot to its own
`data/system/result_snapshot.json`.

Downstream consumers (e.g. NovaBotV2 reading allocation read-only) MUST
validate against this contract before using the values.

---

## Required fields

### Top-level canonical envelope

| Field | Type | Description |
|---|---|---|
| `producer_id` | string | Must be `"NovaAllocationBot"`. |
| `schema_version` | string | Must be `"allocation_result.v2"`. |
| `produced_at` | string | UTC ISO-8601 timestamp for snapshot production. |
| `fresh_until` | string | UTC ISO-8601 timestamp after `produced_at`; default horizon is 24 hours. |
| `data_is_real` | bool | `true` only when all consumed inputs are real and fresh enough. |
| `data_is_real_reasons` | array of string | Empty when `data_is_real=true`; otherwise explains why the envelope is not real. |
| `input_warnings` | array of string | Preserves diagnostics from consumed bot/regime inputs. |

Existing top-level decision fields remain present for backwards compatibility.

### `regime_allocation` block

| Field | Type | Description |
|---|---|---|
| `allocation_version` | string | Contract version (semver). Must equal current contract version. |
| `project` | string | Must be `"NovaAllocationBot"`. |
| `status` | string | Must be `"SAFE_DRY_RUN_ALLOCATION"`. |
| `dry_run` | bool | Must be `true`. |
| `input_source` | string | `"MarketRegimeBot"` or `"fallback"`. |
| `market_regime` | string | One of `BULL`, `SIDEWAYS`, `BEAR`, `HIGH_VOLATILITY`, `UNKNOWN`. |
| `confidence` | int | 0–100. |
| `recommended_allocation` | object | Keys: `NovaBotV2`, `NovaBotV2Options`, `Cash`. Values must sum to 100. |
| `reason` | string | Human-readable explanation of the allocation decision. |
| `broker_execution_enabled` | bool | Must be `false`. |
| `order_placement_enabled` | bool | Must be `false`. |
| `money_movement_enabled` | bool | Must be `false`. |
| `live_trading_enabled` | bool | Must be `false`. |
| `allocation_export_enabled` | bool | Must be `false`. |
| `writes_to_other_projects_enabled` | bool | Must be `false`. |
| `warnings` | array of string | May be empty. Non-empty means input was degraded. |

---

## Allocation rules

| Regime | NovaBotV2 | NovaBotV2Options | Cash |
|---|---|---|---|
| `BULL` | 90 | 10 | 0 |
| `SIDEWAYS` | 80 | 10 | 10 |
| `BEAR` | 70 | 5 | 25 |
| `HIGH_VOLATILITY` | 50 | 0 | 50 |
| fallback / unknown | 90 | 10 | 0 |

Allocation percentages must always sum to exactly 100.

---

## Safety invariants

- `dry_run` is always `true`; no live execution path exists.
- All broker/order/trading/money flags are always `false`.
- NovaAllocationBot never writes to other project directories.
- This snapshot is read-only input for consumers; consumers must not write
  back to this file.

---

## Backwards compatibility rules

1. **Minor additions** (new optional fields): consumers MUST ignore unknown
   fields. Adding a field is non-breaking.
2. **Field removals or type changes**: require a major version bump
   (`1.0` → `2.0`). Consumers MUST reject snapshots whose
   `allocation_version` major component differs from their expected major.
3. **Allocation rule changes** (different percentages for existing regimes):
   require a minor version bump (`1.0` → `1.1`).
4. **New regime values**: non-breaking; consumers not recognising a regime
   MUST fall back to their own safe default rather than erroring.

---

## History

| Version | Change |
|---|---|
| 1.0 | Initial contract (Phase 4). |
| 2.0 | Added top-level canonical envelope fields for `allocation_result.v2`. |
