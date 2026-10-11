# APP-04: Implement ellipsoidal approximation and reference comparison

## Purpose and scope

Add directional ellipsoidal enclosures and an optional external Ellipsoidal Toolbox comparison adapter.

Requirements: ALG-04, ALG-06, EVD-02. Test oracles: T-G02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Declare supported input class and formulas; check shape PSD, degenerate sets and actual inclusion direction.
- [ ] Keep finite ellipsoidal families and their intersection/union semantics explicit; do not assume closure by one ellipsoid.
- [ ] Pin external ET inputs/version if used; no missing MATLAB dependency is presented as a completed native verification.

## Dependencies

Blocked by APP-01, OPT-08.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
