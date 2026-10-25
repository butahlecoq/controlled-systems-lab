# Rejected local limiter-profile attempt

The paired comparison capture is preserved in `linux-omarchy-gcc16-20261025.json` and `.jsonl`. A separate eight-call acknowledged perf attempt was made with the repository's bounded driver and the unpacked Arch `perf` 7.2.3-1 executable.

The profile produced six `cycles:u` samples, but the driver rejected the capture after receiving an unexpected control-FIFO acknowledgement. The driver exited nonzero, only part of the requested eight calls ran, and the sample region is incomplete. The profile is not used to identify a limiter or interpret the timing deltas. Its machine-readable result, driver output, perf output, and incomplete `perf.data` are retained in `linux-omarchy-gcc16-20261025.profile-attempt/` for diagnosis.

A valid source-mapped limiter profile remains outstanding. The comparison itself remains fixture-specific and inconclusive.
