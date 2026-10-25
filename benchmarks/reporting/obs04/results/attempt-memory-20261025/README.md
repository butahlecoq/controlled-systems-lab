# OBS-04 per-attempt peak RSS observations

Five clean Release process captures of the fixed analytic T-S01 fixture. Each
record contains 32 attempts: one warmup and seven measured repetitions for each
strategy/instrumentation arm. All 160 attempts passed the analytic complete
family checks; all 160 per-attempt RSS readings were available.

The run-time source commit is `58fe95b96ab061a8a86d1dfee838b0d2c57762e3`,
with clean source tree hash
`4ade4779f4597381d6e97bfaab2a1684e259417775d314c3c9e4e256c0eb81d6`.
The Release executable was built with GNU C++ 16.2.1, HiGHS 1.11.0 and Qhull
8.0.2. The host was Linux Omarchy on kernel `7.2.5-3-omarchy`, with an AMD
Ryzen 5 3550H and 8 logical CPUs. One solver thread and one driver worker were
requested and observed. Each attempt used a fresh workspace; one warmup per arm
was excluded from measured summaries. No profiler was active during these
captures. The pre-capture 1/5/15-minute load averages were 2.53/3.96/3.28 on
8 logical CPUs; both strategies and instrumentation arms were interleaved
within each process.

On Linux, `process_peak_rss_bytes` is the process `VmHWM` high-water mark after
resetting it immediately before `StrategyPort::run` and reading it after the
call. It includes the driver and all process threads, so it is a process peak
observation, not strategy-only allocation or a memory cap. The run records do
not claim memory enforcement. The fixture is intentionally tiny and the
measurements support no performance winner or application-scale memory claim.

Across the 35 measured calls per arm, observed process peak RSS was:

| Strategy | Instrumentation | Median | Range |
|---|---|---:|---:|
| Reach-back | disabled | 13,418,496 B | 12,754,944–14,430,208 B |
| Reach-back | enabled | 13,451,264 B | 12,550,144–14,213,120 B |
| Direct-joint | disabled | 13,492,224 B | 12,460,032–14,213,120 B |
| Direct-joint | enabled | 13,504,512 B | 12,480,512–14,213,120 B |

Every raw `csl.comparison-record/1`, stdout capture, and saved-record HTML
render is retained below. The renderer consumes only the saved record. Each run
contains event `/9` payloads and completed the codec's exact record round-trip
before the artifact was written.

| Run | Comparison run ID | Record SHA-256 |
|---|---|---|
| 01 | `d814e203485893dda46044a0b26cc048a7d1eb1024824e2051d4d40b6e3eedd9` | `80ccea4f5f870981dab884d4436ffd4429fac0306e47c2a95db6cedabfb0e582` |
| 02 | `796e2fed68678e4def2600783529db933a92f7161ecadab213c45dcdc316caaa` | `115c636722773d0c61f6cdcdce06faefc583c2376c4e73feb3dfd557dea61da9` |
| 03 | `9efee586e08bc3d8b964d1c78029dbe43f666581198eeacd1ec8d145977b682e` | `38ab295e421323a7e5400e106d65a0b155ab516e8741171e64eeadff52134b51` |
| 04 | `008bd3ed2de8cd5f71df6f1d30fd52a84567d545f83b00499fcea1908b44bf0e` | `8b1e133ff26bdbdb1497543c11449b2bcd284a33235af9fa1c64ce8ce41751c1` |
| 05 | `fea393398da880b1a14832b9f4ebde84e16fa3c1f6d50979ca2f1245a2ba1cc1` | `ece3cf88566f8b0054f741e2654b8a2e32c7a29ea6e562efa1cdfa6f358c8ccb` |

Re-render a record with:

```sh
python3 scripts/reports/obs04/render_saved.py \
  --record benchmarks/reporting/obs04/results/attempt-memory-20261025/run-01.json \
  --out /tmp/obs04-attempt-memory.html
```
