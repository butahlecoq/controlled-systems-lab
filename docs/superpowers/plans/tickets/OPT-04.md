# OPT-04: Implement the archival phase-I feasibility kernel

GitHub: [#29](https://github.com/butahlecoq/controlled-systems-lab/issues/29).

## Purpose and scope

Implement the professor-associated phase-I procedure for the equality/nonnegative feasibility tasks used by hull and recovery modules.

Requirements: ALG-01, ALG-02. Test oracles: T-L01, T-L02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Document lineage from L01/L03/L07 and A06; do not claim one saved variant is a verified original release.
- [ ] Return feasible coefficients, auxiliary residual, basis/pivot diagnostics and bounded termination. Define degeneracy and anti-cycling policy.
- [ ] Check triangle membership, collinear inputs, signed coordinates and deterministic pivot ties against the reference LP.

## Dependencies

Blocked by [OPT-02 #18](https://github.com/butahlecoq/controlled-systems-lab/issues/18), [OPT-03 #21](https://github.com/butahlecoq/controlled-systems-lab/issues/21).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
