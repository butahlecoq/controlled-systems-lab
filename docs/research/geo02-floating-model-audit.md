# GEO-02: binary64 set operations and the real-valued model

Date: 2026-10-16. Scope: the merged `csl.geometry.affine-sum` implementation
and its selected finite-V, H-to-V, hull-reduction, and LP dependencies. This is
the scientific review requested by [GEO-02 #40](https://github.com/butahlecoq/controlled-systems-lab/issues/40),
including the [2026-10-15 review questions](https://github.com/butahlecoq/controlled-systems-lab/issues/40#issuecomment-6189677129).
It establishes a conditional mathematical relation, identifies the missing
premises for a real-model guarantee, and does **not** validate the current
floating-point pipeline against an unknown pre-rounding physical model.

## Three sets that must not be conflated

1. **Authored set** `P_real`: the user's intended real-valued inputs and
   coefficients, which may predate binary64 conversion. No input-uncertainty
   certificate currently binds those intentions to stored numbers.
2. **Represented input** `P_64`: for a finite V input with stored vertices
   `v_i`, this is `conv{v_i}`, interpreting each finite binary64 coordinate as
   an exact dyadic rational. Likewise, the stored affine matrix and offset are
   exact dyadic coefficients *for this interpretation*. For an H input, `P_64`
   means the exact half-space/equality intersection of its stored dyadic rows;
   it does **not** mean the polytope output by a numerical converter.
3. **Generated and published set** `Q_64`: `conv{q_i}` or
   `conv{q_ij}`, where the `q` coordinates are the finite binary64 results of
   the loops in [`src/geometry/affine_sum.cpp`](../../src/geometry/affine_sum.cpp).
   The published V representation contains either all generated candidates or
   a subset passing structural and exact dyadic deletion checks. The latter
   prove `conv(retained q) = conv(all q)` as exact real sets of *stored* points.

`SetRelation::equivalent` plus `Assurance::numerical` is the port's algorithmic
relation claim under its recorded assumptions. It does not assert
`Q_64 = M P_real+b`, `Q_64 = P_real+R_real`, exact containment in either
direction, or a bound to either authored real model. `NumericalCheck.max_residual`
describes an attempted reducer reconstruction residual; it is not the distance
from `Q_64` to either real model. For direct finite V, singleton, and empty
inputs, the operation now publishes an exact-post-hoc outward L-infinity bound
from the stored dyadic operation to `Q_64`. For H-to-V inputs, it publishes a
bound when independent global coverage is certified for a bounded ambient-one
interval or supported bounded axis-aligned box. Unsupported H profiles still
leave `error_bound` empty because their global coverage remains uncertified.
The public [affine-sum contract](../contracts/affine-sum-operations.md) and
[`OperationResult`/`GeometryEvidence` types](../../include/csl/geometry/contracts.hpp)
carry this distinction to callers.

## What the deletion proof actually proves

The candidate reducer may use a numerical LP to *find* a convex-combination
witness. Before deleting a stored candidate `q_i`, the consumer checks the
retained/removed partition and acyclic dependencies, then independently checks
with exact dyadic arithmetic that nonnegative stored weights sum exactly to one
and reconstruct `q_i` exactly from stored retained points. If any check fails,
the complete generated cloud is materialized. Thus each deleted `q_i` lies in
`conv(retained q)`, while every retained point was generated, proving the two
hulls equal. This holds even if the LP misses redundant points. It says nothing
about how accurately a candidate was generated. See
[`valid_reduction` and the exact check](../../src/geometry/affine_sum.cpp),
[`exact_convex_combination.hpp`](../../src/geometry/exact_convex_combination.hpp),
and the [hull contract](../contracts/hull-reduction.md).

The [GEO-02 published report](https://butahlecoq.github.io/controlled-systems-lab/geo02-20261013T061151Z-449f188d2de1f50164a55a7b3b3931132dfa8384306ac3c93d5fb3a958cbd754/index.html)
records five small fixtures and support checks. These observations test those
instances; they are not a bound for arbitrary dimensions, magnitudes or
conversion inputs.

## Conditional error theorem for finite V inputs

For a finite nonempty V input, let `v_i`, `M`, and `b` be the stored dyadics,
and let `y_i = M v_i+b` be evaluated *exactly as rational arithmetic*.
The implementation instead stores binary64 `q_i`. If independently verified
numbers `e_i >= ||q_i-y_i||` are available for a chosen norm, set
`E = max_i e_i`. Then

```text
d_H(Q_64, M P_64+b) <= E.
|h_Q(d)-h_(M P_64+b)(d)| <= E ||d||_*  for every direction d.
```

For a Minkowski sum, use each pair `y_ij=v_i+w_j` and the stored result
`q_ij`. The same conclusion holds with `E=max_ij ||q_ij-y_ij||`, because
`conv{v_i}+conv{w_j}=conv{v_i+w_j}`. These are *two-sided* statements: a point
with barycentric coefficients `lambda` in either convex hull is paired with
the point using the same coefficients in the other hull; their distance is at
most `sum lambda_i e_i <= E`. Exact candidate deletion adds zero to `E`.
For Euclidean distance, a verified coordinate bound `|q_ik-y_ik|<=e_k`
suffices with `E=sqrt(sum_k e_k^2)`; support error is at most
`sum_k |d_k| e_k`. Empty inputs remain empty and need a separately stated
empty-set metric convention.

The operation implements this post-hoc proof for direct finite V inputs. It
uses checked exact dyadic accumulators to compare every generated binary64
coordinate with the exact operation on stored input dyadics, tracks the
maximum absolute coordinate discrepancy, and rounds that value upward to a
representable binary64 value using integer bits. The bound uses the output-coordinate units
and L-infinity Hausdorff metric. Exact candidate deletion then adds zero error.
Empty output uses distance zero from empty to empty. Checked-range failure or
an exact error too large for finite binary64 fails closed. The implementation
compares the same candidate values that it passes to materialization, so
cancellation and gradual underflow are covered without a dimension-dependent
unit-roundoff formula. Non-finite generated coordinates cause an unsuccessful
operation. An implementation relying instead on a forward-error formula must
account for the exact evaluation order, multiplication and addition rounding,
dimension, underflow/subnormals, compiler contraction/reassociation and
overflow.

For a bounded ambient-one H input, the exact stored-dyadic interval checker
also bounds the Hausdorff distance `E_H` between the H-defined interval and the
convex hull of the returned V vertices. Affine-sum independently reruns this
checker against the original H rows and returned extrema; it does not consume
the converter's numerical relation or residual as proof of coverage. If
`E_gen` bounds candidate-generation error and `M` is the stored affine map,
then

```text
d_H,∞(M P + b, Q) <= max_r sum_c |M_rc| * E_H + E_gen.
```

For a Minkowski sum with left/right conversion errors `E_L` and `E_R`,

```text
d_H,∞(P_L + P_R, Q) <= E_L + E_R + E_gen.
```

These follow by pairing points with the same convex coefficients in the two
V hulls, applying the induced L-infinity operator norm to the affine error,
and pairing summands for Minkowski addition. Direct finite V inputs have zero
conversion error. Exact dyadic arithmetic composes and outward-rounds the
result, and exact candidate deletion adds zero. Composition through H inputs
is implemented for the bounded ambient-one interval profile and the bounded
axis-aligned box profile in dimensions 2 through 12. Neither profile certifies
authored-real input uncertainty.

The error is observable even with exact dyadic V inputs. Take a singleton
`v=(10^16,1,-10^16)`, a one-row matrix `M=(1,1,1)`, and `b=0`. Every input
number is exactly representable. The exact real image is `{1}`. The current
left-to-right binary64 accumulation computes `10^16+1` as `10^16`, then adds
`-10^16`, publishing `{0}`. The post-hoc evidence reports an L-infinity
bound of 1 for that one-unit discrepancy. Similarly, multiplying stored
`2^-1022` by stored `2^-53` has exact result `2^-1075`, below the smallest
positive binary64 subnormal; a rounded zero is a finite but different
candidate. The operation reports `2^-1074`, the smallest positive subnormal,
as an outward bound for that underflow.

## Why the H path needs an additional proof

For H inputs the adapter first accepts a selected converter's numerical
`equivalent` claim and `NumericalCheck`, then checks that each returned vertex
satisfies the original H rows within the caller's row-scaled tolerance. These
are local checks on *returned* vertices. They cannot prove every extreme point
was returned, that the output hull covers the full H polytope, or that the H
polytope is contained in a known expansion of the output. For example,
`P=[0,L]` may be described by `x>=0, x<=L`. Returning only vertex `0`
has zero row violation for any `L>0`, yet its Hausdorff distance from `P`
is `L`. A converter's asserted numerical equivalence is not an independently
checked coverage certificate. The [Qhull conversion contract](../contracts/polyhedral-conversion.md)
and [upstream Qhull precision manual](https://www.qhull.org/html/qh-impre.htm)
also distinguish empirical precision handling from a theoretical bound.

When a converter establishes `d_H(P_64, V_conv)<=E_conv` under a stated
metric and assumptions, and candidate generation establishes `E_gen` for
that converted V set, the real stored-H affine-image bound is at most
`||M|| E_conv+E_gen`. For two H/V summands it is at most
`E_conv,left+E_conv,right+E_gen`. The norm of `M` must be induced by the
chosen point norm. These compositions are mathematical consequences of
Lipschitz continuity and the triangle inequality. For `P_real`, add
independently justified input and coefficient/model uncertainty. Unknown
pre-rounding data admit no finite claimed error from the present evidence
alone.

The converter independently certifies bounded **ambient-one** H-to-V inputs
against the original stored dyadic rows. Exact rational endpoint bounds and
the returned finite V extrema give a two-sided L-infinity Hausdorff distance,
rounded upward into the conversion evidence. Empty-to-empty distance is zero.
This covers the one-dimensional represented-input profile, including equality
singletons.

It also certifies bounded, axis-aligned boxes in ambient dimensions 2 through
12. For each coordinate, exact dyadic comparisons derive the lower and upper
H endpoints. The checker verifies that every returned V point is inside those
intervals and every distinct box corner is present. Those two checks prove
both inclusions for this box profile and publish a zero L-infinity bound. It
also publishes zero for an empty output when supported axis-aligned stored
rows prove the H set is empty. It caps corner enumeration at 4,096 and declines
unsupported rows, nonempty unbounded inputs, nonfinite values, and arithmetic
range failures. It does not cover
rotated boxes, general higher-dimensional polytopes, or pre-rounding
authored-real values. For ambient-one H inputs and supported box inputs, the
affine-image/Minkowski adapter independently reruns the relevant checker on
the original H rows and converted vertices, then composes its bound with exact
candidate-generation error. Other H-input operation evidence still omits
`error_bound`.

## Scientific disposition and follow-up gate

The represented-candidate deletion guarantee is sound for its narrow scope.
The existing `equivalent` result remains an **unvalidated numerical algorithm
claim** conditional on correct represented input interpretation and, for H
inputs outside the independently checked ambient-one interval or supported
box profiles, the selected converter's unproved coverage. The finite-V and
bounded supported-profile H operation bounds establish a distance to the
stored-dyadic model only. The operation does not establish equivalence or a
certified distance to the authored real set. Callers needing that guarantee
must not promote its relation enum or small residual to a validated
inclusion/coverage result.

To claim a real-model bound in a future profile:

1. Specify whether each operand and coefficient is an exact stored dyadic or
   carries a certified enclosure of authored real data. Fix the norm, output
   metric, coordinate units and empty-set convention.
2. For direct finite V inputs, verify every generated candidate against exact
   dyadic affine/pair arithmetic and publish an outward-rounded maximum error
   with matching request/source identity. **Implemented** by the current
   finite-V affine-sum path; preserve the exact deletion check.
3. For H inputs, obtain a **global two-sided** H/V conversion certificate or
   separate directed bounds. The ambient-one bounded interval profile has
   such a stored-dyadic certificate. No broader H profiles are certified;
   vertex-row residuals alone are insufficient. The bounded ambient-one and
   bounded axis-aligned-box conversion profiles now have stored-dyadic certificates,
   and propagation through the map/sum is implemented for both profiles.
4. Bind any broader `GeometryErrorBound` to a checked verifier and explicit
   assumptions, including upstream model uncertainty. The current finite-V
   bound is computed by the operation's exact dyadic post-hoc check, includes
   underflow and cancellation, and fails closed on overflow/range failure; it
   covers H conversion in the bounded ambient-one and bounded axis-aligned
   box profiles, not authored-input uncertainty. Decide whether the shared relation type needs
   a distinct bounded-numerical result; do not silently relabel the current
   result as validated.

Until those steps exist, this audit resolves the review question and leaves
the stronger real-model proof as explicit future work. No historical B04 or
other nonlinear reachability conclusion follows from GEO-02.
