# Causal policy evaluation: bounded initial measurements

Expected claim: configured Python binary64 feedback query/update/preparation
costs for existing exactly checked policies on the authored two-state model.
This is evaluation of a stored causal policy, never a fresh LP solve or MPC
reoptimization. No timing winner, tuning result, hard-real-time bound or online
MPC replanning capability is inferred. Native online costs remain unmeasured.

The selected measured-repetition0 source policies are in profiles.json, with
original record/sidecar and all four reviewed evidence inventory digests. Inputs
are prepared by the existing218 exact/source/process checks. Capture policy
preparation converts rational coefficients to binary64 tuples. observe(state)
reconstructs the previous residual using previous state and past control;
action() has no current/future uncertainty argument. Only after action() returns
does the plant apply w=+1 or alternating +/-1. Delta is constant +epsilon in BOTH
families:0 for additive profiles,1/64 for the uncertain-A profiles. It is never
passed to the controller. All observations/actions drive the saved state trace.

One warmup plus five measured episodes per profile/family use the same work,
with reversed profile/family order on alternate rounds. For all currently
available36 profiles this derives432 episodes/2016 stages per capture arm,
including warmups; measured denominators are360 episodes/1680 stages. The
separate instrumented profile arm is entirely excluded from latency summaries.
Preparation, residual reconstruction, action query and whole episode clocks
are integer nanoseconds. Initial observation and actual past-residual updates
have distinct statistics. Worker startup/JSON serialization and supervised wall
polling are outside query latency and visible in direct-worker CPU/RSS/process
receipts. Clock resolution/empty-pair costs are recorded; no overhead subtraction.
The checker independently reconstructs rational policy/physical transitions and
original robust bounds. Binary64 outputs are compared with atol=rtol=1e-10,
without calling binary64 exact or deriving robustness from two traces.

The source/input commit must be clean before measurement. Each worker has
30 CPU seconds,60 supervised wall seconds and2GiB address-space admission.
Actual source/input/interpreter identities, load, commands, outputs, errors,
process statuses and cProfile diagnostics are retained. Profiling is a separate
instrumented run, not evidence for a cross-policy timing winner.

```sh
python3 -B -m benchmarks.reporting.mpc07.online.capture --output NEW_CAPTURE
python3 -B -m benchmarks.reporting.mpc07.online.check \
  --capture NEW_CAPTURE --output NEW_VERIFICATION.json
<PINNED_PLOT_PYTHON> -B -m benchmarks.reporting.mpc07.online.figures \
  --capture NEW_CAPTURE --verification NEW_VERIFICATION.json --output NEW_FIGURES
```

Checking uses Python standard library and original source Git objects, with the
unchanged upstream archives available. Rendering additionally uses existing
Matplotlib3.11.2/shared figure style. No native executable, dependency install,
core/public API or library release is introduced. Failures remain in denominators;
only independently checked completed episodes contribute evaluation latencies.
All old archives/sidecars remain unchanged; independent review and managed live
publication remain separate. Keep #603 open until completion is established.

The captured empty timer-pair span is a resolution/overhead diagnostic, not a
quantity subtracted from query timings. When it is a substantial share of the
query span, intrinsic query latency is not independently resolved. Report the
raw instrumented spans and clock floor together; no policy ranking follows.
The renderer reruns the independent saved rational/source check and authenticates
the complete current checking-source map against its separate Git revision before
using a receipt. Historical capture source and current checking source remain
distinct; current checking does not rewrite measured records.
