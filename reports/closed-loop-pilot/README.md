# Closed-loop pilot: initial source-bound NMPC trajectories

These are one-off observed-state feedback trajectories on the immutable Lotka–Volterra, Earth-orbit, and fuel task contracts. At every original absolute stage, the selected local NLP policy receives the just-observed physical state, proposes one held action, and CSL executes exactly one original interval with adaptive RK4 step doubling. The original task hash, horizon, final time, cost schedule, and absolute stage remain bound through each derived one-step request.

The runs use a source-hashed admitted capability graph per task, selected from `docs/catalogue/closed-loop-pilot-capabilities-v1.json`. Each attempt stores its resolution receipt, prepared-controller receipt, per-stage requested and invoked module identities, full replay request/response, raw controls/states, and plots. The raw attempt ledger is `coverage-20261111T115150Z-05590667.json`; the independently checked all-three attempt directories are linked below. Failed and incomplete attempts are retained in the same task folders, including the initial orbit provider, serialization, and final-stage failures and the no-solve runner startup failure.

| Task | Attempt | Holds | Objective components (terminal + running = total) | Independent CSL replays | Sampled state checks |
|---|---|---:|---:|---|---|
| Lotka–Volterra | [`syn-nl-lv-01-20261111T114908Z-8dc20bed`](syn-nl-lv-01/attempts/syn-nl-lv-01-20261111T114908Z-8dc20bed/) | 30/30 | 0.06755422575467881 + 0.024130559408367985 = 0.0916847851630468 | common and tighter tolerance complete; objective difference 0; max endpoint difference 1.28e-13 | 601 CSL samples, zero state/control bound violations |
| Earth orbit | [`earth-orbit-20261111T114923Z-e26a58ff`](earth-orbit/attempts/earth-orbit-20261111T114923Z-e26a58ff/) | 20/20 | 63.89918301942375 + 1.3304813451979687 = 65.22966436462173 | common and tighter tolerance complete; objective difference 0; max endpoint difference 2.17e-19 | 401 CSL samples, zero state/control bound violations |
| Fuel | [`syn-nl-fuel-01-20261111T114928Z-bf3654d0`](syn-nl-fuel-01/attempts/syn-nl-fuel-01-20261111T114928Z-bf3654d0/) | 40/40 | 0.0002544882053355357 + 0.003571496881908354 = 0.0038259850872438897 | common and tighter tolerance complete; objective difference 8.67e-19; max endpoint difference 2.84e-14 | 801 CSL samples, zero state/control bound violations |

The state counts include the initial sample and 20 reported CSL samples for each original held interval. State bounds are checked over that numerical report grid; control bounds are checked on applied holds. These diagnostics do not certify between-sample bounds, robustness, reachability, or global optimality. Each episode includes one NLP solve and one independent CSL held-step execution per update. Solver predictions are saved separately from actual execution observations.

The plots show source-defined time/control views and 2D phase projections with start, end, and soft target markers. Fuel is shown in the source map `(q_ox,m_ox)` and `(q_f,m_f)` with source units. A single trajectory does not define a reachable set.

The saved-record reading layer is [`closed-loop-pilot-v1/index.html`](closed-loop-pilot-v1/index.html), with a minimal Lotka–Volterra 2D example at [`closed-loop-pilot-v1/example-2d.html`](closed-loop-pilot-v1/example-2d.html) and an offline ZIP at [`closed-loop-pilot-v1.zip`](closed-loop-pilot-v1.zip). The report and example are versioned from the committed raw attempts; independent review, main-only Pages deployment, and live URL/hash verification remain pending.

## Reproduce

The run used the qualified Linux CPython 3.11.14 environment described in [`benchmarks/reporting/mpc11/environment/README.md`](../../../benchmarks/reporting/mpc11/environment/README.md). Create a separate environment from the pinned wheel lock with an installed CPython 3.11.14; set `MPC11_VENV`, `MPC11_WHEELS`, and `PYTHON` to user-owned paths. The saved run manifests contain the local interpreter, package versions, host allocation, and binary hash; they are local execution receipts, not inputs to the portable setup instructions.

```sh
export MPC11_VENV="${MPC11_VENV:-$PWD/.venv-mpc11}"
export MPC11_WHEELS="${MPC11_WHEELS:-$PWD/.wheels-mpc11}"
python3.11 -m venv "$MPC11_VENV"
"$MPC11_VENV/bin/python" -m pip download --only-binary=:all: \
  --require-hashes -r benchmarks/reporting/mpc11/environment/requirements-linux-cp311.lock \
  --dest "$MPC11_WHEELS"
"$MPC11_VENV/bin/python" -m pip install --no-index --find-links "$MPC11_WHEELS" \
  --require-hashes -r benchmarks/reporting/mpc11/environment/requirements-linux-cp311.lock
export PYTHON="${PYTHON:-$MPC11_VENV/bin/python}"
"$PYTHON" -m pip check
cmake -S . -B build/closed-loop-pilot-945 -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/closed-loop-pilot-945 --target csl_mpc11_nonlinear_replay
"$PYTHON" benchmarks/reporting/closed_loop/run_closed_loop.py --task all \
  --bridge build/closed-loop-pilot-945/csl_mpc11_nonlinear_replay \
  --output-root reports/closed-loop-pilot
"$PYTHON" scripts/reports/render_closed_loop_pilot.py
```

The runner executes tasks sequentially with one numerical worker. The worker requests a 300-second wall timeout, 300 seconds CPU, and 8 GiB `RLIMIT_AS`; it applies the CPU/address-space limits to the worker process and terminates the worker process group on wall timeout. The host observed at run start is recorded in each run manifest. Checker processes use separate 5-second wall/CPU and 1 GiB `RLIMIT_AS` limits; RSS sampling is per process, not a machine-wide or child-tree memory cap. The suite has no machine-wide memory enforcement.

All timings are descriptive one-off pilot observations. This report makes no speed ranking or module-composition winner claim; the prescribed alternating Release/tuned repetitions and independent performance checker have not been run.

## Release and package impact

This adds a Python reporting runner and report artifacts only. It does not change the installed C++ library API, runtime dependencies, or packaged targets. The executable replay bridge is built from the existing source and is not installed as a new package target.
