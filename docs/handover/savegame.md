# NovaAllocationBot Savegame

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
