# OBS-04 per-attempt CPU and scheduler observations

These five fresh comparison processes use the same `ComparisonSpecId`, with five distinct `ComparisonRunId`s. They were built from clean source commit `f8c62cb86ccaaf9644a9a973a5f79f41dc6058d1` (tree SHA-256 `80706b5b6ba4ecb1c464d8bf02abc3e9e1557fc14d578dc2892aef25004c71e2`) as Release/GNU 16.2.1, with HiGHS 1.11.0 and Qhull 8.0.2. The executable SHA-256 is `121deb424eef3bf5f616119a7ad5bacdf310a0f2512726ffe17bc9b94464c361`. The host was Omarchy/Linux 7.2.5-3 on an AMD Ryzen 5 3550H with 8 logical CPUs.

Each process retained 32 attempts: four strategy/instrumentation arms, one warmup and seven measured repetitions per arm. All 160 attempts passed the analytic family and independent witness checks; stderr was empty. Each event `/8` records strategy wall time, process CPU time during the strategy invocation, and adapter-reported backend scheduler width. All attempts reported width 1. This width is the configured scheduler width reported by the adapter, not the number of busy threads. Process CPU includes all driver threads during the strategy call; it excludes setup, witness selection, and verification.

## Paired instrumentation observations

The values below are enabled-minus-disabled differences within the same process and repetition. There are 35 measured pairs per strategy.

| Strategy | Wall difference median (range), ns | CPU difference median (range), ns | Enabled slower pairs |
| --- | ---: | ---: | ---: |
| Reach-back | +3,395,927 (2,962,278–4,922,671) | +3,402,930 (2,933,502–4,916,179) | 35/35 |
| Direct-joint | +263,513 (-180,333–605,880) | +258,738 (-181,711–607,101) | 34/35 |

Absolute per-arm medians and ranges, process IDs, run/spec IDs, binary identity, and attempt records are in `summary.json` and `run-01.json` through `run-05.json`. Each saved record has an HTML rendering. The ranges overlap for direct-joint, so its paired difference is not consistent. The result is fixture-specific and inconclusive; it does not support a general instrumentation-overhead claim, end-to-end performance claim, or strategy winner.

## Separate limiter profiles

The same executable was profiled in separate runs, 32 strategy calls per arm. Each profile acknowledged 64 enable/disable transitions. `perf report` decoded 889 reach-back samples and 253 direct-joint samples; both reports show zero lost samples. Requested frequency was 4,999 Hz, but effective frequency is not reported. The sampling window includes FIFO command/acknowledgement overhead. Allocation/free, C++ string operations, and HiGHS setup are visible candidates, but this small profile does not isolate a unique limiter. Raw profiles, capability metadata, reports, and logs are retained in `limiter-profile-userspace-perf-32-*`.

The profile tool was Arch `perf` 7.2.3-1 and was run from a signed package extracted under `/tmp` with its signed shared-library dependencies. No system package was installed. Its exact sample scope and limitations are recorded in each `capability.json`.

## Superseded attempts

`superseded/` preserves five earlier successful but dirty-source captures and the initial failed artifact-serialization attempt. They are not part of the reported five-process sample. The serialization failure showed that the comparison artifact layer needed explicit event `/8` support; the clean-source records above were captured after that support was committed.
