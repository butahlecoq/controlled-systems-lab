# QuickHull and ITIS17 paper-informed LP adaptations

This is a first exploratory 2D comparison, not a faithful replay of either paper and not a performance ranking.

## Measurement

The Release executable ran six separately identified methods on three literal square clouds with 5–10 points each. It recorded 18 warmups and 126 measured calls: seven interleaved rounds for each method/fixture pair. The timed interval includes each reducer call and excludes HiGHS workspace creation and output checking. Each input fixture has a versioned SHA-256 recorded in the raw rows. All 144 calls passed: QuickHull outputs and every LP reducer's retained indices were checked with the independent bounded exact 2D hull checker; LP deletions retain exact convex-combination evidence.

Across the three fixtures, per-fixture medians ranged as follows:

| Method | Median range across fixtures | Observed range across all measured calls |
|---|---:|---:|
| Geometric QuickHull | 5.168–15.365 μs | 4.679–19.137 μs |
| LP membership baseline | 624.036–1,206.724 μs | 619.076–1,289.556 μs |
| OPT-06 basis reuse, related to A43 | 45.397–56.502 μs | 37.086–69.283 μs |
| OPT-07 ordered reducer, related to A44 | 632.975–1,228.514 μs | 614.258–2,690.441 μs |
| A43 certificate-safe basis adaptation | 658.676–1,038.336 μs | 646.664–1,702.391 μs |
| A44 incremental LP adaptation | 944.399–1,466.116 μs | 928.894–1,933.636 μs |

These tiny fixtures do not establish scaling or an algorithm winner. The machine had 8 logical processors and about 3.17 GB available memory; load averages were around 1.3–2.3 during the run. No limiter profile or end-to-end workload was collected, so the performance conclusion remains **inconclusive**.

## Paper correspondence

- **A43, Bulaev–Shorikov:** the new identity wraps the current one-shot Phase-I basis-reuse algorithm and adds a complete LP recheck. It does not implement the paper's per-candidate artificial-basis sequence or largest-norm pivot tie rule. The tie rule is recorded as unapplied; basis membership is not treated as proof of extremality.
- **A44, Goranov–Shorikov:** the new identity performs incremental membership against the accepted set, then a complete LP recheck. This adaptation starts with one ordered point and chooses farthest-first normalized Chebyshev distance with stable input-ID ties. That resolves the paper's ambiguous ordering prose for this run.
- Existing OPT-06 and OPT-07 reducers remain separately identified as related methods. Their preliminary results were not relabeled.
- No matching Pascal source was found in the repository, searched archive, filesystem, or available Git history. The unrelated `btulshor.pas` routine was not run, so there is no Pascal timing row.

Both additions are paper-informed adaptations, not faithful source ports. The source PDFs and hashes, exact method identities, selected deviations, build details, raw rows, and reproduction command are retained in this bundle. This does not complete EXP-02 or any full comparison matrix.

## Reproduction

From the repository root, with CMake 3.31.6, GCC 16.2, and network access for pinned dependencies:

```sh
cmake -S . -B build/it17-hull -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=OFF \
  -DCSL_BUILD_IT17_HULL_REPORT=ON
cmake --build build/it17-hull --target csl_it17_hull_comparison_report --parallel 4
build/it17-hull/csl_it17_hull_comparison_report --measure 7 > raw-capture.jsonl
python3 benchmarks/reporting/it17_hull/summarize.py raw-capture.jsonl output-directory
```

The bundled executable was built from source commit `7de5ad294ab8831ea3bcc2907f0355c602971d63`; its SHA-256 is in `executable.sha256`. The source driver and summarizer are included for review. All expected outcomes and raw trial values are in `raw-rows.jsonl` and `summary.csv`; `index.html` and `fixture-geometry.svg` are rendered from those rows/fixtures.
