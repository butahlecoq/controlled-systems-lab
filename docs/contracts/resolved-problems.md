# Resolved mathematical problems

`<csl/problem/validator.hpp>` and `CSL::resolved_problem` add complete, owning
publication on top of the `Problem` DTO introduced in canonical source 1.4 and
retained in source 1.5. This is an additive module; the DTO, LP data result alias
and existing component targets retain their
authority. The target publicly composes `CSL::problem`, `CSL::objectives` and
`CSL::registry`. See [component data](problem-data.md) and the
[identity byte format](problem-identity-v1.md).

## Publication and admission

`resolve(problem, context)` returns exactly one of `ResolvedProblem`, `Diagnostic`
or `OperationStopped`. Publication accepts valid mathematical data; it does not
solve feasibility, infer estimator knowledge, certify a game, or construct an
optimal family. An empty control set or inconsistent constraints can therefore
publish successfully. Invalid dimensions, indexing, time grids and criterion
data remain `invalid_input`. A declared but unrepresented mathematical structure
is `unsupported`. Objective numerical failure remains `OperationStopped` with no
published problem or fabricated infeasibility result.

The context must explicitly select `stage_product_uncoupled`. Its external
sequence set is the Cartesian product `W0 × ... × W(T-1)`; its quantifier scopes
the whole sequence. The initial set and external sequence form a separate
Cartesian product. At zero horizon the external product has one empty sequence.
Correlation across stages, fixed parameter reuse, initial/external coupling and
state- or parameter-dependent dynamics are explicit unsupported intake values.
They reject before validation or copying of their marginal numerical data. An
unspecified or unknown intake value is invalid. A caller must not erase one of
those structures into stage marginals before calling this API.

Validation order is deterministic:

1. Check the uncertainty declaration, model presence, information and time-domain
   enums. Continuous time is unsupported; unknown enum values are invalid.
2. Validate and sort content binding keys, rejecting duplicates.
3. Deep-copy the canonical DTO and its model, preserving authored provider forms.
4. Compose the existing model, control, initial, external and constraint
   snapshot factories. Propagate their diagnostics without reinterpretation.
5. Compose the objective factory using the context's policy, propagate its
   diagnostics/stops, and require the objective dimension to equal state width.
6. Require every adversarial semantics reference to name a resolved content
   binding, compute the structural identity, and publish all owning components.

Set handles must pass the existing native `sets::from_handle` validation.
Arbitrary payloads and forged metadata are rejected by that authority. No extra
eigensolver, rank test, inverse, bounding computation or canonical set conversion
is introduced. Singular dynamics, universal and lower-dimensional sets, and
unknown boundedness remain valid data. Continuous, finite and mixed controls
retain their alternatives, ordered catalogue entries and duplicates. Finite
choices are never converted to their convex hull. Mixed action coordinates do
not introduce switched or hybrid dynamics.

Observations retain their maps, schedule and causal indices without asserting
which state is known to a strategy. Temporal constraints retain the complete CSR
joint map on `x0,...,xT,u0,...,u(T-1)`, including presence with zero rows. Component
factories check dimension arithmetic, CSR structure and offsets.

`prepare_strategy(resolved, registry, configuration, requirements, version)` calls
the actual `StrategyRegistry::prepare` with the frozen canonical description and
copied configuration. It returns `PreparedResolvedStrategy` or the registry's
unchanged `Rejection`. The selected strategy owns its inverse, compactness,
full-dimension, nominal, information and temporal support requirements. There is
no default strategy or hardcoded nominal gate inside the resolver. Registry
check-before-snapshot and dependency-before-factory behavior remains in force.
Resource policy and execution context still belong to execution.

The wrapper retains both the resolved problem and actual prepared strategy.
`preparation()` returns an owning registry preparation usable after registries
and producers are destroyed, under the registry's existing callback-lifetime
rules. Extracting that preparation alone does not add a content-interpreter
seam: a future strategy needing resolved artifacts must define its own explicit
owning dependency. The current API does not turn declarations into executable
game semantics. Existing nominal guards still reject unsupported external,
feedback and finite profiles.

## Ownership and content

Successful handles have no default or unchecked public constructor. Copies are
constant-time retaining owners; rvalues use the same non-destructive copy
semantics. A `ResolvedProblem` owns an immutable canonical compatibility DTO and
the validated model/domain/constraint/objective owners. This intentionally
duplicates some numerical storage to support current registry callers without
another DTO authority. `description()` and `content()` return aliasing shared
owners; component getters return independent retaining handles. Borrowed spans
remain valid while an associated owner is retained.

`snapshot_content(bytes, expected_digest)` copies the actual bytes, computes
private SHA-256, and rejects a supplied digest mismatch at
`problem.content.digest`. Empty input denotes actual empty content. There is no
digest-only or path-only successful constructor. The input span must remain
stable during the synchronous call. Standard allocation exceptions propagate.

Bindings have a case-sensitive nonempty key using ASCII letters, digits and
`._/:-`, an owning `ResolvedContent`, and a display-only source location. Keys
sort in unsigned ASCII order; duplicates are invalid even when bytes agree.
The identity includes keys, actual byte lengths and digests. Locations are
excluded and never opened. Retained adversarial references must match a binding
key, but publication does not verify a decoder's correspondence to coefficients,
interpret the referenced game, or certify its policy/information semantics.

`identity()` is the computed versioned mathematical identity; `authored_label()`
preserves the submitted ID as display text. `description()->id` contains the
computed ID for result provenance. Backend choices, execution budgets, numerical
policy and admissibility evidence are excluded from mathematical identity. Two
accepted policies may publish the same mathematics with different check evidence.
Changing resolved bytes changes identity even when decoded coefficients happen
to agree. Pure path changes do not.

## Scope

This module publishes discrete affine problem descriptions and connects them to
configured strategy admission. It does not implement a filesystem/network
loader, decoder, production synthesis planner, robust/finite/hybrid/temporal
solver, estimator, game interpreter, inverse strategy, or completeness proof.
The remaining actual loader/planner integration and TEST-02 loader criterion
cannot be inferred from these snapshots or analytic test strategies. Publication
tests establish no algorithm-performance claim.
