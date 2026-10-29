# MPC-04 MaxCoordinateGame finite replanning pilot

This pilot applies the repository's C++ `csl.finite_action_minimax` algorithm as nominal and finite-catalogue minimax receding-horizon controllers on the source-derived `MaxCoordinateGame` environment from `imm-rl-lab/optimal_control/Environments`. The C++ driver calls the algorithm at each observation; the Python wrapper saves the records and renders the report.

No license is declared for the upstream repository; this report re-expresses its equations and parameters without copying source code. The pinned source is [`MaxCoordinateGame.py`](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/MaxCoordinateGame/MaxCoordinateGame.py). The source dynamics use state `(time, y, z)`, initial state `(0, 0.2, 0)`, held controls and disturbances in `[-1, 1]`, and terminal objective `max(|y|, |z|)`. Each reported step replays the source's 100 explicit-Euler substeps at `dt=0.1`. The benchmark adaptation scores a four-step episode, with control catalogue `{-1, +1}` and disturbance catalogue `{-1, +1}`. It exhausts all 16 full disturbance histories for each policy and horizon.

The nominal controller calls `finite_action_minimax` against a singleton zero disturbance. The robust controller passes the authored finite disturbance set to the same library algorithm. Each decision compares four signed linear terminal objectives and combines their per-plan worst values to minimize the source `max(|y|,|z|)` objective. The nominal controller plans against zero disturbance. The robust controller minimizes the worst terminal squared objective over every finite disturbance suffix. Both choose controls before the current disturbance is applied, replan from the observed full state, use authored action order for objective differences within a 1e-12 absolute tie tolerance, start with no controller memory, and apply `u=0` after a deadline or solver failure. The deadline is checked after each native solve returns; the current adapter does not interrupt an in-flight solve. The moving horizon uses two prediction stages at every decision and continues the source dynamics beyond the scored episode endpoint. The shrinking horizon uses `4, 3, 2, 1` stages and optimizes the scored endpoint. All reported episode scores use the original unsquared objective.

This is a short finite-catalogue adaptation, not a reproduction of the source's continuous-action four-second RL task. Results cover the authored disturbance catalogue only. The finite history and plan enumeration uses binary64 arithmetic and tolerance-based replay checks; it is not an exact-arithmetic certificate. The model has no additional state safety constraints, so constraint violations are always zero by construction. The experiment reports descriptive per-decision timings; it does not establish a speed winner, continuous-disturbance bound, recursive feasibility, stability, or globally optimal causal minimax policy. It compares the repository finite-action minimax adapter with a zero-disturbance nominal plan; the standard linear QP-MPC arm requested by MPC-04 remains outstanding, so this pilot does not complete that comparison.

## Run and check

```bash
cmake -S . -B build/mpc04 -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
  -DCSL_BUILD_MPC04_REPORT=ON -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF
cmake --build build/mpc04 --target csl_mpc04_max_coordinate_replanning
python3 -B scripts/reports/mpc04/max_coordinate_replanning.py \
  --output reports/algorithm-results/mpc04-max-coordinate-replanning-pilot-20261030 \
  --native-executable build/mpc04/csl_mpc04_max_coordinate_replanning
python3 -B scripts/reports/mpc04/check_max_coordinate.py \
  reports/algorithm-results/mpc04-max-coordinate-replanning-pilot-20261030/result.json
```

The saved result is generated through the C++ `csl.finite_action_minimax` adapter. The Python driver also includes a standalone finite-enumeration reference mode for independent comparison. The driver also forces deadline and solver-failure cases through the episode runner; each test confirms zero-control fallback, continued episode execution, and fallback counting. The driver also executes the two exact policy-gap fixtures from `docs/research/finite-policy-class-reference.md` through its actual remaining-plan/replanning loop before writing the report.

## Captured build evidence

`build.log` records the clean verbose Release rebuild of source commit `bf8ba9346293a322be3083f35e70ac713cbb95fd`. `build-config.json` records the exact CMake options, toolchain, binary path, and SHA-256. The native report and independent replay both passed after the rebuild. The per-decision timings in `result.json` come from this native binary; each is one observation within the same collection, not a performance ranking.

## Release impact

The driver and checker are private report tooling. They add no product API, build dependency, installed target, or package change. The report renderer uses Python standard-library modules only. The controller build links the existing `CSL::finite_action_minimax` target; no new dependency is introduced.


Offline bundle: [mpc04-max-coordinate-replanning-pilot.zip](mpc04-max-coordinate-replanning-pilot.zip).
