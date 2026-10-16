# Issue #3 finite-action minimax report harness

This stacked harness exercises `finite_action_minimax` from frozen source commit
`994f3ee4310b4087d289e2eb02adbdb9dfd97827` (PR #351). The driver is a
non-installed Release executable. Its exact harness commit is embedded at CMake
configuration time and emitted on every raw JSONL row. The branch contains no
accepted measurement or published report; an independent review of the fixed
harness head precedes collection.

## Fixed cases

| Case | Public result checked on every call |
|---|---|
| `l19` | Two one-step actions `0,1`, disturbance vertices `0,1`, objective `(x-1)^2`; sampled values `1,0,1`, both action worst values `1`, maximizers `0,2` and four total terminal evaluations. The middle point is stationary and below either endpoint maximum. |
| `integrator` | Two one-step plans; worst values `1,4`, unique minimizer index `0`. |
| `all_infeasible` | Two plans each violate stage-one robust safety; no optimum is published. |
| `empty_catalogue` | Distinct empty-action status for a positive horizon. |
| `no_scenarios` | Empty disturbance set has no adversarial trajectory to score. |
| `unsupported` | Plan limit one rejects a two-plan catalogue without a partial optimum. |
| `cancelled` | Pre-cancelled search returns `OperationStopped`, with no partial optimum. |
| `b08_rounded` | Entire displayed-data four-step catalogue: 625 plans, 256 corners per plan, 160,000 checked vertices, minimum approximately `67.150601101407`, minimizing plan indices `17,33,129` at absolute tie tolerance `1e-8`. |

B08 is the displayed rounded linear model from L04, as independently derived in
`docs/research/b08-displayed-exact-audit.md`. This driver uses binary64 and
numerical assurance. The reference report's `67.12`, original unrounded arrays,
nonlinear trajectory, historical timing and validated rounding remain separate.
The catalogue optimum is for open-loop fixed sequences, not a feedback policy.

## Functional gate

```powershell
$cmake = 'C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
& $cmake -S . -B build/issue3-report -G 'Visual Studio 17 2022' -A x64 -DBUILD_TESTING=ON -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_ISSUE3_REPORT=ON
& $cmake --build build/issue3-report --config Release --target csl_issue3_finite_action_report --parallel 4
python scripts/reports/issue3/check_smoke.py build/issue3-report/Release/csl_issue3_finite_action_report.exe
```

The smoke emits eight checked JSONL rows and is functional evidence, not
accepted performance data. Configure again at the reviewed clean harness commit
before any measurement so the embedded identity matches the executable.

## Measurement protocol and pending gates

After independent source and harness review, `collect.py` authenticates a clean
exact reviewed head, the allowlisted source-to-harness delta, configured CMake
Release target and dependency graph, NDEBUG/C++20 flags, fresh build, executable
hash and embedded source/harness/fixture IDs before running `--measure 7`.
`--preflight-only` exercises these checks without measurement. Accepted capture
requires a separate review-evidence JSON file naming the exact reviewed head
and two independent review URLs. It saves raw stdout/stderr and process status
before checking the rows, retaining failed and partial attempts. It does not
render or publish a report.

Measurement then uses one excluded warmup and seven measured rounds in alternating
fixture order. Each `l19` observation checks 10,000 fresh public calls, each
small status case checks 5,000, and each B08 observation checks one full
catalogue. Every call in a batch is checked against its literal result. Each
row retains `batch`, `checked_calls`, integer `steady_clock` nanoseconds,
source/harness commits, exact source fixture and canonical input SHA-256,
problem/request IDs, limits, objective convention, assurance, counts and
expected-versus-observed fields. The interval starts before fixture
construction and ends after public execution, independent literal checks and
JSON result construction. It excludes JSONL serialization, process startup,
persistence, plotting and rendering. The rows are batch observations with
different batch sizes; do not infer single-call latency from them.

The B08 canonical input includes the exact hexadecimal binary64 vertices
read from the actual native V disturbance sets, alongside separately named
authored halfwidth parameters. This distinguishes stage-two arithmetic such as
`0.1+0.1*2` from the rounded authored decimal `0.3`. The collector's functional
`test_capture.py` checks this identity distinction and retained partial
stdout/stderr on timeout. Preflight records both the pinned source tree and
the distinct harness tree.

Collection must preserve raw stdout JSONL, stderr, process exit status and any
failed or partial attempt. It must verify clean Release/NDEBUG/C++20 build
provenance, executable and authored-input hashes, compiler/OS/hardware/workers,
actual call counts, literal results and interval adequacy. A separate excluded
limiter profile is needed before a performance comparison. This single-adapter
result has no comparator or speedup claim. Saved records, HTML, CSV, offline ZIP,
independent scientific/report review and a verified main-only Pages URL remain
future gates under `docs/contracts/algorithm-report-records.md` and
`docs/architecture/published-algorithm-results.md`.
