# OBS-04 StrategyPort::run perf sample

This exploratory user-space profile samples only the calls to `StrategyPort::run`
for the analytic T-S01 fixture. Sampling is disabled during analytic baselines,
warmup, workspace creation, result validation, and JSON output. The driver
sends `enable` immediately before each call and `disable` immediately after it
through `perf record`'s control FIFO. Control writes are synchronous with FIFO
consumption; command/OS scheduling overhead around those boundaries is not
measured as part of `run`.

## Provenance

- Source commit: `9dbdf89d` (`Add call-window control to OBS-04 profile driver`).
- Release executable SHA-256: `6bafa99c946c25c3d65addb482677e5cff732ba1d71f9065f4772dbf4ef69b6b`.
- Compiler: GCC 16.2.1, CMake Release configuration.
- Host: AMD Ryzen 5 3550H, 8 online/available logical CPUs; Linux `7.2.5-3-omarchy`, x86_64.
- Profiler: Linux perf `7.2.3-1`; user-mode `cycles:u`, requested frequency 499 Hz, DWARF call graph with 8,192-byte user stack, maximum profile size 32 MiB.
- The executable configures one solver thread and one outer worker. Host load was not captured or controlled; actual native-library threads were not instrumented.
- A sanitized target environment and `/tmp` working directory were used. A byte scan of the raw profile data found no `/home/butahlecoq` or `codex/worktrees` paths.

## Captures

| Strategy | Calls | Passed | Samples | Lost | Sample window |
| --- | ---: | ---: | ---: | ---: | --- |
| reach-back | 500 | 500 | 1,117 | 0 | `StrategyPort::run` only |
| direct-joint (Strategy B) | 2,000 | 2,000 | 485 | 0 | `StrategyPort::run` only |

Every call passed the driver's analytic-family result check. This is not a timing comparison: the call counts differ, samples are not normalized into work or latency, and the captures do not establish a winner. Both symbol summaries show allocator activity (`malloc`, `cfree`, C++ allocation/string routines); this does not prove allocation is the unique limiter. Some sampled addresses remain unsymbolized. The fixture is small and analytic, so do not generalize this profile to application workloads.

The compressed raw `perf.data` files are retained beside short `perf report` summaries. To inspect them, decompress a copy and run `perf report --stdio --no-children --call-graph graph` with a compatible Linux perf build and the matching executable/debug symbols.
