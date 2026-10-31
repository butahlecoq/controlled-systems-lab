# Resource follow-up diagnostics

This capture uses POSIX `wait4` receipts because the host has no `perf`,
`/usr/bin/time`, or `psutil`. The receipt records are therefore the
authoritative per-process CPU and peak-RSS evidence for this bundle. They do
not provide source-mapped phase attribution.
