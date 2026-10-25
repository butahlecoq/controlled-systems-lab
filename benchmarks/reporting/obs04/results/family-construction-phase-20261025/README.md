# OBS-04 family-construction phase capture

This capture exercises the T-S01 analytic comparison after adding complete-family
proposal timing. It is a functional smoke run, not a performance comparison.

- Source commit: `0d2f4f35376c6e8dd98af35c4dd18919511efaba`
- Source snapshot SHA-256: `4073cabf405667938fea1e38a22dfe89e41b2c15d3d1249324786f3145f54def`
- Source tree was clean when the Release binary was configured.
- Compiler: GNU 16.2.1, x86_64, Release, Unix Makefiles
- Backends: HiGHS 1.11.0 and Qhull 8.0.2
- Attempts: 32 total, one warmup plus seven measured repetitions per strategy and instrumentation mode
- Outcome: 32 passed, zero failures; 16 instrumentation enabled and 16 disabled
- The enabled records contain the family-construction span for both strategies. Disabled records retain `null`.
- Comparison record digest: `65825931eb4d6cd1aed477556f174710ccb1e7b4a2b0acb7be91ac001ba2351c`
- `stderr.log` is empty. The driver decoded and validated the saved comparison record before writing it.

The fixture is only the reviewed analytic T-S01 case. These durations do not
identify a general limiter or establish a performance winner. Native backend
thread counts and CPU timings remain unavailable.

To reproduce, configure and build the standalone driver with the repository's
pinned backend dependencies, then run it with `--record <path>`; the JSONL event
stream is written to stdout and can be retained beside that artifact.
