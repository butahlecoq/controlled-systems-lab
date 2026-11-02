# Unlimited Bolza Problem: analytic reference and finite catalogue

This report re-expresses the upstream double-integrator equations and analytic feedback basis. It does not copy upstream source code. The pinned source has no declared license. The main differential-game reachability example remains [TwoPointsOnParallelLines](https://butahlecoq.github.io/controlled-systems-lab/env717-two-points-33ebdad360671940fb54/index.html).

## Model and scope

The source state is `[time, position, velocity]` with `time'=1`, `position'=velocity`, and `velocity'=control`. Each 0.1-second outer step holds one action over ten explicit Euler substeps of 0.01 seconds. The source control is unbounded. Its reward is the negative of `0.1*(position^2 + control^2)` evaluated at the pre-step state, plus terminal reward `-position(T)-velocity(T)` when time reaches one second. The report minimizes the corresponding positive cost.

The upstream initial physical state defaults to `(0,0)`, which makes a poor visual example. This pilot authors `(position, velocity)=(1,0)`. The finite-action comparison restricts actions to `(-2, -1, 0, 1, 2)` over ten stages; it is an exact optimum only for this 5^10 finite catalogue and the source Euler map. It does not solve the original unbounded-control problem.

## Results

The re-expressed continuous analytic feedback reference has objective `1.135557418637` and terminal state `(0.4966327941, -0.8637835718)`. The policy is independently checked against the Euler–Lagrange residual and terminal costate conditions, and its objective is integrated with RK4.

Sampling that policy once per outer step and holding it over the ten source Euler substeps gives objective `1.184807307433`. Exhaustive enumeration of all `9,765,625` finite action sequences gives catalogue minimum `1.261827125000`, controls `[-1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0, -1.0]`, and terminal state `(0.5050000000, -1.0000000000)`. A separate exact-integer dynamic program over the finite state graph verifies the catalogue result.

The phase-plane plot shows position `x` against velocity `v`; the three curves use different solution tracks and are not an algorithm ranking on a matched guarantee. The retained runtime is the native exhaustive finite-catalogue solver call only: median `104,862,960.0 ns` across `28` sequential calls (range `104,348,854–113,685,932 ns`). The excluded child-process profile recorded 99.0% CPU use, 26052 KiB maximum RSS, and no available perf/strace/pidstat profiler; details are in `capture.json`. It is descriptive for this one implementation; no competing solver, end-to-end latency, or performance winner is claimed.

## Provenance and reproduction

- Upstream environment: [https://github.com/imm-rl-lab/optimal_control/tree/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/UnlimitedBolzaProblem](https://github.com/imm-rl-lab/optimal_control/tree/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/UnlimitedBolzaProblem)
- Environment source blob: `1b26ba326fbbce4c31a29f211b97dd3981a227e9`; analytic-agent blob: `d426400cab0b0a18d9819acea84d082991899a06`.
- Driver, algorithm-source fingerprint and repository commit: `result.json`.
- Raw runtime blocks and host load data: `capture.json`.
- Figure data and checksums: `figure-data.json`, `SHA256SUMS`.

Build and run the native driver:

```sh
cmake -S . -B build/env717 -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCSL_DEPENDENCY_PROBES=OFF -DCSL_BUILD_ENV717_REPORT=ON
cmake --build build/env717 --target csl_env717_unlimited_bolza --parallel 4
python3 scripts/reports/env717/check_unlimited_bolza.py build/env717/csl_env717_unlimited_bolza --output reports/algorithm-results/env717-unlimited-bolza-pilot-v1
```

The report is supplementary single-controller coverage for #717. It is not an RL training reproduction, a continuous unbounded-control optimum from CSL, or a comparison of reachability-set representations.
