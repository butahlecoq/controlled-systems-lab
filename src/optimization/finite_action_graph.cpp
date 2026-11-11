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

Unsupported validate_running_cost(const RunningControlCost& cost, std::size_t stage_offset,
        std::size_t horizon, std::size_t control_dimension) {
    if(cost.stages.empty()) {
        if(!cost.objective_id.empty() || cost.original_horizon != 0)
            return unsupported("finite_graph.running_cost", "An inactive running-cost schedule must have empty identity and zero original horizon.");
        return {};
    }
    if(cost.objective_id.empty() || cost.original_horizon == 0 || stage_offset > cost.original_horizon ||
       horizon > cost.original_horizon - stage_offset)
        return unsupported("finite_graph.running_cost", "The running-cost identity and original horizon must cover the requested absolute-stage slice.");
    std::size_t previous = 0;
    bool first = true;
    for(const auto& row : cost.stages) {
        if(row.stage >= cost.original_horizon || (!first && row.stage <= previous))
            return unsupported("finite_graph.running_cost.stages", "Running-cost stages must be unique, increasing, and inside the original horizon.");
        previous = row.stage;
        first = false;
        for(const auto& term : row.terms) {
            if(const auto* quadratic = std::get_if<QuadraticControlPenalty>(&term)) {
                if(quadratic->reference.size() != control_dimension || quadratic->scales.size() != control_dimension ||
                   quadratic->weights.size() != control_dimension || quadratic->normalization_horizon != cost.original_horizon ||
                   !finite(quadratic->reference) || !finite(quadratic->scales) || !finite(quadratic->weights) ||
                   !std::isfinite(quadratic->coefficient) || quadratic->coefficient < 0.0 ||
                   !std::ranges::all_of(quadratic->scales, [](double value) { return value != 0.0; }) ||
                   !std::ranges::all_of(quadratic->weights, [](double value) { return value >= 0.0; }))
                    return unsupported("finite_graph.running_cost.quadratic", "Quadratic cost dimensions, original-horizon normalization, scales, weights, or coefficient are invalid.");
            } else {
                const auto& norm = std::get<EuclideanControlPenalty>(term);
                if(norm.map.cols != control_dimension || norm.map.rows == 0 ||
                   norm.offset.size() != norm.map.rows ||
                   norm.map.values.size() != norm.map.rows * norm.map.cols ||
                   !finite(norm.map.values) || !finite(norm.offset) ||
                   !std::isfinite(norm.coefficient) || norm.coefficient < 0.0)
                    return unsupported("finite_graph.running_cost.euclidean", "Euclidean cost map, offset, or coefficient is invalid.");
            }
        }
    }
    return {};
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
    std::optional<bool> reachable_envelope_contains;
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

using GeometryCallOutcome = std::variant<sets::SetData, Unsupported, OperationStopped>;

GeometryCallOutcome run_geometry(const registry::PreparedProvider<registry::GeometryPort>& provider,
        const FiniteActionNominalRequest& request, GeometryOperation operation,
        std::string suffix, const ExecutionContext& context) {
    const auto provenance = provider.provenance();
    const auto implementation = provenance.actual ? provenance.actual->id : provenance.requested.id;
    GeometryRequestIdentity identity{request.problem,
        {request.request.value + "/" + suffix}, {request.request.value + "/" + suffix + "/output"}};
    OperationRequest geometry_request{identity, implementation, std::move(operation),
        SetRelation::equivalent, Assurance::numerical};
    auto prepared = provider.prepare(geometry_request);
    if(const auto* rejection = std::get_if<registry::Rejection>(&prepared))
        return Unsupported{rejection->diagnostics};
    auto workspace = std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(prepared)).create();
    auto outcome = std::get<0>(workspace)->run(context);
    if(const auto* stopped = std::get_if<OperationStopped>(&outcome)) return *stopped;
    if(const auto* error = std::get_if<Unsupported>(&outcome)) return *error;
    const auto* result = std::get_if<OperationResult>(&outcome);
    if(!result) return unsupported("finite_graph.reachable.operation", "Selected reachable-set operation returned a query result rather than a set.");
    if(const auto diagnostics = check_geometry_evidence(result->evidence, geometry_request); !diagnostics.empty())
        return Unsupported{diagnostics};
    if(result->relation != SetRelation::equivalent)
        return unsupported("finite_graph.reachable.evidence", "Reachable-set operation must return an equivalent numerical set result.");
    auto set = sets::from_handle(result->output);
    if(const auto* error = std::get_if<Diagnostic>(&set)) return unsupported(error->field, error->explanation);
    return std::get<sets::SetData>(std::move(set));
}

SetOutcome action_state_hull(const FiniteActionNominalRequest& request, std::size_t stage) {
    const auto dynamics_value = request.system.stage({stage});
    if(const auto* error = std::get_if<Diagnostic>(&dynamics_value)) return unsupported(error->field, error->explanation);
    const auto& dynamics = std::get<model::DynamicsStage>(dynamics_value);
    Matrix vertices{request.actions.catalogue.size(), request.system.dimensions().state,
        Vector(request.actions.catalogue.size() * request.system.dimensions().state)};
    for(std::size_t point = 0; point < request.actions.catalogue.size(); ++point)
        for(std::size_t row = 0; row < vertices.cols; ++row)
            for(std::size_t col = 0; col < request.actions.dimension; ++col)
                vertices.values[point * vertices.cols + row] += dynamics.B(row, col) * request.actions.catalogue[point][col];
    auto vertex_view = numeric::snapshot(vertices);
    auto ray_view = numeric::snapshot(Matrix{0, vertices.cols, {}});
    if(!std::holds_alternative<numeric::MatrixView>(vertex_view) || !std::holds_alternative<numeric::MatrixView>(ray_view))
        return unsupported("finite_graph.action_hull.snapshot", "Could not snapshot the authored state-space action hull.");
    const auto made = sets::make_v({{"finite-graph-state-action-hull"}, vertices.cols, {}},
        {std::get<numeric::MatrixView>(vertex_view), std::get<numeric::MatrixView>(ray_view)});
    if(const auto* error = std::get_if<Diagnostic>(&made)) return unsupported(error->field, error->explanation);
    return std::get<sets::SetData>(made);
}

bool contains_v_2d(const sets::SetData& set, std::span<const double> point,
        double absolute_tolerance = 1e-9, double relative_tolerance = 1e-10) {
    const auto representation = set.representation();
    const auto* v = std::get_if<sets::VRepresentation>(&representation);
    if(!v || point.size() != 2 || v->vertices.cols() != 2 || v->rays.rows() != 0 || v->vertices.rows() == 0) return false;
    const auto n = v->vertices.rows();
    auto tolerance = [&](double scale) { return absolute_tolerance + relative_tolerance * scale; };
    if(n == 1) {
        const double dx = point[0] - v->vertices(0,0), dy = point[1] - v->vertices(0,1);
        return std::hypot(dx,dy) <= tolerance(std::max(std::abs(point[0]), std::abs(point[1])));
    }
    bool noncollinear = false;
    for(std::size_t i = 0; i < n && !noncollinear; ++i)
        for(std::size_t j = i + 1; j < n && !noncollinear; ++j)
            for(std::size_t k = j + 1; k < n; ++k) {
                const double cross = (v->vertices(j,0)-v->vertices(i,0))*(v->vertices(k,1)-v->vertices(i,1))-
                    (v->vertices(j,1)-v->vertices(i,1))*(v->vertices(k,0)-v->vertices(i,0));
                if(std::abs(cross) > tolerance(std::abs(cross))) { noncollinear=true; break; }
            }
    if(!noncollinear) {
        std::size_t a=0,b=1;
        double max_distance=-1.0;
        for(std::size_t i=0;i<n;++i)for(std::size_t j=i+1;j<n;++j) {
            const double dx=v->vertices(j,0)-v->vertices(i,0),dy=v->vertices(j,1)-v->vertices(i,1);
            const double distance=dx*dx+dy*dy;
            if(distance>max_distance){max_distance=distance;a=i;b=j;}
        }
        const double dx=v->vertices(b,0)-v->vertices(a,0),dy=v->vertices(b,1)-v->vertices(a,1);
        const double px=point[0]-v->vertices(a,0),py=point[1]-v->vertices(a,1);
        const double cross=dx*py-dy*px;
        const double scale=std::abs(dx*py)+std::abs(dy*px);
        const double projection=px*dx+py*dy;
        return std::abs(cross)<=tolerance(scale) && projection>=-tolerance(max_distance) &&
            projection<=max_distance+tolerance(max_distance);
    }
    for(std::size_t i=0;i<n;++i)for(std::size_t j=i+1;j<n;++j) {
        const double dx=v->vertices(j,0)-v->vertices(i,0),dy=v->vertices(j,1)-v->vertices(i,1);
        double min_cross=0.0,max_cross=0.0;
        for(std::size_t k=0;k<n;++k) {
            const double cross=dx*(v->vertices(k,1)-v->vertices(i,1))-dy*(v->vertices(k,0)-v->vertices(i,0));
            min_cross=std::min(min_cross,cross);max_cross=std::max(max_cross,cross);
        }
        const double edge_tolerance=tolerance(std::max(std::abs(min_cross),std::abs(max_cross)));
        if(min_cross>=-edge_tolerance || max_cross<=edge_tolerance) {
            const double point_cross=dx*(point[1]-v->vertices(i,1))-dy*(point[0]-v->vertices(i,0));
            if(min_cross>=-edge_tolerance && point_cross < -tolerance(std::abs(point_cross))) return false;
            if(max_cross<=edge_tolerance && point_cross > tolerance(std::abs(point_cross))) return false;
        }
    }
    return true;
}

GeometryCallOutcome parent_reachable_envelope(
        const FiniteActionNominalRequest& request,
        const registry::PreparedProvider<registry::GeometryPort>& provider,
        std::size_t stage, const Vector& parent, const ExecutionContext& context) {
    const auto dynamics_value = request.system.stage({stage});
    if(const auto* error = std::get_if<Diagnostic>(&dynamics_value)) return unsupported(error->field, error->explanation);
    const auto& dynamics = std::get<model::DynamicsStage>(dynamics_value);
    const auto dimension = parent.size();
    Matrix map{dimension, dimension, Vector(dimension * dimension)};
    Vector offset(dimension);
    for(std::size_t row=0;row<dimension;++row) {
        offset[row]=dynamics.offset[row];
        if(request.nominal_disturbances[stage].size()==dimension)
            offset[row]+=request.nominal_disturbances[stage][row];
        for(std::size_t col=0;col<dimension;++col) map.values[row*dimension+col]=dynamics.A(row,col);
    }
    auto point_view=numeric::snapshot_vector(parent);
    if(!std::holds_alternative<numeric::VectorView>(point_view))
        return unsupported("finite_graph.reachable.parent", "Could not snapshot the retained parent state.");
    auto singleton=sets::make_singleton({{"finite-graph-parent"},dimension,
        {}},std::get<numeric::VectorView>(point_view));
    if(const auto* error=std::get_if<Diagnostic>(&singleton))return unsupported(error->field,error->explanation);
    const auto base=run_geometry(provider,request,
        AffineImage{std::get<sets::SetData>(singleton).as_handle(),std::move(map),std::move(offset)},
        "graph-forward-affine-"+std::to_string(stage),context);
    if(const auto* error=std::get_if<Unsupported>(&base))return *error;
    if(const auto* stopped=std::get_if<OperationStopped>(&base))return *stopped;
    const auto action_set=action_state_hull(request,stage);
    if(const auto* error=std::get_if<Unsupported>(&action_set))return *error;
    return run_geometry(provider,request,
        MinkowskiSum{std::get<sets::SetData>(base).as_handle(),std::get<sets::SetData>(action_set).as_handle()},
        "graph-forward-control-sum-"+std::to_string(stage),context);
}

} // namespace

static FiniteActionGraphOutcome finite_action_stage_layered_graph_impl(const FiniteActionNominalRequest& request,
        FiniteActionGraphLimits limits,
        const registry::PreparedProvider<registry::GeometryPort>& projection_provider,
        const registry::PreparedProvider<registry::GeometryPort>* reachable_set_provider,
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
    if(const auto invalid_cost = validate_running_cost(request.running_cost, request.absolute_stage_offset,
            horizon, dimensions.control); !invalid_cost.diagnostics.empty()) return invalid_cost;
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
        false, {}, {}, {}, {}, FiniteGraphBackwardStatus::root_node, {}});
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
            std::optional<sets::SetData> reachable_envelope;
            if(reachable_set_provider) {
                auto envelope = parent_reachable_envelope(request, *reachable_set_provider,
                    stage, parent.state, context);
                graph.reachable_envelope_calls += 2;
                if(const auto* error = std::get_if<Unsupported>(&envelope)) return *error;
                if(const auto* stopped = std::get_if<OperationStopped>(&envelope)) return *stopped;
                reachable_envelope = std::get<sets::SetData>(std::move(envelope));
                const auto representation = reachable_envelope->representation();
                const auto* v = std::get_if<sets::VRepresentation>(&representation);
                if(!v || v->vertices.cols()!=dimensions.state || v->rays.rows()!=0)
                    return unsupported("finite_graph.reachable.output", "Selected reachable-set provider must return a bounded state-space V polytope.");
            }
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
                std::optional<bool> envelope_ok;
                if(reachable_envelope) {
                    envelope_ok = contains_v_2d(*reachable_envelope, next);
                    if(!*envelope_ok)
                        return unsupported("finite_graph.reachable.witness", "The registered forward outer set failed to contain a child generated by the same authored affine dynamics and discrete action.");
                }
                const auto absolute = request.absolute_stage_offset + stage;
                const auto edge_cost = stage_cost(request.running_cost, absolute, request.actions.catalogue[action_index]);
                const auto terminal_value = evaluate(request.objective, next);
                if(const auto* error = std::get_if<Diagnostic>(&terminal_value)) return unsupported(error->field, error->explanation);
                const double heuristic = parent.heuristic_score + edge_cost + std::get<double>(terminal_value);
                auto lineage = parent.action_lineage;
                lineage.push_back(action_index);
                candidates.push_back({parent_id, action_index, std::move(next), edge_cost, heuristic,
                    state_ok, envelope_ok, std::move(lineage)});
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
                candidate.state_admissible, false, {}, {}, {}, candidate.lineage,
                FiniteGraphBackwardStatus::pending, candidate.reachable_envelope_contains});
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
        node.backward_viable = node.state_admissible && node.reachable_envelope_contains.value_or(true);
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
            child.backward_viable = *child.discrete_transition_witness && *child.predecessor_contains_parent &&
                parent.state_admissible && child.reachable_envelope_contains.value_or(true);
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

FiniteActionGraphOutcome finite_action_stage_layered_graph(const FiniteActionNominalRequest& request,
        FiniteActionGraphLimits limits,
        const registry::PreparedProvider<registry::GeometryPort>& projection_provider,
        const ExecutionContext& context) {
    return finite_action_stage_layered_graph_impl(request, limits, projection_provider, nullptr, context);
}

FiniteActionGraphOutcome finite_action_stage_layered_graph(const FiniteActionNominalRequest& request,
        FiniteActionGraphLimits limits,
        const registry::PreparedProvider<registry::GeometryPort>& projection_provider,
        const registry::PreparedProvider<registry::GeometryPort>& reachable_set_provider,
        const ExecutionContext& context) {
    return finite_action_stage_layered_graph_impl(request, limits, projection_provider, &reachable_set_provider, context);
}

} // namespace csl::optimization
