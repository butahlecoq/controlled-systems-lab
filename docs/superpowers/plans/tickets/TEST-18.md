# TEST-18: Verify fuel-case 2D projection data and visual artifacts

## Purpose and scope

Test mandatory fuel-case visualization through generic coordinate projection/export adapters (EXP-01 plus proposed T-PLOT01). Cover final optimal-family/terminal projections and trajectories; intermediate projections only when explicitly supplied. Limit: projection/samples cannot prove full-family coverage or historical reproduction.

Requirements: REV-02. Test oracles: T-G01, T-X02, T-PLOT01 (proposed), T-B04.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Project the unit 3D box to two selected coordinates and a 3D affine segment (s,1-s,2s), 0<=s<=1, to the expected 2D segment; compare coordinates/support extrema to analytic oracles.
- [ ] For supported fuel scenario data, plot requested state pairs with source coordinate names/units, time/stage labels, trajectory/witness/strategy IDs, target/bound overlays and numerical versus exact/approximate relation labels.
- [ ] Test coordinate reorder, rectangular linear projections, degenerate point/segment, empty and unsupported unbounded outputs; a sampled cloud is labeled sampled and not filled as a proven exact boundary.
- [ ] Projection metadata preserve problem hash, source relation/stage and requested coordinates; a generic nonfuel scenario renders using the same exporter without fuel-index constants in the core.
- [ ] Produce reference PNG/SVG and numeric projection fixtures, manually inspect legibility and overlays, and compare geometry numerically with stable tolerances. Unresolved B04 gets a restoration-labelled diagnostic view rather than a canonical reproduction claim.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by GEO-05, VIZ-02, VIZ-03, VIZ-01, OBS-04.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
