# EXT-07 capability admission and enumeration profile

This bounded profile measures `report_hybrid_capability`, which validates a
request's hybrid model and enumerates its complete allowed mode/edge paths. It
does not compose joint relations, invoke a solver, or measure provider work.

## Run definition

- Source commit: `4c3371a05aad6be3f399b4947e9ab27a63fd6262`
- Source tree: `8143b697ab82b8f459a6aa723b1fe9c3155f2512`
- Configuration: CMake Release, GNU C++ 16.2.1, C++20, CMake 3.31.6
- Native HiGHS adapter disabled; standalone capability-report option enabled
- Host: Linux x86_64, 8 logical processors; one process and one worker
- Workload: ten deterministic fixtures, 1,000 calls per batch, one excluded
  warmup batch and seven measured batches per fixture
- Timing excludes fixture construction, build, and JSON serialization
- Every timed call checks admission, completed enumeration, and a complete path
  count; the collector verifies all 70 measured rows and the expected fixture
  matrix

## Summary

`summary.csv` reports the median and range of each 1,000-call batch. The last
column divides the batch median by 1,000; it is descriptive latency for this
specific capability-report function, not end-to-end hybrid solve time.

| State/control dimension | Horizon | Modes | Edges | Complete paths | Median per call (ns) | Range per call (ns) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 2 | 1 | 1 | 1,997 | 1,989–2,017 |
| 2 | 1 | 2 | 1 | 1 | 2,178 | 2,152–2,260 |
| 4 | 1 | 2 | 1 | 1 | 2,608 | 2,595–2,696 |
| 8 | 1 | 2 | 1 | 1 | 3,936 | 3,857–4,133 |
| 1 | 2 | 2 | 2 | 1 | 2,789 | 2,728–2,849 |
| 1 | 4 | 2 | 2 | 1 | 3,806 | 3,734–4,450 |
| 1 | 8 | 2 | 2 | 1 | 5,694 | 5,562–6,073 |
| 1 | 4 | 4 | 4 | 1 | 5,929 | 5,887–6,067 |
| 1 | 4 | 8 | 8 | 1 | 11,351 | 11,277–11,525 |
| 1 | 8 | 2 | 4 | 256 | 109,406 | 107,245–110,662 |

The single-path cases show increasing admission time as dimensions and catalog
sizes grow. At horizon 8, the 256-path fixture takes a median 109,406 ns per
call, compared with 5,694 ns for the one-path fixture with the same state
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

Raw measurement SHA-256: `925d2910a9a3080d86643d6801fb0f655770ee96113bc31a9a056f17a6b813de`.
The run was captured from the exact source commit above; the collector checks
the full ten-fixture matrix and all seven repetitions before producing the
summary.
