# Immutable convex programs and the reference QP adapter

Source revision 1.5, OPT-08 / issue #22. The canonical request is published by
`optimization::make_convex_program(ConvexProgramInput, ObjectivePolicy)` from
[convex_backend.hpp](../../include/csl/optimization/convex_backend.hpp).
The backend is registered through the independent ConvexPort using
[adapters/convex/highs.hpp](../../include/csl/adapters/convex/highs.hpp).
Link `CSL::convex` for data and numerical checks, or `CSL::highs_convex` for the
reference native implementation. Neither public header exposes native types.

## Source migration and ownership

Revision 1.5 replaces `QuadraticProgram { LinearProgram linear; SparseMatrix
hessian; }` and `variant<QuadraticProgram>` with validated immutable handles.
Construct `ConvexProgramInput` with original ProgramIdentity, TerminalObjective,
CSR constraints, variable/row intervals and an optional squared ProgramId.
Callers must check the result: ConvexProgram, Diagnostics, or OperationStopped.
`ConvexDataResult` is distinct from the existing objective Result and LPDataResult.
LP, MODEL-02, resource and execution interfaces retain their prior semantics.

TerminalObjective and the existing immutable Objective are the sole objective
authority. A former sparse-Hessian author explicitly expands its complete
symmetric matrix to QuadraticTerminal; no triangle is silently chosen. The
canonical quadratic representation is dense, with O(n²) storage and the existing
O(n³) numerical PSD check. This migration introduces no alternate sparse PSD
authority. For a linear objective, the exact zero Hessian uses an owning empty
CSR view with O(n) row offsets and no dense allocation or eigensolve.

Publication validates nonempty identities, objective dimensions, finite data,
sorted unique CSR indices, offsets and ordered finite present interval endpoints.
An absent endpoint is infinite. Quadratics require exact entrywise symmetry in
addition to ObjectivePolicy's unchanged numerical PSD policy. Materially negative
eigenvalues are invalid; negative values within the policy threshold remain
unsupported, without clipping or repair. Numerical arithmetic failures remain
OperationStopped. Publication is backend neutral and proves no feasibility.

Both handles copy in O(1); moving by value leaves the source usable. Publication
copies producer storage. Retained numeric/objective/reformulation handles outlive
the original program. Accessors return const references or borrowed spans; retain
an owner for the lifetime of a borrow. `reformulation()` is a nullable borrowed
pointer; copying its value gives an independently retained owning record.
Changed mathematical data requires a fresh ProgramId, with uniqueness supplied
by the caller rather than a global registry database.

The private implementation reuses a zero-objective LinearProgram solely for
geometry validation, residuals and structural result checks. It is never exposed
as the QP's objective or dispatched to an LP registration. The actual objective
and solver-form objective remain canonical Objective handles.

## Objectives and provenance

Supported originals are affine, convex quadratic `0.5*x'Q*x+q'x+c`, and a pure
residual norm `||L*x-r||₂`. Offsets are retained. For a pure norm, publication uses
the existing explicit norm-square reformulation: `Q=2L'L`, `q=-2L'r`, `c=r'r`.
The original and squared ProgramIds must be distinct and nonempty under the same
ProblemId. The retained reformulation identifies the transformation and both
Objectives. Linear/quadratic requests reject an unnecessary squared ID.

There is no sum-objective input or implicit squaring of mixed objectives.
For example, `|x-1|+0.5x²` on `[0,1]` minimizes at 1; replacing only the norm by
its square changes the minimizer to 2/3. A successful pure-norm solve therefore
reports the original norm cost and checks multipliers in original units.

## Workspace lifecycle

ConvexWorkspace's nonvirtual solve boundary owns a unique WorkspaceIdentity and
monotonic ConvexSolveAttempt. Adapter subclasses override do_solve. Each call,
including pre-cancelled and Unsupported calls, advances the attempt before
dispatch; state is running, returned_result, unsupported, or exception. An
exception records its state before propagation. Sequence exhaustion clears the
old current record and throws rather than wrapping. LP stamps remain separate.
BoundWorkspace exposes the same authoritative convex identity/current attempt.

Historical stamps retain the immutable request and identity after destruction.
A copied historical attempt is not the current attempt. Each factory produces
an exclusive workspace; concurrent calls on one workspace are outside the
contract. Different workspaces can run concurrently within ResourcePolicy.
Native instances are lazy, private and reused, while model, options, clocks,
solutions, basis, logs and callback borrows are reset per call. Native exceptions
discard private native state. No warm-start performance is promised.

## Original-space checks and evidence

evaluate_primal returns original and solver costs, row and variable residuals.
evaluate_dual takes a candidate and explicit lower/upper row and variable
multipliers `(alpha,beta,gamma,delta)`. They are nonnegative in a KKT solution;
the helper retains negative supplied values so sign violations remain observable.
Nonzero multipliers at absent endpoints are invalid.

Stationarity is `gradient(f)-A'alpha+A'beta-gamma+delta`. The gradient is q for
linear objectives, Qx+q for quadratics, and `L'(Lx-r)/||Lx-r||` for nonzero norms.
At checked binary64 componentwise zero residual, zero is the selected valid norm
subgradient, with zero multipliers; no division by zero or differentiability
claim occurs. Native squared-objective multipliers are divided by twice the
positive original norm, with unsafe arithmetic withholding dual evidence.

Complementarity measures absolute products of each multiplier with its own
endpoint slack. All five measures use finite nonnegative maxima and the check
`violation <= absolute_tolerance + relative_tolerance*scale`. Primal scales use
the maximum of 1, activities/coordinates and present endpoints. Stationarity
scales use the per-coordinate sum of absolute gradient and multiplier terms,
with minimum 1. Sign scales use absolute multipliers, minimum 1.
Complementarity scales use `abs(multiplier)*max(1,abs(value),abs(endpoint))`,
minimum 1. Nonfinite products, scales, thresholds or evaluations cannot pass.

Residual contexts name the ORIGINAL identity and versioned verifier. The result
checker verifies structural identity, dimensions, enums and evidence metadata;
it does not re-prove numerical residuals or PSD. Native optimal is promoted to
neutral optimal only when a current finite candidate and all five original-space
measures pass. Otherwise it becomes numerical_failure/undetermined, retaining
available current primal checks and native diagnostics. Outcome support remains
Unestablished even after numerical KKT passes: this is numerical evidence, not a
validated certificate or theorem of exact optimality. Both objective bound fields
remain absent. There is no OptimalFamily, complete minimizer enumeration, basis,
pivot or certificate. Native infeasible/unbounded reports also remain Unestablished.

## Declared native profile and admission

The reference uses the existing private pinned HiGHS 1.11.0 archive, SHA256
`2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275`, MIT, with
signed 32-bit HighsInt. The LP port remains independent. One archive/export and
existing license notices serve both adapters; private static LINK_ONLY edges
do not publish native headers.

Preparation admits binary64 numerical output, all three objective forms, CSR
linear constraints, equalities, free/fixed variables and lower-dimensional sets.
Validated assurance, basis, family/completeness or incompatible representations
are rejected before workspace creation. The common maximum is **4,096 variables**,
including the zero-Hessian LP route. A pure admission calculation precedes native
construction, model conversion and either solve; execution repeats it for direct
workspace callers. Nonzero A/Q entries at or below `1e-12` are unsupported because
the native assessor would remove them. Explicit zero entries remain legal.

Admission checks dimensions, nonzeros, start-array +1 extents and native derived
factor counts before narrowing. For valid basis states, inactive dimension k<=n.
Factor initialization/recompute has capacity<=n; expansion doubles capacity only
when c<=k+1, so `C=2(n+1)` bounds every capacity. Checked wide integer arithmetic
covers C², n², n(n+1), triangular counts, container/index/byte limits and the
named transient factor-copy, recompute and transpose sums. At 4096, C=8194,
C²=67,141,636, and two conservative double buffers total 1,074,266,176 bytes.
These are representability calculations, not allocated/measured peak memory.
The 4096 cap is conservative; it is not a heap guarantee, maximal possible size
or convergence promise. Actual allocation may still fail. A requested memory
cap is Unsupported. Native integer build changes require a new audit.

## Native translation, initialization and stopping

The adapter supplies column-compressed constraints and the complete lower
Hessian triangle in HiGHS's half-quadratic convention; no coefficients are
regularized. Exactly zero Q selects configured simplex; nonzero Q uses choose.
Both instances use threads=1, parallel=off, presolve=off, and explicit infinity
thresholds so finite authored bounds/costs are not silently made infinite.
QP regularization is zero, nullspace limit4096, and use_warm_start=true; these
audited settings are read back. No global scheduler reset is performed.

Nonzero Q first solves a configured zero-cost feasibility LP with identical
geometry. A rowless QP receives a private tautology `0=0`, avoiding the native
bounded-start Cholesky shortcut that cannot generally handle singular Q at zero
regularization. The full QP then receives the current finite solution first and
valid basis second. Current flags, dimensions, warm-start setting, native absolute
bound predicate and independently recomputed Ax are checked before QP run.
Failure withholds QP execution; no hidden default native phase-I fallback is
allowed. The private row is excluded from original residuals and has zero
multiplier contribution. Zero-variable problems explicitly evaluate constant
rows and objective, so native ModelEmpty cannot erase a contradiction.

HighsConvexOptions exposes separate feasibility/simplex and QP iteration caps.
ResourcePolicy and finite nonnegative tolerances are required. Native feasibility
tolerance is max(requested absolute tolerance,1e-10); original-space checks use
the exact requested absolute/relative policy. Relative tolerance is not claimed
as a native QP option. Cancellation/deadline checks occur before/between phases
and before result publication. Simplex can interrupt through its callback; the
pinned QP loop has no public stop-token callback, so asynchronous QP cancellation
is only observed at phase return. Native time/iteration checks cannot preempt a
factorization; no hard deadline or prompt QP cancellation guarantee is made.

Known native resource statuses map to resource_limit, including recognized memory
limit with API error. API errors withhold untrusted native solution/info.
Interrupt maps to cancelled; ambiguous unbounded-or-infeasible remains undetermined.
Unknown/setup/solve/arithmetic errors cannot become infeasibility claims.
Raw owned diagnostics record original/solver identities, profile/options, native
phase/status/iterations, available costs, private row/start and captured logs.
Logging callbacks replace console logging and are removed before borrowed
context/capture lifetime ends. Failed calls expose no stale earlier solution.

## Independent public behavior fixtures

| Input | Literal oracle |
|---|---|
| `(x-3)²`, `[0,5]`; then `[0,2]` | x=3/cost0; x=2/cost1, upper multiplier2 |
| `||[x-3,4]||`, `[0,2]` | x=2, original sqrt17, squared17, original upper multiplier1/sqrt17 |
| `|x-3|`, `[0,5]`; constant `||(3,4)||` | checked zero residual; original5/squared25 |
| `(x-1)²`, `[0,2]×[0,1]` | analytic argmin `{(1,t):0<=t<=1}`; one returned feasible t, no enumeration claim |
| Q=`[[4,2],[2,4]]`, q=`[-8,-10]`, c17, x+y=2 | (.5,1.5), cost4.5, gradient(-3,-3), equality upper multiplier3 |
| `1e-10*x=1e-4`, `(x-3)²` | x=1e6, cost999994000009 |
| x fixed1e21, x² | finite x=1e21, cost1e42 |
| contradictory rows; `-x`, x>=0; `x²-y`, y>=0 | infeasible; zero-Q unbounded; nonzero singular-Q unbounded |
| no variables, constant7; constant `0>=1`; `0=0` | empty optimal point/cost7; infeasible; empty feasible point |
| O(n) zero-linear publication at4095/4096 vs4097/46341 | registered preparation accepts vs Unsupported; no large native solve |

Tests also cover exact PSD/asymmetry policy, producer mutation/retained owners,
literal nonzero residuals, arithmetic stop classification, actual zero-iteration
stops, pre-cancel/deadline, independent/concurrent workspaces, reuse and historical
attempts. Concurrent launch failure releases the two-party barrier before joining
the first future. An installed consumer solves the norm fixture through
find_package(CSL CONFIG) from the actual prefix. Both neutral header-order clients
retain numeric-only linkage. Rare native MemoryLimit/error and sequence-exhaustion
paths are not claimed to have been induced. CTest elapsed times are not benchmarks.

Pinned implementation references: [factor capacity](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/highs/qpsolver/factor.hpp),
[feasible start selection](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/highs/qpsolver/feasibility_highs.hpp),
[QP dispatch](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/highs/qpsolver/a_quass.cpp),
[native options](https://github.com/ERGO-Code/HiGHS/blob/v1.11.0/highs/lp_data/HighsOptions.h).
These explain the chosen profile; executable public fixtures supply its runtime
evidence. Numerical singular convergence outside the tested fixtures is not
guaranteed, and the mathematical objective is never perturbed to hide a failure.
