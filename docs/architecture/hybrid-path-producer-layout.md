# Hybrid producer path layout

## Problem

The hybrid producer validates a fixed mode/edge path, constructs its joint H relation, and lifts the terminal objective into the same coordinates. Preflight, composition, and objective lifting currently resolve modes and edges and derive joint dimensions independently. Issue #738 identifies this as synchronization work that can let producer paths disagree. The refactor must preserve current path ordering, diagnostics, reset semantics, cancellation, and resource limits, while keeping the layout private to the built-in producer.

## Usage (caller's view)

Callers keep using the existing model functions:

```cpp
preflight_hybrid_path_relations(system, request, paths, limits, cancellation);
compose_hybrid_path_relation(system, request, path, limits, cancellation);
lift_hybrid_terminal_objective(system, request, path, limits);
```

The synthesis path admits its full inventory first, then invokes the existing relation and objective operations. Standalone callers of the public functions still receive the same results and diagnostics.

## Shape

One private resolver creates a `HybridPathLayout` that consumers treat as immutable after resolution. It stores resolved mode and edge identities, ordered post-state ranges, per-transition control and pre-reset ranges, and checked total width. The coordinate order is the initial post-state followed by each transition's control, pre-reset state, and next post-state. Separate mode and transition sequences represent a zero-horizon path as one post-state and no transitions.

The resolver owns path-shape, endpoint, connectivity, dimension, and offset validation. A private admission function consumes the layout to count supported H rows and enforce row and matrix-element limits; the resolver enforces coordinate-width overflow and variable limits. Preflight is the sole admission entry point and maps its failures to path-context diagnostics. Admission remains distinct from relation construction, and objective lifting uses the layout without inheriting H-representation admission. Each consumer resolves one ephemeral layout for its call; preflight does not return layouts to synthesis. Composition and objective-lift consumers use named coordinate ranges and do not independently resolve path identities or recalculate offsets.

The resolver, row/resource admission helper, and layout consumers stay private in `src/model/hybrid_system.cpp`. Preflight, composition, and objective lifting all use the same resolver, but a standalone sequence of separate public calls rebuilds an ephemeral layout each time. No internal plan type crosses into synthesis or alternate adapters. The projected adapter, alternate exact adapters, compiled verifiers, and independently authored test oracles remain independent.


## Synthesis decision

Candidate B is the base because its producer-local seam keeps the private type inside the model module and leaves synthesis on its current adapter boundary. Candidate A would pass preflight layouts into synthesis for exact instance reuse, but that requires an extra model-to-synthesis internal API and built-in-adapter-specific flow that the issue does not require. The cross-judge preferred A for reusing each exact layout instance. The rubric did not distinguish shared resolution logic from runtime reuse; the issue asks for one owner, and no performance work is authorized, so the smaller source-local boundary wins.

Graft Candidate A's explicit separation between geometric layout resolution and H-representation/resource admission. Keep Candidate B's named half-open coordinate ranges, with distinct mode and transition sequences. Reject Candidate A's preflight-plan transport across the model/synthesis boundary and its requirement to alter built-in adapter orchestration. The cross-judge found neither design fatally flawed, but scored A higher on reuse and B higher on local ownership. This synthesis selects the smaller ownership seam because the issue asks to eliminate independent reconstruction, not to reuse one allocation across API calls.

Neither candidate supplied the required behavior-test matrix, so implementation adds literal coordinate and limit cases before relying on the design.

## Tradeoffs accepted

- Separate preflight, composition, and objective APIs may be called independently, so each resolves the same layout afresh rather than crossing module boundaries to cache or pass it between calls.
- Compiled verifiers and literal test oracles retain independent geometry, even though that intentionally keeps some mathematical derivation duplicated.

## Alternatives considered

- A single `joint_width` helper hides only arithmetic and leaves mode, edge, and offset reconstruction spread across consumers.
- A public prepared-path object would make callers manage producer-only H layout and could imply that alternate adapters share its representation assumptions.
- Passing preflighted layouts through a new model-to-synthesis private header could avoid repeated resolution in one synthesis path, but adds internal coupling and adapter-specific orchestration for a runtime optimization the issue does not request.

## Verification and remaining risks

The focused `hybrid_model_tests` and `hybrid_path_program_tests` pass. New coverage checks a literal dimension-changing relation and lifted objective, malformed connectivity, stage-context variable-limit diagnostics, and the checked coordinate-width arithmetic at the `size_t` boundary. Existing tests cover zero horizon, resets, cancellation, and row/storage limits. The main remaining risk is preserving diagnostic precedence across less common malformed-profile combinations; the layout stays private so it can be adjusted without changing caller APIs.
