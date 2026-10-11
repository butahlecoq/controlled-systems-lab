# TEST-20: Expand exact structured-set and approximation contract tests

GitHub: [#100](https://github.com/butahlecoq/controlled-systems-lab/issues/100).

## Purpose and scope

Test the implemented zonotope/constrained-zonotope operations and box, parallelotope, zonotope and ellipsoidal approximations against independent low-dimensional inclusion oracles. Each adapter ships its own minimum tests first.

Requirements: ALG-03, ALG-04, ALG-06, EVD-02. Test oracles: T-G01, T-G02, T-V02, T-APPROX01.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Compare exact supported affine/sum operations against analytic supports; intersection is not assumed closed in ordinary zonotopes.
- [ ] For a known box/triangle, check claimed inclusion by a valid analytic or complete low-dimensional oracle; sampled directions are labelled samples, not containment proofs.
- [ ] Test degenerate dimensions, empty input, infeasible recovery, incompatible guarantee requests and unsupported operations; external ET comparison never becomes a runtime requirement.
- [ ] Outer reachability alone cannot supply realizable optimal controls; inner-set cost bounds require a recovery witness and compatible objective assumptions.

## Dependencies

Blocked by [GEO-07 #32](https://github.com/butahlecoq/controlled-systems-lab/issues/32), [GEO-08 #52](https://github.com/butahlecoq/controlled-systems-lab/issues/52), [APP-02 #33](https://github.com/butahlecoq/controlled-systems-lab/issues/33), [APP-03 #42](https://github.com/butahlecoq/controlled-systems-lab/issues/42), [APP-04 #34](https://github.com/butahlecoq/controlled-systems-lab/issues/34), [EXP-03 #99](https://github.com/butahlecoq/controlled-systems-lab/issues/99).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
