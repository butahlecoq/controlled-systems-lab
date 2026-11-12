#include <csl/model/linear_system.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/basis_reuse_reducer.hpp>
#include <csl/geometry/composition_catalogue.hpp>
#include <csl/geometry/source_index_hull.hpp>
#include <csl/optimization/phase_one.hpp>
#if CSL_NATIVE_HAS_HIGHS
#include <csl/adapters/lp/highs.hpp>
#if CSL_NATIVE_HAS_QHULL
#include <csl/adapters/polyhedral/qhull.hpp>
#endif
#endif
#include <csl/optimization/finite_action_nominal.hpp>
#include <csl/optimization/finite_action_graph.hpp>
#include <csl/optimization/objectives.hpp>
#include <csl/optimization/history_cost.hpp>
#include <csl/reachability/feedback_geometry.hpp>
#include <csl/geometry/polyhedral_intersection.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <csl/problem/resolved_problem.hpp>
#if CSL_NATIVE_HAS_HIGHS
#include <csl/adapters/convex/highs.hpp>
#endif
#include <csl/registry/registry.hpp>
#include <csl/sets/data.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <variant>

namespace {
using Json = nlohmann::json;
using namespace csl;

#ifndef CSL_NATIVE_HAS_HIGHS
#define CSL_NATIVE_HAS_HIGHS 0
#endif
#ifndef CSL_NATIVE_HAS_QHULL
#define CSL_NATIVE_HAS_QHULL 0
#endif
#ifndef CSL_NATIVE_BUILD_TYPE
#define CSL_NATIVE_BUILD_TYPE "unknown"
#endif

Json native_build_backend_profile() {
    return {{"build_type", CSL_NATIVE_BUILD_TYPE},
        {"CSL_ENABLE_HIGHS", CSL_NATIVE_HAS_HIGHS != 0},
        {"CSL_ENABLE_QHULL", CSL_NATIVE_HAS_QHULL != 0}};
}

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

struct TraceJsonVisitor {
    Json& stages;
    std::string& representation;
    std::string& relation;

    void operator()(const reachability::FixedPlanReachable& trace) const {
        representation = "exact-polytope";
        relation = "equivalent";
        for(const auto& set : trace.stages) stages.push_back(set_json(set));
    }

    void operator()(const reachability::FinitePlanBoxTrace& trace) const {
        representation = "box";
        relation = "outer";
        for(const auto& stage : trace.stages)
            stages.push_back({{"lower", stage.lower}, {"upper", stage.upper}});
    }

    void operator()(const reachability::FinitePlanZonotopeTrace& trace) const {
        representation = "zonotope";
        relation = "outer";
        for(const auto& stage : trace.stages)
            stages.push_back({{"center", stage.center},
                {"generators", matrix_json(stage.generators.rows, stage.generators.cols,
                    [&](std::size_t i, std::size_t j) {
                        return stage.generators.values[i * stage.generators.cols + j];
                    })}});
    }

    void operator()(const reachability::FinitePlanParallelotopeTrace& trace) const {
        representation = "parallelotope";
        relation = "outer";
        for(const auto& stage : trace.stages)
            stages.push_back({{"lower", stage.lower}, {"upper", stage.upper}});
    }

    void operator()(const reachability::FinitePlanEllipsoidTrace& trace) const {
        representation = "ellipsoid";
        relation = "outer";
        for(const auto& stage : trace.stages)
            stages.push_back({{"center", stage.center}, {"radii", stage.radii}});
    }
};

sets::SetData safe_box(const Json& bounds, std::size_t dimension, const std::string& id) {
    std::size_t count = 0;
    for(const auto& bound : bounds) if(!bound.is_null()) count += 2;
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

TerminalObjective terminal_source(const Json& spec, std::size_t state_dimension) {
    if(spec.at("kind") == "quadratic") {
        const auto q = matrix(spec.at("Q"));
        const auto linear = vector(spec.at("linear"));
        const auto offset = spec.at("offset").get<double>();
        if(q.rows != state_dimension || q.cols != state_dimension || linear.size() != state_dimension)
            throw std::runtime_error("terminal quadratic dimension mismatch");
        return QuadraticTerminal{q, linear, offset};
    }
    const auto map = matrix(spec.at("map"));
    const auto target = vector(spec.at("target"));
    const auto weights = vector(spec.at("weights"));
    if(map.cols != state_dimension || map.rows != target.size())
        throw std::runtime_error("terminal norm dimension mismatch");
    return ResidualNormTerminal{map, target, weights};
}

optimization::Objective terminal_objective(const Json& spec, std::size_t state_dimension) {
    return take(optimization::snapshot(terminal_source(spec, state_dimension)), "terminal-objective");
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
    std::visit(TraceJsonVisitor{stages, representation, relation}, selected.selected_trace);
    return {{"role", "fixed-plan-trajectory-enclosure"}, {"representation", representation},
        {"relation", relation}, {"assurance", "numerical"}, {"stages", std::move(stages)}};
}

Json query_failure(const Json& input, const std::string& status, const std::string& reason) {
    Json result{{"status", status}, {"reason", reason}, {"invocations", Json::array()}};
    for(const auto* key : {"task_id", "task_sha256", "action_profile_id"})
        if(input.is_object() && input.contains(key)) result[key] = input.at(key);
    if(input.is_object() && input.contains("controller_id"))
        result["policy_id"] = input.at("controller_id").get<std::string>() + "/query/1";
    return result;
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

template<class Port>
registry::PreparedProvider<Port> prepare_provider(registry::Registration<Port> registration,
        registry::Requirements requirements) {
    const registry::Method method{registration.identity.id, registration.identity.version};
    registry::Registry<Port> providers;
    if(const auto rejected=providers.add(std::move(registration)))
        throw std::runtime_error(rejected->diagnostics.empty() ? "provider registration failed" : rejected->diagnostics.front().explanation);
    auto prepared=registry::prepare_provider(registry::select_provider(providers,method,requirements));
    if(!std::holds_alternative<registry::PreparedProvider<Port>>(prepared))
        throw std::runtime_error("selected provider failed preparation");
    return std::get<registry::PreparedProvider<Port>>(std::move(prepared));
}

struct MethodSelection { std::string id; std::string version; };

MethodSelection method_selection(const Json& value, const char* field) {
    if(!value.is_object() || !value.contains("id") || !value.contains("version"))
        throw std::runtime_error(std::string(field)+" must explicitly provide id and version");
    return {value.at("id").get<std::string>(),value.at("version").get<std::string>()};
}

template<class Port>
registry::PreparedProvider<Port> select_registered_provider(registry::Registry<Port>& providers,
        const MethodSelection& method, registry::Requirements requirements, const char* field) {
    auto prepared=registry::prepare_provider(registry::select_provider(providers,
        {{method.id},method.version},std::move(requirements)));
    if(const auto* rejected=std::get_if<registry::Rejection>(&prepared))
        throw std::runtime_error(std::string(field)+" selection rejected: "+
            (rejected->diagnostics.empty()?"no diagnostic":rejected->diagnostics.front().explanation));
    return std::get<registry::PreparedProvider<Port>>(std::move(prepared));
}

registry::Registration<registry::HullReducerPort> hull_registration(
        const MethodSelection& method, const registry::Registration<registry::LPPort>& lp_registration) {
    if(method.id=="csl.hull.lp-membership") return geometry::make_lp_hull_reducer_registration();
    if(method.id=="csl.hull.phase-one-basis-bulk")
        return geometry::make_basis_reuse_hull_reducer_registration(lp_registration);
    if(method.id=="csl.hull.ordered-membership") return geometry::make_ordered_hull_reducer_registration();
    if(method.id=="csl.hull.itis17.a43-certified-basis-reuse")
        return geometry::make_itis17_a43_hull_reducer_registration();
    if(method.id=="csl.hull.itis17.a43-artificial-basis")
        return geometry::make_itis17_a43_paper_hull_reducer_registration(geometry::A43PivotRule::phase_one_order);
    if(method.id=="csl.hull.itis17.a43-largest-norm-tie")
        return geometry::make_itis17_a43_paper_hull_reducer_registration(geometry::A43PivotRule::largest_norm_tie);
    if(method.id=="csl.hull.itis17.a44-incremental-lp")
        return geometry::make_itis17_a44_hull_reducer_registration();
    if(method.id=="csl.hull.itis17.a44-paper-farthest-incremental-lp")
        return geometry::make_itis17_a44_paper_hull_reducer_registration();
    if(method.id=="csl.hull.grouped-membership") return geometry::make_grouped_hull_reducer_registration();
    if(method.id=="csl.hull.recursive-split-merge")
        return geometry::make_recursive_hull_reducer_registration(lp_registration);
    throw std::runtime_error("Unsupported or unimplemented HullReducerPort id: "+method.id);
}

registry::PreparedProvider<registry::GeometryPort> affine_sum_provider(const Json& input) {
    const MethodSelection reachable=method_selection(input.at("reachable_set_method"),"reachable_set_method");
    if(reachable.version!="1.0.0")
        throw std::runtime_error("reachable_set_method version is unavailable: "+reachable.id+"@"+reachable.version);
    const MethodSelection hull_method=method_selection(input.at("hull_provider"),"hull_provider");
    const auto& converter_request=input.at("conversion_provider");
    if(!converter_request.is_string() || converter_request.get<std::string>()!="not_used")
        throw std::runtime_error("conversion_provider must explicitly be not_used for the V-only native graph operands");
    registry::Requirements requirements;
    requirements.output.representation={"csl.polyhedron.v"};
    requirements.output.relation=SetRelation::equivalent;
    requirements.output.assurance=Assurance::numerical;
    if(reachable.id=="csl.geometry.affine-sum.source-index") {
        if(input.at("vertex_lp_provider")!="not_used")
            throw std::runtime_error("vertex_lp_provider must be explicitly not_used for a source-index method");
        const auto budget_json=input.at("checker_budget");
        geometry::HullCheckBudget budget{
            std::chrono::milliseconds{budget_json.at("wall_ms").get<std::int64_t>()},
            budget_json.at("max_points").get<std::size_t>()};
        auto catalogue=geometry::make_source_index_hull_catalogue();
        auto selected=select_registered_provider(catalogue,hull_method,{},"SourceIndexHullPort");
        auto registration=geometry::make_affine_sum_registration(
            geometry::SourceIndexAffineSumDependencies{std::move(selected),{},budget});
        return prepare_provider(std::move(registration),requirements);
    }
    if(reachable.id!="csl.geometry.affine-sum")
        throw std::runtime_error("Unsupported or unimplemented reachable-set method: "+reachable.id);

    const MethodSelection lp_method=method_selection(input.at("vertex_lp_provider"),"vertex_lp_provider");
    registry::Registration<registry::LPPort> lp_registration;
    if(lp_method.id=="phase-one-bland") {
        auto lp_result=optimization::phase_one::make_registration();
        if(!std::holds_alternative<registry::Registration<registry::LPPort>>(lp_result))
            throw std::runtime_error("Phase-I LP registration unavailable");
        lp_registration=std::get<registry::Registration<registry::LPPort>>(std::move(lp_result));
    } else if(lp_method.id=="phase-one-priority-tie") {
        optimization::phase_one::Options options;
        options.structural_entering_priorities={0,1,2,3,4};
        auto lp_result=optimization::phase_one::make_registration(std::move(options));
        if(!std::holds_alternative<registry::Registration<registry::LPPort>>(lp_result))
            throw std::runtime_error("Phase-I priority-tie LP registration unavailable");
        lp_registration=std::get<registry::Registration<registry::LPPort>>(std::move(lp_result));
    } else if(lp_method.id=="csl.lp.highs") {
#if CSL_NATIVE_HAS_HIGHS
        auto lp_result=adapters::lp::make_highs_registration();
        if(!std::holds_alternative<registry::Registration<registry::LPPort>>(lp_result)) {
            std::string detail;
            for(const auto& diagnostic:std::get<Diagnostics>(lp_result)) {
                if(!detail.empty()) detail += "; ";
                detail += diagnostic.field+": "+diagnostic.explanation;
            }
            throw std::runtime_error("Requested HiGHS LP registration unavailable"+
                (detail.empty()?std::string{}:": "+detail));
        }
        lp_registration=std::get<registry::Registration<registry::LPPort>>(std::move(lp_result));
#else
        throw std::runtime_error("Requested vertex LP provider csl.lp.highs is unavailable because CSL_ENABLE_HIGHS=OFF; no replacement LP provider was selected.");
#endif
    } else {
        throw std::runtime_error("Unsupported or unimplemented vertex LP provider: "+lp_method.id+"@"+lp_method.version);
    }
    if(lp_registration.identity.id.value!=lp_method.id || lp_registration.identity.version!=lp_method.version)
        throw std::runtime_error("Requested vertex LP provider is not registered in this native build: "+lp_method.id+"@"+lp_method.version);
    registry::Registry<registry::LPPort> lp_catalogue;
    if(const auto rejection=lp_catalogue.add(lp_registration))
        throw std::runtime_error("built-in LP registration failed: "+rejection->diagnostics.front().explanation);
    registry::Requirements lp_requirements;
    lp_requirements.output.representation={"csl.program-result.v1"};
    auto lp=select_registered_provider(lp_catalogue,lp_method,lp_requirements,"vertex LP provider");

    registry::Registry<registry::HullReducerPort> hull_catalogue;
    for(auto registration : {
            hull_registration(hull_method,lp_registration)}) {
        if(const auto rejection=hull_catalogue.add(std::move(registration)))
            throw std::runtime_error("HullReducerPort registration rejected: "+rejection->diagnostics.front().explanation);
    }
    auto hull=select_registered_provider(hull_catalogue,hull_method,{},"HullReducerPort");
    geometry::AffineSumDependencies dependencies{std::move(hull),std::move(lp),std::nullopt};
    auto registration=geometry::make_affine_sum_registration(std::move(dependencies));
    return prepare_provider(std::move(registration),requirements);
}

Json geometry_invocation_json(const optimization::FiniteGraphGeometryInvocation& call) {
    const auto relation=call.relation ? Json(*call.relation==SetRelation::equivalent?"equivalent":
        *call.relation==SetRelation::outer?"outer":*call.relation==SetRelation::inner?"inner":"heuristic") : Json(nullptr);
    return {{"absolute_stage",call.absolute_stage},{"parent_node_id",call.parent_node_id},
        {"request_id",call.request_id},{"ideal_output_id",call.ideal_output_id},
        {"input_ids",call.input_ids},{"operation",call.operation},
        {"requested_method_id",call.requested_method_id},{"actual_method_id",call.actual_method_id},
        {"actual_method_version",call.actual_method_version},{"outcome",call.outcome},
        {"relation",relation},{"elapsed_ns",call.elapsed.count()},
        {"evidence_assumptions",call.evidence_assumptions},{"diagnostics",call.diagnostics}};
}

std::string backward_status(optimization::FiniteGraphBackwardStatus status) {
    using Status = optimization::FiniteGraphBackwardStatus;
    switch(status) {
        case Status::root_node: return "root-node";
        case Status::pending: return "pending-backward-pass";
        case Status::terminal_admissible: return "terminal-node-admissible";
        case Status::terminal_outside_stage_set: return "terminal-node-outside-stage-set";
        case Status::skipped_suffix_nonviable: return "skipped-suffix-nonviable";
        case Status::predecessor_membership_false: return "numerical-predecessor-membership-false";
        case Status::discrete_transition_witness_failed: return "discrete-transition-witness-failed";
        case Status::parent_stage_intersection_empty: return "parent-stage-intersection-empty";
        case Status::representation_filter_rejected: return "representation-filter-rejected";
        case Status::eligible_numerical_predecessor_and_discrete_edge:
            return "eligible-numerical-predecessor-and-discrete-edge";
    }
    return "unknown";
}

Json graph_response(const Json& input, const optimization::FiniteActionNominalRequest& request,
                    std::size_t beam_width, std::size_t max_nodes,
                    optimization::NominalRepresentation representation,
                    std::size_t max_generators) {
    const auto reachable_set_method = input.at("reachable_set_method").at("id").get<std::string>();
    const auto control_optimizer=method_selection(input.at("control_optimizer"),"control_optimizer");
    if(control_optimizer.id!="csl.optimization.finite-action-stage-layered-graph" ||
            control_optimizer.version!="1.0.0")
        return query_failure(input,"unavailable","The explicitly requested control optimizer is not registered in this executable.");
    auto registration = geometry::polyhedral::make_projection_registration();
    registry::Registry<registry::GeometryPort> providers;
    if(const auto error = providers.add(registration))
        return query_failure(input,"unavailable", error->diagnostics.empty() ? "projection registration rejected" : error->diagnostics.front().explanation);
    registry::Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.h"};
    requirements.output.relation = SetRelation::equivalent;
    auto prepared = registry::prepare_provider(registry::select_provider(providers,
        {registration.identity.id, registration.identity.version}, requirements));
    if(!std::holds_alternative<registry::PreparedProvider<registry::GeometryPort>>(prepared))
        return query_failure(input,"unavailable","Exact-H projection provider failed preparation in this executable.");
    auto provider = std::get<registry::PreparedProvider<registry::GeometryPort>>(std::move(prepared));
    const auto reachable_provider = affine_sum_provider(input);
    Json geometry_calls=Json::array();
    const auto geometry_selection=Json{{"reachable_set_method",input.at("reachable_set_method")},
        {"hull_provider",input.at("hull_provider")},{"vertex_lp_provider",input.at("vertex_lp_provider")},
        {"conversion_provider",input.at("conversion_provider")},{"checker_budget",input.at("checker_budget")},
        {"control_optimizer",input.at("control_optimizer")},
        {"terminal_optimizer_provider","not_used"},
        {"terminal_value_evaluation","direct authored objective evaluation"}};
    const auto outcome = optimization::finite_action_stage_layered_graph(request,
        {beam_width, max_nodes, representation==optimization::NominalRepresentation::exact_polytope ?
            std::nullopt : std::optional{representation},max_generators,
            representation==optimization::NominalRepresentation::exact_polytope ?
                std::nullopt : std::optional{representation}}, provider, reachable_provider, {},
        [&geometry_calls](const auto& call) { geometry_calls.push_back(geometry_invocation_json(call)); });
    if(const auto* error = std::get_if<Unsupported>(&outcome)) {
        auto response = query_failure(input,"unsupported",
            error->diagnostics.empty() ? "unsupported graph request" : error->diagnostics.front().explanation);
        response["mathematical_support"] = "not_evaluated";
        response["geometry_selection"] = geometry_selection;
        response["geometry_invocations"] = geometry_calls;
        return response;
    }
    if(const auto* stopped = std::get_if<OperationStopped>(&outcome)) {
        auto response = query_failure(input,"failed",stopped->diagnostics);
        response["mathematical_support"] = "not_evaluated";
        response["geometry_selection"] = geometry_selection;
        response["geometry_invocations"] = geometry_calls;
        return response;
    }
    const auto& graph = std::get<optimization::FiniteActionGraphResult>(outcome);
    const auto& provenance = provider.provenance();
    const auto provider_id = provenance.actual ? provenance.actual->id.value + "@" + provenance.actual->version : "unresolved-provider";
    const std::array<std::string,5> representation_names{"exact-polytope","box","zonotope","parallelotope","ellipsoid"};
    const auto representation_index=static_cast<std::size_t>(representation);
    Json layers = Json::array(), nodes = Json::array(), edges = Json::array(), action_clouds=Json::array();
    for(const auto& cloud:graph.action_cloud_envelopes) {
        Json witnesses=Json::array();
        for(const auto& witness:cloud.action_witnesses)
            witnesses.push_back({{"action_index",witness.action_index},{"child_state",witness.child_state},
                {"accepted_by_selected_shape_numerical_membership",witness.accepted_by_selected_shape_numerical_membership},
                {"contained_in_coordinate_outer_box",witness.contained_in_coordinate_outer_box},
                {"membership_method",witness.membership_method},{"membership_coordinates",witness.membership_coordinates},
                {"membership_residual",witness.membership_residual},{"membership_tolerance",witness.membership_tolerance},
                {"membership_tolerance_scale",witness.membership_tolerance_scale},
                {"membership_tolerance_rule",witness.membership_tolerance_rule},
                {"containment_basis",witness.containment_basis}});
        const auto selected_shape=std::visit([&](const auto& shape)->Json {
            using T=std::decay_t<decltype(shape)>;
            if constexpr(std::is_same_v<T,optimization::FiniteGraphBoxShape>)
                return {{"representation","box"},{"lower",shape.lower},{"upper",shape.upper}};
            else if constexpr(std::is_same_v<T,optimization::FiniteGraphZonotopeShape>)
                return {{"representation","zonotope"},{"center",shape.center},
                    {"generators",matrix_json(shape.generators.rows,shape.generators.cols,
                        [&](std::size_t i,std::size_t j){return shape.generators.values[i*shape.generators.cols+j];})}};
            else if constexpr(std::is_same_v<T,optimization::FiniteGraphParallelotopeShape>)
                return {{"representation","parallelotope"},
                    {"frame",matrix_json(shape.frame.rows,shape.frame.cols,
                        [&](std::size_t i,std::size_t j){return shape.frame.values[i*shape.frame.cols+j];})},
                    {"lower",shape.lower},{"upper",shape.upper}};
            else return {{"representation","ellipsoid"},{"center",shape.center},{"radii",shape.radii}};
        },cloud.selected_outer_shape);
        action_clouds.push_back({{"stage",cloud.stage},{"parent_stage",cloud.stage},{"output_stage",cloud.output_stage},
            {"parent_time",cloud.parent_time},{"output_time",cloud.output_time},{"parent_node_id",cloud.parent_node},
            {"parent_state",cloud.parent_state},{"representation",representation_names.at(static_cast<std::size_t>(cloud.representation))},
            {"module_id",cloud.module_id},{"auxiliary_request_id",cloud.auxiliary_request_id},
            {"lifting_semantics",cloud.lifting_semantics},
            {"source_task_external_disturbance_unchanged",true},
            {"source_task_action_profile_unchanged",true},
            {"auxiliary_model",{{"A",matrix_json(cloud.auxiliary_A.rows,cloud.auxiliary_A.cols,
                    [&](std::size_t i,std::size_t j){return cloud.auxiliary_A.values[i*cloud.auxiliary_A.cols+j];})},
                {"B",matrix_json(cloud.auxiliary_B.rows,cloud.auxiliary_B.cols,
                    [&](std::size_t i,std::size_t j){return cloud.auxiliary_B.values[i*cloud.auxiliary_B.cols+j];})},
                {"E",matrix_json(cloud.auxiliary_E.rows,cloud.auxiliary_E.cols,
                    [&](std::size_t i,std::size_t j){return cloud.auxiliary_E.values[i*cloud.auxiliary_E.cols+j];})},
                {"offset",cloud.auxiliary_offset},{"fixed_auxiliary_control",cloud.auxiliary_control},
                {"source_external_matrix_E",matrix_json(cloud.original_E.rows,cloud.original_E.cols,
                    [&](std::size_t i,std::size_t j){return cloud.original_E.values[i*cloud.original_E.cols+j];})},
                {"source_nominal_external_input",cloud.source_nominal_external},
                {"lifted_Ew_contribution",cloud.lifted_external_contribution},
                {"auxiliary_safe_sets","universal construction constraints"},
                {"auxiliary_disturbance_vertices","authored B*u action images listed below"}}},
            {"authored_action_effect_vertices",cloud.authored_action_effect_vertices},
            {"selected_outer_shape",selected_shape},
            {"outer_coordinate_bounds",{{"lower",cloud.outer_lower},{"upper",cloud.outer_upper}}},
            {"outer_inside_authored_stage_set",cloud.outer_inside_authored_stage_set ? Json(*cloud.outer_inside_authored_stage_set):Json(nullptr)},
            {"action_child_witnesses",witnesses},{"relation","outer"},{"assurance","numerical"}});
    }
    for(const auto& stat : graph.layer_statistics)
        layers.push_back({{"stage", stat.stage}, {"generated", stat.generated}, {"retained", stat.retained},
            {"pruned", stat.pruned}, {"infeasible", stat.stage_inadmissible},
            {"representation_filter_rejected",stat.representation_filter_rejected}});
    for(std::size_t id = 0; id < graph.nodes.size(); ++id) {
        const auto& node = graph.nodes[id];
        nodes.push_back({{"node_id", id}, {"absolute_stage", request.absolute_stage_offset + node.stage},
            {"state", node.state}, {"parent_node_id", node.parent_node ? Json(*node.parent_node) : Json(nullptr)},
            {"action_index", node.action_index ? Json(*node.action_index) : Json(nullptr)},
            {"edge_running_cost", node.edge_running_cost}, {"heuristic_score", node.heuristic_score},
            {"state_admissible", node.state_admissible}, {"stage_set_intersection_nonempty", node.stage_intersection_nonempty},
            {"reachable_envelope_contains", node.reachable_envelope_contains ? Json(*node.reachable_envelope_contains) : Json(nullptr)},
            {"representation_filter_passed",node.representation_filter_passed?Json(*node.representation_filter_passed):Json(nullptr)},
            {"representation_filter_outcome",node.representation_filter_outcome},
            {"representation_edge_outer_enclosure",node.representation_outer_lower.empty()?Json(nullptr):Json{{"lower",node.representation_outer_lower},
                {"upper",node.representation_outer_upper},{"representation",representation_names.at(representation_index)},
                {"coordinate_outer_box",true},{"relation","outer"},{"assurance","numerical"}}},
            {"backward_viable", node.backward_viable},
            {"predecessor_contains_parent", node.predecessor_contains_parent ? Json(*node.predecessor_contains_parent) : Json(nullptr)},
            {"discrete_transition_witness", node.discrete_transition_witness ? Json(*node.discrete_transition_witness) : Json(nullptr)},
            {"backward_value", node.backward_value ? Json(*node.backward_value) : Json(nullptr)},
            {"action_lineage", node.action_lineage}, {"backward_edge_status", backward_status(node.backward_status)}});
    }
    for(std::size_t stage = 1; stage < graph.layers.size(); ++stage)
        for(const auto id : graph.layers[stage]) {
            const auto& node = graph.nodes[id];
            edges.push_back({{"parent_node_id", *node.parent_node}, {"child_node_id", id},
                {"absolute_stage", request.absolute_stage_offset + stage - 1}, {"action_index", *node.action_index},
                {"action", request.actions.catalogue[*node.action_index]}, {"child_state", node.state},
                {"action_lineage", node.action_lineage}, {"backward_viable", node.backward_viable},
                {"predecessor_contains_parent", node.predecessor_contains_parent ? Json(*node.predecessor_contains_parent) : Json(nullptr)},
                {"discrete_transition_witness", node.discrete_transition_witness ? Json(*node.discrete_transition_witness) : Json(nullptr)},
                {"representation_filter_passed",node.representation_filter_passed?Json(*node.representation_filter_passed):Json(nullptr)},
                {"representation_filter_outcome",node.representation_filter_outcome},
                {"representation_edge_outer_enclosure",node.representation_outer_lower.empty()?Json(nullptr):Json{{"lower",node.representation_outer_lower},
                    {"upper",node.representation_outer_upper},{"representation",representation_names.at(representation_index)},
                    {"coordinate_outer_box",true},{"relation","outer"},{"assurance","numerical"}}},
                {"backward_edge_status", backward_status(node.backward_status)}});
        }
    Json invocations = Json::array({{{"module_id", "csl::optimization::finite_action_stage_layered_graph"},
        {"operation", "full-authored-horizon stage-layered finite-action graph and backward Bellman selection"},
        {"selected_method_id",control_optimizer.id},{"selected_method_version",control_optimizer.version},
        {"provider", "public-function"}, {"profile_id", input.at("controller_id")},
        {"terminal_optimizer_provider","not_used"},
        {"terminal_value_evaluation","direct authored objective evaluation"},
        {"outcome", graph.has_viable_path ? "selected" : "no-viable-retained-path"},
        {"generated_edges", std::accumulate(graph.layer_statistics.begin(), graph.layer_statistics.end(), std::size_t{0},
            [](std::size_t count, const auto& row) { return count + row.generated; })},
        {"retained_nodes", graph.nodes.size()}}});
    invocations.push_back({{"module_id", "csl::reachability::prepare_nominal_predecessor"},
        {"operation", "numerical H predecessor membership followed by authored discrete transition witness"},
        {"provider", provider_id}, {"profile_id", input.at("controller_id")},
        {"calls", graph.predecessor_calls}, {"assurance", "numerical, support unestablished"}});
    invocations.push_back({{"module_id", "csl::geometry::polyhedral::intersect_h"},
        {"operation", "intersect each generated point with its authored stage H constraints"},
        {"provider", "public-function"}, {"profile_id", input.at("controller_id")},
        {"calls", graph.stage_intersection_calls}});
    const auto reachable_provenance = reachable_provider.provenance();
    const auto reachable_provider_id = reachable_provenance.actual ?
        reachable_provenance.actual->id.value + "@" + reachable_provenance.actual->version : "unresolved-provider";
    invocations.push_back({{"module_id", "csl::geometry::affine-image"},
        {"operation", "registered affine image of each retained observed-state parent"},
        {"provider", reachable_provider_id}, {"selected_method_id", reachable_set_method}, {"profile_id", input.at("controller_id")},
        {"calls", graph.reachable_envelope_calls / 2}, {"relation", "equivalent"}, {"assurance", "numerical"}});
    invocations.push_back({{"module_id", "csl::geometry::minkowski-sum"},
        {"operation", "registered Minkowski sum with stage-transformed authored discrete action hull"},
        {"provider", reachable_provider_id}, {"selected_method_id", reachable_set_method}, {"profile_id", input.at("controller_id")},
        {"calls", graph.reachable_envelope_calls / 2}, {"relation", "equivalent"}, {"assurance", "numerical"}});
    const std::array<std::string,5> representation_modules{"not_used", "csl::reachability::finite_plan_box",
        "csl::reachability::finite_plan_zonotope", "csl::reachability::finite_plan_parallelotope",
        "csl::reachability::finite_plan_ellipsoid"};
    if(representation_index>0) invocations.push_back({{"module_id",representation_modules.at(representation_index)},
        {"operation","one-step fixed-discrete-edge coordinate-outer enclosure and coordinate-bound child check, with authored-stage safety before graph selection"},
        {"provider","public-function"},{"profile_id",input.at("controller_id")},
        {"representation",representation_names.at(representation_index)},
        {"calls",graph.representation_filter_calls},{"rejected",graph.representation_filter_rejections},
        {"relation","outer"},{"assurance","numerical"},
        {"membership_lowering","box/zonotope/parallelotope/ellipsoid coordinate outer bounds; no conversion claimed"}});
    if(graph.action_cloud_calls>0) invocations.push_back({{"module_id",representation_modules.at(representation_index)},
        {"operation","whole authored-action image outer envelope per retained parent via auxiliary control-image disturbance lift"},
        {"provider","public-function"},{"profile_id",input.at("controller_id")},
        {"calls",graph.action_cloud_calls},{"relation","outer"},{"assurance","numerical"},
        {"semantics","artificial external set is exactly B*conv(authored action catalogue); it is not the source task disturbance or a second player"}});
    Json predicted_sets=Json::array({{{"role", "retained-stage-layered-singleton-nodes"},
        {"representation", "polytope-h"}, {"relation", "equivalent"}, {"assurance", "numerical"}, {"nodes", nodes}}});
    if(!action_clouds.empty())predicted_sets.push_back({{"role","complete-authored-action-parent-clouds"},
        {"representation",representation_names.at(representation_index)},
        {"relation","outer"},{"assurance","numerical"},{"clouds",action_clouds}});
    Json response{{"task_id", input.at("task_id")}, {"task_sha256", input.at("task_sha256")},
        {"action_profile_id", input.at("action_profile_id")},
        {"policy_id", input.at("controller_id").get<std::string>() + "/budgeted-backward-graph-mpc/1"},
        {"representation", representation_index}, {"invocations", invocations},
        {"geometry_selection",geometry_selection},{"geometry_invocations",geometry_calls},
        {"predicted_sets", predicted_sets},
        {"graph_receipt", {{"schema", "csl.closed-loop.finite-action-backward-graph/1"},
            {"task_id", input.at("task_id")}, {"task_sha256", input.at("task_sha256")},
            {"source_model_id", input.at("source_model_id")}, {"predictor_model_id", input.at("predictor_model_id")},
            {"original_horizon", input.at("original_horizon")}, {"absolute_stage_offset", request.absolute_stage_offset},
            {"action_profile_id", input.at("action_profile_id")}, {"objective_id", request.running_cost.objective_id},
            {"representation", representation_names.at(representation_index)}, {"beam_width", beam_width}, {"max_graph_nodes", max_nodes},
            {"geometry_selection",geometry_selection},{"geometry_invocations",geometry_calls},
            {"representation_filter_calls",graph.representation_filter_calls},
            {"representation_filter_rejections",graph.representation_filter_rejections},
            {"action_cloud_calls",graph.action_cloud_calls},{"action_cloud_envelopes",action_clouds},
            {"search_coverage", graph.search_complete ? "complete" : "incomplete"},
            {"node_budget_exhausted", graph.node_budget_exhausted},
            {"optimality_scope", "Bellman minimum over retained graph only; no claim over pruned paths or nonlinear plant"},
            {"no_path_semantics", "no viable retained path after numerical filtering is not a global infeasibility proof"},
            {"layer_statistics", layers}, {"nodes", nodes}, {"edges", edges},
            {"backward_viability_applied_before_selection", true}}}};
    if(!graph.has_viable_path) {
        response["status"] = "unsupported";
        response["reason"] = graph.node_budget_exhausted ?
            "Graph node budget exhausted before a viable full-horizon path was retained; no control is returned." :
            "No viable retained path passed the numerical backward filter; no control is returned and this is not a global infeasibility proof.";
        return response;
    }
    Json states = Json::array(), controls = Json::array(), selected_edges = Json::array();
    for(const auto id : graph.selected_nodes) {
        const auto& node = graph.nodes[id];
        states.push_back(node.state);
        if(node.action_index) {
            controls.push_back(request.actions.catalogue[*node.action_index]);
            selected_edges.push_back({{"parent_node_id", *node.parent_node}, {"child_node_id", id},
                {"absolute_stage", request.absolute_stage_offset + node.stage - 1},
                {"action_index", *node.action_index}, {"action", request.actions.catalogue[*node.action_index]},
                {"child_state", node.state}, {"action_lineage", node.action_lineage},
                {"backward_viable", node.backward_viable},
                {"representation_filter_passed",node.representation_filter_passed?Json(*node.representation_filter_passed):Json(nullptr)},
                {"representation_filter_outcome",node.representation_filter_outcome},
                {"representation_edge_outer_enclosure",node.representation_outer_lower.empty()?Json(nullptr):Json{{"lower",node.representation_outer_lower},
                    {"upper",node.representation_outer_upper},{"representation",representation_names.at(representation_index)},
                    {"coordinate_outer_box",true},{"relation","outer"},{"assurance","numerical"}}},
                {"backward_edge_status", backward_status(node.backward_status)}});
        }
    }
    const auto terminal_value = optimization::evaluate(request.objective,
        graph.nodes[graph.selected_nodes.back()].state);
    if(const auto* error = std::get_if<Diagnostic>(&terminal_value))
        return {{"status", "unsupported"}, {"reason", error->explanation}};
    const double terminal_cost = std::get<double>(terminal_value);
    double running_cost_value = 0.0;
    for(const auto id : graph.selected_nodes) running_cost_value += graph.nodes[id].edge_running_cost;
    response["status"] = "accepted";
    response["control"] = request.actions.catalogue[*graph.nodes[graph.selected_nodes[1]].action_index];
    response["selected_plan"] = {{"states", states}, {"controls", controls},
        {"terminal_objective", terminal_cost}, {"running_objective", running_cost_value},
        {"total_objective", terminal_cost + running_cost_value}};
    response["selected_edges"] = selected_edges;
    response["selector"] = {{"search_coverage", graph.search_complete ? "complete" : "incomplete"},
        {"beam_width", beam_width}, {"max_graph_nodes", max_nodes}, {"retained_graph_value", graph.total_objective},
        {"terminal_objective", terminal_cost}, {"running_objective", running_cost_value},
        {"total_replay_objective", terminal_cost + running_cost_value},
        {"score_kind", "exact-source-cost-on-numerical-affine-predictor"},
        {"policy_semantics", "receding finite-action graph MPC; numerical backward predecessor plus authored discrete-edge witnesses filter before Bellman selection; selected approximation records a whole authored-action outer cloud per retained parent with selected-shape numerical membership witnesses, while its per-edge safety filter checks a coordinate-outer relaxation; replans after each observed hold"},
        {"optimality_scope", "retained graph only; not complete finite-action optimum, nonlinear global optimum, or causal feedback optimum"}};
    return response;
}

template<class T, class... E> T take_history(std::variant<T, E...> result, const char* field) {
    if (const auto* value = std::get_if<T>(&result)) return *value;
    std::string detail = "history operation failed";
    std::visit([&](const auto& item) {
        using V = std::decay_t<decltype(item)>;
        if constexpr (std::is_same_v<V, Diagnostic>) detail = item.field + ": " + item.explanation;
        else if constexpr (std::is_same_v<V, Diagnostics>) {
            if (!item.empty()) detail = item.front().field + ": " + item.front().explanation;
        } else if constexpr (std::is_same_v<V, OperationStopped>) detail = item.diagnostics;
    }, result);
    throw std::runtime_error(std::string(field) + ": " + detail);
}

#if CSL_NATIVE_HAS_HIGHS && CSL_NATIVE_HAS_QHULL
template<class Port>
registry::PreparedProvider<Port> feedback_provider(registry::Registration<Port> registration,
        const std::string& representation) {
    registry::Requirements requirements;
    requirements.output.representation = {representation};
    if constexpr(std::is_same_v<Port, registry::GeometryPort> ||
                 std::is_same_v<Port, registry::ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return prepare_provider(std::move(registration), requirements);
}

Json feedback_membership_json(const reachability::FeedbackSet& shape,
        const std::vector<std::size_t>& indices, const std::string& role) {
    Json membership = std::visit([&](const auto& value) -> Json {
        using T = std::decay_t<decltype(value)>;
        if constexpr(std::is_same_v<T, reachability::FeedbackHMembership>) {
            auto result = set_json(take_history(sets::from_handle(value.set), "feedback-membership"));
            if(result.at("representation") != "polytope-h")
                throw std::runtime_error("feedback H membership is not H-represented");
            result["kind"] = "h";
            if(value.parallelotope_frame)
                result["parallelotope_frame"] = matrix_json(value.parallelotope_frame->rows,
                    value.parallelotope_frame->cols, [&](auto i, auto j) {
                        return value.parallelotope_frame->values[i*value.parallelotope_frame->cols+j]; });
            return result;
        } else {
            const auto& factor = [&]() -> const Matrix& {
                if constexpr(std::is_same_v<T, reachability::FeedbackZonotopeMembership>) return value.generators;
                else return value.factor;
            }();
            Json result{{"kind", std::is_same_v<T, reachability::FeedbackZonotopeMembership> ? "zonotope" : "ellipsoid"},
                {"center", value.center}, {"factor_count", factor.cols},
                {"factor", matrix_json(factor.rows, factor.cols, [&](auto i, auto j) {
                    return factor.values[i*factor.cols+j]; })}};
            if constexpr(std::is_same_v<T, reachability::FeedbackZonotopeMembership>) {
                result["factor_ids"] = Json::array();
                for(const auto& id : value.factors) result["factor_ids"].push_back(id.value);
            }
            return result;
        }
    }, shape.membership);
    membership["indices"] = indices;
    membership["role"] = role;
    membership["scope"] = "forward_relevant_from_observation";
    membership["relation"] = shape.relation == SetRelation::outer ? "outer" :
        shape.relation == SetRelation::equivalent ? "equivalent" : "other";
    membership["assurance"] = shape.assurance == Assurance::numerical ? "numerical" : "validated";
    membership["source_sets"] = Json::array();
    for(const auto& id : shape.source_sets) membership["source_sets"].push_back(id.value);
    membership["construction"] = shape.construction;
    membership["strict_source_domain"] = Json::array();
    for(const auto& predicate : shape.strict_source_domain)
        membership["strict_source_domain"].push_back({{"coordinate", predicate.coordinate},
            {"lower_bound", predicate.lower_bound}, {"strict", true}});
    membership["requests"] = Json::array();
    for(const auto& reference : shape.requests)
        membership["requests"].push_back({{"request", reference.identity.request.value},
            {"ideal_output", reference.identity.ideal_output.value}});
    membership["providers"] = Json::array();
    for(const auto& call : shape.providers) membership["providers"].push_back({
        {"request", call.request.value}, {"port", call.port},
        {"requested", call.requested_module.value},
        {"requested_version", call.requested_version ? Json(*call.requested_version) : Json(nullptr)},
        {"actual", call.actual_module ? Json(call.actual_module->value) : Json(nullptr)},
        {"actual_version", call.actual_version ? Json(*call.actual_version) : Json(nullptr)}});
    membership["support_calls"] = Json::array();
    for(const auto& record : shape.support_calls) std::visit([&](const auto& call) {
        using T = std::decay_t<decltype(call)>;
        const char* status = std::is_same_v<T, registry::LPQueryCompleted> ? "completed" :
            std::is_same_v<T, registry::LPQueryRejected> ? "rejected" :
            std::is_same_v<T, registry::LPQueryStopped> ? "stopped" :
            std::is_same_v<T, registry::LPQuerySolverUnsupported> ? "unsupported" : "not_run";
        const auto& provenance = [&]() -> const registry::Provenance& {
            if constexpr(std::is_same_v<T, registry::LPQueryRejected>) return call.rejection.provenance;
            else return call.provider;
        }();
        membership["support_calls"].push_back({{"program", call.request.program.value}, {"status", status},
            {"requested", provenance.requested.id.value},
            {"requested_version", provenance.requested.version ? Json(*provenance.requested.version) : Json(nullptr)},
            {"actual", provenance.actual ? Json(provenance.actual->id.value) : Json(nullptr)},
            {"actual_version", provenance.actual ? Json(provenance.actual->version) : Json(nullptr)}});
    }, record);
    membership["support_methods"] = Json::array();
    for(const auto method : shape.support_methods)
        membership["support_methods"].push_back(method == reachability::SupportBoundMethod::dual_candidate ?
            "dual_candidate" : "carrier_only");
    return membership;
}

Json feedback_stage_json(const reachability::FeedbackGeometryStage& stage, std::size_t n) {
    Json result{{"stage", stage.stage.value}, {"coordinates", stage.coordinates}, {"memberships", Json::array()}};
    std::vector<std::size_t> indices;
    for(const auto coordinate : stage.coordinates) indices.push_back(stage.stage.value*n+coordinate);
    for(const auto& [role, value] : std::array{
        std::pair{"forward", &stage.forward}, std::pair{"backward", &stage.backward},
        std::pair{"intersection", &stage.intersection}})
        if(*value) result["memberships"].push_back(feedback_membership_json(**value, indices, role));
    for(const auto& [role, value] : std::array{
        std::pair{"forward_h", &stage.forward_h}, std::pair{"backward_h", &stage.backward_h},
        std::pair{"intersection_h", &stage.intersection_h}})
        if(*value) result[role] = set_json(take_history(sets::from_handle((*value)->output), "feedback-source-h"));
    return result;
}

Json feedback_export(const problem::ResolvedProblem& resolved, const Json& in,
        const sets::SetData& terminal, std::size_t n) {
    using namespace reachability;
    const auto name = in.at("geometry_family").get<std::string>();
    const std::map<std::string, FeedbackFamily> families{
        {"polytope",FeedbackFamily::polytope}, {"box",FeedbackFamily::box},
        {"zonotope",FeedbackFamily::zonotope}, {"parallelotope",FeedbackFamily::parallelotope},
        {"ellipsoid",FeedbackFamily::ellipsoid}};
    const auto found = families.find(name);
    if(found == families.end()) throw std::runtime_error("unknown feedback family");
    const auto requested_generators = in.at("geometry_max_generators").get<std::int64_t>();
    if(requested_generators <= 0) throw std::runtime_error("geometry generator budget must be positive");
    const auto max_generators = static_cast<std::size_t>(requested_generators);
    auto lp = take_history(adapters::lp::make_highs_registration(), "feedback-highs");
    auto converter = take_history(adapters::polyhedral::make_qhull_registration(lp), "feedback-qhull");
    auto affine = geometry::make_affine_sum_registration({
        feedback_provider(geometry::make_lp_hull_reducer_registration(), ""),
        feedback_provider(lp, "csl.program-result.v1"),
        feedback_provider(converter, "csl.polyhedron.v")}, {{}, {}});
    ForwardDependencies forward{
        feedback_provider(geometry::polyhedral::make_projection_registration(), "csl.polyhedron.h"),
        feedback_provider(std::move(affine), "csl.polyhedron.v"),
        feedback_provider(converter, "csl.polyhedron.h")};
    auto intersection = feedback_provider(geometry::polyhedral::make_intersection_registration(), "csl.polyhedron.h");
    std::vector<StrictCoordinateLowerBound> strict;
    if(in.at("task_id") == "earth-orbit") strict.push_back({0, 0});
    auto outcome = feedback_geometry(resolved, {in.at("request_id").get<std::string>()},
        terminal.as_handle(), found->second, strict,
        {{forward, intersection}, feedback_provider(lp, "csl.program-result.v1"), max_generators}, {});
    const auto* failure = std::get_if<FeedbackGeometryFailure>(&outcome);
    const auto& geometry = failure ? failure->prefix : std::get<FeedbackGeometry>(outcome);
    Json result{{"family", name}, {"scope", "forward_relevant_from_observation"},
        {"status", failure ? "stopped" : "complete"}, {"stages", Json::array()}};
    for(const auto& row : geometry.stages) result["stages"].push_back(feedback_stage_json(row, n));
    if(failure) {
        result["stop_stage"] = failure->stage.value;
        result["stop_phase"] = static_cast<int>(failure->phase);
        result["pending_requests"] = Json::array();
        for(const auto& reference : failure->pending_requests)
            result["pending_requests"].push_back({{"request", reference.identity.request.value},
                {"ideal_output", reference.identity.ideal_output.value}});
        result["pending_providers"] = Json::array();
        for(const auto& call : failure->pending_providers)
            result["pending_providers"].push_back({{"request", call.request.value},
                {"port", call.port}, {"requested", call.requested_module.value},
                {"actual", call.actual_module ? Json(call.actual_module->value) : Json(nullptr)},
                {"actual_version", call.actual_version ? Json(*call.actual_version) : Json(nullptr)}});
        result["pending_support_calls"] = failure->pending_support_calls.size();
        std::visit([&](const auto& cause) {
            using T = std::decay_t<decltype(cause)>;
            if constexpr(std::is_same_v<T, Unsupported>) {
                result["stop_kind"] = "unsupported";
                result["diagnostics"] = Json::array();
                for(const auto& d : cause.diagnostics) result["diagnostics"].push_back({{"field",d.field},{"explanation",d.explanation}});
            } else {
                result["stop_kind"] = "operation_stopped";
                result["diagnostics"] = cause.diagnostics;
            }
        }, failure->cause);
    }
    return result;
}
#endif

Json continuous_history_query(const Json& in) {
    const auto solver = in.at("history_solver").get<std::string>();
    if (solver != "csl.convex.highs" && solver != "casadi-ipopt")
        throw std::runtime_error("unknown continuous history solver");
    const auto initial = vector(in.at("observed_physical_state"));
    const auto n = initial.size();
    const auto m = in.at("control_bounds").size();
    const auto& coefficients = in.at("predictor_stages");
    const auto horizon = coefficients.size();
    const auto stage = in.at("absolute_update_index").get<std::size_t>();
    const auto original = in.at("original_horizon").get<std::size_t>();
    if (!n || !m || !horizon || stage >= original || horizon != original - stage)
        throw std::runtime_error("invalid continuous remaining horizon or dimensions");
    std::vector<LinearStage> stages;
    for (const auto& row : coefficients)
        stages.push_back({matrix(row.at("A")), matrix(row.at("B")), Matrix{n, 0, {}}, vector(row.at("c"))});
    auto model = std::make_shared<const SystemModel>(SystemModel{
        {{n, m, 0}, TimeDomain::discrete, Coefficients{std::move(stages)}}, {}});
    const double dt = in.at("dt").get<double>();
    Vector times(horizon + 1);
    for (std::size_t i = 0; i <= horizon; ++i) times[i] = (stage + i) * dt;
    std::vector<AdmissibleSet> states, controls;
    for (std::size_t i = 0; i <= horizon; ++i)
        states.emplace_back(safe_box(in.at("state_bounds"), n, "history-state-" + std::to_string(i)).as_handle());
    for (std::size_t i = 0; i < horizon; ++i)
        controls.emplace_back(safe_box(in.at("control_bounds"), m, "history-control-" + std::to_string(i)).as_handle());
    const auto terminal = terminal_source(in.at("terminal_objective"), n);
    Problem source{{in.at("problem_id").get<std::string>()}, std::move(model), std::move(times),
        KnownInitial{initial}, ContinuousDomain{std::move(controls)}, std::move(states), {}, {},
        InformationPattern::nominal_open_loop, terminal};
    const auto resolved = take_history(problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}), "resolve");
    const auto universal = take(sets::make_universal({{"history-universal-terminal"}, n, {}}), "terminal-domain");
    const auto history = take_history(synthesis::recover_joint_history(resolved, universal), "recover-history");
    const auto cost = running_cost(in.at("running_cost"), original, m);
    const auto program = take_history(optimization::compile_history_cost(history, terminal, cost, stage), "compile-history-cost");
    const auto h = std::get<sets::HRepresentation>(history.relation.representation());
    const auto& q = program.quadratic;
    Json norms = Json::array();
    for (const auto& term : program.residual_norms)
        norms.push_back({{"map", matrix_json(term.map.rows, term.map.cols,
            [&](std::size_t i, std::size_t j) { return term.map.values[i * term.map.cols + j]; })},
            {"target", term.target}, {"weights", term.weights}, {"coefficient", term.coefficient}});
    Json response{{"status", "exported"}, {"task_id", in.at("task_id")}, {"task_sha256", in.at("task_sha256")},
        {"action_profile_id", in.at("action_profile_id")}, {"policy_id", in.at("controller_id")},
        {"history_relation", set_json(history.relation)},
        {"history_objective", {{"quadratic", {{"Q", matrix_json(q.Q.rows, q.Q.cols,
            [&](std::size_t i, std::size_t j) { return q.Q.values[i * q.Q.cols + j]; })},
            {"linear", q.linear}, {"offset", q.offset}}}, {"residual_norms", std::move(norms)}}},
        {"coordinates", {{"state_dimension", n}, {"control_dimension", m}, {"horizon", horizon},
            {"layout", "x0..xT,u0..u(T-1)"}}}, {"geometry", "not_used"},
        {"assurance", "numerical affine history; no validated completeness or nonlinear safety claim"}};
    response["requested_solver"] = solver;
    if(in.contains("geometry_family")) {
        if(solver != "casadi-ipopt") throw std::runtime_error("feedback family requires explicitly selected casadi-ipopt");
#if CSL_NATIVE_HAS_HIGHS && CSL_NATIVE_HAS_QHULL
        response["geometry"] = feedback_export(resolved, in, universal, n);
        if(response["geometry"].at("status") != "complete") {
            response["status"] = "failed";
            response["reason"] = "feedback geometry stopped; partial stage prefix retained";
            return response;
        }
#else
        response["status"] = "unavailable";
        response["reason"] = "feedback geometry requires registered HiGHS and Qhull";
        return response;
#endif
    }
    if (solver == "casadi-ipopt") return response;
    if (!program.residual_norms.empty()) {
        response["status"] = "unsupported";
        response["reason"] = "the selected convex QP provider does not support a sum of residual norms";
        return response;
    }
#if CSL_NATIVE_HAS_HIGHS
    SparseMatrix rows{h.inequalities.rows() + h.equalities.rows(), q.dimension, {0}, {}, {}};
    std::vector<Interval> bounds;
    const auto append_rows = [&](const auto& matrix, const auto& values, bool equality) {
        for (std::size_t i = 0; i < matrix.rows(); ++i) {
            for (std::size_t j = 0; j < matrix.cols(); ++j) {
                if (const double value = matrix(i, j); value != 0) {
                    rows.column_indices.push_back(j); rows.values.push_back(value);
                }
            }
            rows.row_offsets.push_back(rows.values.size());
            const auto value = values[i];
            bounds.push_back(equality ? Interval{value, value} : Interval{{}, value});
        }
    };
    append_rows(h.inequalities, h.upper_bounds, false);
    append_rows(h.equalities, h.equality_values, true);
    auto qp = take_history(optimization::make_convex_program({
        {{in.at("problem_id").get<std::string>()}, {in.at("request_id").get<std::string>()}},
        QuadraticTerminal{q.Q, q.linear, q.offset}, std::move(rows),
        std::vector<Interval>(q.dimension), std::move(bounds), {}}), "make-history-qp");
    using namespace registry;
    Registry<ConvexPort> registry;
    auto entry = take_history(adapters::convex::make_highs_registration(), "highs-registration");
    if (registry.add(std::move(entry))) throw std::runtime_error("convex registration failed");
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    auto preparation = prepare_pipeline(select(registry, {{"csl.convex.highs"}, {}}, qp, requirements));
    if (std::holds_alternative<Rejection>(preparation)) throw std::runtime_error("convex provider rejected history QP");
    const auto& prepared = std::get<PreparedPipeline<ConvexPort>>(preparation);
    auto [workspace] = prepared.create();
    const auto resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    const auto actual = prepared.provenance()[0].actual.value();
    const auto outcome = workspace->run({resources, {}, {}, {1e-8, 1e-8}, "continuous-history"});
    const auto* result = std::get_if<ProgramResult>(&outcome);
    if (!result || result->termination != Termination::completed ||
        result->outcome.value != MathematicalOutcome::optimal || !result->primal ||
        !optimization::check_program_result(*result, qp, Assurance::numerical).empty()) {
        response["status"] = "failed";
        response["reason"] = "convex history provider did not return a completed optimum";
        response["solver_receipt"] = {{"provider", actual.id.value}, {"version", actual.version},
            {"raw_diagnostics", result ? result->raw_diagnostics : "provider returned unsupported"}};
        return response;
    }
    const auto& primal = *result->primal;
    if (primal.size() != q.dimension || !std::all_of(primal.begin(), primal.end(), [](double value) { return std::isfinite(value); })) {
        response["status"] = "failed";
        response["reason"] = "convex history provider returned an invalid primal";
        response["solver_receipt"] = {{"provider", actual.id.value}, {"version", actual.version},
            {"raw_diagnostics", result->raw_diagnostics}};
        return response;
    }
    std::vector<Vector> xs, us;
    for (std::size_t k = 0; k <= horizon; ++k)
        xs.emplace_back(primal.begin() + k*n, primal.begin() + (k+1)*n);
    const auto control_offset = (horizon+1)*n;
    for (std::size_t k = 0; k < horizon; ++k)
        us.emplace_back(primal.begin() + control_offset+k*m, primal.begin() + control_offset+(k+1)*m);
    const auto evaluated = take_history(optimization::evaluate_history_cost(program, xs, us), "evaluate-history-cost");
    response["status"] = "solved";
    response["primal"] = primal;
    response["source_cost"] = {{"terminal", evaluated.terminal}, {"running", evaluated.running}, {"total", evaluated.total}};
    response["solver_receipt"] = {{"provider", actual.id.value}, {"version", actual.version},
        {"termination", "completed"}, {"outcome", "optimal"}, {"assurance", "numerical"},
        {"raw_diagnostics", result->raw_diagnostics}};
    return response;
#else
    response["status"] = "unavailable";
    response["reason"] = "compiled native executable has no registered convex QP provider";
    return response;
#endif
}

Json query(const Json& in) {
    if(in.value("mode", std::string{}) == "continuous-history/1") return continuous_history_query(in);
    if(in.contains("candidate_action_indices") &&
            (!in.at("candidate_action_indices").is_array() || in.at("candidate_action_indices").empty())) {
        auto result=query_failure(in,"rejected",
            "An explicit candidate_action_indices catalogue must be a nonempty array of full-horizon histories.");
        result["mathematical_support"]="not_evaluated";
        result["candidate_plan_search"]={{"policy_id",in.value("candidate_search_policy",std::string("caller-declared-history-subset/1"))},
            {"candidate_count",0},{"search_coverage","not_evaluated"},
            {"reason","no candidate histories were supplied; exhaustive search was not substituted"}};
        return result;
    }
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
    if(in.contains("candidate_action_indices")) {
        request.candidate_action_indices.emplace();
        for(const auto& candidate:in.at("candidate_action_indices"))
            request.candidate_action_indices->push_back(candidate.get<std::vector<std::size_t>>());
    }
    const auto representation_index = in.at("representation_index").get<std::size_t>();
    const std::array<optimization::NominalRepresentation, 5> representations{
        optimization::NominalRepresentation::exact_polytope,
        optimization::NominalRepresentation::box,
        optimization::NominalRepresentation::zonotope,
        optimization::NominalRepresentation::parallelotope,
        optimization::NominalRepresentation::ellipsoid};
    if(representation_index >= representations.size()) throw std::runtime_error("representation index must be in [0,4]");
    if(in.value("search_policy", std::string{}) == "stage-layered-backward-viability")
        return graph_response(in, request,
            in.at("limits").value("max_beam_width", std::size_t{16}),
            in.at("limits").value("max_graph_nodes", std::size_t{2048}),
            representations[representation_index],
            in.at("limits").value("max_generators_per_stage",std::size_t{1000}));
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
    const auto candidate_evaluation_coverage = std::visit([](const auto& row) -> std::string {
        using T = std::decay_t<decltype(row)>;
        if constexpr(std::is_same_v<T, optimization::NominalTrackSelected>) {
            if(row.coverage==optimization::NominalSearchCoverage::complete) return "complete";
            if(row.coverage==optimization::NominalSearchCoverage::stopped) return "stopped";
            return "incomplete";
        }
        if constexpr(std::is_same_v<T, optimization::NominalTrackNoScoredCandidate>) {
            if(row.coverage==optimization::NominalSearchCoverage::complete) return "complete";
            if(row.coverage==optimization::NominalSearchCoverage::stopped) return "stopped";
            return "incomplete";
        }
        if constexpr(std::is_same_v<T, optimization::NominalTrackStopped>) return "stopped";
        return "incomplete";
    }, track.outcome);
    Json invocations = Json::array({{{"module_id", "csl::optimization::finite_action_nominal_profile"},
        {"operation", operations.at(representation_index)},
        {"provider", "public-function"},
        {"profile_id", in.at("controller_id")}, {"outcome", route_outcome}}});
    Json base{{"task_id", in.at("task_id")}, {"task_sha256", in.at("task_sha256")},
        {"action_profile_id", in.at("action_profile_id")},
        {"policy_id", in.at("controller_id").get<std::string>() + "/receding-fixed-plan-mpc/1"},
        {"representation", representation_index}, {"invocations", invocations}};
    Json candidate_plan_search=nullptr;
    if(in.contains("candidate_action_indices") && request.candidate_action_indices) {
        const auto action_count=in.at("actions").size();
        std::size_t full_count=1;
        bool overflow=false;
        for(std::size_t stage=0;stage<horizon;++stage) {
            if(action_count!=0 && full_count>std::numeric_limits<std::size_t>::max()/action_count) {
                overflow=true;
                break;
            }
            full_count*=action_count;
        }
        candidate_plan_search={{"policy_id",in.value("candidate_search_policy",std::string("caller-declared-history-subset/1"))},
            {"full_authored_horizon",horizon},{"original_horizon",in.at("original_horizon")},
            {"action_catalogue_size",action_count},{"candidate_count",request.candidate_action_indices->size()},
            {"candidate_action_indices",*request.candidate_action_indices},
            {"candidate_budget",in.at("limits").at("max_plans")},
            {"all_rows_span_full_prediction_horizon",true},{"indices_refer_to_untouched_source_action_catalogue",true},
            {"full_action_history_count",overflow?Json("exceeds_size_t"):Json(full_count)},
            {"search_coverage",!overflow&&full_count==request.candidate_action_indices->size()?"complete":"incomplete"},
            {"candidate_evaluation_coverage",candidate_evaluation_coverage}};
        base["candidate_plan_search"]=candidate_plan_search;
    }
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
        {"policy_semantics", in.contains("candidate_action_indices") ?
            "receding-horizon finite-action fixed-plan MPC over a declared bounded set of full-remaining-horizon action-index histories; selected first action is reapplied after observation" :
            "receding-horizon nominal finite-action fixed-plan selection; first action reapplied after observation"},
        {"optimality_scope", in.contains("candidate_action_indices") ?
            "declared full-horizon candidate histories only; coverage against the complete action product is reported separately; no nonlinear global-feedback claim" :
            "finite action catalogue and declared numerical affine predictor; no nonlinear global-feedback claim"}};
    base["query_receipt"] = {{"schema", "csl.closed-loop.native-policy-query-receipt/1"},
        {"task_id", in.at("task_id")}, {"task_sha256", in.at("task_sha256")},
        {"source_model_id", in.at("source_model_id")}, {"predictor_model_id", in.at("predictor_model_id")},
        {"predictor_assurance", in.at("predictor_assurance")},
        {"objective_id", result.objective_id}, {"original_horizon", result.original_horizon},
        {"absolute_update_index", result.absolute_stage_offset}, {"action_profile_id", in.at("action_profile_id")},
        {"controller_id", in.at("controller_id")}, {"representation", in.at("representation_name")},
        {"search_coverage", coverage}, {"candidate_score", selected->candidate_score},
        {"score_kind", base["selector"]["score_kind"]}, {"selected_control", selected->replay.controls.front()},
        {"predicted_set_role", "fixed-plan-trajectory-enclosure"},
        {"candidate_plan_search",candidate_plan_search}, {"invocations", base["invocations"]}};
    return base;
}
} // namespace

int main() {
    std::string line;
    while(std::getline(std::cin, line)) {
        Json input;
        try {
            input=Json::parse(line);
            auto output=query(input);
            output["build_backend_profile"]=native_build_backend_profile();
            std::cout << output.dump() << '\n';
        } catch(const std::exception& error) {
            auto output=query_failure(input, "failed", error.what());
            output["build_backend_profile"]=native_build_backend_profile();
            std::cout << output.dump() << '\n';
        }
        std::cout.flush();
    }
    return 0;
}
