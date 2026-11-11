#include <csl/model/linear_system.hpp>
#include <csl/optimization/finite_action_nominal.hpp>
#include <csl/optimization/objectives.hpp>
#include <csl/sets/data.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <cmath>
#include <iostream>
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
            return {{"representation", "polytope-h"},
                {"inequalities", matrix_json(rows.rows(), rows.cols(),
                    [&](std::size_t i, std::size_t j) { return rows(i, j); })},
                {"upper_bounds", std::move(bounds)}};
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
    Json invocations = Json::array({{{"module_id", "csl::optimization::finite_action_nominal_profile"},
        {"operation", operations.at(representation_index)},
        {"provider", "public-function"},
        {"profile_id", in.at("controller_id")}, {"outcome", route_outcome}}});
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
