# TEST-05: Run reusable LP adapter contracts on every selected backend

GitHub: [#35](https://github.com/butahlecoq/controlled-systems-lab/issues/35).

## Purpose and scope

Test LP port, backend status translation and optional simplex diagnostics (ALG-01/02, SOL-03). Limit: tests only claim bounds/rays/certificates actually supported by each adapter; passing examples do not verify arbitrary backend correctness.

Requirements: REV-02. Test oracles: T-L01, T-L02.

Read the [2026-10-11-controlled-systems-master-design.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md), [2026-10-11-controlled-systems-backlog.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) and [modular-algorithms-and-solution-sets.md](https://github.com/butahlecoq/controlled-systems-lab/blob/main/docs/architecture/modular-algorithms-and-solution-sets.md).

## Acceptance criteria

- [ ] Independent analytic oracle: minimize -x-2y with x,y>=0 and x+y<=1 gives (0,1), objective -2; include maximization-to-minimization sign translation and explicit free/fixed variable bounds.
- [ ] x<=0 and x>=1 is infeasible; minimize -x with x>=0 is unbounded; contradictory redundant rows and degenerate optimal faces exercise status translation.
- [ ] Recompute primal residuals and any reported dual bound from neutral program data, including equalities and infinite bounds; test scaling and objective offset preservation.
- [ ] Induce a documented iteration/resource limit or use a contract stub; partial candidate/bound evidence cannot become optimal or infeasible.
- [ ] Run the same neutral suite per selected LP adapter; optional basis diagnostics are explicitly unavailable on generic adapters and supported simplex diagnostics obey a dedicated contract.
- [ ] The originating implementation ships with meaningful minimum acceptance tests written before its code; this separate issue expands the suite using independently designed oracles and records discovered defects as fixes.

## Dependencies

Blocked by [OPT-03 #21](https://github.com/butahlecoq/controlled-systems-lab/issues/21), [OPT-02 #18](https://github.com/butahlecoq/controlled-systems-lab/issues/18), [RUN-01 #25](https://github.com/butahlecoq/controlled-systems-lab/issues/25).

Related scientific/architecture issues: [#7](https://github.com/butahlecoq/controlled-systems-lab/issues/7), [#8](https://github.com/butahlecoq/controlled-systems-lab/issues/8). These are not additional blockers.

## Delivery and review

Expand independent tests through the module interface. Minimum acceptance tests belong to the implementation ticket and cannot wait for this issue. Record failures as linked fixes. Do not use historical wall-clock values as unit-test thresholds.

Use the plan ownership map to claim files before editing. Later-phase tickets do not expand the first-release scope. Do not alter source transcriptions or label a witness sample as a complete optimal family.
