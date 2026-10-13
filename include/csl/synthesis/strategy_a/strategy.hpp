#pragma once
#include <csl/reachability/nominal_forward.hpp>
#include <csl/synthesis/control_recovery.hpp>
#include <csl/synthesis/terminal_minimizers.hpp>

namespace csl::synthesis::strategy_a {
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
