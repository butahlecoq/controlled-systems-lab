# OBS-04 loader and admission phase captures

This capture set was superseded by
[`phase-split-final-20261025`](../phase-split-final-20261025/README.md), which
adds a nested canonical resolution/source snapshot timer. These records retain
their exact source provenance and remain valid for the earlier phase schema.

Five clean Release process captures of the fixed analytic T-S01 fixture. Each
completed 32 attempts: one warmup and seven measured repetitions for each
strategy/instrumentation arm. All 160 attempts passed the analytic and witness
checks. The records share one `ComparisonSpecId` and have distinct run IDs.

The source is commit `99a048ae427ae9ff39d2c7f33b141879fbd946e0`, with clean
source tree hash
`a6c253cb73b5352563ed30790b7195e6af3778ccd6c17aaed5c515e2650b8142`.
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
| Scenario file read | 60,972 ns | 59,086–71,448 ns |
| Loader JSON parse | 100,712 ns | 55,664–113,353 ns |
| Semantic load and resolution | 209,805 ns | 146,179–233,202 ns |
| Provider registration | 130,953 ns | 110,769–216,230 ns |
| Inclusive comparison admission | 142,197 ns | 106,159–212,738 ns |
| Reach-back capability callback (nested) | 8,032 ns | 7,682–11,034 ns |
| Direct-joint capability callback (nested) | 4,261 ns | 3,841–6,216 ns |

Each JSON record and stdout log retains the raw result and the structured
`csl.obs04-shared-preflight/3` measurement. Record SHA-256 digests:

| Run | Comparison run ID | Record SHA-256 |
|---|---|---|
| 01 | `5152a9f2575a2e3e3836c0e3cf9bec2a58ff66dab861c56282eb1bc8f3f701bd` | `d6e436c375e02c582104388ddded3005c87c21f37b70a8097637423f38bc577c` |
| 02 | `120a89c62188c6efdda1ca45783dfbf31b504d783d657e797f7825a013a3678f` | `4f4d81b7e8efe65fde2e38618df98b0723ba8a0843a8d6d4dd4affdf4b474e55` |
| 03 | `1bcd5b729cea0f7938947db52e450f3d3925fd917b8b8cd7a31e50019954866f` | `5d99c11f0e3dbb088a3f8d10934f181033533dad6ef7b98150278ac2720bcd99` |
| 04 | `5c2480c590a9e5054a79f87e99bd7e13239593ed8aa9cc596a65c54b01292441` | `d14a2adbf0cd22367a9ce21cba3a97f4c1f6c52e5dc35780664a97b4e6ec25d8` |
| 05 | `c2376e85b43575996753e0e38382325e6988394a73545c596e6fe7ebc91a86d6` | `925495b1d3d054ca1656fbccbdd949c5e08a9013db3d93401f3205e1d95ac20b` |
