# VIZ-04: Associate nonlinear replay results with linearly optimal witnesses

GitHub: [#92](https://github.com/butahlecoq/controlled-systems-lab/issues/92).

## Purpose and scope

Goal: extend final comparison/plot artifacts with optional independent plant replay records for complete selected linear witnesses. Requirements EXP-01/02/04, EVD-01/02 and SOL-04/05. Sources: b04-tables.md and b04-restoration.md. Inputs are witness history, explicit reference-plant identity/parameters/initial conditions and integration/control-hold conventions; outputs store replay trajectory, original replay objective, numerical/integration diagnostics and distinct replay timing. This ticket consumes a separately implemented plant adapter. It neither implements nonlinear optimization nor chooses the best replay witness as a new primary objective.

Requirements: EXP-08, EXP-06. Test oracles: T-O02, T-V01, T-V02, T-X02, T-REPLAY01: tied linear witnesses with distinct nonlinear replay.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] A linear witness links to separate linear verification and nonlinear replay records; labels distinguish linear optimality evidence, nonlinear feasibility/quality and absence of nonlinear global-optimality evidence.
- [ ] Different linearly optimal witnesses can produce distinct replay trajectories/costs without being called inconsistent linear solver results; original objective convention and plant units are preserved.
- [ ] Missing plant parameters, initial conditions, full controls or integration/hold conventions yield unavailable replay with named prerequisites; no interpolation of historical controls or fitted coefficients fills gaps silently.
- [ ] Keep nominal reference, frozen-coefficient regulator and witness policies distinct, including the fact that the nominal u=0 row is not a demonstrated zero-control solution from perturbed B04 initial data.
- [ ] A small independently specified nonlinear test plant demonstrates replay variation for tied linear witnesses and detects deliberately wrong control timing; B04 replay reproduction remains gated by canonical histories/conventions.

## Dependencies

Blocked by [VIZ-01 #87](https://github.com/butahlecoq/controlled-systems-lab/issues/87), [OBS-04 #83](https://github.com/butahlecoq/controlled-systems-lab/issues/83), [EXP-04 #56](https://github.com/butahlecoq/controlled-systems-lab/issues/56), [SYN-05 #71](https://github.com/butahlecoq/controlled-systems-lab/issues/71), [OPT-01 #17](https://github.com/butahlecoq/controlled-systems-lab/issues/17).

Related scientific/architecture issues: [#6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), [#10](https://github.com/butahlecoq/controlled-systems-lab/issues/10). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
