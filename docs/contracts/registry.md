# Typed adapter registry and preparation

The additive [resolved problem bridge](resolved-problems.md) invokes this actual
registry with an owning canonical description and computed mathematical ID.
Configured strategy restrictions remain capability/admission decisions; they do
not redefine publication validity. The bridge preserves the pure planning,
check-before-snapshot and dependency-before-factory contracts below.

CORE-04 adds `<csl/registry/registry.hpp>` and the installed `CSL::registry`
target. The current [native interface revision is 1.8](core-interfaces.md).
This is a C++20 source interface for compatible in-process toolchains. It
provides no portable C++ ABI, loader, global registry, fallback algorithm or
production optimization implementation.

## Typed registration and the runtime seam

`Registry<Port>` owns registrations indexed by module ID. Each registration
contains its actual ID/version, a pure capability callback, a typed workspace
factory and an optional separate basis-diagnostics factory. Duplicate IDs reject
with the incoming requested identity and the already registered actual identity.
Empty IDs/versions and absent callbacks reject at registration. A method request
can pin a version; mismatch never selects a different version silently. Unknown
methods remain explicitly unresolved in `Rejection::provenance.actual`.

The existing mathematical interfaces have separate `LPPort`, `ConvexPort`,
`GeometryPort`, `ConversionPort`, `ApproximationPort`, `SelectorPort` and
`StrategyPort` traits. Their request/workspace/result distinctions are preserved.
`GeometryPort` admits the separately typed `DependentSum` request only for an
adapter with factor-identity semantics; its existing `MinkowskiSum` request
retains the independent-set meaning. See the [geometry source contract](core-interfaces.md)
and [generator adapter](generator-sets.md).

`FiniteActionMinimaxPort` is a separate numerical-oracle interface. Its frozen
query contains the finite-action minimax request and limits, and its result
keeps the oracle's six distinct outcome variants. The registered reference
and its bounded scope are documented in [finite-action minimax](finite-action-minimax.md).
It does not construct a `SynthesisOutcome` or claim a joint optimal family.

`ValidatedFiniteActionMinimaxPort` is a separate validated-oracle interface
with validated assurance and a bounds representation. Its query freezes the
validated request and plan/history/operation limits. Complete bounds,
infeasible-catalogue, and unresolved-catalogue results carry and are checked
against the frozen problem/request identities; empty, no-scenario, unsupported,
and stopped variants remain status-only. Its admitted scope and numerical
preconditions are documented in [finite-action minimax](finite-action-minimax.md).

`SelectorRequest` pairs the existing family and witness request;
`StrategyRequest` owns an immutable `ResolvedProblem`, the effective
`FamilyRequest`, strategy configuration and selected strategy version. LP and
convex factories can call the existing backend's `make_workspace()`; their
factories return the same exclusive mathematical workspace interfaces.
`StrategyPort::run` checks the numerical policy against the prepared family
request before invoking the workspace and validates family/outcome identity on
return. `SynthesisWorkspace::solve` returns `SynthesisResult` only; the port's
`SynthesisOutcome` can report top-level `Unsupported` only before that call.
A late provider rejection belongs in `SynthesisResult` with scoped
request provenance and retained evidence. Contract validation failures use
`contract_rejected` and retain the original stop evidence separately; they do
not synthesize a provider request identity.

GEO-02 adds `HullReducerPort` (`hull-reducer`) as a separately selectable
operation. `geometry::make_lp_hull_reducer_registration()` registers the current
LP-membership reducer; another reducer registers its own workspace under a
different method identity. Its `run_with(context, dependency...)` is available
only when that port declares the matching typed `run` signature. The hull port
accepts an `LPWorkspace` dependency rather than selecting a concrete solver.
For generated LP requests, `registry::RegisteredLPQueryRunner` instead owns a
`PreparedProvider<LPPort>` by value. It calls `prepare(concrete_request)` for
each query, creates no workspace on rejection, and creates a request-specific
exclusive workspace for each admitted synchronous solve. Its closed query
records retain the concrete program identity, provider provenance, and one
closed outcome: admission rejection, pre-execution cancellation/deadline,
solver rejection, completed result (including returned subject identity), or
non-completed termination reason. They do not retain solver vectors.
The runner forwards the caller's `ExecutionContext` and remains sequential; it
does not create a nested executor.

For a concrete `OperationRequest`, `<csl/geometry/operation_admission.hpp>`
offers `geometry::prepare_geometry_operation` for both a prepared provider and
a fixed `Selection<GeometryPort>`. Successful admission returns the usual
`PreparedPipeline<GeometryPort>`; rejection returns
`GeometryAdmissionRejection`, pairing the registry's provider rejection with
the submitted `GeometryReference` (problem, request, ideal output and ordered
operand set IDs). The reference is derived from immutable request metadata;
neither overload creates a workspace. A missing operation remains a scoped
`unsupported` diagnostic, never a mathematical infeasibility result. Method
selection before a concrete request retains the registry's requestless
`Rejection` contract.

`LPWorkspaceView` remains a low-level borrowed adapter for a caller-owned
`BoundWorkspace<LPPort>` and forwards direct solves without per-query
`PreparedProvider` admission. It is not the registered generated-request path
and must not outlive its corresponding `BoundWorkspace<LPPort>`.

`select(registry, method, request, requirements, transitions)` borrows a complete
typed request. `prepare_pipeline(selection...)` returns either a rejection or a
`PreparedPipeline<Ports...>`. The prepared value has no public/default unchecked
constructor. Its `create()` returns a tuple of exclusively owned
`BoundWorkspace<Port>` values. `run(context)` invokes the corresponding original
mathematical method on the retained complete request. There is no route to swap
an unchecked request into an already prepared workspace.

`StrategyRegistry` is the stable runtime seam. The client passes a
`StrategyRequest` and requirements to `prepare()` and receives
`variant<PreparedStrategy, Rejection>`, independent of the selected strategy's
dependency tuple. Its registrations pair a pure capability callback with a pure
planner. A planner calls `check_pipeline` for its required typed dependencies,
then `compose_strategy(checked, builder)`. The builder receives the exclusive
workspace tuple plus the frozen strategy request and requirements, and returns a
`unique_ptr<SynthesisWorkspace>` that owns those dependencies. Neither the model
nor the runtime client dispatches on an algorithm ID. The optional third
`prepare` argument pins the strategy version; dependency `Method` values pin
their own versions. Successful provenance includes the strategy followed by
every selected dependency, with both requested and actual identity/version.
An optional pure `expected_lineage` callback can freeze the strategy's ordered
transformation identities into the prepared request before workspace creation.
The strategy must emit those same identities at runtime, and any complete-family
verifier still checks the proposed mathematical evidence against the frozen
problem, request, strategy and lineage.

### Request-dependent complete-family verifier selection

`StrategyRegistration` may provide a pure request-dependent resolver for the
complete-family verifier key. The resolver receives the complete immutable
`StrategyRequest` and returns either one `(ModuleId, version)` key or no key.
This resolver selects proof authority only when the request requires
`Completeness::established`. If no resolver is registered, the static
`complete_family_verifier` key retains its exact current behavior. If a
resolver is registered but established completeness is not required, the
static key also retains its current behavior and the resolver is not consulted.
For a request that does require established completeness, the resolver owns
selection: an empty result rejects preparation and never falls back to the
static key. A selected key that does not identify a registered compiled
verifier also rejects in this established-completeness path. A static key may
be empty when a resolver is installed; it is not a fallback for a missing or
unknown resolver selection when established completeness is required.

For requests requiring established completeness, selection and verifier lookup
occur synchronously during `StrategyRegistry::prepare`, before the strategy
planner can snapshot dependencies, before any workspace factory is invoked,
and before native solver/backend creation. The selected key and resolved
verifier binding are frozen into `PreparedStrategy`; later mutation or
destruction of the registration/registry cannot change them. The compiled
verifier identity is carried with the prepared complete-family authority and is
bound into result evidence alongside the problem/request/profile, strategy
identity/version, canonical coordinates and ordered transformation lineage.
Evidence from another verifier key, even one registered for the same strategy,
must fail the binding check. The selected key identifies the checker; it is not
itself proof of completeness. Requests not requiring established completeness
retain existing static-key behavior, including the current behavior when no
static key is configured.

The resolver is deterministic for an equal immutable request and has no
observable effects. It must not inspect mutable external state, allocate or
create native resources, call a solver/provider, or depend on call order. Any
configuration it needs is immutable and owned by the callback value without
mutable transitive aliases. Concurrent preparation of different request
profiles must not leak verifier identity between prepared values. The resolver
must be total for valid `StrategyRequest` values in the
established-completeness path: unsupported profiles return no key. If it throws,
the exception follows the existing callback exception
policy and propagates; it is not converted to a mathematical outcome or to a
static-key fallback. In the established-completeness path, an empty selection
or unknown key is a scoped admission rejection with requested strategy identity
and verifier-selection diagnostics, and creates no workspace.

`PreparedStrategy::expected_synthesis_identity()` returns a value copy of the
resolved problem ID, frozen family request, canonical coordinates, selected
strategy ID and version, and expected ordered lineage captured during
preparation. The method is read-only and does not expose the retained
`StrategyRequest`, registry, callbacks, or mutable aliases. It exists so an
application can independently bind downstream verification to the admission
snapshot rather than copying identity fields from a strategy-produced family.
The copy remains valid after the registry and registration are destroyed; it
does not confer family validity or completeness. This additive source-interface
contract requires integration review with the application composition seam.

Contract examples:

| Registration/request | Expected preparation result |
|---|---|
| Static key `csl.verifier.ts01-analytic@1`, no resolver, T-S01 | Same verifier behavior as before this extension. |
| Static T-S01 key plus resolver; T-S01 requires established completeness | Resolver explicitly selects `csl.verifier.ts01-analytic@1`. |
| Same registration; T-S02 constant-objective request requires established completeness | Resolver selects its distinct T-S02 verifier key and that identity remains bound in the prepared authority/evidence. |
| Same registration; request does not require established completeness | Preserve current static-key behavior and do not call the resolver. |
| Resolver installed, unsupported profile requires established completeness | Reject before planner snapshot/workspace/native creation; do not use the static T-S01 key. |
| Resolver selects an unregistered key for established completeness, or T-S01 evidence is presented under T-S02 prepared authority | Reject admission or evidence binding respectively. |

The registry contract tests must exercise the public preparation/result path:
static-key compatibility with and without a resolver; a non-established
request using the static key without invoking the resolver; two established-
completeness requests selecting distinct keys from one strategy registration;
empty resolver result despite a populated static key; unknown-key rejection;
proof/evidence rejection when verifier identity is crossed; and concurrent
preparation of T-S01/T-S02 with no identity leakage. Use observable resolver,
planner, factory and native-backend counters to prove that missing/unknown
selection on the established-completeness path rejects before planning or
workspace creation. Doctest/contract assertions must include literal expected
verifier IDs and versions, not just callback invocation counts. T-S01 retains its analytic
verifier identity. T-S02's constant-objective profile must use its own verifier
identity because its full feasible-history relation is a different proof
obligation; neither profile may authorize the other's completeness evidence.

A resolver's key-selection callback does not replace the existing
claim-specific evidence checks or establish the scientific numerical-coverage
policy. T-V02 and the evidence migration gate remain authoritative for what
counts as complete-family support.

A new interface supplies `Request`, `Workspace`, `name`, a `snapshot` function
and a typed `run` function, then instantiates `Registry<NewPort>`. No central
variant or dispatch switch changes. A new strategy can hide a different tuple
behind its registered planner. The custom counter-port test exercises this path
through both direct preparation and the unchanged runtime strategy client; it
does not invent hull mathematics. Until OPT-05 introduces its mathematical port,
a strategy requiring hull execution returns an explicit unresolved hull
rejection. An unused optional configuration axis need not be registered.

## Whole-pipeline capability checks

Preparation has two phases:

1. Resolve every selected method and run all pure capability checks; compare
   each declared offer to requirements and every producer/consumer transition.
2. Only after the whole pipeline accepts, snapshot complete typed requests and
   capture their factories. Actual native/workspace creation waits for `create`.

Phase one permits small diagnostic and plan metadata allocations. Checked entries
borrow registration pointers; even copying a factory callback is deferred because
its captures could contain numeric configuration. Registry lifetime and stability
must therefore span the entire deferred synchronous snapshot.
It forbids numeric data copying, geometry materialization, native backend setup
and workspace creation. The custom-port snapshot counter verifies that an early
compatible dependency is not snapshotted when a later dependency rejects.

`Requirements` keeps scalar arithmetic, expected output representation,
assurance, optional set relation, family target, optional completeness and basis
support separate. Actual buffers remain `double`; binary32, exact and interval
requests reject. Validated assurance is rejected by default. A port may opt in
through its typed `accepts_validated_assurance` trait; admission still requires
exact output assurance and representation matching. The validated finite-action
minimax port is currently the only opt-in and advertises its bounds certificate
representation. Relations and family targets must match when requested.
An exact family target, equivalent relation or numerical assurance never
establishes completeness. `Completeness` is a declared capability requirement,
not proof that a result contains the complete optimal family. Result evidence
still needs the existing claim-specific checks and later verifiers.

Each `Transition` identifies an earlier producer by tuple index and the output
metadata its consumer requires. Preparation compares representation, assurance,
requested relation, family target and completeness. A forward, self or missing
producer rejects. There is no automatic conversion, approximation, relaxation or
guarantee weakening. Strategies explicitly declare the operations, typed
requests, required dependencies and transitions; the registry does not infer
them from algorithm IDs. A transition is a metadata compatibility declaration,
not a runtime dataflow engine. Its strategy builder wires the corresponding
workspaces and operands. Strategies own the correctness of that declaration,
including operand identities and any later data-dependent operations.

Capability callbacks must inspect the complete typed request: operation kind,
representation and payload support, objective/reformulation, shape, finite
values, native integer limits and required assumptions. They must reconcile
request-contained policies with outer requirements and the advertised offer.
The registry cannot derive arbitrary mathematics from a label. Unknown
convexity, compactness, attainment or invertibility cannot establish a needed
assumption. The bounded LP fixture checks finite interval endpoints explicitly,
which establishes its own compact/attained domain; it rejects unbounded or
otherwise unsupported requests. The forward strategy fixture uses the existing
narrow nominal-profile guard and separately restricts objective kind. The guard
permits singular forward dynamics and conservatively rejects an inverse-only
profile without verified invertibility. Temporal coupling, finite/mixed control,
feedback and continuous time remain capability rejection, never infeasibility.
Passing these checks is not whole-problem validation: timestamps, full dimension
consistency, all objective properties, payload validity and feasibility are
MODEL-03 and adapter obligations.

Rejections identify the failing port, requested/resolved actual method and a
field/reason. A capability callback returning an empty rejection diagnostic list
gets an explicit callback-contract diagnostic. The registry does not translate
rejections or factory exceptions into mathematical outcomes. Allocation failures
propagate; a null factory result is a programming error (`logic_error`). If any
tuple factory throws, already created unique workspaces are destroyed by RAII,
and no partial successful pipeline is returned.

## Ownership and extension-author preconditions

Selections and checked plans borrow their source requests and registries. The
caller must keep them live and unchanged from the beginning of checking through
the end of synchronous snapshot preparation. `check_pipeline` is the planner
composition stage, not a persistable result: returning a checked plan referring
to a dead local, or changing its request before `snapshot`, violates this
precondition. A planner that owns a request must retain that owner through the
deferred snapshot, for example in its builder capture. Planners call
`check_pipeline`, not `prepare_pipeline`/`StrategyRegistry::prepare`, so a nested
dependency cannot snapshot before the enclosing plan accepts.

Prepared values own immutable copied requests, requirements and registration metadata.
Built-in snapshots copy every owning vector/matrix/configuration value.
`StrategyPort::snapshot` also deep-copies `SystemModel`, eliminating mutable
producer model aliases. Bound workspaces retain the immutable request for their
entire lifetime, including if the source registry, request, prepared plan or
configuration has been destroyed. Each `create` constructs fresh unique mutable
workspaces. Workspaces are noncopyable; one owner may transfer them to a worker.
Concurrent use of a single workspace remains unsupported. A borrowed `basis()`
pointer is valid only while its owning bound workspace exists. The optional
`basis_factory(request, workspace)` receives the actual freshly created typed
mathematical workspace, after its non-null check. A diagnostic may borrow that
one workspace to observe its evolving solve state; it must not refer to a
different creation or coordinate through mutable captured state. Diagnostics
are destroyed before the mathematical workspace, including exceptional creation
cleanup. Neither object depends on the prepared plan or registry remaining alive.
A null primary factory result rejects creation before dereferencing it or
invoking the basis connection. Moved-from
prepared handles are only suitable for destruction or assignment.

Opaque `SetPayload` and `JointRelationPayload` values cannot be deep-copied
through registry revision 1.1. Their publication precondition is strict: construct an
owning `shared_ptr<const ConcretePayload>` with immutable transitive data, retain
no mutable producer alias to the object or anything it references, and do not
mutate hidden caches without the payload's explicit safe contract. Merely
converting a `shared_ptr<MutablePayload>` to `shared_ptr<const SetPayload>` does
not meet this rule. A custom port's `snapshot` must similarly eliminate mutable
producer aliases or retain already published immutable owning views. For
[CORE-03 numeric views](numeric-data.md), retain `MatrixView`/`VectorView` objects;
their descriptors and spans alone borrow and do not retain storage.

The registry owns copied callback objects; copying `std::function` does **not**
freeze arbitrary captures. Extension authors must capture immutable owned
configuration by value or by privately published `shared_ptr<const Config>`
without mutable transitive aliases. Capabilities and planners must be pure and
thread-safe, and may read borrowed registries only during synchronous preparation.
Factories/builders may allocate their own mutable workspace but must not retain
mutable shared configuration or reuse a workspace. Every object needed after
preparation must be owned by the prepared callback/request; dangling reference
captures are invalid. Test factory counters and snapshot counters are explicitly
synchronous test instrumentation, not a recommended adapter configuration.
The lifetime tests capture privately copied configuration, mutate and destroy
the source, and observe literal independent workspace results.

Register during setup; concurrent `add` and preparation on the same registry is
unsupported. Independent registries need no global serialization. After setup,
concurrent reads/preparations and independent creations are permitted under the
callback/payload contracts above. No locking or global backend settings are
introduced here.

## Acceptance evidence and limits

[Registry tests](../../tests/contract/registry/registry_tests.cpp) register two
test-only working LP algorithms: endpoint enumeration and coefficient-sign
selection. Both support only one finite interval variable with no constraint
rows, subject to a conservative binary64 arithmetic profile: endpoint products
and `std::fma(coefficient, endpoint, offset)` objective values must be finite.
When the coefficient is nonzero and the endpoints differ, the two evaluated
objectives must remain distinguishable; otherwise both adapters reject with
`unsupported` / `lp.arithmetic` during capability checking, before factories.
This includes overflow, underflow ties and a large offset rounding unequal
objectives to a tie. A genuinely constant objective or degenerate interval is
still accepted when its arithmetic is finite. Both algorithms evaluate accepted
objectives using the same specified fused operation; endpoint enumeration orders
the two endpoint values, while coefficient-sign selection chooses the endpoint
from the coefficient. Numerical objective values are not validated exact bounds.
The same caller changes only configured method identity:
`min(3*x+2), x in [-1,4]` gives `x=-1`, value `-1`; coefficients `-2` and `0`
give `(4,-6)` and `(-1,2)`. They publish distinct `endpoint/1.0` and `sign/2.0`
provenance. This establishes bounded LP substitution, not general LP support or
an optimal control family. Production LP/convex adapters remain OPT-03/OPT-08.

Other adapters are explicitly plumbing fixtures. They return stopped or
undetermined outcomes, or forward the bounded LP result as an incumbent without
a family. They establish callable registration, request binding and exclusive
ownership, not mathematical completeness. Tests cover all-port factory absence
on rejection; scalar, representation, objective, relation, assurance, family,
completeness and basis rejection; downstream transitions; unknown and duplicate
IDs; T-M03 profiles; immutable request/configuration lifetime; custom extension;
and factory-exception cleanup. Doctest assertions remain active in Release.

The [public consumer](../../tests/installed/registry_client.cpp) builds in the
source tree and in a copied isolated consumer tree with only the installed
headers/`find_package(CSL CONFIG)` target. It verifies a retained custom-port
request and literal independent mutable state. Full production solvers, model
validation, optimal-family reconstruction, scenario loading, statistics and
performance claims are outside CORE-04.


## Generated requests through a frozen registered provider

`<csl/registry/provider.hpp>` adds an owning selected-registration provider for
algorithms that generate later LP or other typed requests. It uses the existing
port traits and changes no fixed `PreparedPipeline` / `BoundWorkspace` API.
`select_provider(registry, method, requirements)` and `check_providers(...)`
resolve every declared method/version and check known scalar, assurance and
basis-factory requirements without copying registration callbacks, snapshotting
numeric requests or constructing workspaces. `CheckedProviders` borrows the
registrations until its synchronous `snapshot()`, exactly like `CheckedPipeline`.
It has no output offer: future numeric capability acceptance is conditional.

`snapshot()` yields an owning tuple of `PreparedProvider<Port>` values.
`prepare_provider(selection)` is the standalone check-and-snapshot convenience.
Each provider freezes actual/requested identity/version and Requirements in
immutable shared storage. Callbacks obey the same pure-capability and immutable
captured-configuration contract as existing registrations: a callback retaining
mutable aliases or dangling references violates that contract; copying a
std::function cannot make arbitrary external state immutable.

`provider.prepare(concrete_request)` has no per-query requirements argument.
It calls the selected capability callback on the complete concrete request,
checks the actual offer and requested basis availability, then uses the existing
checked pipeline snapshot path. Rejection copies no request and creates no
workspace. A successful prepared pipeline owns its complete request and selected
factory and creates a fresh exclusive bound workspace through the original path.
Neither provider nor caller can swap unchecked requests into a live workspace.
A declaration requiring established completeness does not itself establish that
capability; a future offer lacking it rejects. Callback/factory exceptions retain
the existing exception/RAII policy, and basis diagnostics retain their original
workspace lifetime and ordering.

The narrow composition overload is
`compose_strategy(checked_fixed_pipeline, checked_providers, builder)`. Its
builder receives `(fixed_workspace_tuple, prepared_provider_tuple,
frozen_strategy_request, requirements)`. Both fixed request snapshots and
provider callback copies are deferred until the enclosing StrategyRegistry has
accepted its capability and all declared known dependency checks. Planners use
`check_pipeline` / `check_providers`, not their standalone prepare conveniences;
all registries/borrowed requests stay stable through synchronous preparation.
Provenance lists the strategy, fixed dependencies, then generated providers.
Concrete generated calls still record their own successful or rejected request
admission; the declaration is never a promise about unseen numeric data.

A provider can be copied and retained after the source registry/request/config
objects die. Independent `prepare().create()` calls obtain independent mutable
workspaces. An algorithm needing multiple varying programs stores the provider
and prepares each program; it never receives a raw unchecked workspace. No
central port dispatch, solver implementation, fallback, or hull mathematics is
introduced by this seam.
