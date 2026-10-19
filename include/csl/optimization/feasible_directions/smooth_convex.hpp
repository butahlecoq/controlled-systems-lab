#pragma once

#include <csl/optimization/zoutendijk/projection.hpp>

#include <functional>
#include <optional>
#include <span>
#include <string>
#include <variant>

namespace csl::optimization::feasible_directions {

enum class ObjectiveClaim { declared_convex, unspecified, declared_nonconvex };

// Convexity and the gradient formula are caller assertions, not certificates.
struct SmoothObjective {
    std::string id;
    std::size_t dimension;
    ObjectiveClaim claim;
    std::function<double(std::span<const double>)> value;
    std::function<Vector(std::span<const double>)> gradient;
};

struct SmoothPolicy {
    std::size_t max_iterations{1000};
    std::size_t max_projection_iterations{1000};
    std::size_t max_backtracks{40};
    double armijo_fraction{1e-4};
    double contraction{0.5};
    double minimum_step{1e-12};
};

enum class StationarityReason { zero_projected_direction, projected_gradient_tolerance };
enum class SmoothEvidence { declared_convex_numerical_stationarity };

struct SmoothStationary {
    Vector point;
    double objective;
    Vector gradient;
    double projected_gradient_residual;
    std::size_t iterations;
    std::size_t objective_evaluations;
    StationarityReason reason;
    SmoothEvidence evidence{SmoothEvidence::declared_convex_numerical_stationarity};
};

enum class SmoothStopReason {
    cancelled, deadline_expired, resource_limit, callback_failure, numerical_failure,
    line_search_stall, operation_rejected, contract_rejected
};

struct SmoothStopped {
    SmoothStopReason reason;
    Vector last_feasible_iterate;
    std::optional<double> last_objective;
    std::size_t iterations;
    std::size_t objective_evaluations;
};

using SmoothOutcome = std::variant<SmoothStationary, SmoothStopped, Diagnostics, Unsupported>;

SmoothOutcome minimize(const LinearProgram& feasible_set, const SmoothObjective& objective,
    std::span<const double> feasible_start, LPWorkspace& projection_workspace,
    const ExecutionContext& context, SmoothPolicy policy = {});

} // namespace csl::optimization::feasible_directions
