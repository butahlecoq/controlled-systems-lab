# OPT-11: Add a recursive split-and-merge hull strategy

GitHub: [#45](https://github.com/butahlecoq/controlled-systems-lab/issues/45).

## Purpose and scope

Implement a new hull-level divide-and-conquer strategy using hull(hull(P1) union hull(P2)). The archive supports ordered/grouped filtering and a separate 2D QuickHull; this recursive LP-backed strategy is a new extension. Reuse the hull port and selected membership backend.

Requirements: ALG-02, ALG-07, RUN-02, RUN-03. Test oracles: T-L02, T-R01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Provide the finite-point hull-equivalence argument and deterministic partition/merge policy before code; stop small leaves with the existing reducer.
- [ ] Compare hull support and removed-point certificates with the independent baseline on signed, duplicate and affine-degenerate fixtures, across input permutations.
- [ ] Use exclusive child workspaces and a common resource budget; record leaf/merge LP work, peak intermediate point counts and parallel overhead without claiming a universal speedup.

## Dependencies

Blocked by [OPT-05 #30](https://github.com/butahlecoq/controlled-systems-lab/issues/30), [RUN-01 #25](https://github.com/butahlecoq/controlled-systems-lab/issues/25).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
