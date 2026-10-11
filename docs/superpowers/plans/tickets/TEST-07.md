# TEST-07: Expand barycentric membership and hull reduction tests

GitHub: [#48](https://github.com/butahlecoq/controlled-systems-lab/issues/48).

## Purpose and scope

Test hull membership, redundancy removal and recovery independently of optional phase-I basis reuse (ALG-02). Limit: tolerances report numerical membership; hull preservation is established for analytic fixtures, not inferred from successful simplex pivots.

Requirements: REV-02. Test oracles: T-L02, T-G01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] For triangle vertices (0,0),(1,0),(0,1), validate interior (1/4,1/4), edge (1/2,1/2), vertex and exterior (1,1) against hand-derived x>=0,y>=0,x+y<=1.
- [ ] Recompute nonnegative barycentric weights, sum-to-one and reconstruction residual independently; duplicate points and a collinear hull cannot crash or be promoted to full dimension.
- [ ] Remove interior/repeated points from a square and compare support in analytic directions and surviving extremes, rather than asserting one arbitrary vertex order.
- [ ] Exercise generic LP feasibility adapter without basis diagnostics and a specialized adapter when present; required specialized capability fails explicitly if absent.
- [ ] Stage-labelled barycentric recovery preserves coordinate maps and returns a complete reconstructed input/control vector, including zero-dimensional cases.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by [OPT-05 #30](https://github.com/butahlecoq/controlled-systems-lab/issues/30), [OPT-03 #21](https://github.com/butahlecoq/controlled-systems-lab/issues/21), [GEO-01 #16](https://github.com/butahlecoq/controlled-systems-lab/issues/16).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
