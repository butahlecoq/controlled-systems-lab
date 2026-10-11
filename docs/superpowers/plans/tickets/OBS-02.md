# OBS-02: Implement nested and parallel timing with explicit wall and CPU semantics

## Purpose and scope

Goal: supply a lightweight ExecutionContext timing collector for OBS-01. Requirements RUN-02/03/04 and EXP-01/04. Inputs are scoped module/operation spans and worker/task relationships; output is timing data and correctly defined aggregates. Use a monotonic wall clock, optional CPU clock with process/thread scope explicitly stated, and an injectable clock for tests. Keep the disabled collector cheap. Do not enforce platform-specific CPU or peak-memory counters where unavailable, or claim parent/child times are additive.

Requirements: OBS-01, OBS-02, EXP-07. Test oracles: T-R01, T-R02, T-X02, T-OBS02: fake-clock nested and overlapping interval oracle.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] A deterministic fake-clock nested example distinguishes inclusive duration from exclusive wall time computed by child interval union; parent and child inclusive durations are never summed as an end-to-end total.
- [ ] Overlapping parallel spans report run wall latency separately from sum of worker work durations. CPU metrics declare thread/process scope and availability; shared process CPU deltas are not attributed independently to overlapping children.
- [ ] Cross-thread task parentage and span IDs survive concurrent collection without sharing mutable solver workspaces, data races, or double-counting the same span.
- [ ] RAII scope closure records cancelled, failed and resource-limited operations; clock anomalies and incomplete spans are diagnosed rather than producing plausible false totals.
- [ ] Disabled collection retains results/evidence and yields explicitly absent detailed metrics; test overhead as a benchmark measurement, not a fragile wall-clock unit-test threshold.

## Dependencies

Blocked by OBS-01, RUN-01.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
