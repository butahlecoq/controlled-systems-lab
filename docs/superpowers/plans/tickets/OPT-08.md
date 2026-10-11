# OPT-08: Integrate convex-program interfaces and a reference adapter

GitHub: [#22](https://github.com/butahlecoq/controlled-systems-lab/issues/22).

## Purpose and scope

Solve supported terminal convex programs through a registered QP/conic adapter.

Requirements: ALG-01, OPT-01, SOL-02, EVD-02. Test oracles: T-C01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Declare supported objective, equalities, lower-dimensional sets and evidence scope before execution.
- [ ] Check inside/boundary optima, zero residual and semidefinite minima against analytic answers.
- [ ] Return point and optimality evidence without claiming it already describes every terminal minimizer.

## Dependencies

Blocked by [OPT-01 #17](https://github.com/butahlecoq/controlled-systems-lab/issues/17), [CORE-04 #14](https://github.com/butahlecoq/controlled-systems-lab/issues/14).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
