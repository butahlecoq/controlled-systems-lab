# REVIEW-05 verified paired scalar horizon timing

This Release capture reruns the HORIZON-01 scalar integrator at T=2, 4, and 8
using source revision `d4598f340b9d492db2013f2304c529bc4358010a`. Each horizon
has one excluded warmup pair and six alternating measured pairs. All 42
attempts pass the fixture-specific exact rational checker, including all 36
measured attempts and all 18 matched measured pairs. The checker proves that
each emitted candidate relation is the unique all-zero optimal-history set for
these three fixtures only.

## Matched timings

| Horizon | Reach-back median (range) | Strategy B median (range) | Verified pairs |
|---:|---:|---:|---:|
| 2 | 6.059 ms (5.371–11.527) | 0.770 ms (0.696–1.893) | 6/6 |
| 4 | 11.361 ms (11.060–13.784) | 0.779 ms (0.696–1.435) | 6/6 |
| 8 | 27.337 ms (23.158–33.496) | 0.975 ms (0.774–1.650) | 6/6 |

The solver interval is `SynthesisWorkspace::run()` only. These are descriptive
measurements from one host and workload family; they establish no general
winner, speedup, or complexity claim. The scalar state/control dimensions
remain fixed. The joint relation grows from 5 to 17 coordinates; row and
nonzero-coefficient counts are in `summary.json`. Output byte counts are not
allocated-memory measurements. The runner enforces one backend thread, 300 s
CPU, 8 GiB address space, and 300 s per-process wall timeout. It does not
record peak RSS or per-phase costs.

## Reproduction

From the repository root, set `BUILD` to an empty Release build directory and
`OUTPUT` to a new empty directory. CMake 3.31.6 and Ninja are used for the
captured build.

```sh
cmake -S benchmarks/reporting/review05 -B "$BUILD" \
  -DCSL_SOURCE_ROOT="$PWD" -DCMAKE_BUILD_TYPE=Release -G Ninja
ninja -C "$BUILD" -j4 csl_review05_horizon_ladder
python3 benchmarks/reporting/review05/run_horizon_ladder.py \
  --driver "$BUILD/csl_review05_horizon_ladder" \
  --scenarios benchmarks/reporting/review05/scenarios --output "$OUTPUT"
python3 benchmarks/reporting/review05/check_horizon_ladder.py --bundle "$OUTPUT"
python3 benchmarks/reporting/review05/summarize_horizon_ladder.py --bundle "$OUTPUT"
python3 benchmarks/reporting/review05/render_horizon_ladder.py --bundle "$OUTPUT"
```

The fixture hashes, strategy outputs, exact-check results, timings, process
limits, environment, and measurement-source hashes are retained in this
bundle. Build identity is recorded in `build-provenance.json`; `SHA256SUMS`
covers every other file in this directory.
