# MPC-10 bounded finite, mixed and hybrid comparison

This optional source/report consumer compares three distinct nominal products:
finite catalogue controls, continuous-plus-catalogue controls, and explicit
mode/edge automata. The authored profile has two physical coordinates with
`y=0` invariant, one active scalar coordinate, horizons 0–3, dyadic data,
independent interval controls, and affine functional resets. It does not claim
general hybrid scalability or causal/robust hybrid-game synthesis.

The native consumer calls the public finite-history cursor, mixed-branch
specializer, Strategy B joint-program builder and registered HiGHS LP port.
Finite-only histories use the exact embedding `R^0 × catalogue`: there are no
continuous coordinates, and catalogue indices/physical controls are unchanged.
Hybrid cases use public portfolio/path construction and execution. Candidate
faces are built through the public API; the independent public exact-H verifier
establishes complete families where its bounded proofs succeed. Numerical
primal ranking only selects candidates and is never its own coverage proof.

The independent SCIP formulation uses catalogue, mode and edge one-hot
variables, exact adjacency and native linear indicators. An equality is two
indicator inequalities. Continuous-variable bounds come from authored interval
bounds and their mode unions. The second physical coordinate is eliminated
using the exact invariant `y=0`; no guessed big-M value or convex-hull relaxation
is introduced. Mode-specific terminal cost is selected at the post-reset
terminal mode. The indicator API is documented in the versioned
[PySCIPOpt model reference](https://pyscipopt.readthedocs.io/en/v6.3.0/api/model.html).

For a fixed history, exact interval propagation establishes every attainable
scalar state, intersects source/pre-reset/guard/destination intervals in their
specified order, and applies the affine reset. Back-substitution constructs an
exact witness at the minimizing endpoint. Enumerating all bounded histories
establishes branch feasibility, minima and every tied index/edge identity.
The checker independently rebuilds the native joint LP rows/objective and the
SCIP submitted model. It binds SCIP structured witnesses to the raw solution,
replays original physical equations/constraints, and checks native outcomes.
Native candidate H faces are compared with the full original relation plus the
exact global-value equality, preserving joint history correlations.

The primary unrestricted SCIP solve yields one numerical incumbent, bounds and
gap. Additional fixed-history SCIP solves check branch feasibility/values;
their costs remain separate. Neither a SCIP incumbent nor a set of endpoint
samples is labelled a complete continuous family.

## Run and recheck

Use the existing qualified optional environment; this unit installs nothing.
The CMake consumer accepts the paths of existing pinned HiGHS/JSON dependencies
and builds current CSL/adapters against the existing native archive:

```sh
cmake -S benchmarks/reporting/mpc10 -B <BUILD> \
  -DCSL_SOURCE_ROOT=<CHECKOUT> \
  -DCSL_EXISTING_HIGHS_LIBRARY=<EXISTING_LIBHIGHS> \
  -DCSL_EXISTING_HIGHS_SOURCE=<EXISTING_HIGHS_SOURCE> \
  -DCSL_EXISTING_HIGHS_BINARY=<EXISTING_HIGHS_BUILD> \
  -DCSL_EXISTING_JSON_SOURCE=<EXISTING_JSON_SOURCE>
cmake --build <BUILD> --target csl_mpc10 -j2
<SCIP_PYTHON> -m benchmarks.reporting.mpc10.run \
  --bridge <BUILD>/csl_mpc10 --output <NEW_CAPTURE>
<SCIP_PYTHON> -m benchmarks.reporting.mpc10.check \
  --bundle <CAPTURE> --output <NEW_VERIFICATION_JSON>
<PLOT_PYTHON> -m benchmarks.reporting.mpc10.figures \
  --bundle <CAPTURE> --verification <VERIFICATION_JSON> --output <NEW_FIGURES>
```

Run modules from the checkout root. Capture/output directories must be new.
The checked source snapshots, complete capture inventory, reviewing-source
fingerprints and verification input map are shared by checker and renderer.
Rendering validates those bindings before reading data and never rewrites a
capture, receipt or original checksum. Optional plotting uses the repository's
Matplotlib 3.11.2/shared quantitative figure style. The capture runner uses POSIX
resource limits; this pilot qualifies Linux only.

Initial immutable evidence and source/reading-layer qualification are in
[`evidence/comparison-525871ea`](evidence/comparison-525871ea/README.md).
See [the six-requirement disposition](../../../docs/research/mpc10-comparison-disposition.md)
for outcome scope, release impact and closure gates.
