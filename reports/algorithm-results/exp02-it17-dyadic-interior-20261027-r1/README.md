# EXP-02 repeated ITIS17 dyadic hull pilot

## Verdict

**Inconclusive as a performance comparison.** The run produced repeatable, independently hull-checked results for QuickHull, basis reuse, and the A44 adaptation on these two small 2D fixtures. The baseline, ordered membership, and A43 adaptation failed the driver's completion checks in every measured attempt. This is useful initial evidence for this fixture family, not a winner or scalability claim.

## Expected claim

Before measurement, the expected claim was: report five interleaved measured attempts plus one warmup for every existing method on deterministic 64- and 256-point interior-heavy square clouds. Preserve all failures and report timing summaries only for methods whose output checks pass. Keep A43/A44 identities as paper-informed C++ adaptations. No general speedup is claimed.

## Workload and method identity

Each cloud has the four unit-square corners and unique interior points from the deterministic 1/32-grid generator (`0x6d2b79f5`). Input hashes are embedded in each raw row. All methods used the same cloud per size. Methods are geometric QuickHull, LP membership baseline, phase-one basis reuse, ordered membership, the A43 certificate-safe basis adaptation, and the A44 incremental-LP adaptation. The last two are adaptations informed by the ITIS17 papers, not faithful ports. No A43/A44 Pascal source was found in the available home-directory search; the two local `.doc` files are article copies without source listings. An unrelated Pascal unit is not substituted.

## Execution and timing scope

Release build, GCC 16.2.1, `-O3 -DNDEBUG`, HiGHS configured for one thread. The benchmark process ran serially on an 8-logical-CPU AMD Ryzen 5 3550H host. Load was 1.56/1.36/0.76 before the reported runs and 1.03/1.25/0.74 after. The host had 7.9 GiB total memory and 3.0 GiB available before the runs. No per-process memory or CPU limiter was enforced. The comparison-program exploratory limits are therefore recorded as requested, not enforced.

For LP methods, a fresh HiGHS workspace is created before the timer; the timer covers the reducer call and excludes workspace creation and output validation. QuickHull is timed around its call, then checked. The driver validates complete point accounting, certificate verifier identity, the exact source-index hull checker, and the four known square corners. It does not independently replay each emitted removal certificate. The solver is configured for one thread; OS thread count was not instrumented.

A separate `top` profile-only run (`--measure 20`, 256 points) observed the benchmark process at about 99.4–100% of one logical CPU, with RSS about 8.8 MiB. It did not sample source functions, so the precise hot spot is not established. `/usr/bin/time`, `perf`, `pidstat`, and `strace` are unavailable. Since the limiter cannot be mapped within the implementation and the benchmark excludes workspace setup, the performance verdict remains inconclusive.

## Results

Successful rows only are summarized with median and full range. Failed attempts remain in `summary.csv` as counts, retained-point counts, and diagnostic-only elapsed values.

| Fixture | Method | Passed | Retained | Median (ms) | Range (ms) |
|---|---|---:|---:|---:|---:|
| 64 points | Geometric QuickHull | 5/5 | 4 | 0.1412 | 0.1407–0.1417 |
| 64 points | Phase-one basis reuse | 5/5 | 34 | 0.2201 | 0.2175–0.2424 |
| 64 points | A44 incremental LP adaptation | 5/5 | 4 | 7.3310 | 7.3110–7.3752 |
| 256 points | Geometric QuickHull | 5/5 | 4 | 0.5689 | 0.5497–0.6874 |
| 256 points | Phase-one basis reuse | 5/5 | 125 | 0.7516 | 0.7356–0.7975 |
| 256 points | A44 incremental LP adaptation | 5/5 | 4 | 28.2498 | 27.9564–30.3696 |

The LP baseline and ordered method passed 0/5 at each size. A43 passed 0/5 at either size. A44 and QuickHull retained the four expected corners. Basis reuse produced valid hulls under the driver's checker but retained interior points. Failed-attempt elapsed values are not successful performance measurements.

## Evidence files

- [`index.html`](index.html): versioned, standalone report with the input-geometry figure, passing timing summary and explicit failures/limitations.
- [`fixture-geometry.svg`](fixture-geometry.svg): the shared 64- and 256-point inputs with their exact square hull.
- [`record.json`](record.json): source identity, input hashes, scope and evidence limits for the Pages landing card.
- [`SHA256SUMS`](SHA256SUMS): hashes for every file in this immutable report bundle.
- `raw/n64.jsonl`, `raw/n256.jsonl`: all 72 raw warmup and measured rows.
- `raw/n64.stderr`, `raw/n256.stderr`: validation diagnostics, including every failed method attempt.
- `validated-rows.jsonl`, `summary.csv`: validated matrix and per-method summaries.
- `raw/top-profile.txt`: separate, non-reported CPU/RSS sampling run.
- `raw/environment-before.txt`, `raw/environment-after.txt`, `raw/configure.log`, `raw/build.log`: host and build records.
- `raw/source.sha256`, `raw/executable.sha256`: source and executable digests.

The report staging script publishes this bundle under the versioned route
`exp02-it17-dyadic-interior-20261027-r1/`, adds raw/summary links to the
Pages archive, and creates an offline ZIP. The public URL remains pending until
the reviewed PR is merged and the main-only Pages workflow is verified.

## Reproduction

From the repository root, configure and build with CMake 3.31.6 (use the absolute binary path if the `cmake` shim has no active version), then run serially:

```sh
cmake -S benchmarks/reporting/it17_hull -B build/exp02-it17-dyadic-interior-20261027-r1 \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS_RELEASE='-O3 -DNDEBUG'
cmake --build build/exp02-it17-dyadic-interior-20261027-r1 \
  --target csl_it17_hull_comparison_report -j2
build/exp02-it17-dyadic-interior-20261027-r1/csl/csl_it17_hull_comparison_report \
  --dyadic-size 64 --measure 5
build/exp02-it17-dyadic-interior-20261027-r1/csl/csl_it17_hull_comparison_report \
  --dyadic-size 256 --measure 5
python3 reports/algorithm-results/exp02-it17-dyadic-interior-20261027-r1/summarize.py
```

The 5 measured rounds are interleaved within each fixture. Re-run the two commands separately to preserve the recorded fixture-specific input hashes and attempt order.

After the source rows are present, regenerate the saved HTML, figure, metadata
and bundle hashes without rerunning the solver:

```sh
python3 reports/algorithm-results/exp02-it17-dyadic-interior-20261027-r1/render_report.py
```

This PR adds a report-only Pages staging route; it changes no public C++ API,
dependency, installation, release, or package workflow. Release/package impact:
**no release needed**. Pages deployment remains gated on review, merge and live
URL verification.
