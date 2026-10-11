# EXT-01: Add fixed-plan disturbance reachability and global worst-case reference

## Purpose and scope

Support declared independent bounded process disturbances and a justified worst-case objective oracle.

Requirements: MOD-02, EVD-02, ALG-05. Test oracles: T-V02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] For fixed controls propagate the entire disturbance set; reject robust state violations without clipping away counterexamples.
- [ ] For supported compact polytopes and convex objectives, evaluate terminal vertices or use another reviewed global bound; a local minimizer of negative convex cost is not a global oracle.
- [ ] Check interval endpoint maxima, all-infeasible plans and archived B08 rounded-data reference without claiming nonlinear reproduction.

## Dependencies

Blocked by SYN-01, OPT-01, GEO-03.

Related scientific/architecture issues: [#3](https://github.com/butahlecoq/controlled-systems-lab/issues/3), [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
