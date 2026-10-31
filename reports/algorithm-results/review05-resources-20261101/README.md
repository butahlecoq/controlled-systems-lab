# REVIEW-05 resource-receipt follow-up

This bundle repeats the fixed scalar constraint-row ladder with a POSIX
`fork`/`exec`/`wait4` wrapper around every isolated strategy process. It retains
the exact same three fixtures, alternating schedule and independent checker as
the constraint-row report, while recording user CPU, system CPU, total child
CPU and peak RSS for every attempt.

All 42 attempts passed the exact checker, including six measured pairs at each
of 2, 4 and 8 authored state rows per stage. `strategy_run_ns` remains the
solver-only timing; process receipts cover the whole child and are reported
separately. These are descriptive single-host observations. They do not prove
a speedup, memory scaling law, internal phase attribution, or source-level
limiter.
