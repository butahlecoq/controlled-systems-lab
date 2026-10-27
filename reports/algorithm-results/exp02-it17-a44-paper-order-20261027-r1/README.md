> Superseded pre-commit capture. Retained for audit only; do not use these rows as current evidence. The clean-source rerun is in [r2](../exp02-it17-a44-paper-order-20261027-r2/README.md).

# EXP-02: A44 farthest-seeded hull pilot

## Verdict

**Inconclusive as a performance comparison.** A44 v2 passed all ten measured attempts on two small exact-dyadic 2D clouds, but the measurement excludes workspace setup and does not cover representative end-to-end use. Other reducers' failed attempts are retained and excluded from passing-time summaries.

## Method change

The ITIS'17 A44 paper describes a candidate set seeded by the first `k+1` points considered farthest from the bounding-box center, followed by incremental LP hull-membership checks and a full final recheck. It separately says the ordering is by increasing distance, which conflicts with its “first `k+1` points are most distant” description. Version 2.0.0 records the farthest-first interpretation and uses normalized Euclidean distance, matching the paper's stated Euclidean norm. The prior C++ adaptation and its results remain method version 1.0.0; no Pascal source was found in the audited repository history or available paper archive.

Each candidate deletion still requires an exact binary64 convex-combination certificate. A separate independent 2D hull checker verifies that retained source points cover the full input hull. The 2D geometry figure is included at [`fixture-geometry.svg`](fixture-geometry.svg).

## Workload and outcomes

Both fixtures contain the unit-square corners and deterministic interior points generated on a 1/32 grid from seed `0x6d2b79f5`; methods received the identical input per size. Input SHA-256 values are carried in each JSONL row.

Five interleaved measured repetitions and one warmup were run per method and fixture. There are 72 raw rows total. Successful timing summaries and failure counts are in [`summary.csv`](summary.csv).

A44 v2 passed 5/5 measured attempts on each size and retained the four corners. QuickHull and phase-one basis reuse also passed 5/5 at each size. The LP baseline, ordered membership, and A43 certificate-safe adaptation failed their completion checks on every measured attempt; their diagnostic durations are not treated as performance measurements. The independent report retains their raw rows and stderr diagnostics.

Passing medians and full ranges:

| Fixture | Method | Passed | Median | Range |
|---|---|---:|---:|---:|
| 64 points | QuickHull | 5/5 | 0.140 ms | 0.140–0.141 ms |
| 64 points | Basis reuse | 5/5 | 0.229 ms | 0.211–0.246 ms |
| 64 points | A44 v2 | 5/5 | 7.129 ms | 7.083–7.190 ms |
| 256 points | QuickHull | 5/5 | 0.563 ms | 0.547–0.567 ms |
| 256 points | Basis reuse | 5/5 | 0.755 ms | 0.739–0.851 ms |
| 256 points | A44 v2 | 5/5 | 27.898 ms | 27.641–30.981 ms |

The separate unreported profile observed the benchmark process using about 94–100% of one logical CPU. A44 v2 made 61 incremental queries at 64 points and 253 at 256 points, plus four final rechecks at each size. LP solving is the likely limiter based on the call count and CPU saturation; no source-function profile was available. No resource limiter was enforced, and workspace creation is outside the timed interval. These limits keep the timing conclusion exploratory.

## Provenance and reproduction

- Base commit: `235714d546f1d0985e663d5943fea40017d69a0e`.
- Compiler: GCC 16.2.1; CMake 3.31.6; Release (`-O3 -DNDEBUG`).
- LP provider: HiGHS 1.11.0, configured for one thread.
- Executable SHA-256: see `raw/executable.sha256`.
- The source diff digest captured at run time is in `raw/source-diff.sha256`; the method's paper identities and hashes are in [`docs/research/exp02-itis17-source-audit-20261027.md`](../../../docs/research/exp02-itis17-source-audit-20261027.md).
- Environment, profile-only output, exact input geometry, raw rows and diagnostics are under `raw/`.

From the repository root, with the configured CMake 3.31.6 binary:

```sh
cmake -S . -B build/exp02-a44-v2 -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
  -DCSL_DEPENDENCY_PROBES=OFF -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=OFF \
  -DCSL_BUILD_IT17_HULL_REPORT=ON -DCSL_BUILD_REPORTS=ON
cmake --build build/exp02-a44-v2 --target csl_geometry_checks csl_it17_hull_comparison_report -j2
ctest --test-dir build/exp02-a44-v2 -R '^itis17_hull_reducers_test$' --output-on-failure
build/exp02-a44-v2/csl_it17_hull_comparison_report --dyadic-size 64 --measure 5
build/exp02-a44-v2/csl_it17_hull_comparison_report --dyadic-size 256 --measure 5
python3 reports/algorithm-results/exp02-it17-a44-paper-order-20261027-r1/summarize.py
```

This pilot advances only the hull comparison slice. It does not satisfy EXP-02's paired control strategies, full dimension/distribution/representation matrix, comparison-record requirements, resource enforcement, or end-to-end measurements. Issue #94 remains open.
