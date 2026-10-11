# REVIEW-05: Deep review of per-worker execution and measured scalability

GitHub: [#95](https://github.com/butahlecoq/controlled-systems-lab/issues/95).

## Purpose and scope

Inspect immutable sharing, per-worker state, cancellation/resource contracts and scaling behavior (RUN-01..04). Scientific limit: measured ranges do not imply polynomial complexity, hard real-time guarantees or scalable enumeration of exponential output.

Requirements: REV-03. Test oracles: T-R01, T-R02, T-TIM01 (proposed).

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Audit all mutable caches, solver workspaces, warm starts, lazy payloads and logging paths for actual ownership/synchronization; run overlap detectors and supported race tooling.
- [ ] Trace total outer/backend/BLAS thread policy and memory enforcement declarations; noninterruptible calls and cancellation latency must match capabilities.
- [ ] Run reproducible dimension/horizon/constraint/representation-size sweeps on both strategies, with equal family/witness output scope, numerical tolerance and verification; retain raw data and hardware.
- [ ] Separate representation/output growth, sparse assembly/factorization, conversions, family queries and instrumentation overhead; report failures and memory limits rather than only best runtimes.
- [ ] Identify architectural bottlenecks/copies and fixes based on measured evidence; require mathematical correctness and partial-evidence behavior to hold under parallel stress.
- [ ] Run after the relevant code and evidence exist. An independent reviewer records commit IDs, file/line findings, reproductions and severity; blocking findings become linked fix tickets and are rechecked before closure. The implementer cannot self-sign off.
- [ ] Review batch job isolation, failure/cancellation propagation, result ordering and per-scenario provenance using TEST-23; distinguish outer concurrency from native backend threads.

## Dependencies

Blocked by [RUN-01 #25](https://github.com/butahlecoq/controlled-systems-lab/issues/25), [OPT-03 #21](https://github.com/butahlecoq/controlled-systems-lab/issues/21), [OPT-08 #22](https://github.com/butahlecoq/controlled-systems-lab/issues/22), [SYN-03 #66](https://github.com/butahlecoq/controlled-systems-lab/issues/66), [SYN-04 #67](https://github.com/butahlecoq/controlled-systems-lab/issues/67), [OBS-02 #60](https://github.com/butahlecoq/controlled-systems-lab/issues/60), [TEST-15 #78](https://github.com/butahlecoq/controlled-systems-lab/issues/78), [TEST-17 #89](https://github.com/butahlecoq/controlled-systems-lab/issues/89), [RUN-02 #80](https://github.com/butahlecoq/controlled-systems-lab/issues/80), [TEST-23 #88](https://github.com/butahlecoq/controlled-systems-lab/issues/88).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Review implemented code at a fixed commit against both repository standards and this specification. Report reproducible findings, severity and guarantee implications. Record the disposition of every finding and independently recheck blocking fixes.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
