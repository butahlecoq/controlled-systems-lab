# OBS-04 loader and admission phase captures

Five clean Release process captures of the fixed analytic T-S01 fixture. Each
completed 32 attempts: one warmup and seven measured repetitions for each
strategy/instrumentation arm. All 160 attempts passed the analytic and witness
checks. The records share one `ComparisonSpecId` and have distinct run IDs.

The source is commit `e8179bda9f637a2da3fa3537fd695df9c661aae3`, with clean
source tree hash
`68c50734c8eebc576412c7825ea94e80cf1084c217a7f8769aa3e6bd3072fb6e`.
The Release executable used GNU C++ 16.2.1, HiGHS 1.11.0 and Qhull 8.0.2.
The host was Linux Omarchy on kernel `7.2.5-3-omarchy`, with an AMD Ryzen 5
3550H and 8 logical CPUs. One solver thread and one driver worker were
requested and observed. Workspaces were fresh per attempt; each arm had one
excluded warmup. The OS cache was not flushed.

The loader parse interval measures the actual bounded parser. Translation and
input validation include schema/field checks, model construction, and problem
assembly. The canonical resolution/source snapshot interval is nested inside
translation; semantic load is the inclusive post-parse load interval. Admission
is inclusive; capability callback intervals are nested inside it, call the
original callback once, and exclude common guards and other registry work.
Nested intervals are not additive. The fixture is intentionally tiny; these
values make no application-scale latency or performance-winner claim.

| Phase | Median | Range |
|---|---:|---:|
| Scenario file read | 38,622 ns | 36,667–52,172 ns |
| Loader JSON parse | 60,064 ns | 57,689–83,811 ns |
| Translation and input validation (inclusive) | 131,861 ns | 122,712–170,344 ns |
| Canonical resolution and source snapshot (nested) | 73,334 ns | 66,909–95,683 ns |
| Semantic load (inclusive) | 137,728 ns | 127,880–173,697 ns |
| Provider registration | 94,914 ns | 89,607–120,896 ns |
| Comparison admission (inclusive) | 103,366 ns | 95,404–127,182 ns |
| Reach-back capability callback (nested) | 7,194 ns | 5,727–10,337 ns |
| Direct-joint capability callback (nested) | 4,749 ns | 4,331–5,239 ns |

Each JSON record and stdout log retains raw results and the structured
`csl.obs04-shared-preflight/4` timings. Record SHA-256 digests:

| Run | Comparison run ID | Record SHA-256 |
|---|---|---|
| 01 | `979ee589527dfe14469480225af15141257938b24766ac441f9667c532606fac` | `822cb0c2c41c24ae0a92314ccf5dc462a07fe456819f1148ec55a059000d1781` |
| 02 | `265fc894831145152eed1599e783047b7b36bc2fe6bfc359176ad7ce4fb95a9d` | `d967272d07078f806a68e78e1aa20390b5574cf322474c60bd49228ca2abf08e` |
| 03 | `90096e9b517d737da0ca4ee2b79bd6c36ed583e5b70c6a0c8193b6592db8ca90` | `ca0c302c3f4f7c76b277d4c82b5592428d959eaa2189b0b2a07d2e4c9dbbd0e1` |
| 04 | `1a5282dc93e8c3a923df1fdfcacce90a3e4ad3e5b5195c15954b4730f17ddde7` | `d8d4d9d9104733ad0c46aa5caf1e54c2142eb1a1456dc36b9b6e04c0145d8bb1` |
| 05 | `2104dd26c11d2f2de7601b28f20b406eeb1cf8015b665c8670641b1e70875b98` | `e895ea66c8bf1e21513063a12b7ec823cb34f63caba0589f588fa7b95712c7a9` |
