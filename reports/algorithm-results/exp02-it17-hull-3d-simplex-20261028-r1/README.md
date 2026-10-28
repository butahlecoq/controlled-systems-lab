# EXP-02: 3D hull reducer pilot

This is the first three-dimensional hull-ladder cell, recorded for issue [#94](https://github.com/butahlecoq/controlled-systems-lab/issues/94). It compares five LP reducers on one fixed 250-point input. The earlier pure 3D Halton cloud is retained in [the initial attempt](../exp02-it17-hull-3d-halton-cloud-20261028-r1/README.md); all reducers kept all points there, so it did not exercise pruning.

## Input and independent check

The fixture consists of the four standard tetrahedron vertices and 246 strictly interior points. For each point, bases 2, 3, and 5 of the unscrambled Halton sequence select three positive integer barycentric weights. Accepted triples have sum at most 7; the fourth positive weight completes the sum to 8. Points use weights in multiples of 1/8, so all input coordinates and the known removal witnesses are exactly representable in binary64. Repeated interior points are retained in the input to exercise duplicate removal.

The driver records actual retained source IDs and every removal certificate. The Python summarizer independently parses those records, verifies exact dyadic certificate weights with `fractions.Fraction`, checks exact reconstruction in all three coordinates, and checks that later-removal references form an acyclic chain ending at retained IDs. This proves the output and input have the same convex hull. The four tetrahedron vertices must remain because they are extreme points of the analytic input fixture.

QuickHull is recorded as unsupported because the registered QuickHull implementation is 2D-only. The figure projects the input into the three coordinate planes. It plots input points only; it does not draw projected hull boundaries.

## Result

Five alternating measured calls per LP reducer followed one warmup. The independent hull check passed for all 25 measured calls. Basis reuse, the A43 adaptation, and the A44 adaptation returned complete reductions with the four tetrahedron vertices and 246 removals. The baseline and ordered LP reducers returned hull-valid certificates but reported incomplete reducer status; their timings are withheld from the comparison table.

| Method | Complete measured outcomes | Median reducer time | Range |
|---|---:|---:|---:|
| Basis reuse related to A43 | 5/5 | 0.957739 ms | 0.940070–0.962279 ms |
| A43 certificate-safe basis adaptation | 5/5 | 1.650499 ms | 1.591902–1.657902 ms |
| A44 incremental LP adaptation | 5/5 | 28.256975 ms | 27.372360–29.494640 ms |

These are descriptive measurements for this fixture only. No speedup claim is made: the host did not provide an available source-mapped profiler, and the baseline and ordered reducer attempts were incomplete. The timed region is the reducer call; each call receives a fresh HiGHS workspace, created before timing. Certificate validation and JSON serialization happen after timing. HiGHS is pinned to 1.11.0, with native solver threading disabled.

The first pure Halton cloud, its unsuccessful attempts, and raw records remain unchanged in the linked exploratory bundle. Neither A43 nor A44 is a faithful Pascal or paper implementation; both are explicitly named paper-informed adaptations.

## Reproduction

The benchmark driver and report generator are in `benchmarks/reporting/it17_hull/`. Configure and build in Release with the pinned HiGHS LP adapter:

```sh
cmake -S . -B build/it17-hull-3d -DCMAKE_BUILD_TYPE=Release \
  -DCSL_BUILD_IT17_HULL_REPORT=ON -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=OFF
cmake --build build/it17-hull-3d --target csl_it17_hull_3d_report --parallel 2
build/it17-hull-3d/csl_it17_hull_3d_report --measure 5 > raw-rows.jsonl
python3 benchmarks/reporting/it17_hull/summarize_3d.py \
  --raw raw-rows.jsonl --output-dir reports/algorithm-results/exp02-it17-hull-3d-simplex-20261028-r1
```

The measured executable was built from source commit `cac63501496abf9598edab3943a0b35c0f274ae5` with GCC 16.2.1, CMake 3.31.6, Release flags `-O3 -DNDEBUG`, HiGHS 1.11.0, and Linux x86_64. The raw folder retains the executable SHA256, run output, stderr, process limit, host, compiler, and CMake settings. The report is self-contained and opens from [`index.html`](index.html); source records are in [`validated-rows.jsonl`](validated-rows.jsonl), [`summary.csv`](summary.csv), and [`raw/`](raw/). See [`SHA256SUMS`](SHA256SUMS) or download the [offline ZIP](exp02-it17-hull-3d-simplex-20261028-r1.zip).

## Delivery impact

This adds an optional, non-installed report executable and a versioned evidence bundle. It changes no public library API, package dependency, or installation target. No release or package workflow update is needed.
