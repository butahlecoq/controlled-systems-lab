# TEST-15: Expand execution isolation, cancellation and resource-policy tests

## Purpose and scope

Test immutable inputs, exclusive mutable worker state and partial-result/resource behavior (RUN-02/03/04). Limit: concurrency tools support listed platforms and budgets are only enforced where adapters declare enforcement.

Requirements: REV-02. Test oracles: T-R01, T-R02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Concurrent fixed analytic runs use distinct workspace/warm-start/cache ownership; a barrier-controlled detecting backend fails on cross-worker borrowing.
- [ ] Sequential versus parallel mathematical results agree under recorded tolerance and seed settings; require deterministic output ordering where contracted, not bitwise floating-point equality.
- [ ] Cancel before solve, at documented operation boundaries and during supported native calls; keep incumbents/bounds with actual evidence and no complete-family promotion.
- [ ] Nested outer/solver/BLAS requests share total thread policy; unsupported thread-control and memory admission-only modes are exposed rather than represented as enforced.
- [ ] Run supported race/ownership tooling and a bounded multi-run stress fixture; record tool limitations. Memory/resource exhaustion has documented outcomes without timing-based unit-test deadlines.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by RUN-01, OPT-03, OPT-08, SYN-03, SYN-04, SYN-05.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
