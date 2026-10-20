# G-NEON — BTC Swing V5 (review gate)

Scope: Railway Preview, Neon project `cool-sea-01964139`. No trading cadence changes.
Engine remains `INTERVAL_SECONDS=300` with UTC slots, advisory lock and journal.
The generic 600-second requirement is explicitly exempted for this market-monitoring system.

## Approved implementation in this branch
- Push Dispatcher polling has a bounded setting `PUSH_POLL_SECONDS` (default 30 s, valid 5–300 s). This is independent of Engine and adds up to 25 s of idle push latency versus the previous 5 s loop.
- Neon Preview transaction pooler is enabled at the service, but Railway connection URLs are **not switched** until advisory-lock compatibility and transaction semantics are regression tested. Do **not** switch Engine to transaction pooling blindly: it holds a session advisory lock.
- Neon Free API returned HTTP 412 `modifying the suspend interval is not permitted on this account` when attempting the requested 300 s auto-suspend. The attempted combined change failed; a separate pooler enable succeeded. `suspend_timeout_seconds` remains 0. Verify behavior in Neon console/support before G-NEON approval.
- Preview Railway currently deploys API from `fix/g6-ops-madrid-timezone`, Engine/Push from `develop/f6-tg-removal`. This audit branch is **not deployed**.

## G-NEON release checklist
- [ ] Gather billable CU-h from the Neon console; daily project consumption API requires eligible paid plan and is not assured on Free.
- [ ] Verify both branches, plan quota, and whether the account auto-suspends despite reported zero timeout.
- [ ] Observe 24 h and seven-day soak; record snapshots, compute idle and session counts, and external metrics.
- [ ] Regress Engine 300 s slots, deduplication, PostgreSQL advisory locks, no real orders, authentication and roles, freshness of market data, push retries and PWA background notifications.
- [ ] Switch connection URLs to pooled only after explicit regression of session locks; leave Engine direct if necessary.
- [ ] Configure an **external** quota notification path (not stored in Neon), with 50/65/75/85/95% warning thresholds proportional to verified quota.
- [ ] Define responses at 85% (diagnose and disable noncritical jobs), 95% (plan upgrade/escalation), and 100% (degraded state, no stale-as-current, notify operator). Never disable safety-related signals silently.
- [ ] Inspect Railway environment drift and pin a release matrix of branches/commits and variable names. Do not log secrets.
- [ ] Test Preview recovery from Neon unavailability and suspended state without disturbing production.
- [ ] Do not promote without evidence for 24 h usage and 7-day stability.

## Regression notes
CI test `tests/test_g_neon_dispatcher.py` asserts 30 s default, range and Engine=300 seconds. The existing repository suite and Preview smoke tests are required for actual acceptance. No live freeze, alerts, orders, or database migrations performed as part of this branch.
