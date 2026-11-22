#pragma once

#include <csl/synthesis/contracts.hpp>

#include <csl/problem/resolved_problem.hpp>

namespace csl::synthesis {

// A single H-polyhedral relation in canonical [x0,...,xT,u0,...,u(T-1)]
// coordinates. It retains the correlations needed to recover entire histories.
struct JointHistoryRelation {
    JointCoordinates coordinates;
    sets::SetData relation;
};

using ControlRecoveryOutcome = std::variant<JointHistoryRelation, Diagnostics>;

// Constructs the feasible preimage of the supplied terminal-state relation.
// This first implementation supports discrete nominal open-loop systems with
// a known initial point, continuous controls, no external input, and native
// H/singleton/empty/universal polyhedral sets. No variables are projected out.
// Binary64 row assembly is not a numerical or validated completeness proof.
ControlRecoveryOutcome recover_joint_history(const problem::ResolvedProblem &,
                                             const sets::SetData &terminal_relation);

struct HistoryIndexRange {
    std::size_t begin, end; // Half-open range in the canonical H relation.
    bool operator==(const HistoryIndexRange &) const = default;
};

struct HistoryPrefixProjection {
    StageIndex stage;
    HistoryIndexRange state_columns;
    std::vector<HistoryIndexRange> inequality_rows;
    std::vector<HistoryIndexRange> equality_rows;
};

struct LiftedHistoryProjections {
    JointHistoryRelation history;
    // One view per stage. Project the listed rows onto state_columns for the
    // forward set. Project all rows onto the same columns for the
    // forward-relevant terminal-feasible set and its intersection with forward.
    std::vector<HistoryPrefixProjection> prefixes;
};

using LiftedHistoryProjectionOutcome = std::variant<LiftedHistoryProjections, Diagnostics>;

// Construct shared lifted descriptions of the stage marginals of the stored
// affine problem. The views need no variable elimination or copied H matrices.
LiftedHistoryProjectionOutcome
recover_lifted_history_projections(const problem::ResolvedProblem &,
                                   const sets::SetData &terminal_relation);

} // namespace csl::synthesis
