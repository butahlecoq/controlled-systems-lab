# Equality/nonnegative phase-I kernel

`<csl/optimization/phase_one.hpp>` and `CSL::phase_one` provide the independent
`phase-one-bland` registration, version `1`, on the existing `registry::LPPort`.
The module uses source revision 1.5 without changing its canonical types.
[Linear program publication, attempts and evidence](linear-programs.md) remain
authoritative. [Research lineage](../research/phase-one-lineage.md) distinguishes
the mathematical sources and saved implementation variants.

## Supported mathematics and replacement

`phase_one::make_program(identity, A, b)` constructs the canonical immutable
`LinearProgram` for `A*x=b`, `x>=0`, with objective and offset exactly zero.
It checks RHS length and delegates CSR, finite data, identity, interval and
ownership checks to `make_linear_program`. Input is borrowed only during the
synchronous call; the resulting program owns independent snapshots. Callers
must assign a new program identity when the mathematics changes. The helper
does not append an affine row, exclude a queried point, remove duplicate columns
or solve the system.

`make_registration(options)` returns a registration or diagnostics. Prepare it
through the registry with representation `csl.program-result.v1`, numerical
assurance and binary64 scalar. It admits only zero objectives/offsets, equality
rows and exactly `[0,+infinity)` variable bounds. Legal other LPs are explicitly
unsupported before factory invocation. The ordinary witness consumer can select
this adapter or the registered reference LP on the same immutable request.
Consumers needing basis data must request `basis_diagnostics=true`; unsupported
reference diagnostics are an explicit rejection, never a fabricated basis.

Empty dimensions, zero or duplicate rows, dependent structural columns,
contradictory equalities and unbounded feasible cones are valid inputs. A feasible
constant-zero program reports numerical optimality, including a homogeneous
cone; it does not report objective unboundedness or enumerate a solution family.
The module supplies no hull reducer, bulk/grouped classification, warm start,
control recovery, general nonconstant-objective optimizer or certificate verifier.

## Auxiliary problem and deterministic pivots

For each row set `s_i=-1` if `b_i<0`, otherwise `+1`, including signed zero.
With `D=diag(s)`, form `N=D*A`, `q=abs(b)`. Solve the auxiliary problem

```
minimize w = sum(a)
N*x + a = q,    x >= 0, a >= 0.
```

The fresh initial basis is the artificial identity, with `x=0`, `a=q`. No
structural-rank assumption, row deletion, epsilon perturbation or regularization
is used. Structural variables precede artificial variables in their original
index order. Artificial variables may reenter. For a current ordered basis B,
compute basic coefficients `z=B^-1*q`, dual vector `B^T*y=c_B`, and reduced
costs `c_j-C_j^T*y`. The implementation uses private pinned Eigen 3.4 FullPivLU
factorization/solves, not an explicit inverse.

Choose the least-index eligible entering variable. Among all strictly positive
directions choose the minimum computed ratio; an exactly equal computed ratio
is resolved by least **basic variable index**, not row position. A zero step is
a degenerate pivot and counts toward the same finite cap. This is Bland's
ordering in exact arithmetic. The exact-arithmetic finiteness theorem does not
establish convergence of floating tolerance decisions. Binary64 execution uses
the guards below and an unconditional finite committed-pivot cap.

A tentative basis is factored, solved and its candidate freshly checked before
commit. Failed tentative work increments the factorization count but creates no
pivot event. The previous finite candidate is retained; a failed basis or basic
point check makes current basis coordinates unavailable. A successful commit
advances the basis iteration once and records the actual before/after auxiliary
values, signed entering coefficient, step, leaving slot and tagged identities.

## Floating guards and evidence

Numerical policy tolerances `a` and `r` must be finite and nonnegative. All
products, sums, scales and thresholds used for decisions must be finite.
The pivot guard is `eta=max(pivot_relative_tolerance,64*epsilon*max(1,m))`;
`eta>=1` fails. Nontrivial bases require full numerical rank and reciprocal
condition estimate greater than eta. Fresh residuals check `B*z=q`, `B^T*y=c_B`
and `B*d=C_j` against `a+r*scale`.

Small negative basic values within the numerical threshold may be clipped only
when forming the candidate and ratios; their actual violation is retained in
auxiliary nonnegativity diagnostics. Larger violations fail. Fresh auxiliary
rows and original CSR rows are checked componentwise, with row scale
`max(1,abs(activity),abs(rhs))`. Original canonical primal residuals are also
recomputed by `evaluate_primal`; a large unrelated row cannot hide a failed
small row through aggregate scaling.

Pricing uses threshold `a+r*max(1,abs(cost),sum(abs(column_i*y_i)))`. Eligibility
requires a reduced cost below the negative threshold. If no variable is eligible
but any computed nonbasic reduced cost is negative, the result is
`uncertain_pricing`, not infeasible. Every strictly positive direction must
exceed `eta*max(1,norm_inf(direction))`; a smaller positive direction produces
`uncertain_pivot` instead of silently ignoring a potentially binding row.

If auxiliary value is at most `a+r*max(1,sum(abs(b)))` **and** the original
candidate passes all checks, the result is completed/optimal. A positive
auxiliary value with checked basis/dual data and all computed nonbasic reduced
costs nonnegative reports completed/infeasible. Both reports carry
`Unestablished` support. There are no objective bounds, validated certificates,
hull-vertex claims or complete-family claims. The original objective remains
zero and is distinct from the auxiliary objective.

Cancellation, deadline/cap/budget exhaustion, arithmetic overflow, uncertain
pricing/pivots and failed numerical basis checks report undetermined. Retained
primal coefficients are candidates with their original residuals, including
possibly infeasible partial candidates. For example `A=[1e-300], b=[1]` has an
exact finite feasible solution, but default pricing reports uncertainty. The
triangle RHS `[0.5,-1e-12,1]` is numerically feasible at absolute tolerance 1e-8
and has positive auxiliary optimum at 1e-14; neither report establishes exact
membership.

## Diagnostics and ownership

Requesting basis diagnostics supplies canonical `BasisSnapshot`, `PivotRecord`
and `BasisCoordinates`. Structural columns are original A columns. Artificial
column i is the original-row vector `s_i*e_i`, tagged `AuxiliaryColumn`, never
`RowActivityColumn`. Thus `B_original=D*B_normalized`; coordinates for original
RHS r solve `B_normalized*z=D*r`. With `A=[-2], b=[-4]`, the initial auxiliary
column is `[-1]`, the entering coefficient is 2, the step is 2 and final
coordinates for RHS `[-6]` are `[3]`.

A `dynamic_cast<const phase_one::DiagnosticsView*>(bound->basis())` exposes the
optional phase-I `Snapshot`: current solve stamp, reason/termination, actual
pivot/degenerate/factorization/pricing counters, normalization, auxiliary values
and residuals, bounded compact trace and admission estimate. Before solving or
after unsupported/exceptional attempts, diagnostics are unavailable. A fresh
stopped result may expose only the last checked finite state. A pre-entry stop
has no artificial basis, candidate or successful residual. A changed attempt or
another workspace's reference cannot access the previous basis. Owning snapshot
copies may survive workspace destruction but remain historical.

Programs and prepared plans retain immutable owners; each created workspace owns
its own mutable matrices, factors, indices and diagnostics. No concurrent or
reentrant access to one workspace is supported. Separate workspaces may run
concurrently. The synchronous post-commit `pivot_observer` receives a borrowed
event valid during the callback and may copy it or request cancellation. Caller
captures must own their data and provide any needed synchronization. Observer
exceptions propagate through the canonical NVI, invalidate current diagnostics,
and permit a later fresh run. Destruction does not leave background work.

## Capacity, stops and costs

Default options are pivot limit 10000, dense entry limit 1048576, trace limit128
and relative pivot guard 1e-12. A zero pivot cap still permits an already-feasible
initial point; otherwise it stops before the required next factorization. Trace
limits zero or two change stored diagnostics only; total pivots remain actual
and truncation is explicit. Each workspace performs serial arithmetic, with
private `EIGEN_DONT_PARALLELIZE`, and validates existing resource credits.

Before dense allocation, checked arithmetic validates m, n, m+n, m*n, m*m and
Eigen index widths, plus `m*(n+m)<=dense_entry_limit`. Static rejection occurs
before factory invocation. The accounted admission estimate is

```
E = sizeof(double)*(m*n + 8*m*m + 16*m + 4*n)
  + sizeof(size_t)*(8*m + 2*n)
  + sizeof(PivotEvent)*min(trace_limit,pivot_limit).
```

All products/additions are checked. A runtime memory allowance smaller than E
returns resource_limit/capacity before dense initialization. E is an admission
estimate, not a hard heap/RSS bound. It covers normalized N; simultaneous current
and tentative B/LU storage with matrix temporary allowance; q, basic vectors,
cost/dual/column/direction and candidate/auxiliary vectors with vector allowance;
one current basis index vector and factor permutation allowance; normalization
signs; and the reserved bounded event trace. Eigen/allocator overhead, identity
strings, immutable program owners and caller-requested owning diagnostic copies
are not a hard-accounted heap guarantee. Canonical basis snapshots may themselves
contain O(m*m) explicit artificial coefficients.

Poll cancellation before initialization, after initialization, around every
factor/solve, at least every 64 candidate columns while pricing, after checked
candidates and observer callbacks, and before publication. Reuse the original
absolute steady-clock deadline. Explicit cancellation wins when both stops are
observed. Factorizations, solves and user observers are noninterruptible spans;
there is no hard stop-latency guarantee, sleep, detached watchdog or retry loop.

Publication is O(m+n+nnz) time/storage. Dense setup is O(m*n); each factored basis
costs O(m^3), solves O(m^2), pricing O(m*(n+m)), original residual checks
O(m+n+nnz). Stored scratch is O(m*n+m*m+n+m), plus O(min(pivots,trace_limit)) trace.
No polynomial total pivot bound or measured speedup is claimed. Numerical HTML
reporting and any measurements require their separate reviewed artifact stage;
unit tests and CTest duration are not performance evidence.
