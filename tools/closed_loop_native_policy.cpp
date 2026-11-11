#include <csl/model/linear_system.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/optimization/finite_action_nominal.hpp>
#include <csl/optimization/objectives.hpp>
#include <csl/reachability/nominal_predecessor.hpp>
#include <csl/registry/registry.hpp>
#include <csl/sets/data.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <variant>

namespace {
using Json = nlohmann::json;
using namespace csl;

template<class T> T take(std::variant<T, Diagnostic> result, const char* field) {
    if(const auto* error = std::get_if<Diagnostic>(&result))
        throw std::runtime_error(std::string(field) + ": " + error->explanation);
    return std::get<T>(std::move(result));
}
template<class T> T take(std::variant<T, Diagnostic, OperationStopped> result, const char* field) {
    if(const auto* error = std::get_if<Diagnostic>(&result))
        throw std::runtime_error(std::string(field) + ": " + error->explanation);
    if(const auto* stopped = std::get_if<OperationStopped>(&result))
        throw std::runtime_error(std::string(field) + ": " + stopped->diagnostics);
    return std::get<T>(std::move(result));
}

Matrix matrix(const Json& value) {
    const auto rows = value.size();
    const auto cols = rows == 0 ? 0 : value.at(0).size();
    Vector data;
    data.reserve(rows * cols);
    for(const auto& row : value) {
        if(row.size() != cols) throw std::runtime_error("ragged matrix");
        for(const auto& entry : row) data.push_back(entry.get<double>());
    }
    return {rows, cols, std::move(data)};
}

Vector vector(const Json& value) {
    return value.get<Vector>();
}

Json matrix_json(std::size_t rows, std::size_t cols, const auto& at) {
    Json result = Json::array();
    for(std::size_t row = 0; row < rows; ++row) {
        Json values = Json::array();
        for(std::size_t col = 0; col < cols; ++col) values.push_back(at(row, col));
        result.push_back(std::move(values));
    }
    return result;
}

Json set_json(const sets::SetData& set) {
    return std::visit([&](const auto& repr) -> Json {
        using T = std::decay_t<decltype(repr)>;
        if constexpr(std::is_same_v<T, sets::VRepresentation>) {
            const auto& vertices = repr.vertices;
            return {{"representation", "polytope-v"},
                {"vertices", matrix_json(vertices.rows(), vertices.cols(),
                    [&](std::size_t i, std::size_t j) { return vertices(i, j); })}};
        } else if constexpr(std::is_same_v<T, sets::HRepresentation>) {
            const auto& rows = repr.inequalities;
            Json bounds = Json::array();
            for(const auto item : repr.upper_bounds.values()) bounds.push_back(item);
            Json equality_values = Json::array();
            for(const auto item : repr.equality_values.values()) equality_values.push_back(item);
            return {{"representation", "polytope-h"},
                {"inequalities", matrix_json(rows.rows(), rows.cols(),
                    [&](std::size_t i, std::size_t j) { return rows(i, j); })},
                {"upper_bounds", std::move(bounds)},
                {"equalities", matrix_json(repr.equalities.rows(), repr.equalities.cols(),
                    [&](std::size_t i, std::size_t j) { return repr.equalities(i, j); })},
                {"equality_values", std::move(equality_values)}};
        } else if constexpr(std::is_same_v<T, sets::SingletonRepresentation>) {
            Json point = Json::array();
            for(const auto item : repr.point.values()) point.push_back(item);
            return {{"representation", "singleton"}, {"point", std::move(point)}};
        } else if constexpr(std::is_same_v<T, sets::UniversalRepresentation>) {
            return {{"representation", "universal"}};
        } else {
            return {{"representation", "empty"}};
        }
    }, set.representation());
}

sets::SetData safe_box(const Json& bounds, std::size_t dimension, const std::string& id) {
    std::size_t count = 0;
    for(const auto& bound : bounds) if(!bound.is_null()) count += 2;
    if(count == 0) return take(sets::make_universal({{id}, dimension, {}}), "universal-safe-set");
    Matrix a{count, dimension, Vector(count * dimension, 0.0)};
    Vector b; b.reserve(count);
    std::size_t row = 0;
    for(std::size_t coordinate = 0; coordinate < dimension; ++coordinate) {
        const auto& bound = bounds.at(coordinate);
        if(bound.is_null()) continue;
        const double lower = bound.at(0).get<double>();
        const double upper = bound.at(1).get<double>();
        a.values[row * dimension + coordinate] = 1.0; b.push_back(upper); ++row;
        a.values[row * dimension + coordinate] = -1.0; b.push_back(-lower); ++row;
    }
    const auto empty_matrix = take(numeric::snapshot(Matrix{0, dimension, {}}), "empty-equalities");
    const auto empty_vector = take(numeric::snapshot_vector(Vector{}), "empty-equality-values");
    return take(sets::make_h({{id}, dimension, {}},
        {take(numeric::snapshot(a), "safe-inequalities"),
         take(numeric::snapshot_vector(b), "safe-bounds"), empty_matrix, empty_vector}), "bounded-safe-set");
}

optimization::Objective terminal_objective(const Json& spec, std::size_t state_dimension) {
    if(spec.at("kind") == "quadratic") {
        const auto q = matrix(spec.at("Q"));
        const auto linear = vector(spec.at("linear"));
        const auto offset = spec.at("offset").get<double>();
        if(q.rows != state_dimension || q.cols != state_dimension || linear.size() != state_dimension)
            throw std::runtime_error("terminal quadratic dimension mismatch");
        return take(optimization::snapshot(QuadraticTerminal{q, linear, offset}),
            "terminal-quadratic");
    }
    const auto map = matrix(spec.at("map"));
    const auto target = vector(spec.at("target"));
    const auto weights = vector(spec.at("weights"));
    if(map.cols != state_dimension || map.rows != target.size())
        throw std::runtime_error("terminal norm dimension mismatch");
    return take(optimization::snapshot(ResidualNormTerminal{map, target, weights}),
        "terminal-euclidean-norm");
}

optimization::RunningControlCost running_cost(const Json& spec, std::size_t full_horizon,
    std::size_t control_dimension) {
    optimization::RunningControlCost result;
    result.objective_id = spec.at("objective_id").get<std::string>();
    result.original_horizon = full_horizon;
    for(const auto& stage_json : spec.at("stages")) {
        optimization::AbsoluteStageControlCost stage{stage_json.at("stage").get<std::size_t>(), {}};
        for(const auto& term : stage_json.at("terms")) {
            const auto kind = term.at("kind").get<std::string>();
            if(kind == "quadratic") {
                auto reference = vector(term.at("reference"));
                auto scales = vector(term.at("scales"));
                auto weights = vector(term.at("weights"));
                if(reference.size() != control_dimension || scales.size() != control_dimension ||
                   weights.size() != control_dimension) throw std::runtime_error("running quadratic dimension mismatch");
                stage.terms.emplace_back(optimization::QuadraticControlPenalty{
                    std::move(reference), std::move(scales), std::move(weights),
                    term.at("coefficient").get<double>(), full_horizon});
            } else if(kind == "euclidean") {
                auto map = matrix(term.at("map"));
                auto offset = vector(term.at("offset"));
                stage.terms.emplace_back(optimization::EuclideanControlPenalty{
                    std::move(map), std::move(offset), term.at("coefficient").get<double>()});
            } else throw std::runtime_error("unknown running control-cost term");
        }
        result.stages.push_back(std::move(stage));
    }
    return result;
}

Json trace_json(const optimization::NominalTrackSelected& selected) {
    Json stages = Json::array();
    std::string representation;
    std::string relation;
    std::visit([&](const auto& trace) {
        using T = std::decay_t<decltype(trace)>;
        if constexpr(std::is_same_v<T, reachability::FixedPlanReachable>) {
            representation = "exact-polytope"; relation = "equivalent";
            for(const auto& set : trace.stages) stages.push_back(set_json(set));
        } else if constexpr(std::is_same_v<T, reachability::FinitePlanBoxTrace>) {
            representation = "box"; relation = "outer";
            for(const auto& stage : trace.stages) stages.push_back({{"lower", stage.lower}, {"upper", stage.upper}});
        } else if constexpr(std::is_same_v<T, reachability::FinitePlanZonotopeTrace>) {
            representation = "zonotope"; relation = "outer";
            for(const auto& stage : trace.stages) stages.push_back({{"center", stage.center},
                {"generators", matrix_json(stage.generators.rows, stage.generators.cols,
                    [&](std::size_t i, std::size_t j) { return stage.generators.values[i * stage.generators.cols + j]; })}});
        } else if constexpr(std::is_same_v<T, reachability::FinitePlanParallelotopeTrace>) {
            representation = "parallelotope"; relation = "outer";
            for(const auto& stage : trace.stages) stages.push_back({{"lower", stage.lower}, {"upper", stage.upper}});
        } else {
            representation = "ellipsoid"; relation = "outer";
            for(const auto& stage : trace.stages) stages.push_back({{"center", stage.center}, {"radii", stage.radii}});
        }
    }, selected.selected_trace);
    return {{"role", "fixed-plan-trajectory-enclosure"}, {"representation", representation},
        {"relation", relation}, {"assurance", "numerical"}, {"stages", std::move(stages)}};
}

bool contains_with_tolerance(const sets::SetData& set, const Vector& point,
                             double absolute_tolerance = 1e-9,
                             double relative_tolerance = 1e-10) {
    if(point.size() != set.metadata()->set.dimension) return false;
    const auto representation = set.representation();
    if(const auto* singleton = std::get_if<sets::SingletonRepresentation>(&representation)) {
        if(singleton->point.size() != point.size()) return false;
        for(std::size_t i = 0; i < point.size(); ++i)
            if(std::abs(point[i] - singleton->point[i]) > absolute_tolerance +
               relative_tolerance * std::max(std::abs(point[i]), std::abs(singleton->point[i]))) return false;
        return true;
    }
    if(std::holds_alternative<sets::UniversalRepresentation>(representation)) return true;
    if(std::holds_alternative<sets::EmptyRepresentation>(representation)) return false;
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if(!h) return false;
    for(std::size_t row = 0; row < h->inequalities.rows(); ++row) {
        double lhs = 0.0, scale = std::abs(h->upper_bounds[row]);
        for(std::size_t col = 0; col < point.size(); ++col) {
            const double term = h->inequalities(row, col) * point[col];
            lhs += term; scale += std::abs(term);
        }
        if(lhs > h->upper_bounds[row] + absolute_tolerance + relative_tolerance * scale) return false;
    }
    for(std::size_t row = 0; row < h->equalities.rows(); ++row) {
        double lhs = 0.0, scale = std::abs(h->equality_values[row]);
        for(std::size_t col = 0; col < point.size(); ++col) {
            const double term = h->equalities(row, col) * point[col];
            lhs += term; scale += std::abs(term);
        }
        if(std::abs(lhs - h->equality_values[row]) > absolute_tolerance + relative_tolerance * scale) return false;
    }
    return true;
}

double absolute_stage_cost(const optimization::RunningControlCost& cost,
                           std::size_t absolute_stage, const Vector& control) {
    double value = 0.0;
    for(const auto& stage : cost.stages) {
        if(stage.stage != absolute_stage) continue;
        for(const auto& term : stage.terms) {
            std::visit([&](const auto& penalty) {
                using T = std::decay_t<decltype(penalty)>;
                if constexpr(std::is_same_v<T, optimization::QuadraticControlPenalty>) {
                    if(penalty.reference.size() != control.size())
                        throw std::runtime_error("recovery cost/control dimensions differ");
                    for(std::size_t i = 0; i < control.size(); ++i) {
                        const double residual = (control[i] - penalty.reference[i]) / penalty.scales[i];
                        value += penalty.coefficient / static_cast<double>(penalty.normalization_horizon) *
                            penalty.weights[i] * residual * residual;
                    }
                } else {
                    if(penalty.map.cols != control.size())
                        throw std::runtime_error("recovery norm/control dimensions differ");
                    double squared = 0.0;
                    for(std::size_t row = 0; row < penalty.map.rows; ++row) {
                        double residual = penalty.offset[row];
                        for(std::size_t col = 0; col < control.size(); ++col)
                            residual += penalty.map.values[row * penalty.map.cols + col] * control[col];
                        squared += residual * residual;
                    }
                    value += penalty.coefficient * std::sqrt(squared);
                }
            }, term);
        }
    }
    return value;
}

struct FirstStepRecovery {
    Vector control;
    double running_cost;
    Json predecessor_set;
    Json invocation;
    Json receipt;
};

FirstStepRecovery recover_first_action_2d(const Json& in,
        const optimization::FiniteActionNominalRequest& request,
        const optimization::NominalTrackSelected& selected) {
    const auto dimension = request.initial_state.size();
    if(dimension != 2 || selected.replay.states.size() < 2 || selected.replay.controls.empty())
        throw std::runtime_error("2D first-action predecessor recovery needs one complete transition");
    const auto dynamics_value = request.system.stage({0});
    if(const auto* error = std::get_if<Diagnostic>(&dynamics_value))
        throw std::runtime_error("predecessor dynamics: " + error->explanation);
    const auto& dynamics = std::get<model::DynamicsStage>(dynamics_value);
    Matrix a{dimension, dimension, Vector(dimension * dimension)};
    Matrix b{dimension, request.actions.dimension, Vector(dimension * request.actions.dimension)};
    Vector offset(dimension);
    for(std::size_t row = 0; row < dimension; ++row) {
        offset[row] = dynamics.offset[row];
        for(std::size_t col = 0; col < dimension; ++col)
            a.values[row * dimension + col] = dynamics.A(row, col);
        for(std::size_t col = 0; col < request.actions.dimension; ++col)
            b.values[row * request.actions.dimension + col] = dynamics.B(row, col);
    }

    Vector lower(request.actions.dimension, std::numeric_limits<double>::infinity());
    Vector upper(request.actions.dimension, -std::numeric_limits<double>::infinity());
    for(const auto& action : request.actions.catalogue)
        for(std::size_t col = 0; col < action.size(); ++col) {
            lower[col] = std::min(lower[col], action[col]);
            upper[col] = std::max(upper[col], action[col]);
        }
    Json control_bounds = Json::array();
    for(std::size_t col = 0; col < lower.size(); ++col) control_bounds.push_back({lower[col], upper[col]});
    auto controls = safe_box(control_bounds, request.actions.dimension, "finite-action-hull");
    auto target = take(sets::make_singleton({{"selected-first-step-target"}, dimension, {}},
        take(numeric::snapshot_vector(selected.replay.states[1]), "predecessor-target")), "predecessor-target-set");

    auto registration = geometry::polyhedral::make_projection_registration();
    registry::Registry<registry::GeometryPort> registry;
    if(const auto error = registry.add(registration))
        throw std::runtime_error("predecessor projection registration: " +
            (error->diagnostics.empty() ? std::string("registration rejected") : error->diagnostics.front().explanation));
    registry::Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.h"};
    requirements.output.relation = SetRelation::equivalent;
    const registry::Method method{registration.identity.id, registration.identity.version};
    auto provider_result = registry::prepare_provider(
        registry::select_provider(registry, method, requirements));
    if(!std::holds_alternative<registry::PreparedProvider<registry::GeometryPort>>(provider_result))
        throw std::runtime_error("predecessor projection provider rejected the H relation");
    auto provider = std::get<registry::PreparedProvider<registry::GeometryPort>>(std::move(provider_result));
    reachability::NominalPredecessorRequest predecessor_request{
        {{in.at("problem_id").get<std::string>()},
         {in.at("request_id").get<std::string>() + "/first-step-predecessor"},
         {in.at("request_id").get<std::string>() + "/selected-next-state"}},
        request.admissible_states.front().as_handle(), controls.as_handle(), target.as_handle(),
        std::move(a), std::move(b), std::move(offset)};
    auto prepared_result = reachability::prepare_nominal_predecessor(predecessor_request, provider);
    if(!std::holds_alternative<reachability::PreparedNominalPredecessor>(prepared_result))
        throw std::runtime_error("nominal predecessor did not admit the source-bound 2D request");
    auto outcome = std::get<reachability::PreparedNominalPredecessor>(std::move(prepared_result)).run({});
    if(!std::holds_alternative<reachability::NominalPredecessorResult>(outcome))
        throw std::runtime_error("nominal predecessor failed for selected first-step target");
    auto predecessor = std::get<reachability::NominalPredecessorResult>(std::move(outcome));
    auto predecessor_data = take(sets::from_handle(predecessor.result.output), "predecessor-output");
    if(!contains_with_tolerance(predecessor_data, request.initial_state))
        throw std::runtime_error("observed state is outside the selected-plan predecessor set");

    const auto target_data = target;
    std::vector<Vector> feasible_catalogue_actions;
    for(const auto& action : request.actions.catalogue) {
        Vector next(dimension);
        for(std::size_t row = 0; row < dimension; ++row) {
            next[row] = predecessor_request.offset[row];
            for(std::size_t col = 0; col < dimension; ++col)
                next[row] += dynamics.A(row, col) * request.initial_state[col];
            for(std::size_t col = 0; col < action.size(); ++col)
                next[row] += dynamics.B(row, col) * action[col];
        }
        if(contains_with_tolerance(target_data, next) &&
           contains_with_tolerance(request.admissible_states[1], next))
            feasible_catalogue_actions.push_back(action);
    }
    const Vector& selected_control = selected.replay.controls.front();
    const auto recovered = std::find(feasible_catalogue_actions.begin(), feasible_catalogue_actions.end(), selected_control);
    if(recovered == feasible_catalogue_actions.end())
        throw std::runtime_error("selected first action has no finite-catalogue predecessor witness");
    const double stage_cost = absolute_stage_cost(request.running_cost,
        request.absolute_stage_offset, *recovered);
    const auto& provenance = predecessor.projection_provider;
    const std::string provider_id = provenance.actual_module && provenance.actual_version ?
        provenance.actual_module->value + "@" + *provenance.actual_version : "unresolved-provider";
    return {*recovered, stage_cost,
        {{"role", "one-step-feasible-state-predecessor"}, {"representation", "polytope-h"},
         {"relation", "equivalent"}, {"assurance", "numerical"},
         {"support", "unestablished"}, {"set", set_json(predecessor_data)}},
        {{"module_id", "csl::reachability::prepare_nominal_predecessor"},
         {"operation", "one-step existential-control state predecessor"},
         {"provider", provider_id}, {"profile_id", in.at("controller_id")},
         {"projection_provider", provider_id}},
        {{"schema", "csl.closed-loop.native-first-step-recovery/1"},
         {"predecessor_request", predecessor_request.identity.request.value},
         {"observed_state_in_predecessor", true},
         {"selected_target_state", selected.replay.states[1]},
         {"selected_control", *recovered},
         {"finite_catalogue_witness_count", feasible_catalogue_actions.size()},
         {"running_cost_objective_id", request.running_cost.objective_id},
         {"absolute_stage", request.absolute_stage_offset},
         {"original_horizon", request.running_cost.original_horizon},
         {"selected_stage_running_cost", stage_cost},
         {"predecessor_assurance", "numerical with unestablished support"},
         {"replay_check", "affine one-step state lies in selected singleton target and next-state bounds"}}};
}

Json query(const Json& in) {
    const auto& coefficient_stages = in.at("predictor_stages");
    const auto horizon = coefficient_stages.size();
    const auto initial = vector(in.at("observed_physical_state"));
    const auto dimension = initial.size();
    if(horizon == 0 || dimension == 0) throw std::runtime_error("nonempty state and prediction tail are required");
    const auto& actions_json = in.at("actions");
    if(actions_json.empty()) throw std::runtime_error("finite action domain is empty");
    const auto action_dimension = actions_json.at(0).size();
    std::vector<LinearStage> stages;
    stages.reserve(horizon);
    for(const auto& row : coefficient_stages) {
        auto a = matrix(row.at("A")); auto b = matrix(row.at("B"));
        auto c = vector(row.at("c"));
        stages.push_back({std::move(a), std::move(b), Matrix{dimension, 0, {}}, std::move(c)});
    }
    const auto absolute_stage = in.at("absolute_update_index").get<std::size_t>();
    const auto dt = in.at("dt").get<double>();
    Vector times(horizon + 1);
    for(std::size_t i = 0; i <= horizon; ++i) times[i] = static_cast<double>(absolute_stage + i) * dt;
    const SystemModel authored{{{dimension, action_dimension, 0}, TimeDomain::discrete,
        Coefficients{std::move(stages)}}, {}};
    auto system = take(model::snapshot(authored, times), "linear-predictor");
    std::vector<Vector> actions;
    for(const auto& action : actions_json) actions.push_back(vector(action));
    std::vector<Vector> external(horizon, Vector{});
    std::vector<sets::SetData> safe;
    for(std::size_t i = 0; i <= horizon; ++i)
        safe.push_back(safe_box(in.at("state_bounds"), dimension, "safe-stage-" + std::to_string(i)));
    const auto objective = terminal_objective(in.at("terminal_objective"), dimension);
    const auto cost = running_cost(in.at("running_cost"), in.at("original_horizon").get<std::size_t>(), action_dimension);
    optimization::FiniteActionNominalRequest request{
        {in.at("problem_id").get<std::string>()}, {in.at("request_id").get<std::string>()},
        std::move(system), initial, {action_dimension, std::move(actions)}, std::move(external),
        std::move(safe), objective, cost, absolute_stage};
    const auto representation_index = in.at("representation_index").get<std::size_t>();
    const std::array<optimization::NominalRepresentation, 5> representations{
        optimization::NominalRepresentation::exact_polytope,
        optimization::NominalRepresentation::box,
        optimization::NominalRepresentation::zonotope,
        optimization::NominalRepresentation::parallelotope,
        optimization::NominalRepresentation::ellipsoid};
    if(representation_index >= representations.size()) throw std::runtime_error("representation index must be in [0,4]");
    const auto outcome = optimization::finite_action_nominal_profile(request,
        {in.at("limits").at("max_plans").get<std::size_t>(),
         in.at("limits").at("max_points_per_stage").get<std::size_t>(),
         in.at("limits").at("max_score_evaluations").get<std::size_t>(),
         in.at("limits").at("max_generators_per_stage").get<std::size_t>(), 0.0},
        representations[representation_index]);
    if(const auto* error = std::get_if<Unsupported>(&outcome))
        return {{"status", "unsupported"}, {"reason", error->diagnostics.empty() ? "unsupported" : error->diagnostics.front().explanation}};
    if(const auto* stopped = std::get_if<OperationStopped>(&outcome))
        return {{"status", "failed"}, {"reason", stopped->diagnostics}};
    const auto& result = std::get<optimization::FiniteActionNominalResult>(outcome);
    const std::array<std::string, 5> operations{"exact-polytope-plan-select", "box-plan-select",
        "zonotope-plan-select", "parallelotope-plan-select", "ellipsoid-plan-select"};
    const auto& tracks = result.tracks;
    if(tracks.size() != 1) throw std::runtime_error("selected-profile route executed inactive tracks");
    const auto& track = tracks.front();
    const auto* selected = std::get_if<optimization::NominalTrackSelected>(&track.outcome);
    const auto route_outcome = std::visit([](const auto& row) -> std::string {
        using T = std::decay_t<decltype(row)>;
        if constexpr(std::is_same_v<T, optimization::NominalTrackSelected>) return "selected";
        if constexpr(std::is_same_v<T, optimization::NominalTrackNoScoredCandidate>) return "no-scored-candidate";
        if constexpr(std::is_same_v<T, optimization::NominalTrackUnsupported>) return "unsupported";
        return "stopped";
    }, track.outcome);
    std::optional<FirstStepRecovery> recovery;
    if(selected && dimension == 2 && representation_index == 0)
        recovery = recover_first_action_2d(in, request, *selected);
    Json invocations = Json::array({{{"module_id", "csl::optimization::finite_action_nominal_profile"},
        {"operation", operations.at(representation_index)},
        {"provider", "public-function"},
        {"profile_id", in.at("controller_id")}, {"outcome", route_outcome}}});
    if(recovery) invocations.push_back(recovery->invocation);
    Json base{{"task_id", in.at("task_id")}, {"task_sha256", in.at("task_sha256")},
        {"action_profile_id", in.at("action_profile_id")},
        {"policy_id", in.at("controller_id").get<std::string>() + "/receding-fixed-plan-mpc/1"},
        {"representation", representation_index}, {"invocations", invocations}};
    if(!selected) {
        const auto [status, reason] = std::visit([](const auto& row) -> std::pair<std::string,std::string> {
            using T = std::decay_t<decltype(row)>;
            if constexpr(std::is_same_v<T, optimization::NominalTrackUnsupported>)
                return {"unsupported", row.reason.diagnostics.empty() ? "unsupported route" : row.reason.diagnostics.front().explanation};
            if constexpr(std::is_same_v<T, optimization::NominalTrackStopped>)
                return {"failed", row.reason.diagnostics};
            if constexpr(std::is_same_v<T, optimization::NominalTrackNoScoredCandidate>) {
                bool unscored = false, stopped = false;
                std::string detail;
                for(const auto& attempt : row.attempts) {
                    if(const auto* refusal = std::get_if<optimization::NominalPlanUnscored>(&attempt)) {
                        unscored = true;
                        if(detail.empty() && !refusal->reason.diagnostics.empty())
                            detail = refusal->reason.diagnostics.front().explanation;
                    }
                    stopped = stopped || std::holds_alternative<optimization::NominalPlanStopped>(attempt);
                }
                if(unscored) return {"unsupported", detail.empty() ? "all candidate representation scores were unavailable" : detail};
                if(stopped) return {"failed", "search stopped before a scored candidate was retained"};
                return {"rejected", "no enumerated plan satisfies the declared nominal predictor and state constraints"};
            }
            return {"failed", "selected representation returned no usable plan"};
        }, track.outcome);
        base["status"] = status;
        base["reason"] = reason;
        return base;
    }
    if(selected->replay.controls.empty()) throw std::runtime_error("selected nominal plan has no action to apply");
    const auto coverage = selected->coverage == optimization::NominalSearchCoverage::complete ? "complete" :
        (selected->coverage == optimization::NominalSearchCoverage::stopped ? "stopped" : "incomplete");
    base["status"] = "accepted";
    base["control"] = selected->replay.controls.front();
    base["predicted_sets"] = Json::array({trace_json(*selected)});
    base["selected_plan"] = {{"states", selected->replay.states}, {"controls", selected->replay.controls},
        {"terminal_objective", selected->replay.terminal_objective},
        {"running_objective", selected->replay.running_objective},
        {"total_objective", selected->replay.total_objective}};
    base["selector"] = {{"search_coverage", coverage}, {"candidate_score", selected->candidate_score},
        {"score_kind", selected->score_kind == optimization::NominalScoreKind::exact_deterministic_objective ?
            "exact-deterministic-objective" :
            (selected->score_kind == optimization::NominalScoreKind::numerical_outer_estimate_plus_exact_running_cost ?
                "numerical-terminal-estimate-plus-exact-running-cost" : "numerical-outer-enclosure-estimate")},
        {"objective_id", result.objective_id}, {"original_horizon", result.original_horizon},
        {"absolute_stage_offset", result.absolute_stage_offset}, {"selected_control", selected->replay.controls.front()},
        {"terminal_objective", selected->replay.terminal_objective},
        {"running_objective", selected->replay.running_objective}, {"total_replay_objective", selected->replay.total_objective},
        {"policy_semantics", "receding-horizon nominal finite-action fixed-plan selection; first action reapplied after observation"},
        {"optimality_scope", "finite action catalogue and declared numerical affine predictor; no nonlinear global-feedback claim"}};
    base["query_receipt"] = {{"schema", "csl.closed-loop.native-policy-query-receipt/1"},
        {"task_id", in.at("task_id")}, {"task_sha256", in.at("task_sha256")},
        {"source_model_id", in.at("source_model_id")}, {"predictor_model_id", in.at("predictor_model_id")},
        {"predictor_assurance", in.at("predictor_assurance")},
        {"objective_id", result.objective_id}, {"original_horizon", result.original_horizon},
        {"absolute_update_index", result.absolute_stage_offset}, {"action_profile_id", in.at("action_profile_id")},
        {"controller_id", in.at("controller_id")}, {"representation", in.at("representation_name")},
        {"search_coverage", coverage}, {"candidate_score", selected->candidate_score},
        {"score_kind", base["selector"]["score_kind"]}, {"selected_control", selected->replay.controls.front()},
        {"predicted_set_role", "fixed-plan-trajectory-enclosure"}, {"invocations", base["invocations"]}};
    if(recovery) {
        base["control"] = recovery->control;
        base["recovered_control"] = recovery->control;
        base["predicted_sets"].push_back(recovery->predecessor_set);
        base["selector"]["policy_semantics"] =
            "receding-horizon finite-action MPC plus a numerical first-step predecessor/recovery witness for its selected singleton target";
        base["query_receipt"]["first_step_recovery"] = recovery->receipt;
        base["query_receipt"]["invocations"] = base["invocations"];
    }
    return base;
}
} // namespace

int main() {
    std::string line;
    while(std::getline(std::cin, line)) {
        try { std::cout << query(Json::parse(line)).dump() << '\n'; }
        catch(const std::exception& error) {
            std::cout << Json{{"status", "failed"}, {"reason", error.what()}}.dump() << '\n';
        }
        std::cout.flush();
    }
    return 0;
}
