# MPC07 actual causal policy evaluation

Capture source0524f7e4 is separate from current checking source5de8910f.
All original fixed/joint archives and corrected sidecars remain byte-unchanged.
The existing strict218 checks selected24 fixed-unit and12 joint-unit measured
repetition0 policies. Constant physical delta=+epsilon is used in BOTH traces,
with epsilon0 additive or1/64 uncertain-A; only w is positive/alternating.
Current/future delta/w never enter the controller API. Actual returned controls
are consumed by the original 2D physical plant after the action returns.

One warmup plus five measured repetitions per36profiles/two traces derive432
episodes/2016stages in the measured arm, including72warmup episodes/336stages.
All360measured episodes/1680stages complete; there are zero failures. The separate
instrumented profile arm repeats432episodes/2016stages and is wholly excluded
from latency statistics. Independent source/rational-policy/physical/bound replay
checks both arms (864episodes), with maximum action/state error1.7763568394002505e-15
under recorded atol=rtol=1e-10. This is not an exact-binary64 or new robustness proof.

The clock-pair median is2375ns (min1467,max31428). For the N8joint policy on the
positive trace, the instrumented query median is4749ns, range1816–6146ns across
40queries; the five policy-preparation spans have median353889ns, range349908–370721ns.
Per-stage work varies, including the initial zero action. This is a generic dense
Python evaluator, not a sparsity-tuned kernel. Timer overhead is substantial;
intrinsic query time is not independently resolved and no overhead is subtracted.
Do not compare the small policy differences or infer a winner/hard-real-time bound.
Query/update costs are actual stored-feedback execution, not LP synthesis or MPC
reoptimization latency. Initial observation, observed past-residual reconstruction,
query, rational-to-binary64 policy preparation, whole episodes and worker clocks
remain separate in verification.json. All sums use recorded integer nanoseconds.

The measured worker is197652189ns supervised wall,0.153347s user/0.039830s system
CPU and20760KiB direct-worker peak RSS. Its supervised wall includes Python startup,
JSON I/O and polling. POSIX admission is30CPU seconds/60wall seconds/2GiB address
space. Environment/interpreter SHA, clock resolution/overhead and load are retained.
The separate cProfile shows432preparations and2016actual queries/observations;
rational parsing/conversion dominates preparation. Profiling itself is heavily
instrumented (profile worker about2seconds) and establishes no native/tuning ranking.

The N8figure uses the actual positive physical trace for four joint-unit classes.
Circles mark initial state, crosses terminal state. The q=0 line is a zero terminal
q-squared cost reference, not a claim that a selected path attains zero. Complete
raw actions/states/time-stage arrays, hashes and physical bounds are linked in
figure-data.json. No reachable-set, global or newly certified worst-path claim.

Verify outer SHA256SUMS, extract capture.zip into scratch and verify its inner
SHA256SUMS. From a source checkout containing the capture/checking commits and
unchanged four upstream evidence folders, run the current standard-library reader:

```sh
python3 -B -m benchmarks.reporting.mpc07.online.check \
  --capture SCRATCH/capture --output NEW_VERIFICATION.json
```

checking-source.zip preserves the current complete helper text/hashes, rather than
substituting a cached receipt for source validation. Git objects remain required.
Rendering uses the existing optional Matplotlib3.11.2/shared quantitative style;
no solver/native binary, dependency installation, API or library release is added.
This is local source/evidence delivery. Independent reviews, managed publication,
actual deployed hashes/examples and completion audit remain pending. Keep #603 open.
