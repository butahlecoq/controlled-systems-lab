# OPT-10: Extend feasible directions to declared smooth convex objectives

GitHub: [#50](https://github.com/butahlecoq/controlled-systems-lab/issues/50).

## Purpose and scope

Add a reviewed differentiable-convex feasible-direction adapter without treating generic callbacks as certified convex programs.

Requirements: ALG-01, OPT-01, EVD-02. Test oracles: T-C01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Specify objective/gradient and linear-constraint contracts, line-search conditions and supported convergence/optimality evidence.
- [ ] Handle zero direction, infeasible starts and numerical stalls distinctly; compare analytic smooth convex cases with a trusted solver.
- [ ] Document ALOWER/projected-gradient source differences; nonconvex or unsupported constraints do not acquire global-optimum labels.

## Dependencies

Blocked by [OPT-09 #39](https://github.com/butahlecoq/controlled-systems-lab/issues/39).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
