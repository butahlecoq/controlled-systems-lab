# APP-01: Define inner and outer approximation policies and evidence

## Purpose and scope

Expose approximation as a separate registered operation with a reference set, direction and budget.

Requirements: ALG-04, ALG-06, EVD-02. Test oracles: T-G02, T-V02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Equivalent conversion, inner, outer and heuristic output use distinct labels and capability checks.
- [ ] For R_in subset R subset R_out, supported objective bounds retain direction; an inner reachable state needs a realizable trajectory for an achievable plan.
- [ ] Reject a requested enclosure guarantee when inclusion evidence is unavailable; reachable-set approximation does not imply the same relation for optimizer families.

## Dependencies

Blocked by GEO-01, CORE-04.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
