# EXP-02: first four-dimensional hull-ladder cell

This is one bounded 4D workload for issue #94: a standard 4-simplex plus 245 dyadic interior points, 250 points total. Four Halton coordinates (bases 2, 3, 5, 7) select positive integer weights for the four coordinate axes. Accepted weights sum to at most 7; the positive fifth barycentric weight completes the total to 8. The points and certificate weights are exactly representable in binary64.

## Independent check

The driver saves retained source IDs and every removal certificate. The Python summarizer independently recomputes the versioned little-endian binary64 input-manifest hash and uses `fractions.Fraction` to verify exact weight sums, coordinate reconstruction in four coordinates, coverage of every input point by either a retained point or a certificate, and acyclic certificate chains ending in retained points. All five analytic simplex corners must remain retained. The exact certificate-chain diagnostic passed for all 25 measured LP calls; baseline and ordered LP remain inconclusive because their reducers reported incomplete status.

QuickHull is recorded unsupported because the registered geometric implementation is 2D-only. The plot shows six pairwise coordinate projections of the same 4D input, with red markers for the five simplex corners; it does not imply projected hull boundaries. The reducer family also supports 2D; [`2d-visual-companion.svg`](2d-visual-companion.svg) is copied from the existing [2D hull pilot report](https://butahlecoq.github.io/controlled-systems-lab/quickhull-it17-paper-adaptations-20261024-r1/index.html) and uses a separate fixture.

## Results

Five LP reducers each received one warmup and five measured calls. Three methods completed all five reductions, retained the five simplex corners, and removed 245 points. Baseline and ordered LP each returned exact hull-equivalent certificates but incomplete reducer status; their timing is withheld.

| Method | Exact hull diagnostics | Reducer complete | Evidence status | Retained median | Median reducer time | Range |
|---|---:|---:|---|---:|---:|---:|
| Baseline LP | 5/5 | 0/5 | inconclusive | — | withheld | withheld |
| Basis reuse related to A43 | 5/5 | 5/5 | verified | 5 | 1.138422 ms | 1.126271–1.164125 ms |
| Ordered LP related to A44 | 5/5 | 0/5 | inconclusive | — | withheld | withheld |
| A43 certificate-safe adaptation | 5/5 | 5/5 | verified | 5 | 1.952011 ms | 1.917928–1.958646 ms |
| A44 incremental adaptation | 5/5 | 5/5 | verified | 5 | 28.387651 ms | 28.212977–29.515389 ms |
| Geometric QuickHull | n/a | unsupported in 4D | inconclusive | n/a | n/a | n/a |

These are descriptive results for one deterministic fixture. A43 and A44 are paper-informed adaptations, not faithful paper or Pascal implementations. No speedup claim is made; a source-mapped limiter profile was unavailable.

## Reproduction

Build the optional Release driver with the pinned HiGHS adapter:

```sh
cmake -S . -B build/it17-hull-4d -DCMAKE_BUILD_TYPE=Release \
  -DCSL_BUILD_IT17_HULL_REPORT=ON -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=OFF
cmake --build build/it17-hull-4d --target csl_it17_hull_4d_report --parallel 2
build/it17-hull-4d/csl_it17_hull_4d_report --measure 5 > raw-rows.jsonl
python3 benchmarks/reporting/it17_hull/summarize_4d.py \
  --raw raw-rows.jsonl --output-dir reports/algorithm-results/exp02-it17-hull-4d-simplex-20261028-r1
```

The recorded binary was built from source commit `dc23a890c4a7e13ad543f56781cc8ebd9bfea770` using GCC 16.2.1, CMake 3.31.6, Release `-O3 -DNDEBUG`, and HiGHS 1.11.0. Solver threads were disabled. A 1,800-second timeout and 12 GiB address-space limit were requested and enforced with GNU `timeout` and `ulimit -v`. The reducer timing excludes fresh workspace creation, exact checking, and serialization.

The report is self-contained at [`index.html`](index.html). Raw rows, validated rows with separate reducer outcomes and evidence statuses, CSV, six 4D input projections, the 2D visual companion, build/host snapshots, executable hash, process limits, and an offline archive are included. See [`SHA256SUMS`](SHA256SUMS).

## Delivery impact

Adds an optional, non-installed report executable and a versioned evidence bundle. No public library API, dependency, package, or installation changes.
