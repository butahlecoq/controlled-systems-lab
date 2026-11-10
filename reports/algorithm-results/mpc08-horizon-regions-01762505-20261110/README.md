# Matched original-quadratic MPC08 horizon cells

This is the second bounded #604 unit, stacked on the separately reviewed N=1/predecessor evidence. It preserves the original double-integrator A=[[1,1],[0,1]], B=(0,1), U=[-1,1], initial X=[-3,3]×[-2,2], terminal T={|p+v|≤1, |p+2v|≤1} and cost ||xN||², with no running cost. Intermediate states are explicitly unconstrained; X bounds initial parameters. N=2/4/8 use the same fixture.

## Exact whole-domain product

The endpoint map is z=(p+Nv,v)+D_Nu, with column j of D_N equal to (N-1-j,1). Its exact reachable control image is a rank-two zonotope. Perpendicular normals (1,-k) for k=0,...,N-1 and their opposites give all its facets; each bound is the exact sum of generator absolute supports. The independent feasible parameter polygon is built from a convex hull of all box-corner endpoint images, Minkowski-added to T and mapped back by A^-N, then clipped to X.

Zero-, one-face and independent two-face KKT candidates produce affine optimal endpoint maps and closed parameter H-polygons. The checker separately enumerates rational H intersections, rejects recession directions, requires the canonical bounded X rows, proves whole-cell feasibility/active equalities/nonnegative multipliers/stationarity, checks boundary agreement, and proves full-domain coverage by exact area with disjoint interiors. Feasible areas are 47/3, 23 and 24. Cell counts are 9, 7 and 1: this fixture does not exhibit critical-region explosion. These are delivered endpoint-map cells; no globally minimal/maximal partition count is asserted.

Strict convexity in endpoint z makes z*(p,v) unique, even though the control Hessian is singular for N>2. The COMPLETE original optimizer family is the H-relation

```
-1 <= uj <= 1, j=0,...,N-1
D_N u = z*(p,v) - (p+Nv,v).
```

Every original optimum has that endpoint; every control in this nonempty slice has the optimal original value. All intermediate states follow uniquely from the dynamics. This proof describes the whole fiber, not a selected trajectory, and grants no new CSL quadratic-verifier capability. N=16 is outside the explicit corner-enumeration profile, refused by the producer rather than silently extending the cap.

## Actual initial numbers

| N | Endpoint cells | Stored H rows | Polygon edges | Serialized reference bytes | Construction ns (one descriptive run) |
|---|---|---|---|---|---|
| 2 | 9 | 120 | 34 | 3881 | 25417848 |
| 4 | 7 | 122 | 28 | 3680 | 67449621 |
| 8 | 1 | 24 | 4 | 1119 | 185848292 |

The raw reference also records independent-check intervals and six actual location/endpoint-evaluation batches per horizon (first excluded warmup, five repetitions), with exact batch work counts. Serialized bytes are storage, not peak Python working memory. Native process wait4 peak RSS is recorded separately. No tuning/native profile, isolated-library rebuild or timing ranking is claimed; performance is inconclusive.

## Actual public CSL boundary

The existing public Strategy B exact-H route supports finite linear terminal objectives. All 36 original-quadratic exact-family requests were explicitly refused at preparation. A separately labelled reduction fixes the optimal endpoint to zero and uses a zero linear objective. At the six dyadic parameters (p,v)=(0,0),(1,0) for each horizon, this reduction is equivalent to the original optimum by the exact whole-domain proof above. It is NOT a generic quadratic verifier.

There are 72 raw requests including one warmup and five measured repetitions for every query/request type. At N=2 all 12 reduced requests returned registry-verified complete families; the saved checker compares every native H-row/equality with the full expected initial/dynamics/input/terminal relation, including row sign/scale normalization. At N=4 and N=8, all 12 reduced requests per horizon hit `resource_limit`: “Nominal exact-H optimum-face construction exhausted its row or arithmetic budget.” Those outcomes remain inconclusive; widths 14 and 26 being below 32 does not guarantee the row/operation budgets will suffice. No candidates or failed requests are promoted to complete families.

The driver is freshly compiled from hash-bound client bytes. Static CSL/HiGHS libraries are reused from the explicitly recorded prior Release build, with individual hashes. No current clean full-library rebuild or binary redistribution is claimed. No new public API, installed dependency or library release is introduced; plotting uses the existing optional Matplotlib3.11.2 environment and shared numeric-axis style. Native process limits are 300s wall/CPU and 8GiB address space, one sequential worker/requested solver thread; no aggregate cgroup cap or actual width observation is claimed here.

## Recheck and figure

Extract `capture.zip` to a fresh directory. From a checkout containing the capture commit and current saved checker:

```sh
python -B benchmarks/reporting/mpc08_explicit/capture_horizon_regions.py --recheck /path/to/extracted
```

This checks saved data only: no native optimization or integration is launched. Complete inner inventory, mandatory committed source hashes, client/binary receipt, literal query inventory, exact proofs, numerical request classifications, complete native H-fiber equality, costs/work counts and summaries are rechecked. Source is capture commit 017625057d253ae191405ca163bbda85729af3aa; later e5010d6c adds stored cost/process coherence checks without modifying this capture. Open `horizon-regions.svg` or PNG for the three matched 2D parameter partitions. The archive is flat and contains its inner SHA256SUMS.

Full #604 remains open for independent review, CI, qualified publication and literal acceptance reconciliation. General parametric engines, ordinary LQR running costs, MPT3/PPOPT execution, broad original-quadratic registered families and universal set-approximation comparisons are not inferred from this bounded unit.
