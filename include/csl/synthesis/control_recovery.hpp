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
ControlRecoveryOutcome recover_joint_history(const problem::ResolvedProblem&,
    const sets::SetData& terminal_relation);

} // namespace csl::synthesis
