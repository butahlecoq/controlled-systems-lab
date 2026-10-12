# Immutable linear programs and optional basis diagnostics

OPT-02 provides `<csl/optimization/linear_program.hpp>` and
`<csl/optimization/lp_backend.hpp>`, linked as `CSL::optimization`. The module
uses the canonical types in contracts.hpp and the retaining CORE-03 numeric
views. Source revision 1.3 is a deliberate migration from revision 1.2, not a
stable binary ABI. Model observation semantics are unchanged.

Source patch 1.3.1 names the LP data result `optimization::LPDataResult<T>`
(`std::variant<T, Diagnostics>`). Replace explicit LP `optimization::Result<T>`
annotations with this name; inferred `auto` callers require no change. The
objective module keeps `optimization::Result<T>` with its distinct `T`,
`Diagnostic` and `OperationStopped` alternatives. This resolves the public-header
collision in [issue #119](https://github.com/butahlecoq/controlled-systems-lab/issues/119):
objective and LP headers can coexist in either include order. Numerical and
diagnostic semantics are unchanged.

## Authored input and mathematical convention

Construct `LinearProgramInput`, then handle the alternatives returned by
`optimization::make_linear_program`: `LinearProgram` or `Diagnostics`.

```cpp
LinearProgramInput input{
    {{"problem"}, {"triangle"}}, {-1, -2}, 0,
    {1, 2, {0, 2}, {0, 1}, {1, 1}},
    {{0, {}}, {0, {}}}, {{{}, 1}}};
auto created = csl::optimization::make_linear_program(input);
```

This describes **minimize c^T x + offset**, with row intervals
`lower <= A*x <= upper` and variable intervals. The example minimizes -x-2y
on x,y >= 0, x+y <= 1, with optimum (0,1), value -2. Offset +7 changes the
reported program value to 5. Maximization of f is authored as minimization of
-f, including negating its offset; translating results and bounds back requires
an explicit sign/direction transformation and original-program evidence.

Missing lower/upper endpoints mean negative/positive infinity. Present endpoints
must be finite. Equal endpoints describe equality rows and fixed variables.
Free variables, free rows, explicit zeros, redundant rows, zero dimensions and
constant objectives are legal. A reversed interval is malformed input. The two
separate rows x<=0 and x>=1 are valid data for an infeasible program; construction
does not solve it or reject it as unsupported. Minimize -x on x>=0 is similarly
valid unbounded program data. No vertex-list or boundedness requirement is added.

Creation checks nonempty problem/program IDs, objective/variable/row dimensions,
finite objective and offset, finite ordered intervals and the CORE-03 CSR rules:
zero-based sorted unique columns, consistent offsets, finite stored coefficients.
It delegates numeric checks and private copying to CORE-03. Native adapters must
check their own integer-width limits before narrowing size_t indices. No backend
container appears in the public interface.

A ProgramId must change when mathematical program data or its reformulation
changes. IDs are caller assigned; this module does not hash programs or detect
reused IDs. Sharing the original ProblemId is insufficient to transfer bounds or
outcomes between different programs.

## Ownership and costs

LinearProgram has no default or public storage constructor. Its private storage
retains immutable numeric objective/CSR snapshots and owns interval arrays,
identity and offset. Creation copies producer data once; the producer must keep
input live and stable for the synchronous factory call. Later mutation,
reallocation or destruction cannot change the program. No external owner token
or surviving writable numeric alias is accepted.

Copies cost O(1) and share the immutable storage. The handle has copy operations
without destructive moves, so moving it leaves its source usable. Accessors
return const numeric-view references and const interval spans; retain the program
for their borrowed lifetime, or copy the numeric views to retain their buffers.
Numeric descriptors remain borrowed from those views. Concurrently assigning
the same handle object is not supported; distinct copies are shareable.

Creation costs O(m+n+nnz) time/storage. LPPort::snapshot now copies only this
handle. Prepared registry plans and independently created workspaces share its
private immutable data without per-worker CSR copies. Solver state and warm
starts belong exclusively to each workspace. Allocation/length exceptions
propagate; expected invalid input returns diagnostics.

## Numerical evaluation and result evidence

`evaluate_primal(program, candidate, policy, verifier)` returns
`PrimalEvaluation` or diagnostics. It recomputes c^T x+offset and maximum row
and variable interval violations. Each measure includes its scale: maximum of
1, relevant finite interval endpoints, and row activities or variable values.
The comparison is `violation <= absolute_tolerance + relative_tolerance*scale`.
The evaluator rejects nonfinite input/arithmetic and overflowing tolerance
comparisons. It performs ordinary binary64 arithmetic, without rounding bounds
or conditioning guarantees, in CSR column order. Time O(m+n+nnz), temporary
storage O(1) excluding result identity strings.

A finite evaluated objective is a candidate value. It is not an optimal value,
feasibility certificate or justified lower bound. Neither evaluator returns
objective-bound evidence automatically.

Typed `PrimalResiduals` and `DualResiduals` carry the full ProgramIdentity,
verifier ID/version and tolerances. Arithmetic is explicitly binary64.
Unavailable dual stationarity, sign or complementarity checks are absent, not
zero. Structured checks supplement raw diagnostics. They establish no outcome,
validated assurance or family completeness.

`evaluate_dual` is a numerical evaluation of supplied lower/upper row and
variable multipliers. With nonnegative multipliers the minimization convention is:

```
stationarity = c - A^T*row_lower + A^T*row_upper - var_lower + var_upper
Lagrangian constant = offset + row_l^T*row_lower - row_u^T*row_upper
                             + var_l^T*var_lower - var_u^T*var_upper
```

Multipliers on absent endpoints must be exactly zero; endpoint absence is
checked before multiplication. The evaluator rejects wrong dimensions and
nonfinite arithmetic. Negative multipliers are reported through the sign
violation. Stationarity scale is the maximum of 1 and, per column, the sum of
absolute objective and multiplier contributions. Sign scale is the maximum of
1 and absolute multiplier values. Complementarity remains absent because no
primal candidate is supplied. Complexity is O(m+n+nnz), with O(n) scratch space.

For the triangle above, row_upper=2, var_lower=(1,0), other multipliers zero give
stationarity (0,0) and Lagrangian constant offset-2. The literal values are -2
with no offset and 5 with offset 7. Small stationarity residuals do **not** make
that constant a guaranteed bound on an arbitrary program. This is not a general
certificate verifier, and it does not repair inexact dual feasibility.

`ProgramResult` keeps termination and ProgramOutcomeClaim separate. Completed,
cancelled, resource_limit and numerical_failure cannot by themselves establish
optimality, infeasibility or unboundedness. An `Unestablished` mathematical
outcome is a reported status without supporting evidence, including on a stopped
solve. Optional primal data remains a candidate. Stopped results may retain
independently supported bounds and residuals.

`ProgramObjectiveBound` carries its own `ProgramBoundEvidence`: complete
ProgramIdentity, support and assumptions. `SynthesisResult` continues to use
problem-scoped ObjectiveEvidence. Translating a bound requires explicit
mathematical justification; there is no implicit program-to-synthesis conversion.
Unchecked CertificateReference and Unestablished are not justified evidence.

`check_program_result` checks identity, enum values, finite candidate shape,
finite/ordered bound values, support metadata and residual metadata. It rejects
validated assurance because no verified-certificate type exists here. Supported
infeasibility conflicts with a supported finite upper bound; supported
minimization-unboundedness conflicts with a supported finite lower bound. Raw
candidates and unestablished reports are not silently promoted to supported
claims. Symbolic text remains unverified provenance. Passing this structural
checker is not proof of correct outcomes or bounds. It costs O(n plus evidence
text) and does not recompute solver certificates.

## Exclusive workspaces and authoritative attempts

LPWorkspace::solve is a nonvirtual dispatch method; adapters implement protected
`do_solve`. Dispatch stamps every attempt before calling adapter code. The stamp
retains the actual immutable program, the actual workspace's private const token,
and a monotonically increasing uint64 attempt number. There is no shared global
counter or mutable backend state in this module.

The observable states are:

- No attempt before the first call.
- `running` after advancing the attempt, before adapter code.
- `returned_result` for any returned ProgramResult, including cancellation,
  resource limits and numerical failures.
- `unsupported` for an Unsupported return.
- `exception` when adapter code throws; the original exception is rethrown.

Every call invalidates the previous attempt as current, including early stops
and unsupported calls. Counter exhaustion clears current eligibility and throws
before adapter code; it never wraps or reuses a number. This impractical overflow
path is implemented without a test-only mutation hook. Workspaces remain
noncopyable and exclusively owned; concurrent/reentrant calls on one workspace
violate the ownership contract. Independent workspaces have independent tokens
and attempt state. This is no native global-thread-pool audit.

LPWorkspace exposes workspace_identity() and last_attempt(). The latter is a
borrow, changed by the next solve; copy it for a historical record. The actual
`BoundWorkspace<LPPort>` forwards these same two observations, so callers can
obtain the expected stamp independently of any basis diagnostic. Other registry
ports acquire no LP accessor or numeric dependency. basis_factory still receives
the actual workspace. Diagnostics are destroyed before that workspace, which is
destroyed before its retained program.

## Basis and pivot data

BasisDiagnostics is optional. It reports snapshot/pivot/coordinate capabilities,
returns a typed available snapshot or BasisUnavailable, and can optionally answer
coordinates(reference,rhs). Reasons distinguish unsupported, not yet solved,
unavailable result and stale reference. Human-readable text is supplementary.
Generic LP adapters need no simplex data. Specialized algorithms must handle
unavailable features explicitly; they cannot silently substitute a different
algorithm. This ticket adds no warm starts, native pivot execution or hull
classification.

For m original rows, an available snapshot has exactly m ordered distinct column
identities in the neutral representation A*x-s=0:

- StructuralColumn(j) is A[:,j], j<n.
- RowActivityColumn(i) is -e_i, i<m.
- AuxiliaryColumn(id,coefficients) gives exactly m finite coefficients in the
  same original row space. Auxiliary identity is distinct from original indices.

The ordered matrix B is m by m and must be numerically invertible for an adapter
to advertise basis coordinates. Scaled/permuted/presolved native data must map
back to original rows. Rank-reduced, unmapped or singular/factorization-failed
states report unavailable. Do not pad or guess a basis. Zero rows admit an empty
basis and empty coordinates for an empty rhs; no leaving position or pivot exists.

BasisReference binds the solve stamp and basis iteration. Iteration 0 is an
initial basis; each actual pivot advances it once. A snapshot is the current
**post-pivot** basis. Optional PivotRecord also contains before/after references,
the ordered pre-pivot basis, entering/leaving columns, leaving slot k and:

`coefficient = (B_before^-1 * a_entering)[k]` (signed).

The after reference must equal the snapshot reference and have iteration
before+1. The leaving identity is before_basis[k], entering was nonbasic, and
only slot k changes. For B_before=[2], entering=[6], the coefficient is **3**;
the post-pivot expression 1 is not this diagnostic. For entering=[-6], it is
**-3**. The post-pivot [6] basis maps rhs=[12] to coordinates [2]. Last-pivot
history beyond this record is optional and not required.

Coordinates(reference,rhs) computes B*z=rhs for the requested current ordered
basis in original row coordinates. Both rhs and returned z must contain exactly
m finite values. The result owns z and its reference. A changed basis/attempt
returns stale-reference unavailability; this interface does not restore history.

Check returned data against fresh authoritative state:

```cpp
// Handle the unavailable alternative before extracting BasisSnapshot.
auto answer = worker.run(context);
auto diagnostic = worker.basis()->snapshot();
if (auto* basis = std::get_if<BasisSnapshot>(&diagnostic)) {
    auto issues = optimization::check_basis_snapshot(*basis, worker.last_attempt());
    // Handle issues before using this as the current basis.
}
```

`check_basis_snapshot` requires a returned_result attempt and exact stamp/program
association, then checks counts, tagged indices, distinct identities, finite
auxiliary data and pivot ordering/association. `check_basis_coordinates` also
checks the requested basis reference and finite m-vector shape. Checks are
structural: they do not factor B, recompute pivot coefficients, verify coordinate
solutions or detect a dishonest adapter attaching old numbers to a new stamp.
Basis validation costs O(m^2) for distinctness and auxiliary data, without
numeric program copies. No claim of linear-time diagnostic validation is made.

Worker W1 cannot accept W2's stamp merely because both solved the same program
at attempt 1. After a second stopped call, attempt-1 snapshots are historical,
never current. Unsupported or exceptional calls expose no current available
basis. Owning snapshots can outlive workspaces; their copied stamps retain only
immutable program data and identity tokens. For current checks callers must use
fresh last_attempt(), not a deliberately copied historical expected record.

## Migration and verification scope

Replace authored LinearProgram aggregates with LinearProgramInput plus the
checked factory. Replace public field access with const accessors. LP adapters
override do_solve rather than solve; LPPort retains its canonical request and
run path. Source 1.5 replaces the QuadraticProgram placeholder with immutable
objective/geometry accessors; see the [convex source migration](convex-programs.md).
Only callers
that construct LPs need CSL::optimization; registry itself links contracts only.

Existing endpoint/sign registry fixtures retain their finite one-variable domain
and literal outputs. Their program bounds use program identities; the forwarding
synthesis fixture now reports an incumbent without blindly copying those bounds.
Existing destruction-order and independent-workspace tests remain in place.

Unit and contract tests cover literal primal/dual values, offsets, free/fixed and
equality bounds, malformed input, contradictory rows, unbounded data, partial
results, evidence mismatch, typed optional diagnostics and current-versus-historical
basis association. The installed optimization client compiles only against the
installed package and executes a candidate-evaluation fixture with separate
workspaces. No fixture is advertised as a general LP solver.

This is interface/evidence coverage of T-L01/T-L02, not a production native LP
adapter, completed barycentric membership/recovery algorithm, phase-I kernel,
validated arithmetic, full certificate validation or complete optimal-family
construction. OPT-03 and later algorithm/test tickets retain that work.

## Registered equality/nonnegative phase I

The independent `phase-one-bland` version1 adapter is now available through the
same immutable `LinearProgram` and `LPPort` seam for zero-objective `A*x=b, x>=0`
programs. It supplies numerical auxiliary and original-space basis/pivot data;
its guarded Bland policy, finite caps, cooperative stops and unestablished
outcomes are specified in [the phase-I contract](phase-one.md). This additive
module leaves the canonical source1.5/NVI/evidence rules above unchanged. Hull
reduction, grouped classification and validated certificates remain separate.
