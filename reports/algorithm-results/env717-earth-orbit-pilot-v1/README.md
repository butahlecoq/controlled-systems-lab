# EarthOrbitalMotion finite-catalog control pilot

This report re-expresses the source equations from [`EarthOrbitalMotion.py`](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/EarthOrbitalMotion/EarthOrbitalMotion.py) at upstream commit `f4d76c60f4003f50954174e96eafd8e514bd5441` (blob `ce97d9d223a6ba6d02ce9a8f6a2fba26ef0fdd7d`). The repository has no declared license, so this report copies no source implementation.

## Model and adaptation

The physical state is `(time, radius, radial velocity, angle, angular rate)` in seconds, km, km/s, radians and radians/s. The source parameters are `G=6.67448478e-20`, Earth mass `5.9726e+24` kg, spacecraft mass `50.0` kg, `dt=100 s`, 100 RK4 substeps per decision and terminal time 2000 s. Each action has radial and angular components bounded by `[-0.5, 0.5]`. Running cost is `0.001 * norm(action) * dt`; the terminal cost is the Euclidean norm of radius error and `100000` times angular-rate error.

The source default starts on the 6900 km target orbit and therefore has a zero-control baseline. This pilot authors an initial radius of 7000 km, with zero radial velocity and the source constructor's circular angular rate at that radius. It retains the 6900 km target, 20 decision stages and 2000 second horizon. The continuous controls are replaced by nine grid vectors from `(-0.5, 0, 0.5)²`. A plan chooses one vector for each of three fixed blocks of 7, 7 and 6 stages. The complete `9³=729` open-loop catalog is exhaustively scored. The result is not a continuous-action optimum, feedback policy, minimax result or RL-training reproduction.

## Result

Independent Python replay verifies every one of the 729 plans. Selected plan index `0` has cost `65.232100494153` (source reward `-65.232100494153`), compared with zero-control cost `100.027657644173`. The selected block actions are `[[-0.5, -0.5], [-0.5, -0.5], [-0.5, -0.5]]`. The [phase-plane plot](orbit-phase-plane.svg) uses radius and angular rate, with both selected and zero-action trajectories and the target orbit.

The single-worker C++ Release driver reports median `56.701 ms` across 7 sequential complete catalog searches after 2 warmups (range `56.646–56.949 ms`); every plan completed successfully. It times plan decoding, source-equation propagation and scoring, not JSON export or independent verification. Each pass performs 1,458,000 inner RK4 steps. A separate, unreported process profile used 99.8% CPU, so the search is compute-bound by integration. This single small fixture has no comparison claim; timings are descriptive.

## Reproduction

Configure and build with the repository's pinned CMake/Ninja versions:

```sh
mise exec cmake@3.31.6 ninja@1.12.1 -- cmake -S . -B build/env717-report \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
  -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_ENV717_REPORT=ON
mise exec cmake@3.31.6 ninja@1.12.1 -- cmake --build build/env717-report \
  --target csl_env717_earth_orbit --parallel 2
python3 scripts/reports/env717/check_earth_orbit.py \
  build/env717-report/csl_env717_earth_orbit \
  --output reports/algorithm-results/env717-earth-orbit-pilot-v1
```

The checker independently enumerates and replays all plans, creates `result.json`, `figure-data.json`, `capture.json`, an HTML page, SVG figure and `SHA256SUMS`. The output remains scoped to the finite action and state adaptation above.
