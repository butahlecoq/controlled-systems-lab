# REVIEW-02: Deep review of geometry algorithms and interchangeable backends

GitHub: [#70](https://github.com/butahlecoq/controlled-systems-lab/issues/70).

## Purpose and scope

Inspect implemented polyhedral geometry, hull/recovery, conversions, registry and LP/convex adapters (ALG-01..07, OPT-01/02). Scientific limit: numerical exact formulas do not certify rounding; later zonotope/ellipsoid/approximation capabilities remain deferred.

Requirements: REV-03. Test oracles: T-G01, T-G02, T-L01, T-L02, T-C01, T-O01, T-O02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Trace a second compatible LP adapter through neutral programs, statuses and evidence without editing models/objectives/planners; generic membership cannot require specialized phase-I basis data.
- [ ] Review mathematical formulas, bounds/equalities/rays and lower-dimensional/empty behavior against analytic fixtures; inspect status/dual-bound translation and rectangular objective mappings.
- [ ] Exercise test representation registration and incompatible guarantee routes; equivalent versus inner/outer/heuristic conversions must be explicit with no silent relaxation.
- [ ] Audit conversion/materialization costs, redundancy degeneracy and allocation growth; identify hidden dimensional/compactness/invertibility assumptions and capabilities needed for each path.
- [ ] Review dependency/version/license decisions only from recorded pinned integrations and primary evidence; findings include concrete reproductions, fixes and numerical limitations.
- [ ] Run after the relevant code and evidence exist. An independent reviewer records commit IDs, file/line findings, reproductions and severity; blocking findings become linked fix tickets and are rechecked before closure. The implementer cannot self-sign off.

## Dependencies

Blocked by [GEO-02 #40](https://github.com/butahlecoq/controlled-systems-lab/issues/40), [GEO-03 #31](https://github.com/butahlecoq/controlled-systems-lab/issues/31), [GEO-04 #41](https://github.com/butahlecoq/controlled-systems-lab/issues/41), [GEO-05 #51](https://github.com/butahlecoq/controlled-systems-lab/issues/51), [CORE-04 #14](https://github.com/butahlecoq/controlled-systems-lab/issues/14), [OPT-03 #21](https://github.com/butahlecoq/controlled-systems-lab/issues/21), [OPT-08 #22](https://github.com/butahlecoq/controlled-systems-lab/issues/22), [OPT-05 #30](https://github.com/butahlecoq/controlled-systems-lab/issues/30), [OPT-01 #17](https://github.com/butahlecoq/controlled-systems-lab/issues/17), [TEST-04 #27](https://github.com/butahlecoq/controlled-systems-lab/issues/27), [TEST-05 #35](https://github.com/butahlecoq/controlled-systems-lab/issues/35), [TEST-06 #36](https://github.com/butahlecoq/controlled-systems-lab/issues/36), [TEST-07 #48](https://github.com/butahlecoq/controlled-systems-lab/issues/48), [TEST-08 #63](https://github.com/butahlecoq/controlled-systems-lab/issues/63), [TEST-09 #64](https://github.com/butahlecoq/controlled-systems-lab/issues/64).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Review implemented code at a fixed commit against both repository standards and this specification. Report reproducible findings, severity and guarantee implications. Record the disposition of every finding and independently recheck blocking fixes.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
