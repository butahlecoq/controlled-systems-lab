# MODEL-01: Define affine LTI/LTV models and separate observations

## Purpose and scope

Construct reusable immutable dynamics and observation models with explicit time and input roles.

Requirements: MOD-01, MOD-02, MOD-03, MOD-04, MOD-05, MOD-09. Test oracles: T-M01, T-M02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [linear-system-contract.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/linear-system-contract.md).

## Acceptance criteria

- [ ] Represent A/B/E/offset and observation/error/feedthrough maps, including singular A and absent ports.
- [ ] Compact LTI and explicit LTV providers agree for x0=2, A=3, B=2, a=-1, u=[1,-2]: states [2,7,16].
- [ ] Validate timestamps and pre/post-action availability. No observations does not grant full-state knowledge.

## Dependencies

Blocked by CORE-03.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
