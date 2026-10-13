#pragma once
#include <csl/sets/data.hpp>
#include <csl/registry/provider.hpp>
#include <csl/optimization/convex_backend.hpp>
namespace csl::synthesis {
// The slice is a terminal-state set, not a joint trajectory family.
struct TerminalSlice { ProblemId problem; sets::SetData feasible; };
struct TerminalConstruction {
    SetId feasible_slice; // program bounds are scoped to this supplied slice
    EvidenceSupport support{Unestablished{}};
    std::string characterization;
    std::vector<std::string> assumptions;
};
struct TerminalMinimizers {
    Termination termination{Termination::completed};
    MathematicalOutcome outcome{MathematicalOutcome::undetermined};
    std::optional<sets::SetData> relation;
    std::optional<ProgramResult> optimization;
    std::optional<OptimumEvidence> optimum;
    TerminalConstruction construction;
    std::optional<registry::Provenance> provider;
    Diagnostics diagnostics;
};
class TerminalOptimizer {
    registry::PreparedProvider<registry::LPPort> lp_;
    registry::PreparedProvider<registry::ConvexPort> convex_;
public:
    TerminalOptimizer(registry::PreparedProvider<registry::LPPort>, registry::PreparedProvider<registry::ConvexPort>);
    TerminalMinimizers solve(const problem::ResolvedProblem&, const FamilyRequest&, const TerminalSlice&, const ExecutionContext&) const;
};
}
