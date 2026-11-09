# Alternating NI1 workload timing

The bounded source/report consumer uses the existing Linux optional MPC-11
lock and existing Release native bridges. It records one separate warmup and
five measured repetitions, with arm order A/B, B/A, A/B, B/A, A/B. A is the
full-joint affine QP with positive uniform objective multiplier 1000, followed
by nonlinear execution and replay. B is nominal shrinking-horizon NI1 NMPC,
including every held CVODES execution and independent CSL RK4 replay. These
are different model/policy classes, so their clocks are not solver parity.

```sh
python benchmarks/reporting/mpc11/run_timing.py \
  --affine-bridge <EXISTING_AFFINE_BINARY> \
  --replay-bridge <EXISTING_REPLAY_BINARY> --output <CAPTURE_DIRECTORY>
python benchmarks/reporting/mpc11/check_timing.py \
  --bundle <CAPTURE_DIRECTORY> --output <NEW_SUMMARY_JSON>
```

Completed units are reused only after their full byte inventory and command
identity match. Failed completed units remain failures. Interrupted attempts
are preserved, and a new attempt directory is used on resume. An exclusive
file lock prevents concurrent capture writers. A source/configuration/binary
change rejects resume. Use the recorded source revision to resume a frozen
capture; later checker revisions are separate reading tools. POSIX wait4,
fcntl and resource limits make this optional capture command POSIX-specific;
no Windows timing qualification is claimed.

The environment receipt binds NI1 scenario bytes, numerical generators, source
files, provider implementation, dependency lock and actual bridge binaries.
The checker validates each associated QP/NLP and replay before extracting
clocks, binds every consumed capture file, and can validate copied source
snapshots against both the capture hashes and the recorded Git commit using
`--source-snapshot <DIRECTORY>`. The current reader hash is separate from the
original captured checker snapshot. No measurement output is rewritten by a
check. Fresh checker durations are excluded from repeated algorithm aggregates.

Native setup/optimization and Python configuration construction have different
spans. NMPC setup/optimization are sums over all 30 LV or 40 fuel updates;
held execution is the sum of CVODES hold calls. Affine CVODES integration
includes construction of its integrator; NMPC's held-call sum excludes its
once-per-case integrator construction, which remains in the process envelope.
Independent integration clocks and whole process clocks are both retained.
Never add nested spans or label startup/checker/serialization time as solver
time. The outer wait4 receipt reports CPU including reaped descendants and
the largest process RSS high-water mark, not simultaneous process-tree memory.

Saved evidence is in
[`evidence/timing-five-68515dcb`](evidence/timing-five-68515dcb/README.md).
It retains all warmup/measured raw output, any failures, checks, host load,
resource receipts and a separate instrumented fuel profile. The profile is
excluded from timing samples. A Python call-boundary profile cannot establish
a native HiGHS/IPOPT limiter. The comparative performance verdict remains
inconclusive; descriptive medians/ranges are initial observations for this
configured host workload. No core API, required dependency, install artifact,
publication workflow or library release changes. This unit does not deploy
results or close issue #607.
