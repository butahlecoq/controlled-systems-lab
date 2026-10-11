# CORE-04: Select compatible algorithm adapters through a registry

GitHub: [#14](https://github.com/butahlecoq/controlled-systems-lab/issues/14).

## Purpose and scope

Resolve registered methods, set operations and backend workspaces from capabilities and requested evidence.

Requirements: ALG-01, ALG-03, ALG-05, ALG-07. Test oracles: T-M03.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Register at least two distinct compatible adapters without editing model or client dispatch logic.
- [ ] Reject unsupported representation/objective/scalar/guarantee requests before allocation-heavy work; include a reason and actual method identity.
- [ ] Create independent mutable workspaces from immutable configuration; no portable cross-compiler C++ ABI is claimed.

## Dependencies

Blocked by [CORE-03 #13](https://github.com/butahlecoq/controlled-systems-lab/issues/13).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
