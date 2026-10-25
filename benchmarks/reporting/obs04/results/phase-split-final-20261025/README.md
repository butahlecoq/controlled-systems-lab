# OBS-04 loader and admission phase captures

Five clean Release process captures of the fixed analytic T-S01 fixture. Each
completed 32 attempts: one warmup and seven measured repetitions for each
strategy/instrumentation arm. All 160 attempts passed the analytic and witness
checks. The records share one `ComparisonSpecId` and have distinct run IDs.

The source is commit `63ae0162e1cd85d94b347c68a875a2fcff09ede6`, with clean
source tree hash
`887f377545a4004edfedc3980fa479ee5b65a8a55cfd75e40fafebda116671c6`.
The Release executable used GNU C++ 16.2.1, HiGHS 1.11.0 and Qhull 8.0.2.
The host was Linux Omarchy on kernel `7.2.5-3-omarchy`, with an AMD Ryzen 5
3550H and 8 logical CPUs. One solver thread and one driver worker were
requested and observed. Workspaces were fresh per attempt; each arm had one
excluded warmup. The OS cache was not flushed.

The loader parse interval measures the actual bounded parser. Translation and
input validation include schema/field checks, model construction, and problem
assembly. The canonical resolution/snapshot interval is nested inside
translation; semantic load is the inclusive post-parse load interval. Admission
is inclusive; capability callback intervals are nested inside it, call the
original callback once, and exclude common guards and other registry work.
Nested intervals are not additive. The fixture is intentionally tiny; these
values make no application-scale latency or performance-winner claim.

| Phase | Median | Range |
|---|---:|---:|
| Scenario file read | 77,664 ns | 35,479–100,922 ns |
| Loader JSON parse | 106,439 ns | 51,892–112,165 ns |
| Translation and input validation (inclusive) | 233,900 ns | 136,540–253,456 ns |
| Canonical resolution and source snapshot (nested) | 125,645 ns | 73,963–141,011 ns |
| Semantic load (inclusive) | 237,671 ns | 139,893–263,164 ns |
| Provider registration | 162,732 ns | 97,429–193,112 ns |
| Comparison admission (inclusive) | 188,992 ns | 103,016–207,779 ns |
| Reach-back capability callback (nested) | 10,616 ns | 8,032–37,295 ns |
| Direct-joint capability callback (nested) | 6,635 ns | 2,374–8,520 ns |

Each JSON record and stdout log retains raw results and the structured
`csl.obs04-shared-preflight/3` timings. Record SHA-256 digests:

| Run | Comparison run ID | Record SHA-256 |
|---|---|---|
| 01 | `e1c0d1956d110169b8d1f4939b937c814b3be312ee3d9998c953f9f593073073` | `ed70262ac3a33767f106c127fa261eb7fb6bae835d6a3e6d26d5e82548efd710` |
| 02 | `5c82948c0e872e3ee7cd052ccf1beaef142773c7ee8bd8262feddc1e40e634d3` | `2368d0fe37088b2165934e1db40c6b69823d9c33f5bb38906902d0cf02a6a331` |
| 03 | `fa3b5cc407238d18419d11c60aa19e7660abda6ec6cac6752c7d4bbf5c0851e0` | `c66f9abc4ea75e05cfc4110edb59703daa72a0728ce6c0f206aa3f09ad979d4b` |
| 04 | `0dd27254f4871a6d6ebe71764a466b07deabcea4c90517858b028aa59ff4fea3` | `fd33fc0068fcb74e865c37ad019b7b807d17abafb2da3b4fbf01cae43f0592b0` |
| 05 | `e20a7bb6ab586535a98f45c3fe2f292cec22664f98a85bccc70f359ebd694d27` | `d28118dabb6c192e5384d10c3f6b7eef96ba21a6c273f5cc7c779ab53beebd06` |
