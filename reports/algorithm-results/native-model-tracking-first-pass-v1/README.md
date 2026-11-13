# Native model tracking first pass

This bundle records one bounded native MPC/tracking pass through all 35 entries
in the public discrete-model catalogue. It contributes initial execution
evidence to issue #1012; it does not cover every model/formulation combination
or close the issue.

## Outcomes

The immutable run at [`capture-20261113T183906Z`](capture-20261113T183906Z/)
attempted all 35 records. Thirty-two completed their C++ solve, first-action
application, plant step and replans. Three attempts were refused by the
registered HiGHS convex adapter: models 23, 27 and 28 each contain a nonzero
matrix coefficient at or below its `1e-12` native-removal threshold. The
literal coefficients remain intact in the recorded model data. No small value
was rounded away to force admission. The installed SDK exposed HiGHS as its
convex QP adapter; the available CasADi adapter serves a different optimizer
port. The refusals and stderr are retained in each model directory.

[`independent-checks-20261113T184915Z`](independent-checks-20261113T184915Z/)
contains the independent checker results. It recomputed full-state dynamics, the applied action and
the task objective for every completed plan. It checked 429 state transitions:
150 transitions across the 15 source21 replans and 279 across the 31 completed
authored tasks. All 32 completed cases passed. The maximum absolute dynamics
residual was `7.474e-13`; the maximum objective-evaluation difference was
`1.905e-12`. The checker also verifies the source21 printed state/input bounds
and recomputes each realized stage cost. See
[`checks.json`](independent-checks-20261113T184915Z/checks.json),
[`independent_results.csv`](independent-checks-20261113T184915Z/independent_results.csv)
and [`full_state_trajectory_checked.csv`](independent-checks-20261113T184915Z/full_state_trajectory_checked.csv).
The objective and realized-cost values are per-profile; their scales differ and
do not rank models.

The [visual example](visual-example-20261113T184921Z/index.html) contains 15
plots for catalogue models whose full state is two-dimensional and a separate
projection of the fully checked 12-state source21 trajectory onto indexed
coordinates x3 and x9. It plots executed observed states; every full-dimensional
state and transition was checked before projection. Panels identify their
model, task, coordinates, units, source hash and source qualification. There is
no cross-model performance ranking.

Earlier attempts remain alongside the authoritative capture:

- [`capture-20261113T182201Z`](capture-20261113T182201Z/) is the first complete
  attempt before detailed adapter refusal diagnostics were added.
- [`capture-20261113T182620Z`](capture-20261113T182620Z/) reran only models 23,
  27 and 28 to capture those diagnostics; it confirmed the same refusals.

The final 35-case capture records the detailed failures directly. These earlier
attempts are retained as run history and are not merged into the final results.

## Task definitions

Model 21 uses the existing native source21 task adapter and literal OSQP
quadcopter MPC example: horizon 10, its printed running/terminal state costs,
control cost, reference and bounds, with 15 observed-state replans. The source
does not specify semantic units for every coordinate. The catalogue's nominal
0.1-second step is retained as an owner-catalogue assumption. The official
source model's external input is fixed to zero, as in the existing task; its
catalogue `G` channel remains in the model-data capture.

The other 34 models do not provide a common MPC horizon, objective or
actuator bounds. Each therefore uses a separately identified authored nominal
task: target zero; a fixed three-stage horizon at each of three replans;
diagonal state weights `1 / max(1, abs(initial_i))^2`; terminal weight five
times the running state weight; `R = 0.02 I`; no state bounds; and recorded
coordinate input bounds `[-1, 1]`. Those bounds and costs are authored task
choices, not source calibrations. When a catalogue entry supplies a nominal
external vector, the driver folds `E w` into the affine dynamics and applies
that same vector in the native plant step. When it supplies none, the task
explicitly fixes external input to zero. All original `E` matrices and the
catalogue source/synthetic labels remain in the capture.

The model catalogue retains source identifiers, printed model qualifications,
source hashes, time steps, coordinate names/units, and rank/calibration limits.
No empirical identification or physical nonlinear stability claim is made.

## Build and reproduce

The capture used GNU C++ 16.2.1 and CMake 3.31.6 in Release mode, with one
build thread. The manifest records the driver executable hashes, source-file
hashes, CMake cache and link-command hashes, the installed archive hashes, and
the SDK snapshot inventory digest. The running-history component archive
matches the component qualified at source commit
`c16a19dd900bc5e186273008f610a712dc177981`, with SHA-256
`12efd2001ee09b2154e6b18fc5a78e937dface24207bdd850a964f3beedcb00b`. The
capture also records the composed current-main 4ec package snapshot used for
the coherent full run. This is component provenance, not a qualification claim
for the entire installed SDK. The copied package is independently usable:
`CSLTargets.cmake` computes its import prefix relative to the config file
(lines 49–56), and the final link command resolves the model catalogue, history
compiler and HiGHS archives under the copied snapshot. The earlier initial
attempt used the original prefix; the coherent full capture does not rely on it.
The private source archive and research materials are not included.

With an installed CSL package that exports `CSL::highs_convex`,
`CSL::model_catalogue` and `CSL::nominal_quadratic_history`, build and capture
with:

```sh
cmake -S examples -B build \
  -DCSL_DIR="$CSL_PREFIX/lib/cmake/CSL" \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 1 \
  --target native_model_tracking native_discrete_models quadcopter_mpc
python scripts/reports/native_model_tracking_first_pass.py \
  --build build --sdk-snapshot "$CSL_PREFIX"
python scripts/reports/verify_native_model_tracking_first_pass.py \
  reports/algorithm-results/native-model-tracking-first-pass-v1/<capture> \
  --retry reports/algorithm-results/native-model-tracking-first-pass-v1/<capability-retry>
python scripts/reports/render_native_model_tracking_first_pass.py \
  --capture reports/algorithm-results/native-model-tracking-first-pass-v1/<capture> \
  --catalogue reports/algorithm-results/native-model-tracking-first-pass-v1/<capture> \
  --checks reports/algorithm-results/native-model-tracking-first-pass-v1/<independent-checks>
```

The supervisor makes a new capture directory and one attempt directory per
model before launching the native process. It applies a 60-second wall limit to
each authored case and 120 seconds to source21, writes stdout/stderr and status
receipts, and continues after a failure or timeout. Every captured output is
kept; later attempts use new directories.

## Delivery impact

This change adds consumer-side example and reporting sources. It changes no
public library API, dependency, exported target or installed package contents.
No library release or package update is needed. The example is built against
the existing installed public targets.
