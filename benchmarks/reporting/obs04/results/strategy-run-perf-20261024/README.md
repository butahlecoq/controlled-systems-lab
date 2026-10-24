# OBS-04 approximate StrategyPort call-boundary perf sample

This exploratory user-space profile attempts to gate sampling around
`StrategyPort::run` calls for the analytic T-S01 fixture. The driver sends
`enable` immediately before each call and `disable` immediately after it through
`perf record`'s control FIFO. It does not wait for command-completion
acknowledgements, so a sampling transition may straddle a call boundary. Treat
these as approximate run-boundary profiles, not isolated samples of the
`StrategyPort::run` body. Perf begins disabled; after processing each command,
it is disabled during analytic baselines, warmup, workspace creation, result
validation, and output.

## Provenance

- Source commit: `ffb2032b` (`Label OBS-04 perf window as approximate`).
- Release executable SHA-256: `92847337c15f54048cd0bb81672e09c04c0ee58ba0481c3e6a9940fa29c02280`.
- Compiler: GCC 16.2.1, CMake Release configuration.
- Host: AMD Ryzen 5 3550H, 8 online/available logical CPUs; Linux `7.2.5-3-omarchy`, x86_64.
- Profiler: Linux perf `7.2.3-1`; user-mode `cycles:u`, requested frequency 499 Hz, DWARF call graph with 8,192-byte user stack, maximum profile size 32 MiB.
- The executable configures one solver thread and one outer worker. Host load was not captured or controlled; actual native-library threads were not instrumented.
- A sanitized target environment and `/tmp` working directory were used. A byte scan of the raw profile data found no `/home/butahlecoq` or `codex/worktrees` paths.

## Captures

| Strategy | Calls | Passed | Samples | Lost | Sample window |
| --- | ---: | ---: | ---: | ---: | --- |
| reach-back | 500 | 500 | 1,131 | 0 | Approximate run-boundary gate |
| direct-joint (Strategy B) | 2,000 | 2,000 | 486 | 0 | Approximate run-boundary gate |

Every call passed the driver's analytic-family result check. This is not a timing
comparison: the call counts differ, samples are not normalized into work or
latency, and the captures do not establish a winner. Both symbol summaries show
allocator activity (`malloc`, `cfree`, C++ allocation/string routines); this does
not prove allocation is the unique limiter. Some sampled addresses remain
unsymbolized. The fixture is small and analytic, so do not generalize this
profile to application workloads. These files cannot support a precise limiter
claim until perf command completion is synchronized at each call boundary.

The compressed raw `perf.data` files are retained beside short `perf report`
summaries. To inspect them, decompress a copy and run
`perf report --stdio --no-children --call-graph graph` with a compatible Linux
perf build and the matching executable/debug symbols.

## Control protocol status

These retained files predate the acknowledged-control change and remain
approximate run-boundary captures. The current driver waits for perf's `ack\n`
response after every control command, but no new host capability or synchronized
profile is recorded by these historical files. Run the opt-in Linux PR probe to
produce a separate result; it reports `unavailable` when runner permissions or
PMU access prevent collection.
