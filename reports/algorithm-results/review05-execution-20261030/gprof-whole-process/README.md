# REVIEW-05 whole-process gprof capture

Captured 2026-10-30 from tracked source revision `210bbe39377be3131f537d65d4f0857c6b4c3462`. The profile binary is a separate GCC 16.2.1 Release build with `-pg` compile and link flags; its SHA-256 is recorded in `../environment.json`. The ordinary paired comparison was run earlier from the clean same revision with the uninstrumented Release binary. Its immutable record remains `../obs04-current-main-comparison.json`.

`perf` is not installed on this host. The driver now permits repeated checked strategy calls without perf FIFOs and labels that mode `whole_process`, `perf_controlled: false`, and zero acknowledged perf commands. The raw gprof data therefore includes process startup, a warmup, workspace creation, requested strategy calls, analytic result checks and shutdown. It does not isolate `StrategyPort::run`.

Each requested call passed the analytic T-S01 family checks:

| Strategy | Checked calls | gprof sample time | Resolution |
| --- | ---: | ---: | ---: |
| Reach-back | 500 | 0.48 s | 0.01 s/sample |
| Strategy B (direct-joint) | 2,000 | 0.38 s | 0.01 s/sample |

The profiles attribute much of the sampled work to HiGHS option/model lifecycle and simplex/solver code; reach-back also shows `csl::numeric::snapshot` and forward-child bookkeeping. The totals are only 48 and 38 samples, and gprof instrumentation changes runtime. Treat the function rankings as exploratory. They do not establish a unique bottleneck, a speed comparison, or a general limiter. The paired ordinary run is the only timing evidence here; it covers one tiny two-stage scalar fixture and does not form a scaling curve.

Files:

- `reach-back.gmon.615549`, `direct-joint.gmon.615552`: raw process profiles.
- `reach-back.gprof.txt`, `direct-joint.gprof.txt`: gprof flat and call-graph reports.
- `reach-back-profile.stdout.json`, `direct-joint-profile.stdout.json`: verified call counts and explicit profile scope.
- `reach-back-profile.stderr.txt`, `direct-joint-profile.stderr.txt`: stderr captures.
