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
    model::HybridRelationLimits relation_limits;
    std::vector<model::HybridRelationOperationRecord> relation_operations;
};

using HybridPortfolioProgramResult = std::variant<std::vector<HybridPathProgram>, Diagnostics,
    OperationStopped, model::HybridPathCompositionFailureReport>;

using HybridPathProgramResult = std::variant<HybridPathProgram, Diagnostics, OperationStopped,
    model::HybridPathCompositionFailureReport>;

// Builds one directly formulated program per edge path. Branch identity is
// encoded into the generated ProgramId so parallel paths remain separate.
HybridPathProgramResult build_hybrid_path_program(const model::HybridSystem&,
    const model::HybridRequest&, const model::HybridPath&, ProblemId,
    model::HybridRelationLimits, optimization::ObjectivePolicy = {},
    std::stop_token cancellation = {});

// Enumerates and builds the complete allowed branch portfolio transactionally:
// no partial branch-program list is returned on a limit, capability, or stop.
HybridPortfolioProgramResult build_hybrid_portfolio_programs(const model::HybridSystem&,
    const model::HybridRequest&, ProblemId, model::HybridEnumerationLimits,
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

// Objective-bound comparison is deliberately separate from complete-family
// verification. The returned paths are branches that cannot yet be excluded
// from the global minimum using the supplied numerical bounds; they are not
// certified minimizer loci.
struct HybridPortfolioBoundSource {
    model::HybridPath path;
    ProgramObjectiveBound bound;
};
struct HybridPortfolioObjectiveBounds {
    double global_lower_bound;
    double global_upper_bound;
    std::vector<model::HybridPath> potentially_optimal_paths;
    std::vector<HybridPortfolioBoundSource> global_lower_bound_sources;
    std::vector<HybridPortfolioBoundSource> global_upper_bound_sources;
    NumericalPolicy policy;
};
struct HybridPortfolioObjectiveIncomplete {
    std::vector<std::size_t> branches_without_comparable_bounds;
};
using HybridPortfolioObjectiveAnalysis = std::variant<HybridPortfolioObjectiveBounds,
    HybridPortfolioObjectiveIncomplete, Diagnostics>;

HybridPortfolioObjectiveAnalysis compare_hybrid_portfolio_objective_bounds(
    std::span<const HybridPathProgram>, const HybridPortfolioExecution&, NumericalPolicy);

// Builds the affine optimal-face equations implied by a feasible optimizer
// anchor. This remains a candidate until the selected family verifier accepts
// the anchor's global optimality and the face's complete coverage.
struct HybridPathOptimalFaceCandidate {
    model::HybridPath path;
    sets::SetData relation;
    Vector anchor;
    ProgramResult solver_result;
    std::vector<registry::Provenance> providers;
    std::string characterization;
    std::vector<std::string> assumptions;
};
using HybridPathOptimalFaceResult = std::variant<HybridPathOptimalFaceCandidate,
    Diagnostics, OperationStopped>;

HybridPathOptimalFaceResult build_hybrid_path_optimal_face_candidate(
    const HybridPathProgram&, const ProgramResult&, NumericalPolicy,
    std::stop_token cancellation = {});

struct HybridPortfolioOptimalFaceCandidates {
    HybridPortfolioObjectiveBounds objective_bounds;
    std::vector<HybridPathOptimalFaceCandidate> branches;
};
using HybridPortfolioOptimalFaceAnalysis = std::variant<HybridPortfolioOptimalFaceCandidates,
    HybridPortfolioObjectiveIncomplete, Diagnostics, OperationStopped>;

// Transactionally assembles a candidate face for every branch that objective
// bounds cannot exclude. The result retains path and provider provenance but
// is not a verified complete globally optimal family.
HybridPortfolioOptimalFaceAnalysis assemble_hybrid_portfolio_optimal_face_candidates(
    std::span<const HybridPathProgram>, const HybridPortfolioExecution&, NumericalPolicy,
    std::stop_token cancellation = {});

HybridPortfolioExecution execute_hybrid_path_programs(
    std::span<const HybridPathProgram>,
    const registry::PreparedProvider<registry::LPPort>&,
    const registry::PreparedProvider<registry::ConvexPort>&,
    const ExecutionContext&);

} // namespace csl::synthesis
