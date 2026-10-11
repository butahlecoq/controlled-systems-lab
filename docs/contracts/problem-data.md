# Immutable problem domains, constraints and initial information

MODEL-02 / issue #20 supplies `<csl/problem/domains.hpp>`,
`<csl/problem/constraints.hpp>` and `<csl/problem/initial_information.hpp>`
through the installed `CSL::problem` target. Source revision 1.4 retains the
canonical request DTOs in `contracts.hpp`; the immutable descriptions returned
by this module use those same types. There is no competing request schema.
`CSL::problem` composes the existing model, set and numeric modules.

## Construction and ownership

The four factories `snapshot_controls`, `snapshot_initial`, `snapshot_external`
and `snapshot_constraints` consume authored data and an immutable
`model::LinearSystem`. Dimensions and T come only from that validated model.
They return `problem::Result<T>`, a variant of the immutable handle and one
`Diagnostic`. They do not validate a complete `Problem`, select a strategy,
evaluate observations, solve feasibility or establish evidence.

Every handle has private construction, no default invalid state and ordinary
copy construction/assignment. Copies and rvalue construction/assignment retain
immutable shared storage; the source remains valid. No mutable producer storage
is adopted, even when the caller supplies `std::move`. Authored vectors,
catalogue entries, singleton points, intervals, envelopes and strings are copied.
Native set payloads share their existing immutable storage.

`ControlDomains::description()`, `InitialData::description()` and
`ExternalData::description()` return aliasing const owners. `Constraints::states()`
does the same for the state-set list. Keep the returned owner alive while borrowing
its contents; it can outlive the original handle. `Constraints::temporal()` returns
an optional `TemporalData` containing a retaining numeric matrix view and a const
owner for the row intervals. Those owners also survive the outer handle. Numeric
descriptor spans retain the numeric module's borrow-lifetime rules.

Generic `SetHandle` inputs are accepted only after `sets::from_handle` verifies
the private native payload and its complete envelope. Null/foreign payloads return
`unsupported`; corrupted native envelopes return `invalid_input`. A const pointer
to an arbitrary foreign payload is not an ownership guarantee. Accepted canonical
descriptions preserve the elementary/set-handle alternative without normalization.
Native coordinates, IDs, labels and supplied evidence remain retained unchanged.

## Control and state domains

For T transitions there are T control stages and T+1 state stages. A continuous
domain must explicitly contain T sets in R^m, and state constraints T+1 sets in
R^n. Unrestricted means explicit `UniversalSet`, not a missing list. Empty,
singleton, lower-dimensional, unbounded and unknown-boundedness sets are legal
data. The module does not infer feasibility or boundedness from successful input
construction.

`FiniteDomain{dimension,catalogue}` contains one ordered, stage-invariant catalogue
reused at every control stage. Every action is a finite vector of the declared
dimension, equal to m for a pure finite domain. Empty catalogues and duplicate
actions are retained. Catalogue index preserves authored action identity. No
sorting, hull, relaxation or deduplication occurs.

`MixedDomain` is the product of its stagewise continuous set and finite catalogue,
in coordinate order `[continuous, discrete]`. For discrete dimension d, require
d <= m and continuous dimension m-d. Empty catalogues still have explicit d.
Mixed identity survives d=0 or m-d=0. Neither finite nor mixed actions imply
mode/guard/reset or switching dynamics; those require a separate future model.

Zero-dimensional ports are legal. In R^0, `UniversalSet{0}` and `Singleton{{}}`
represent the unique empty vector but retain different tags. `EmptySet{0}` is
different from both. A dimension-0 catalogue with one empty vector is different
from an empty catalogue. At T=0 there is one state and no control stage; even an
empty finite catalogue restricts no control choice. No infeasibility is inferred.

## Initial and external information

`InitialInformation` aliases the existing KnownInitial/InitialSet variant.
Known points must have n finite coordinates. Initial sets must have dimension n
and an explicit existential or universal `SetQuantifier`. Missing/unknown tags
are invalid; a singleton InitialSet is never converted into KnownInitial. Missing,
partial or full observations do not change this declaration or grant knowledge.

An absent external optional means no external channel and requires p=0.
`KnownExternalSequence` has exactly T finite p-dimensional vectors.
`ExogenousExternalInput` and `AdversarialExternalInput` have exactly T sets of
dimension p and an explicit whole-sequence quantifier. A present dimension-0
alternative remains present, and positive-dimensional zero forcing stays a
different input description from an absent port.

Exogenous names a role, not a boundedness guarantee. Native boundedness
yes/no/unknown is retained; H data with unknown boundedness and universal R^p
are accepted without promotion or bounds computation. Adversarial inputs remain
distinct from exogenous uncertainty. Their nonempty `semantics_reference` is a
deferred reference to objective/policy/information semantics, not a resolved or
verified executable game. It cannot change the admissible product below.

The T stage sets mean exactly W=W0 x ... x W(T-1), in ordered blocks
`[w0,...,w(T-1)]`. Every cross-stage combination is admissible. The quantifier
ranges once over that whole sequence, not over one sampled history. At T=0 the
empty product contains the unique empty sequence; it is not empty. A present
set-sequence still requires a quantifier then. An empty factor at T>0 makes the
product empty, without a construction-time feasibility or quantified-truth claim.

Initial and external admissibility have the uncoupled product X0 x W. Known
points/sequences contribute their singletons. Reusing a stage set or SetId does
not correlate disturbances. Correlated histories, a fixed uncertain parameter
reused across stages and initial/external coupling are unrepresented by this
schema. Callers/loaders must reject those requests as unsupported before a lossy
conversion to marginals, or use a future separately specified joint type. These
factories cannot detect dependence that a caller already erased. Product sets
do not imply probabilistic independence. Feedback/game quantifier alternation,
policy measurability and full strategy validation are not established here.

For example, two independent factors {-1,1} give w0-w1 in {-2,0,2}; a fixed
parameter w0=w1 gives only 0. Native V endpoints -1,1 represent the interval
[-1,1], whose product has difference interval [-2,2], not the finite image.
The tests enumerate retained endpoints as an ownership/coordinate oracle,
without claiming native nonconvex-set or correlated-uncertainty execution.

## Full-history temporal relation

`snapshot_constraints` accepts the state list and optional canonical
`TemporalConstraints`. CSR columns are `[x0,...,xT,u0,...,u(T-1)]`, width
`(T+1)*n+T*m`. Checked size arithmetic precedes copying or index calculations.
No external coordinate or uncertainty-dependence relation is encoded there.
`state_offset(k)` returns k*n for k in [0,T]; `control_offset(k)` returns
(T+1)*n+k*m for k in [0,T). Out-of-range stages are diagnostics, including every
control query at T=0. Zero-width blocks can share offsets while their stage
identities remain separate.

The numeric module validates and snapshots CSR storage, finite values and column
ordering. Supply one `Interval` per row; every present endpoint must be finite,
with lower <= upper. Equal endpoints encode equality; missing lower/upper means
unbounded in that direction. Both absent is an explicitly retained vacuous row.
Redundant, zero and mutually contradictory rows remain authored data. Bounds and
CSR are retained in their original order without pruning, projection or lifting.

Absence differs from a present zero-row relation. A zero-row relation still has
the full joint column width and CSR offsets `{0}`. No rate bound, prior control
or adjacent-only interpretation is introduced. In the test relation with T=3,
n=m=1, the rows x3-2*x0+u0=7 and u2-u0 in [-1/4,1/4] retain nonadjacent history.
The literal vectors `[1,0,0,8,1,0,1.25]` and `[1,0,0,8,1,0,0.5]` map to
`[7,0.25]` and `[7,-0.5]` respectively. These are data-consumption checks, not
a temporal solver or exact-lift claim.

## Diagnostics, costs and supported scope

Validation reports the first failure in deterministic order: controls check
variant dimensions/catalogue before continuous stages for mixed data; initial
sets check quantifier then set; external data checks absent-port compatibility,
quantifier, count and stage data, then adversarial reference. Constraints check
coordinate width, state count/data, temporal width/CSR, interval count/endpoints.
Native set-envelope validation precedes expected model-dimension comparison.

Fields use `problem.controls`, `problem.states`, `problem.initial`,
`problem.external` and `problem.temporal` prefixes, with zero-based `[i]` for
authored elements. Wrong cardinality uses `.stages`, dimensions `.dimension`,
nonfinite points `.point`, invalid catalogue actions `.catalogue[i]`, quantifiers
`.quantifier`, temporal CSR/width `.shape` and intervals `.bounds`/`.bounds[i]`.
Overflow is `problem.temporal.coordinates`; bad indices are
`problem.state_stage` or `problem.control_stage`. Set imports append their
original `sets.handle.*` field and preserve diagnostic code/explanation.

Construction takes linear time in copied DTO vector/text and CSR input size;
sharing native set coefficients does not scan or copy those coefficients.
Handle copies, retained-description getters and offsets take O(1). Allocation
failure follows standard C++ exceptions. This is an algorithmic cost statement,
not a measured performance result. No cancellation/workspace is needed for this
data layer.

The unchanged nominal capability guard requires known point, nominal open loop,
continuous convex polyhedral stages, no external alternative and no nonempty
temporal rows. It rejects present zero forcing conservatively. Unsupported
profiles remain distinct from input errors or infeasibility. Model construction
still accepts singular discrete dynamics and rejects continuous-time execution
without discretization. Complete-problem/strategy validation belongs to MODEL-03;
finite/hybrid, temporal, robust and observation-control execution remain separate
tickets. No geometric operation, evidence promotion or family completeness is
provided here.

The module tests cover these input/ownership distinctions through public
factories; the installed client links only `CSL::problem` through the installed
prefix. Both neutral public-header include orders include all three new headers
and retain their numeric/contracts-only link boundary.
