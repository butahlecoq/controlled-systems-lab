# MPC-04 MaxCoordinateGame finite replanning pilot

This pilot applies nominal and finite-catalogue minimax receding-horizon control to the source-derived `MaxCoordinateGame` environment from `imm-rl-lab/optimal_control/Environments`.

The pinned source is [`MaxCoordinateGame.py`](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/MaxCoordinateGame/MaxCoordinateGame.py). The source dynamics use state `(time, y, z)`, initial state `(0, 0.2, 0)`, held controls and disturbances in `[-1, 1]`, and terminal objective `max(|y|, |z|)`. Each reported step replays the source's 100 explicit-Euler substeps at `dt=0.1`. The benchmark adaptation scores a four-step episode, with control catalogue `{-1, +1}` and disturbance catalogue `{-1, +1}`. It exhausts all 16 full disturbance histories for each policy and horizon.

The nominal controller plans against zero disturbance. The robust controller minimizes the worst terminal squared objective over every finite disturbance suffix. Both choose controls before the current disturbance is applied, replan from the observed full state, use authored action order for exact ties, start with no controller memory, and apply `u=0` after a deadline or solver failure. The moving horizon uses two prediction stages at every decision and continues the source dynamics beyond the scored episode endpoint. The shrinking horizon uses `4, 3, 2, 1` stages and optimizes the scored endpoint. All reported episode scores use the original unsquared objective.

This is a short finite-catalogue adaptation, not a reproduction of the source's continuous-action four-second RL task. Results cover the authored disturbance catalogue only. The finite history and plan enumeration uses binary64 arithmetic and tolerance-based replay checks; it is not an exact-arithmetic certificate. The model has no additional state safety constraints, so constraint violations are always zero by construction. The experiment reports descriptive per-decision timings; it does not establish a speed winner, continuous-disturbance bound, recursive feasibility, stability, or globally optimal causal minimax policy.

## Run and check

```bash
python3 -B scripts/reports/mpc04/max_coordinate_replanning.py \
  --output reports/algorithm-results/mpc04-max-coordinate-replanning-pilot-20261030
python3 -B scripts/reports/mpc04/check_max_coordinate.py \
  reports/algorithm-results/mpc04-max-coordinate-replanning-pilot-20261030/result.json
```

This is a standalone Python reference pilot with exhaustive finite-plan enumeration; it is not yet wired to the repository's C++ `finite_action_minimax` adapter. It provides an initial scenario result and replay oracle for that integration. The driver also forces deadline and solver-failure cases through the episode runner; each test confirms zero-control fallback, continued episode execution, and fallback counting. The driver also executes the two exact policy-gap fixtures from `docs/research/finite-policy-class-reference.md` through its actual remaining-plan/replanning loop before writing the report.

## Release impact

The driver and checker are private report tooling. They add no product API, build dependency, installed target, or package change. Python standard-library only.


Offline bundle: [mpc04-max-coordinate-replanning-pilot.zip](mpc04-max-coordinate-replanning-pilot.zip).
