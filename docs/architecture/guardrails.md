# NovaAllocationBot Guardrails Authority

This document is the central repo-owned safety authority for future Codex,
Claude, and human-assisted development prompts in NovaAllocationBot.

The guardrails are informational and policy-oriented. They do not enable broker
access, order execution, scheduler activation, Telegram execution, live trading,
or automatic money movement.

NovaAllocationBot is an advisory-only capital allocation recommendation engine
for the NOVA ecosystem. It reads portfolio snapshots and health data, and
produces allocation recommendations. It is not a trading bot, broker client,
execution engine, or scheduler authority. Recommendations are advisory only and
are never automatically acted upon.

## Permanent Forbidden Areas

The following areas are permanently forbidden unless a human explicitly opens a
separate reviewed implementation task with written approval:

- Broker imports or broker connections.
- IBKR or TWS imports, configuration, or integration changes.
- Order placement or order routing.
- Live trading behavior.
- Trading decision logic that affects real or simulated execution.
- Scheduler activation or scheduler behavior changes.
- Telegram execution or Telegram runtime behavior changes.
- Credential access, credential changes, or credential discovery.
- `.env` access or `.env` changes.
- Automatic money movement.

## Allowed Safe Work

The following work is allowed when it remains inert, reporting-only, and covered
by validation where appropriate:

- Runtime status JSON.
- Autocycle status JSON.
- Cycle history JSON.
- Reports.
- Schemas.
- Validators.
- Tests.
- Documentation.
- Read-only analytics.

Allowed work may define file formats, validate metadata, or write explicitly safe
status files only when the implementation is scoped to allocation reporting and
does not alter scheduler, execution, broker, Telegram, or trading logic behavior.

## Human Approval Requirements

Commits and pushes require human approval. Autonomous agents may prepare diffs,
run tests, and report status, but must not commit or push unless the current user
message explicitly requests it.

Any future change that could affect broker access, order execution, scheduler
behavior, Telegram runtime behavior, TWS/IBKR integration, credentials, `.env`,
live trading, or money movement requires separate human review and approval.

## Broker, Order, And Trading Restrictions

NovaAllocationBot must not add broker imports, broker calls, order placement,
order mutation, order cancellation, or live-trading paths as part of
documentation, schema, validator, test, reporting, metadata, or read-only
analytics work.

Allocation recommendation logic must not be connected to any execution path.
Allocation outputs are advisory signals only and must never automatically
influence order placement, capital movement, or live trading decisions.

## Allocation Advisory Boundary

All allocation recommendations are:
- Informational only.
- Not binding on any trading system.
- Not capable of initiating orders, moving capital, or modifying positions.
- Requiring explicit human review and approval before any action is taken.

The downstream allocation export capability (planned Phase 7) may only be
implemented after a separate human-reviewed implementation task with explicit
written approval. Export must never be triggered automatically.

## Runtime Persistence Policy

Runtime persistence is allowed only for inert status metadata such as runtime
status JSON, autocycle status JSON, cycle history JSON, reports, schemas,
validators, tests, and documentation.

Runtime persistence must not activate a scheduler, create a background service,
change Telegram runtime behavior, connect to a broker, access credentials, read
or write `.env`, place orders, alter trading decisions, or move money.

When there is uncertainty, stop before implementation and document the blocker.
