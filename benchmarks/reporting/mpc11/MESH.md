# Collocation mesh sensitivity

The `scenarios/mesh-ni2` variants change only collocation elements per original
hold interval from one to two and the controller identity. Plant equations,
physical grid, objective, observation, actuator bounds and execution/replay
integrators are unchanged. This is a different discretized controller problem;
a local solution is not a global optimum or a nonlinear enclosure proof.

Run the existing bounded worker on the explicit configuration directory:

```sh
python benchmarks/reporting/mpc11/run_nmpc.py \
  --scenario-directory benchmarks/reporting/mpc11/scenarios/mesh-ni2 \
  --bridge <BUILD_DIR>/csl_mpc11_nonlinear_replay --output <NEW_DIRECTORY>
python benchmarks/reporting/mpc11/check_nmpc_saved.py --bundle <NEW_DIRECTORY>
```

Keep every solve, failure and executed prefix. Compare controls, original
executed objective, independently replayed physical trajectories and local
stationarity/primal diagnostics with the one-element pilot. Setup, solve and
integration durations are descriptive pilot diagnostics, not timing rankings.
No core API or required dependency changes; no library release needed.

The bounded NI2 pilot and comparison are saved in
[`evidence/mesh-pilot-c0029ded`](evidence/mesh-pilot-c0029ded/README.md).
Both cases complete, all 70 saved NLPs rebuild, and fresh CSL native replays
match the saved numerical responses at both contract tolerances. The summary
keeps physical control/trajectory differences, original J_0 and local diagnostics
separate from descriptive single-pilot clocks. This does not prove mesh
convergence, global optimality or a comparative timing result.

The post-capture package checker at `3866dad1` validates full hexadecimal
capture/review revisions before file or Git operations, rejects symlinked
packages and missing source inventories, and authenticates copied review helpers
against their recorded Git commit. Git option injection and rebound copied
helper mutations are rejected. Five focused package/replay/initialization tests
pass. The original mesh archive, numerical records and comparison remain
unchanged; the capture/checker provenance is not relabelled as this later source.
