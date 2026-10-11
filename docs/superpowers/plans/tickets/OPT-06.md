# OPT-06: Add basis-reuse hull classification as a replaceable method

GitHub: [#37](https://github.com/butahlecoq/controlled-systems-lab/issues/37).

## Purpose and scope

Use completed phase-I basis information to classify multiple hull candidates without changing the HullReducer interface.

Requirements: ALG-02, ALG-04, RUN-04. Test oracles: T-L02, T-G02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [algorithm-module-inventory.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/algorithm-module-inventory.md), [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Distinguish within-solve bulk classification from cross-query warm starts; preserve input point IDs.
- [ ] Validate every bulk removal; skipped basis points need a proof or final verification pass.
- [ ] Compare permuted, degenerate and interior-basis clouds with the baseline hull. Publish LP/pivot/bulk counters without a universal speedup claim.

## Dependencies

Blocked by [OPT-04 #29](https://github.com/butahlecoq/controlled-systems-lab/issues/29), [OPT-05 #30](https://github.com/butahlecoq/controlled-systems-lab/issues/30).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
