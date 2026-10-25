# Bounded source profile summary

The profile driver used the same executable SHA-256 as the five paired captures:
`9c8fdf63b91ab0c48c6e9650051f9b56753e231dd33ba03e906d444ee8af15f2`. Its
embedded build manifest binds that binary to clean source commit
`76d8ae64b8ec7d36c975eae64f7581bf345cf387`. The profile wrapper recorded
worktree commit `9f7a07e62272c38aa1f0d062a609f756c121b795`; between those commits,
the benchmark driver and profile wrapper did not change.

The system did not have `perf` installed. I downloaded the Arch `perf` 7.2.3-1
package and its missing libraries into `/tmp`, verified the package signatures
with the local pacman keyring, and ran the probe with those extracted files. No
system packages were installed. Host kernel was `7.2.5-3-omarchy`,
`perf_event_paranoid=2`, with 8 logical CPUs; load before profiling was
`0.96, 1.18, 1.63`.

Each strategy profile requested 32 calls at 4,999 Hz, returned 32 passed calls
and 64 acknowledged control transitions, and stayed within the 32 MiB and
120-second bounds. `perf report` decoded 933 reach-back samples from 106,076
bytes and 180 direct-joint samples from 30,220 bytes. Both reports counted zero
lost samples. The effective sampling frequency is not reported by the probe.
The exact capability metadata, raw `perf.data`, stderr, and symbol reports are
retained in the adjacent `limiter-profile-userspace-perf-32-*` directories.

The largest self-sample symbols were `malloc`/`cfree` (reach-back: 7.02%/7.12%;
direct-joint: 10.13%/5.91%). Stacks also include C++ string construction,
HiGHS option/info record construction, and HiGHS setup/solve methods. This
points to allocation-heavy string and backend setup work as candidates for
further study. The direct-joint profile has only 180 samples, the T-S01 case is
small, and the capture window includes FIFO acknowledgement work. These samples
do not establish one unique limiter or a general performance conclusion.
