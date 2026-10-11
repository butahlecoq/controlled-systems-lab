# VIZ-03: Export standalone scientific final-result figures

GitHub: [#96](https://github.com/butahlecoq/controlled-systems-lab/issues/96).

## Purpose and scope

Goal: render PlotData and performance-table records with standard scientific plotting tools into standalone vector figures and raster previews. Requirements EXP-01/02/04/06. Choose and document a plotting/export adapter after dependency review; a standalone external plotting tool is allowed and does not select public language bindings. Inputs are saved artifacts and PlotRequest; outputs include control/state figures, selected 2D pair figures and detailed timing charts/tables. Plotting/export stays outside solver logic, and interactive intermediate viewing is optional future scope.

Requirements: EXP-08, EXP-06. Test oracles: T-X02, T-VIZ03: regenerated standalone figure integration and visual QA.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Export standalone SVG or PDF plus PNG with axes, units, readable legends, method/witness labels, objective/evidence context, approximation/sample labels and scenario identity. Figures open and remain interpretable without an app or live solver.
- [ ] Support plot regeneration from saved raw data with a versioned style/export configuration; record plotting-tool version and export timing separately from mathematical solve/query latency.
- [ ] Provide fuel flow/stock state plots, stage-aligned controls and requested 2D coordinate pairs; visually inspect exported artifacts for clipped labels, indistinguishable series, hidden negative balances and misleading projection legends.
- [ ] A timing figure preserves wall-versus-work/CPU definitions and labels unavailable metrics; it does not show overlapping inclusive durations as an additive latency stack.
- [ ] Integration tests validate artifact contents and numerical series against an analytic fixture, while documented visual QA checks the produced figures; avoid brittle exact-pixel assertions.

## Dependencies

Blocked by [VIZ-01 #87](https://github.com/butahlecoq/controlled-systems-lab/issues/87), [VIZ-02 #91](https://github.com/butahlecoq/controlled-systems-lab/issues/91), [OBS-05 #86](https://github.com/butahlecoq/controlled-systems-lab/issues/86), [CORE-01 #11](https://github.com/butahlecoq/controlled-systems-lab/issues/11).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Ship meaningful unit/contract tests with the implementation, using the named independent oracle. Return commits, tests and commands run, supported assumptions, numerical/evidence limitations and unresolved findings. Shared contract changes require an explicit specification revision and integration review.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
