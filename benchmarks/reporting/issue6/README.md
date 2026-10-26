# B06 finite-action reference

This reference combines the L09 displayed model with the owner's 2026-10-25
confirmation that each disturbance component ranges independently over
`[-1,1]` at each of five discrete stages. The article does not print this
numerical disturbance set, so this case is not a historical reproduction.
`B06-historical` remains unchanged and non-executable.

The project runner calls the existing `finite_action_minimax` implementation.
The separate integer-scaled exhaustive oracle enumerates every action sequence
and every disturbance-corner history. It uses exact integer state coordinates
scaled by 1500 and an objective-squared denominator of 9,000,000. Together,
these give an exact reference for the explicitly stated rational case. The
solver measurement itself uses the project's binary64 numerical assurance.

The saved run found one minimizing plan, the printed L09 sequence
`(-0.3, 1, 0, 0, 0.3)`, with exact squared objective
`1100939049/9000000` and norm `11.060133859949435`. Seven Release calls had
median `1,196,536,901 ns`, range `1,188,696,999–1,253,915,262 ns`, and no
failures. The cumulative process peak RSS was `107,936 KiB`. The report and
flow/stock projections are in
[`reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46`](../../../reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46/index.html).
No limiter profile was collected; this single-adapter result makes no speedup
claim.

## Reproduce

Configure and build a clean Release driver:

```sh
cmake -S . -B build/issue6-b06 -DBUILD_TESTING=OFF \
  -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF \
  -DCSL_BUILD_ISSUE6_B06_REPORT=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/issue6-b06 --target csl_issue6_b06_report csl_issue6_b06_phase_report csl_issue6_b06_exact_oracle --parallel 4
```

Capture the oracle, one geometry record, and one excluded warmup plus seven
measured single-call observations:

```sh
build/issue6-b06/csl_issue6_b06_exact_oracle > exact-oracle.json
build/issue6-b06/csl_issue6_b06_report --geometry > geometry.json
build/issue6-b06/csl_issue6_b06_report --measure 7 > raw-runs.jsonl
python3 scripts/reports/issue6/check_capture.py <result-directory>
python3 scripts/reports/issue6/render.py <result-directory>
```

The measurement interval includes construction of the immutable solver request
and the public solver call. It excludes process startup, serialization, exact
oracle execution, figure generation, and HTML rendering. The runner verifies
all 3,125 plans and records 3,200,000 terminal-vertex evaluations per call.
Seven observations describe this one case; they do not support a comparison,
speedup, or general scalability claim. The `[-1,1]^2` disturbance set and the
interpretation of `-10/T` with discrete `T=5` are explicit reference-case
inputs, not recovered historical run details.

## B09 A08 source-revision fuel reference

`b09-a08-source-revision-reference-v1` is an independent C++ implementation of
the four-stage affine model transcribed from the local `Minmaxclosedloop.m`
revision (SHA-256 `06c2f750a2c7deb01dbc457185378b440f8ba134216d7ab0762b8b28229ba2d9`)
and its `Minmaxopenloop.m` planner (SHA-256
`59daeacc7727cb7ff5e0090368d76e401fa4d0c874ef359a97d6acb722467aa6`). The
source paper is L13 (`Электронная версия_статьи.pdf`, SHA-256
`4556046bb893a9a7a8c7b8489673dc95315d8ea49bf37e787a59d897c8a7a70e`). These
identities do not establish which source revision generated a printed paper
row, and this is not a historical reproduction.

Both owner-selected objective variants are run:

```text
J_lambda(x) = sqrt((x1-60)^2 + x2^2 + (x3-24)^2 + x4^2
                   + lambda*(x2-2.5*x4)^2), lambda in {0,1}.
```

The solver minimizes the equivalent squared objective. The objective is evaluated
on the four-state terminal reachable set for all `9^4 = 6,561` fixed action
plans. Each stage uses four corners of `[-1,1]^2`; the 4D set is projected to
flows `(x1,x3)` and stocks `(x2,x4)` for the figures. The nonlinear red path is
a deterministic plant replay of one representative minimizing open-loop plan.
A second trajectory replans with the finite-horizon minimax solver at each
observation. This is receding-horizon control, not a global causal-policy
optimality claim. The lower plot shows both stock trajectories by model stage.
Neither path is the uncertain reachable-set boundary. The plotted points are
stored V-representation rows; duplicate coordinates can overlap, and the rows are
not asserted to be exposed extreme points.

An independent Python oracle directly enumerates every plan and every disturbance
corner history, checking all four state constraints and the terminal cost. It
agrees on the complete minimizing sequence family: four plans for lambda 0 and
six for lambda 1. The squared minima are 2,518.0254696696175 and
13,408.277178974853, respectively. The numerical solver uses a `1e-8` absolute
tolerance in squared objective when retaining near-optimal plans.

Seven alternating Release measurement rounds per objective use one excluded
warmup in each separately launched process. The public call includes request
construction and minimax solution, but not process startup,
serialization, independent enumeration or figure rendering. On the recorded
8-thread Ryzen 5 3550H host, medians were 242.333 ms (lambda 0; range
234.719–251.626 ms) and 240.476 ms (lambda 1; range 234.693–242.919 ms);
complete raw records are in the [B09 result bundle](../../../reports/algorithm-results/b09-a08-source-reference-4818ddde/index.html).
These are single-adapter observations, not a speed comparison or scalability
claim. No source-mapped limiter profile was collected. Assurance is numerical;
no validated-arithmetic or historical row claim is made.

Both nonlinear replay terminal states are evaluated with the same `J_lambda`
criterion. The saved geometry rows report the open-loop and receding-horizon
values separately from the robust predicted minimax value. The exhaustive
corner-history Python checker independently recomputes both replay costs and
checks every open-loop minimizer. Each terminal V representation stores 256
rows: 256 distinct points for lambda 0 and 240 for lambda 1. These are stored
representation points, not a count of exposed extreme points. Linux process peak
RSS is the Linux process high-water mark sampled for measured calls after
minimax result assembly and before optional geometry and replay calculations. It
excludes nonlinear replay and receding-horizon replanning, and is not per-stage
memory or per-call allocation accounting.

Build and reproduce after configuring a Release tree with
`-DCSL_BUILD_ISSUE6_B09_REPORT=ON`:

```sh
build/csl_issue6_b09_report --lambda 0 --geometry > lambda0-geometry.json
build/csl_issue6_b09_report --lambda 1 --geometry > lambda1-geometry.json
python3 benchmarks/reporting/issue6/b09_measure_alternating.py build/csl_issue6_b09_report --rounds 7 --output raw-runs.jsonl
python3 benchmarks/reporting/issue6/b09_independent_oracle.py oracle.json lambda0-geometry.json lambda1-geometry.json
python3 benchmarks/reporting/issue6/b09_render_projection.py lambda0-geometry.json --output lambda0-projections
```

The saved projections are included with raw solver rows, independent oracle
output, provenance and checksums in the B09 result bundle.

## OBS-06 phase timing captures

The phase captures measure the same B06/B07/B09 model cases. They expose the
actual minimax call tree: validation, per-plan setup and propagation, each
stage V materialization, objective evaluation, record assembly and result
selection. Not-called phases remain explicit; `span_count` is planned records,
while `call_count` excludes not-called records. Raw wall ticks retain their
clock period, and CPU/worker metrics stay explicitly unavailable where no CPU
clock or worker span was supplied. Inclusive and exclusive sums are grouped by
operation; totals across different operations are not elapsed wall time.

B06 phase timing uses a separate report executable so the original
`b06_finite_minimax.cpp` source hash remains fixed for historical B06 captures.

Run after building the three Release report targets:

```sh
build/csl_issue6_b06_phase_report --phase-timing > b06-phase.json
build/csl_issue6_b07_report --phase-timing > b07-phase.jsonl
build/csl_issue6_b09_report --lambda 0 --phase-timing > b09-lambda0-phase.json
build/csl_issue6_b09_report --lambda 1 --phase-timing > b09-lambda1-phase.json
python3 benchmarks/reporting/issue6/fuel_phase_summary.py \
  b06-phase.json b07-phase.jsonl b09-lambda0-phase.json b09-lambda1-phase.json \
  --output fuel-phase-summary.csv --provenance capture-provenance.json
```

The summary script regenerates CSV and Markdown tables from the raw spans. The
capture manifest records executable hashes and environment facts; each raw row
records its source commit, driver hash and scenario/fixture hash. The paired
instrumentation checks report baseline and instrumented call intervals and
verify identical successful outputs. B06 also checks an unsupported capacity
failure pair and retains its failure-path spans.

The figures for these fuel models are available in the existing result
bundles: [B06 4D terminal projection](../../../reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46/terminal-projections.svg),
[B07 flow and stock projections](../../../reports/algorithm-results/b07-owner-approved-eight-case-v1/projections.svg),
and [B09 lambda 0](../../../reports/algorithm-results/b09-a08-source-reference-4818ddde/projections-lambda0.svg)
and [lambda 1](../../../reports/algorithm-results/b09-a08-source-reference-4818ddde/projections-lambda1.svg).
Each plots a 2D projection of saved terminal rows from the 4D model; B09 also
shows the nonlinear replay traces. These are explanatory geometry figures, not
timing plots or strategy winner claims.
