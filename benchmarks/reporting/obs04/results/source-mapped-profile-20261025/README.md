# OBS-04 source-mapped limiter diagnostic

This is a separate profiling diagnostic for the active OBS-04 PR head, not part
of its tuned Release timing records. Both profiles used the exact T-S01 driver
at source commit `51c675355aadfcc6e1b43052412d2cca57346e06`, source tree SHA-256
`3dfc792fad4ba3d5b1d573ec308ce2febb1352e0da278541a75c6dd1a019f87e`, and binary
SHA-256 `c3d8c5af7ee4485c28a3e3a5854a52a2422a94ff373b277ba9a880d14b8382f7`.
The binary is an optimized Release build with GCC 16.2.1 and `-O3 -DNDEBUG -g1`
line tables. The debug-information build has its own binary identity and is not
used for the comparison timing results.

Each capture made 32 acknowledged enable/disable transitions around analytic
strategy calls. Both driver processes exited successfully with all analytic
checks passing. The user-space Arch `perf` 7.2.3-1 package captured `cycles:u`
with call graphs at a requested 4,999 Hz; effective frequency is not reported.
Reach-back produced 936 decoded samples over 212.278 ms. Direct-joint produced
175 samples over 63.592 ms. Both reports show zero lost samples. The sampling
window includes FIFO enable/acknowledgement overhead.

Source symbols and line tables resolve in the report. Reach-back samples are
spread across allocation/free paths and HiGHS setup/cleanup symbols; its largest
individual HiGHS entries are below 0.5%. Direct-joint's largest individual
entries are the HiGHS `Basis` constructor (1.46%) and `HEkk` destructor (1.16%),
with other setup/cleanup entries below 1%. A source annotation of `HEkk::solve`
contained only four samples. These captures do not establish one unique limiter
or a dominant source line. The accepted conclusion remains inconclusive for
this small fixture.

Raw profiles, bounded-probe metadata/logs, and `perf report --source` output
are retained per strategy. No speed, overhead, or winner claim follows from
these profiles. They only improve source attribution over the earlier
non-debug-symbol captures.
