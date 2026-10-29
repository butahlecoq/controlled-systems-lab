# EXP-02: 250-point QuickHull and LP reducer slice

## Result

All 48 attempts (six warmups and 42 measured calls) passed accounting, expected-corner retention, and the independent exact represented-binary64 2D finite-hull check. Each method had seven interleaved measured calls on one deterministic 250-point square cloud.

The performance result is **inconclusive**. The capture has no source-function profile (`perf` and `strace` are unavailable), represents one small 2D fixture, and excludes workspace setup and validation. The medians below are descriptive observations, not a ranking or scalability claim.

| Method | Median call | Range | Reducer complete |
| --- | ---: | ---: | ---: |
| Geometric QuickHull | 0.549 ms | 0.528–0.905 ms | n/a |
| LP membership baseline | 67.621 ms | 67.237–69.812 ms | 0/7 |
| Phase-I basis reuse (related to A43) | 0.749 ms | 0.722–0.825 ms | 7/7 |
| Ordered LP membership (related to A44) | 67.190 ms | 66.785–68.651 ms | 0/7 |
| A43 certificate-safe adaptation | 24.518 ms | 24.266–25.307 ms | 0/7 |
| A44 incremental LP farthest seed | 27.472 ms | 27.177–30.603 ms | 7/7 |

The geometric fixture contains the four unit-square corners and 246 unique interior dyadic points generated from seed `0x6d2b79f5`. Every row uses input SHA256 `805fb5e027ee97394494ef3d23123e47c86d31e21de53f4a5c239867204d04b3`. The independent checker reports `verified` for all 48 attempts, with a five-second wall budget and 250-point bound. Exact hull validity is separate from LP reducer completion; incomplete reducers can retain redundant inputs while returning the correct hull.

A43 and A44 are paper-informed adaptations, not faithful reproductions or Pascal ports. The available Pascal source search and paper identities are recorded in the [ITIS17 research note](../../../docs/research/itis17-lp-hull-methods-for-quickhull.md). The broader dimension, distribution, representation, and control-strategy matrix in issue #94 remains open.

## Environment and reproduction

- Source commit: `9b53f24e9d2e4f1d7c1ec82150589a4bbb50387a`.
- AMD Ryzen 5 3550H, 8 logical CPUs; Linux x86_64, kernel 7.2.8-9-omarchy.
- GCC 16.2.1, C++20, CMake 3.31.6, Ninja, HiGHS 1.11.0, Release build.
- Pre-run load average: `0.45, 1.14, 0.86`.
- Timing covers the public algorithm/reducer call. LP workspace setup, independent checking, and JSON serialization are excluded.
- One warmup precedes seven measured calls per method; method order rotates each round.
- The clean build completed all 287 Ninja steps. Vendored HiGHS emitted one `-Wmaybe-uninitialized` warning in `HighsSymmetry.cpp`; the target linked successfully.

Build with `CMAKE_BUILD_TYPE=Release`, `CSL_ENABLE_HIGHS=ON`, `CSL_ENABLE_QHULL=OFF`, `BUILD_TESTING=OFF`, and `CSL_BUILD_IT17_HULL_REPORT=ON`, then run:

```sh
csl_it17_hull_comparison_report --dyadic-size 250 --measure 7
python3 raw/summarizer.py raw/raw-rows.jsonl .
```

Raw rows, timing output, executable hash, run configuration, the full clean Release build log and build record, fixture plot, and summarizer are retained in this immutable bundle.
