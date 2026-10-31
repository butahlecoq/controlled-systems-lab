# REVIEW-05 HORIZON-01 clean committed-source capture

This bundle was built and captured from clean source commit `34bc9fdf437d6eaa63f28c579acc6c82f506ede5`. The earlier exploratory run is preserved in `../review05-horizon01-20261030/` and is not overwritten.

The run covers the synthetic scalar integrator at horizons 2, 4, and 8. It performs one excluded warmup pair and six alternating measured pairs per horizon. The timed region is `SynthesisWorkspace::run()`; process setup and launch are recorded separately. The 42 attempts all completed; each process requested one backend thread and observed width one. The independent checker marked 21 Strategy B outputs verified and 21 reach-back outputs inconclusive. There were zero verified paired repetitions at every horizon. Therefore the durations below are descriptive only; they do not support a ranking, speedup, or scalability claim. The checker verifies the fixture-specific analytic optimum where the required candidate rows are present; it does not establish completeness of a candidate family.

## Descriptive all-completed timing

| Horizon | Reach-back median (range) | Strategy B median (range) | Verified pairs |
|---:|---:|---:|---:|
| 2 | 8.503 ms (5.954–12.685) | 1.115 ms (0.711–1.528) | 0/6 |
| 4 | 14.880 ms (10.682–19.919) | 0.978 ms (0.770–1.817) | 0/6 |
| 8 | 26.599 ms (22.614–32.164) | 0.903 ms (0.778–2.012) | 0/6 |

Host load averages at capture start were 10.03, 9.50, and 5.31 on 8 logical CPUs. AB/BA order was balanced, but this load and the spreads make the timings unsuitable for a comparative performance conclusion. No profiler was available (`perf` and `pidstat` are absent), so the runtime limiter is not identified.

## Replay and evidence

The CMake 3.31.6 Release build log, binary/source hashes, host metadata, immutable inputs, all stdout/stderr, attempt records, independent checks, summary, and HTML rendering are retained in this directory. `SHA256SUMS` covers the bundle files except itself. The corresponding source is in `benchmarks/reporting/review05/`.
