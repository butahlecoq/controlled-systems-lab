# OPT-09: Implement the Pascal-derived Zoutendijk projection method

GitHub: [#39](https://github.com/butahlecoq/controlled-systems-lab/issues/39).

## Purpose and scope

Add a feasible-direction adapter for Euclidean projection onto a supported linearly constrained set, using A06 ZODENTEK as source evidence.

Requirements: ALG-01, OPT-02, EVD-01. Test oracles: T-C01, T-L02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Record the active-constraint direction LP and feasible-start policy. Implement the smooth quadratic equivalent and retain original projection distance.
- [ ] The step bound checks all positive directional derivatives; regression has an inactive zero-derivative row before a later finite bound.
- [ ] Compare interval/box/face/singleton projections with analytic and reference QP results; feasible iterates, zero direction, termination and KKT residual are explicit.

## Dependencies

Blocked by [OPT-04 #29](https://github.com/butahlecoq/controlled-systems-lab/issues/29), [OPT-08 #22](https://github.com/butahlecoq/controlled-systems-lab/issues/22).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
