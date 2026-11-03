# REVIEW-05 source profile across the scalar horizon ladder

## Question and conclusion

This extends the source-attribution diagnostic to the existing HORIZON-01
scalar integrator fixtures at T=2, 4, and 8. It asks whether the profiled
functions change enough with joint-relation size to identify one optimization
target. They do not: reach-back samples remain spread across HiGHS lifecycle,
LP, geometry, and exact-check functions, while Strategy B has only 31, 31, and
47 sampled 10 ms ticks. No symbol approaches the predeclared 15% threshold.

This remains a low-resolution diagnostic. It makes no speed, ranking, scaling,
memory, or limiter claim. The 10 ms `gprof` sampling interval makes the Strategy
B entries especially coarse.

## Workload and exact checking

All fixtures use `x[t+1] = x[t] + u[t]`, `x[0]=0`, `0<=u[t]<=1`, minimizing
`x[T]`. The independent rational checker verifies that each saved candidate
relation equals the unique all-zero history for the corresponding exact
fixture. Each horizon used three alternating process groups and 1,000 fresh
workspace calls per process: 3,000 per strategy and 6,000 total. T=2 and T=4
captures each independently verify all 6,000 outputs in their retained raw
streams. The T=8 capture is the previously reviewed and independently verified
bundle under [PR #869](https://github.com/butahlecoq/controlled-systems-lab/pull/869).
All three use the same profiled driver SHA-256 recorded below.

The existing exact horizon ladder reports relation growth as follows:

| Horizon | Joint coordinates | Reach-back H rows (ineq/eq) | Strategy B H rows (ineq/eq) | Reach-back nonzero coefficients | Strategy B nonzero coefficients |
|---:|---:|---:|---:|---:|---:|
| 2 | 5 | 6 / 4 | 4 / 4 | 14 | 12 |
| 4 | 9 | 10 / 6 | 8 / 6 | 24 | 22 |
| 8 | 17 | 18 / 10 | 16 / 10 | 44 | 42 |

These are recorded H-relation shapes, not allocated-byte counts. The profile
includes process setup and output serialization; `strategy_run_ns` is not used
for the source-profile conclusion.

## Profile observations

| Horizon | Strategy | Sampled CPU | Largest function share | Interpretation |
|---:|---|---:|---|---|
| 2 | Reach-back | 3.71 s / 371 ticks | 4.58%, `Highs::callSolveQp` closure manager | samples distributed across solver lifecycle and CSL work |
| 2 | Strategy B | 0.31 s / 31 ticks | 6.45%, `OptionRecordString::~OptionRecordString` | too few ticks to order functions |
| 4 | Reach-back | 9.55 s / 955 ticks | 4.92%, `Highs::callSolveQp` closure manager | same broad distribution |
| 4 | Strategy B | 0.31 s / 31 ticks | 6.45%, `_init` | too few ticks to order functions |
| 8 | Reach-back | 20.05 s / 2,005 ticks | 4.89%, `OptionRecordString::~OptionRecordString` | same broad distribution |
| 8 | Strategy B | 0.47 s / 47 ticks | 6.38%, `HFactor::ftranL` | too few ticks to order functions |

The reach-back leaders are HiGHS lifecycle entries (`callSolveQp` closure
manager or option-record destructor), each below 5% in these captures. Other
leading entries include simplex routines, `HighsLPWorkspace::solve_native`,
`exact_convex_combination`, and witness verification. The leading symbol shifts
between horizons and does not establish a bottleneck. Strategy B's small sample
count makes its leading percentages quantized by two or three ticks at each
horizon.

## Provenance and limits

The instrumented executable is SHA-256
`805443cd169b74491fab39c54ba64f923774af3988445f87397d47fec3a29bce`, built
with Release dependencies (`-O3 -DNDEBUG -g`) and `-pg` only on the driver.
Build and host metadata are in `build-provenance.json`; each T=2/T=4 child
bundle records its fixture/source hashes, process order, exact outputs,
per-process limits, stdout/stderr and gmon hashes. Each process had 300 s CPU,
8 GiB address-space, and 300 s wall limits. These are caps, not measured
memory-scaling observations.

The T=2/T=4 source tree was dirty only because this extension was being
captured before its commit; the exact measurement source files are hashed in
each manifest and checked by the offline verifier. T=8 uses the prior committed
capture bundle whose provenance is recorded in that bundle. Source maps for
representative symbols are in the [T=8 profile report](../review05-source-profile-final-20261102/README.md).

The profile includes startup and serialization, records no pre-run load average,
and samples at 10 ms. A previous fully call-instrumented pilot was too costly
and is excluded. The captures therefore identify no general limiter and do not
support comparative timing claims.

## Reproduction

From the repository root, build the profile driver using the commands in the
[T=8 profile report](../review05-source-profile-final-20261102/README.md), then
set `DRIVER` to that exact executable. Use separate new empty output directories
for the T=2 and T=4 captures:

```sh
python3 benchmarks/reporting/review05/capture_source_profile.py \
  --driver "$DRIVER" --scenario benchmarks/reporting/review05/scenarios/horizon01-t02.json \
  --output "$OUTPUT_T02" --process-groups 3 --repeats-per-process 1000
python3 benchmarks/reporting/review05/verify_source_profile.py --bundle "$OUTPUT_T02"
python3 benchmarks/reporting/review05/capture_source_profile.py \
  --driver "$DRIVER" --scenario benchmarks/reporting/review05/scenarios/horizon01-t04.json \
  --output "$OUTPUT_T04" --process-groups 3 --repeats-per-process 1000
python3 benchmarks/reporting/review05/verify_source_profile.py --bundle "$OUTPUT_T04"
```

The raw flat reports can be regenerated with `profile-commands.txt`. Rebuild
the machine-readable summary with:

```sh
python3 benchmarks/reporting/review05/summarize_source_profile_matrix.py \
  --profiles reports/algorithm-results/review05-source-profile-horizon-matrix-20261102 \
  --output reports/algorithm-results/review05-source-profile-horizon-matrix-20261102/profile-summary.json
```

The `SHA256SUMS` file covers this README, build provenance, profile summaries,
commands, and the full T=2/T=4 capture bundles.
