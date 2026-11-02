# Pendulum-v0 finite-action pilot

This report re-expresses the pinned Gym v0.21.0 Pendulum dynamics; it does not copy the upstream implementation. The original `optimal_control` notebook points to Gym `Pendulum-v0` but does not pin a simulator version. This pilot adopts Gym v0.21.0 commit `c755d5c35a25ab118746e2ba885894ff66fb8c43` and records the exact environment and registry blobs.

## Model and scope

The physical state is `(theta, theta_dot)`. Gym uses `dt=0.05`, `g=10.0`, `m=l=1`, torque bound `[-2.0,2.0]`, and angular-speed bound `[-8.0,8.0]`. Each step clips the action, evaluates `angle_normalize(theta)^2 + 0.1*theta_dot^2 + 0.001*u^2` at the pre-step state, updates and clips angular velocity, then advances the angle using the clipped new velocity. The reward is the negative cost. Gym's `Pendulum-v0` wrapper has a 200-step time limit; this pilot uses only 10 steps.

The source reset samples random states. The pilot authors the reproducible initial state `[1.5, 0.0]` and restricts the continuous torque to `[-2.0, -1.0, 0.0, 1.0, 2.0]` N·m. It exhaustively evaluates all `9,765,625` fixed open-loop sequences. The reported minimum is exact only for this finite catalogue, horizon and binary64 transition implementation; it is not a continuous-action or full-horizon optimum and is not a minimax result.

## Results

The finite-catalogue plan has accumulated source cost `41.059357276952` and reward `-41.059357276952`. Its selected torques are `[-2.0, -2.0, -2.0, -2.0, -2.0, -2.0, -2.0, -2.0, -2.0, 0.0]` N·m; its terminal state is `(2.6800700083, 4.1185942430)`. The zero-torque baseline has cost `60.195793402956`. The saved position-velocity phase portrait is generated from these replayed trajectories.

The native Release enumerator reports median `2498.552 ms` per complete catalogue search across `7` sequential repetitions after `2` warmups (range `2488.720–2517.126 ms`). The timed region includes decoding and propagation of every plan; it excludes JSON serialization, independent Python verification and report rendering. This is one implementation and one fixture, so no comparative performance conclusion is made. Raw repetitions and host/compiler data are in `result.json` and `capture.json`.

## Provenance and reproduction

- Upstream environment notebook: https://github.com/imm-rl-lab/optimal_control/tree/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/Pendulum/Pendulum.ipynb (blob `db58eb7779d84a3a5032288734d61f6d6dcdba09`).
- Adopted Gym source: https://github.com/openai/gym/blob/c755d5c35a25ab118746e2ba885894ff66fb8c43/gym/envs/classic_control/pendulum.py (blob `10ced4d43d218fbf0bb344b3bbc006fcaa7f8362`); registry: https://github.com/openai/gym/blob/c755d5c35a25ab118746e2ba885894ff66fb8c43/gym/envs/__init__.py (blob `a90b0370730e74d783971a1a3f0771c5a2fb572e`).
- Upstream Gym license at this commit: MIT. The upstream `optimal_control` repository has no declared license; this report re-expresses equations and copies no source implementation.
- Build and run: `cmake -S benchmarks/reporting/env717/pendulum-build -B build/env717-pendulum -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON`, `cmake --build build/env717-pendulum --target csl_env717_pendulum --parallel 2`, then `python3 scripts/reports/env717/check_pendulum.py build/env717-pendulum/csl_env717_pendulum --output reports/algorithm-results/env717-pendulum-pilot-v1`.
- The complete raw record, independently replayed optimum and checksums are saved with this report.
