# MPC-06 completion evidence and delivery disposition

This is the completion handoff for issue [#602](https://github.com/butahlecoq/controlled-systems-lab/issues/602), not issue closure or a publication claim. Its six acceptance bullets and opening fixed-plan-reference scope were audited in [the delivery plan](../superpowers/plans/2026-11-10-mpc06-delivery.md).

## Evidence by acceptance requirement

| Requirement | Evidence and limit |
| --- | --- |
| Supported affine LTI/full-state/continuous-control profile | The unchanged native input specifies A=[[1,1],[0,1]], B=E=(0,1), W=[-1/8,1/8], X=[-1,1]² and U=[-1,1]. [B,AB] is nonsingular; K=(-1,-2) gives F²=0. Unsupported LTV, model/correlated uncertainty, finite actuators and measured-state-reset policies remain outside admission. |
| Independent RPI, tightening, terminal and edge checks | The immutable pilot already proves the finite nilpotent RPI with zero tail, support tightenings, initial membership and empty-tightening/unsafe-plan edge cases. The online study independently checks admitted/rejected representation variants. Nominal terminal {0} with v=0 and the admitted RPI error set give a terminal continuation; three executed receding steps need not themselves end at nominal zero. |
| Matched exact robust reference and distinct quantifiers | The original finite-error interval/grid matches the prescribed-K nominal-terminal-zero planning class. New exact N=3 M0 and fixed-K references eliminate terminal equalities to one scalar. Rational candidate construction is independently checked by a global active-quadratic lower-bound certificate. M0, fixed-K and general feedback-winning sets are not conflated; unsafe disturbance histories are never clipped. |
| Explicit objective and independently checked cost | Six exact class minima cover the three recorded initial states and two fixed policy classes. Sixty FIRST native predicted plans, held for three steps, have matched nonnegative fixed-K minimax gaps. Actual three-step receding-prefix costs remain separate because their terminal/tail scope differs. All references use the actual finite cost sum(x²+u²)+x3². A nominal surrogate is not called minimax. |
| Sound representation direction and conservatism | Exact polytope/parallelotope/zonotope identities, the inflated outer tube and separately certified invariant ellipse retain their stated inclusion/RPI evidence. The outer coordinate box and emitted APP-04 ellipse fail RPI and are rejected, despite enclosing Z. No volume correctness, generic inner-ellipse producer or cross-class winner is claimed. Representation gates #99/#100 are closed. |
| Offline/online/checker costs, figure and qualification | Saved native preparation/setup/solve, APP-04 construction, exact construction/checking and process intervals stay separate. Prescribed K has no gain optimization. The prior Z/terminal proof has no isolated construction timing; this is unavailable, not zero. New pinned shared-style figures show invariant/tightened sets, actual saved paths and the finite initial grid. Performance remains descriptive and inconclusive for ranking. |

The original native v1/v2/v3 archives and their 180 QPs remain unchanged. The [new saved report](../../reports/algorithm-results/mpc06-completion-v2/index.html) carries the checked reference record, full upstream evidence, reviewing-source hashes, exact certificates and figure provenance. Plotting, checking and staging start no native solver.

## Platform, dependency and release/package impact

The new unit delivers source scripts, exact records and a versioned scientific report. It adds no public API, package layout or installed binary. **Delivery outcome: no standalone library release needed.** The existing installed-library workflow remains responsible for its advertised package profiles; this report-only unit does not invent another installed-binary acceptance gate.

- Existing optional HiGHS 1.11.0 remains the numerical QP provider with its pinned MIT/bundled notices. Qhull is disabled for this native study. No acados, OSQP, HPIPM or MATLAB installation is added.
- New figures use the existing report-only `matplotlib==3.11.2` requirements and `csl-report-quantitative-v1` axis policy. Native numerical status and exact stored-value reference checks remain distinct evidence.
- Local native capture used Release GCC 16.2.1 on Linux; the source/flags/cache/binary digest are retained. PR #899 at `eee2db25` passed dedicated GCC 13, Clang 18 and Windows MSVC native public-QP/APP-04 smoke jobs in [run 42710326480](https://github.com/butahlecoq/controlled-systems-lab/actions/runs/42710326480). Its Linux core/HiGHS installed consumers and ASan/UBSan jobs also passed. This qualifies only the exercised profiles; new report validation and exact-head review remain pending.
- The project's distribution-license decision remains unchanged. The publication ZIP contains source/report evidence rather than a compiled library, vendored dependency archives or private paper material. Original CMake cache paths remain explicitly retained provenance, not a portable installed package. Staging checks the complete inventory and rejects symlinks, unexpected bytes and stale renderer output.

## Publication boundary and remaining gates

The dedicated adapter rechecks the exact references and held-plan extraction, the upstream checked-source/raw-response bindings, all file digests and deterministic Matplotlib output. It creates a content-derived route, publication manifest and deterministic offline ZIP. The existing cumulative Pages augmentation adds this route alongside MPC-01, B04-C and the earlier MPC-06 objective report. The original `algorithm-reports.yml` is byte-identical; the existing main-only workflow, reviewed upstream artifact, serialization and stale-head checks remain authoritative.

Before reporting #602 complete: obtain independent code/results/standards completion review, pass exact-head reporting/platform checks, merge in dependency order, verify the deployed page/figures/manifests/raw records/offline ZIP and record the actual accessible URL. Do not close the issue from local staging success alone. There is no new owner-confirmation or installed-binary gate beyond the actual task and delivery scope.

The v2 reading layer adds explicit authentication of copied checker snapshots
against recorded source-file digests. The v1 report remains immutable; its
numerical reference and native inputs are unchanged. This is a provenance fix.
