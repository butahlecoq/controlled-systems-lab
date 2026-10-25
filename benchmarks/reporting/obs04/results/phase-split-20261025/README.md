# OBS-04 loader and admission phase captures

This initial capture set was superseded by
[`phase-split-corrected-20261025`](../phase-split-corrected-20261025/README.md)
after review found the optional timer read the clock even when disabled. The
corrected source avoids clock reads without an observer; these original records
remain here with their exact source provenance.

Five clean Release process captures of the fixed analytic T-S01 fixture. Each
process completed 32 attempts: one warmup and seven measured repetitions for
each strategy/instrumentation arm. All 160 attempts passed the analytic and
witness checks. The records share one `ComparisonSpecId` and have distinct run
IDs.

The source is commit `4fba0b9ff3a158cc6d7960bfccc07d2452e0bc85`, with clean
source tree hash
`bcf7f623747bdd6b294d6e65a93b5004378c2d21e412734c415ff9c7058cb38a`.
The Release executable used GNU C++ 16.2.1, HiGHS 1.11.0 and Qhull 8.0.2.
The host was Linux Omarchy on kernel `7.2.5-3-omarchy`, with an AMD Ryzen 5
3550H and 8 logical CPUs. One solver thread and one driver worker were
requested and observed. Workspaces were fresh per attempt; each arm had one
excluded warmup. The OS cache was not flushed.

Phase timings are process-level observations. The parser interval is the real
bounded parser called by the loader. Semantic load includes format dispatch,
schema/model construction, canonical resolution and source snapshot creation.
Admission is inclusive; the two capability callback intervals are nested inside
it, call the original callback once, and exclude common guards and other
registry work. These nested intervals are not additive with admission. The
fixture is intentionally tiny; these values make no application-scale latency
or performance-winner claim.

| Phase | Median | Range |
|---|---:|---:|
| Scenario file read | 52,940 ns | 36,388–82,413 ns |
| Loader JSON parse | 80,667 ns | 53,359–101,340 ns |
| Semantic load and resolution | 176,490 ns | 128,858–250,033 ns |
| Provider registration | 123,689 ns | 104,553–186,407 ns |
| Inclusive comparison admission | 122,153 ns | 95,683–200,446 ns |
| Reach-back capability callback (nested) | 7,753 ns | 6,704–13,969 ns |
| Direct-joint capability callback (nested) | 4,819 ns | 4,330–16,273 ns |

Each JSON record and stdout log retains the raw result and the structured
`csl.obs04-shared-preflight/3` measurement. Record SHA-256 digests:

| Run | Comparison run ID | Record SHA-256 |
|---|---|---|
| 01 | `2b8b2301975d86f1a18bc1caf617a0a0e9e086885cfed289eb422096d4e3b322` | `335f6295c183cfcb92fa726b60f6a77d2f81820c8542d7e4afddc19c9e8e29bb` |
| 02 | `287d7ea55f734cf5f9d1aa858df900fe1a47f76905a97914b19a98c27b434e2c` | `9d115183c800ca88dfd4a5f09c2a6644c560797c7387385cce1b4a4db86134ad` |
| 03 | `f2ae5d88e06bd182ff7354f550dfe4d09da2484e8a888cd82fdc507856dfa8b2` | `7d09c1a6056a8625e2d880717dee04c8dd7926ee5cf17a7181a3517dc413940e` |
| 04 | `55434d06ddd9f81455a1c03cddfbcbe2bc38ab1469cf39b904acde572c61816b` | `7e539044b2dfe551d25851fc791c05492199548e577d05d893812f4abd98abdf` |
| 05 | `454868f6a2c0f8e5abda0c80dc18e62554ecc4b4e2df24d3d2fd667a789b2097` | `7c93332d57317153a6675b14b4939d9c4f2b6251e655bddffc02f05d73a101d0` |
