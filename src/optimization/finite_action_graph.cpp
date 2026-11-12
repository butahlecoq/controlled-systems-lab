#include <csl/optimization/finite_action_graph.hpp>

#include <csl/geometry/polyhedral_intersection.hpp>
#include <csl/reachability/nominal_predecessor.hpp>
#include <csl/reachability/finite_plan_box.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>
#include <csl/reachability/finite_plan_parallelotope.hpp>
#include <csl/reachability/finite_plan_ellipsoid.hpp>
#include <csl/sets/data.hpp>
#include <csl/model/linear_system.hpp>

#include "running_cost_evaluation.hpp"

#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <numeric>
#include <chrono>
#include <type_traits>

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
            if(quadratic->coefficient == 0.0) continue;
            const auto quadratic_cost = detail::quadratic_stage_cost(*quadratic, control);
            if(!quadratic_cost) return std::numeric_limits<double>::quiet_NaN();
            total += *quadratic_cost;
        } else {
            const auto& norm = std::get<EuclideanControlPenalty>(term);
            if(norm.coefficient == 0.0) continue;
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
    std::optional<bool> representation_filter_passed;
    std::string representation_filter_outcome;
    Vector representation_outer_lower;
    Vector representation_outer_upper;
    std::vector<std::size_t> lineage;
};

struct RepresentationFilter { bool passed{}; std::string outcome; Vector lower; Vector upper; };
using RepresentationFilterOutcome = std::variant<RepresentationFilter, Unsupported, OperationStopped>;

Matrix copy_matrix(const numeric::MatrixView& source) {
    Matrix result{source.rows(), source.cols(), Vector(source.rows() * source.cols())};
    for(std::size_t row=0;row<source.rows();++row)
        for(std::size_t col=0;col<source.cols();++col)
            result.values[row*result.cols+col]=source(row,col);
    return result;
}

RepresentationFilterOutcome representation_edge_filter(const FiniteActionNominalRequest& request,
        NominalRepresentation representation, std::size_t stage, const Vector& parent,
        const Vector& action, const Vector& expected_child, std::size_t max_generators,
        const std::string& edge_id, const ExecutionContext& context) {
    const auto source_dynamics=request.system.stage({stage});
    if(const auto* error=std::get_if<Diagnostic>(&source_dynamics))
        return unsupported(error->field,error->explanation);
    const auto& d=std::get<model::DynamicsStage>(source_dynamics);
    const auto dimensions=request.system.dimensions();
    const Matrix a=copy_matrix(d.A),b=copy_matrix(d.B),e=copy_matrix(d.E);
    Vector offset(dimensions.state);
    for(std::size_t i=0;i<dimensions.state;++i) offset[i]=d.offset[i];
    SystemModel one_step_model{{dimensions,TimeDomain::discrete,
        std::vector<LinearStage>{{a,b,e,offset}}},{}};
    const double times[]{0.0,1.0};
    auto system=model::snapshot(one_step_model,times);
    if(const auto* error=std::get_if<Diagnostic>(&system)) return unsupported(error->field,error->explanation);
    const auto singleton=[&](const Vector& values,const std::string& id)->std::variant<sets::SetData,Unsupported> {
        auto view=numeric::snapshot_vector(values);
        if(const auto* error=std::get_if<Diagnostic>(&view)) return unsupported(error->field,error->explanation);
        auto set=sets::make_singleton({{id},values.size(),{}},std::get<numeric::VectorView>(view));
        if(const auto* error=std::get_if<Diagnostic>(&set)) return unsupported(error->field,error->explanation);
        return std::get<sets::SetData>(std::move(set));
    };
    auto initial=singleton(parent,"graph-representation-parent");
    if(const auto* error=std::get_if<Unsupported>(&initial)) return *error;
    auto disturbance=singleton(request.nominal_disturbances[stage],"graph-representation-disturbance");
    if(const auto* error=std::get_if<Unsupported>(&disturbance)) return *error;
    reachability::FixedPlanRequest fixed{std::get<model::LinearSystem>(std::move(system)),
        std::get<sets::SetData>(std::move(initial)),{action},
        {std::get<sets::SetData>(std::move(disturbance))},
        {request.admissible_states[stage],request.admissible_states[stage+1]},
        {request.request.value+"/representation-edge-"+edge_id}};

    Vector lower,upper;
    const auto bounded=[&](const auto& trace)->bool {
        const auto& last=trace.stages.back();
        lower.assign(dimensions.state,0.0); upper.assign(dimensions.state,0.0);
        if constexpr(std::is_same_v<std::decay_t<decltype(last)>,reachability::BoxStage>) {
            lower=last.lower;upper=last.upper;
        } else if constexpr(std::is_same_v<std::decay_t<decltype(last)>,reachability::FinitePlanZonotopeTrace::Stage>) {
            lower=last.center;upper=last.center;
            for(std::size_t row=0;row<dimensions.state;++row)
                for(std::size_t col=0;col<last.generators.cols;++col) {
                    const auto radius=std::abs(last.generators.values[row*last.generators.cols+col]);
                    lower[row]-=radius;upper[row]+=radius;
                }
        } else if constexpr(std::is_same_v<std::decay_t<decltype(last)>,reachability::ParallelotopeStage>) {
            for(std::size_t row=0;row<dimensions.state;++row)
                for(std::size_t col=0;col<dimensions.state;++col) {
                    const auto q=trace.frame.values[row*dimensions.state+col];
                    const auto midpoint=(last.lower[col]+last.upper[col])*0.5;
                    const auto radius=(last.upper[col]-last.lower[col])*0.5;
                    lower[row]+=q*midpoint-std::abs(q)*radius;
                    upper[row]+=q*midpoint+std::abs(q)*radius;
                }
        } else {
            for(std::size_t row=0;row<dimensions.state;++row) {
                lower[row]=last.center[row]-last.radii[row];
                upper[row]=last.center[row]+last.radii[row];
            }
        }
        return lower.size()==expected_child.size() && upper.size()==expected_child.size();
    };
    const auto member=[&]() {
        for(std::size_t i=0;i<expected_child.size();++i)
            if(expected_child[i]<lower[i]-1e-9-1e-10*std::abs(expected_child[i]) ||
               expected_child[i]>upper[i]+1e-9+1e-10*std::abs(expected_child[i])) return false;
        return true;
    };
    const auto not_outer_safe=[](const Unsupported& value) {
        return !value.diagnostics.empty() && value.diagnostics.front().field.find("safe_sets")!=std::string::npos;
    };
    if(representation==NominalRepresentation::box) {
        auto result=reachability::finite_plan_box(fixed,context);
        if(const auto* stopped=std::get_if<OperationStopped>(&result))return *stopped;
        if(const auto* error=std::get_if<Unsupported>(&result)) {
            if(not_outer_safe(*error))return RepresentationFilter{false,"outer_enclosure_not_contained_in_stage_set",{}, {}};
            return *error;
        }
        bounded(std::get<reachability::FinitePlanBoxTrace>(result));
        const bool contains=member();
        return RepresentationFilter{contains,contains?"box_outer_contains_discrete_child":"box_outer_misses_discrete_child",std::move(lower),std::move(upper)};
    }
    if(representation==NominalRepresentation::zonotope) {
        auto result=reachability::finite_plan_zonotope(fixed,{max_generators},context);
        if(const auto* stopped=std::get_if<OperationStopped>(&result))return *stopped;
        if(const auto* error=std::get_if<Unsupported>(&result)) {
            if(not_outer_safe(*error))return RepresentationFilter{false,"outer_enclosure_not_contained_in_stage_set",{}, {}};
            return *error;
        }
        bounded(std::get<reachability::FinitePlanZonotopeTrace>(result));
        const bool contains=member();
        return RepresentationFilter{contains,contains?"zonotope_coordinate_outer_contains_discrete_child":"zonotope_coordinate_outer_misses_discrete_child",std::move(lower),std::move(upper)};
    }
    if(representation==NominalRepresentation::parallelotope) {
        auto result=reachability::finite_plan_parallelotope(fixed,context);
        if(const auto* stopped=std::get_if<OperationStopped>(&result))return *stopped;
        if(const auto* error=std::get_if<Unsupported>(&result)) {
            if(not_outer_safe(*error))return RepresentationFilter{false,"outer_enclosure_not_contained_in_stage_set",{}, {}};
            return *error;
        }
        bounded(std::get<reachability::FinitePlanParallelotopeTrace>(result));
        const bool contains=member();
        return RepresentationFilter{contains,contains?"parallelotope_coordinate_outer_contains_discrete_child":"parallelotope_coordinate_outer_misses_discrete_child",std::move(lower),std::move(upper)};
    }
    if(representation==NominalRepresentation::ellipsoid) {
        auto result=reachability::finite_plan_ellipsoid(fixed,context);
        if(const auto* stopped=std::get_if<OperationStopped>(&result))return *stopped;
        if(const auto* error=std::get_if<Unsupported>(&result)) {
            if(not_outer_safe(*error))return RepresentationFilter{false,"outer_enclosure_not_contained_in_stage_set",{}, {}};
            return *error;
        }
        bounded(std::get<reachability::FinitePlanEllipsoidTrace>(result));
        const bool contains=member();
        return RepresentationFilter{contains,contains?"ellipsoid_coordinate_outer_contains_discrete_child":"ellipsoid_coordinate_outer_misses_discrete_child",std::move(lower),std::move(upper)};
    }
    return unsupported("finite_graph.representation_filter","Only box, zonotope, parallelotope and ellipsoid edge filters are supported.");
}

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
        for(std::size_t col=0;col<request.nominal_disturbances[stage].size();++col)
            offset[row]+=dynamics.E(row,col)*request.nominal_disturbances[stage][col];
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

std::string geometry_operation_name(const GeometryOperation& operation) {
    return std::visit([](const auto& value) {
        using T=std::decay_t<decltype(value)>;
        if constexpr(std::is_same_v<T,AffineImage>) return std::string{"affine-image"};
        if constexpr(std::is_same_v<T,MinkowskiSum>) return std::string{"minkowski-sum"};
        if constexpr(std::is_same_v<T,DependentSum>) return std::string{"dependent-sum"};
        if constexpr(std::is_same_v<T,Intersection>) return std::string{"intersection"};
        if constexpr(std::is_same_v<T,Projection>) return std::string{"projection"};
        if constexpr(std::is_same_v<T,AffinePreimage>) return std::string{"affine-preimage"};
        if constexpr(std::is_same_v<T,SupportQuery>) return std::string{"support-query"};
        return std::string{"containment-query"};
    },operation);
}

std::string diagnostics_text(const Diagnostics& diagnostics) {
    std::string text;
    for(const auto& item:diagnostics) {
        if(!text.empty()) text += "; ";
        text += item.field + ": " + item.explanation;
    }
    return text;
}

GeometryCallOutcome run_geometry(const registry::PreparedProvider<registry::GeometryPort>& provider,
        const FiniteActionNominalRequest& request, GeometryOperation operation,
        std::string suffix, const ExecutionContext& context,
        std::vector<FiniteGraphGeometryInvocation>* observations,
        const FiniteGraphGeometryObserver& observer,
        std::size_t absolute_stage,std::size_t parent_node_id) {
    const auto provenance = provider.provenance();
    const auto implementation = provenance.actual ? provenance.actual->id : provenance.requested.id;
    GeometryRequestIdentity identity{request.problem,
        {request.request.value + "/" + suffix}, {request.request.value + "/" + suffix + "/output"}};
    OperationRequest geometry_request{identity, implementation, std::move(operation),
        SetRelation::equivalent, Assurance::numerical};
    const auto reference=geometry_reference(geometry_request);
    const auto started=std::chrono::steady_clock::now();
    const auto make_observation=[&](std::string outcome,std::optional<SetRelation> relation,
            std::vector<std::string> assumptions,std::string diagnostics) {
        if(!observations) return;
        const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now()-started);
        FiniteGraphGeometryInvocation record;
        record.absolute_stage=absolute_stage;
        record.parent_node_id=parent_node_id;
        record.request_id=geometry_request.identity.request.value;
        record.ideal_output_id=geometry_request.identity.ideal_output.value;
        for(const auto& id:reference.inputs) record.input_ids.push_back(id.value);
        record.operation=geometry_operation_name(geometry_request.operation);
        record.requested_method_id=provenance.requested.id.value;
        record.actual_method_id=provenance.actual?provenance.actual->id.value:"unresolved-provider";
        record.actual_method_version=provenance.actual?provenance.actual->version:"unresolved";
        record.outcome=std::move(outcome);
        record.relation=relation;
        record.elapsed=elapsed;
        record.evidence_assumptions=std::move(assumptions);
        record.diagnostics=std::move(diagnostics);
        observations->push_back(record);
        if(observer) observer(record);
    };
    auto prepared = provider.prepare(geometry_request);
    if(const auto* rejection = std::get_if<registry::Rejection>(&prepared)) {
        make_observation("provider_rejected",{}, {},diagnostics_text(rejection->diagnostics));
        return Unsupported{rejection->diagnostics};
    }
    auto workspace = std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(prepared)).create();
    auto outcome = std::get<0>(workspace)->run(context);
    if(const auto* stopped = std::get_if<OperationStopped>(&outcome)) {
        make_observation("stopped",{}, {},stopped->diagnostics);
        return *stopped;
    }
    if(const auto* error = std::get_if<Unsupported>(&outcome)) {
        make_observation("unsupported",{}, {},diagnostics_text(error->diagnostics));
        return *error;
    }
    const auto* result = std::get_if<OperationResult>(&outcome);
    if(!result) {
        make_observation("unexpected_query_result",{}, {},"Selected reachable-set operation returned a query result rather than a set.");
        return unsupported("finite_graph.reachable.operation", "Selected reachable-set operation returned a query result rather than a set.");
    }
    if(const auto diagnostics = check_geometry_evidence(result->evidence, geometry_request); !diagnostics.empty()) {
        make_observation("invalid_evidence",result->relation,result->evidence.assumptions,diagnostics_text(diagnostics));
        return Unsupported{diagnostics};
    }
    if(result->relation != SetRelation::equivalent) {
        make_observation("wrong_relation",result->relation,result->evidence.assumptions,"Expected equivalent set relation.");
        return unsupported("finite_graph.reachable.evidence", "Reachable-set operation must return an equivalent numerical set result.");
    }
    auto set = sets::from_handle(result->output);
    if(const auto* error = std::get_if<Diagnostic>(&set)) {
        make_observation("invalid_output",result->relation,result->evidence.assumptions,error->explanation);
        return unsupported(error->field, error->explanation);
    }
    make_observation("completed",result->relation,result->evidence.assumptions,{});
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
    const auto action_hull_id="finite-graph-state-action-hull/"+request.request.value+"/stage-"+
        std::to_string(request.absolute_stage_offset+stage);
    const auto made = sets::make_v({{action_hull_id}, vertices.cols, {}},
        {std::get<numeric::MatrixView>(vertex_view), std::get<numeric::MatrixView>(ray_view)});
    if(const auto* error = std::get_if<Diagnostic>(&made)) return unsupported(error->field, error->explanation);
    return std::get<sets::SetData>(made);
}

bool contains_v(const sets::SetData& set, std::span<const double> point,
        double absolute_tolerance = 1e-9, double relative_tolerance = 1e-10) {
    const auto representation = set.representation();
    const auto* v = std::get_if<sets::VRepresentation>(&representation);
    if(!v || point.empty() || point.size() != v->vertices.cols() || v->rays.rows() != 0 || v->vertices.rows() == 0)
        return false;
    const auto dimension=point.size(), count=v->vertices.rows();
    const auto tolerance=[&](double scale) { return absolute_tolerance+relative_tolerance*scale; };
    const auto max_vertices=std::min(count,dimension+1);
    std::vector<std::size_t> selected;
    for(std::size_t subset_size=1;subset_size<=max_vertices;++subset_size) {
        bool found=false;
        std::function<void(std::size_t)> visit=[&](std::size_t next) {
            if(found)return;
            if(selected.size()==subset_size) {
                const auto rows=dimension+1,cols=subset_size;
                std::vector<double> matrix(rows*(cols+1),0.0);
                double scale=1.0;
                for(std::size_t row=0;row<dimension;++row) {
                    for(std::size_t col=0;col<cols;++col) {
                        const auto value=v->vertices(selected[col],row);
                        matrix[row*(cols+1)+col]=value;
                        scale=std::max(scale,std::abs(value));
                    }
                    matrix[row*(cols+1)+cols]=point[row];
                    scale=std::max(scale,std::abs(point[row]));
                }
                for(std::size_t col=0;col<cols;++col)matrix[dimension*(cols+1)+col]=1.0;
                matrix[dimension*(cols+1)+cols]=1.0;
                const auto pivot_tolerance=std::max(1e-13,relative_tolerance*scale);
                std::vector<std::size_t> pivot_rows(cols,rows);
                std::size_t rank=0;
                for(std::size_t col=0;col<cols;++col) {
                    std::size_t pivot=rank;
                    for(std::size_t row=rank;row<rows;++row)
                        if(std::abs(matrix[row*(cols+1)+col])>std::abs(matrix[pivot*(cols+1)+col]))pivot=row;
                    if(rank==rows || std::abs(matrix[pivot*(cols+1)+col])<=pivot_tolerance)return;
                    for(std::size_t j=0;j<=cols;++j)std::swap(matrix[rank*(cols+1)+j],matrix[pivot*(cols+1)+j]);
                    const auto divisor=matrix[rank*(cols+1)+col];
                    for(std::size_t j=col;j<=cols;++j)matrix[rank*(cols+1)+j]/=divisor;
                    for(std::size_t row=0;row<rows;++row)if(row!=rank) {
                        const auto factor=matrix[row*(cols+1)+col];
                        for(std::size_t j=col;j<=cols;++j)matrix[row*(cols+1)+j]-=factor*matrix[rank*(cols+1)+j];
                    }
                    pivot_rows[col]=rank++;
                }
                for(std::size_t row=rank;row<rows;++row) {
                    double coefficient_scale=0.0;
                    for(std::size_t col=0;col<cols;++col)coefficient_scale=std::max(coefficient_scale,std::abs(matrix[row*(cols+1)+col]));
                    if(coefficient_scale<=pivot_tolerance && std::abs(matrix[row*(cols+1)+cols])>tolerance(scale))return;
                }
                double sum=0.0;
                for(std::size_t col=0;col<cols;++col) {
                    const auto weight=matrix[pivot_rows[col]*(cols+1)+cols];
                    if(weight < -tolerance(1.0))return;
                    sum+=weight;
                }
                found=std::abs(sum-1.0)<=tolerance(1.0);
                return;
            }
            const auto remaining=subset_size-selected.size();
            for(std::size_t i=next;i+remaining<=count;++i) {
                selected.push_back(i);visit(i+1);selected.pop_back();
                if(found)return;
            }
        };
        visit(0);
        if(found)return true;
    }
    return false;
}

struct ParentActionCloud { FiniteGraphActionCloudEnvelope record; };
using ParentActionCloudOutcome = std::variant<ParentActionCloud,Unsupported,OperationStopped>;

std::optional<bool> outer_box_inside_set(std::span<const double> lower,
        std::span<const double> upper, const sets::SetData& set) {
    if(lower.size()!=upper.size() || lower.size()!=set.metadata()->set.dimension) return false;
    const auto representation=set.representation();
    if(std::holds_alternative<sets::UniversalRepresentation>(representation))return true;
    if(std::holds_alternative<sets::EmptyRepresentation>(representation))return false;
    if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation)) {
        if(singleton->point.size()!=lower.size())return false;
        for(std::size_t i=0;i<lower.size();++i)
            if(lower[i]!=singleton->point[i] || upper[i]!=singleton->point[i])return false;
        return true;
    }
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h)return std::nullopt;
    for(std::size_t row=0;row<h->inequalities.rows();++row) {
        double maximum=0.0;
        for(std::size_t col=0;col<lower.size();++col) {
            const auto a=h->inequalities(row,col);
            const auto endpoint=a>=0.0?upper[col]:lower[col];
            const auto product=a*endpoint;
            if(!std::isfinite(product))return false;
            maximum=std::nextafter(maximum+std::nextafter(product,
                std::numeric_limits<double>::infinity()),std::numeric_limits<double>::infinity());
        }
        if(maximum>h->upper_bounds[row])return false;
    }
    if(h->equalities.rows()!=0)return false;
    return true;
}

ParentActionCloudOutcome parent_action_cloud(const FiniteActionNominalRequest& request,
        NominalRepresentation representation,std::size_t stage,std::size_t parent_id,
        const Vector& parent,std::size_t max_generators,const ExecutionContext& context) {
    const auto dimensions=request.system.dimensions();
    const auto original_stage=request.system.stage({stage});
    if(const auto* error=std::get_if<Diagnostic>(&original_stage))return unsupported(error->field,error->explanation);
    const auto& d=std::get<model::DynamicsStage>(original_stage);
    const auto action_effect=action_state_hull(request,stage);
    if(const auto* error=std::get_if<Unsupported>(&action_effect))return *error;
    const auto& effect_set=std::get<sets::SetData>(action_effect);
    const auto effect_rep=effect_set.representation();
    const auto* effect_v=std::get_if<sets::VRepresentation>(&effect_rep);
    if(!effect_v || effect_v->rays.rows()!=0 || effect_v->vertices.rows()!=request.actions.catalogue.size())
        return unsupported("finite_graph.action_cloud.input","Authored B*action images must form a bounded nonempty V cloud.");
    Matrix identity{dimensions.state,dimensions.state,Vector(dimensions.state*dimensions.state,0.0)};
    Matrix zero_control{dimensions.state,dimensions.control,Vector(dimensions.state*dimensions.control,0.0)};
    for(std::size_t i=0;i<dimensions.state;++i)identity.values[i*dimensions.state+i]=1.0;
    Vector offset(dimensions.state);
    Vector external_contribution(dimensions.state,0.0);
    for(std::size_t i=0;i<dimensions.state;++i) {
        offset[i]=d.offset[i];
        for(std::size_t col=0;col<dimensions.external;++col) {
            const auto term=d.E(i,col)*request.nominal_disturbances[stage][col];
            external_contribution[i]+=term;
            offset[i]+=term;
        }
    }
    const Dimensions lifted_dimensions{dimensions.state,dimensions.control,dimensions.state};
    const auto lifted_offset=offset;
    SystemModel lifted_model{{lifted_dimensions,TimeDomain::discrete,
        std::vector<LinearStage>{{copy_matrix(d.A),std::move(zero_control),std::move(identity),std::move(offset)}}},{}};
    const double times[]{0.0,1.0};
    const auto lifted_system=model::snapshot(lifted_model,times);
    if(const auto* error=std::get_if<Diagnostic>(&lifted_system))return unsupported(error->field,error->explanation);
    const auto auxiliary_id=request.request.value+"/aux-action-cloud-"+
        std::to_string(request.absolute_stage_offset+stage)+"-parent-"+std::to_string(parent_id);
    auto parent_view=numeric::snapshot_vector(parent);
    if(!std::holds_alternative<numeric::VectorView>(parent_view))
        return unsupported("finite_graph.action_cloud.parent","Could not snapshot retained parent state.");
    auto parent_set=sets::make_singleton({{auxiliary_id+"/parent"},dimensions.state,{}},
        std::get<numeric::VectorView>(parent_view));
    if(const auto* error=std::get_if<Diagnostic>(&parent_set))return unsupported(error->field,error->explanation);
    const auto safe=sets::make_universal({{auxiliary_id+"/safe"},dimensions.state,{}});
    if(const auto* error=std::get_if<Diagnostic>(&safe))return unsupported(error->field,error->explanation);
    reachability::FixedPlanRequest auxiliary{std::get<model::LinearSystem>(lifted_system),
        std::get<sets::SetData>(parent_set),{Vector(dimensions.control,0.0)},{effect_set},
        {std::get<sets::SetData>(safe),std::get<sets::SetData>(safe)},{auxiliary_id}};

    Vector lower,upper;
    std::string module;
    FiniteGraphActionCloudShape selected_shape{FiniteGraphBoxShape{}};
    const auto as_bounds=[&](const auto& last,const auto& frame) {
        lower.resize(dimensions.state);upper.resize(dimensions.state);
        using Stage=std::decay_t<decltype(last)>;
        if constexpr(std::is_same_v<Stage,reachability::BoxStage>) {
            lower=last.lower;upper=last.upper;
        } else if constexpr(std::is_same_v<Stage,reachability::FinitePlanZonotopeTrace::Stage>) {
            lower=last.center;upper=last.center;
            for(std::size_t row=0;row<dimensions.state;++row)
                for(std::size_t col=0;col<last.generators.cols;++col) {
                    const auto radius=std::abs(last.generators.values[row*last.generators.cols+col]);
                    lower[row]=std::nextafter(lower[row]-radius,-std::numeric_limits<double>::infinity());
                    upper[row]=std::nextafter(upper[row]+radius,std::numeric_limits<double>::infinity());
                }
        } else if constexpr(std::is_same_v<Stage,reachability::ParallelotopeStage>) {
            for(std::size_t row=0;row<dimensions.state;++row)
                for(std::size_t col=0;col<dimensions.state;++col) {
                    const auto q=frame.values[row*dimensions.state+col];
                    const auto left=q*last.lower[col],right=q*last.upper[col];
                    const auto term_lower=std::nextafter(std::min(left,right),-std::numeric_limits<double>::infinity());
                    const auto term_upper=std::nextafter(std::max(left,right),std::numeric_limits<double>::infinity());
                    lower[row]=std::nextafter(lower[row]+term_lower,-std::numeric_limits<double>::infinity());
                    upper[row]=std::nextafter(upper[row]+term_upper,std::numeric_limits<double>::infinity());
                }
        } else {
            lower.resize(last.center.size());upper.resize(last.center.size());
            for(std::size_t i=0;i<last.center.size();++i) {
                lower[i]=std::nextafter(last.center[i]-last.radii[i],-std::numeric_limits<double>::infinity());
                upper[i]=std::nextafter(last.center[i]+last.radii[i],std::numeric_limits<double>::infinity());
            }
        }
    };
    if(representation==NominalRepresentation::box) {
        module="csl::reachability::finite_plan_box";
        const auto outcome=reachability::finite_plan_box(auxiliary,context);
        if(const auto* stopped=std::get_if<OperationStopped>(&outcome))return *stopped;
        if(const auto* error=std::get_if<Unsupported>(&outcome))return *error;
        const auto& shape=std::get<reachability::FinitePlanBoxTrace>(outcome).stages.back();
        selected_shape=FiniteGraphBoxShape{shape.lower,shape.upper};
        as_bounds(shape,Matrix{});
    } else if(representation==NominalRepresentation::zonotope) {
        module="csl::reachability::finite_plan_zonotope";
        const auto outcome=reachability::finite_plan_zonotope(auxiliary,{max_generators},context);
        if(const auto* stopped=std::get_if<OperationStopped>(&outcome))return *stopped;
        if(const auto* error=std::get_if<Unsupported>(&outcome))return *error;
        const auto& shape=std::get<reachability::FinitePlanZonotopeTrace>(outcome).stages.back();
        selected_shape=FiniteGraphZonotopeShape{shape.center,shape.generators};
        as_bounds(shape,Matrix{});
    } else if(representation==NominalRepresentation::parallelotope) {
        module="csl::reachability::finite_plan_parallelotope";
        const auto outcome=reachability::finite_plan_parallelotope(auxiliary,context);
        if(const auto* stopped=std::get_if<OperationStopped>(&outcome))return *stopped;
        if(const auto* error=std::get_if<Unsupported>(&outcome))return *error;
        const auto& trace=std::get<reachability::FinitePlanParallelotopeTrace>(outcome);
        const auto& shape=trace.stages.back();
        selected_shape=FiniteGraphParallelotopeShape{trace.frame,shape.lower,shape.upper};
        as_bounds(trace.stages.back(),trace.frame);
    } else if(representation==NominalRepresentation::ellipsoid) {
        module="csl::reachability::finite_plan_ellipsoid";
        const auto outcome=reachability::finite_plan_ellipsoid(auxiliary,context);
        if(const auto* stopped=std::get_if<OperationStopped>(&outcome))return *stopped;
        if(const auto* error=std::get_if<Unsupported>(&outcome))return *error;
        const auto& shape=std::get<reachability::FinitePlanEllipsoidTrace>(outcome).stages.back();
        selected_shape=FiniteGraphEllipsoidShape{shape.center,shape.radii};
        as_bounds(shape,Matrix{});
    } else return unsupported("finite_graph.action_cloud.representation","Only the four selected numerical approximation modules support this cloud route.");
    if(lower.size()!=dimensions.state || upper.size()!=dimensions.state || !finite(lower) || !finite(upper))
        return unsupported("finite_graph.action_cloud.output","Selected set module did not produce finite coordinate outer bounds.");

    FiniteGraphActionCloudEnvelope record;
    const auto parent_time=request.system.time({stage});
    const auto output_time=request.system.time({stage+1});
    if(const auto* error=std::get_if<Diagnostic>(&parent_time))return unsupported(error->field,error->explanation);
    if(const auto* error=std::get_if<Diagnostic>(&output_time))return unsupported(error->field,error->explanation);
    record.stage=request.absolute_stage_offset+stage;
    record.output_stage=request.absolute_stage_offset+stage+1;
    record.parent_time=std::get<double>(parent_time);
    record.output_time=std::get<double>(output_time);
    record.parent_node=parent_id;
    record.representation=representation;record.module_id=std::move(module);
    record.auxiliary_request_id=auxiliary_id;record.parent_state=parent;
    record.auxiliary_A=copy_matrix(d.A);
    record.original_E=copy_matrix(d.E);
    record.source_nominal_external=request.nominal_disturbances[stage];
    record.lifted_external_contribution=external_contribution;
    record.auxiliary_B={dimensions.state,dimensions.control,Vector(dimensions.state*dimensions.control,0.0)};
    record.auxiliary_E={dimensions.state,dimensions.state,Vector(dimensions.state*dimensions.state,0.0)};
    record.auxiliary_offset=lifted_offset;
    for(std::size_t i=0;i<dimensions.state;++i) {
        record.auxiliary_E.values[i*dimensions.state+i]=1.0;
    }
    record.auxiliary_control=Vector(dimensions.control,0.0);
    record.outer_lower=lower;record.outer_upper=upper;record.selected_outer_shape=std::move(selected_shape);
    record.outer_inside_authored_stage_set=outer_box_inside_set(lower,upper,request.admissible_states[stage+1]);
    for(std::size_t row=0;row<effect_v->vertices.rows();++row) {
        Vector vertex(dimensions.state);
        for(std::size_t col=0;col<dimensions.state;++col)vertex[col]=effect_v->vertices(row,col);
        record.authored_action_effect_vertices.push_back(std::move(vertex));
    }
    for(std::size_t action=0;action<request.actions.catalogue.size();++action) {
        const auto child=request.system.step({stage},parent,request.actions.catalogue[action],request.nominal_disturbances[stage]);
        if(const auto* error=std::get_if<Diagnostic>(&child))return unsupported(error->field,error->explanation);
        if(const auto* stopped=std::get_if<OperationStopped>(&child))return *stopped;
        const auto state=std::get<Vector>(child);
        const auto& effect=record.authored_action_effect_vertices[action];
        bool affine_equivalent=true;
        for(std::size_t row=0;row<state.size();++row) {
            double reconstructed=d.offset[row]+external_contribution[row];
            for(std::size_t col=0;col<dimensions.state;++col)reconstructed+=d.A(row,col)*parent[col];
            reconstructed+=effect[row];
            affine_equivalent=affine_equivalent && std::abs(reconstructed-state[row])<=1e-9+
                1e-10*std::max(std::abs(reconstructed),std::abs(state[row]));
        }
        if(!affine_equivalent)return unsupported("finite_graph.action_cloud.lineage","Lifted auxiliary action image does not match the original affine model transition.");
        bool coordinate_inside=true;
        for(std::size_t i=0;i<state.size();++i) {
            if(state[i]<lower[i] || state[i]>upper[i]) {
                coordinate_inside=false;
                break;
            }
        }
        const auto shape_membership=finite_graph_action_cloud_membership(record,state);
        if(!shape_membership.supported)
            return unsupported("finite_graph.action_cloud.shape_membership.inconclusive",
                "Selected-shape membership witness is unsupported for this numeric generator/frame layout; this is not a physical infeasibility result.");
        if(!shape_membership.contained)
            return unsupported("finite_graph.action_cloud.shape_membership.refused",
                "A recomputed authored action child failed the selected-shape numeric membership check; no edge is certified from this approximation.");
        record.action_witnesses.push_back({action,state,shape_membership.contained,coordinate_inside,
            shape_membership.method,shape_membership.witness_coordinates,
            shape_membership.reconstruction_residual,shape_membership.tolerance,
            shape_membership.tolerance_scale,
            "max(64*epsilon*global-coordinate-scale,64*denorm_min)",
            "Accepted by selected-shape numerical membership predicate; this is not a literal set-inclusion claim. The original-versus-lifted affine transition was recomputed within numerical tolerance."});
    }
    return ParentActionCloud{std::move(record)};
}

GeometryCallOutcome parent_reachable_envelope(
        const FiniteActionNominalRequest& request,
        const registry::PreparedProvider<registry::GeometryPort>& provider,
        std::size_t stage,std::size_t parent_node_id,const Vector& parent,const ExecutionContext& context,
        std::vector<FiniteGraphGeometryInvocation>* observations,
        const FiniteGraphGeometryObserver& observer) {
    const auto dynamics_value = request.system.stage({stage});
    if(const auto* error = std::get_if<Diagnostic>(&dynamics_value)) return unsupported(error->field, error->explanation);
    const auto& dynamics = std::get<model::DynamicsStage>(dynamics_value);
    const auto dimension = parent.size();
    Matrix map{dimension, dimension, Vector(dimension * dimension)};
    Vector offset(dimension);
    for(std::size_t row=0;row<dimension;++row) {
        offset[row]=dynamics.offset[row];
        for(std::size_t col=0;col<request.nominal_disturbances[stage].size();++col)
            offset[row]+=dynamics.E(row,col)*request.nominal_disturbances[stage][col];
        for(std::size_t col=0;col<dimension;++col) map.values[row*dimension+col]=dynamics.A(row,col);
    }
    auto point_view=numeric::snapshot_vector(parent);
    if(!std::holds_alternative<numeric::VectorView>(point_view))
        return unsupported("finite_graph.reachable.parent", "Could not snapshot the retained parent state.");
    const auto absolute_stage=request.absolute_stage_offset+stage;
    const auto singleton_id="finite-graph-parent/"+request.request.value+"/stage-"+
        std::to_string(absolute_stage)+"-node-"+std::to_string(parent_node_id);
    auto singleton=sets::make_singleton({{singleton_id},dimension,
        {}},std::get<numeric::VectorView>(point_view));
    if(const auto* error=std::get_if<Diagnostic>(&singleton))return unsupported(error->field,error->explanation);
    const auto base=run_geometry(provider,request,
        AffineImage{std::get<sets::SetData>(singleton).as_handle(),std::move(map),std::move(offset)},
        "graph-forward-affine-stage-"+std::to_string(absolute_stage)+"-parent-"+std::to_string(parent_node_id),
        context,observations,observer,absolute_stage,parent_node_id);
    if(const auto* error=std::get_if<Unsupported>(&base))return *error;
    if(const auto* stopped=std::get_if<OperationStopped>(&base))return *stopped;
    const auto action_set=action_state_hull(request,stage);
    if(const auto* error=std::get_if<Unsupported>(&action_set))return *error;
    return run_geometry(provider,request,
        MinkowskiSum{std::get<sets::SetData>(base).as_handle(),std::get<sets::SetData>(action_set).as_handle()},
        "graph-forward-control-sum-stage-"+std::to_string(absolute_stage)+"-parent-"+std::to_string(parent_node_id),
        context,observations,observer,absolute_stage,parent_node_id);
}

} // namespace

static FiniteActionGraphOutcome finite_action_stage_layered_graph_impl(const FiniteActionNominalRequest& request,
        FiniteActionGraphLimits limits,
        const registry::PreparedProvider<registry::GeometryPort>& projection_provider,
        const registry::PreparedProvider<registry::GeometryPort>* reachable_set_provider,
        const ExecutionContext& context, const FiniteGraphGeometryObserver& geometry_observer) {
    const auto dimensions = request.system.dimensions();
    const auto horizon = request.system.horizon();
    if(limits.beam_width == 0 || limits.max_nodes == 0)
        return unsupported("finite_graph.limits", "Beam width and maximum node count must be positive.");
    if(dimensions.state != 2 && dimensions.state != 4)
        return unsupported("finite_graph.model", "The finite-action graph admits 2D or 4D nominal systems.");
    if(request.initial_state.size() != dimensions.state || request.actions.dimension != dimensions.control ||
       request.actions.catalogue.empty() || request.admissible_states.size() != horizon + 1 ||
       request.nominal_disturbances.size() != horizon || request.objective.dimension() != dimensions.state)
        return unsupported("finite_graph.request", "Finite action graph request dimensions do not match the nominal system.");
    for(const auto& disturbance:request.nominal_disturbances)
        if(disturbance.size()!=dimensions.external || !finite(disturbance))
            return unsupported("finite_graph.disturbances","Each authored nominal external input must be finite and match the source model external dimension.");
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
        false, {}, {}, {}, {}, FiniteGraphBackwardStatus::root_node, {}, {}, {}, {}, {}});
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
            if(limits.parent_action_cloud_representation) {
                auto cloud=parent_action_cloud(request,*limits.parent_action_cloud_representation,
                    stage,parent_id,parent.state,limits.max_generators_per_stage,context);
                ++graph.action_cloud_calls;
                if(const auto* error=std::get_if<Unsupported>(&cloud))return *error;
                if(const auto* stopped=std::get_if<OperationStopped>(&cloud))return *stopped;
                graph.action_cloud_envelopes.push_back(std::move(std::get<ParentActionCloud>(cloud).record));
            }
            std::optional<sets::SetData> reachable_envelope;
            if(reachable_set_provider) {
                const auto calls_before=graph.reachable_geometry_invocations.size();
                auto envelope = parent_reachable_envelope(request, *reachable_set_provider,
                    stage,parent_id,parent.state,context,&graph.reachable_geometry_invocations,geometry_observer);
                graph.reachable_envelope_calls += graph.reachable_geometry_invocations.size()-calls_before;
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
                    envelope_ok = contains_v(*reachable_envelope, next);
                    if(!*envelope_ok)
                        return unsupported("finite_graph.reachable.witness", "The registered forward outer set failed to contain a child generated by the same authored affine dynamics and discrete action.");
                }
                const auto absolute = request.absolute_stage_offset + stage;
                const auto edge_cost = stage_cost(request.running_cost, absolute, request.actions.catalogue[action_index]);
                if(!std::isfinite(edge_cost))
                    return unsupported("finite_graph.running_cost.overflow", "Authored running cost overflowed for a finite discrete edge; graph scores are not ranked.");
                std::optional<bool> representation_filter_passed;
                std::string representation_filter_outcome;
                Vector representation_outer_lower,representation_outer_upper;
                if(limits.edge_representation_filter) {
                    if(!state_ok) {
                        representation_filter_passed=false;
                        representation_filter_outcome="discrete_child_outside_authored_stage_set";
                    } else {
                        const auto filtered=representation_edge_filter(request,*limits.edge_representation_filter,
                            stage,parent.state,request.actions.catalogue[action_index],next,
                            limits.max_generators_per_stage,std::to_string(parent_id)+"-"+
                                std::to_string(action_index),context);
                        ++graph.representation_filter_calls;
                        if(const auto* error=std::get_if<Unsupported>(&filtered)) return *error;
                        if(const auto* stopped=std::get_if<OperationStopped>(&filtered)) return *stopped;
                        representation_filter_passed=std::get<RepresentationFilter>(filtered).passed;
                        representation_filter_outcome=std::get<RepresentationFilter>(filtered).outcome;
                        representation_outer_lower=std::get<RepresentationFilter>(filtered).lower;
                        representation_outer_upper=std::get<RepresentationFilter>(filtered).upper;
                    }
                    if(representation_filter_passed==false) ++graph.representation_filter_rejections;
                }
                const auto terminal_value = evaluate(request.objective, next);
                if(const auto* error = std::get_if<Diagnostic>(&terminal_value)) return unsupported(error->field, error->explanation);
                const double terminal = std::get<double>(terminal_value);
                const double heuristic = parent.heuristic_score + edge_cost + terminal;
                if(!std::isfinite(terminal) || !std::isfinite(heuristic))
                    return unsupported("finite_graph.ranking.overflow", "Terminal or accumulated heuristic score is non-finite; graph candidates are not sorted.");
                auto lineage = parent.action_lineage;
                lineage.push_back(action_index);
                candidates.push_back({parent_id, action_index, std::move(next), edge_cost, heuristic,
                    state_ok, envelope_ok, representation_filter_passed,
                    std::move(representation_filter_outcome),std::move(representation_outer_lower),
                    std::move(representation_outer_upper),std::move(lineage)});
            }
        }
        auto& stats = graph.layer_statistics[stage];
        stats.generated = candidates.size();
        std::stable_sort(candidates.begin(), candidates.end(), [](const Candidate& left, const Candidate& right) {
            if(left.state_admissible != right.state_admissible) return left.state_admissible > right.state_admissible;
            if(left.representation_filter_passed.value_or(true) != right.representation_filter_passed.value_or(true))
                return left.representation_filter_passed.value_or(true) > right.representation_filter_passed.value_or(true);
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
                FiniteGraphBackwardStatus::pending, candidate.reachable_envelope_contains,
                candidate.representation_filter_passed,candidate.representation_filter_outcome,
                candidate.representation_outer_lower,candidate.representation_outer_upper});
            graph.layers[stage + 1].push_back(node_id);
            ++graph.layer_statistics[stage + 1].retained;
            if(!candidate.state_admissible) ++graph.layer_statistics[stage + 1].stage_inadmissible;
            if(candidate.representation_filter_passed==false)
                ++graph.layer_statistics[stage+1].representation_filter_rejected;
        }
        if(retained < candidates.size() && graph.nodes.size() >= limits.max_nodes) graph.node_budget_exhausted = true;
        if(retained == 0) break;
    }
    graph.search_complete = !graph.node_budget_exhausted &&
        std::ranges::all_of(graph.layer_statistics, [](const auto& row) { return row.pruned == 0; });
    if(graph.layers.back().empty()) return graph;

    for(const auto id : graph.layers.back()) {
        auto& node = graph.nodes[id];
        node.backward_viable = node.state_admissible && node.reachable_envelope_contains.value_or(true) &&
            node.representation_filter_passed.value_or(true);
        node.backward_status = !node.representation_filter_passed.value_or(true) ?
            FiniteGraphBackwardStatus::representation_filter_rejected :
            (node.state_admissible ? FiniteGraphBackwardStatus::terminal_admissible :
                FiniteGraphBackwardStatus::terminal_outside_stage_set);
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
                if(child.representation_filter_passed.value_or(true))
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
                for(std::size_t col=0;col<request.nominal_disturbances[stage].size();++col)
                    replay[row]+=dynamics.E(row,col)*request.nominal_disturbances[stage][col];
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
            else if(!child.representation_filter_passed.value_or(true)) child.backward_status = FiniteGraphBackwardStatus::representation_filter_rejected;
            else child.backward_status = eligible_status();
            child.backward_viable = *child.discrete_transition_witness && *child.predecessor_contains_parent &&
                parent.state_admissible && child.reachable_envelope_contains.value_or(true) &&
                child.representation_filter_passed.value_or(true);
            if(!child.backward_viable) continue;
            const double candidate = child.edge_running_cost + *child.backward_value;
            if(!std::isfinite(candidate))
                return unsupported("finite_graph.bellman.overflow", "Accumulated backward Bellman value is non-finite; no policy is selected.");
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

FiniteGraphCloudMembership finite_graph_action_cloud_membership(
        const FiniteGraphActionCloudEnvelope& cloud,std::span<const double> point) {
    FiniteGraphCloudMembership result;
    if(point.empty() || point.size()!=cloud.outer_lower.size() || point.size()!=cloud.outer_upper.size() || !finite(point)) {
        result.method="dimension-or-finiteness-invalid";
        return result;
    }
    if(!finite(std::span<const double>(cloud.outer_lower)) || !finite(std::span<const double>(cloud.outer_upper))) {
        result.method="non-finite-coordinate-outer-bounds";
        return result;
    }
    for(std::size_t i=0;i<point.size();++i)if(cloud.outer_lower[i]>cloud.outer_upper[i]) {
        result.method="reversed-coordinate-outer-bounds";
        return result;
    }
    const auto valid_shape=std::visit([&](const auto& shape) {
        using T=std::decay_t<decltype(shape)>;
        if constexpr(std::is_same_v<T,FiniteGraphBoxShape>) {
            if(shape.lower.size()!=point.size() || shape.upper.size()!=point.size() ||
               !finite(std::span<const double>(shape.lower)) || !finite(std::span<const double>(shape.upper)))return false;
            for(std::size_t i=0;i<point.size();++i)if(shape.lower[i]>shape.upper[i])return false;
            return true;
        } else if constexpr(std::is_same_v<T,FiniteGraphParallelotopeShape>) {
            if(shape.frame.rows!=point.size() || shape.frame.cols!=point.size() ||
               shape.frame.values.size()!=point.size()*point.size() ||
               shape.lower.size()!=point.size() || shape.upper.size()!=point.size() ||
               !finite(std::span<const double>(shape.frame.values)) ||
               !finite(std::span<const double>(shape.lower)) || !finite(std::span<const double>(shape.upper)))return false;
            for(std::size_t i=0;i<point.size();++i)if(shape.lower[i]>shape.upper[i])return false;
            return true;
        } else if constexpr(std::is_same_v<T,FiniteGraphEllipsoidShape>) {
            if(shape.center.size()!=point.size() || shape.radii.size()!=point.size() ||
               !finite(std::span<const double>(shape.center)) || !finite(std::span<const double>(shape.radii)))return false;
            return std::all_of(shape.radii.begin(),shape.radii.end(),[](double radius){return radius>=0.0;});
        } else {
            return shape.center.size()==point.size() && shape.generators.rows==point.size() &&
                shape.generators.values.size()==shape.generators.rows*shape.generators.cols &&
                finite(std::span<const double>(shape.center)) && finite(std::span<const double>(shape.generators.values));
        }
    },cloud.selected_outer_shape);
    if(!valid_shape) {
        result.method="malformed-or-non-finite-selected-shape";
        return result;
    }
    double scale=0.0;
    for(const auto value:point)scale=std::max(scale,std::abs(value));
    for(const auto value:cloud.outer_lower)scale=std::max(scale,std::abs(value));
    for(const auto value:cloud.outer_upper)scale=std::max(scale,std::abs(value));
    result.tolerance_scale=scale;
    result.tolerance=std::max(64.0*std::numeric_limits<double>::epsilon()*scale,
        64.0*std::numeric_limits<double>::denorm_min());
    auto membership=std::visit([&](const auto& shape)->FiniteGraphCloudMembership {
        using T=std::decay_t<decltype(shape)>;
        auto membership=result;
        membership.supported=true;
        if constexpr(std::is_same_v<T,FiniteGraphBoxShape>) {
            membership.method="coordinate-membership-in-selected-box";
            membership.contained=shape.lower.size()==point.size() && shape.upper.size()==point.size();
            if(!membership.contained) {
                membership.supported=false;
                membership.method="box-dimension-unsupported";
                return membership;
            }
            membership.witness_coordinates.assign(point.begin(),point.end());
            double residual=0.0;
            for(std::size_t i=0;i<point.size();++i) {
                residual=std::max(residual,std::max(shape.lower[i]-point[i],point[i]-shape.upper[i]));
                membership.contained=membership.contained && point[i]>=shape.lower[i]-result.tolerance &&
                    point[i]<=shape.upper[i]+result.tolerance;
            }
            membership.reconstruction_residual=std::max(0.0,residual);
        } else if constexpr(std::is_same_v<T,FiniteGraphParallelotopeShape>) {
            membership.method="frame-coordinate-solve-and-interval-check";
            const auto n=point.size();
            if(shape.frame.rows!=n || shape.frame.cols!=n || shape.frame.values.size()!=n*n) {
                membership.supported=false;membership.method="parallelotope-frame-dimension-unsupported";return membership;
            }
            std::vector<double> augmented(n*(n+1));
            for(std::size_t row=0;row<n;++row) {
                for(std::size_t col=0;col<n;++col)augmented[row*(n+1)+col]=shape.frame.values[row*n+col];
                augmented[row*(n+1)+n]=point[row];
            }
            double frame_scale=0.0;
            for(const auto value:shape.frame.values)frame_scale=std::max(frame_scale,std::abs(value));
            const auto pivot_tolerance=std::max(64.0*std::numeric_limits<double>::epsilon()*frame_scale,
                64.0*std::numeric_limits<double>::denorm_min());
            for(std::size_t col=0;col<n;++col) {
                std::size_t pivot=col;
                for(std::size_t row=col+1;row<n;++row)
                    if(std::abs(augmented[row*(n+1)+col])>std::abs(augmented[pivot*(n+1)+col]))pivot=row;
                if(std::abs(augmented[pivot*(n+1)+col])<=pivot_tolerance) {
                    membership.supported=false;membership.method="singular-parallelotope-frame";return membership;
                }
                for(std::size_t j=col;j<=n;++j)std::swap(augmented[col*(n+1)+j],augmented[pivot*(n+1)+j]);
                const auto divisor=augmented[col*(n+1)+col];
                for(std::size_t j=col;j<=n;++j)augmented[col*(n+1)+j]/=divisor;
                for(std::size_t row=0;row<n;++row)if(row!=col) {
                    const auto factor=augmented[row*(n+1)+col];
                    for(std::size_t j=col;j<=n;++j)augmented[row*(n+1)+j]-=factor*augmented[col*(n+1)+j];
                }
            }
            membership.witness_coordinates.resize(n);
            for(std::size_t i=0;i<n;++i)membership.witness_coordinates[i]=augmented[i*(n+1)+n];
            membership.contained=shape.lower.size()==n && shape.upper.size()==n;
            if(!membership.contained) {
                membership.supported=false;membership.method="parallelotope-interval-dimension-unsupported";return membership;
            }
            for(std::size_t i=0;i<n;++i)
                if(membership.witness_coordinates[i]<shape.lower[i]-result.tolerance ||
                   membership.witness_coordinates[i]>shape.upper[i]+result.tolerance)
                    membership.contained=false;
            double residual2=0.0;
            for(std::size_t row=0;row<n;++row) {
                double reconstructed=0.0;
                for(std::size_t col=0;col<n;++col)reconstructed+=shape.frame.values[row*n+col]*membership.witness_coordinates[col];
                const auto residual=reconstructed-point[row];residual2+=residual*residual;
            }
            membership.reconstruction_residual=std::sqrt(residual2);
            membership.contained=membership.contained && membership.reconstruction_residual<=result.tolerance;
        } else if constexpr(std::is_same_v<T,FiniteGraphEllipsoidShape>) {
            membership.method="normalized-ellipsoid-quadratic-metric";
            if(shape.center.size()!=point.size() || shape.radii.size()!=point.size()) {
                membership.supported=false;membership.method="ellipsoid-dimension-unsupported";return membership;
            }
            double metric=0.0;
            membership.witness_coordinates.resize(point.size());
            for(std::size_t i=0;i<point.size();++i) {
                if(shape.radii[i]==0.0) {
                    if(std::abs(point[i]-shape.center[i])>result.tolerance) { metric=std::numeric_limits<double>::infinity();break; }
                    membership.witness_coordinates[i]=0.0;
                } else {
                    const auto coordinate=(point[i]-shape.center[i])/shape.radii[i];
                    membership.witness_coordinates[i]=coordinate;metric+=coordinate*coordinate;
                }
            }
            membership.reconstruction_residual=std::max(0.0,std::sqrt(metric)-1.0);
            membership.contained=metric<=1.0+64.0*std::numeric_limits<double>::epsilon()*
                static_cast<double>(std::max<std::size_t>(1,point.size()));
        } else {
            membership.method="bounded-axis-aligned-generator-coefficients";
            const auto n=point.size(),g=shape.generators.cols;
            membership.witness_coordinates.assign(g,0.0);
            double generator_scale=0.0;
            for(const auto value:shape.generators.values)generator_scale=std::max(generator_scale,std::abs(value));
            const auto generator_tolerance=std::max(64.0*std::numeric_limits<double>::epsilon()*generator_scale,
                64.0*std::numeric_limits<double>::denorm_min());
            if(g==0) {
                double residual2=0.0;
                for(std::size_t i=0;i<n;++i) {
                    const auto residual=point[i]-shape.center[i];
                    residual2+=residual*residual;
                }
                membership.reconstruction_residual=std::sqrt(residual2);
                membership.contained=membership.reconstruction_residual<=result.tolerance;
                return membership;
            }
            if(g==1) {
                double dot=0.0,norm2=0.0;
                for(std::size_t i=0;i<n;++i) {
                    const auto generator=shape.generators.values[i];
                    dot+=(point[i]-shape.center[i])*generator;norm2+=generator*generator;
                }
                if(norm2==0.0) {
                    membership.supported=false;membership.method="degenerate-single-generator-zonotope";return membership;
                }
                const auto alpha=dot/norm2;membership.witness_coordinates[0]=alpha;
                double residual2=0.0;
                for(std::size_t i=0;i<n;++i) {
                    const auto residual=point[i]-shape.center[i]-alpha*shape.generators.values[i];
                    residual2+=residual*residual;
                }
                membership.reconstruction_residual=std::sqrt(residual2);
                membership.contained=std::abs(alpha)<=1.0+64.0*std::numeric_limits<double>::epsilon()*std::max(1.0,std::abs(alpha)) &&
                    membership.reconstruction_residual<=result.tolerance;
                return membership;
            }
            std::vector<std::vector<std::size_t>> columns_by_axis(n);
            for(std::size_t col=0;col<g;++col) {
                std::optional<std::size_t> axis;
                for(std::size_t row=0;row<n;++row) {
                    const auto value=shape.generators.values[row*g+col];
                    if(std::abs(value)>generator_tolerance) {
                        if(axis) {
                            membership.supported=false;
                            membership.method="non-axis-aligned-multiple-zonotope-generators-inconclusive";
                            return membership;
                        }
                        axis=row;
                    }
                }
                if(axis)columns_by_axis[*axis].push_back(col);
            }
            bool within_capacity=true;
            Vector delta(n),capacity(n,0.0);
            for(std::size_t row=0;row<n;++row) {
                delta[row]=point[row]-shape.center[row];
                for(const auto col:columns_by_axis[row])capacity[row]+=std::abs(shape.generators.values[row*g+col]);
                if(!std::isfinite(delta[row]) || !std::isfinite(capacity[row])) {
                    membership.supported=false;
                    membership.method="axis-aligned-zonotope-capacity-overflow-inconclusive";
                    return membership;
                }
                if(std::abs(delta[row])>capacity[row]+result.tolerance)within_capacity=false;
            }
            if(!within_capacity) {
                membership.contained=false;
                membership.method="axis-aligned-generator-capacity-exclusion";
                double distance2=0.0;
                for(std::size_t row=0;row<n;++row) {
                    const auto excess=std::max(0.0,std::abs(delta[row])-capacity[row]);
                    distance2+=excess*excess;
                }
                membership.reconstruction_residual=std::sqrt(distance2);
                return membership;
            }
            for(std::size_t row=0;row<n;++row) {
                double remaining=delta[row];
                for(const auto col:columns_by_axis[row]) {
                    const auto generator=shape.generators.values[row*g+col];
                    const auto magnitude=std::min(1.0,std::abs(remaining)/std::abs(generator));
                    const auto coefficient=(std::signbit(remaining)!=std::signbit(generator))?-magnitude:magnitude;
                    membership.witness_coordinates[col]=coefficient;
                    remaining-=generator*coefficient;
                }
                if(std::abs(remaining)>result.tolerance) {
                    membership.supported=false;
                    membership.method="axis-aligned-zonotope-witness-rounding-inconclusive";
                    return membership;
                }
            }
            double residual2=0.0;
            for(std::size_t row=0;row<n;++row) {
                double reconstructed=shape.center[row];
                for(std::size_t col=0;col<g;++col)
                    reconstructed+=shape.generators.values[row*g+col]*membership.witness_coordinates[col];
                const auto residual=point[row]-reconstructed;
                residual2+=residual*residual;
            }
            for(std::size_t col=0;col<g;++col)
                if(std::abs(membership.witness_coordinates[col])>1.0+64.0*std::numeric_limits<double>::epsilon()*
                    std::max(1.0,std::abs(membership.witness_coordinates[col]))) {
                    membership.supported=false;
                    membership.contained=false;
                    membership.method="axis-aligned-zonotope-coefficient-overflow-inconclusive";
                    return membership;
                }
            membership.reconstruction_residual=std::sqrt(residual2);
            membership.contained=membership.reconstruction_residual<=result.tolerance;
        }
        return membership;
    },cloud.selected_outer_shape);
    if(membership.supported &&
       (!std::isfinite(membership.reconstruction_residual) || !std::isfinite(membership.tolerance) ||
        !finite(std::span<const double>(membership.witness_coordinates)))) {
        membership.supported=false;
        membership.contained=false;
        membership.method="non-finite-membership-arithmetic-inconclusive";
    }
    return membership;
}

FiniteActionGraphOutcome finite_action_stage_layered_graph(const FiniteActionNominalRequest& request,
        FiniteActionGraphLimits limits,
        const registry::PreparedProvider<registry::GeometryPort>& projection_provider,
        const ExecutionContext& context) {
    return finite_action_stage_layered_graph_impl(request, limits, projection_provider, nullptr, context,{});
}

FiniteActionGraphOutcome finite_action_stage_layered_graph(const FiniteActionNominalRequest& request,
        FiniteActionGraphLimits limits,
        const registry::PreparedProvider<registry::GeometryPort>& projection_provider,
        const registry::PreparedProvider<registry::GeometryPort>& reachable_set_provider,
        const ExecutionContext& context, FiniteGraphGeometryObserver observer) {
    return finite_action_stage_layered_graph_impl(request, limits, projection_provider, &reachable_set_provider, context,observer);
}

} // namespace csl::optimization
