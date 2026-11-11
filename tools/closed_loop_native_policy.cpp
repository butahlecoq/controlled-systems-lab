#include <csl/model/linear_system.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/geometry/polyhedral_intersection.hpp>
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
#include <numeric>
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

struct GraphNode {
    std::size_t stage{};
    Vector state;
    std::size_t parent{std::numeric_limits<std::size_t>::max()};
    std::size_t action_index{std::numeric_limits<std::size_t>::max()};
    double edge_cost{};
    double heuristic{};
    bool state_admissible{};
    bool intersection_nonempty{};
    bool viable{};
    double value{std::numeric_limits<double>::infinity()};
    std::string lineage;
    std::string backward_edge_status;
};

struct GraphCandidate {
    std::size_t parent{};
    std::size_t action_index{};
    Vector state;
    double edge_cost{};
    double heuristic{};
    bool state_admissible{};
    bool intersection_nonempty{};
    std::string lineage;
};

bool intersects_stage_h(const sets::SetData& admissible, const Vector& point,
                        const std::string& id) {
    Json point_bounds = Json::array();
    for(const double coordinate : point) point_bounds.push_back({coordinate, coordinate});
    const auto point_h = safe_box(point_bounds, point.size(), id + "/point-h");
    const auto intersection = geometry::polyhedral::intersect_h(admissible, point_h, {id + "/intersection"});
    if(const auto* diagnostics = std::get_if<Diagnostics>(&intersection))
        throw std::runtime_error("stage H intersection: " +
            (diagnostics->empty() ? std::string("unsupported") : diagnostics->front().explanation));
    return contains_with_tolerance(std::get<sets::SetData>(intersection), point);
}

struct GraphPolicyResult {
    std::vector<GraphNode> nodes;
    std::vector<std::vector<std::size_t>> layers;
    std::vector<std::size_t> selected_nodes;
    std::vector<std::size_t> generated;
    std::vector<std::size_t> retained;
    std::vector<std::size_t> pruned;
    std::vector<std::size_t> infeasible;
    std::size_t predecessor_calls{};
    bool complete{};
    bool has_viable_path{};
    double total_cost{};
};

bool predecessor_contains(const optimization::FiniteActionNominalRequest& request,
        const sets::SetData& control_hull, const registry::PreparedProvider<registry::GeometryPort>& provider,
        std::size_t stage, const Vector& parent, const Vector& child, const Json& input,
        const std::string& lineage) {
    const auto dynamics_value = request.system.stage({stage});
    if(const auto* error = std::get_if<Diagnostic>(&dynamics_value))
        throw std::runtime_error("graph predecessor dynamics: " + error->explanation);
    const auto& dynamics = std::get<model::DynamicsStage>(dynamics_value);
    const auto dimension = parent.size();
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
    auto target = take(sets::make_singleton({{"graph-child-" + lineage}, dimension, {}},
        take(numeric::snapshot_vector(child), "graph-child-view")), "graph-child-target");
    reachability::NominalPredecessorRequest predecessor_request{
        {{input.at("problem_id").get<std::string>()},
         {input.at("request_id").get<std::string>() + "/graph-predecessor-" + lineage},
         {input.at("request_id").get<std::string>() + "/graph-target-" + lineage}},
        request.admissible_states.at(stage).as_handle(), control_hull.as_handle(), target.as_handle(),
        std::move(a), std::move(b), std::move(offset)};
    auto prepared = reachability::prepare_nominal_predecessor(predecessor_request, provider);
    if(!std::holds_alternative<reachability::PreparedNominalPredecessor>(prepared))
        throw std::runtime_error("graph predecessor preparation rejected a concrete retained edge");
    auto outcome = std::get<reachability::PreparedNominalPredecessor>(std::move(prepared)).run({});
    if(!std::holds_alternative<reachability::NominalPredecessorResult>(outcome)) return false;
    const auto& result = std::get<reachability::NominalPredecessorResult>(outcome);
    const auto set = take(sets::from_handle(result.result.output), "graph-predecessor-set");
    return contains_with_tolerance(set, parent);
}

GraphPolicyResult run_exact_graph(const Json& input,
        const optimization::FiniteActionNominalRequest& request,
        std::size_t beam_width, std::size_t max_nodes) {
    if(request.initial_state.size() != 2)
        throw std::runtime_error("stage-layered predecessor graph currently requires the 2D exact-H route");
    const auto horizon = request.system.horizon();
    if(horizon == 0) throw std::runtime_error("stage-layered graph needs at least one authored transition");
    auto registration = geometry::polyhedral::make_projection_registration();
    registry::Registry<registry::GeometryPort> registry;
    if(const auto error = registry.add(registration))
        throw std::runtime_error("graph projection registration: " +
            (error->diagnostics.empty() ? std::string("registration rejected") : error->diagnostics.front().explanation));
    registry::Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.h"};
    requirements.output.relation = SetRelation::equivalent;
    auto prepared_provider = registry::prepare_provider(registry::select_provider(registry,
        {registration.identity.id, registration.identity.version}, requirements));
    if(!std::holds_alternative<registry::PreparedProvider<registry::GeometryPort>>(prepared_provider))
        throw std::runtime_error("graph exact-H projection provider did not prepare");
    auto provider = std::get<registry::PreparedProvider<registry::GeometryPort>>(std::move(prepared_provider));

    Vector action_lower(request.actions.dimension, std::numeric_limits<double>::infinity());
    Vector action_upper(request.actions.dimension, -std::numeric_limits<double>::infinity());
    for(const auto& action : request.actions.catalogue)
        for(std::size_t j = 0; j < action.size(); ++j) {
            action_lower[j] = std::min(action_lower[j], action[j]);
            action_upper[j] = std::max(action_upper[j], action[j]);
        }
    Json hull_bounds = Json::array();
    for(std::size_t j = 0; j < action_lower.size(); ++j) hull_bounds.push_back({action_lower[j], action_upper[j]});
    const auto control_hull = safe_box(hull_bounds, request.actions.dimension, "finite-action-control-hull");

    GraphPolicyResult graph;
    graph.layers.resize(horizon + 1);
    graph.generated.resize(horizon);
    graph.retained.resize(horizon + 1);
    graph.pruned.resize(horizon);
    graph.infeasible.resize(horizon + 1);
    const bool initial_ok = intersects_stage_h(request.admissible_states.front(), request.initial_state, "graph-root");
    graph.nodes.push_back({0, request.initial_state, std::numeric_limits<std::size_t>::max(),
        std::numeric_limits<std::size_t>::max(), 0.0, 0.0, initial_ok, initial_ok, false,
        std::numeric_limits<double>::infinity(), "root", "root-node"});
    graph.layers[0].push_back(0);
    graph.retained[0] = 1;
    if(!initial_ok) {
        graph.infeasible[0] = 1;
        graph.complete = true;
        return graph;
    }

    for(std::size_t stage = 0; stage < horizon; ++stage) {
        std::vector<GraphCandidate> candidates;
        for(const auto parent_id : graph.layers[stage]) {
            const auto& parent = graph.nodes.at(parent_id);
            for(std::size_t action_index = 0; action_index < request.actions.catalogue.size(); ++action_index) {
                const auto step = request.system.step({stage}, parent.state,
                    request.actions.catalogue[action_index], request.nominal_disturbances[stage]);
                if(const auto* error = std::get_if<Diagnostic>(&step))
                    throw std::runtime_error("graph affine transition: " + error->explanation);
                if(const auto* stopped = std::get_if<OperationStopped>(&step))
                    throw std::runtime_error("graph affine transition stopped: " + stopped->diagnostics);
                auto next = std::get<Vector>(step);
                const auto state_ok = intersects_stage_h(request.admissible_states[stage + 1], next,
                    "graph-" + parent.lineage + "-" + std::to_string(action_index));
                const auto edge_cost = absolute_stage_cost(request.running_cost,
                    request.absolute_stage_offset + stage, request.actions.catalogue[action_index]);
                const auto terminal_value = optimization::evaluate(request.objective, next);
                if(const auto* error = std::get_if<Diagnostic>(&terminal_value))
                    throw std::runtime_error("graph terminal heuristic: " + error->explanation);
                const auto cumulative = parent.heuristic + edge_cost + std::get<double>(terminal_value);
                const auto lineage = parent.lineage + "/" + std::to_string(action_index);
                candidates.push_back({parent_id, action_index, std::move(next), edge_cost,
                    cumulative, state_ok, state_ok, lineage});
            }
        }
        graph.generated[stage] = candidates.size();
        std::stable_sort(candidates.begin(), candidates.end(), [](const auto& left, const auto& right) {
            if(left.state_admissible != right.state_admissible) return left.state_admissible > right.state_admissible;
            if(left.heuristic != right.heuristic) return left.heuristic < right.heuristic;
            if(left.parent != right.parent) return left.parent < right.parent;
            if(left.action_index != right.action_index) return left.action_index < right.action_index;
            return left.lineage < right.lineage;
        });
        const auto retained = std::min({beam_width, candidates.size(), max_nodes - std::min(max_nodes, graph.nodes.size())});
        graph.pruned[stage] = candidates.size() - retained;
        graph.complete = graph.complete && candidates.size() == retained;
        for(std::size_t i = 0; i < retained; ++i) {
            const auto& candidate = candidates[i];
            const auto id = graph.nodes.size();
            graph.nodes.push_back({stage + 1, candidate.state, candidate.parent, candidate.action_index,
                candidate.edge_cost, candidate.heuristic, candidate.state_admissible,
                candidate.intersection_nonempty, false,
                std::numeric_limits<double>::infinity(), candidate.lineage, "pending-backward-pass"});
            graph.layers[stage + 1].push_back(id);
            ++graph.retained[stage + 1];
            if(!candidate.state_admissible) ++graph.infeasible[stage + 1];
        }
        if(retained == 0) break;
    }
    graph.complete = std::ranges::all_of(graph.pruned, [](std::size_t count) { return count == 0; });
    if(graph.layers.back().empty()) return graph;

    for(const auto id : graph.layers.back()) {
        auto& node = graph.nodes[id];
        node.viable = node.state_admissible;
        node.backward_edge_status = node.state_admissible ? "terminal-node-admissible" : "terminal-node-outside-stage-set";
        if(node.viable) {
            const auto value = optimization::evaluate(request.objective, node.state);
            if(const auto* error = std::get_if<Diagnostic>(&value))
                throw std::runtime_error("graph terminal objective: " + error->explanation);
            node.value = std::get<double>(value);
        }
    }
    for(std::size_t reverse = horizon; reverse > 0; --reverse) {
        const auto stage = reverse - 1;
        for(const auto child_id : graph.layers[stage + 1]) {
            auto& child = graph.nodes[child_id];
            if(!child.viable) {
                child.backward_edge_status = "skipped-suffix-nonviable";
                continue;
            }
            auto& parent = graph.nodes[child.parent];
            const auto& selected_action = request.actions.catalogue[child.action_index];
            const auto dynamics_value = request.system.stage({stage});
            if(const auto* error = std::get_if<Diagnostic>(&dynamics_value))
                throw std::runtime_error("graph edge replay dynamics: " + error->explanation);
            const auto& dynamics = std::get<model::DynamicsStage>(dynamics_value);
            Vector replayed(child.state.size());
            for(std::size_t row = 0; row < child.state.size(); ++row) {
                replayed[row] = dynamics.offset[row];
                for(std::size_t col = 0; col < parent.state.size(); ++col)
                    replayed[row] += dynamics.A(row, col) * parent.state[col];
                for(std::size_t col = 0; col < selected_action.size(); ++col)
                    replayed[row] += dynamics.B(row, col) * selected_action[col];
            }
            const bool discrete_witness = contains_with_tolerance(
                take(sets::make_singleton({{"graph-edge-replay"}, replayed.size(), {}},
                    take(numeric::snapshot_vector(replayed), "graph-edge-replay-view")), "graph-edge-replay-set"), child.state);
            ++graph.predecessor_calls;
            const bool predecessor = predecessor_contains(request, control_hull, provider,
                stage, parent.state, child.state, input, child.lineage);
            if(!predecessor) child.backward_edge_status = "numerical-predecessor-membership-false";
            else if(!discrete_witness) child.backward_edge_status = "discrete-transition-witness-failed";
            else if(!parent.state_admissible) child.backward_edge_status = "parent-stage-intersection-empty";
            else child.backward_edge_status = "eligible-numerical-predecessor-and-discrete-edge";
            child.viable = discrete_witness && predecessor && parent.state_admissible;
            if(!child.viable) continue;
            const auto candidate = child.edge_cost + child.value;
            if(candidate < parent.value) {
                parent.value = candidate;
                parent.viable = true;
            }
        }
    }
    if(!graph.nodes.front().viable) return graph;
    graph.has_viable_path = true;
    graph.total_cost = graph.nodes.front().value;
    std::size_t current = 0;
    graph.selected_nodes.push_back(current);
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        std::size_t best = std::numeric_limits<std::size_t>::max();
        double best_value = std::numeric_limits<double>::infinity();
        for(const auto child_id : graph.layers[stage + 1]) {
            const auto& child = graph.nodes[child_id];
            if(child.parent != current || !child.viable) continue;
            const auto candidate = child.edge_cost + child.value;
            if(candidate < best_value || (candidate == best_value && child.action_index < graph.nodes[best].action_index)) {
                best = child_id;
                best_value = candidate;
            }
        }
        if(best == std::numeric_limits<std::size_t>::max()) {
            graph.has_viable_path = false;
            graph.selected_nodes.clear();
            return graph;
        }
        current = best;
        graph.selected_nodes.push_back(current);
    }
    return graph;
}

Json graph_response(const Json& input, const optimization::FiniteActionNominalRequest& request,
                    std::size_t beam_width, std::size_t max_nodes) {
    const auto absolute_stage = request.absolute_stage_offset;
    auto graph = run_exact_graph(input, request, beam_width, max_nodes);
    Json layers = Json::array(), nodes = Json::array(), edges = Json::array();
    for(std::size_t stage = 0; stage < graph.retained.size(); ++stage)
        layers.push_back({{"stage", absolute_stage + stage},
            {"generated", stage < graph.generated.size() ? graph.generated[stage] : 0},
            {"retained", graph.retained[stage]}, {"pruned", stage < graph.pruned.size() ? graph.pruned[stage] : 0},
            {"infeasible", graph.infeasible[stage]}});
    for(std::size_t id = 0; id < graph.nodes.size(); ++id) {
        const auto& node = graph.nodes[id];
        nodes.push_back({{"node_id", id}, {"absolute_stage", absolute_stage + node.stage}, {"state", node.state},
            {"parent_node_id", node.parent == std::numeric_limits<std::size_t>::max() ? Json(nullptr) : Json(node.parent)},
            {"action_index", node.action_index == std::numeric_limits<std::size_t>::max() ? Json(nullptr) : Json(node.action_index)},
            {"edge_running_cost", node.edge_cost}, {"state_admissible", node.state_admissible},
            {"stage_set_intersection_nonempty", node.intersection_nonempty},
            {"backward_viable", node.viable}, {"backward_value", std::isfinite(node.value) ? Json(node.value) : Json(nullptr)},
            {"lineage", node.lineage}, {"backward_edge_status", node.backward_edge_status}});
    }
    for(std::size_t stage = 1; stage < graph.layers.size(); ++stage)
        for(const auto id : graph.layers[stage]) {
            const auto& node = graph.nodes[id];
            edges.push_back({{"parent_node_id", node.parent}, {"child_node_id", id},
                {"absolute_stage", absolute_stage + stage - 1}, {"action_index", node.action_index},
                {"action", request.actions.catalogue[node.action_index]}, {"child_state", node.state},
                {"lineage", node.lineage}, {"backward_viable", node.viable},
                {"backward_edge_status", node.backward_edge_status},
                {"discrete_transition_witness", true}});
        }
    Json invocations = Json::array({{{"module_id", "csl::optimization::run_exact_graph"},
        {"operation", "full-authored-horizon stage-layered graph with backward viability before Bellman selection"},
        {"provider", "public-function"}, {"profile_id", input.at("controller_id")},
        {"outcome", graph.has_viable_path ? "selected" : "no-viable-retained-path"},
        {"generated_edges", std::accumulate(graph.generated.begin(), graph.generated.end(), std::size_t{0})},
        {"retained_nodes", graph.nodes.size()}}});
    invocations.push_back({{"module_id", "csl::reachability::prepare_nominal_predecessor"},
        {"operation", "exact-H predecessor membership on each retained discrete edge"},
        {"provider", "csl.geometry.polyhedral-projection@1.0.0"}, {"profile_id", input.at("controller_id")},
        {"calls", graph.predecessor_calls}, {"assurance", "numerical, support unestablished"}});
    invocations.push_back({{"module_id", "csl::geometry::polyhedral::intersect_h"},
        {"operation", "intersect each retained singleton node with its authored stage H constraints"},
        {"provider", "public-function"}, {"profile_id", input.at("controller_id")},
        {"calls", std::accumulate(graph.generated.begin(), graph.generated.end(), std::size_t{1})}});
    Json response{{"task_id", input.at("task_id")}, {"task_sha256", input.at("task_sha256")},
        {"action_profile_id", input.at("action_profile_id")},
        {"policy_id", input.at("controller_id").get<std::string>() + "/budgeted-backward-graph-mpc/1"},
        {"representation", 0}, {"invocations", invocations},
        {"predicted_sets", Json::array({{{"role", "retained-stage-layered-singleton-nodes"},
            {"representation", "polytope-h"}, {"relation", "equivalent"}, {"assurance", "numerical"}, {"nodes", nodes}}})},
        {"graph_receipt", {{"schema", "csl.closed-loop.finite-action-backward-graph/1"},
            {"task_id", input.at("task_id")}, {"task_sha256", input.at("task_sha256")},
            {"source_model_id", input.at("source_model_id")}, {"predictor_model_id", input.at("predictor_model_id")},
            {"original_horizon", input.at("original_horizon")}, {"absolute_stage_offset", absolute_stage},
            {"action_profile_id", input.at("action_profile_id")}, {"objective_id", request.running_cost.objective_id},
            {"representation", "exact-polytope"}, {"beam_width", beam_width}, {"max_graph_nodes", max_nodes},
            {"search_coverage", graph.complete ? "complete" : "incomplete"},
            {"optimality_scope", "Bellman minimum over retained graph only; no claim over pruned paths or nonlinear plant"},
            {"no_path_semantics", "no viable retained path after numerical filtering is not a global infeasibility proof"},
            {"layer_statistics", layers}, {"nodes", nodes}, {"edges", edges},
            {"backward_viability_applied_before_selection", true}}}};
    if(!graph.has_viable_path) {
        response["status"] = "unsupported";
        response["reason"] = graph.nodes.size() >= max_nodes ?
            "Graph node budget exhausted before retaining a viable full-horizon path; no action is returned." :
            "No viable retained path passed the numerical backward filter; this is not a global infeasibility proof and no action is returned.";
        return response;
    }
    Json states = Json::array(), controls = Json::array(), selected_edges = Json::array();
    for(const auto id : graph.selected_nodes) {
        const auto& node = graph.nodes[id];
        states.push_back(node.state);
        if(id != 0) {
            controls.push_back(request.actions.catalogue[node.action_index]);
            selected_edges.push_back({{"parent_node_id", node.parent}, {"child_node_id", id},
                {"absolute_stage", absolute_stage + node.stage - 1}, {"action_index", node.action_index},
                {"action", request.actions.catalogue[node.action_index]}, {"child_state", node.state},
                {"lineage", node.lineage}, {"backward_viable", node.viable}});
        }
    }
    const auto terminal_value = optimization::evaluate(request.objective, graph.nodes[graph.selected_nodes.back()].state);
    if(const auto* error = std::get_if<Diagnostic>(&terminal_value)) throw std::runtime_error("selected graph terminal objective: " + error->explanation);
    const double terminal_cost = std::get<double>(terminal_value);
    double running_cost_value = 0.0;
    for(const auto id : graph.selected_nodes) if(id != 0) running_cost_value += graph.nodes[id].edge_cost;
    response["status"] = "accepted";
    response["control"] = request.actions.catalogue[graph.nodes[graph.selected_nodes[1]].action_index];
    response["recovered_control"] = response["control"];
    response["selected_plan"] = {{"states", states}, {"controls", controls}, {"terminal_objective", terminal_cost},
        {"running_objective", running_cost_value}, {"total_objective", terminal_cost + running_cost_value}};
    response["selected_edges"] = selected_edges;
    response["selector"] = {{"search_coverage", graph.complete ? "complete" : "incomplete"}, {"beam_width", beam_width},
        {"retained_graph_value", graph.total_cost}, {"terminal_objective", terminal_cost},
        {"running_objective", running_cost_value}, {"total_replay_objective", terminal_cost + running_cost_value},
        {"score_kind", "exact-source-cost-on-numerical-affine-predictor"},
        {"policy_semantics", "receding finite-action graph MPC; backward predecessor viability filters authored edges before Bellman selection; replans after each observed hold"},
        {"optimality_scope", "retained graph only; not complete finite-action optimum, nonlinear global optimum, or causal feedback optimum"}};
    return response;
}

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
    if(in.contains("stage_state_bounds")) {
        const auto& rows = in.at("stage_state_bounds");
        if(rows.size() != horizon + 1) throw std::runtime_error("stage_state_bounds must include every absolute state stage");
        for(std::size_t i = 0; i <= horizon; ++i)
            safe.push_back(safe_box(rows[i], dimension, "safe-stage-" + std::to_string(i)));
    } else {
        for(std::size_t i = 0; i <= horizon; ++i)
            safe.push_back(safe_box(in.at("state_bounds"), dimension, "safe-stage-" + std::to_string(i)));
    }
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
    if(representation_index == 0 && in.value("search_policy", std::string{}) == "stage-layered-backward-viability")
        return graph_response(in, request,
            in.at("limits").value("max_beam_width", std::size_t{16}),
            in.at("limits").value("max_graph_nodes", std::size_t{2048}));
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
