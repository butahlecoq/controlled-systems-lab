# EXT-07 capability admission and enumeration profile

This bounded profile measures `report_hybrid_capability`, which validates a
request's hybrid model and enumerates its complete allowed mode/edge paths. It
does not compose joint relations, invoke a solver, or measure provider work.

## Run definition

- Source commit: `41883fdca2f15aad3d05808894a64b4ab0a4195d`
- Source tree: `62a1813cbacab1fc4bd5af2f4b2b15b5f96aa229`
- Configuration: CMake Release, GNU C++ 16.2.1, C++20, CMake 3.31.6
- Native HiGHS and Qhull adapters disabled; standalone capability-report option enabled
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
| 1 | 1 | 2 | 1 | 1 | 1,943 | 1,929–2,110 |
| 2 | 1 | 2 | 1 | 1 | 2,134 | 2,089–2,581 |
| 4 | 1 | 2 | 1 | 1 | 2,813 | 2,476–3,197 |
| 8 | 1 | 2 | 1 | 1 | 3,812 | 3,719–4,834 |
| 1 | 2 | 2 | 2 | 1 | 2,752 | 2,682–3,028 |
| 1 | 4 | 2 | 2 | 1 | 3,818 | 3,653–4,506 |
| 1 | 8 | 2 | 2 | 1 | 5,652 | 5,484–5,958 |
| 1 | 4 | 4 | 4 | 1 | 6,301 | 5,836–6,695 |
| 1 | 4 | 8 | 8 | 1 | 11,543 | 11,326–17,570 |
| 1 | 8 | 2 | 4 | 256 | 112,360 | 111,027–127,369 |

The single-path cases show increasing admission time as dimensions and catalog
sizes grow. At horizon 8, the 256-path fixture takes a median 112,360 ns per
call, compared with 5,652 ns for the one-path fixture with the same state
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

Raw measurement SHA-256: `37e05ea5c0fdcecf95325095820f186b07521483bed105631baebc3476c5e3f2`.
The run was captured from the exact source commit above; the collector checks
the full ten-fixture matrix and all seven repetitions before producing the
summary.
