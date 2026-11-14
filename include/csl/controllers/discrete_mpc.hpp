#pragma once

#include <csl/model/discrete_catalogue.hpp>
#include <csl/optimization/nominal_quadratic_history.hpp>

#include <span>
#include <optional>
#include <string>
#include <string_view>
#include <variant>

namespace csl::controllers {

enum class DomainChoice {
    source_continuous,
    explicit_continuous_relaxation,
    authored_continuous_domain
};

enum class ArrivalAvailability { not_applicable, before_decision };

enum class ObservationSemantics { ideal_full_state };

enum class EpisodePolicy { nominal_open_loop, observed_state_mpc };

// A source constraint row for one transition stage. A row means
// lower <= Hx*x[k] + Hu*u[k] + Hw*w[k] <= upper. `Hw` is folded against the
// declared forecast when compiling a nominal QP; replay inputs remain separate.
struct StageLinearConstraint {
    Matrix state_map;
    Matrix control_map;
    Matrix external_map;
    std::vector<Interval> bounds;
};

// Terminal constraints contain only x[T]; they cannot accidentally carry a
// control or external-input column at a nonexistent terminal decision.
struct TerminalStateConstraint {
    Matrix state_map;
    std::vector<Interval> bounds;
};

struct AuthoredTaskChoices {
    ProblemId problem_id;
    ProgramId program_id;
    std::string profile_id;
    std::string objective_id;
    std::string horizon_id;
    std::size_t final_stage{};
    std::vector<optimization::QuadraticHistoryStageCost> running_costs;
    QuadraticTerminal terminal_cost;
    std::vector<Vector> forecast_external;
    std::string forecast_id;
    std::vector<Vector> replay_external;
    std::string replay_id;
    std::optional<Vector> initial_state_override;
    std::optional<std::vector<Interval>> authored_state_bounds;
    std::optional<std::vector<Interval>> authored_control_bounds;
    std::vector<TerminalStateConstraint> terminal_state_constraints;
    DomainChoice domain_choice{DomainChoice::source_continuous};
    ArrivalAvailability arrival_availability{ArrivalAvailability::not_applicable};
    ObservationSemantics observation{ObservationSemantics::ideal_full_state};
};

struct TaskProvenance {
    std::string model_id;
    std::string source_reference;
    std::string profile_id;
    std::string objective_origin;
    std::string horizon_origin;
    std::string initial_origin;
    std::string forecast_id;
    std::string replay_id;
    std::string domain_choice;
    std::string observation_semantics;
};

struct NominalMpcTask {
    model::catalogue::DiscreteModelData model;
    KnownInitial initial;
    ProblemId problem_id;
    ProgramId program_id;
    std::size_t final_stage{};
    std::vector<std::vector<Interval>> state_bounds;
    std::vector<std::vector<Interval>> control_bounds;
    std::vector<StageLinearConstraint> stage_constraints;
    std::vector<std::vector<optimization::ControlPositivePartBudget>> control_positive_part_budgets;
    std::vector<TerminalStateConstraint> terminal_state_constraints;
    std::vector<optimization::QuadraticHistoryStageCost> running_costs;
    QuadraticTerminal terminal_cost;
    std::vector<Vector> forecast_external;
    std::vector<Vector> replay_external;
    ObservationSemantics observation{ObservationSemantics::ideal_full_state};
    TaskProvenance provenance;
};

struct DeferredTask {
    std::string model_id;
    std::string profile_id;
    std::string reason;
    TaskProvenance provenance;
};

using ProfileAdmission = std::variant<NominalMpcTask, DeferredTask, Diagnostics>;

// Builds source-constraint profiles from the canonical catalogue record. The
// objective, horizon, external schedules and any missing domain limits must be
// supplied by the caller; none are inferred from the model ID.
ProfileAdmission make_source_task_profile(std::string_view model_id,
                                          const AuthoredTaskChoices &choices);

// Compiles the suffix [start_stage, final_stage] for a new observation. The
// returned QP keeps the existing base history coordinates and objective
// convention; auxiliary variable mappings are explicit in its layout.
optimization::ConvexDataResult<optimization::CompiledNominalQuadraticHistory>
compile_mpc_decision(const NominalMpcTask &task, StageIndex start_stage,
                     std::span<const double> observed_state);

enum class EpisodeStop {
    completed,
    compilation_rejected,
    solver_unsupported,
    solver_not_optimal,
    simulation_stopped
};

struct MpcDecisionEvidence {
    StageIndex stage;
    Vector observed_state;
    std::optional<ProgramIdentity> program_identity;
    std::optional<WorkspaceIdentity> workspace_identity;
    std::optional<std::variant<ProgramResult, Unsupported, Diagnostics, OperationStopped>> solve;
    std::optional<ConvexSolveAttempt> attempt;
    std::optional<optimization::HistoryVariableLayout> variable_layout;
    std::vector<Vector> predicted_states;
    std::vector<Vector> predicted_controls;
    Diagnostics replay_constraint_diagnostics;
    std::optional<Vector> applied_control;
    std::optional<Vector> next_state;
};

struct MpcEpisodeEvidence {
    EpisodePolicy policy{EpisodePolicy::nominal_open_loop};
    EpisodeStop stop{EpisodeStop::completed};
    std::vector<MpcDecisionEvidence> decisions;
    std::vector<Vector> realized_states;
    std::vector<Vector> applied_controls;
    Diagnostics terminal_constraint_diagnostics;
    std::optional<double> realized_objective;
};

// Executes one finite episode to its fixed final stage. Open loop solves once;
// observed-state MPC solves the remaining suffix at each stage and applies its
// first control. Both use the same task, cost, bounds and actual replay inputs.
MpcEpisodeEvidence execute_nominal_episode(const NominalMpcTask &task, EpisodePolicy policy,
                                           ConvexWorkspace &workspace,
                                           const ExecutionContext &context);

} // namespace csl::controllers
