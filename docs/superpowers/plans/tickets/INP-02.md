# INP-02: Select scenarios and run method profiles from a native CLI

## Purpose and scope

Provide a simple launcher for choosing a scenario, validating it and running the two selected methods.

Requirements: INP-01, INP-03, EXP-05, REV-01. Test oracles: T-I01, T-I02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Basic use selects a file and default comparison profile; backend/seed/resources remain optional overrides.
- [ ] Return actionable capability/input failures and save final versioned results through the artifact interface.
- [ ] CLI contains no duplicated optimization logic and supports validation-only execution without an expensive solve.

## Dependencies

Blocked by INP-01, SYN-05, SYN-06, RUN-01.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
