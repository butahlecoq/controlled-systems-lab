# B09 A08 source-reference bundle

This is an independent finite-action reference derived from the local A08 MATLAB source revision and owner-approved objective variants. It is not a historical reproduction and does not restore any paper table-row mapping. See [the benchmark notes](../../../benchmarks/reporting/issue6/README.md#b09-a08-source-revision-fuel-reference) and [the scenario](scenario.json).

The figures show 2D projections of the 4D terminal set in flow coordinates `(x1,x3)` and stock coordinates `(x2,x4)`, plus a separate deterministic nonlinear replay. The reachable set is computed from the uncertain linear model; the replay is a trajectory, not a set boundary.

The independent Python oracle enumerates all 6,561 plans and all disturbance-corner histories, with constraints checked at every stage. Both lambda variants agree on objective and all minimizing action sequences. Raw timings include one excluded warmup and seven measured calls per objective. They support only descriptive single-adapter latency observations.
