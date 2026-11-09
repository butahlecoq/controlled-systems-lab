# MPC-06 propagated-anchor online study implementation plan

> **For agentic workers:** Use superpowers:executing-plans for the verified units below.

**Goal:** Complete the remaining #602 restricted-policy online-QP/reference and representation study without changing immutable prior reports.

**Architecture:** Retain the existing LTI plant, nilpotent K and stagewise independent disturbance interval. Initialize nominal anchor z0=x0, then propagate it using the applied nominal control; never reset it from disturbed measurements. At every step solve the tightened N=3 nominal quadratic program with terminal z3=0. Its terminal equations eliminate v1,v2, leaving one bounded quadratic variable v0. Exact rational interval/derivative calculations independently check the numerical CSL convex-port solution. Deterministic nominal anchors preserve affine disturbance dependence; vertex enumeration proves finite-horizon worst cost for this policy only.

**Tech Stack:** C++20 public CSL convex registration/HiGHS; existing approximation contracts; Python Fraction independent checks and saved-record rendering. No new dependency or acados.

**Spec:** Live issue #602 and `2026-10-28-mpc06-architecture-progress.md`; gates #596/#3/#83/#99/#100 are closed. Owner authorized captures.

## Ownership and verifiable units

- [ ] New `scripts/reports/mpc06_online/model.py` and `tests/reporting/test_mpc06_online.py`: exact restricted-policy QP, finite-error matched reference, RPI/inclusion evidence and counterexamples. Tests cover terminal equations, interior/boundary/empty intervals and wrong policies.
- [ ] New `benchmarks/reporting/mpc06_online/`: standalone public-port native QP runner, separate prepare/setup/solve measurements and backend evidence. Compile with existing libraries or bounded -j2 build and validate against exact reference.
- [ ] New capture/check/render scripts and scenario: finite initial-state grid, fixed-K nominal-anchor policy, exact/outer/rejected shapes, online solve and independent checking costs, five alternating repetitions, failure retention, source/binary provenance and immutable result directory. Reuse existing figure as historical linked evidence, add saved online trajectories/feasibility evidence as needed.
- [ ] Independent reviews, supported dependency/license/platform plan, installed/public-client and hosted checks, report publication verification. Keep #602 open until all acceptance evidence is complete.

## Mathematical fixture and evidence boundaries

Use A=[[1,1],[0,1]], B=E=(0,1), K=(-1,-2), W=[-1/8,1/8], X=[-1,1]^2, U=[-1,1]. Nominal objective is sum(z_k^T z_k+v_k^2), terminal z3=0. For z0=(p,q), v=(a,-p-3q-2a,p+2q+a). Tightened state/input rows give an exact interval for a. Strict convexity gives the exact clipped derivative root. Terminal nominal {0} with v=0 is invariant; actual terminal error tube must independently be RPI and satisfy original X/U.

Compare invariant-tube QPs with stage-specific exact finite-error tightenings only under identical fixed K, initial error zero, terminal condition and nominal objective. Report nominal objective and actual worst disturbance cost separately; neither is fixed-plan minimax or a general feedback-winning optimum. Retained anchor reoptimization is deterministic, so disturbance vertices suffice for convex actual quadratic cost. State-reset reoptimization would invalidate that argument and is unsupported.

Exact Z has generator columns (0,1)/8 and (1,-1)/8. Equivalent polytope/parallelotope/zonotope descriptions share the same set. Inflated alpha Z (alpha>=1) remains RPI. An outer axis box containing Z can fail RPI and must be rejected with an exact successor witness. Ellipsoid inclusion alone is insufficient; check its error transition independently. Reuse APP-01/03/04 routes where they admit the source representation; never infer an RPI certificate from their outer-enclosure evidence or volume. All approximations retain their direction and any extra support padding.

## Delivery

This adds research executables/scripts, not a generic MPC API or package dependency. HiGHS is the existing optional MIT dependency with pinned notices; its numerical QP status is not proof. Reuse supported GCC/Clang/MSVC/ASan/install gates, record exact exercised profiles, and retain unresolved project distribution-license gate. No standalone release needed. No edits to old report evidence or frozen publication workflows.
