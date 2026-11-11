#include <csl/optimization/finite_action_graph.hpp>

#include <csl/geometry/polyhedral_intersection.hpp>
#include <csl/reachability/nominal_predecessor.hpp>
#include <csl/sets/data.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>

namespace csl::optimization {
namespace {

Unsupported unsupported(std::string field, std::string explanation) {
    return {{{DiagnosticCode::unsupported, std::move(field), std::move(explanation)}}};
}

bool finite(std::span<const double> values) {
    return std::ranges::all_of(values, [](double value) { return std::isfinite(value); });
}

bool contains_with_tolerance(const sets::SetData& set, std::span<const double> point,
        double absolute_tolerance = 1e-9, double relative_tolerance = 1e-10) {
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
            lhs += term;
            scale += std::abs(term);
        }
        if(lhs > h->upper_bounds[row] + absolute_tolerance + relative_tolerance * scale) return false;
    }
    for(std::size_t row = 0; row < h->equalities.rows(); ++row) {
        double lhs = 0.0, scale = std::abs(h->equality_values[row]);
        for(std::size_t col = 0; col < point.size(); ++col) {
            const double term = h->equalities(row, col) * point[col];
            lhs += term;
            scale += std::abs(term);
        }
        if(std::abs(lhs - h->equality_values[row]) > absolute_tolerance + relative_tolerance * scale) return false;
    }
    return true;
}

using SetOutcome = std::variant<sets::SetData, Unsupported>;
SetOutcome box(std::span<const double> lower, std::span<const double> upper,
               std::vector<std::string> labels, std::string id) {
    if(lower.size() != upper.size() || (!labels.empty() && labels.size() != lower.size()))
        return unsupported("finite_graph.box.dimension", "Box coordinates and labels have inconsistent dimensions.");
    const auto dimension = lower.size();
    Matrix a{2 * dimension, dimension, Vector(2 * dimension * dimension, 0.0)};
    Vector b; b.reserve(2 * dimension);
    for(std::size_t coordinate = 0; coordinate < dimension; ++coordinate) {
        if(!std::isfinite(lower[coordinate]) || !std::isfinite(upper[coordinate]) || lower[coordinate] > upper[coordinate])
            return unsupported("finite_graph.box.bounds", "Finite ordered bounds are required for the graph point and control hulls.");
        a.values[(2 * coordinate) * dimension + coordinate] = 1.0;
        b.push_back(upper[coordinate]);
        a.values[(2 * coordinate + 1) * dimension + coordinate] = -1.0;
        b.push_back(-lower[coordinate]);
    }
    auto av = numeric::snapshot(a); auto bv = numeric::snapshot_vector(b);
    auto ev = numeric::snapshot(Matrix{0, dimension, {}}); auto fv = numeric::snapshot_vector(Vector{});
    if(!std::holds_alternative<numeric::MatrixView>(av) || !std::holds_alternative<numeric::VectorView>(bv) ||
       !std::holds_alternative<numeric::MatrixView>(ev) || !std::holds_alternative<numeric::VectorView>(fv))
        return unsupported("finite_graph.box.snapshot", "Could not snapshot graph H bounds.");
    const auto made = sets::make_h({{std::move(id)}, dimension, std::move(labels)},
        {std::get<numeric::MatrixView>(av), std::get<numeric::VectorView>(bv),
         std::get<numeric::MatrixView>(ev), std::get<numeric::VectorView>(fv)});
    if(const auto* error = std::get_if<Diagnostic>(&made)) return unsupported(error->field, error->explanation);
    return std::get<sets::SetData>(made);
}

SetOutcome stage_intersection(const sets::SetData& admissible, std::span<const double> point,
        std::string id) {
    const auto labels = admissible.metadata()->coordinate_labels;
    const auto point_h = box(point, point, labels, id + "/point");
    if(const auto* error = std::get_if<Unsupported>(&point_h)) return *error;
    const auto intersection = geometry::polyhedral::intersect_h(admissible,
        std::get<sets::SetData>(point_h), {id + "/stage-intersection"});
    if(const auto* diagnostics = std::get_if<Diagnostics>(&intersection))
        return unsupported(diagnostics->empty() ? "finite_graph.intersection" : diagnostics->front().field,
            diagnostics->empty() ? "Stage H intersection was not admitted." : diagnostics->front().explanation);
    return std::get<sets::SetData>(intersection);
}

double stage_cost(const RunningControlCost& cost, std::size_t stage, std::span<const double> control) {
    const auto found = std::lower_bound(cost.stages.begin(), cost.stages.end(), stage,
        [](const AbsoluteStageControlCost& row, std::size_t value) { return row.stage < value; });
    if(found == cost.stages.end() || found->stage != stage) return 0.0;
    double total = 0.0;
    for(const auto& term : found->terms) {
        if(const auto* quadratic = std::get_if<QuadraticControlPenalty>(&term)) {
            double sum = 0.0;
            for(std::size_t j = 0; j < control.size(); ++j) {
                const double residual = (control[j] - quadratic->reference[j]) / quadratic->scales[j];
                sum += quadratic->weights[j] * residual * residual;
            }
            total += quadratic->coefficient * sum / static_cast<double>(quadratic->normalization_horizon);
        } else {
            const auto& norm = std::get<EuclideanControlPenalty>(term);
            double squared = 0.0;
            for(std::size_t row = 0; row < norm.map.rows; ++row) {
                double value = norm.offset[row];
                for(std::size_t col = 0; col < norm.map.cols; ++col)
                    value += norm.map.values[row * norm.map.cols + col] * control[col];
                squared += value * value;
            }
            total += norm.coefficient * std::sqrt(squared);
        }
    }
    return total;
}

struct Candidate {
    std::size_t parent{};
    std::size_t action_index{};
    Vector state;
    double edge_cost{};
    double heuristic{};
    bool state_admissible{};
    std::vector<std::size_t> lineage;
};

struct PredecessorCheck { bool contains_parent{}; };
using PredecessorOutcome = std::variant<PredecessorCheck, Unsupported, OperationStopped>;

PredecessorOutcome predecessor_contains(const FiniteActionNominalRequest& request,
        const sets::SetData& control_hull,
        const registry::PreparedProvider<registry::GeometryPort>& projection_provider,
        std::size_t stage, const Vector& parent, const Vector& child, std::span<const std::size_t> lineage,
        const ExecutionContext& context) {
    const auto dynamics_value = request.system.stage({stage});
    if(const auto* error = std::get_if<Diagnostic>(&dynamics_value))
        return unsupported(error->field, error->explanation);
    const auto& dynamics = std::get<model::DynamicsStage>(dynamics_value);
    const auto dimension = parent.size();
    Matrix a{dimension, dimension, Vector(dimension * dimension)};
    Matrix b{dimension, request.actions.dimension, Vector(dimension * request.actions.dimension)};
    Vector offset(dimension);
    for(std::size_t row = 0; row < dimension; ++row) {
        offset[row] = dynamics.offset[row];
        for(std::size_t col = 0; col < dimension; ++col) a.values[row * dimension + col] = dynamics.A(row, col);
        for(std::size_t col = 0; col < request.actions.dimension; ++col)
            b.values[row * request.actions.dimension + col] = dynamics.B(row, col);
    }
    auto target_view = numeric::snapshot_vector(child);
    if(!std::holds_alternative<numeric::VectorView>(target_view))
        return unsupported("finite_graph.target", "Could not snapshot the graph child state.");
    const auto target_result = sets::make_singleton({{"graph-child"}, dimension,
        request.admissible_states[stage + 1].metadata()->coordinate_labels},
        std::get<numeric::VectorView>(target_view));
    if(const auto* error = std::get_if<Diagnostic>(&target_result)) return unsupported(error->field, error->explanation);
    std::string lineage_id;
    for(const auto index : lineage) lineage_id += "/" + std::to_string(index);
    reachability::NominalPredecessorRequest predecessor_request{
        {request.problem, {request.request.value + "/graph-predecessor" + lineage_id},
            {request.request.value + "/graph-target" + lineage_id}},
        request.admissible_states[stage].as_handle(), control_hull.as_handle(),
        std::get<sets::SetData>(target_result).as_handle(), std::move(a), std::move(b), std::move(offset)};
    auto prepared = reachability::prepare_nominal_predecessor(predecessor_request, projection_provider);
    if(!std::holds_alternative<reachability::PreparedNominalPredecessor>(prepared))
        return unsupported("finite_graph.predecessor.prepare", "Prepared projection provider rejected a concrete stage edge.");
    auto outcome = std::get<reachability::PreparedNominalPredecessor>(std::move(prepared)).run(context);
    if(const auto* failure = std::get_if<reachability::NominalPredecessorFailure>(&outcome)) {
        if(const auto* stopped = std::get_if<OperationStopped>(&failure->cause)) return *stopped;
        const auto& reason = std::get<Unsupported>(failure->cause);
        return reason;
    }
    const auto& result = std::get<reachability::NominalPredecessorResult>(outcome);
    const auto set = sets::from_handle(result.result.output);
    if(const auto* error = std::get_if<Diagnostic>(&set)) return unsupported(error->field, error->explanation);
    return PredecessorCheck{contains_with_tolerance(std::get<sets::SetData>(set), parent)};
}

FiniteGraphBackwardStatus eligible_status() {
    return FiniteGraphBackwardStatus::eligible_numerical_predecessor_and_discrete_edge;
}

} // namespace

FiniteActionGraphOutcome finite_action_stage_layered_graph(const FiniteActionNominalRequest& request,
        FiniteActionGraphLimits limits,
        const registry::PreparedProvider<registry::GeometryPort>& projection_provider,
        const ExecutionContext& context) {
    const auto dimensions = request.system.dimensions();
    const auto horizon = request.system.horizon();
    if(limits.beam_width == 0 || limits.max_nodes == 0)
        return unsupported("finite_graph.limits", "Beam width and maximum node count must be positive.");
    if(dimensions.state != 2 || dimensions.external != 0)
        return unsupported("finite_graph.model", "The first graph implementation admits 2D nominal systems without external inputs.");
    if(request.initial_state.size() != dimensions.state || request.actions.dimension != dimensions.control ||
       request.actions.catalogue.empty() || request.admissible_states.size() != horizon + 1 ||
       request.nominal_disturbances.size() != horizon || request.objective.dimension() != dimensions.state)
        return unsupported("finite_graph.request", "Finite action graph request dimensions do not match the nominal system.");
    if(horizon == 0 || !finite(request.initial_state))
        return unsupported("finite_graph.horizon", "Graph requires a nonempty horizon and finite initial state.");
    for(const auto& action : request.actions.catalogue)
        if(action.size() != dimensions.control || !finite(action))
            return unsupported("finite_graph.actions", "Each authored discrete action must be finite and have the declared control dimension.");

    Vector control_lower(dimensions.control, std::numeric_limits<double>::infinity());
    Vector control_upper(dimensions.control, -std::numeric_limits<double>::infinity());
    for(const auto& action : request.actions.catalogue)
        for(std::size_t j = 0; j < dimensions.control; ++j) {
            control_lower[j] = std::min(control_lower[j], action[j]);
            control_upper[j] = std::max(control_upper[j], action[j]);
        }
    std::vector<std::string> action_labels(dimensions.control);
    for(std::size_t j = 0; j < dimensions.control; ++j) action_labels[j] = "u" + std::to_string(j);
    const auto control_hull_result = box(control_lower, control_upper, std::move(action_labels), "finite-action-hull");
    if(const auto* error = std::get_if<Unsupported>(&control_hull_result)) return *error;
    const auto& control_hull = std::get<sets::SetData>(control_hull_result);

    FiniteActionGraphResult graph;
    graph.layers.resize(horizon + 1);
    graph.layer_statistics.resize(horizon + 1);
    for(std::size_t stage = 0; stage <= horizon; ++stage)
        graph.layer_statistics[stage].stage = request.absolute_stage_offset + stage;
    const auto root_intersection = stage_intersection(request.admissible_states.front(), request.initial_state, "graph-root");
    if(const auto* error = std::get_if<Unsupported>(&root_intersection)) return *error;
    ++graph.stage_intersection_calls;
    const bool initial_ok = contains_with_tolerance(std::get<sets::SetData>(root_intersection), request.initial_state);
    graph.nodes.push_back({0, request.initial_state, {}, {}, 0.0, 0.0, initial_ok, initial_ok,
        false, {}, {}, {}, {}, FiniteGraphBackwardStatus::root_node});
    graph.layers[0].push_back(0);
    graph.layer_statistics[0].retained = 1;
    if(!initial_ok) {
        graph.layer_statistics[0].stage_inadmissible = 1;
        graph.search_complete = true;
        return graph;
    }

    for(std::size_t stage = 0; stage < horizon; ++stage) {
        if(context.cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled, "Finite action graph expansion cancelled."};
        std::vector<Candidate> candidates;
        for(const auto parent_id : graph.layers[stage]) {
            const auto& parent = graph.nodes[parent_id];
            for(std::size_t action_index = 0; action_index < request.actions.catalogue.size(); ++action_index) {
                const auto step = request.system.step({stage}, parent.state,
                    request.actions.catalogue[action_index], request.nominal_disturbances[stage]);
                if(const auto* error = std::get_if<Diagnostic>(&step)) return unsupported(error->field, error->explanation);
                if(const auto* stopped = std::get_if<OperationStopped>(&step)) return *stopped;
                auto next = std::get<Vector>(step);
                const auto intersection = stage_intersection(request.admissible_states[stage + 1], next,
                    "graph-node-" + std::to_string(parent_id) + "-" + std::to_string(action_index));
                if(const auto* error = std::get_if<Unsupported>(&intersection)) return *error;
                ++graph.stage_intersection_calls;
                const bool state_ok = contains_with_tolerance(std::get<sets::SetData>(intersection), next);
                const auto absolute = request.absolute_stage_offset + stage;
                const auto edge_cost = stage_cost(request.running_cost, absolute, request.actions.catalogue[action_index]);
                const auto terminal_value = evaluate(request.objective, next);
                if(const auto* error = std::get_if<Diagnostic>(&terminal_value)) return unsupported(error->field, error->explanation);
                const double heuristic = parent.heuristic_score + edge_cost + std::get<double>(terminal_value);
                auto lineage = parent.action_lineage;
                lineage.push_back(action_index);
                candidates.push_back({parent_id, action_index, std::move(next), edge_cost, heuristic, state_ok, std::move(lineage)});
            }
        }
        auto& stats = graph.layer_statistics[stage];
        stats.generated = candidates.size();
        std::stable_sort(candidates.begin(), candidates.end(), [](const Candidate& left, const Candidate& right) {
            if(left.state_admissible != right.state_admissible) return left.state_admissible > right.state_admissible;
            if(left.heuristic != right.heuristic) return left.heuristic < right.heuristic;
            if(left.parent != right.parent) return left.parent < right.parent;
            if(left.action_index != right.action_index) return left.action_index < right.action_index;
            return left.lineage < right.lineage;
        });
        const auto available = limits.max_nodes - std::min(limits.max_nodes, graph.nodes.size());
        const auto retained = std::min({limits.beam_width, candidates.size(), available});
        stats.pruned = candidates.size() - retained;
        for(std::size_t i = 0; i < retained; ++i) {
            const auto& candidate = candidates[i];
            const auto node_id = graph.nodes.size();
            graph.nodes.push_back({stage + 1, candidate.state, candidate.parent, candidate.action_index,
                candidate.edge_cost, candidate.heuristic, candidate.state_admissible,
                candidate.state_admissible, false, {}, {}, {}, candidate.lineage, FiniteGraphBackwardStatus::pending});
            graph.layers[stage + 1].push_back(node_id);
            ++graph.layer_statistics[stage + 1].retained;
            if(!candidate.state_admissible) ++graph.layer_statistics[stage + 1].stage_inadmissible;
        }
        if(retained < candidates.size() && graph.nodes.size() >= limits.max_nodes) graph.node_budget_exhausted = true;
        if(retained == 0) break;
    }
    graph.search_complete = !graph.node_budget_exhausted &&
        std::ranges::all_of(graph.layer_statistics, [](const auto& row) { return row.pruned == 0; });
    if(graph.layers.back().empty()) return graph;

    for(const auto id : graph.layers.back()) {
        auto& node = graph.nodes[id];
        node.backward_viable = node.state_admissible;
        node.backward_status = node.state_admissible ? FiniteGraphBackwardStatus::terminal_admissible :
            FiniteGraphBackwardStatus::terminal_outside_stage_set;
        if(node.backward_viable) {
            const auto value = evaluate(request.objective, node.state);
            if(const auto* error = std::get_if<Diagnostic>(&value)) return unsupported(error->field, error->explanation);
            node.backward_value = std::get<double>(value);
        }
    }

    for(std::size_t reverse = horizon; reverse > 0; --reverse) {
        const auto stage = reverse - 1;
        for(const auto child_id : graph.layers[stage + 1]) {
            auto& child = graph.nodes[child_id];
            if(!child.backward_viable) {
                child.backward_status = FiniteGraphBackwardStatus::skipped_suffix_nonviable;
                continue;
            }
            auto& parent = graph.nodes[*child.parent_node];
            const auto dynamics_value = request.system.stage({stage});
            if(const auto* error = std::get_if<Diagnostic>(&dynamics_value)) return unsupported(error->field, error->explanation);
            const auto& dynamics = std::get<model::DynamicsStage>(dynamics_value);
            const auto& action = request.actions.catalogue[*child.action_index];
            Vector replay(child.state.size());
            for(std::size_t row = 0; row < replay.size(); ++row) {
                replay[row] = dynamics.offset[row];
                for(std::size_t col = 0; col < parent.state.size(); ++col)
                    replay[row] += dynamics.A(row, col) * parent.state[col];
                for(std::size_t col = 0; col < action.size(); ++col)
                    replay[row] += dynamics.B(row, col) * action[col];
            }
            bool discrete_witness = replay.size() == child.state.size();
            for(std::size_t i = 0; discrete_witness && i < replay.size(); ++i)
                discrete_witness = std::abs(replay[i] - child.state[i]) <= 1e-9 +
                    1e-10 * std::max(std::abs(replay[i]), std::abs(child.state[i]));
            child.discrete_transition_witness = discrete_witness &&
                contains_with_tolerance(request.admissible_states[stage + 1], replay) &&
                contains_with_tolerance(request.admissible_states[stage + 1], child.state);
            ++graph.predecessor_calls;
            const auto predecessor = predecessor_contains(request, control_hull, projection_provider,
                stage, parent.state, child.state, child.action_lineage, context);
            if(const auto* error = std::get_if<Unsupported>(&predecessor)) return *error;
            if(const auto* stopped = std::get_if<OperationStopped>(&predecessor)) return *stopped;
            child.predecessor_contains_parent = std::get<PredecessorCheck>(predecessor).contains_parent;
            if(!*child.predecessor_contains_parent) child.backward_status = FiniteGraphBackwardStatus::predecessor_membership_false;
            else if(!*child.discrete_transition_witness) child.backward_status = FiniteGraphBackwardStatus::discrete_transition_witness_failed;
            else if(!parent.state_admissible) child.backward_status = FiniteGraphBackwardStatus::parent_stage_intersection_empty;
            else child.backward_status = eligible_status();
            child.backward_viable = *child.discrete_transition_witness && *child.predecessor_contains_parent && parent.state_admissible;
            if(!child.backward_viable) continue;
            const double candidate = child.edge_running_cost + *child.backward_value;
            if(!parent.backward_value || candidate < *parent.backward_value) {
                parent.backward_value = candidate;
                parent.backward_viable = true;
            }
        }
    }
    if(!graph.nodes.front().backward_viable) return graph;
    graph.has_viable_path = true;
    graph.total_objective = *graph.nodes.front().backward_value;
    std::size_t current = 0;
    graph.selected_nodes.push_back(current);
    for(std::size_t stage = 0; stage < horizon; ++stage) {
        std::optional<std::size_t> best;
        double best_value = std::numeric_limits<double>::infinity();
        for(const auto child_id : graph.layers[stage + 1]) {
            const auto& child = graph.nodes[child_id];
            if(child.parent_node != current || !child.backward_viable) continue;
            const auto value = child.edge_running_cost + *child.backward_value;
            if(!best || value < best_value || (value == best_value && *child.action_index < *graph.nodes[*best].action_index)) {
                best = child_id;
                best_value = value;
            }
        }
        if(!best) {
            graph.has_viable_path = false;
            graph.selected_nodes.clear();
            return graph;
        }
        current = *best;
        graph.selected_nodes.push_back(current);
    }
    return graph;
}

} // namespace csl::optimization
