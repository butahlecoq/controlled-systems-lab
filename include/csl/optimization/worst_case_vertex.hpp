#pragma once

#include <csl/optimization/objectives.hpp>
#include <csl/sets/data.hpp>

namespace csl::optimization {

struct WorstCaseValue {
    double value;
    Vector maximizer;
    std::size_t evaluated_vertices;
    Assurance assurance;
};
struct WorstCaseEmpty {};
using WorstCaseVertexOutcome = std::variant<WorstCaseValue, WorstCaseEmpty,
    Unsupported, OperationStopped>;

// Numerical reference for a complete bounded V polytope and a convex terminal
// objective. Redundant V rows are evaluated. Quadratic convexity relies on the
// Objective's numerical PSD check; no validated global bound is implied.
WorstCaseVertexOutcome worst_case_vertex(const sets::SetData& domain,
    const Objective& objective, std::size_t max_vertices,
    const ExecutionContext& context = {});

} // namespace csl::optimization
