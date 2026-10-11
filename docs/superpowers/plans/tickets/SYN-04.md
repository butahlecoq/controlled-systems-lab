# SYN-04: Build optimal families by direct joint-trajectory optimization

GitHub: [#67](https://github.com/butahlecoq/controlled-systems-lab/issues/67).

## Purpose and scope

Solve the sparse full-trajectory program and construct its optimal relation behind the common synthesis interface.

Requirements: SOL-01, SOL-02, EXP-05, MOD-05. Test oracles: T-S01, T-S02, T-S03.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Encode every transition, initial/stage constraint and original terminal objective; no hidden state-constraint omission.
- [ ] Return supported complete families as relations, not a single QP minimizer; do not use Cartesian control marginals.
- [ ] Check the same analytic cases as the reachability strategy, including singular A and multiple histories for one terminal point.

## Dependencies

Blocked by [MODEL-03 #28](https://github.com/butahlecoq/controlled-systems-lab/issues/28), [OPT-08 #22](https://github.com/butahlecoq/controlled-systems-lab/issues/22), [SYN-02 #61](https://github.com/butahlecoq/controlled-systems-lab/issues/61).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
