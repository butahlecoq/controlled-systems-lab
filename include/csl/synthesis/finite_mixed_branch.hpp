#pragma once

#include <csl/problem/resolved_problem.hpp>
#include <csl/registry/registry.hpp>
#include <csl/synthesis/contracts.hpp>
#include <csl/synthesis/finite_action_histories.hpp>
#include <csl/sets/data.hpp>

#include <cstddef>
#include <optional>
#include <utility>
#include <variant>
#include <vector>

namespace csl::synthesis {

struct FiniteMixedBranchCoordinates {
    JointCoordinates source;
    JointCoordinates continuous_subproblem;
    std::vector<Vector> discrete_controls;
};

struct FiniteMixedBranchProblem {
    FiniteActionHistory history;
    Problem problem;
    FiniteMixedBranchCoordinates coordinates;
};

using FiniteMixedBranchOutcome = std::variant<FiniteMixedBranchProblem, Diagnostics>;
using FiniteMixedBranchRelationOutcome = std::variant<sets::SetData, Diagnostics>;

struct FailedFiniteMixedBranch {
    FiniteActionHistory history;
    Diagnostics diagnostics;
};

// Ordered outcomes retain each history even when branch specialization refuses it.
using FiniteMixedBranchEntry = std::variant<FiniteMixedBranchProblem, FailedFiniteMixedBranch>;

struct FiniteMixedBranchPrefix {
    std::vector<FiniteMixedBranchEntry> entries;
    bool complete{}; // All catalogue-index histories were emitted, not all branches feasible.
};

// One evaluated branch preserves either its prepared branch and objective or
// the original preparation refusal. A missing objective is valid only for a
// refused branch; it must never be interpreted as a zero-cost candidate.
struct FiniteMixedBranchEvaluation {
    FiniteMixedBranchEntry branch;
    std::optional<double> objective;
    // The branch's full continuous solution relation, in continuous-subproblem
    // joint coordinates. It stays attached to its catalogue-index history.
    std::optional<sets::SetData> continuous_relation;
    // Present only when the continuous branch result passed the registered
    // complete-family verifier. The lifted source-coordinate relation keeps
    // the finite action history fixed by catalogue index.
    std::optional<OptimalFamily> verified_continuous_family;
    std::optional<sets::SetData> source_relation;

    FiniteMixedBranchEvaluation(FiniteMixedBranchEntry branch_value,
        std::optional<double> objective_value,
        std::optional<sets::SetData> continuous_relation_value = {},
        std::optional<OptimalFamily> verified_family_value = {},
        std::optional<sets::SetData> source_relation_value = {})
        : branch(std::move(branch_value)), objective(objective_value),
          continuous_relation(std::move(continuous_relation_value)),
          verified_continuous_family(std::move(verified_family_value)),
          source_relation(std::move(source_relation_value)) {}
};

struct FiniteMixedBranchPortfolio {
    std::vector<FiniteMixedBranchEvaluation> evaluations;
    // These minima are over the supplied evaluations. They are globally
    // minimal only when complete is true; otherwise unseen histories may win.
    std::vector<std::size_t> optimal_evaluation_indices;
    std::optional<double> optimum;
    bool enumeration_complete{}; // Every history was evaluated without an execution stop.
    bool complete{}; // Enumeration completed and every history has a valid objective.
    // True when every tolerance-selected branch has a relation payload. This
    // does not certify family validity, objective optimality, or completeness.
    bool all_selected_relations_present{};
};

using FiniteMixedBranchPortfolioOutcome = std::variant<FiniteMixedBranchPortfolio, Diagnostics>;

struct FiniteMixedBranchLimits {
    // Bounds the retained attempt/evaluation vector, not just one cursor page.
    std::size_t max_branch_evaluations{256};
    // Bounds both the continuous and source-coordinate H relations retained per run.
    std::size_t max_retained_relation_rows{100'000};
    // Counts dense matrix values and right-hand-side values in both relations.
    std::size_t max_retained_relation_scalars{10'000'000};
};

struct FiniteMixedBranchSolveRequest {
    StrategyConfiguration strategy;
    FamilyRequest family;
    problem::ResolutionContext resolution;
    std::size_t branches_per_page{64};
    double near_optimal_tolerance{};
    FiniteMixedBranchLimits limits{};
};

struct FiniteMixedBranchSolveResult {
    FiniteMixedBranchPortfolio portfolio;
    bool history_enumeration_complete{}; // Cursor emitted every history, including stopped attempts.
    bool every_branch_solved{};
    double effective_tie_tolerance{};
    std::optional<OperationStopped> stop;
    std::size_t retained_relation_rows{};
    std::size_t retained_relation_scalars{};
};

using FiniteMixedBranchSolveOutcome = std::variant<FiniteMixedBranchSolveResult, Diagnostics>;

// Streams prepared branches in catalogue-index order without materializing the full product.
class FiniteMixedBranchCursor {
    problem::ResolvedProblem source_;
    FiniteActionHistoryCursor histories_;

    FiniteMixedBranchCursor(problem::ResolvedProblem, FiniteActionHistoryCursor);

public:
    static std::variant<FiniteMixedBranchCursor, Diagnostics> prepare(
        const problem::ResolvedProblem&);

    // A zero-sized request leaves the continuation position unchanged.
    FiniteMixedBranchPrefix take_prefix(std::size_t max_branches);
};

// Fixes one complete catalogue-index history in a nominal discrete-time
// mixed-control problem and returns the equivalent continuous subproblem.
// The mapping records how a later joint relation returns to source coordinates.
FiniteMixedBranchOutcome prepare_finite_mixed_branch(
    const problem::ResolvedProblem&, const FiniteActionHistory&);

// Embeds an H-represented continuous branch relation into the source problem's
// canonical joint coordinates and fixes every discrete control coordinate.
FiniteMixedBranchRelationOutcome lift_finite_mixed_branch_relation(
    const FiniteMixedBranchProblem&, const sets::SetData&);

// Selects every minimal evaluated branch within the caller's tolerance,
// without reordering catalogue histories or dropping refusals. The result is
// a global minimum only when enumeration_complete is true.
// The selector does not solve a branch, infer a continuous family, or treat a
// convex relaxation as a discrete candidate.
FiniteMixedBranchPortfolioOutcome select_finite_mixed_branch_portfolio(
    std::vector<FiniteMixedBranchEvaluation>, bool enumeration_complete,
    double near_optimal_tolerance);

// Resolves every finite-action history, solves its continuous subproblem with
// the requested registered strategy, and retains only registry-verified
// complete branch families. The returned portfolio is globally complete only
// when enumeration and every branch solve succeeded.
FiniteMixedBranchSolveOutcome solve_finite_mixed_branch_portfolio(
    const problem::ResolvedProblem&, const registry::StrategyRegistry&,
    const FiniteMixedBranchSolveRequest&, const ExecutionContext& = {});

} // namespace csl::synthesis
