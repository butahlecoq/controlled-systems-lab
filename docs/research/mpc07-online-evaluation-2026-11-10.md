# MPC07 actual stored-feedback evaluation — 2026-11-10

The #603 latency completion audit now has an actual causal feedback-evaluation
capture, separate from the original batch LP policy synthesis. It evaluates the
existing verified rational policies through a binary64 controller API on the
same authored2D physical models. It does not optimize/replan an MPC problem.

The strict upstream218 checks select measured repetition0 from24 fixed-unit
profiles and12 joint-unit profiles. Actions depend only on observed full states
and stored past control/observations. After observing x_t, the controller
reconstructs the previous transition residual eta or normalized two-state zeta;
only then does it evaluate v+M*past_eta or H*past_zeta. The plant applies the
current uncertainty after action returns. Delta stays constant+epsilon in both
trace families (0 additive,1/64 uncertain-A); w is all+1 or alternates signs.
The API never receives delta or w.

Capture source `0524f7e4a2babefab50fd9a724cedda782f2c46f` was clean and committed
before measurement. All36profiles/two traces have one excluded warmup plus five
measured repetitions, with reversed ordering on alternate rounds:432episodes
and2016stages per arm including warmups;360episodes/1680stages enter the measured
statistics. A separate cProfile arm repeats the same work and is wholly excluded.
Both arms complete with zero failures and pass independent rational policy,
causality, source, original bound and physical-transition replay. Maximum actual
action/state difference is1.7763568394002505e-15 under atol=rtol=1e-10. Exact
rational policy certificates are distinct from binary64 execution consistency.

The primary diagnostic example is the N8joint/positive trace:40instrumented
queries have median4749ns and range1816–6146ns. The empty timestamp-pair median
is2375ns (min1467,max31428), so intrinsic method latency is not independently
resolved. No timer overhead is subtracted. The five preparation spans have
median353889ns and range349908–370721ns. This generic dense Python evaluator
uses the same coefficient loops including zeros; it is not sparsity-tuned.
These initial configured spans imply no winner, real-time guarantee or speedup.

Preparation (rational-to-binary64 policy construction), initial observation,
past-residual update, query, episode and direct-worker CPU/RSS/wall have separate
scopes. The worker includes startup/JSON I/O and supervised polling; its observed
197652189ns wall,0.153347s user/0.039830s system CPU and20760KiB peak RSS are not
query latency. Admission is30CPU seconds/60wall seconds/2GiB address space. The
separate high-overhead profiler confirms432preparations and2016actual queries/
observations and highlights rational parsing/conversion in preparation; it is
not a native limiter/tuning study. Source/input/interpreter hashes, clock/load,
commands, outcomes and raw process streams remain in the immutable capture.

Evidence is `benchmarks/reporting/mpc07/evidence/online-evaluation-0524f7e4`.
Its original raw ZIP SHA256 is
`c4b2ecbacc936cdbf4761119d5fef1272b305013de6494724cd389fe6ec269f2`.
Current checking source `5de8910f119d645e5c6bbd0eb678e70e0988f4fe` separately
adds complete source/receipt authentication and explicit POSIX capture refusal;
it does not relabel the historical capture as remeasured. The figure renderer
reruns the independent saved check before consuming the receipt. All original
fixed/joint captures, corrected sidecars and this new raw capture stay unchanged.

The saved N8positive-trace figure shows the four joint-unit policy classes in
2D phase coordinates, stage/state and held-control traces. Initial/terminal
markers and q=0 as a zero terminal-cost reference are explicit. It shows neither
a full reachable set nor a new global/worst-path/continuous-safety proof.

Nine tests pass with actual Python3.14.8 (2.760s) and3.11.14 (3.101s), including
source-map/source/action forgery after checksum renewal, empty checker maps,
noncausal API use, delayed normalization, all72policy/trace combinations, partial
failure preservation and unsupported-POSIX refusal. Capture is Linux/POSIX only;
source/rational checking requires a byte-preserving source checkout/Git objects
and the unchanged upstream evidence. Existing optional Matplotlib3.11.2/shared
style renders figures. No dependency installation, solver/native run/build,
core/public API change or standalone library release is introduced.

LP-solve and MPC-reoptimization latency remain unmeasured; this added result is
actual evaluation of already synthesized causal feedback. Independent review,
root-owned shared producer/publication integration, current CI and live route/
download/example verification remain pending. Keep #603 open until completion
is proven; this source/evidence unit is not a deployment or completion claim.
