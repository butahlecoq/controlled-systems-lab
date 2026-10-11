# TEST-08: Expand exact polyhedral operation tests with degenerate cases

## Purpose and scope

Test supported H/V polyhedral affine image, sum, intersection, support and preimage/projection operations (ALG-03/05). Limit: mathematically exact formulas executed in double are numerical evidence, not validated inclusion.

Requirements: REV-02. Test oracles: T-G01, T-G02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Use independently enumerated rational boxes/triangles: translate and reflect a unit box; intersect x+y<=1 with [0,1]^2; Minkowski-sum [0,1] and [2,3] gives [2,4].
- [ ] Affine singular map (x,y)->(x,0) of [0,1]^2 is a segment, not an empty or two-dimensional set; distinguish ambient and affine dimensions.
- [ ] Preimage of y=0 through (x,y)->y is an unbounded line; where unsupported, return unsupported instead of invented finite vertices.
- [ ] Test empty, singleton, universal and lower-dimensional inputs separately; support distinguishes finite value, empty and unbounded.
- [ ] Check projection of x+y=1 in [0,1]^2 gives [0,1] and preserve equality information; use fixed-seed low-dimensional cases with independent rational enumeration where applicable.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by GEO-02, GEO-03, GEO-04, GEO-05, GEO-01, OPT-03.

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
