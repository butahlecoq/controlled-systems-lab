#pragma once

#include <csl/model/hybrid_system.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <csl/optimization/linear_program.hpp>
#include <csl/registry/provider.hpp>
#include <span>

namespace csl::synthesis {

struct HybridPathProgram {
    model::HybridPath path;
    sets::SetData joint_relation;
    TerminalObjective lifted_objective;
    std::variant<LinearProgram, ConvexProgram> program;
};

using HybridPathProgramResult = std::variant<HybridPathProgram, Diagnostics, OperationStopped>;

// Builds one directly formulated program per edge path. Branch identity is
// encoded into the generated ProgramId so parallel paths remain separate.
HybridPathProgramResult build_hybrid_path_program(const model::HybridSystem&,
    const model::HybridRequest&, const model::HybridPath&, ProblemId,
    model::HybridRelationLimits, optimization::ObjectivePolicy = {},
    std::stop_token cancellation = {});

// Executes supplied branch programs independently and retains each result and
// its solver provenance. This does not compare objectives or certify a global
// optimal hybrid family.
struct HybridBranchExecution {
    model::HybridPath path;
    Termination termination{Termination::operation_rejected};
    MathematicalOutcome outcome{MathematicalOutcome::undetermined};
    std::optional<ProgramResult> result;
    std::vector<registry::Provenance> providers;
    Diagnostics diagnostics;
};

struct HybridPortfolioExecution {
    std::vector<HybridBranchExecution> branches;
    // True only if every supplied branch produced a contract-valid completed
    // solver result. This says nothing about cross-branch optimality.
    bool all_supplied_branches_completed{};
};

HybridPortfolioExecution execute_hybrid_path_programs(
    std::span<const HybridPathProgram>,
    const registry::PreparedProvider<registry::LPPort>&,
    const registry::PreparedProvider<registry::ConvexPort>&,
    const ExecutionContext&);

} // namespace csl::synthesis
