# MPC-11 implementation and evidence plan

This plan implements [the synthetic controller contract](../contracts/mpc11-synthetic-controller-study.md)
for both SYN-NL-LV-01 and SYN-NL-FUEL-01. Issue #607 remains open until the
actual records, independent checks, figures and reviewed integration exist.
The owner authorized autonomous execution; acados remains excluded.

1. **Scenario and environment inputs.** Add canonical scenario JSON for both
   complete authored models, including scales, objective normalization, physical
   and controller-only constraints. Resolve the optional CPython 3.11 environment
   with exact wheel/transitive hashes and bundled notices. Check the loaded
   IPOPT/MUMPS versions and preserve the environment receipt before capturing
   results. Do not add these packages as required CSL dependencies.
2. **CSL affine producer.** Implement the saved matrix-exponential discretization
   and reference samples, export the actual public CSL model/program and joint
   quadratic objective, and retain the returned control witness and provider
   evidence. Check coefficient dimensions, objective terms and affine replay
   against literal small fixtures. Handle unsupported objective/provider plans
   explicitly before running a comparison.
3. **Existing independent replay seam.** Add derivative callbacks/declarations
   for both synthetic cases to the existing simulation example/harness layer.
   Validate scaled/physical transforms, units, holds, objective reconstruction,
   domain errors, cancellation, incomplete prefixes and witness association.
   Add cheap analytic decoupled/zero-control fixtures; independent replay must
   not consume optimizer state trajectories as its own output.
4. **NMPC driver.** Implement the shrinking Radau NLP, explicit running cost,
   physical bounds, first-input hold, exact full-state observation, deterministic
   guesses and primal-only warm start. Save per-update setup/solve diagnostics
   and stop without fallback on failure. First validate LV's two-state path,
   then fuel's four-state path; retain failures as outcomes rather than silently
   changing parameters to obtain success.
5. **Independent checker.** Replay each saved control history with the existing
   adaptive RK4 seam at both tolerance settings. Recompute original nonlinear
   cost, constraint violations and sensitivity; compare against CVODES execution
   without treating agreement as a certified bound. Verify the affine witness is
   identical across the first two variants. Check solver-status/partial-trace
   consistency and reject unsupported global/robust claims.
6. **Bounded captures.** Run both cases and all three variants with resource
   receipts. Separate correctness pilots from repeated timing evidence. For
   timing comparisons, perform the required alternating repetitions and a
   separate limiter profile, retaining setup, optimization, execution, replay
   and export costs. Refine collocation mesh under a new configuration ID and
   report sensitivity without rewriting the initial capture.
7. **Saved-data figures and publication.** Generate the LV phase plane and both
   fuel mass/flow panels, companion state/control traces, minimal complete
   inputs, source identities, raw records and replay commands. Visually inspect
   figures, validate checksums and portable paths, and add reviewed report and
   example routes through the existing catalog/Pages workflow. Preserve existing
   sampled-LV and historical fuel artifacts unchanged.
8. **Completion audit.** Independent specification and standards reviews check
   the exact final source/bundle revisions against all six #607 acceptance
   criteria. Confirm hosted checks and deployed artifacts. Close #607 only when
   both actual synthetic cases and every required evidence item are delivered;
   record remaining historical physical-map and nonlinear robustness limits.

Each step produces a reviewable commit or result bundle. Source fixes and
reruns append new identities; prior attempts remain available. A successful
NLP/replay does not prove nonlinear global optimality, minimax correctness,
continuous-time safety or reachable-set containment.
