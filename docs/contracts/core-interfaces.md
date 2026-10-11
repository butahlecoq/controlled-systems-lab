# Native interfaces, revision 1.2

Date: 2026-10-11. CORE-01 / issue #11; MODEL-01 / issue #15 revision. This revision turns the [native design sketch](../superpowers/specs/2026-10-11-cpp-core-contracts-design.md) into a compiled source contract in [contracts.hpp](../../include/csl/contracts.hpp). The [master specification](../superpowers/specs/2026-10-11-controlled-systems-master-design.md) remains the requirements authority. Integration review is required before downstream adapters depend on this revision.

This delivery contains values, coarse abstract ports and small structural guards. Revision 1.1 adds scoped outcome claims, mathematical geometry operands and reference-bound geometry evidence following integration review. It does **not** implement optimization adapters, a registry, a problem validator, numerical synthesis, geometry, family construction or a scenario loader. The [isolated probes](../../probes/core-01/CMakeLists.txt) exercise selected dependencies directly. CORE-02 owns the product build; later module tickets own implementation. The [dependency decision](../architecture/decisions/0002-native-integrations.md) records pinned versions and licensing.

Revision 1.2 replaces the authored observation aggregate with canonical maps,
constant/indexed providers and explicit source/measurement/availability schedules.
MODEL-01 implements the separate [immutable discrete model module](linear-model.md).
The preceding implementation exclusions describe the original CORE-01 delivery;
subsequent modules retain their own documented scope. No operation/evidence port
or numeric/registry interface changes in revision 1.2.

## Common rules

- C++20, `double`, compatible in-process toolchains. Revision 1 is source-level compatibility, not a stable C++ binary/plugin ABI. No Eigen, HiGHS, JSON or test-library type occurs in the public header.
- Problem, program, set, request, mathematical reference, module and representation IDs are different types. IDs are opaque strings; a future loader/artifact layer computes canonical identities. Changing run settings must not change mathematical problem identity. A `ProgramIdentity` combines a problem ID with the particular program/reformulation ID; multiple programs for one problem must not share that program ID.
- Input aggregates are **unvalidated authored values**. Adapters must validate before numerical execution. `check_model_shape` and `check_nominal_profile` are deliberately narrow guards and do not create a `ValidatedProblem`. Passing them does not prove convexity, compactness, attainment, finite values, correct timestamps or adapter compatibility.
- Construct published snapshots using `make_shared<const T>` and retain no mutable aliases. Models, set payloads, joint relations and resource policy may be shared immutably. Asynchronously retained problem data must retain its owner. `const&` arguments are borrowed only for the duration of the call.
- In particular, `shared_ptr<const SystemModel>` still points to authored data and cannot eliminate surviving producer aliases. Use `model::snapshot` for a validated immutable executable model: it copies authored buffers into private numeric snapshots, even from rvalues. It does not validate the enclosing `Problem`.
- Workspaces are noncopyable, are returned as `unique_ptr`, and have one owner. The owner can transfer the pointer to a worker. Neither concurrent use of the same workspace nor mutable backend-global configuration is permitted without an adapter's explicit contract. Noncopyability alone cannot prevent callers from aliasing a pointer; this remains an ownership precondition.
- Expected unsupported capabilities have their own `Unsupported` alternative; mathematical infeasibility is a `MathematicalOutcome` with evidence, never inferred from rejection. Invalid authored data uses field diagnostics. Allocation failures propagate `std::bad_alloc`; invalid internal invariants are programming defects. No exception is translated into infeasibility.
- Pure guards do not need cancellation. Potentially expensive ports receive `ExecutionContext`; adapters must state cancellation granularity and native-call latency. Revision 1 supplies no timeout enforcement, scheduler or memory allocator.

## Numerical, model and problem values

`Matrix` owns a contiguous row-major `rows * cols` buffer. `Vector` owns contiguous doubles. `SparseMatrix` owns CSR arrays: `row_offsets.size()==rows+1`, first offset zero, nondecreasing offsets, final offset `values.size()==column_indices.size()`, sorted unique column indices within each row and in range. Absent bounds mean negative/positive infinity on the respective side; a present endpoint must be finite and lower must not exceed upper. Adapters reject dimensions/indices outside their native integer range before narrowing. Dense copies cost O(rows*cols); CSR copies cost O(rows+nnz). These authored values are separate from CORE-03's [retained numeric snapshots](numeric-data.md), whose contract defines layout, stride and lifetime and which MODEL-01 uses internally.

For n states, m controls and p external inputs, every `LinearStage` has A n×n, B n×m, E n×p and offset n. `check_model_shape` checks these shapes/storage without imposing invertibility. It scans coefficient descriptors, not matrix values: O(T) for LTV, O(1) for constant coefficients; diagnostic storage is O(number of failures). Constant coefficients are stored once. Zero-dimensional control/external ports are legal. A zero transition matrix is a valid model.

There are T transitions and controls, states x0 through xT, and T+1 strictly increasing physical times. LTV has exactly T stages. State sets have T+1 entries, continuous control sets T entries; restrictions must be explicit, including universal/empty/singleton sets. Known initial data has n components. Observation maps, error maps, feedthrough and before/after-decision timing are separate from dynamics and information. Absence of observations does not grant knowledge. MODEL-01 implements model/time/observation validation; problem domains and information-pattern validation remain MODEL-02/03.

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

`check_nominal_profile` checks only the first profile: discrete, known initial point, nominal open loop, no external inputs, continuous convex polyhedral stage sets, no nonempty temporal rows, numerical assurance. It reports unsupported future profiles in O(number of stage sets); it does not solve a feasibility problem. Empty sets pass profile checks and must subsequently lead to a properly evidenced infeasibility result. Empty temporal rows pass. Every inverse-dependent pipeline is rejected because revision 1 has no invertibility verification port; this conservative outcome includes singular dynamics without restricting model representation. Downstream algorithms may add an explicit checked invertibility prerequisite.

The three terminal forms are cᵀx+d, ½xᵀQx+qᵀx+c, and ||Lx−r||₂. Q must be symmetric PSD; rectangular L is allowed. Native adapters must independently validate/reformulate them. Constant/nonunique objectives cannot collapse to one optimizer. Objective evaluation costs O(n), O(n²) for dense Q, and O(rows(L)*n). A label does not prove PSD.

## Sets, geometry and programs

| Interface | Supported properties and output | Ownership, failure and cost |
|---|---|---|
| `SetHandle` | Set ID, dimension, extensible representation ID, three-state convex/polyhedral/bounded metadata; opaque immutable payload | Payload sharing O(1), identity/metadata strings copy O(their length); payload construction depends on representation. Null payload is invalid for an actual handle. Unknown metadata is not permission to assume a property. Empty/universal/singleton authored sets are separate alternatives. |
| `SetOperatorWorkspace` | Typed mathematical operands, separate implementation ID, requested set relation and assurance; set/support/containment results | Per-worker mutable state; `Unsupported` if operation/representation/guarantee unavailable. No silent downgrade. Output size can be exponential for projection or vertex materialization. |
| `RepresentationConverterWorkspace` | Equivalent representation only, selected output ID | Conversion preserves the mathematical set; result must have `equivalent` relation. Conversion is not approximation. Materialization may be exponential. |
| `SetApproximatorWorkspace` | Explicit inner/outer/heuristic relation, requested representation and size budget | Invalid equivalent-as-approximation requests are rejected; reported relation must meet the request. Budget is admission information until enforced by an adapter. Approximation of a reachable set is not automatically an approximation of its optimizer set. |
| `LPWorkspace` / `LPBackend` | Minimize linear objective plus offset over CSR row and variable intervals, including zero-objective feasibility | Factory allocates independent native state. Sparse translation O(rows+cols+nnz); solver cost is backend/problem dependent. Primal may be absent on limit/failure. Mathematical status does not certify evidence. |
| `ConvexWorkspace` / `ConvexBackend` | Revision 1 convex quadratic programs with full symmetric CSR Q and the same linear constraints | Independent port even when supplied by the same native library. Translation includes triangular storage conversion. General conic/SDP/nonconvex support requires a contract revision and separate capability. |
| `BasisDiagnostics` | Optional secondary interface | Generic LP calls never require a basis. A specialized phase-I hull policy must resolve this capability before use; a generic feasibility policy is a different algorithm. |

Set/operator metadata and evidence are declarations to be checked by registered compatible adapters; the header is not a proof system. Geometry ports return a successful set/query value, `Unsupported`, or `OperationStopped` (cancellation, limit or numerical failure, without a successful output/guarantee). A partial object cannot be returned as a successful equivalent conversion. Conversion and approximation return only set transforms; their result types cannot contain scalar/boolean query answers.

### Mathematical geometry operands and results

`GeometryOperation` is a closed variant for the initially specified operations. Algorithm IDs select implementations, never encode mathematical operands. A new mathematical operation requires a source-contract revision; a new implementation of an existing operation does not.

| Request alternative | Inputs, dimension and coordinate convention | Successful result |
|---|---|---|
| `AffineImage` | Input S in Rⁿ, row-major M in Rᵐˣⁿ, offset b in Rᵐ; ideal output {Mx+b : x in S} | Set in Rᵐ |
| `MinkowskiSum` | Ordered S and T both in Rⁿ; ideal output {s+t : s in S, t in T} | Set in Rⁿ |
| `Intersection` | Ordered S and T both in Rⁿ; ideal output S intersect T | Set in Rⁿ |
| `Projection` | Input S in Rⁿ and ordered zero-based coordinate indices i₀,...,iₖ₋₁ in [0,n); output order is exactly the supplied order. Repeated indices are permitted and retain equality dependencies. | Set {(x[i₀],...,x[iₖ₋₁]) : x in S} in Rᵏ |
| `AffinePreimage` | Target T in Rᵐ, M in Rᵐˣⁿ, b in Rᵐ; no invertibility assumption | Set {x in Rⁿ : Mx+b in T} |
| `SupportQuery` | Input S in Rⁿ and direction d in Rⁿ, asking sup dᵀx | Finite reported value, `EmptySupport` (sup empty = −infinity), or `UnboundedSupport` (+infinity); optional attaining point |
| `ContainmentQuery` | Ordered subset candidate S and superset candidate T in the same Rⁿ, asking S subset T | Contained, not contained or undetermined; optional counterexample point |

`OperationResult`, `SupportResult` and `ContainmentResult` each carry `GeometryEvidence`. A support maximizer must have input dimension and is absent when attainment is unestablished, empty or unbounded; absence does not prove nonattainment. A containment counterexample, if present, must belong to S outside T. Scalar/boolean result type does not establish evidence strength. `required_relation` applies to set-valued requests; queries use their support/containment scope and assurance and must use `equivalent` in this field. No inner/outer scalar-query semantics are introduced. Native execution/result validation remains downstream.

`check_operation_shape` validates affine buffer shapes/storage and offset sizes, coordinate ranges, matching binary-operation dimensions and support direction size. It does not evaluate transforms, query sets, check matrix coefficient finiteness, validate payloads or establish any geometric property. Its cost is O(number of projection indices) for projection and O(1) descriptor checks for the other forms. Owning request copies cost the numerical operand size, with shared immutable payloads retained through their handles. The [contract tests](../../probes/core-01/contract_tests.cpp) express both y=x₀+2 and y=(x₁+3,x₀+4) from the same two-dimensional set, plus projections in two different coordinate orders, without backend types or hidden workspace operands.

### Geometry reference and evidence binding

Every request has `GeometryRequestIdentity`: originating problem, unique immutable request ID and reference ID for its exact ideal mathematical output. A set ID identifies immutable mathematical set content/coordinates; new content requires a new ID. A request ID binds the complete request, including operation kind, ordered set IDs, numerical operands, selected output representation/policy, relation and assurance. Changing a transform, coordinate selection or policy requires a new request ID. Equivalent ideal outputs may share a reference ID while distinct operational requests retain distinct request IDs. Reusing an ID for different content violates the contract; these guards compare assigned identities and do not implement canonical hashing or a registry.

`GeometryEvidence.reference` repeats that request identity and the ordered input set IDs, with a separate claim scope (`set_relation`, `support_value` or `containment`). Thus two projections of one problem, or reversed containment operands, cannot reuse one another's evidence. For conversion and approximation, the ideal output reference denotes the unchanged mathematical input set in the same coordinates: conversion claims equivalence to it, while approximation claims the declared inner/outer/heuristic relation to it. `OperationResult.output.id` identifies the actual returned set, and `relation` states its relation to that ideal output.

Evidence carries explicit applicable assumptions, support and an optional error bound with metric ID, nonnegative finite magnitude and units. The metric must define what is compared to the ideal output (for example a Euclidean Hausdorff bound); no generic norm or direction is silently assumed. Claim support must justify the bound under the listed assumptions. Symbolic text or numerical checks remain their declared evidence level; a certificate reference is unchecked and is not a validated bound.

`check_geometry_evidence` derives expected ordered set IDs and claim scope from the operation (or single conversion/approximation input). It rejects mismatched problem/request/reference/input identities or scope, unsupported validated assurance, and negative/nonfinite/unsupported error bounds. Cost is O(total identity lengths + input count); it copies only reference IDs, not numerical operands. Passing this guard establishes structural binding only: it does not verify a mathematical argument, estimate error, enforce the returned relation, or validate a native result.

### Outcome claims independent of objective bounds

`ProgramResult` keeps termination (completed, cancelled, resource limit, numerical failure) separate from a `ProgramOutcomeClaim`. The claim contains its `ProgramIdentity`, mathematical outcome (optimal, infeasible, unbounded, unattained infimum, undetermined), explicit `EvidenceSupport` and applicable assumptions. `SynthesisResult` instead carries a `SynthesisOutcomeClaim` bound directly to its original `ProblemId`. These records have no dependency on a primal, family or finite objective bound; infeasibility and unboundedness can carry support while all those optional fields are absent. Transferring a reformulated program's claim to the original problem requires a justified translation and its assumptions; matching a problem ID alone is insufficient.

An `Unestablished` outcome is a reported status without supporting evidence. `NumericalCheck` can record, for example, residual checks on an infeasibility dual witness or an improving feasible ray under stated assumptions; small residuals do not certify the outcome. `SymbolicArgument` can cite a contradiction or unbounded-ray argument under explicit assumptions, but the text itself is not machine checked. `CertificateReference` stores a proposed certificate/verifier for future checking and cannot be labelled validated. Numerical infeasibility, symbolic support and an unsupported request remain distinguishable without manufacturing objective bounds. The same support alternatives apply to optimality and nonattainment, with evidence specific to the claimed outcome.

`check_outcome_evidence` rejects a different problem/program identity and every validated request in this revision; it allows explicitly unestablished support. Cost is O(identity length), with no solve or evidence verification. Bounds retain their own independent evidence and native diagnostics remain available. Impossible adapter combinations, NaN bounds and results claiming proved optimality without suitable evidence must be rejected in downstream result validation. A nonzero native status must never be quietly converted to an empty feasible set.

## Joint family and claim-specific evidence

Canonical joint order is `[x0, ..., xT, u0, ..., u(T-1)]`: state block k starts at k*n, control block k at (T+1)*n+k*m. `JointCoordinates` carries T and dimensions; lifted payloads must retain an exact decoding map to this order, including all cross-stage dependencies. External coordinates are excluded from this nominal relation. Overflow and coordinate-map validity are adapter input checks. A `JointRelationPayload` cannot be replaced with stage marginals or a witness vector.

`OptimalFamily` names the **requested mathematical target**, not an automatically proven result. Its `FamilyTarget` says exact optimal relation, candidate relaxation or partial relation. Feasibility, optimality and completeness are separate claims, each bound to the expected `ProblemId`. A full family is Z* = {z ∈ F : φ(xT)=v*}; all terminal minimizers and consistent histories must be retained. For a two-step integrator with controls in [0,1] and cost (x2−1)², the control relation is u0+u1=1: two selected endpoints and the Cartesian product [0,1]² are both inadequate replacements.

`WitnessBatch` is a separate, nonconvertible type. It cannot itself establish completeness. `WitnessSelectorWorkspace` returns owning T+1 states and T controls per witness, original objective, requested count, identity, seed and search diagnostics; fewer distinct witnesses do not prove a singleton. Selection cost depends on relation and query and may require further optimization. Trajectory verification is a separate downstream module, not a reuse of a solver feasibility flag.

`EvidenceSupport` distinguishes unestablished evidence, numerical residual checks with tolerances/verifier, symbolic argument with assumptions, and **unchecked** certificate references. Symbolic argument text is provenance, not a machine-checked proof. No revision-1 type represents successfully validated evidence; a future verifier must introduce that outcome explicitly. `check_family_evidence` rejects a validated request, any mismatched problem identity, numerical completeness assertions, and nonempty completeness assertions on relaxed/partial relations. Passing it only means these structural checks passed, never that a supplied symbolic argument is correct. Its cost is O(total ID/string comparison length), constant claim count.

Numerical pipeline results may carry exact-target relations with unestablished completeness. A relaxation φ ≤ incumbent+tolerance remains labelled as such. Native optimal status, low residuals or agreement between backends do not promote it to full Z*. Unsupported completeness cases must return a limitation before numerical synthesis purports to construct a full family.

## Execution, configuration and caller example

`StrategyConfiguration` has independent IDs for strategy, LP, convex method, hull policy, geometry operator, converter, approximation policy, selector and representation. No implementation resolves those IDs yet. The future registry must check the whole pipeline (objective, domain, compactness/attainment, relation/output scope, arithmetic and evidence), not merely call the nominal profile guard.

`SynthesisStrategy` has immutable configuration/capability checks and produces an exclusive workspace. `SynthesisResult` retains optional joint family, owning incumbents, objective evidence and timing spans on limited runs. Cancellation and a lack of family do not imply infeasibility. Family construction/query costs may grow exponentially; the contract promises no polynomial runtime.

One immutable `ResourcePolicy` covers outer workers and native threads. `check_resources` requires positive counts and `outer_workers * threads_per_worker <= total_threads`, with division avoiding overflow. Cost O(1). It is admission validation; backend adapters must actually apply the limit and account for BLAS/global thread pools. `memory_bytes` is an accounting request until a backend advertises enforcement. `TimingSpan` stores parent and absolute run-relative start/end offsets; overlapping/nested durations must not be summed as end-to-end latency. Full versioned provenance/statistics artifacts belong to OBS-01.

The [compiled caller example](../../probes/core-01/caller_example.cpp) shares one immutable problem and resource policy between reachability/backward-recovery and direct joint-trajectory configurations. It transfers two exclusive workspaces into separate asynchronous tasks. Both adapters are explicitly **contract fixtures returning Unsupported**; no optimization or family is manufactured. The example uses unrestricted stage sets, so it is not the bounded two-step acceptance experiment above. Native dependency probes additionally exercise separate HiGHS objects, without claiming race/sanitizer coverage.

## Acceptance and remaining work

[Contract tests](../../probes/core-01/contract_tests.cpp) supply executable portions of T-M03 and T-V02. They cover shape/singular representation, unsupported profiles, temporal-empty handling, evidence identity, numerical/validated separation, incomplete relation coverage and resource admission. Revision 1.1 adds scoped outcome evidence without bounds/families, neutral geometry operand shapes, query scopes, conversion/approximation reference binding and error-bound metadata. Type checks prevent copying workspace objects or converting witness batches to families. All expensive module implementations and their full validation remain downstream. The isolated [probe README](../../probes/core-01/README.md) contains exact commands and observed platform results.

Revision 1.2 adds MODEL-01's immutable affine LTI/LTV evaluation and explicit
observation schedule, with literal dynamics/feedthrough, causal-clock, rejection
and lifetime tests plus an installed client. It does not close admissibility or
the broader architecture obligations. Any change to this contract must revise
this document and affected tests before integration.
