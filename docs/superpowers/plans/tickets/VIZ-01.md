# VIZ-01: Prepare backend-neutral final control and state plot data

## Purpose and scope

Goal: define a PlotData adapter that consumes final comparison artifacts and independently verified complete witnesses. Requirements SOL-04/05, EXP-01/06, EVD-01/02. Sources: modular architecture and B04 tables/restoration. Outputs carry state/control coordinates, units, stage/time axes, method/witness identities, known bounds/targets, objective and evidence labels. Rendering is outside synthesis/geometry/optimization; no frontend, Python binding or interactive intermediate viewer is selected here.

Requirements: EXP-08, EXP-06. Test oracles: T-S01, T-V01, T-V02, T-X02, T-VIZ01: stage/time plot-data alignment.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Controls use T stage intervals and states T+1 stage points; optional physical timestamps are used only when supplied and do not discretize dynamics. The control hold convention is explicit where a physical-time step plot is shown.
- [ ] Plot every selected witness with stable method/witness identity and common axes; label samples as selected complete witnesses rather than the whole optimal family.
- [ ] Expose original objective, residual/evidence references, requested/returned/distinct counts and duplicate diagnostics; a path marked invalid or unverified cannot be displayed as certified optimal.
- [ ] For fuel metadata preserve oxidizer flow/working-stock balance and fuel flow/working-stock balance, units kg/s and kg, and source targets/flow bounds. Negative stock balance remains visible without an invented nonnegative constraint.
- [ ] An analytic two-step fixture validates axis indexing and control/state alignment; malformed witness lengths, evidence/problem mismatch and missing physical-time conventions give explicit errors or stage-only plots.

## Dependencies

Blocked by OBS-04, SYN-05, MODEL-01, SYN-06.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
