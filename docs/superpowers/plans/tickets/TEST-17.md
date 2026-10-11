# TEST-17: Verify detailed submodule timing tables and accounting

## Purpose and scope

Test mandatory user-requested observability: detailed per-submodule timing across both strategies, workers and final reports (EXP-01/04 plus proposed T-TIM01). This extends earlier summary-only docs. Limit: synthetic-clock correctness does not establish speed or hard real-time performance.

Requirements: REV-02. Test oracles: T-X02, T-R02, T-TIM01 (proposed).

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Inject a deterministic monotonic fake clock; verify setup/validation, forward propagation, intersections, hull reduction, conversion, terminal optimization, direct assembly, backward recovery, backend calls, first/additional witness, independent verification, projection and export rows where applicable.
- [ ] Nested spans report inclusive/exclusive duration, call count and strategy/run/worker/module identity; sums use documented nesting rules and cannot double-count parent and child into end-to-end time.
- [ ] Overlapping worker spans distinguish elapsed wall time from aggregate worker time; a missing/unimplemented phase is explicitly not-applicable rather than invented zero.
- [ ] Exceptions, cancellation, resource limits and early unsupported results close spans and preserve partial timing rows; disabled tracing uses documented behavior.
- [ ] Versioned raw timing records render detailed machine-readable and human-readable tables with time units, cold/warm state, backend versions and thread settings; actual profiling smoke tests use no fragile time thresholds.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by OBS-02, OBS-03, OBS-04, OBS-05.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
