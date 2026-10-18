#pragma once

#include <csl/model/hybrid_system.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <csl/optimization/linear_program.hpp>

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

} // namespace csl::synthesis
