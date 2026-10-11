# EXP-04: Implement an independent nonlinear replay adapter

## Purpose and scope

Implement replay of complete controls on an independently specified plant. Start with an analytic nonlinear toy plant; accept B04 only when its plant parameters and timing conventions are sourced. This is simulation, with no nonlinear optimization claim.

Requirements: EXP-01, EXP-02, EVD-01. Test oracles: T-V01, T-O02, T-REPLAY01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [baselines.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/baselines.md), [b04-restoration.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/b04-restoration.md), [b04-tables.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/research/b04-tables.md).

## Acceptance criteria

- [ ] Declare plant parameters, initial state, integration method, tolerances and control-hold convention; missing data return named prerequisites.
- [ ] For x_next=x+u+u^2, x0=0, controls (0,1) and (0.5,0.5) have terminal states 2 and 1.5, although both give 1 under the linear integrator; independently check these values.
- [ ] Preserve original plant units and objective, numerical diagnostics, plant identity and separate replay timing; no fitted archival coefficients or invented histories.

## Dependencies

Blocked by MODEL-01, OPT-01, SYN-06.

Related scientific/architecture issues: [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), [#10](https://github.com/butahlecoq/controlled-systems-lab/issues/10). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
