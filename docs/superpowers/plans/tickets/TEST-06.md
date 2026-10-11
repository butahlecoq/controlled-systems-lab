# TEST-06: Run reusable convex adapter contracts with singular objectives

GitHub: [#36](https://github.com/butahlecoq/controlled-systems-lab/issues/36).

## Purpose and scope

Test convex backend capabilities, objective mappings and numerical status evidence (OPT-01/02, ALG-01, SOL-03). Limit: this covers supported convex minimization; it supplies no convex-maximization or minimax guarantee.

Requirements: REV-02. Test oracles: T-C01, T-O02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Hand-solved QP: minimize (x-2)^2 on [0,1] gives x=1 and original cost 1; unconstrained positive-definite examples check stationarity and translated one-half factors.
- [ ] On [0,1]^2, minimize (x+y-1)^2: optimum zero has the whole segment x+y=1; the backend point output cannot be labeled a complete family.
- [ ] Test rectangular/rank-deficient residual norm with zero optimal residual and nondifferentiability, through the adapter's supported conic or documented quadratic reformulation.
- [ ] Unsupported objective classes and invalid convexity get preflight diagnostics; finite optimum, infeasible and solver numerical-limit cases keep distinct outcomes.
- [ ] Recompute objective and residuals independently; verify primal/dual evidence provenance only where adapter capabilities support it.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by [OPT-08 #22](https://github.com/butahlecoq/controlled-systems-lab/issues/22), [OPT-01 #17](https://github.com/butahlecoq/controlled-systems-lab/issues/17), [RUN-01 #25](https://github.com/butahlecoq/controlled-systems-lab/issues/25).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
