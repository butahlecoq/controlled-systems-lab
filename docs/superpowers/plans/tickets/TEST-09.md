# TEST-09: Expand geometry registry, conversion and guarantee contract tests

## Purpose and scope

Test extensible registrations, equivalent H/V routes and future approximation metadata (ALG-03/04/06/07). Limit: approximation algorithms remain deferred; fake inner/outer operators test contract enforcement only.

Requirements: REV-02. Test oracles: T-G02, T-M03.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Register a test representation/operator externally and resolve it without changing planner switches; registration conflict and missing compatible operation give actionable diagnostics.
- [ ] Round-trip a rational triangle and a degenerate segment between supported H/V forms; compare membership, supports and dimension against analytic oracles, not byte equality.
- [ ] An unbounded half-space cannot silently convert into a bounded V-point list; fail or use declared ray-capable output.
- [ ] Request equivalent output from a fake outer-only adapter: preflight rejects; inner/outer/heuristic results retain their relation and reference-set/problem identities through serialization.
- [ ] Use fake future zonotope/ellipsoid registrations to verify no automatic exact closure or conversion route is assumed and no approximation downgrade is allowed.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by CORE-04, GEO-03, GEO-02, GEO-04, GEO-05.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
