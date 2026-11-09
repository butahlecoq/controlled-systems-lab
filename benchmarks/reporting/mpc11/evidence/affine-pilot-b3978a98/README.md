# MPC-11 actual CSL affine correctness pilots

Capture source: `b3978a98a8bfb30e21841466244ed7f78e987886`, clean worktree.
The public consumer uses `CSL::highs_convex` version `1.0.0+highs.1.11.0`
through `make_convex_program` and the registered `ConvexPort`. The archived
build receipt identifies the Release compiler, executable and source hashes.
No Python optimizer supplies the accepted plans. No core API or backend option
changed.

| Case | Authored objective | Running-cost contribution | Witness check |
| --- | ---: | ---: | --- |
| Tiny analytic joint QP | 2 | Included analytically | x0=0, x1=u=1 |
| SYN-NL-FUEL-01 | 0.010570464036763268 | 0.0016000000000000005 | Numerical affine replay/cost/bounds pass |
| SYN-NL-LV-01 | 0.0782955745731609 | 0.016032051380787938 | Numerical affine replay/cost/bounds pass |

The full joint LV and fuel captures use a positive uniform objective
multiplier of 1000. All quadratic, linear and constant coefficients receive
the same factor; every dynamics row and variable bound remains unchanged.
The positive-scalar minimizer identity is a real-arithmetic statement. Stored
binary64 cost coefficients are rounded, so this bundle checks numerical
cost/replay consistency rather than certifying identical stored-QP argmin
families. Its raw objective-map text denotes the intended mathematical map.
Native objectives divide by 1000 to recover the authored dimensionless cost.
`accepted/` retains both scaled and unscaled programs with their content hashes,
full physical/scaled model coefficients, controls/states, raw native outcomes,
original-cost recomputation and affine-replay checks. The native optimal
outcome has unestablished evidence support; these numerical witness checks do
not certify a complete optimizer family, real-arithmetic optimality, nonlinear
feasibility or nonlinear control performance.

`unscaled-joint/`, `controls-first/`, and `equality-eliminated/` preserve all
nine prior attempts, including the three LV native resource-limit outcomes.
Each retains its source revision, complete inputs and raw output. Their limited
candidate primals are not promoted to optimal plans. Each bridge attempt used
single-process 300-second CPU/wall and 8 GiB address-space caps, plus a native
290-second cooperative deadline. These correctness pilots are not repeated
performance evidence. The observed native active-set cycling and successful
conditioning demonstrate sensitivity of this particular numerical profile;
no general performance/scalability conclusion follows.

`diagnostics/` contains scratch native cold/scaled probes and exact dyadic
interval proofs for removing redundant rows. Its README distinguishes these
unqualified diagnosis files from accepted run records, including copied hash
fields that are not valid identities after a scratch mutation. The archive's
per-file checksums bind their actual bytes. These diagnostic native-only probes
do not replace the actual CSL producer used in `accepted/`.

Extract `capture.zip` into an empty directory. Verify its inner SHA256SUMS,
then run from a source checkout with the optional locked environment:

```sh
OPENBLAS_NUM_THREADS=1 "$MPC11_VENV/bin/python" \
  benchmarks/reporting/mpc11/check_affine_saved.py --bundle <EXTRACTED>/accepted
```

All three accepted witnesses pass this saved-record check without running a
solver. The archive's outer hash is stored in `SHA256SUMS` and `summary.json`.
There is no Pages deployment or nonlinear/NMPC claim in this evidence slice.
Nonlinear execution, independent nonlinear replay, receding-horizon control,
comparison figures and publication remain #607 work.

The additive saved checker at `118d2d6ae0239a0554b2a6c9b41e195c78f75fc6` rebuilds both authored
models and joint programs, then re-applies declared transforms and compares all
coefficients, bounds, rows, reconstruction maps and retained source programs.
An updated self-hash cannot substitute for this relationship check. The
original capture source and archive bytes remain unchanged; this revision
adds verification and does not rerun optimization. Exact serialized rebuilding
uses the locked numerical environment and fails closed when a different
implementation produces different binary64 coefficients.
