# EXP-02: distinguish verified hulls from incomplete reductions

## Verdict

The output-status correction changes the result interpretation: all six methods
returned a retained source-index set whose exact hull matched the complete input
on both measured fixtures. The LP baseline, ordered LP reducer, and A43
certificate-safe adaptation report incomplete reducer status.
They return geometrically valid hulls while retaining redundant points.
Performance conclusions remain **inconclusive**.

## Workload and evidence

The run used deterministic exact-dyadic square clouds with 64 and 256 points.
Each contained all four unit-square corners plus unique interior points on a
`1/32` grid, generated from seed `0x6d2b79f5`. Every method used identical input
for each size; the shared input digests appear in the raw rows. Each method ran
once as warmup and five measured times in interleaved order. All 72 rows
(12 warmups and 60 measurements) passed complete point accounting and the
independent exact 2D source-index hull checker.

The independent check establishes equality of the input and retained hulls.
`reducer_status_complete` separately preserves the LP reducer's
`ReductionStatus::complete` value. This status means candidate results were
completed and correctly bound; it does not prove that every retained point is
an extreme vertex. A valid result may therefore keep unresolved interior
points. The retained count remains part of the result-quality evidence.
QuickHull has no `ReductionStatus`, so its status is not applicable.

| Points | Method | Hull verified | Reducer status complete | Retained | Median reducer call |
|---:|---|---:|---:|---:|---:|
| 64 | QuickHull | 5/5 | n/a | 4 | 0.142 ms |
| 64 | LP membership baseline | 5/5 | 0/5 | 64 | 10.252 ms |
| 64 | Phase-I basis reuse (related to A43) | 5/5 | 5/5 | 34 | 0.225 ms |
| 64 | Ordered LP membership (related to A44) | 5/5 | 0/5 | 64 | 10.302 ms |
| 64 | A43 certificate-safe adaptation | 5/5 | 0/5 | 34 | 5.337 ms |
| 64 | A44 incremental LP adaptation v2 | 5/5 | 5/5 | 4 | 7.112 ms |
| 256 | QuickHull | 5/5 | n/a | 4 | 0.572 ms |
| 256 | LP membership baseline | 5/5 | 0/5 | 255 | 69.935 ms |
| 256 | Phase-I basis reuse (related to A43) | 5/5 | 5/5 | 125 | 0.756 ms |
| 256 | Ordered LP membership (related to A44) | 5/5 | 0/5 | 255 | 69.555 ms |
| 256 | A43 certificate-safe adaptation | 5/5 | 0/5 | 123 | 25.306 ms |
| 256 | A44 incremental LP adaptation v2 | 5/5 | 5/5 | 4 | 28.176 ms |

The full ranges, row identities, hashes, per-attempt call counts, and warmups
are retained in [the 64-point raw rows](../../reports/algorithm-results/exp02-it17-a44-paper-order-20261028-r3/raw/n64.jsonl),
[the 256-point raw rows](../../reports/algorithm-results/exp02-it17-a44-paper-order-20261028-r3/raw/n256.jsonl),
and [the summary CSV](../../reports/algorithm-results/exp02-it17-a44-paper-order-20261028-r3/summary.csv).
The point-cloud geometry is shown in the [fixture figure](../../reports/algorithm-results/exp02-it17-a44-paper-order-20261028-r3/fixture-geometry.svg);
the bundle's `SHA256SUMS` covers all saved files.

## Measurement limits

The benchmark used a Release build (`-O3 -DNDEBUG`) from source commit
`7c839f41246823300a939562ce239b0bf80282b8`, GCC 16.2.1, CMake 3.31.6,
HiGHS 1.11.0, and one LP solver thread. The executable SHA-256 is recorded in
the report bundle. The host was an AMD
Ryzen 5 3550H with 8 logical CPUs; pre-run load averages were `2.25, 1.70,
1.06` and `2.23, 1.71, 1.06` for the 64- and 256-point runs, with 4.26 GiB
available memory.

Timing covers the reducer call only. It excludes LP workspace creation and
output validation; no per-run memory/CPU limiter was available, and `perf` was
not installed for source-function profiling. LP call counts were 64/256 for
the baseline, 34/125 for basis reuse, 34/125 for A43, and 65/257 for A44 at the
two sizes. Those counts make
LP work a plausible limiter for the LP methods, but do not identify a hot
source function. Treat the timings as descriptive for these fixtures, not as
end-to-end latency, a general speed ranking, or scalability evidence.

The A43 and A44 implementations remain separately identified
paper-informed C++ adaptations, not faithful historical ports. The paper's
original Pascal implementation was not recovered in the repository or
available local archives. The available `btulshor.pas` is a different method
and was not substituted.

## Reproduction

Configure the optional `csl_it17_hull_comparison_report` target in Release,
then run:

```sh
csl_it17_hull_comparison_report --dyadic-size 64 --measure 5
csl_it17_hull_comparison_report --dyadic-size 256 --measure 5
```

This is one bounded hull-method slice of EXP-02. It does not complete the
dimension/distribution ladder or the paired control-strategy and representation
axes. Issue #94 remains open.
