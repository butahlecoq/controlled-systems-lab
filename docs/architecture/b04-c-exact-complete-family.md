# B04-C exact complete-family verifier

## Problem

B04-C has an external exact-arithmetic dossier, but it has not passed Strategy A's compiled verifier and prepared-request boundary. Its optimal history relation contains non-dyadic rational equalities, while the existing public H-set and exact-H builders accept binary64 data. Converting the equalities to doubles would change the family. The admitted profile also has 16 controls and 84 canonical joint coordinates, so it cannot use the current nominal exact-H profile unchanged. The verifier must establish the objective optimum and full relation coverage as separate claims, then bind both to the frozen Strategy A request before publication.

## Usage (caller's view)

Strategy A owns verifier selection and result publication. Callers prepare and execute an ordinary request; they do not supply a verifier key, certificate, or relation internals.

```cpp
auto prepared = registry.prepare(b04_c::request(corrected_track_problem()));
if (auto* rejected = std::get_if<Rejection>(&prepared))
    return record_refusal(rejected->diagnostics);

auto strategy = std::get<PreparedStrategy>(std::move(prepared));
auto workspace = strategy.create();
auto result = strategy.run(*workspace, request, context);
// A complete family is present only after the registered compiled verifier accepts it.
```

An unsupported target, assurance, representation, materialization request, source profile, strategy version, or lineage is rejected during preparation, before workspace creation.

```cpp
auto outcome = registry.prepare(request_with_unsupported_projection);
// Returns an explicit unsupported/resource outcome; there is no binary64-H fallback.
```

The family carries a profile-specific exact relation. The first supported query is exact membership of a full canonical history; a query result is not a second completeness proof.

```cpp
auto membership = b04_c::contains(*result.family, exact_history);
// member / not_member / resource_limit, computed over exact rational values.
```

## Shape

### Data model

The mathematical family is stored in its smallest exact coordinate system: 16 control variables, all 100 feasible control and phase inequalities, the exact terminal fiber equalities, and an affine lift to the canonical 84-coordinate history `(x0,…,x16,u0,…,u15)`.

```cpp
namespace csl::synthesis::b04_c::detail {
struct Rational { BigInt numerator; BigInt denominator; }; // reduced, denominator > 0
struct ExactRow { std::vector<Rational> coefficients; Rational bound; };
struct ControlPolytope { std::vector<ExactRow> inequalities; };
struct TerminalFiber {
    std::vector<ExactRow> equalities; // exact x_T(u) = x*_T; dependent rows retained canonically
};
struct AffineHistoryLift {
    Matrix<Rational> state_maps; // 17 state blocks, each mapped from the 16 controls
    Vector<Rational> state_offsets;
};
struct ExactB04CFamily {
    ControlPolytope feasible_controls;
    TerminalFiber optimal_terminal_fiber;
    AffineHistoryLift lift;
    std::array<Rational, 4> unique_terminal_state;
};
}
```

The profile parser reconstructs model data from the authoritative `ResolvedProblem` and effective `FamilyRequest`. Binary64 fields are converted by exact bit decomposition to represented dyadics; exact profile constants remain rationals. The verifier does not trust a producer's row matrix, dimension, source label, or Python record as proof authority.

### Verification and publication

`StrategyRegistry::prepare` continues to select the compiled verifier before planning or workspace creation. The B04 selector admits only the exact corrected-track scenario, the established exact-optimal-relation target, the declared assurance and representation, and a supported resource request. It freezes the verifier key, strategy version, problem/request identity, coordinates, and ordered lineage through the existing prepared-strategy authority.

At execution, the producer returns an untrusted `CompleteFamilyProposal`. The verifier independently reconstructs:

1. **Objective optimality.** Rebuild the represented-dyadic convex quadratic and check the exact feasible witness, exact replay, exact objective and zero gradient. The residual map restricted to the reachable terminal affine image has rank two; strict convexity on that image gives a unique terminal state. This proves the minimum value and terminal point for the represented profile.
2. **Family coverage.** Reconstruct all feasible inequalities and the exact terminal fiber in control coordinates. Prove that the relation is precisely the feasible control set intersected with the terminal equalities, then verify all 17 state maps. This covers the complete 84-coordinate family without materializing an 84D binary64 H matrix. The induced terminal set is the singleton already established by the objective proof.
3. **Request binding.** Match the reconstructed proof and relation to the frozen problem, complete effective request, 84-coordinate schema, strategy/version, verifier key and ordered lineage. A matching digest or producer claim alone is not evidence.

Only after these checks does the existing prepared workspace publish the family as registry-verified. Any identity mismatch, malformed rational, unsupported query, cap exhaustion or failed proof returns a typed rejection/resource outcome. It never publishes a partial family or falls back to rounded H data.

### Bounded relation queries

The opaque payload initially supports exact full-history membership: extract the 16 controls, check the feasible inequalities and terminal equalities, and check each of the 17 four-state blocks against its affine lift. The exact terminal set is recorded as the unique state from the objective proof. The initial profile does not promise generic support functions, arbitrary projection, uniform sampling or binary64 set export. Add those only with an explicit exact query contract and independently checked operation limits.

The verifier checks dimensions before allocation and charges rational arithmetic against versioned caps for rows, coefficient bits, operations and aggregate bytes. Cap values are calibrated against the fixed profile and frozen with the verifier version. Every cap returns refusal/inconclusive evidence; no floating-point approximation silently substitutes for exact arithmetic.

This is a deep profile module: the public strategy flow remains unchanged, while model reconstruction, rational arithmetic, row generation, lift checks and refusal policy stay behind one compiled verifier boundary. The only initial exact relation operation is whole-history membership.

## Synthesis decision

Candidate A is the base: a profile-owned 16-control rational relation, exact terminal fiber and affine joint-history lift. It best matches the one fixed B04-C profile and avoids introducing a general exact-polyhedron API before another consumer exists. Candidate B's useful contribution is explicit pre-allocation caps for dimensions, rows, coefficient growth and operations; those become part of the B04 verifier version. Candidate B's generic affine-view and Fourier–Motzkin projection machinery is not adopted because arbitrary 84D projection is unnecessary for the current contract and can grow combinatorially. A cross-family judge was unavailable: the configured candidate and judge pools contained only GPT-family models.

Candidate A's sketch needs two corrections before implementation: represent the terminal fiber equations explicitly alongside the 100 inequalities, and treat the rank-two claim as the residual map restricted to the reachable terminal affine image, not as the rank of the five-component residual map on all of `R^4`.

## Tradeoffs accepted

- We accept a profile-specific rational payload in exchange for preserving non-dyadic terminal equalities exactly.
- We accept only whole-history membership initially in exchange for a truthful 84D relation contract with bounded implementation scope.
- We accept canonical reconstruction in the verifier in exchange for not trusting producer-supplied coverage data.
- We accept versioned arithmetic caps in exchange for deterministic refusal before unbounded exact work.
- We accept that the external Python dossier remains research evidence until a compiled Strategy A proposal passes this verifier.

## Alternatives considered

- **General exact rational H-relations with affine query views.** This could serve future profiles, but it exposes a broad query and resource surface and invites unbounded projections. It loses on interface depth until a second admitted consumer exists.
- **Convert the relation to the current binary64 H representation.** This would permit reuse of generic geometry tooling but rounds the non-dyadic fiber and can change the set; it is invalid as proof authority.
- **Publish only the 16-control polytope and omit the lift.** This would leave the claimed `JointRelation` coordinates uncheckable and would not establish membership of complete state/control histories.

## Open questions and risks

- Are the proposed row, bit-growth, operation and byte caps sufficient on every supported compiler, and what checked fixture should freeze them?
- Does the existing family serialization contract allow the opaque exact-rational payload, or does a separate versioned payload schema need to precede registered publication?
- Which independently implemented exact checker should validate the compiled verifier's full relation reconstruction without treating the existing Python dossier as authority?

## Next implementation step

Implement the private canonical B04-C model reconstruction and exact terminal-fiber representation, then connect it to Strategy A's real prepare, proposal-check and post-verification publication flow.
