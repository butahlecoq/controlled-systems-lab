# MPC-05 finite causal minimax pilot

This saved run compares the dependency-free finite Bellman solver with an independent HiGHS extensive-form scenario-tree model on correctness fixtures and the `TwoPointsOnParallelLines` differential-game adaptation.

The applied example has three 0.1-second stages, finite controls `(-2.5, 0, 2.5)`, finite disturbances `(-1, 0, 1)`, exact full-state observation, and terminal squared position gap. The two figure panels are the players' phase planes `(x1,x2)` and `(x3,x4)`. They show forward reachable polytopes, the terminal reachable sets, robust backward-winning nodes, forward/backward intersections, and the replayed worst-case trajectory. The plotted path was checked against the causal policy replay for this run.

The upstream environment uses continuous controls over 10 seconds. This three-stage finite adaptation is not an RL reproduction and does not establish a continuous-control or continuous-disturbance guarantee. The original source code is not copied.

The causal value is `14.58094225` and the open-loop fixed-plan value is `14.58094225`. These values coincide for this adaptation. The separate strict-gap fixture demonstrates a finite policy-class difference (fixed-plan value 2, causal value 1). The report includes no runtime or comparative performance claim.

Reproduce from the repository root with the recorded CMake Release build:

```sh
cmake --preset dev -DCSL_BUILD_MPC05_REPORT=ON
cmake --build build/dev --target csl_mpc05_causal_tree_report --parallel 2 2>&1 | tee /tmp/mpc05-build.log
python3 scripts/reports/mpc05/make_report.py \
  --executable build/dev/csl_mpc05_causal_tree_report \
  --build-dir build/dev \
  --build-log /tmp/mpc05-build.log \
  --output /tmp/mpc05-causal-tree
```

`capture.json` records source fingerprints, compiler, solver version, and host. `build.log` records the native driver build. `result.json` contains raw solver output; `figure-data.json` contains the independently reconstructed finite sets and policy witness; `projections.svg` is the two-panel figure. `index.html` is a standalone readable report.
