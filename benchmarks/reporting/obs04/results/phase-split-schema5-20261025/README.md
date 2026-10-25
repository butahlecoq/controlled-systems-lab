# OBS-04 shared-preflight schema `/5` captures

Five sequential Release process captures of the fixed analytic T-S01 fixture.
Each comparison record contains 32/32 completed attempts: one warm-up plus
seven measured repetitions for each strategy/instrumentation arm. The records
share one `ComparisonSpecId`; each has a distinct `ComparisonRunId`. No stderr
was emitted. These runs validate the new directly measured preflight fields;
they are not a strategy performance comparison and support no speedup claim.

The executable was built from clean source commit
`63978d01c7b7fb52e2b16219940c037240d05a96`, with source-tree SHA-256
`ca624f1c35375703b2473b203d4bb4d5f5641dfc38959098fc5a96b9d9958ba9`
(`source_dirty: false`). Release build: GNU C++ 16.2.1, Ninja, HiGHS 1.11.0,
Qhull 8.0.2. Host: Linux Omarchy, kernel `7.2.5-3-omarchy`, AMD Ryzen 5 3550H,
8 logical CPUs. One worker and one backend thread were requested. Workspaces
were fresh per attempt; OS caches were not flushed. Executable SHA-256:
`bc9d35014426d0bcbf8712b071f91dcb469900b62900519cf15a0480a11ef653`.

Each table value is one shared-preflight observation per process. The five
values are reported as median and full range. The fixture is intentionally
tiny, and these timings do not establish application-scale latency. The
registry callback-external intervals, capability callback intervals, common
guards, and inclusive admission are nested; do not add nested values to
admission or infer a residual by subtraction.

| Phase | Median | Range |
|---|---:|---:|
| Comparison admission (inclusive) | 135,982 ns | 106,230–262,676 ns |
| Common application guards (nested) | 1,955 ns | 1,886–2,445 ns |
| Reach-back registry outside capability callback (nested) | 71,727 ns | 53,499–105,810 ns |
| Reach-back capability callback (nested) | 7,543 ns | 6,635–18,718 ns |
| Direct-joint registry outside capability callback (nested) | 23,187 ns | 20,044–86,953 ns |
| Direct-joint capability callback (nested) | 4,819 ns | 4,400–6,635 ns |

Each JSON record embeds all 32 run artifacts and measurements. The paired
stdout log contains `csl.obs04-shared-preflight/5`; stderr logs are empty.
Record SHA-256 and `ComparisonRunId`:

| Run | ComparisonRunId | Record SHA-256 |
|---|---|---|
| 01 | `cf8989ae2c3e8628bc69d3d6f80cff67cb5db9ba4f1deb5e5f012c111b65caff` | `35884f21e2afa48f8fdcb170a41de6c81980a28dffaf211efe69bdfa906316c0` |
| 02 | `aff581b00c7d81078a8b769be16b198ba8ac7dc536f730633baaf9f7154c4c9c` | `5c56da1d9f528beb5a9716eefee556e3e321539704dae2688a90fc4c41d1e43b` |
| 03 | `2919847be14017a3cc5924c8ded3fb580e2293d40e49c8b56e8696189e4c9511` | `dbe356b7b189036d85793070f6f5d7eed9b316f6f77b4a05b1fd3a89d72c4512` |
| 04 | `36470ff8ceeb8f542683b28e926f81f724d906eacff425352f9ad618e4ee2143` | `7e2d53ce61732a5a1e4692bdbf5e7e771a1d57ff4ba74d0747e932ac4049f2fd` |
| 05 | `860707c31325d925ad8ed976a765c75170891138b5a9226337efcff2d71727dd` | `d9f2c35dfa1d0c9989cffe4bda7898cfbbfbd4667f984f1feb65812bd4b5505e` |
