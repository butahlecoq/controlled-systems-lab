# MPC-09 TwoParticleGame output-feedback pilot

This report adapts the source-attributed `TwoParticleGame` from the RL differential-game repository to an explicit finite output-feedback experiment. It uses the source RK4 flow at 0.2-second decision intervals, two initial states, three control and disturbance values, an additive-noise relative-position sensor, and a three-stage horizon. The noisy outputs enter the reviewed CSL affine observation and replay API. The source code is not copied; the pinned source and Apache-2.0 license are recorded in `result.json`.

The certainty-equivalent planner uses a full-history constrained least-squares state hypothesis. The set-based planner retains every state compatible with the complete noisy observation history. Both call CSL `finite_action_minimax`, execute only the first action, and replan after the next reading. The convex hulls used by that planner are exact for its convex terminal gap objective: the maximum is attained at vertices, which are the authored finite states and disturbance endpoints. Their lookahead does not branch on future observations.

The saved run covers 864 matched rows. The certainty-equivalent worst terminal gap is 0.680600659 (0 misses of the finite `gap <= 1` target); the set-based receding worst gap is 0.420600659 (0 misses). An independent complete finite observation-history dynamic program has worst gap 0.260000000 and optimal first action(s) [0.0]. The set-based receding planner uses open-loop future controls and is not the same controller as that feedback-tree reference. The verifier replays each state, released measurement, estimate, posterior, action, and terminal outcome. A separate missed/delayed sample replay shows that releasing a reading at stage two changes the next action from 0 to 3 in its declared finite fixture.

These are finite catalogue results. They do not reproduce the continuous-action RL training task, certify continuous observation noise, or establish global output-feedback optimality. No timing or speed comparison was made. The source differential-game reachability figure with forward and backward sets is available in the [TwoParticleGame minimax report](https://butahlecoq.github.io/controlled-systems-lab/env717-two-particle-minimax-31bb367020af7a94b1a7/).

Reproduce from the repository root with a Release build:

```sh
cmake -S . -B build/mpc09 -DCSL_BUILD_MPC09_REPORT=ON -DBUILD_TESTING=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/mpc09 --target csl_mpc09_output_feedback_report --parallel 2 2>&1 | tee /tmp/mpc09-build.log
python3 scripts/reports/mpc09/make_report.py \
  --executable build/mpc09/csl_mpc09_output_feedback_report \
  --build-dir build/mpc09 --build-log /tmp/mpc09-build.log \
  --output /tmp/mpc09-output-feedback
```

`result.json` contains all 864 trajectories per controller with observations, estimates, posterior states, actions and terminal outcomes. `figure-data.json` and `projections.svg` show both particle phase planes for a matched worst-case row. `capture.json`, `environment.json`, `build.log`, and `SHA256SUMS` preserve build and input provenance.
