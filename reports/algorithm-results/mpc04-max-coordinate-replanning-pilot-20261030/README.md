# MPC-04 MaxCoordinateGame closed-loop pilot

This report compares two repository finite-action planners with two linear QP MPC controllers on the source-derived `MaxCoordinateGame` differential-game environment. Each controller observes the full state, selects a control, then the current disturbance is applied. The controller replans at the next observation. Every run starts from the same initial state with no controller memory or warm start.

The upstream source is [`MaxCoordinateGame.py`](https://github.com/imm-rl-lab/optimal_control/blob/f4d76c60f4003f50954174e96eafd8e514bd5441/Environments/MaxCoordinateGame/MaxCoordinateGame.py). Its state is `(time, y, z)`, dynamics are `y'=z+v`, `z'=-y+u`, the initial state is `(0, 0.2, 0)`, and its terminal objective is `max(|y|,|z|)`. The report re-expresses those equations and parameters; it does not copy upstream source code. The upstream repository declares no license.

## Compared controllers

| Controller | Control set | Disturbance model | Plan and terminal objective |
|---|---|---|---|
| Nominal finite action | `{-1,+1}` | Zero disturbance | Exhaustive remaining-plan minimization of terminal `max(|y|,|z|)^2` |
| Finite minimax | `{-1,+1}` | Finite set `{-1,+1}` | One common open-loop plan minimizes the worst terminal squared objective over every suffix |
| Nominal linear QP | Continuous `[-1,1]` | Zero disturbance | HiGHS QP minimizes the same terminal squared max-coordinate objective through a scalar epigraph |
| Finite-history robust QP | Continuous `[-1,1]` | Finite set `{-1,+1}` | One common open-loop plan is constrained against every complete finite disturbance suffix and minimizes the same terminal objective |

Each controller is run with a shrinking horizon (`4,3,2,1`, ending at the scored terminal time) and a moving two-stage horizon. The moving horizon continues the source dynamics beyond the episode endpoint. The continuous QP and discrete-action controllers have different control domains; their result rows are not a same-domain optimality comparison. The robust QP is a finite-history open-loop plan followed by replanning, not an in-horizon scenario-tree feedback policy.

The benchmark scores 16 complete four-step disturbance histories per controller and horizon: 128 episodes and 512 transitions. It runs five fresh native processes with controller order alternated forward/reverse. The independent checker replays the source's 100 explicit-Euler substeps, recomputes selected-plan objectives and episode outcomes, checks the analytic one-step QP solution, and verifies the recorded HiGHS primal/dual residuals against their stated tolerances. Native deadline and solver-failure fixtures exercise the same C++ episode loop and check zero-control fallback, fallback counts, and continued execution. The two authored policy-gap fixtures run through the actual finite replanning loop.

The SVG shows executed histories in the `(y,z)` phase plane and the corresponding control/disturbance timeline. It is a state-space/control plot for this three-state source model; the separate four-state fuel/environment visualizations use the `(x1,x2)` oxidizer and `(x3,x4)` fuel projections.

## Evidence limits

This is a finite-action and continuous-control QP adaptation of a source RL environment, not a reproduction of its continuous-action four-second RL experiment. Disturbance guarantees cover only the enumerated binary histories. Arithmetic and replay checks use binary64 with explicit tolerances. There are no state safety constraints in this slice. The report establishes finite-episode outcomes only; it makes no continuous-disturbance, globally optimal causal minimax, recursive-feasibility, stability, scalability, speedup, or performance-winner claim. Timing is descriptive. A source-mapped limiter profile was unavailable, so performance interpretation is inconclusive.

## Reproduce

```bash
cmake -S . -B build/mpc04 -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
  -DCSL_BUILD_MPC04_REPORT=ON -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=OFF
cmake --build build/mpc04 --target csl_mpc04_max_coordinate_replanning --parallel 2
python3 -B scripts/reports/mpc04/max_coordinate_replanning.py \
  --output reports/algorithm-results/mpc04-max-coordinate-replanning-pilot-20261030 \
  --native-executable build/mpc04/csl_mpc04_max_coordinate_replanning
python3 -B scripts/reports/mpc04/check_max_coordinate.py \
  reports/algorithm-results/mpc04-max-coordinate-replanning-pilot-20261030/result.json
```

## Captured build and release impact

`capture.json`, `environment.json`, `build-config.json`, and `build.log` identify the source commit, report/checker and native driver, executable SHA-256, Release toolchain, HiGHS provider, host, configuration, and timing scope. `result.json` also records the implementation commit and executable hash. Per-decision solve samples and the five process repetitions are retained in the result. The latency interval includes planner problem construction and solve calls; process startup, provider setup, JSON output, replay, and rendering are separately recorded or excluded as stated in the data.

This report adds private benchmark tooling and an optional target. It adds no public API, installed target, new dependency, or package change; HiGHS is an existing optional dependency and must be enabled for this report target.

Files: [standalone report](index.html), [raw result](result.json), [phase-plane and control plot](trajectory.svg), and [offline payload checksums](BUNDLE-SHA256SUMS). The outer directory also contains `mpc04-max-coordinate-replanning-pilot.zip`; its archive hash is listed in the adjacent `SHA256SUMS` file.
