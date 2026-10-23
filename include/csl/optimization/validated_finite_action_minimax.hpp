#pragma once

#include <csl/optimization/finite_action_minimax.hpp>
#include <variant>

namespace csl::optimization {

struct ValidatedFiniteActionMinimaxRequest {
    ProblemId problem;
    RequestId request;
    model::LinearSystem system;
    sets::SetData initial;
    FiniteDomain actions;
    std::vector<sets::SetData> disturbances;
    std::vector<sets::SetData> safe_sets;
    Objective objective;
};

struct ValidatedFiniteActionMinimaxLimits {
    std::size_t max_plans;
    std::size_t max_histories_per_plan;
    std::size_t max_interval_operations;
};

struct ObjectiveInterval { double lower, upper; };
struct HistoryPath {
    std::size_t initial_vertex;
    std::vector<std::size_t> disturbance_vertices;
};
enum class ConstraintKind { inequality, equality, singleton_coordinate, empty_set };
struct SafetyViolation {
    std::size_t stage;
    HistoryPath history;
    std::size_t row;
    ConstraintKind kind;
    ObjectiveInterval residual;
};
struct SafetyOverlap {
    std::size_t stage;
    HistoryPath history;
    std::size_t row;
    ConstraintKind kind;
    ObjectiveInterval residual;
};
struct SafetyMargin {
    std::size_t stage;
    std::size_t row;
    ConstraintKind kind;
    ObjectiveInterval residual_hull;
};
struct ValidatedPlanFeasible {
    std::vector<std::size_t> action_indices;
    ObjectiveInterval worst_case;
    std::size_t histories_examined;
    std::vector<SafetyMargin> stage_constraint_margins;
};
struct ValidatedPlanInfeasible {
    std::vector<std::size_t> action_indices;
    SafetyViolation witness;
};
struct ValidatedPlanUnresolved {
    std::vector<std::size_t> action_indices;
    ObjectiveInterval worst_case;
    std::size_t histories_examined;
    SafetyOverlap first_overlap;
};
using ValidatedPlanEvidence = std::variant<ValidatedPlanFeasible,
    ValidatedPlanInfeasible, ValidatedPlanUnresolved>;

class ValidatedMinimaxBounds {
public:
    const ProblemId& problem() const noexcept { return problem_; }
    const RequestId& request() const noexcept { return request_; }
    double lower() const noexcept { return lower_; }
    double upper() const noexcept { return upper_; }
    bool exact_value() const noexcept { return lower_ == upper_; }
    const std::vector<ValidatedPlanEvidence>& plans() const noexcept { return plans_; }
private:
    ValidatedMinimaxBounds(ProblemId, RequestId, double, double,
        std::vector<ValidatedPlanEvidence>);
    ProblemId problem_;
    RequestId request_;
    double lower_, upper_;
    std::vector<ValidatedPlanEvidence> plans_;
    friend struct ValidatedMinimaxBuilder;
};
class ValidatedMinimaxInfeasible {
public:
    const ProblemId& problem() const noexcept { return problem_; }
    const RequestId& request() const noexcept { return request_; }
    const std::vector<ValidatedPlanEvidence>& plans() const noexcept { return plans_; }
private:
    ValidatedMinimaxInfeasible(ProblemId problem, RequestId request,
            std::vector<ValidatedPlanEvidence> plans)
        : problem_(std::move(problem)), request_(std::move(request)), plans_(std::move(plans)) {}
    ProblemId problem_;
    RequestId request_;
    std::vector<ValidatedPlanEvidence> plans_;
    friend struct ValidatedMinimaxBuilder;
};
class ValidatedMinimaxUnresolved {
public:
    const ProblemId& problem() const noexcept { return problem_; }
    const RequestId& request() const noexcept { return request_; }
    const std::vector<ValidatedPlanEvidence>& plans() const noexcept { return plans_; }
private:
    ValidatedMinimaxUnresolved(ProblemId problem, RequestId request,
            std::vector<ValidatedPlanEvidence> plans)
        : problem_(std::move(problem)), request_(std::move(request)), plans_(std::move(plans)) {}
    ProblemId problem_;
    RequestId request_;
    std::vector<ValidatedPlanEvidence> plans_;
    friend struct ValidatedMinimaxBuilder;
};
struct ValidatedMinimaxEmptyCatalogue {};
struct ValidatedMinimaxNoScenarios {};
using ValidatedFiniteActionMinimaxOutcome = std::variant<ValidatedMinimaxBounds,
    ValidatedMinimaxInfeasible, ValidatedMinimaxUnresolved,
    ValidatedMinimaxEmptyCatalogue, ValidatedMinimaxNoScenarios,
    Unsupported, OperationStopped>;

ValidatedFiniteActionMinimaxOutcome validated_finite_action_minimax(
    const ValidatedFiniteActionMinimaxRequest&, ValidatedFiniteActionMinimaxLimits,
    const ExecutionContext& context = {});

} // namespace csl::optimization
