# REVIEW-05 HORIZON-01 scalar horizon ladder

This is a bounded analytic pilot for the scalability report. It runs both
nominal strategies on the same scalar integrator at horizons 2, 4, and 8:

```text
x[t+1] = x[t] + u[t],  x[0] = 0,  0 <= u[t] <= 1
minimize x[T]
```

The exact minimum is 0, attained by the all-zero history. This pilot times only
`SynthesisWorkspace::run()` with `steady_clock`; process setup and launch are
recorded separately. It performs one excluded warmup pair and six alternating
measured pairs per horizon. Each strategy process has POSIX CPU, address-space,
and wall-clock limits. Attempts, stdout/stderr, copied fixtures, hashes,
environment, actual backend thread observations (or explicit null where
unavailable), exact checks, and summaries are preserved in the output bundle.
The manifest records host RAM, requested driver/backend widths, and per-process
CPU, address-space, and wall-clock enforcement.

## Build and run

From the repository root, configure with an installed CMake 3.31+ and Ninja:

```sh
cmake -S benchmarks/reporting/review05 \
  -B /tmp/csl-review05-horizon-build \
  -DCSL_SOURCE_ROOT="$PWD" -DCMAKE_BUILD_TYPE=Release -G Ninja
ninja -C /tmp/csl-review05-horizon-build csl_review05_horizon_ladder
python3 benchmarks/reporting/review05/run_horizon_ladder.py \
  --driver /tmp/csl-review05-horizon-build/csl_review05_horizon_ladder \
  --scenarios benchmarks/reporting/review05/scenarios \
  --output /tmp/csl-review05-horizon-results
python3 benchmarks/reporting/review05/check_horizon_ladder.py \
  --bundle /tmp/csl-review05-horizon-results
python3 benchmarks/reporting/review05/summarize_horizon_ladder.py \
  --bundle /tmp/csl-review05-horizon-results
python3 benchmarks/reporting/review05/render_horizon_ladder.py \
  --bundle /tmp/csl-review05-horizon-results
```

The checker verifies fixture hashes and dimensions, analytic zero objective and
incumbent, and the required initial-state, dynamics, and control-bound rows in
each candidate H-relation. Candidate relations can have different semantics;
this check does not claim either candidate is the complete feasible or optimal
history family. The result is numerical evidence for this one synthetic scalar
fixture. It does not establish a winner, speedup, algorithm scalability,
validated arithmetic, or historical reproduction. The fixture has one state,
so it has no 2D visual example.

Keep source, raw attempts, checks, and summary together when retaining a run.
The runner refuses a non-empty output directory so separate captures cannot
overwrite each other's evidence.
