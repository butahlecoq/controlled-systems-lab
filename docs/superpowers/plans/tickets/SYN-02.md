# SYN-02: Construct the entire terminal minimizer relation

GitHub: [#61](https://github.com/butahlecoq/controlled-systems-lab/issues/61).

## Purpose and scope

Return supported full terminal argmin sets and optimum evidence, including nonunique convex minima.

Requirements: SOL-01, SOL-02, SOL-03, EVD-02. Test oracles: T-S02, T-S03, T-C01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Linear optimal faces, constant objectives and semidefinite/residual-map degeneracy preserve all terminal optima.
- [ ] Document and independently check the convex quadratic/residual optimal-level characterization used to build the relation; one solver point alone is insufficient.
- [ ] Attainment, finite optimum and numerical completeness limits are explicit; unsupported nonpolyhedral argmin construction is rejected.

## Dependencies

Blocked by [OPT-08 #22](https://github.com/butahlecoq/controlled-systems-lab/issues/22), [GEO-05 #51](https://github.com/butahlecoq/controlled-systems-lab/issues/51).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
