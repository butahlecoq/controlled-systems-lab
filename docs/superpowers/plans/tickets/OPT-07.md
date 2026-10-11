# OPT-07: Add ordered and grouped hull reduction strategies

GitHub: [#38](https://github.com/butahlecoq/controlled-systems-lab/issues/38).

## Purpose and scope

Expose the archive ordering/grouping methods inspired by divide-and-conquer as distinct HullReducer adapters.

Requirements: ALG-02, ALG-03, RUN-04. Test oracles: T-G02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Identify which Scientific Research and Constrained QLPHULL steps actually run; document commented-out sections and differences.
- [ ] Sorting, filtering, grouping and final reduction preserve hull equality for every input permutation and degeneracy fixture.
- [ ] Declare this as a hull-level strategy, separate from LP pivot rules and recursive QuickHull; expose grouping/order counters.

## Dependencies

Blocked by [OPT-05 #30](https://github.com/butahlecoq/controlled-systems-lab/issues/30).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
