# EXT-03 memory-lift transform microbenchmark

This is an exploratory, single-fixture measurement of temporal memory lifting and history recovery. It does not time or compare control solvers.

The fixture is a two-step scalar integrator with initial control memory `p0=1/4` and both slew increments in `[-1/4,1/4]`. Every call constructs the source problem, applies the lift, checks coordinate identities and index maps, recovers the known feasible lifted history, and checks original dynamics, control bounds, slew bounds, and terminal value.

Seven measured batches of ten calls followed one excluded warmup batch. All 70 measured calls passed. Median elapsed time was 45.63 microseconds per call; the range was 43.15–56.91 microseconds per call. The limiter is not source-profiled. No speedup, solver, application-scale, or scalability conclusion follows.

`raw-events.jsonl` retains all batch events. `records.json` stores the validated summary, `environment.json` the build and machine identity, and `manifest.json` hashes the bundle files. Rebuild with the command in `commands.txt`; render only from these saved records.
