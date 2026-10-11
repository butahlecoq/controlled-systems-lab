# CORE-01: Fix public contracts and choose compatible native dependencies

## Purpose and scope

Publish a small interface revision for model, sets, programs, families, evidence and execution. Choose matrix, LP, convex, parser, test and build integrations before adapter work starts.

Requirements: MOD-01, ALG-01, ALG-03, ALG-05, RUN-01, EVD-02. Test oracles: T-M03, T-V02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Record supported properties, ownership, error outcomes and performance costs at each interface. No solver-library container appears in a public problem/result type.
- [ ] Record candidate versions, license constraints, supported toolchains and an integration probe for each selected dependency. Do not change the undecided project license.
- [ ] Provide caller examples for the two synthesis strategies and independent workspaces. Keep numerical evidence separate from validated claims.

## Dependencies

No prerequisite implementation issue. Ready to start.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
