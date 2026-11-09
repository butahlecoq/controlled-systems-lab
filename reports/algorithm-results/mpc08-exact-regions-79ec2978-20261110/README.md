# MPC08 exact region/predecessor first capture

This partial #604 evidence unit separates full rational fixture proofs from numerical CSL observations. Extract `capture.zip` into a new directory, then run from a repository checkout containing source commit `79ec2978bb18a77abf5817b6f940aa3a89b0e488`:

```sh
python -B benchmarks/reporting/mpc08_explicit/recheck_exact_regions.py /path/to/extracted-capture
```

The checker never launches a numerical algorithm or rewrites the capture. It checks the complete inner inventory, recorded committed source hashes, build/client binding, exact region and geometry proofs, actual CSV inputs, every raw observation and regenerated summaries. Open extracted `index.html` for the labelled two-panel figure. ZIP has 17 flat members, including its own inventory. No Pages publication is claimed.

## Results and limits

Nine N=1 double-integrator regions cover the complete feasible initial-state polygon (area 21/2); 22 shared boundaries have equal action/value. Independent rational H-row intersection checks prove coverage, KKT and value identities. The terminal-only objective, initial X, U, terminal T and horizon are explicit in the reference. The N=2 terminal-velocity full optimizer fiber is distinct from its minimum-norm selector. At v0=0, horizons 1/2/4/8/12/16 have 1/2/6/70/924/12870 exact vertices; N=16 enumeration is refused by the 1000-vertex cap. This is optimizer-fiber vertex growth, not exponential critical-region growth.

Seven whole-set inclusions compare nominal exists-u and robust exists-u/forall-w predecessors with inner/outer target boxes. The original terminal T is nominally invariant; a smaller T_robust is invariant under K=(-1,-2) for every w in [-1/8,1/8]. A concrete counterexample shows original T is not robust under that policy. Boxes receive containment directions, not invariance claims. These are initial-state parameter sets, not a general winning-set or forward-reachable-set equality.

The native capture contains 360 observations: 120 public ConvexPort QP witnesses independently replayed against the exact reference, 120 Strategy B candidate-containing observations, and Strategy A 90 completed plus 30 noncompleted candidate-containing observations. Those candidates never establish complete-family equality. An additional 432 public LPPort observations check 72 set/direction supports against exact H/V optima. Each query has one excluded warmup and five retained repetitions. Requested threads are one; actual support backend widths are saved, while QP/strategy widths were not collected.

All actual setup/run intervals, failures, resource receipts and hardware are retained. Performance remains inconclusive: the native client was freshly compiled and its source/binary/libraries are hash-bound, but static libraries were reused from the recorded prior build. The five measured repetitions are descriptive initial numbers, not a speedup ranking. `load_after` records the end of the strategy/QP portion, before the separate LP process. Memory is process peak RSS; it is not isolated region storage.

## Remaining issue scope

This unit does not deliver a general parametric engine, critical-region scaling across horizons, exact original-quadratic registered complete-family equality, MPT3 execution, or full #604 closure. Ordinary LQR with running costs remains a separate variant. No public API, mandatory dependency or release is added. The optional report uses the existing Matplotlib environment and shared axis style. Independent review, CI and a later qualified publication are required before closure.

## Primary-source grounding

The [2002 author-hosted mpQP paper](https://cse.lab.imtlucca.it/~bemporad/publications/papers/automatica-mpqp.pdf) uses a positive-definite problem for its unique affine optimizer result; that does not establish uniqueness for the singular multistep terminal-only variant. Its [2003 corrigendum](https://cse.lab.imtlucca.it/~bemporad/publications/papers/automatica-mpqp-corrige.pdf) changes Example 7.1's terminal matrix; this synthetic fixture is not that example. Official [MPT3 license](https://www.mpt3.org/pmwiki.php/Main/License) and [installation](https://www.mpt3.org/pmwiki.php/Main/Installation) pages describe GPL and MATLAB/toolbox prerequisites. Neither MATLAB nor MPT was installed or executed.
