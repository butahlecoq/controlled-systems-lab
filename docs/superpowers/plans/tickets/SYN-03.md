# SYN-03: Build optimal families by reachability and backward recovery

## Purpose and scope

Implement the historical-method-based strategy with complete joint-history semantics.

Requirements: SOL-01, SOL-02, EXP-05, ALG-02. Test oracles: T-S01, T-S02, T-S03, T-L02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Recover the feasible preimage of the entire terminal minimizer relation, retaining cross-stage state/control dependence.
- [ ] For the two-step integrator, represent u0+u1=1 and reject (1,1); for a constant criterion preserve every feasible trajectory.
- [ ] Separate extensions for family completeness from the archived single-witness algorithm; record assumptions and any inverse-only fast-path limits.

## Dependencies

Blocked by SYN-01, SYN-02, GEO-05, OPT-02.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
