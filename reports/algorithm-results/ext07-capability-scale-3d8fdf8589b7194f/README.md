# EXT-07 capability admission and enumeration profile

This bounded profile measures `report_hybrid_capability`, which validates a
request's hybrid model and enumerates its complete allowed mode/edge paths. It
does not compose joint relations, invoke a solver, or measure provider work.

## Run definition

- Source commit: `fec792f4d595085191dab970e0e0a67281588293`
- Source tree: `2662d36a9649a4b89522cb2224d7dd272b1185c7`
- Configuration: CMake Release, GNU C++ 16.2.1, C++20, CMake 3.31.6
- Native HiGHS and Qhull adapters disabled; standalone capability-report option enabled
- Host: Linux x86_64, 8 logical processors; one process and one worker
- Workload: ten deterministic fixtures, 1,000 calls per batch, one excluded
  warmup batch and seven measured batches per fixture
- Timing excludes fixture construction, build, and JSON serialization
- Every timed call checks admission, completed enumeration, and a complete path
  count; the collector verifies all 70 measured rows, path caps, fixture labels,
  and the expected profile matrix

## Summary

`summary.csv` reports the median and range of each 1,000-call batch. The last
column divides the batch median by 1,000; it is descriptive latency for this
specific capability-report function, not end-to-end hybrid solve time.

| State/control dimension | Horizon | Modes | Edges | Complete paths | Median per call (ns) | Range per call (ns) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 2 | 1 | 1 | 1,970 | 1,958–2,070 |
| 2 | 1 | 2 | 1 | 1 | 2,163 | 2,137–2,195 |
| 4 | 1 | 2 | 1 | 1 | 2,602 | 2,568–2,625 |
| 8 | 1 | 2 | 1 | 1 | 3,864 | 3,835–4,028 |
| 1 | 2 | 2 | 2 | 1 | 2,789 | 2,751–2,858 |
| 1 | 4 | 2 | 2 | 1 | 3,723 | 3,674–3,829 |
| 1 | 8 | 2 | 2 | 1 | 5,619 | 5,509–5,772 |
| 1 | 4 | 4 | 4 | 1 | 6,001 | 5,930–6,041 |
| 1 | 4 | 8 | 8 | 1 | 11,472 | 11,394–11,687 |
| 1 | 8 | 2 | 4 | 256 | 110,408 | 108,482–111,802 |

The single-path cases show increasing admission time as dimensions and catalog
sizes grow. At horizon 8, the 256-path fixture takes a median 110,408 ns per
call, compared with 5,619 ns for the one-path fixture with the same state
dimension, horizon, and mode count. This is an expected path-enumeration cost,
not a solver comparison or general scaling law. Source inspection shows profile
validation scans mode/edge data and the enumerator computes backward-reachable
modes before depth-first enumeration and materializing each complete path. A
separate `time` profile of the full sweep was CPU-heavy (1.140 s user, 0.088 s
system, 1.229 s elapsed). `perf` and `strace` were unavailable on this host, so
no function-level profiler claim is made.

These fixtures establish only that the selected bounded cases were admitted
and fully enumerated on this build. They do not measure joint-relation growth,
LP or verification runtime, memory, provider CPU, or enforced resource limits.
The path cap is `2^horizon` (at most 256 here); larger catalogues and horizons
remain unmeasured. No performance winner, cross-host comparison, or general
scalability guarantee follows from this report.

## Evidence files

- `measure.jsonl`: all seven raw repetitions for each of ten fixtures
- `summary.csv`, `summary.json`: validated median/range summaries
- `host.json`: compiler, build mode, host scope and measurement boundary
- `prebuild.json`, `postrun.json`: clean source-tree and executable receipts
- `configure.log`, `build.log`: path-redacted build logs

Raw measurement SHA-256: `3d8fdf8589b7194f50986a3c6a8adef12abd5df3f7cc5233bfd6458abee9bbec`.
The run was captured from the exact source commit above; the collector checks
the full ten-fixture matrix and all seven repetitions before producing the
summary.
