# TEST-04: Expand objective evaluation and justified reformulation tests

GitHub: [#27](https://github.com/butahlecoq/controlled-systems-lab/issues/27).

## Purpose and scope

Test the linear, convex-quadratic and rectangular residual-norm modules independently of solvers (OPT-01/02). Limit: convexity is checked under the declared numerical policy; a numerical PSD check is not a validated certificate.

Requirements: REV-02. Test oracles: T-O01, T-O02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] At x=[1,2], linear c=[2,-1], d=3 gives 3; Q=diag(2,0), q=[0,1], c=3 gives 6 using the one-half convention.
- [ ] For L=[[1,0,0],[0,1,1]], r=[1,4], x=[1,1,3], the norm is zero; at x=[4,1,7], original norm is 5 and squared solver cost is 25.
- [ ] Use analytic bounded minimizer sets to show norm/square give the same minimizers while reporting different original versus transformed values; include zero residual and rank-deficient L.
- [ ] Reject wrong rectangular-map dimensions, materially nonsymmetric/indefinite Q and nonfinite data under documented tolerances.
- [ ] A sum containing other objective terms cannot inherit the pure norm-to-square equivalence; transformation provenance records weights, offsets and conventions.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by [OPT-01 #17](https://github.com/butahlecoq/controlled-systems-lab/issues/17).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
