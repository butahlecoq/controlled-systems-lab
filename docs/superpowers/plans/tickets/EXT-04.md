# EXT-04: Add initial-set semantics and observation-based control workflows

## Purpose and scope

Keep uncertain initial information, estimation and feedback distinct from nominal point-initialized planning.

Requirements: MOD-03, MOD-08, EVD-02. Test oracles: T-M02, T-V02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Specify existential versus all-initial-states planning and available observation history; no initial-set union silently becomes one robust plan.
- [ ] Implement a supported controller/estimator lifecycle with pre/post-decision timing and per-step evidence.
- [ ] Use separate scenario variants and tests for partial/noisy observations; sampled simulation does not certify every disturbance.

## Dependencies

Blocked by MODEL-02, SYN-06, EXT-01.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
