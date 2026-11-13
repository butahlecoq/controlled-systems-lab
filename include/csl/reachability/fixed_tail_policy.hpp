#pragma once

#include <csl/reachability/inner_template.hpp>
#include <csl/optimization/history_cost.hpp>
#include <csl/registry/provider.hpp>

namespace csl::reachability {

struct FixedTailHRows { Matrix inequalities; Vector upper_bounds; Matrix equalities; Vector equality_values; };
enum class FixedTailFamily { polytope, box, zonotope, parallelotope, ellipsoid };
struct TailStateLift {
    std::size_t stage;
    std::vector<Matrix> maps;
    std::vector<Vector> offsets;
};
struct FullHistoryLift {
    JointCoordinates coordinates;
    Matrix map;
    Vector offset;
};
Diagnostics check_full_history_lift(const FullHistoryLift&,std::size_t primary_dimension);

struct FixedTailModel {
    ProblemId problem;
    std::vector<LinearStage> stages;
    Vector observed;
    std::vector<FixedTailHRows> state_domains, control_domains;
    std::vector<std::vector<Interval>> input_carriers;
    FixedTailHRows full_history;
    optimization::HistoryCostProgram source_cost;
};
using FixedTailModelResult=std::variant<FixedTailModel,Diagnostic>;
FixedTailModelResult prepare_fixed_tail(const problem::ResolvedProblem&,
    const optimization::RunningControlCost&,std::size_t absolute_stage_offset);

using HistoryLiftResult=std::variant<FullHistoryLift,Diagnostic>;
HistoryLiftResult fixed_control_tail_lift(const FixedTailModel&,std::span<const double> anchor);
std::variant<TailStateLift,Diagnostic> fixed_tail_state_lift(const FixedTailModel&,
    std::span<const double> anchor,StageIndex);
std::variant<Vector,Diagnostic> recover_fixed_tail_history(const FullHistoryLift&,
    std::span<const double> current_control);

struct FixedTailWarmHistory {
    JointCoordinates coordinates;
    std::size_t absolute_stage;
    std::string source_objective_id;
    std::size_t original_horizon;
    Vector history;
};
struct FixedTailInitialization {
    Vector history;
    std::string policy;
    std::optional<std::size_t> source_stage;
};
std::variant<FixedTailInitialization,Diagnostic> initialize_fixed_tail(const FixedTailModel&,
    const std::optional<FixedTailWarmHistory>& previous={});

struct FixedTailRegion {
    StageIndex stage;
    FixedTailFamily family;
    FixedTailHRows reference;
    std::optional<InnerTemplate> inner;
    TailStateLift tail;
    Vector carrier_lower,carrier_upper;
    // Algorithmic margins for optional strict positive state coordinates.
    std::vector<std::size_t> strict_coordinates;
    std::vector<Vector> strict_margins_by_future_stage;
};
struct FixedTailSolveRequest {
    ProgramIdentity identity;
    FixedTailHRows domain;
    optimization::HistoryCostProgram source_cost;
    FullHistoryLift lift;
    std::vector<FixedTailRegion> regions;
    Vector initial_primary;
    bool feasibility_only;
    std::vector<std::size_t> strictly_positive_history_coordinates;
};
Diagnostics check_fixed_tail_solve_request(const FixedTailSolveRequest&);

struct FixedTailSolveResult {
    Vector primary,history;
    double objective;
    Vector supplied_initial_primary, supplied_initial_duals, provider_initial_primary_readback;
    std::vector<Vector> region_factors;
    std::string diagnostics;
};
using FixedTailSolveOutcome=std::variant<FixedTailSolveResult,Diagnostic,OperationStopped>;
class FixedTailOptimizerWorkspace:public ExclusiveWorkspace {
public:
    virtual FixedTailSolveOutcome solve(const FixedTailSolveRequest&,const ExecutionContext&)=0;
};
} // namespace csl::reachability

namespace csl::registry {
struct FixedTailOptimizerPort {
    using Request=reachability::FixedTailSolveRequest;
    using Workspace=reachability::FixedTailOptimizerWorkspace;
    static constexpr const char* name="fixed-tail-optimizer";
    static Request snapshot(const Request& request) { return request; }
    static reachability::FixedTailSolveOutcome run(Workspace& workspace,const Request& request,
        const ExecutionContext& context) { return workspace.solve(request,context); }
};
} // namespace csl::registry

namespace csl::reachability {
struct FixedTailPolicyRequest {
    FixedTailModel model;
    RequestId request;
    FixedTailFamily family;
    Vector shifted_initial_history;
    std::vector<std::size_t> strictly_positive_state_coordinates;
};
enum class FixedTailCommandBoundSide { lower, upper };
inline constexpr NumericalPolicy fixed_tail_command_recovery_tolerance{1e-10,1e-12};
struct FixedTailCommandAdjustment {
    StageIndex stage;
    std::size_t coordinate;
    FixedTailCommandBoundSide side;
    double raw,recovered,source_bound,allowed_absolute_adjustment;
};
struct FixedTailPolicyResult {
    ProblemId problem;
    RequestId request;
    FixedTailFamily family;
    Vector control,history,recovered_anchor_history;
    optimization::HistoryCostEvaluation cost;
    FixedTailSolveResult feasibility, reduced_argmin;
    std::vector<FixedTailCommandAdjustment> anchor_control_adjustments,command_adjustments;
    FullHistoryLift lift;
    std::vector<FixedTailRegion> regions;
    std::vector<registry::Provenance> providers;
};
struct FixedTailPolicyFailure {
    std::string phase;
    Diagnostic cause;
    std::optional<FixedTailSolveResult> feasibility,reduced_argmin;
    std::vector<FixedTailRegion> region_prefix;
    std::vector<registry::Provenance> providers;
};
using FixedTailPolicyOutcome=std::variant<FixedTailPolicyResult,FixedTailPolicyFailure,OperationStopped>;

// A complete native policy step. Only the current continuous input is free in
// the final source-cost solve. Auxiliary feasibility never minimizes source J.
FixedTailPolicyOutcome fixed_tail_policy(const FixedTailPolicyRequest&,
    const registry::PreparedProvider<registry::FixedTailOptimizerPort>&,
    const ExecutionContext&);
} // namespace csl::reachability
