# Native interfaces, revision 1.7

Revision 1.7 (GEO-07, 2026-10-16) adds `DependentSum` as a distinct
`GeometryOperation` request for factor-bearing set handles. It does not alter
`MinkowskiSum`: the latter remains the independent set sum. The new request is
defined by the operands' immutable factor IDs and constraints; adapters unable
to read those identities reject it. `check_operation_shape` checks the two
ambient dimensions, while a compatible adapter also checks ordered coordinate
labels and valid factor payloads. The registered generator adapter supports the
new request at numerical assurance. This shared source-interface change needs
integration review; no validated binary64 equality is implied.

Revision 1.6 (OBS-02, 2026-10-13) adds a trailing, default-empty
`ExecutionContext::timing` handle to the independent timing collector. Existing
aggregate initializers remain source compatible; struct layout changes, and this
is not a stable binary ABI. The [timing contract](timing-collector.md) specifies
planned IDs/parentage, scoped completion, wall interval unions, CPU scope,
unavailable metrics and disabled collection. Solver workspaces, mathematical
claims, problem/configuration identity encodings and artifact schemas do not
change. Independent integration review is required before downstream
instrumentation relies on this extension.

MODEL-03 adds the [resolved problem module](resolved-problems.md) without changing
the canonical `Problem` DTO introduced in source 1.4 and retained in source 1.5.
It publishes immutable composition, computes the
[versioned structural math/content identity](problem-identity-v1.md), and bridges
to actual configured registry admission. The authored ID is retained as a label;
the frozen compatibility DTO carries the computed ID. Data publication does not
assert feasibility or supply a production loader, planner or synthesis family.

Date: 2026-10-11. CORE-01 / issue #11; MODEL-01 / issue #15 and OPT-02 / issue #18 revisions. This revision turns the [native design sketch](../superpowers/specs/2026-10-11-cpp-core-contracts-design.md) into a compiled source contract in [contracts.hpp](../../include/csl/contracts.hpp). The [master specification](../superpowers/specs/2026-10-11-controlled-systems-master-design.md) remains the requirements authority. Integration review is required before downstream adapters depend on this revision.

This delivery contains values, coarse abstract ports and small structural guards. Revision 1.1 adds scoped outcome claims, mathematical geometry operands and reference-bound geometry evidence following integration review. It does **not** implement optimization adapters, a registry, a problem validator, numerical synthesis, geometry, family construction or a scenario loader. The [isolated probes](../../probes/core-01/CMakeLists.txt) exercise selected dependencies directly. CORE-02 owns the product build; later module tickets own implementation. The [dependency decision](../architecture/decisions/0002-native-integrations.md) records pinned versions and licensing.

Revision 1.2 replaces the authored observation aggregate with canonical maps,
constant/indexed providers and explicit source/measurement/availability schedules.
MODEL-01 implements the separate [immutable discrete model module](linear-model.md).
EXT-05 adds an [explicit continuous-affine conversion boundary](time-domains.md)
that publishes discrete transitions with a method receipt before snapshot or
problem construction; this does not change the revision 1 discrete model seam.
The preceding implementation exclusions describe the original CORE-01 delivery;
subsequent modules retain their own documented scope. No operation/evidence port
or numeric/registry interface changes in revision 1.2.

Revision 1.3 makes the canonical LinearProgram an immutable validated handle,
adds program-scoped bounds and structured numerical residuals, and gives the
optional basis port typed snapshots/coordinates. LPWorkspace owns authoritative
solve-attempt stamps. See [linear programs](linear-programs.md) for conventions,
source migration, ownership, checks and limitations. Revision 1.2 observation
maps, schedules and model semantics are unchanged. This revision implements no
production native LP adapter or certificate verifier.

Revision 1.3.1 renames the LP data result alias to
`optimization::LPDataResult<T>` so the LP and objective headers can be included
together in either order ([issue #119](https://github.com/butahlecoq/controlled-systems-lab/issues/119)).
LP result annotations using the former `optimization::Result<T>` must migrate;
callers using inferred types need no change. LP alternatives remain `T` or
`Diagnostics`, and objective `optimization::Result<T>` remains `T`, `Diagnostic`
or `OperationStopped`. No mathematical, evidence, ownership or runtime behavior
changes in this source patch.

Revision 1.5 makes ConvexProgram/QuadraticProgram immutable canonical handles,
with original Objective and explicit pure-norm-square provenance. ConvexWorkspace
owns separate authoritative solve attempts. The [convex contract](convex-programs.md)
documents the deliberate full-CSR Hessian to dense QuadraticTerminal source
migration, numerical KKT evidence and native 4096-variable profile. All source
1.4 domain, LPDataResult, LP and execution contracts remain unchanged.

Revision 1.4 adds explicit dimensions to the canonical finite catalogue and
quantifiers to initial sets. `InitialInformation` names the existing point/set
variant; `Problem::external` now holds optional known-sequence, exogenous or
adversarial input alternatives. The [immutable problem-data module](problem-data.md)
validates and retains these descriptions and optional full-history temporal CSR.
This revision preserves source 1.3.1's `optimization::LPDataResult<T>` composition
fix and all LP, evidence and solve-attempt interfaces.

Migrate `FiniteDomain{catalogue}` to `FiniteDomain{dimension,catalogue}`. Mixed
coordinates are `[continuous,discrete]`, with explicit discrete dimension d and
continuous dimension m-d. Supply `InitialSet{set,SetQuantifier::existential}` or
`universal`; omitted/unknown quantifiers are invalid at snapshot construction.
There is no inferred quantifier for legacy set-initialized requests. Replace an
old external set assignment with an explicitly selected known sequence or
`ExogenousExternalInput{T_stage_sets,quantifier}` (or a separately identified
adversarial declaration). Exogenous is a role, not a boundedness claim: yes/no/
unknown metadata survives. Those stage sets denote a Cartesian product with one
whole-sequence quantifier and no initial/external coupling; correlated or fixed-
parameter inputs cannot be migrated by silently taking their marginals. Empty
external optionals remain absent. The nominal guard and its conservative profile
are unchanged; accepted data does not promise execution or feasibility.

## Common rules

- C++20, `double`, compatible in-process toolchains. Revision 1 is source-level compatibility, not a stable C++ binary/plugin ABI. No Eigen, HiGHS, JSON or test-library type occurs in the public header.
- Problem, program, set, request, mathematical reference, module and representation IDs are different types. IDs are opaque strings; a future loader/artifact layer computes canonical identities. Changing run settings must not change mathematical problem identity. A `ProgramIdentity` combines a problem ID with the particular program/reformulation ID; multiple programs for one problem must not share that program ID.
- `LinearProgramInput` and other input aggregates are **unvalidated authored values**. The canonical `LinearProgram` is created only by `optimization::make_linear_program`, which validates and privately snapshots its authored input. Adapters must validate before numerical execution. `check_model_shape` and `check_nominal_profile` are deliberately narrow guards and do not create a `ValidatedProblem`. Passing them does not prove convexity, compactness, attainment, finite values, correct timestamps or adapter compatibility.
- Construct published snapshots using `make_shared<const T>` and retain no mutable aliases. Models, set payloads, joint relations and resource policy may be shared immutably. Asynchronously retained problem data must retain its owner. `const&` arguments are borrowed only for the duration of the call.
- In particular, `shared_ptr<const SystemModel>` still points to authored data and cannot eliminate surviving producer aliases. Use `model::snapshot` for a validated immutable executable model: it copies authored buffers into private numeric snapshots, even from rvalues. It does not validate the enclosing `Problem`.
- Workspaces are noncopyable, are returned as `unique_ptr`, and have one owner. The owner can transfer the pointer to a worker. Neither concurrent use of the same workspace nor mutable backend-global configuration is permitted without an adapter's explicit contract. Noncopyability alone cannot prevent callers from aliasing a pointer; this remains an ownership precondition.
- Expected unsupported capabilities have their own `Unsupported` alternative; mathematical infeasibility is a `MathematicalOutcome` with evidence, never inferred from rejection. Invalid authored data uses field diagnostics. Allocation failures propagate `std::bad_alloc`; invalid internal invariants are programming defects. No exception is translated into infeasibility.
- Pure guards do not need cancellation. Potentially expensive ports receive `ExecutionContext`; adapters must state cancellation granularity and native-call latency. Revision 1 supplies no timeout enforcement, scheduler or memory allocator.

## Numerical, model and problem values

`Matrix` owns a contiguous row-major `rows * cols` buffer. `Vector` owns contiguous doubles. `SparseMatrix` owns CSR arrays: `row_offsets.size()==rows+1`, first offset zero, nondecreasing offsets, final offset `values.size()==column_indices.size()`, sorted unique column indices within each row and in range. Absent bounds mean negative/positive infinity on the respective side; a present endpoint must be finite and lower must not exceed upper. Adapters reject dimensions/indices outside their native integer range before narrowing. Dense copies cost O(rows*cols); CSR copies cost O(rows+nnz). These authored values are separate from CORE-03's [retained numeric snapshots](numeric-data.md), whose contract defines layout, stride and lifetime and which MODEL-01 uses internally.

For n states, m controls and p external inputs, every `LinearStage` has A n×n, B n×m, E n×p and offset n. `check_model_shape` checks these shapes/storage without imposing invertibility. It scans coefficient descriptors, not matrix values: O(T) for LTV, O(1) for constant coefficients; diagnostic storage is O(number of failures). Constant coefficients are stored once. Zero-dimensional control/external ports are legal. A zero transition matrix is a valid model.

There are T transitions and controls, states x0 through xT, and T+1 strictly increasing physical times. LTV has exactly T stages. State sets have T+1 entries, continuous control sets T entries; restrictions must be explicit, including universal/empty/singleton sets. Known initial data has n components. Observation maps, error maps, feedthrough and before/after-decision timing are separate from dynamics and information. Absence of observations does not grant knowledge. MODEL-01 implements model/time/observation validation; MODEL-02 validates immutable domain/initial/external/temporal data, while complete-problem and strategy/information compatibility remain MODEL-03.

### Revision 1.2 observation migration

The former `Observation{state_map,control_map,error_map,offset,timing}` is replaced
by `Observation{coefficients,schedule}`. `ObservationStage` owns state, control,
**external** and error maps C/Du/Dw/F plus offset b. `ObservationCoefficients` is
one constant stage or explicit stages indexed by sample, with exactly
`schedule.size()` records. Each `ObservationSample` explicitly names
`state_stage`, `measured_at`, `available_at` and optional joint `input_stage`.
Each event is an `ObservationPoint{StageIndex,ObservationTiming}`. Channel output
and error dimensions remain fixed. Schedule order is preserved, not sorted.

This is an intentional source migration: callers must supply Dw and the schedule;
there is no inferred timestamp or lossy legacy converter. Dynamics and
`SystemModel` composition are unchanged. The source revision is not a stable ABI.

The grid supplied to `model::snapshot` is the only timestamp source. Event order
is before(k) < after(k) < before(k+1); after(k) follows transition completion at
times[k+1], whereas before(k+1) is a later causal event at the same physical time.
State x_s is released at after(s−1), except x0 at before(0); u_j/w_j are released
at after(j). Measurement cannot precede a source release, and availability
cannot precede measurement. Absent input_stage requires zero Du/Dw and empty
evaluation inputs; an explicit stage preserves the dependency even for zero
maps. At T only before(T) exists, and T=0 permits observations there without
inputs. See [the complete model contract](linear-model.md) for bounds, derived
timestamps, delayed samples, ownership, costs and unsupported clock extensions.

Model evaluation returns an owning value (including event metadata for an
observation), malformed-input `Diagnostic`, or canonical
`OperationStopped{numerical_failure,...}` for nonfinite arithmetic from valid
finite operands. It verifies neither supplied vector history nor estimation or
optimization claims. The numeric module's result alias and existing operation
ports remain unchanged.

`Problem` separates model, admissibility, objective and information from `StrategyConfiguration`. Continuous, finite and mixed domains and initial uncertainty are distinct alternatives. Empty temporal constraints are representable. Temporal CSR columns use canonical joint coordinates (below). Continuous-time metadata is representable but rejected by the nominal guard; no discretization is performed. External disturbances/feedback are later profiles.

`check_nominal_profile` checks only the first profile: discrete, known initial point, nominal open loop, no external inputs, continuous convex polyhedral stage sets, no nonempty temporal rows, numerical assurance. It reports unsupported future profiles without solving a feasibility problem. Empty sets pass profile checks and must subsequently lead to a properly evidenced infeasibility result. Empty temporal rows pass. Every inverse-dependent pipeline is rejected because revision 1 has no invertibility verification port. For a finite, shape-valid stored A with an exact zero row, the diagnostic names the first offending transition; otherwise the generic no-proof diagnostic remains. This detection does not establish invertibility for any other A. It adds O(T n²) inspection for inverse requests with T transitions and n state coordinates. Downstream algorithms may add an explicit checked invertibility prerequisite.

The three terminal forms are cᵀx+d, ½xᵀQx+qᵀx+c, and ||Lx−r||₂. Q must be symmetric PSD; rectangular L is allowed. Native adapters must independently validate/reformulate them. Constant/nonunique objectives cannot collapse to one optimizer. Objective evaluation costs O(n), O(n²) for dense Q, and O(rows(L)*n). A label does not prove PSD.

## Sets, geometry and programs

| Interface | Supported properties and output | Ownership, failure and cost |
|---|---|---|
| `SetHandle` | Set ID, dimension, extensible representation ID, three-state convex/polyhedral/bounded metadata; opaque immutable payload | Payload sharing O(1), identity/metadata strings copy O(their length); payload construction depends on representation. Null payload is invalid for an actual handle. Unknown metadata is not permission to assume a property. Empty/universal/singleton authored sets are separate alternatives. |
| `SetOperatorWorkspace` | Typed mathematical operands, separate implementation ID, requested set relation and assurance; set/support/containment results | Per-worker mutable state; `Unsupported` if operation/representation/guarantee unavailable. No silent downgrade. Output size can be exponential for projection or vertex materialization. |
| `RepresentationConverterWorkspace` | Equivalent representation only, selected output ID | Conversion preserves the mathematical set; result must have `equivalent` relation. Conversion is not approximation. Materialization may be exponential. |
| `SetApproximatorWorkspace` | Explicit inner/outer/heuristic relation, requested representation and size budget | Invalid equivalent-as-approximation requests are rejected; reported relation must meet the request. Budget is admission information until enforced by an adapter. Approximation of a reachable set is not automatically an approximation of its optimizer set. |
| `LPWorkspace` / `LPBackend` | Minimize linear objective plus offset over CSR row and variable intervals, including zero-objective feasibility; `unbounded` means unbounded below | Factory allocates independent native state. Sparse translation O(rows+cols+nnz); solver cost is backend/problem dependent. Primal may be absent on limit/failure. Mathematical status does not certify evidence. No maximize sense is accepted. |
| `ConvexWorkspace` / `ConvexBackend` | Minimize immutable linear, convex quadratic and pure residual norm originals; dense canonical Q and CSR linear constraints; `unbounded` means unbounded below | Independent port with original/squared identity and exclusive attempt history. Private native triangular conversion; numerical original-space KKT evidence, no complete family. Dense publication costs O(n²) storage/O(n³) PSD checking. General conic/SDP/nonconvex support requires a contract revision and separate capability. No maximize sense or global maximization of convex objectives is offered. |
| `BasisDiagnostics` | Optional typed snapshot, last-pivot and basis-coordinate capabilities | Owning snapshots identify the program, actual workspace and attempt. Current checks compare the independently observed workspace stamp; generic LP calls require no basis. See [the basis contract](linear-programs.md#basis-and-pivot-data). |

Set/operator metadata and evidence are declarations to be checked by registered compatible adapters; the header is not a proof system. Geometry ports return a successful set/query value, `Unsupported`, or `OperationStopped` (cancellation, limit or numerical failure, without a successful output/guarantee). A partial object cannot be returned as a successful equivalent conversion. Conversion and approximation return only set transforms; their result types cannot contain scalar/boolean query answers.

### Mathematical geometry operands and results

`GeometryOperation` is a closed variant for the initially specified operations. Algorithm IDs select implementations, never encode mathematical operands. A new mathematical operation requires a source-contract revision; a new implementation of an existing operation does not.

| Request alternative | Inputs, dimension and coordinate convention | Successful result |
|---|---|---|
| `AffineImage` | Input S in Rⁿ, row-major M in Rᵐˣⁿ, offset b in Rᵐ; ideal output {Mx+b : x in S} | Set in Rᵐ |
| `MinkowskiSum` | Ordered S and T both in Rⁿ; ideal output {s+t : s in S, t in T} | Set in Rⁿ |
| `DependentSum` | Ordered factor-bearing S and T in Rⁿ with matching coordinate labels; shared `FactorId`s denote the same bounded scalar, each input equality system applies to the joint factor assignment; ideal output is the sum of the two affine maps over that joint feasible factor domain | Set in Rⁿ; unsupported for handles without compatible factor identities |
| `Intersection` | Ordered S and T both in Rⁿ; ideal output S intersect T | Set in Rⁿ |
| `Projection` | Input S in Rⁿ and ordered zero-based coordinate indices i₀,...,iₖ₋₁ in [0,n); output order is exactly the supplied order. Repeated indices are permitted and retain equality dependencies. An optional `maximum_peak_rows` is a required H-intermediate-work cap; provider admission must enforce it or reject the request. | Set {(x[i₀],...,x[iₖ₋₁]) : x in S} in Rᵏ |
| `AffinePreimage` | Target T in Rᵐ, M in Rᵐˣⁿ, b in Rᵐ; no invertibility assumption | Set {x in Rⁿ : Mx+b in T} |
| `SupportQuery` | Input S in Rⁿ and direction d in Rⁿ, asking sup dᵀx | Finite reported value, `EmptySupport` (sup empty = −infinity), or `UnboundedSupport` (+infinity); optional attaining point |
| `ContainmentQuery` | Ordered subset candidate S and superset candidate T in the same Rⁿ, asking S subset T | Contained, not contained or undetermined; optional counterexample point |

`OperationResult`, `SupportResult` and `ContainmentResult` each carry `GeometryEvidence`. A support maximizer must have input dimension and is absent when attainment is unestablished, empty or unbounded; absence does not prove nonattainment. A containment counterexample, if present, must belong to S outside T. Scalar/boolean result type does not establish evidence strength. `required_relation` applies to set-valued requests; queries use their support/containment scope and assurance and must use `equivalent` in this field. No inner/outer scalar-query semantics are introduced. Native execution/result validation remains downstream.

### Registered native geometry capability snapshot

The closed request variant above is broader than the adapters currently registered by the native library. This snapshot records implemented admission routes, not theoretical closure of a representation. “Equivalent” describes the relation requested or returned by an adapter; it is not, by itself, proof of exact equivalence. Binary64 results can round, and validated floating-point enclosure is not implied. The rows state material evidence limits where relevant.

| Registered route | Supported requests and input class | Output/guarantee | Explicitly unsupported or deferred |
|---|---|---|---|
| `csl.geometry.generators.operations` 1.1.0 | `AffineImage` for imported zonotope or constrained-zonotope handles; `MinkowskiSum` for compatible generator handles with disjoint factor IDs; `DependentSum` for factor-bearing handles with matching ordered coordinate labels | Returns an equivalent relation from symbolic generator algebra; binary64 coefficient evaluation may round and is not enclosed | Intersection, projection, preimage and queries; Minkowski inputs with shared factor IDs; non-binary64 or validated assurance |
| `csl.geometry.generators.v-conversion` 1.0.0 | Unconstrained generator handle to finite V representation, admitted only when full cube-corner output fits the configured vertex cap | Returns an equivalent relation from the real-arithmetic cube-corner identity; binary64 corner evaluation is not enclosed; redundant corners remain and factor dependence metadata is lost in V output | Constrained generators, H output, cap overflow, non-binary64 or validated assurance |
| `csl.geometry.affine-sum` 1.0.0 | `AffineImage` and independent `MinkowskiSum` requests over compatible finite native set handles; H inputs need a selected H-to-V converter; positive-dimensional universal inputs and V inputs with nonempty rays fail execution | Reports an equivalent relation with `NumericalCheck`; residuals do not generally establish conversion coverage. A global L-infinity bound is reported only for applicable exact-dyadic cases. Output is V and execution uses selected hull-reducer/LP dependencies | `DependentSum`, intersection, projection and queries; unsupported input/materialization routes; validated assurance |
| `csl.geometry.lazy-expression` 1.0.0 | `AffineImage`, coordinate `Projection`, and independent `MinkowskiSum` over native V/empty leaves or nested lazy expressions | Immutable `csl.geometry.lazy-v` expression with an equivalent requested relation and `Unestablished` binary64 evidence; creating it does not enumerate output vertices | H leaves, dependent sums, other operations, and validated assurance |
| `csl.geometry.lazy-support` 1.0.0 | `SupportQuery` on lazy expressions using a caller-selected prepared leaf support provider; finite direction batches through `sample_support` | Finite, empty, or unbounded answers with query-scoped `Unestablished` evidence; batch coverage is explicitly `directions_only` | Complete-set or inclusion claims from samples, unsupported leaves, and validated assurance |
| `csl.geometry.lazy-materializer` 1.0.0 | Explicit `ConversionRequest` from a lazy expression to native V, with caller vertex/ray caps and stop context | Preflights row growth, checks overflow and cancellation, then returns full V output or no output; `materialize_expression` reports provider, lineage, estimates and realized rows | Implicit conversion, H output, cap overflow, validated arithmetic and partial-set publication |
| `csl.geometry.polyhedral-projection` 1.0.0 | Projection of valid imported set handles or lazy projection handles; lazy output retains the source, while H output admits H/empty/singleton/universal sources and V output admits V/empty/singleton sources | For H output, returns an equivalent relation with `Unestablished` support; binary64 equality substitution/Fourier–Motzkin elimination has no exact-arithmetic, inclusion, coverage or error-bound certificate. V/lazy output uses symbolic coordinate copying or source retention. H intermediate rows obey the stricter of provider-configured and per-request peak-row limits; a per-request cap is rejected for non-H output. V storage is checked for overflow | Unsupported source/output pairs, repeated coordinate indices and validated assurance |
| `csl.geometry.projection-materializer` 1.0.0 | Explicit conversion of a lazy projection handle to native H or V, under the same output-specific source admission; optional row limit applies to H materialization | Same evidence limits as the projection route: H support is `Unestablished`; V materialization uses symbolic coordinate copying. No partial set is returned on failure | Unsupported source/output pairs, other output representations and validated assurance |
| `csl.conversion.qhull` 1.0.0+qhull.8.0.2 | Explicit H↔V conversion for admitted native polyhedral `SetData`; H→V checks feasibility/boundedness with the selected LP backend, while V→H rejects nonempty rays | Reports an equivalent representation request with numerical residual evidence and assumptions; residual checks do not generally prove coverage. Ambient-one H→V additionally reports a global stored-dyadic interval bound | Non-binary64/validated assurance, unsupported/unbounded inputs, and cases where numerical prerequisites or residual checks fail; only optional caller dimension/row limits and Qhull/container bounds are available. Cancellation/deadlines are cooperatively polled but cannot interrupt a Qhull call mid-call; no byte budget is enforced |
| `csl.approximation.box`, `parallelotope`, `inner-box`, `inner-parallelotope` version 1 | Outer: bounded native V input with one/two axis directions or two independent 2D orientation rows; inner: declared four-corner 2D box/parallelogram against native H input | Outer H slabs and inner V hulls pass independent exact stored-binary64 vertex/ray or H-row inclusion checks; evidence records orientation, budget and representation sizes, with no finite error bound | Empty/unbounded V outer inputs, unsupported dimensions, invalid inner shape, insufficient budget, non-binary64/validated assurance, or a failed H/V inclusion check |

This is an implementation inventory, so changing registrations requires updating the row from the adapter's admission predicate and tests. Lazy projection can retain any supported imported `SetData` source, but this does not imply that each H/V materializer can materialize it; separate generator-set handles are not `SetData`. `Intersection` currently has a native H-set helper, but no `GeometryPort` registration; `AffinePreimage` and `ContainmentQuery` likewise have request types but no registered native route in this snapshot. A registration existing in the source tree also does not imply that every application composition selects it. Ellipsoidal and composite-family routes remain deferred; the bounded box/parallelotope approximation routes above provide only their stated set relations, not general optimizer-family or validated enclosure claims.

`check_operation_shape` validates affine buffer shapes/storage and offset sizes, coordinate ranges, matching binary-operation dimensions (including `DependentSum`) and support direction size. It does not evaluate transforms, query sets, check matrix coefficient finiteness, validate factor identities/payloads or establish any geometric property. Its cost is O(number of projection indices) for projection and O(1) descriptor checks for the other forms. Owning request copies cost the numerical operand size, with shared immutable payloads retained through their handles. The [contract tests](../../probes/core-01/contract_tests.cpp) express both y=x₀+2 and y=(x₁+3,x₀+4) from the same two-dimensional set, plus projections in two different coordinate orders, without backend types or hidden workspace operands.

### Geometry reference and evidence binding

Every request has `GeometryRequestIdentity`: originating problem, unique immutable request ID and reference ID for its exact ideal mathematical output. A set ID identifies immutable mathematical set content/coordinates; new content requires a new ID. A request ID binds the complete request, including operation kind, ordered set IDs, numerical operands, selected output representation/policy, relation and assurance. Changing a transform, coordinate selection or policy requires a new request ID. Equivalent ideal outputs may share a reference ID while distinct operational requests retain distinct request IDs. Reusing an ID for different content violates the contract; these guards compare assigned identities and do not implement canonical hashing or a registry.

`GeometryEvidence.reference` repeats that request identity and the ordered input set IDs, with a separate claim scope (`set_relation`, `support_value` or `containment`). Thus two projections of one problem, or reversed containment operands, cannot reuse one another's evidence. For conversion and approximation, the ideal output reference denotes the unchanged mathematical input set in the same coordinates: conversion claims equivalence to it, while approximation claims the declared inner/outer/heuristic relation to it. `OperationResult.output.id` identifies the actual returned set, and `relation` states its relation to that ideal output.

Evidence carries explicit applicable assumptions, support and an optional error bound with metric ID, nonnegative finite magnitude and units. The metric must define what is compared to the ideal output (for example a Euclidean Hausdorff bound); no generic norm or direction is silently assumed. Claim support must justify the bound under the listed assumptions. Symbolic text or numerical checks remain their declared evidence level; a certificate reference is unchecked and is not a validated bound.

`check_geometry_evidence` derives expected ordered set IDs and claim scope from the operation (or single conversion/approximation input). It rejects mismatched problem/request/reference/input identities or scope, unsupported validated assurance, and negative/nonfinite/unsupported error bounds. Cost is O(total identity lengths + input count); it copies only reference IDs, not numerical operands. Passing this guard establishes structural binding only: it does not verify a mathematical argument, estimate error, enforce the returned relation, or validate a native result.

### Outcome claims independent of objective bounds

`ProgramResult` keeps termination (completed, cancelled, resource limit, numerical failure) separate from a `ProgramOutcomeClaim`. The claim contains its `ProgramIdentity`, mathematical outcome (optimal, infeasible, unbounded, unattained infimum, undetermined), explicit `EvidenceSupport` and applicable assumptions. `SynthesisResult` instead carries a `SynthesisOutcomeClaim` bound directly to its original `ProblemId`. These records have no dependency on a primal, family or finite objective bound; infeasibility and unboundedness can carry support while all those optional fields are absent. Transferring a reformulated program's claim to the original problem requires a justified translation and its assumptions; matching a problem ID alone is insufficient.

An `Unestablished` outcome is a reported status without supporting evidence. `NumericalCheck` can record, for example, residual checks on an infeasibility dual witness or an improving feasible ray under stated assumptions; small residuals do not certify the outcome. `SymbolicArgument` can cite a contradiction or unbounded-ray argument under explicit assumptions, but the text itself is not machine checked. `CertificateReference` stores a proposed certificate/verifier for future checking and cannot be labelled validated. Numerical infeasibility, symbolic support and an unsupported request remain distinguishable without manufacturing objective bounds. The same support alternatives apply to optimality and nonattainment, with evidence specific to the claimed outcome.

`check_outcome_evidence` rejects a different problem/program identity and every validated request in this revision; it allows explicitly unestablished support. Cost is O(identity length), with no solve or evidence verification. All current LP, convex and synthesis objectives have minimization sense. Program bounds use `ProgramBoundEvidence` with the full `ProgramIdentity` (the exact normalized objective and program), support and assumptions; synthesis bounds retain `ClaimEvidence` scoped to the original `ProblemId` and exact resolved objective. A finite lower or upper bound respectively bounds the infimum from below or above, including the objective offset. Each bound is independently supported. `unbounded` means unbounded below. There is no maximize API: a caller starting from source maximization must form `g=-f`, including its offset, before program creation, then explicitly translate bound direction and retain source/normalized identities and evidence. Contradiction checks run only when minimization direction and identity are authoritative; ambiguous direction leaves the outcome undetermined and preserves independently supported bounds. There is no implicit evidence conversion. Native diagnostics remain available. Impossible adapter combinations, NaN bounds and results claiming proved optimality without suitable evidence must be rejected in downstream result validation. A nonzero native status must never be quietly converted to an empty feasible set.

## Joint family and claim-specific evidence

Canonical joint order is `[x0, ..., xT, u0, ..., u(T-1)]`: state block k starts at k*n, control block k at (T+1)*n+k*m. `JointCoordinates` carries T and dimensions; lifted payloads must retain an exact decoding map to this order, including all cross-stage dependencies. External coordinates are excluded from this nominal relation. Overflow and coordinate-map validity are adapter input checks. A `JointRelationPayload` cannot be replaced with stage marginals or a witness vector.

`FamilyRequest` records the resolved objective identity, profile, requested target, numerical solve policy, assurance, representation and optional materialization limit. `OptimalFamily` has private construction and read-only accessors. The single `FamilyPublisher::publish` gate checks binding and returns either an immutable family value or diagnostics. Its product is exactly one typed outcome: `CompleteOptimalFamily`, `PartialOptimalFamily` or `CandidateFamily`; the target is derived from the variant. A complete family is Z* = {z ∈ F : φ(xT)=v*}; all terminal minimizers and consistent histories must be retained. For a two-step integrator with controls in [0,1] and cost (x2−1)², the control relation is u0+u1=1: two selected endpoints and the Cartesian product [0,1]² are both inadequate replacements.

`check_family_request` requires the effective objective to match the nonempty resolved problem identity, a nonempty profile, and finite nonnegative absolute and relative tolerances. Registry preparation, direct `StrategyPort` execution, and family publication share this check. Invalid requests reject before workspace execution; zero tolerances remain a caller policy choice. This validates request structure and does not choose coverage thresholds or establish evidence validity.

`WitnessBatch` is a separate, nonconvertible type. It cannot itself establish completeness. `SelectorPort` retains the source `FamilyIdentity` in the returned batch and rejects a conflicting identity or witness problem. `WitnessSelectorWorkspace` returns owning T+1 states and T controls per witness, original objective, requested count, seed and search diagnostics; fewer distinct witnesses do not prove a singleton. Selection cost depends on relation and query and may require further optimization. Trajectory verification is a separate downstream module, not a reuse of a solver feasibility flag.

`EvidenceSupport` distinguishes unestablished evidence, numerical residual checks with tolerances/verifier, symbolic argument with assumptions, and **unchecked** certificate references. Symbolic argument text is provenance, not a machine-checked proof. `CompleteOptimalFamily` structurally requires a joint relation, optimum evidence, completeness evidence and assurance. Completeness evidence binds the resolved problem, full effective family request, ordered coordinates, strategy ID/version and ordered transformation lineage. Its `CompletenessSupport` variant represents `Unestablished`, `SymbolicArgument`, `CertificateReference`, and `NumericalCheck` alongside numerical coverage, validated coverage, and registered completeness evidence. All seven alternatives are untrusted claims at construction and decoding. The shared strategy boundary accepts complete-family publication only when support is the matching selected `RegisteredCompletenessEvidence` and its compiled verifier accepts the claim; the four newly representable forms cannot pass that gate. Numerical and validated coverage have distinct types, but no reviewed generic coverage verifier or validated arithmetic profile exists yet. Generic complete publication therefore fails closed; the exact T-S01 live-capability exception and its wire limits are documented below. Partial publication requires a stated scope and evidence that every retained history is optimal. No such verifier is reviewed yet, so partial publication also fails closed even if a strategy supplies symbolic text or a certificate reference. Candidate publication declares outer, feasible inner, or heuristic meaning. Its feasibility is separately typed as unknown, supported for the whole relation, or supported for a named full-history witness; an outer enclosure with one feasible witness does not claim every enclosed history feasible. Passing the candidate checks establishes structural consistency, not mathematical truth.

The dedicated `csl.synthesis.ts01-analytic` registration is a narrow exception to the general complete-family refusal: it accepts only the two-step scalar discrete integrator with exact known initial state 0, A=B=1, zero offsets and external map, independent closed controls `[0,1]`, no extra constraints, and the exact squared terminal objective `(x2-1)^2`. It constructs the exact joint relation and issues a typed live capability bound to the immutable resolved problem, effective request, coordinates, strategy/version and relation. The result is **numerically assured**, not validated by a general-purpose checker; generic strategies and generic numerical, symbolic or certificate-reference evidence remain unable to publish complete families. This capability is an in-memory proof object, not a portable certificate. Run-statistics v3 cannot encode it and `encode_run` returns `unsupported`; serialization refusal follows the closed wire contract and makes no mathematical claim about the live result. Decoding never recreates trusted proof capability from text. Issue [#202](https://github.com/butahlecoq/controlled-systems-lab/issues/202) tracks the future generic, versioned verifier seam.

`SynthesisResult` keeps execution termination apart from its mathematical outcome. It may retain independently supported `FeasibleIncumbent` records, objective bounds, timings and a permitted candidate family after cancellation, deadline, resource or numerical stops. `SynthesisWorkspace::solve` returns a `SynthesisResult`; only the shared port can return top-level `Unsupported` before solving. A real late generated-request rejection uses `operation_rejected` with `ScopedRequestRejection`: exact request/provenance, provider diagnostics, completed lineage and retained-evidence scope. The shared `StrategyPort` validates claims before returning them. A contradictory result uses `contract_rejected` with `ContractValidationFailure`, preserves independently valid evidence and the original stop record, and never manufactures provider provenance. A relaxation φ ≤ incumbent+tolerance remains a candidate. Native optimal status, low residuals or agreement between backends do not promote it to full Z*.

`check_synthesis_result` with a `FamilyIdentity` compares the complete identity exactly, including ordered lineage (an empty vector means exactly zero transformation steps). `SynthesisIdentityExpectation` is used when a prepared strategy checks a result before its generated transformations are known; its optional lineage is `nullopt` in that case, while a concrete vector requests exact ordered comparison. This distinction lets caller-supplied identities detect altered or omitted steps without treating an unknown pre-solve lineage as an empty chain.

If a workspace reports infeasibility, unboundedness or an unattained infimum alongside a valid candidate family, the synthesis `StrategyPort` retains the candidate and changes the mathematical outcome to `undetermined` in its contract-rejected result. A claimed infeasibility with an independently supported feasible incumbent is handled the same way. After authoritative minimization direction and objective identity are established, supported infeasibility conflicts with a supported finite upper bound, and unbounded-below conflicts with a supported finite lower bound. On contradiction, this synthesis boundary sanitizes the outcome while retaining every independent consistent bound and candidate; ambiguous direction or identity cannot trigger a direction-based contradiction. The original contradiction remains in the contract diagnostics; artifact publication rejects any unsanitized combination. This is distinct from the LP `check_program_result` validator, which returns diagnostics for an authoritative contradiction and does not sanitize the result.

The port requires each retained incumbent to have supported feasibility, finite T+1 state and T control histories in the resolved coordinate dimensions, and a finite objective. It rejects a supported lower objective bound greater than any supported feasible incumbent objective; this comparison uses the bound as stated, without inventing a rounding margin. A finite number with `Unestablished` support is not retained as an objective bound. `SymbolicArgument` records the stated argument and assumptions but is not itself a machine-checked proof; numerical support likewise remains scoped to its numerical policy. Rejected malformed histories and unsupported or contradictory bounds are removed while valid evidence survives.

Scoped provider stops and rejections require a nonempty generated request, port and requested module. A supplied requested version must be nonempty. Actual module and version are either both absent (for example, an unknown-provider admission rejection), or both present and nonempty. Malformed provenance yields contract rejection while the original provider facts, supported candidate, bounds, incumbents and timings remain available; the boundary does not infer or repair provider identities.

## Execution, configuration and caller example

`StrategyConfiguration` has independent IDs for strategy, LP, convex method, hull policy, geometry operator, converter, approximation policy, selector and representation. The registry resolves selected methods and checks their declared capability and dependency requirements; individual strategies remain responsible for the mathematical profiles they offer.

`SynthesisStrategy` receives an immutable `ResolvedProblem` and effective `FamilyRequest` and produces an exclusive workspace. The prepared request owns both through `StrategyPort`. The execution numerical policy must equal `FamilyRequest.numerical` before the workspace runs. Cancellation and a lack of family do not imply infeasibility. Family construction/query costs may grow exponentially; the contract promises no polynomial runtime.

The boundary validates every declared transformation step for nonempty request,
input/output set, module and version identities, and rejects duplicate request
IDs. A complete claim must repeat the whole ordered lineage in its completeness
binding. The prepared request cannot predict transformations generated during
solving, so this structural check does not verify that each claimed step was
executed; an independent runtime ledger/verifier is needed before completeness
can be published. Complete and partial publication remain closed meanwhile.

One immutable `ResourcePolicy` covers outer workers and native threads. `check_resources` requires positive counts and `outer_workers * threads_per_worker <= total_threads`, with division avoiding overflow. Cost O(1). It is admission validation; backend adapters must actually apply the limit and account for BLAS/global thread pools. `memory_bytes` is an accounting request until a backend advertises enforcement. `TimingSpan` stores parent and absolute run-relative start/end offsets; overlapping/nested durations must not be summed as end-to-end latency. Full versioned provenance/statistics artifacts belong to OBS-01.

The [compiled caller example](../../probes/core-01/caller_example.cpp) resolves one problem and checks capability for reachability/backward-recovery and direct joint-trajectory configurations. Both adapters are explicitly unsupported contract fixtures; it creates separate exclusive workspaces but does not invoke them after capability rejection. No optimization or family is manufactured. The example uses unrestricted stage sets, so it is not the bounded two-step acceptance experiment above. Native dependency probes additionally exercise separate HiGHS objects, without claiming race/sanitizer coverage.

## Acceptance and remaining work

[Contract tests](../../probes/core-01/contract_tests.cpp) supply executable portions of T-M03 and T-V02. They cover shape/singular representation, unsupported profiles, temporal-empty handling, evidence identity, numerical/validated separation, incomplete relation coverage and resource admission. Revision 1.1 adds scoped outcome evidence without bounds/families, neutral geometry operand shapes, query scopes, conversion/approximation reference binding and error-bound metadata. Type checks prevent copying workspace objects or converting witness batches to families. All expensive module implementations and their full validation remain downstream. The isolated [probe README](../../probes/core-01/README.md) contains exact commands and observed platform results.

Revision 1.2 adds MODEL-01's immutable affine LTI/LTV evaluation and explicit
observation schedule, with literal dynamics/feedthrough, causal-clock, rejection
and lifetime tests plus an installed client. It does not close admissibility or
the broader architecture obligations. Any change to this contract must revise
this document and affected tests before integration.

## Portable scenario statistics

The additive `CSL::artifacts` module owns the [run-statistics contract](run-statistics.md),
configuration identity and closed portable scenario wire format. Public source
revision 1.5 and canonical mathematical DTO authority remain unchanged. Artifact
publication validates ownership and data consistency; it grants no solver or
checked-verifier authority.

### T-S01 oriented witness queries (SYN-05 scoped slice)

`CSL::witness_selector` registers `csl.selector.ts01-directions` through the existing
`SelectorPort`, with a frozen injected `PreparedProvider<LPPort>`. It accepts only
registry-verified complete T-S01 `ExactJointRelation` payloads in the H representation,
including those produced by Strategy A or B. Each finite two-coordinate direction
is **minimized** in control order `(u0,u1)`; `(1,-1)` returns `(0,1)` and `(-1,1)`
returns `(1,0)`. State histories are retained in canonical order and original cost
is zero. This is a numerical query of the existing complete relation, not new
completeness evidence or independent trajectory verification.

`WitnessBatch` retains requested directions, distinctness tolerance, seed, selector
identity and source family identity. `requested` asks for distinct histories;
`returned_count()` is the raw successful observation cardinality (repeats retained).
`distinct_count()` scans observations in order, accepting a representative only
when no earlier accepted representative has matching state/control time and coordinate
shapes and maximum absolute difference over the full joint history at most the
specified tolerance. This closeness relation is nontransitive and the greedy count
can depend on order. State-only changes and differing shapes remain distinct.
Directions are attempted in request order until enough distinct histories are found
or directions are exhausted. Exhaustion is a search shortfall and never proves
uniqueness; seed is provenance only and no random or uniform sampling claim is made.

Cancellation/deadlines are checked before admission and each LP query; the immutable
resource/numerical policy is forwarded to the injected provider. Native stops retain
earlier observations and leave family target/evidence unchanged. Memory policy retains
the existing accounting-only contract; allocation failure returns a query resource
limit. Unsupported families/directions and known provider capabilities reject before
solving. Generic representations, singleton proofs and validated queries are outside
this slice.

## Directional ellipsoid representation

The immutable native `csl.ellipsoid.directional2d` payload stores a planar
center, independent orientation rows, projected bounds and radii. Import
validates its `SetHandle` envelope. The approximation policy admits an outer
relation from a bounded native planar V set only after exact stored-binary64
vertex checks. A finite family preserves separate reviewed members and means
intersection for outer members or union for inner members. The complete public
contract and supported input class are in
[ellipsoidal approximation](ellipsoidal-approximation.md).
