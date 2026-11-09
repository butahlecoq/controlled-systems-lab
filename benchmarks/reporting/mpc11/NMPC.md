# Execute a shrinking-horizon nominal nonlinear controller

The optional `nmpc.py` and `run_nmpc.py` consumer implements MPC-11 step 4 for
both canonical synthetic cases. It uses the locked do-mpc 5.1.2, CasADi 3.8.0,
IPOPT/MUMPS stack. It adds no core API, required dependency or release change.
The [controller contract](../../../docs/contracts/mpc11-synthetic-controller-study.md)
remains authoritative. NMPC does not use the affine-only trust region.

Run with the [locked environment](environment/README.md) and the existing
[independent replay bridge](NONLINEAR.md):

```sh
python benchmarks/reporting/mpc11/run_nmpc.py \
  --bridge <BUILD_DIR>/csl_mpc11_nonlinear_replay --output <NEW_OUTPUT_DIR>
python benchmarks/reporting/mpc11/check_nmpc_saved.py --bundle <NEW_OUTPUT_DIR>
CSL_MPC11_NMPC_BUNDLE=<NEW_OUTPUT_DIR> python -m unittest tests.reporting.test_mpc11_nmpc
```

The worker rebuilds the actual do-mpc Radau NLP with `N-j` intervals at update
`j`, and terminal time fixed at the original `T`. State variables are `z=x/scale`.
Controls retain physical units. Fuel stage references are the original absolute
midpoint schedule tail, with no evaluation after `T`. The terminal TVP slot
copies the last valid reference because the terminal objective does not use it.

## Preserve the authored discrete effort cost

In the pinned do-mpc source, `controller/_mpc.py` lines 1250–1259 add
`omega[k]*lterm_fun(...)` once per stage and add `mterm_fun` at the final stage.
There is no additional `dt` factor for this direct `lterm`. With nominal
`n_robust=0`, the single branch has weight one. The driver therefore sets
`lterm = running_weight/original_N * sumsqr((u-reference)/running_scale)`.
It sets input-change regularization to zero explicitly. It does not substitute
`set_rterm` input-change penalties for the authored input effort.

The short functional fixture evaluates the expanded objective on supplied
controls at a shortened horizon. Two controls equal to .05 with original
`N=3` produce `.05*2/3`, rather than a `dt`-scaled value or a denominator of two.
The fixture also solves an actual short stationary LV problem, checks the
shifted guess and initial observation, and executes a held zero input with
CVODES. A separate actual NLP with `max_iter=0` proves failed local convergence
is rejected. Fixture changes are not canonical study results.

## Bound every optimization state node

The driver reads Radau degree, elements, solver settings and physical bounds
from the scenario. It explicitly bounds every state slot, including initial
and terminal mesh states and final-interval collocation states. This matters
because do-mpc 5.1.2 `_update_bounds` bounds intermediate intervals and the
terminal mesh endpoint but omits the terminal interval's collocation slots.
Initial dummy collocation slots also receive bounds and reference guesses;
they do not represent additional physical trajectory samples.

The driver disables IPOPT bound relaxation (`bound_relax_factor=0`) to preserve
the authored actuator bounds. This numerical setting is recorded in the source,
not a change to physical limits. Local solve acceptance requires the native
success flag, finite values, scaled primal violation at most `1e-6`, and an
independently reconstructed objective difference at most `1e-8`. Inputs outside
physical limits by more than `1e-10` stop execution without clipping or fallback.
Every optimization node's physical state violation is retained separately.

## Keep guesses, local diagnostics and execution distinct

The initial state guesses use the declared reference at corresponding Radau
and mesh times, with the initial mesh state replaced by the actual observation.
At later updates the driver drops the first prior state/collocation interval
and input. It adds no terminal repeat. Each solve retains its full primal guess,
labels, numeric parameters, source solve hash and actual observation. The
pinned controller's `S` solver is called directly with its generated objective,
constraints and bounds, and explicit zero `lam_x0` and `lam_g0` arrays every time.
This avoids do-mpc's default reuse of prior dual multipliers. Access to the
pinned `_lb_opt_x` and `_ub_opt_x` numeric structs mirrors its own `solve` call.

Records retain the full returned primal, duals, constraints, expanded objective,
raw IPOPT log, return status, success flag and iteration diagnostics. The local
stationarity diagnostic is `norm_inf(grad(f)+J_g^T*lam_g+lam_x)` in scaled NLP
coordinates. It is a local numerical diagnostic, not global optimality evidence.

Only the first accepted control is applied. CVODES integrates the original
nonlinear ODE across that hold, with 20 output samples. Its endpoint is the
next exact full-state observation. Affine or NLP prediction states never replace
execution states. Setup, local solve, execution and external process durations
remain separate. Correctness pilots run sequentially, with one requested
numerical-library thread, 300-second process CPU and wall limits and an 8 GiB
address-space limit. They establish no comparative performance result.

The attempt record is rewritten after each complete executed hold. Failed
setup, solve, input-bound checks or execution stop before the next hold. Raw
logs and the last complete executed prefix remain available after process
termination. Partial histories have a running-cost prefix and no completed
`J_0`. The bridge consumes an explicitly declared prefix grid, with the full
unchanged scenario hash and original `N` bound alongside it. Independent RK4
runs at both contract tolerances consume only the held controls and initial
state. Prefix objective checks never change the running-cost denominator.

## Recheck saved evidence without solving again

`check_nmpc_saved.py` rebuilds each do-mpc transcription but performs no
optimization. It checks complete coefficients/bounds and symbolic objective
identity, absolute references, deterministic guesses, initial observations,
source solve hashes, supplied primal constraints, direct original objective,
local stationarity, applied first inputs, scaled/physical transforms and
independent replay associations. It recomputes sampled physical violations,
execution/replay differences and tolerance sensitivity. Validating this saved
record does not prove arbitrary trajectory rows solve the ODE; rerunning the
separate integration callbacks provides that check.

Figures, refined collocation meshes, alternating timing repetitions and final
publication remain later steps. No result here is minimax, globally optimal,
continuously safe or a reachable-set enclosure. Issue #607 remains open.
