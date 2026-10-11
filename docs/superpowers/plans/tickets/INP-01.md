# INP-01: Load and validate versioned scenario files

GitHub: [#44](https://github.com/butahlecoq/controlled-systems-lab/issues/44).

## Purpose and scope

Accept short user-authored scenarios and optional run settings without C++ edits.

Requirements: INP-01, INP-02, INP-03, INP-04, INP-05, MOD-09. Test oracles: T-I01, T-I02, T-I03.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Freeze syntax/schema through CORE-01, infer and cross-check dimensions, and document stable resolved defaults.
- [ ] Malformed shape/stage/schema and unknown fields identify the field and expected form; no guessed bounds or automatic discretization.
- [ ] Backend changes preserve mathematical scenario identity; historical non-executable records retain restoration diagnostics.

## Dependencies

Blocked by [MODEL-03 #28](https://github.com/butahlecoq/controlled-systems-lab/issues/28).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
