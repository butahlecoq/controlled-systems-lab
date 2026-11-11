# Issue 941 implementation plan

## Goal and done condition

Give the three deterministic plants stable, source-bound task identities that a shared model, objective, affine-prediction, and CSL replay adapter can consume. Done means every task contract validates against its named source, the common API emits a finite physical vector field and exact physical objective, each affine prediction has a saved Jacobian/offset/discretization receipt and point check, replay works through `CSL::simulation`, and contract checks reject malformed dimensions, units, domains, source identities, and costs. No benchmark or solver run is part of this issue.

## Data shape

A task contract binds a source model manifest to state/control coordinate declarations, physical bounds and domain, a fixed time grid, an exact objective definition, execution/replanning semantics, control-domain adaptation IDs, policy-query scope, and prediction provenance. The physical ODE and objective remain separate from an affine prediction record. An episode record carries task hash, controls, physical states, objective components, and independent replay association.

## Workflow

1. [x] Verify source equations, units, parameters, costs, timing, and legacy identities from the audited MPC11 files and Earth-orbit pilot. Capture exact source hashes.
2. [x] Add three canonical task contracts and a parser that binds them to the source files. Reject drift instead of accepting copied values silently.
3. [x] Implement one common physical model/objective/prediction adapter. Reuse the actual MPC11 affine builder for LV and fuel. Add an explicitly orbit-specific analytic Jacobian and exact ZOH affine discretization; reject orbit in the LV fallback.
4. [x] Extend the existing CSL nonlinear replay bridge with the orbit ODE and units. Keep the old finite three-block orbit benchmark unchanged and separately identified.
5. [x] Add independent analytic checks, task-domain and coordinate checks, off-trajectory query fixtures, and a common CLI example. Reuse the saved LV phase illustration.
6. [x] Run focused contract, Jacobian, scaling, objective, and replay checks. The qualified Python suite passes; the CSL bridge matches independent RK4 at every held-stage endpoint.
7. [ ] Inspect the exact diff, record delivery impact, then commit and open a PR for independent review. Do not merge before coordinator review.

## Scope and rigor

This touches three source models, one shared task API, the existing MPC11 prediction/replay path, and contract tests. The main risk is accidentally presenting unlike control domains or objectives as one task. Hash-bound source association, exact objective formulas, explicit adaptation IDs, and independent physical-cost checks are the gates. Release impact is none: this adds benchmark/report tooling and contracts, not a public installed C++ API or dependency.
