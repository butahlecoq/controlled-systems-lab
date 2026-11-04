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
  --output /tmp/csl-review05-horizon-results \
  --resource-receipts
python3 benchmarks/reporting/review05/check_horizon_ladder.py \
  --bundle /tmp/csl-review05-horizon-results
python3 benchmarks/reporting/review05/summarize_horizon_ladder.py \
  --bundle /tmp/csl-review05-horizon-results
python3 benchmarks/reporting/review05/summarize_resource_ladder.py \
  --attempts /tmp/csl-review05-horizon-results/attempts.jsonl \
  --output /tmp/csl-review05-horizon-results/resource-summary.json
python3 benchmarks/reporting/review05/render_horizon_ladder.py \
  --bundle /tmp/csl-review05-horizon-results
```

The checker verifies fixture hashes and dimensions, the required
initial-state/dynamics/control rows, the analytic terminal level `x[T] <= 0`,
and that every emitted H row contains the shared all-zero history. For this
fixture, those exact rational checks prove each candidate relation is the
singleton optimal-history set: `x[T] = sum(u[t])` and `u[t] >= 0` force every
control and state to zero. This is an independent fixture-specific oracle; it
does not establish general candidate-family completeness or validated
arithmetic. Timing summaries use only measured repetitions where both sides
pass this oracle; failures and inconclusive rows remain in the raw record.

The ladder varies horizon, relation coordinates, row counts, and nonzero H
coefficients while keeping the state and control dimensions at one. These are
coefficient counts, not allocated-byte measurements. It does not vary state
dimension or add a separate per-stage constraint-count axis. It does not establish a winner,
speedup, general complexity bound, or historical reproduction. The fixture is
scalar and has no supported 2D state-set visual example.

Keep source, raw attempts, checks, and summary together when retaining a run.
The runner refuses a non-empty output directory so separate captures cannot
overwrite each other's evidence.

`--resource-receipts` uses POSIX `wait4` for each isolated strategy process and
records user CPU, system CPU and peak RSS. The resource summary excludes each
horizon's warmup pair. These process-level readings include startup and setup;
they are not solver-phase allocations and are not added to `strategy_run_ns`.

## HORIZON-01 phase diagnostics

The horizon runner accepts `--phase-diagnostics` to collect OBS-03 spans in a separate instrumented capture. These values include instrumentation overhead and are diagnostic only; do not compare them directly with the uninstrumented timing ladder. The capture covers Strategy A forward/preimage/terminal-optimization spans, per-stage affine-image/Minkowski-sum/to-H/projection provider calls, and Strategy B’s joint program-build and LP program-run spans. Program-build timing covers joint H assembly and construction of the solver program object; it does not separate those two steps or expose LP factorization internals. Family-construction spans not called by candidate-mode executions remain explicitly unavailable. Per-stage family queries and witness-selector queries remain unmeasured. The helper `summarize_phase_ladder.py` validates each expected operation and stage while retaining unavailable spans.

Use a separate output directory for this run:

```sh
python3 benchmarks/reporting/review05/run_horizon_ladder.py \
  --driver /tmp/csl-review05-horizon-build/csl_review05_horizon_ladder \
  --scenarios benchmarks/reporting/review05/scenarios \
  --output /tmp/csl-review05-phase-results \
  --resource-receipts --phase-diagnostics
python3 benchmarks/reporting/review05/check_horizon_ladder.py --bundle /tmp/csl-review05-phase-results
python3 benchmarks/reporting/review05/summarize_phase_ladder.py \
  --attempts /tmp/csl-review05-phase-results/attempts.jsonl \
  --output /tmp/csl-review05-phase-results/phase-summary.json
python3 benchmarks/reporting/review05/summarize_resource_ladder.py \
  --attempts /tmp/csl-review05-phase-results/attempts.jsonl \
  --output /tmp/csl-review05-phase-results/resource-summary.json
python3 benchmarks/reporting/review05/summarize_horizon_ladder.py --bundle /tmp/csl-review05-phase-results
python3 benchmarks/reporting/review05/render_horizon_ladder.py --bundle /tmp/csl-review05-phase-results
```

## DIMENSION-01 vector pilot

The follow-up pilot crosses state/control dimensions 1 and 2 with horizons 2
and 4. Each stage has an explicit `[-T,T]^n` state box, controls are in
`[0,1]^n`, the initial state is zero, and the objective minimizes the sum of
terminal coordinates. Both strategy relations are checked against exact
rational plant, control, state-box, and terminal-objective rows before a timing
pair is reported. Strategy refusals and incomplete pairs remain in the saved
records. This fixture-specific oracle does not infer general family
completeness.

Build `csl_review05_dimension_ladder` in a clean Release tree, then run:

```sh
python3 benchmarks/reporting/review05/run_dimension_ladder.py \
  --driver /tmp/csl-review05-dimension-build/csl_review05_dimension_ladder \
  --scenarios benchmarks/reporting/review05/scenarios \
  --output /tmp/csl-review05-dimension-results \
  --resource-receipts
python3 benchmarks/reporting/review05/check_dimension_ladder.py \
  --bundle /tmp/csl-review05-dimension-results
python3 benchmarks/reporting/review05/summarize_dimension_ladder.py \
  --bundle /tmp/csl-review05-dimension-results
python3 benchmarks/reporting/review05/summarize_dimension_resource.py \
  --attempts /tmp/csl-review05-dimension-results/attempts.jsonl \
  --output /tmp/csl-review05-dimension-results/resource-summary.json
python3 benchmarks/reporting/review05/render_dimension_ladder.py \
  --bundle /tmp/csl-review05-dimension-results
```

## CONSTRAINT-01 authored state-row ladder

This slice holds the scalar integrator, dimension (1), horizon (2), initial
state, control box and objective fixed. It increases the authored state H-row
count from 2 to 4 to 8 per stage. Added inequalities are strictly redundant
over the common interval `[-2,2]`. One warmup and six alternating measured
pairs are retained per fixture, including failed or inconclusive results.

Build the driver in a clean Release tree, then capture, check and render:

```sh
cmake -S benchmarks/reporting/review05 \
  -B /tmp/csl-review05-constraint-build \
  -DCSL_SOURCE_ROOT="$PWD" -DCMAKE_BUILD_TYPE=Release -G Ninja
ninja -C /tmp/csl-review05-constraint-build csl_review05_dimension_ladder
python3 benchmarks/reporting/review05/run_constraint_ladder.py \
  --driver /tmp/csl-review05-constraint-build/csl_review05_dimension_ladder \
  --scenarios benchmarks/reporting/review05/scenarios \
  --output /tmp/csl-review05-constraint-results
python3 benchmarks/reporting/review05/check_constraint_ladder.py \
  --bundle /tmp/csl-review05-constraint-results
python3 benchmarks/reporting/review05/summarize_constraint_ladder.py \
  --bundle /tmp/csl-review05-constraint-results
python3 benchmarks/reporting/review05/render_constraint_ladder.py \
  --bundle /tmp/csl-review05-constraint-results
```

The exact fixture oracle verifies the common plant and constraints, attained
zero objective and feasibility of the zero history. It proves the unique
zero optimum only for these three fixtures; it does not establish general
candidate-family completeness. The timed region is only
`SynthesisWorkspace::run()`. This slice does not measure allocated memory or
internal phases, identify a source-level limiter, or support a speedup or
complexity claim.

The resource follow-up uses a POSIX `fork`/`exec`/`wait4` wrapper around each
isolated strategy process. It records child user CPU, system CPU and peak RSS
for every attempt while retaining the same exact output checker. These process
receipts cover the whole child and are separate from the solver-only timing;
they are descriptive and are not added to it.
