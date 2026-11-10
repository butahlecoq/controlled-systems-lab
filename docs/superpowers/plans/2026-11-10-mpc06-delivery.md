# MPC-06 exact-reference and report delivery plan

> **For agentic workers:** Use superpowers:executing-plans; execute the verified units below without changing prior archives.

**Goal:** Finish the remaining #602 reference/report deliverables, then hand them to independent completion review before publication or closure.

**Architecture:** Reuse the 180 native QPs and version-3 checked-source layer. Add a separately labelled exact N=3 nominal-terminal-zero fixed-plan reference for K=0 and the prescribed feedback K. Publish a saved-data reading layer with existing report staging/combined main-only Pages augmentation and shared Matplotlib style; do not change the frozen base workflow or old bundles.

**Spec:** Live #602, its six acceptance bullets and opening fixed-plan-minimax scope; `2026-11-10-mpc06-online-anchor.md`. The owner authorized execution and report delivery. Live native prerequisites #596/#3/#83 and representation prerequisites #99/#100 are closed.

## Acceptance audit before implementation

1. **Supported system:** Existing record fixes affine LTI A=[[1,1],[0,1]], B=E=(0,1), exact full state, continuous U and independent compact stage disturbances. [B,AB] has nonzero determinant and prescribed K=(-1,-2) gives F²=0. LTV/model/correlated uncertainty and finite actuators remain unadmitted; this is no general MPC parser.
2. **RPI/tightening/terminal:** Immutable base pilot already proves exact nilpotent RPI, support tightenings, initial membership and empty-tightening edge case. Online records add equivalent/outer/rejected shapes, prescribed terminal nominal {0} and its v=0 continuation, with independent RPI/safety checks. Do not recreate or overwrite the original pilot or its fixed-policy 3/8 cost.
3. **Matched reference:** Current finite-error feasible intervals and finite initial grid match prescribed-K nominal-terminal-zero planning, not a general state-feedback winning set. The opening fixed-open-loop minimax comparison is not yet delivered. Add exact K=0 and prescribed-K frozen nominal-plan references with explicit distinct policy/quantifier labels. No cross-class bound ordering or general causal optimum is inferred.
4. **Objective:** Existing actual receding-controller surrogate and finite disturbance costs are explicit and checked. Its three executed receding inputs need not satisfy the initial horizon's nominal terminal-zero condition. Therefore evaluate the **first native predicted plan held for three steps** against the exact frozen-plan K reference; keep actual receding-prefix cost separate. Do not call its surrogate a minimax optimum.
5. **Representation:** Existing exact polytope/parallelotope/zonotope identities, inflated outer tube, independent RPI-certified ellipse and rejected outer box/APP-04 ellipse supply sound directions/inclusions. No volume correctness or inner-ellipsoid producer is claimed; use closed #99/#100 infrastructure rather than adding a new generic representation framework.
6. **Cost/visual/delivery:** Native preparation/setup/solve, APP-04 construction, exact construction/checking and process observations are retained. Prescribed K has no gain-optimization cost; expose unavailable standalone historical K/Z/terminal timings honestly, and retain separately timed exact reference construction/checking. Publish standard Matplotlib 3.11.2/shared-style 2D invariant/tightening, actual paths and finite-grid illustrations from saved data. Reuse existing optional HiGHS qualifications and current hosted platform checks. There is no new API, required solver or installed-binary artifact, so no new installed-binary gate or standalone library release is needed. Main-only/stale-head publication and a live URL check remain gates.

## Exact reference proof route

For initial z=(p,q), nominal terminal z3=0 gives v=(a,-p-3q-2a,p+2q+a). For each policy K=0 or K=(-1,-2), all eight disturbance vertices yield affine state/input coordinates and linear robust feasibility constraints on a. Their intersection is an exact rational interval. Every actual cost has the same positive quadratic coefficient: q*a²+b_i*a+c_i. Verify that coefficient rather than assuming it. The upper envelope can attain its minimum only at an interval endpoint, an active quadratic stationary point, or an intersection of two affine residual lines. Check rational candidates, then independently verify endpoint/subgradient optimality with active costs. The continuous-box maximum follows convexity for each fixed nominal plan and fixed gain. These are finite-horizon class optima, not a general causal value.

## Ownership and units

- [ ] New exact reference/checker module and tests under `scripts/reports/mpc06_delivery/`, `tests/reporting/test_mpc06_delivery.py`; preserve all native archives.
- [ ] New saved reference and Matplotlib publication figures/read layer, with source/bound-input manifests and independent replay tests.
- [ ] New immutable stage adapter and deterministic offline ZIP; hook into existing combined main-only augmentation and route catalog, with tamper/receipt/provenance tests. Coordinate shared aggregation/catalog ownership with root.
- [ ] Document platform/dependency/release impact and the exact residual gates. Obtain independent reviews; do not deploy or close #602 before review and live publication verification.
