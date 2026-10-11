# Immutable terminal objectives and recorded norm squaring

OPT-01 adds `<csl/optimization/objectives.hpp>` and `CSL::objectives`, using the
existing revision 1.1 objective DTOs and [immutable numeric snapshots](numeric-data.md).
There is no solver, terminal-minimizer selection, or optimal-family construction
in this module. It provides coefficient validation, numerical evaluation and one
explicit reformulation. It does not establish optimality, uniqueness or family
completeness.

## Publication and ownership

`optimization::snapshot(const TerminalObjective&, ObjectivePolicy)` returns
`Result<Objective>`, a variant of `Objective`, `Diagnostic`, and
`OperationStopped`. The three authored forms retain their original conventions:

| Authored form | Original cost | Required shape |
|---|---|---|
| `LinearTerminal` | `c^T x + d` | `c` has length n |
| `QuadraticTerminal` | `0.5 x^T Q x + q^T x + c` | Q is n by n; q has length n |
| `ResidualNormTerminal` | `||L x - r||_2` | L is m by n; r has length m |

The supplied L includes any weights. Rectangular maps, rank deficiency, zero
coefficients, and zero dimensions are supported. No additional term or weight
is inferred. All coefficients and offsets must be finite. Dense storage and
dimension-product validation use `numeric::snapshot`; shape failures specific
to objectives use `objective.shape`.

Publication copies producer buffers into privately created immutable numeric
storage. Even a moved producer with surviving mutable aliases cannot change the
published objective. The input must remain readable and unmodified only during
the synchronous call. Objective handles copy in O(1) and deliberately have no
destructive move; the source of a move remains usable. `coefficients()` returns
an owning variant of read-only matrix/vector views by value. A returned numeric
descriptor/span still needs its owning view for its entire borrow lifetime.

`policy()` and optional `quadratic_checks()` return copies, including verifier
strings. Mutating those copies cannot change the stored policy/evidence. There
is no public default/storage constructor or partially valid successful handle.
Each evaluation/reformulation uses private local buffers. Concurrent reads of
independent handle copies are safe; concurrent assignment of the same handle
object requires caller synchronization.

## Numerical quadratic policy

Only `Assurance::numerical` is implemented. A validated request returns
`unsupported` at `objective.assurance`, without a numerical fallback. Unknown
assurance values and negative/nonfinite tolerances return `invalid_input`.
Policy tolerances default to `1e-8` absolute and relative, and may both be zero.

For Q, let `s = max_ij |Q_ij|` (zero for empty Q) and
`a = max_ij |Q_ij-Q_ji|`. Publication requires
`a <= absolute_tolerance + relative_tolerance*s`. Failure returns
`invalid_input` at `objective.symmetry`. This is an explicit tolerance policy,
not an exact-symmetry assertion. Original Q is never overwritten.

Eigen 3.4.0 privately computes eigenvalues of the symmetric part `(Q+Q^T)/2`,
normalized by s to reduce overflow, then rescales the results. The algebraic
identity `x^T Q x = x^T ((Q+Q^T)/2) x` explains this check; it is distinct from
the numerical assurance of the eigensolver. Evaluation uses the stored original
Q, and rounding may make the two arithmetic paths differ. The zero/empty matrix
bypasses Eigen entirely. No PSD projection, eigenvalue clipping or coefficient
repair occurs.

Let `lambda_min` be the computed minimum eigenvalue,
`e = max_i |lambda_i|`, and `t = absolute_tolerance + relative_tolerance*e`:

- `lambda_min < -t`: `invalid_input` at `objective.psd` (numerically indefinite).
- `-t <= lambda_min < 0`: `unsupported` at `objective.psd` (PSD unresolved).
- `lambda_min >= 0`: the numerical check accepts the objective, including zero
  and semidefinite cases. It does not require positive definiteness.

The optional `QuadraticChecks` exists only for quadratic objectives. It records
the two `NumericalCheck`s, minimum eigenvalue and eigenvalue scale. The symmetry
check's `max_residual` is a; the PSD check's `max_residual` is the measured
negative-eigenvalue violation, zero on an accepted object. This is **not an
eigendecomposition backward-error bound**, interval enclosure, certificate, or
proof of convexity. The verifier ID identifies the symmetric-part Eigen check.
No evidence input is accepted or relabeled as verified.

Some mathematically PSD but ill-conditioned matrices may produce a small negative
computed eigenvalue and be declined. Scaling that turns a nonzero symmetric-part
entry into zero, rescaling that erases a nonzero minimum eigenvalue, nonfinite
checks, and eigensolver failure return `OperationStopped` with
`StopReason::numerical_failure`. These guards do not make floating arithmetic
validated or detect every rounding error.

## Original evaluation and recorded transformation

`evaluate(objective, point)` computes the original cost directly from that
objective's stored coefficients. It requires exactly n finite coordinates;
violations return `invalid_input` at `objective.point`. It never reads a solver's
reported value or takes a square root of the expanded quadratic. The residual
norm uses repeated `std::hypot`, including at zero, so no derivative or division
by a zero norm is needed.

`square_residual_norm(original)` accepts only a residual objective and returns
`Result<NormSquareReformulation>`. Its immutable record provides `original()`,
`squared()`, and `transformation() == residual_norm_squared`. The squared
objective contains:

```
Q = 2 L^T L
q = -2 L^T r
c = r^T r
```

Its policy is retained and its generated Q passes the same numerical quadratic
checks. The record retains both coefficient sets and their numerical policy;
it makes no separate validated equivalence claim. In real arithmetic, squaring
is strictly increasing on nonnegative norm values, so it preserves the entire
minimizer set. Floating expansion can worsen conditioning and cancellation;
cost gaps and tolerances in squared units are not gaps/tolerances in norm units.
There is no sum-of-terms transformation.

For a solver-returned point, report `evaluate(record.original(), point)`.
For L=`[[1,0],[0,2],[1,-1]]`, r=`[1,2,0]`, the generated coefficients are
Q=`[[4,-2],[-2,10]]`, q=`[-2,-8]`, c=`5`. At x=`[3,1]` the original cost is
sqrt(8), while the expanded quadratic gives 8; at x=`[1,1]` both are zero.

L=`[1,0]`, r=`[1]` has zero cost at both `[1,0]` and `[1,7]`, and in fact at
every `[1,y]`. Zero linear/quadratic coefficients yield their stored offset;
zero L with r=`[3,4]` yields the constant norm 5 and squared constant 25. An
m-by-0 residual map acts on the empty point and yields `||r||`; a 0-by-n map
yields zero on every length-n point. No case returns or assumes a unique
terminal minimizer.

## Arithmetic, costs and failure limits

Arithmetic uses ordinary double products and sums, in coordinate order, with
no compensated/exact/interval arithmetic or promised rounding bound. Overflow
and nonfinite results return `OperationStopped`, never a usable infinite/NaN
cost. A finite norm may exist while its squared coefficients do not: r=`[1e200]`
with zero L evaluates to `1e200`, but squaring fails. The original handle remains
usable. Even a mathematically finite expanded value can fail when an intermediate
overflows. Ordinary underflow/cancellation in cost evaluation is not certified.
Allocation failures and standard container length errors propagate as exceptions,
as in the numeric layer.

Linear/residual publication costs O(n)/O(mn+m) time and storage; quadratic
publication uses O(n^3) eigensolver time and O(n^2) storage. Evaluations cost
O(n), O(n^2), and O(mn+m), respectively, with no shared mutable workspace.
Norm expansion costs O(mn^2+mn+m), O(n^2+n) new coefficient storage, followed by
quadratic validation. Resource budgets, cancellation and solver workspaces are
separate future adapters.

## Build and verification

Link `CSL::objectives`; the installed public interface depends only on
`CSL::numeric` and `CSL::contracts`. Eigen 3.4.0 uses the existing ADR 0002
SHA-256 pin and private SYSTEM includes with `EIGEN_MPL2_ONLY`. Neither Eigen
types, include paths nor CMake targets appear in the exported interface. The
module-specific fetch helper does not execute Eigen's build/install project.
Eigen notices are copied to `share/CSL/notices/Eigen-3.4.0` at installation;
the pinned source URL and source/distribution obligations remain documented in
[ADR 0002](../architecture/decisions/0002-native-integrations.md).

The [public tests](../../tests/unit/objectives/objectives_tests.cpp) cover the
T-O01/T-O02 literal oracles and objective-degeneracy part of T-C01. The
[consumer](../../tests/installed/objectives_client.cpp) runs both in the source
build and from a copied source tree using only the installed package. A full
solver/family proof is outside these objective tests.
