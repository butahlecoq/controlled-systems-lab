#pragma once

#include <csl/synthesis/contracts.hpp>
#include <csl/reachability/nominal_forward.hpp>
#include <csl/synthesis/control_recovery.hpp>
#include <csl/synthesis/terminal_minimizers.hpp>
#include <csl/artifacts/run_statistics.hpp>

namespace csl::synthesis::strategy_a {
// OBS-03 plan slots owned by Strategy A. Callers who enable timing must include
// these IDs in the CollectionPlan, rooted/nested as described in
// docs/contracts/timing-collector.md.
namespace timing {
inline constexpr artifacts::SpanId run{0};
inline constexpr artifacts::SpanId forward{1};
inline constexpr artifacts::SpanId feasible_preimage{2};
inline constexpr artifacts::SpanId terminal_optimization{3};
inline constexpr artifacts::SpanId terminal_preimage{4};
}
enum class PreimageTarget { forward_terminal_slice, terminal_candidate };
// Scoped derivation evidence: terminal-program bounds concern the supplied
// forward slice, not an independently verified original-problem optimum.
struct CandidateHistory final : JointRelationPayload {
    PreimageTarget target{PreimageTarget::forward_terminal_slice};
    JointHistoryRelation history;
    reachability::ForwardTube forward;
    std::optional<TerminalMinimizers> terminal;
    CandidateHistory(PreimageTarget,JointHistoryRelation,reachability::ForwardTube,
        std::optional<TerminalMinimizers>);
};
using Providers = registry::CheckedProviders<registry::GeometryPort,
    registry::GeometryPort,registry::ConversionPort,registry::LPPort,registry::ConvexPort>;

// Provider order: equivalent H projection, equivalent V affine/sum, equivalent
// H conversion, LP, convex. Borrows checked registrations until strategy prepare
// snapshots them; thereafter registries can be destroyed. No local registry.
// First profile: nominal_open_loop, candidate_relaxation, numerical, native H.
// Exact/partial claims and caller materialization limits are unsupported until
// coverage and capacity semantics are reviewed. Singular A needs no inverse.
registry::StrategyRegistration make_registration(Providers);
} // namespace csl::synthesis::strategy_a
