# EXP-02: A44 farthest-seeded hull pilot, output-status update

## Verdict

All six methods returned retained source-index sets whose exact hulls match
the complete input on both measured fixtures. The LP membership baseline,
ordered LP reducer, and A43 certificate-safe adaptation still report incomplete
point classification; their unresolved redundant points remain in the output.
This report separates geometric validity from reduction completeness.

Performance interpretation remains **inconclusive**. The run excludes LP
workspace creation and output validation, has no source-function profile or
resource limiter, and covers only two small 2D square clouds.

## Workload and results

The inputs contain all four unit-square corners plus unique interior points on
a `1/32` grid from seed `0x6d2b79f5`, at sizes 64 and 256. Each method receives
the same bit-identical input for a size. There is one warmup and five
interleaved measured attempts for every method and size. Raw rows contain input
hashes, outcomes, call counts and individual timings.

| Points | Method | Hull verified | Reducer status complete | Retained | Median reducer call |
|---:|---|---:|---:|---:|---:|
| 64 | QuickHull | 5/5 | n/a | 4 | 0.144 ms |
| 64 | LP membership baseline | 5/5 | 0/5 | 64 | 10.424 ms |
| 64 | Phase-I basis reuse (related to A43) | 5/5 | 5/5 | 34 | 0.226 ms |
| 64 | Ordered LP membership (related to A44) | 5/5 | 0/5 | 64 | 10.568 ms |
| 64 | A43 certificate-safe adaptation | 5/5 | 0/5 | 34 | 5.273 ms |
| 64 | A44 incremental LP adaptation v2 | 5/5 | 5/5 | 4 | 7.191 ms |
| 256 | QuickHull | 5/5 | n/a | 4 | 0.587 ms |
| 256 | LP membership baseline | 5/5 | 0/5 | 255 | 70.204 ms |
| 256 | Phase-I basis reuse (related to A43) | 5/5 | 5/5 | 125 | 0.769 ms |
| 256 | Ordered LP membership (related to A44) | 5/5 | 0/5 | 255 | 69.816 ms |
| 256 | A43 certificate-safe adaptation | 5/5 | 0/5 | 123 | 25.267 ms |
| 256 | A44 incremental LP adaptation v2 | 5/5 | 5/5 | 4 | 27.939 ms |

The [fixture geometry](fixture-geometry.svg) shows both square point clouds.
The [summary CSV](summary.csv), [64-point rows](raw/n64.jsonl),
[256-point rows](raw/n256.jsonl), stderr files, environment, executable hash,
and this README are preserved in the bundle. `SHA256SUMS` covers every file.

## Method identity and evidence

A43 and A44 remain separately identified paper-informed C++ adaptations, not
faithful historical ports. A43 wraps the certificate-safe Phase-I basis-reuse
method and a final LP recheck; it omits the paper's per-candidate
artificial-basis sequence and largest-norm tie policy. A44 v2 uses the paper's
`k+1` farthest-point seed and normalized Euclidean distance, choosing
farthest-first to resolve conflicting ordering descriptions. No matching
Pascal implementation was recovered; the available `btulshor.pas` is a
different method. Source filenames, PDF hashes, cited pages, and the search
limit are recorded in [`raw/paper-identities.txt`](raw/paper-identities.txt).

The independent bounded exact 2D source-index checker verifies that the
retained set covers the full input hull. The result `passed` field records
accounting plus this hull check. `reducer_status_complete` records whether an
LP reducer returned `ReductionStatus::complete`; it does not claim that every
retained point is an extreme vertex. QuickHull has no `ReductionStatus`, so
the JSON field is null and the table displays n/a. Exact deletion certificates
are retained for LP removals.

## Environment and timing scope

- Source commit: `34e101b0319479779dee89c8d0c1658f14ef1247`.
- Release build, GCC 16.2.1, CMake 3.31.6, C++20, HiGHS 1.11.0, one LP thread.
- AMD Ryzen 5 3550H, Linux x86_64, 8 logical CPUs; pre-run load average `0.76, 1.25, 0.77`; 2.5 GiB available memory.
- Timing covers the public reducer call. LP workspace creation and output validation are outside the interval.
- No resource limiter or source-function profile was available. LP call counts are retained but do not establish the precise hot function.

## Reproduction

Configure and build `csl_it17_hull_comparison_report` in Release with HiGHS
1.11.0 and run:

```sh
csl_it17_hull_comparison_report --dyadic-size 64 --measure 5
csl_it17_hull_comparison_report --dyadic-size 256 --measure 5
python3 summarize.py
```

This is a bounded hull-method slice of EXP-02. It does not complete the
dimension/distribution ladder or paired control-strategy and representation
axes. Issue #94 remains open.
