# CartPole finite-action pilot

Upstream source commit: `f4d76c60f4003f50954174e96eafd8e514bd5441`. The source environment notebook is blob `21d1122b701df85e21b5225fdbd42ff9f3bd702e`; the DCEM learning notebook is blob `5af9324376c342da177a411394730ccc3f7edd5b`; `OneAgentSolver.py` is blob `87485e23497e286022d76c6f2e70e0469aa18584`. The upstream calls Gym `CartPole-v1` but records no Gym package pin. This report adopts Gym v0.21.0 at `c755d5c35a25ab118746e2ba885894ff66fb8c43`. The pinned solver unpacks the legacy four-value step result, which is the reason for this version selection. The Gym CartPole source file blob is `e11adcba6f413017e8661e8990dde668a63a129c` and its registry blob is `a90b0370730e74d783971a1a3f0771c5a2fb572e`.

This report independently re-expresses, rather than copies, the source equations. The upstream repository declares no license in its metadata; the adopted Gym source is MIT licensed. Initial state is the exact zero vector, the midpoint of the source reset support `[-0.05,0.05]^4`. The adaptation enumerates all `16384` left/right open-loop plans for `14` steps or until the first strict position/angle termination. Every executed action receives reward `+1`, including the first terminating action. The maximum is `14` and `13136` plans attain it. The selected smallest-index witness is plan `3` with `14` executed actions.

The figure shows exact finite-prefix point catalogs in `(cart position, cart velocity)` and `(pole angle, pole angular velocity)`, including first-termination states and one maximum-reward trajectory. The result file preserves all plan outcomes; the Python checker independently replays every plan and constructs the figure data.

This finite, deterministic, 14-step open-loop result is not a learned policy, minimax result, or solution of the original 500-step RL task. The notebook's learned episode scores are not compared because its Gym dependency is not pinned and those scores use different policy semantics.

## Reproduce

```sh
cmake -S benchmarks/reporting/env717/cartpole-build -B build/env717-cartpole -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/env717-cartpole --config Release --target csl_env717_cartpole
python3 scripts/reports/env717/check_cartpole.py build/env717-cartpole/csl_env717_cartpole --repetitions 9
python3 scripts/reports/env717/capture_cartpole_report_generation.py --executable build/env717-cartpole/csl_env717_cartpole --checker scripts/reports/env717/check_cartpole.py --profile reports/algorithm-results/env717-cartpole-pilot-v1/profile.json --output build/env717-cartpole/report-generation.json
python3 scripts/reports/env717/check_cartpole.py build/env717-cartpole/csl_env717_cartpole --repetitions 9 --report-generation-evidence build/env717-cartpole/report-generation.json --limiter-profile reports/algorithm-results/env717-cartpole-pilot-v1/profile.json --output build/env717-cartpole/reproduction
```

Enumeration timing includes allocation, all `221728` completed state transitions, termination checks, and reward evaluation for all plans. Five warmups preceded nine measured Release calls; the single-host median and range are descriptive only.

The full report collection was separately timed over `5` runs after `1` discarded warmup, with median `1564.749 ms` (range `1537.527–1590.888 ms`). This includes the native collector, independent full-catalogue replay, projection generation and report file writes; it excludes configure/build.

The limiter diagnostic uses GNU gprof 2.47 on a separate Release `-pg -fno-inline` build. Two 300-repetition profiles used 10 ms samples and placed `75.81–77.65%` of sampled self CPU in `advance_state`. The profiles are coarse and instrumented; call-arc totals were not used because they disagree with independently verified transition totals. `profile.json` and `report-generation.json` preserve the evidence and limits.
