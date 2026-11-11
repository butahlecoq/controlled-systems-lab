#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/composition_catalogue.hpp>
#include <csl/geometry/generator_adapter.hpp>
#include <csl/geometry/approximation.hpp>
#include <csl/geometry/box_parallelotope.hpp>
#include <csl/geometry/quickhull_2d.hpp>
#include <csl/geometry/legacy_btulshor.hpp>
#include <csl/optimization/finite_action_nominal.hpp>
#include <csl/optimization/phase_one.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <csl/registry/strategy_catalogue.hpp>
#include <csl/sets/data.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/synthesis/terminal_minimizers.hpp>
#include "two_points_fixture.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>

#ifndef CSL_CATALOGUE_HAS_HIGHS
#define CSL_CATALOGUE_HAS_HIGHS 0
#endif
#ifndef CSL_CATALOGUE_HAS_QHULL
#define CSL_CATALOGUE_HAS_QHULL 0
#endif
#ifndef CSL_CATALOGUE_HAS_HIGHS_CONVEX
#define CSL_CATALOGUE_HAS_HIGHS_CONVEX 0
#endif

namespace {
using namespace csl;

std::string escape(std::string_view value) {
    std::ostringstream out;
    for (const unsigned char ch : value) {
        switch (ch) {
        case '"': out << "\\\""; break;
        case '\\': out << "\\\\"; break;
        case '\n': out << "\\n"; break;
        case '\r': out << "\\r"; break;
        case '\t': out << "\\t"; break;
        default:
            if (ch < 0x20) out << "\\u00" << "0123456789abcdef"[ch >> 4] << "0123456789abcdef"[ch & 0xf];
            else out << static_cast<char>(ch);
        }
    }
    return out.str();
}

std::string read_file(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot read inventory file: " + path);
    std::ostringstream contents;
    contents << input.rdbuf();
    return contents.str();
}

void append_provider(std::vector<registry::Registration<registry::LPPort>>& providers,
        registry::Registration<registry::LPPort> provider) {
    providers.push_back(std::move(provider));
}

void emit_rejection(std::ostream&, const registry::Rejection&);

std::vector<registry::Registration<registry::LPPort>> compiled_lp_providers() {
    std::vector<registry::Registration<registry::LPPort>> result;
#if CSL_CATALOGUE_HAS_HIGHS
    auto highs = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(highs))
        throw std::runtime_error("compiled HiGHS registration failed");
    append_provider(result,std::get<registry::Registration<registry::LPPort>>(std::move(highs)));
#endif
    auto phase_one = optimization::phase_one::make_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(phase_one))
        throw std::runtime_error("compiled Phase-I registration failed");
    append_provider(result,std::get<registry::Registration<registry::LPPort>>(std::move(phase_one)));
    return result;
}

registry::Registration<registry::LPPort> priority_tie_provider() {
    optimization::phase_one::Options options;
    options.structural_entering_priorities = {0,1,2,3,4};
    auto provider = optimization::phase_one::make_registration(std::move(options));
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(provider))
        throw std::runtime_error("compiled Phase-I priority-tie registration failed");
    return std::get<registry::Registration<registry::LPPort>>(std::move(provider));
}

template<class T> T take(numeric::Result<T> result) {
    if (!std::holds_alternative<T>(result)) throw std::runtime_error("numeric snapshot failed");
    return std::get<T>(std::move(result));
}

template<class T, class... Alternatives> T take_variant(std::variant<T, Alternatives...> result,
        std::string_view operation) {
    if (!std::holds_alternative<T>(result)) throw std::runtime_error(std::string(operation) + " failed");
    return std::get<T>(std::move(result));
}

void emit_generator_operation_candidates(std::ostream& out) {
    auto source = take_variant(sets::make_generator_set({{"catalogue-generator-source"},{0},
        {1,1,{1}},{{"catalogue.factor.0"}},{0,1,{}},{},{"x"}}),"generator fixture construction");

    auto operation_registration = geometry::generators::make_operation_registration();
    registry::Registry<registry::GeometryPort> operation_registry;
    if (operation_registry.add(operation_registration)) throw std::runtime_error("generator operation registration failed");
    registry::Requirements operation_requirements;
    operation_requirements.output.representation = {"csl.zonotope"};
    operation_requirements.output.relation = SetRelation::equivalent;
    auto operation_provider = take_variant(registry::prepare_provider(
        registry::select_provider(operation_registry,
            {{"csl.geometry.generators.operations"},{"1.1.0"}},operation_requirements)),
        "generator operation provider prepare");
    OperationRequest operation_request{{{"catalogue-generator-profile"},{"affine-image"},{"catalogue-generator-image"}},
        {"csl.geometry.generators.operations"},
        AffineImage{source.as_handle(),{1,1,{2}},{1}},SetRelation::equivalent,Assurance::numerical};
    auto operation_plan = take_variant(operation_provider.prepare(operation_request),"generator affine-image prepare");
    auto [operation_workspace] = operation_plan.create();
    auto operation_result = take_variant(operation_workspace->run({{},{},{},{1e-8,1e-8},"catalogue-generator-profile"}),
        "generator affine-image execution");
    if (!check_geometry_evidence(operation_result.evidence,operation_request).empty())
        throw std::runtime_error("generator affine-image evidence rejected");
    const auto image = take_variant(sets::from_generator_handle(operation_result.output),"generator output import");
    if (image.center() != Vector{1} || image.generators().values != Vector{2})
        throw std::runtime_error("generator affine-image oracle mismatch");

    auto conversion_registration = geometry::generators::make_v_conversion_registration(2);
    registry::Registry<registry::ConversionPort> conversion_registry;
    if (conversion_registry.add(conversion_registration)) throw std::runtime_error("generator V-conversion registration failed");
    registry::Requirements conversion_requirements;
    conversion_requirements.output.representation = {"csl.polyhedron.v"};
    conversion_requirements.output.relation = SetRelation::equivalent;
    auto conversion_provider = take_variant(registry::prepare_provider(
        registry::select_provider(conversion_registry,
            {{"csl.geometry.generators.v-conversion"},{"1.0.0"}},conversion_requirements)),
        "generator V-conversion provider prepare");
    ConversionRequest conversion_request{{{"catalogue-generator-profile"},{"v-conversion"},{"catalogue-generator-v"}},
        image.as_handle(),{"csl.polyhedron.v"},Assurance::numerical};
    auto conversion_plan = take_variant(conversion_provider.prepare(conversion_request),"generator V-conversion prepare");
    auto [conversion_workspace] = conversion_plan.create();
    auto conversion_result = take_variant(conversion_workspace->run({{},{},{},{1e-8,1e-8},"catalogue-generator-profile"}),
        "generator V-conversion execution");
    if (!check_geometry_evidence(conversion_result.evidence,conversion_request).empty())
        throw std::runtime_error("generator V-conversion evidence rejected");
    const auto converted = take_variant(sets::from_handle(conversion_result.output),"converted V output import");
    const auto representation = converted.representation();
    const auto* vertices = std::get_if<sets::VRepresentation>(&representation);
    if (!vertices || vertices->vertices.rows() != 2 || vertices->vertices.cols() != 1)
        throw std::runtime_error("generator V-conversion output shape mismatch");
    const std::set<double> converted_vertices{vertices->vertices(0,0),vertices->vertices(1,0)};
    if (converted_vertices != std::set<double>{-1,3})
        throw std::runtime_error("generator V-conversion vertex oracle mismatch");

    out << "[{\"graph_id\":\"supporting/generator-affine-image-1d-v1\",\"status\":\"admitted\","
        << "\"attempt\":\"completed\",\"request_id\":\"affine-image\","
        << "\"requested\":{\"id\":\"csl.geometry.generators.operations\",\"version\":\"1.1.0\"},"
        << "\"actual\":{\"id\":\"csl.geometry.generators.operations\",\"version\":\"1.1.0\"},"
        << "\"input_dimension\":1,\"output_representation\":\"csl.zonotope\",\"center\":[1],\"generators\":[2]},"
        << "{\"graph_id\":\"supporting/generator-v-conversion-1d-v1\",\"status\":\"admitted\","
        << "\"attempt\":\"completed\",\"request_id\":\"v-conversion\","
        << "\"requested\":{\"id\":\"csl.geometry.generators.v-conversion\",\"version\":\"1.0.0\"},"
        << "\"actual\":{\"id\":\"csl.geometry.generators.v-conversion\",\"version\":\"1.0.0\"},"
        << "\"input_dimension\":1,\"output_representation\":\"csl.polyhedron.v\",\"vertex_count\":"
        << vertices->vertices.rows() << ",\"vertices\":[" << *converted_vertices.begin() << ','
        << *converted_vertices.rbegin() << "]}]";
}

SetHandle interval(std::string id) {
    const sets::Description description{SetId{std::move(id)},1,{"u"}};
    const sets::HRepresentation representation{
        take(numeric::snapshot(Matrix{2,1,{1,-1}})),take(numeric::snapshot_vector(Vector{1,0})),
        take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))};
    auto result = sets::make_h(description,representation);
    if (!std::holds_alternative<sets::SetData>(result)) throw std::runtime_error("interval construction failed");
    return std::get<sets::SetData>(std::move(result)).as_handle();
}

problem::ResolvedProblem ts01_problem() {
    const LinearStage stage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}};
    auto model = std::make_shared<const SystemModel>(SystemModel{
        Dynamics{{1,1,0},TimeDomain::discrete,stage},{}});
    Problem source;
    source.id = {"catalogue-ts01-integrator"};
    source.model = std::move(model);
    source.times = {0,1,2};
    source.initial = KnownInitial{{0}};
    source.controls = ContinuousDomain{{interval("catalogue-u0"),interval("catalogue-u1")}};
    source.states = {UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    source.information = InformationPattern::nominal_open_loop;
    QuadraticTerminal objective;
    objective.Q = Matrix{1,1,{2}};
    objective.linear = {-2};
    objective.offset = 1;
    source.objective = std::move(objective);
    auto resolved = problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled,{},{}});
    if (!std::holds_alternative<problem::ResolvedProblem>(resolved))
        throw std::runtime_error("TS01 profile problem resolution failed");
    return std::get<problem::ResolvedProblem>(std::move(resolved));
}

void emit_ts01_candidates(std::ostream& out) {
    registry::StrategyRegistry strategies;
    if (strategies.add(synthesis::strategy_ts01::make_registration()))
        throw std::runtime_error("TS01 strategy registration failed");
    const auto problem = ts01_problem();
    FamilyRequest family;
    family.profile = "ts01_exact_integrator";
    family.objective = problem.identity();
    family.target = FamilyTarget::exact_optimal_relation;
    family.assurance = Assurance::numerical;
    family.representation = {"csl.polyhedron.h"};
    StrategyConfiguration configuration;
    configuration.strategy = {synthesis::strategy_ts01::strategy_id};
    configuration.representation = family.representation;
    registry::StrategyRequest request{problem,configuration,family,{}, {}};
    registry::Requirements requirements;
    requirements.output.representation = family.representation;
    requirements.output.assurance = family.assurance;
    requirements.output.family = family.target;
    requirements.output.completeness = registry::Completeness::established;
    const auto rows = registry::enumerate_strategy_candidates(strategies,request,requirements);
    out << '[';
    for (std::size_t i = 0; i < rows.size(); ++i) {
        if (i) out << ',';
        const auto& row = rows[i];
        out << "{\"graph_id\":\"" << escape(row.graph.id) << "\",\"strategy\":\""
            << escape(row.graph.strategy.id.value) << "\",\"version\":\""
            << escape(row.graph.strategy.version) << "\",\"status\":\""
            << (row.status == registry::CandidateStatus::admitted ? "admitted" : "incompatible")
            << "\",\"prepared_providers\":[";
        for (std::size_t j = 0; j < row.provenance.size(); ++j) {
            if (j) out << ',';
            const auto& provider = row.provenance[j];
            out << "{\"port\":\"" << escape(provider.port) << "\",\"requested\":\""
                << escape(provider.requested.id.value) << "\",\"actual\":\""
                << escape(provider.actual ? provider.actual->id.value : "unresolved") << "\",\"version\":\""
                << escape(provider.actual ? provider.actual->version : "unresolved") << "\"}";
        }
        out << "],\"first_unmet\":";
        if (row.rejection) emit_rejection(out,*row.rejection);
        else out << "null";
        if (row.status == registry::CandidateStatus::admitted) {
            auto prepared = registry::prepare_strategy_candidate(strategies,row.graph,request,requirements);
            out << ",\"reprepare\":\""
                << (std::holds_alternative<registry::PreparedStrategyCandidate>(prepared) ? "admitted" : "rejected")
                << "\"}";
        } else out << ",\"reprepare\":\"not_run\"}";
    }
    out << ']';
}

std::string_view nominal_representation(optimization::NominalRepresentation value) {
    using R = optimization::NominalRepresentation;
    switch (value) {
    case R::exact_polytope: return "exact_polytope";
    case R::box: return "box";
    case R::zonotope: return "zonotope";
    case R::parallelotope: return "parallelotope";
    case R::ellipsoid: return "ellipsoid";
    }
    throw std::runtime_error("unknown nominal representation");
}

void emit_nominal_profiles(std::ostream& out) {
    const auto source = issue824::fixture::two_points_request("catalogue-nominal-source");
    optimization::FiniteActionNominalRequest request{
        source.problem, {"catalogue-nominal-profile"}, source.system,
        {4.5, 0.0, 0.0, 0.0}, source.actions, {{1.0}, {1.0}, {1.0}},
        source.admissible_states, source.objective};
    const auto outcome = optimization::finite_action_nominal(
        request, {27, 1000, 100000, 1000, 0.0});
    const auto* result = std::get_if<optimization::FiniteActionNominalResult>(&outcome);
    out << "[";
    if (!result) {
        out << "{\"graph_id\":\"nominal-two-points-v1\",\"status\":\"implementation_missing\",\"first_unmet\":{\"field\":\"finite_action_nominal\",\"reason\":\"native profile returned unsupported or stopped\"}}]";
        return;
    }
    for (std::size_t i = 0; i < result->tracks.size(); ++i) {
        if (i) out << ',';
        const auto& track = result->tracks[i];
        out << "{\"graph_id\":\"nominal-two-points-v1/" << nominal_representation(track.representation)
            << "\",\"group\":\"reachable_set_representation\",\"status\":\"";
        const auto* selected = std::get_if<optimization::NominalTrackSelected>(&track.outcome);
        out << (selected ? "admitted" : "implementation_missing") << "\",\"active_roles\":{"
            << "\"route_symbol\":\"csl::optimization::finite_action_nominal\","
            << "\"representation\":\"" << nominal_representation(track.representation)
            << "\",\"vertex_lp_provider\":\"not_used\",\"terminal_optimizer\":\"finite_action_enumeration\"},"
            << "\"profile\":{\"id\":\"env717-two-points-short-horizon-v1\","
            << "\"state_dimension\":4,\"control_dimension\":1,\"horizon\":3,"
            << "\"action_count\":3,\"plan_budget\":27,\"numerical_assurance\":\"numerical\","
            << "\"relation\":\"" << (i == 0 ? "exact deterministic objective" : "numerical outer-enclosure ranking estimate")
            << "\",\"tolerance\":0}";
        if (!selected) {
            out << ",\"first_unmet\":{\"field\":\"nominal_track\",\"reason\":\"no selected scored plan\"}}";
            continue;
        }
        out << ",\"attempt\":\"completed\",\"search_coverage\":\""
            << (selected->coverage == optimization::NominalSearchCoverage::complete ? "complete" : "incomplete")
            << "\",\"attempt_count\":" << selected->attempts.size()
            << ",\"selected_attempt\":" << selected->selected_attempt
            << ",\"candidate_score\":" << selected->candidate_score
            << ",\"score_kind\":\""
            << (selected->score_kind == optimization::NominalScoreKind::exact_deterministic_objective
                ? "exact_deterministic_objective" : "numerical_outer_enclosure_estimate")
            << "\",\"replay\":{\"state_count\":" << selected->replay.states.size()
            << ",\"control_count\":" << selected->replay.controls.size()
            << ",\"terminal_objective\":" << selected->replay.terminal_objective << "},\"first_unmet\":null}";
    }
    out << ']';
}

void emit_priority_tie_lp_profile(std::ostream& out) {
    optimization::phase_one::Options options;
    options.structural_entering_priorities = {0,1,2,3,4};
    auto registration = optimization::phase_one::make_registration(std::move(options));
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(registration))
        throw std::runtime_error("Phase-I priority-tie registration is unavailable");
    registry::Registry<registry::LPPort> providers;
    if (providers.add(std::get<registry::Registration<registry::LPPort>>(std::move(registration))))
        throw std::runtime_error("Phase-I priority-tie registration could not be admitted");
    const SparseMatrix matrix{1,5,{0,5},{0,1,2,3,4},{1,1,1,1,1}};
    auto program_result = optimization::phase_one::make_program(
        {{"catalogue-priority-tie-problem"},{"catalogue-priority-tie-lp"}},matrix,Vector{1.0});
    const auto* program = std::get_if<LinearProgram>(&program_result);
    if (!program) {
        out << "{\"graph_id\":\"phase-one-priority-tie/one-row-five-variable-v1\","
            << "\"status\":\"incompatible\",\"provider\":{\"id\":\"phase-one-priority-tie\",\"version\":\"1\"},"
            << "\"first_unmet\":{\"field\":\"profile.request\",\"reason\":\"native LP fixture rejected\"}}";
        return;
    }
    registry::Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    requirements.output.assurance = Assurance::numerical;
    const auto prepared = registry::prepare_pipeline(registry::select(
        providers,registry::Method{{"phase-one-priority-tie"},"1"},*program,requirements));
    out << "{\"graph_id\":\"phase-one-priority-tie/one-row-five-variable-v1\",\"status\":\"";
    const auto* pipeline = std::get_if<registry::PreparedPipeline<registry::LPPort>>(&prepared);
    if (!pipeline) {
        out << "incompatible\",\"first_unmet\":{\"field\":\"provider.prepare\",\"reason\":\"concrete LP rejected\"}}";
        return;
    }
    auto workspace = std::get<0>(pipeline->create());
    const auto result = workspace->run({});
    const auto* completed = std::get_if<ProgramResult>(&result);
    const bool solved = completed && completed->termination == Termination::completed && completed->primal;
    out << (solved ? "admitted" : "incompatible") << "\",\"provider\":{\"id\":\"phase-one-priority-tie\","
        << "\"version\":\"1\",\"actual\":\"phase-one-priority-tie\"},"
        << "\"profile\":{\"rows\":1,\"variables\":5,\"structural_priorities\":[0,1,2,3,4],"
        << "\"assurance\":\"numerical\",\"terminal_optimizer\":\"not_used\"},"
        << "\"attempt\":\"" << (solved ? "completed" : "incomplete") << "\",\"first_unmet\":";
    if (solved) out << "null}";
    else out << "{\"field\":\"phase_one.solve\",\"reason\":\"priority-tie feasibility solve did not complete\"}}";
}

void emit_rejection(std::ostream& out, const registry::Rejection& rejection) {
    out << "{\"field\":\"";
    if (!rejection.diagnostics.empty()) out << escape(rejection.diagnostics.front().field);
    out << "\",\"reason\":\"";
    if (!rejection.diagnostics.empty()) out << escape(rejection.diagnostics.front().explanation);
    out << "\"}";
}

void emit_candidate(std::ostream& out, const geometry::HullReducerCatalogue& catalogue,
        const geometry::HullCandidateGraph& graph) {
    const geometry::PointCloud fixture{{"vertex-square-2d-v1"},
        {{0,0},{1,0},{1,1},{0,1},{0.5,0.5}}};
    out << "{\"graph_id\":\"" << escape(graph.id) << "\",\"active_roles\":{"
        << "\"vertex_reducer\":{\"id\":\"" << escape(graph.vertex_reducer.id.value)
        << "\",\"version\":\"" << escape(graph.vertex_reducer.version) << "\"},"
        << "\"vertex_lp_provider\":{\"id\":\"" << escape(graph.vertex_lp.id.value)
        << "\",\"version\":\"" << escape(graph.vertex_lp.version) << "\"},"
        << "\"terminal_optimizer\":\"not_used\"},";
    auto prepared = geometry::prepare_hull_candidate(catalogue,graph,fixture);
    if (const auto* rejection = std::get_if<registry::Rejection>(&prepared)) {
        out << "\"status\":\"incompatible\",\"first_unmet\":";
        emit_rejection(out,*rejection);
        out << ",\"attempt\":\"not_run\"}";
        return;
    }
    auto execution = geometry::run_hull_candidate(
        std::get<geometry::PreparedHullCandidate>(std::move(prepared)));
    out << "\"status\":\"admitted\",\"first_unmet\":null,\"prepared_providers\":[";
    for (std::size_t i = 0; i < execution.prepared_providers.size(); ++i) {
        if (i) out << ',';
        const auto& provider = execution.prepared_providers[i];
        out << "{\"port\":\"" << escape(provider.port) << "\",\"requested\":\""
            << escape(provider.requested.id.value) << "\",\"actual\":\""
            << escape(provider.actual ? provider.actual->id.value : "unresolved") << "\",\"version\":\""
            << escape(provider.actual ? provider.actual->version : "unresolved") << "\"}";
    }
    const auto* reduction = std::get_if<geometry::HullReduction>(&execution.reduction);
    const std::set<std::size_t> expected{0,1,2,3};
    const bool exact_fixture = reduction && reduction->status == geometry::ReductionStatus::complete &&
        std::set<std::size_t>(reduction->retained.begin(),reduction->retained.end()) == expected;
    out << "],\"outer_lp_runner_queries\":[";
    for (std::size_t i = 0; i < execution.outer_lp_runner_queries.size(); ++i) {
        if (i) out << ',';
        const auto& query = execution.outer_lp_runner_queries[i];
        if (const auto* completed = std::get_if<registry::LPQueryCompleted>(&query)) {
            out << "{\"status\":\"completed\",\"requested\":\""
                << escape(completed->provider.requested.id.value) << "\",\"actual\":\""
                << escape(completed->provider.actual ? completed->provider.actual->id.value : "unresolved")
                << "\",\"version\":\""
                << escape(completed->provider.actual ? completed->provider.actual->version : "unresolved") << "\"}";
        } else if (const auto* rejected = std::get_if<registry::LPQueryRejected>(&query)) {
            out << "{\"status\":\"rejected\",\"request\":\""
                << escape(rejected->request.program.value) << "\",\"module_tuple\":{\"port\":\""
                << escape(rejected->rejection.provenance.port) << "\",\"requested\":{\"id\":\""
                << escape(rejected->rejection.provenance.requested.id.value) << "\",\"version\":\""
                << escape(rejected->rejection.provenance.requested.version.value_or("any")) << "\"},\"actual\":";
            if (rejected->rejection.provenance.actual)
                out << "{\"id\":\"" << escape(rejected->rejection.provenance.actual->id.value)
                    << "\",\"version\":\"" << escape(rejected->rejection.provenance.actual->version) << "\"}";
            else out << "null";
            out << "},\"first_unmet\":{";
            if (rejected->rejection.diagnostics.empty()) out << "\"field\":\"unknown\",\"reason\":\"no diagnostic was returned\"";
            else out << "\"field\":\"" << escape(rejected->rejection.diagnostics.front().field)
                << "\",\"reason\":\"" << escape(rejected->rejection.diagnostics.front().explanation) << "\"";
            out << "}}";
        } else if (const auto* unsupported = std::get_if<registry::LPQuerySolverUnsupported>(&query)) {
            out << "{\"status\":\"unsupported\",\"provider\":\""
                << escape(unsupported->provider.actual ? unsupported->provider.actual->id.value :
                    unsupported->provider.requested.id.value) << "\",\"first_unmet\":{";
            if (unsupported->diagnostics.empty()) out << "\"field\":\"unknown\",\"reason\":\"no diagnostic was returned\"";
            else out << "\"field\":\"" << escape(unsupported->diagnostics.front().field)
                << "\",\"reason\":\"" << escape(unsupported->diagnostics.front().explanation) << "\"";
            out << "}}";
        } else if (const auto* not_run = std::get_if<registry::LPQueryNotRun>(&query)) {
            out << "{\"status\":\"not_run\",\"provider\":\""
                << escape(not_run->provider.requested.id.value) << "\"}";
        } else {
            const auto& stopped = std::get<registry::LPQueryStopped>(query);
            out << "{\"status\":\"stopped\",\"request\":\""
                << escape(stopped.request.program.value) << "\"}";
        }
    }
    out << "],\"attempt\":\"" << (exact_fixture ? "completed" : "incomplete")
        << "\",\"execution_first_unmet\":";
    const registry::LPQueryRejected* first_query_rejection = nullptr;
    for (const auto& query : execution.outer_lp_runner_queries) {
        if (const auto* rejected = std::get_if<registry::LPQueryRejected>(&query)) {
            first_query_rejection = rejected;
            break;
        }
    }
    if (!first_query_rejection) out << "null";
    else {
        const auto& rejection = first_query_rejection->rejection;
        out << "{\"request\":\"" << escape(first_query_rejection->request.program.value)
            << "\",\"module_tuple\":{\"requested\":\"" << escape(rejection.provenance.requested.id.value)
            << "\",\"actual\":\"" << escape(rejection.provenance.actual ? rejection.provenance.actual->id.value : "unresolved")
            << "\"},\"field\":\"" << (rejection.diagnostics.empty() ? "unknown" :
                escape(rejection.diagnostics.front().field)) << "\",\"reason\":\""
            << (rejection.diagnostics.empty() ? "no diagnostic was returned" :
                escape(rejection.diagnostics.front().explanation)) << "\"}";
    }
    out << ",\"reducer_metrics\":";
    if (!reduction) out << "null";
    else {
        out << '{';
        bool metric = false;
        auto field = [&](std::string_view name, std::size_t value) {
            if (metric) out << ',';
            metric = true;
            out << '"' << name << "\":" << value;
        };
        if (reduction->basis_reuse) {
            field("captured_basis_solves",reduction->basis_reuse->basis_solves);
            field("certified_bulk_removals",reduction->basis_reuse->bulk_removals);
        }
        if (reduction->recursive) {
            field("recursive_leaf_lp_calls",reduction->recursive->leaf_lp_calls);
            field("recursive_merge_lp_calls",reduction->recursive->merge_lp_calls);
        }
        if (reduction->itis17_a43)
            field("a43_final_recheck_calls",reduction->itis17_a43->final_recheck_calls);
        if (reduction->itis17_a43_paper) {
            field("a43_paper_candidate_solves",reduction->itis17_a43_paper->candidate_solves);
            field("a43_paper_final_recheck_calls",reduction->itis17_a43_paper->final_recheck_calls);
        }
        if (reduction->itis17_a44) {
            field("a44_incremental_membership_calls",reduction->itis17_a44->incremental_membership_calls);
            field("a44_final_recheck_calls",reduction->itis17_a44->final_recheck_calls);
        }
        if (reduction->grouped)
            field("grouped_candidates",reduction->grouped->grouped_candidates);
        out << '}';
    }
    out << ",\"fixture_expected_retained\":[0,1,2,3],\"retained\":[";
    if (reduction) for (std::size_t i = 0; i < reduction->retained.size(); ++i) {
        if (i) out << ',';
        out << reduction->retained[i];
    }
    out << "]}";
}

void emit_conversion_candidates(std::ostream& out) {
    out << '[';
#if CSL_CATALOGUE_HAS_QHULL && CSL_CATALOGUE_HAS_HIGHS
    auto lp_result = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(lp_result))
        throw std::runtime_error("HiGHS registration for Qhull profile unavailable");
    auto converter_result = adapters::polyhedral::make_qhull_registration(
        std::get<registry::Registration<registry::LPPort>>(std::move(lp_result)));
    if (!std::holds_alternative<registry::Registration<registry::ConversionPort>>(converter_result))
        throw std::runtime_error("Qhull converter registration unavailable");
    registry::Registry<registry::ConversionPort> conversions;
    const auto registration = std::get<registry::Registration<registry::ConversionPort>>(std::move(converter_result));
    if (conversions.add(registration)) throw std::runtime_error("Qhull converter registration rejected");
    const auto matrix = take(numeric::snapshot(Matrix{4,2,{1,0,-1,0,0,1,0,-1}}));
    const auto bounds = take(numeric::snapshot_vector(Vector{1,1,1,1}));
    const auto empty_matrix = take(numeric::snapshot(Matrix{0,2,{}}));
    const auto empty_vector = take(numeric::snapshot_vector(Vector{}));
    const auto h = sets::make_h({{"catalogue-conversion-square-v1"},2,{"x","y"}},
        {matrix,bounds,empty_matrix,empty_vector});
    if (!std::holds_alternative<sets::SetData>(h)) throw std::runtime_error("Qhull H input profile invalid");
    ConversionRequest request{{{"catalogue-conversion-problem"},{"square-h-to-v"},{"exact-square"}},
        std::get<sets::SetData>(h).as_handle(),{"csl.polyhedron.v"},Assurance::numerical};
    registry::Requirements required;
    required.output = {{"csl.polyhedron.v"},Assurance::numerical,SetRelation::equivalent,{},{}};
    const auto prepared = registry::prepare_pipeline(registry::select(conversions,
        {{"csl.conversion.qhull"},{}},request,required));
    const auto* pipeline = std::get_if<registry::PreparedPipeline<registry::ConversionPort>>(&prepared);
    if (!pipeline) {
        out << "{\"graph_id\":\"supporting/qhull-square-h-to-v-v1\",\"status\":\"incompatible\","
            << "\"first_unmet\":{\"field\":\"converter.prepare\",\"reason\":\"concrete conversion request rejected\"}}]";
        return;
    }
    auto workspace = std::get<0>(pipeline->create());
    const auto converted = workspace->run(ExecutionContext{});
    const auto* operation = std::get_if<OperationResult>(&converted);
    bool four_vertices = false;
    if (operation) {
        const auto data = sets::from_handle(operation->output);
        if (const auto* set = std::get_if<sets::SetData>(&data)) {
            const auto repr = set->representation();
            if (const auto* v = std::get_if<sets::VRepresentation>(&repr))
                four_vertices = v->vertices.rows() == 4;
        }
    }
    out << "{\"graph_id\":\"supporting/qhull-square-h-to-v-v1\",\"status\":\""
        << (four_vertices ? "admitted" : "incompatible")
        << "\",\"active_roles\":{\"converter\":{\"id\":\"" << escape(registration.identity.id.value)
        << "\",\"version\":\"" << escape(registration.identity.version)
        << "\"},\"lp_provider\":{\"id\":\"csl.lp.highs\",\"version\":\"1.1.0+highs.1.11.0\"},"
        << "\"vertex_lp_provider\":\"not_used\",\"terminal_optimizer\":\"not_used\"},"
        << "\"input_dimension\":2,\"input_representation\":\"csl.polyhedron.h\","
        << "\"output_representation\":\"csl.polyhedron.v\",\"relation\":\"equivalent\","
        << "\"attempt\":\"" << (four_vertices ? "completed" : "incomplete") << "\",\"output_vertices\":"
        << (four_vertices ? 4 : 0) << ",\"first_unmet\":";
    if (four_vertices) out << "null}";
    else out << "{\"field\":\"qhull.output\",\"reason\":\"square conversion did not return four vertices\"}}]";
#else
    out << "{\"graph_id\":\"supporting/qhull-square-h-to-v-v1\",\"status\":\"backend_unavailable\","
        << "\"module_tuple\":{\"converter\":\"csl.conversion.qhull\",\"lp_provider\":\"csl.lp.highs\"},"
        << "\"first_unmet\":{\"field\":\"build.CSL_ENABLE_QHULL\",\"reason\":\"Qhull conversion profile requires compiled Qhull and HiGHS registrations.\"}}";
#endif
    out << ']';
}

void emit_approximation_candidates(std::ostream& out) {
    const auto vertices = take(numeric::snapshot(Matrix{4,2,{-1,-1,1,-1,1,1,-1,1}}));
    const auto rays = take(numeric::snapshot(Matrix{0,2,{}}));
    const auto source = sets::make_v({{"catalogue-approximation-square-v1"},2,{"x","y"}},
        {vertices,rays});
    if (!std::holds_alternative<sets::SetData>(source)) throw std::runtime_error("box approximation V profile invalid");
    ApproximationRequest request{
        {{"catalogue-approximation-problem"},{"square-v-to-box"},{"square-reference"}},
        std::get<sets::SetData>(source).as_handle(),{"csl.polyhedron.h"},SetRelation::outer,4,Assurance::numerical};
    registry::Registry<registry::ApproximationPort> approximations;
    const registry::Method method{{"csl.approximation.box"},"1"};
    if (approximations.add(geometry::approximation::make_box_registration({"catalogue-box"})))
        throw std::runtime_error("box approximation registration rejected");
    const auto outcome = geometry::approximation::run_registered(
        approximations,method,request,ExecutionContext{});
    const auto* enclosed = std::get_if<geometry::approximation::EnclosedApproximation>(&outcome);
    out << "[{\"graph_id\":\"supporting/box-outer-v-to-h-square-v1\",\"status\":\""
        << (enclosed ? "admitted" : "incompatible")
        << "\",\"active_roles\":{\"approximation\":{\"id\":\"csl.approximation.box\",\"version\":\"1\"},"
        << "\"vertex_lp_provider\":\"not_used\",\"terminal_optimizer\":\"not_used\"},"
        << "\"input_dimension\":2,\"input_representation\":\"csl.polyhedron.v\","
        << "\"output_representation\":\"csl.polyhedron.h\",\"relation\":\"outer\","
        << "\"assurance\":\"numerical\",\"size_budget\":4,\"attempt\":\""
        << (enclosed ? "completed" : "incomplete") << "\",\"first_unmet\":";
    if (enclosed) out << "null}]";
    else out << "{\"field\":\"approximation.prepare_or_run\",\"reason\":\"box route did not return checked enclosure evidence\"}}]";
}

void emit_terminal_optimizer_candidates(std::ostream& out) {
    out << '[';
#if CSL_CATALOGUE_HAS_HIGHS_CONVEX
    auto lp_registration_result = adapters::lp::make_highs_registration();
    auto convex_registration_result = adapters::convex::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(lp_registration_result) ||
        !std::holds_alternative<registry::Registration<registry::ConvexPort>>(convex_registration_result))
        throw std::runtime_error("HiGHS terminal optimizer dependencies unavailable");
    auto lp_registration = std::get<registry::Registration<registry::LPPort>>(std::move(lp_registration_result));
    auto convex_registration = std::get<registry::Registration<registry::ConvexPort>>(std::move(convex_registration_result));
    const auto lp_identity = registry::Method{lp_registration.identity.id,lp_registration.identity.version};
    const auto convex_identity = registry::Method{convex_registration.identity.id,convex_registration.identity.version};
    registry::Registry<registry::LPPort> lps;
    registry::Registry<registry::ConvexPort> convexes;
    if (lps.add(std::move(lp_registration)) || convexes.add(std::move(convex_registration)))
        throw std::runtime_error("terminal optimizer provider registration failed");
    registry::Requirements required;
    required.output.representation = {"csl.program-result.v1"};
    auto lp_provider = take_variant(registry::prepare_provider(registry::select_provider(lps,lp_identity,required)),
        "terminal optimizer LP provider prepare");
    auto convex_provider = take_variant(registry::prepare_provider(registry::select_provider(convexes,convex_identity,required)),
        "terminal optimizer convex provider prepare");
    synthesis::TerminalOptimizer optimizer(std::move(lp_provider),std::move(convex_provider));
    auto problem = ts01_problem();
    FamilyRequest family;
    family.objective = problem.identity();
    family.profile = "ts01_exact_integrator";
    family.representation = {"csl.polyhedron.h"};
    const auto context = ExecutionContext{std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),
        {},{},{1e-8,1e-8},"catalogue-terminal-optimizer"};
    const auto terminal_set = sets::from_handle(interval("catalogue-terminal-slice"));
    const auto* slice = std::get_if<sets::SetData>(&terminal_set);
    if (!slice) throw std::runtime_error("terminal optimizer slice construction failed");
    const auto result = optimizer.solve(problem,family,{problem.identity(),*slice},context);
    bool relation_has_one = false;
    if (result.relation) {
        const auto representation = result.relation->representation();
        if (const auto* h = std::get_if<sets::HRepresentation>(&representation)) {
            relation_has_one = true;
            for (std::size_t i = 0; i < h->inequalities.rows(); ++i)
                relation_has_one &= h->inequalities(i,0) <= h->upper_bounds[i] + 1e-8;
            for (std::size_t i = 0; i < h->equalities.rows(); ++i)
                relation_has_one &= std::abs(h->equalities(i,0) - h->equality_values[i]) <= 1e-8;
        }
    }
    const bool completed = result.termination == Termination::completed &&
        result.outcome == MathematicalOutcome::optimal && result.optimization && result.optimization->primal &&
        result.optimization->primal->size() == 1 && std::abs(result.optimization->primal->front()-1.0) <= 1e-6 &&
        relation_has_one;
    out << "{\"graph_id\":\"supporting/terminal-optimizer-ts01-profile-v1\","
        << "\"status\":\"" << (completed ? "admitted" : "incompatible")
        << "\",\"active_roles\":{\"terminal_minimizer\":\"csl::synthesis::TerminalOptimizer::solve\","
        << "\"terminal_lp_provider\":{\"id\":\"" << escape(lp_identity.id.value)
        << "\",\"version\":\"" << escape(lp_identity.version.value()) << "\"},"
        << "\"terminal_optimizer_provider\":{\"id\":\"" << escape(convex_identity.id.value)
        << "\",\"version\":\"" << escape(convex_identity.version.value())
        << "\"},\"vertex_lp_provider\":\"not_used\"},"
        << "\"profile\":{\"objective_id\":\"" << escape(problem.identity().value)
        << "\",\"state_dimension\":1,\"terminal_slice\":\"[0,1]\"},"
        << "\"candidate\":" << (result.optimization && result.optimization->primal ? result.optimization->primal->front() : 0)
        << ",\"expected_candidate\":1,\"optimal_relation_contains_candidate\":"
        << (relation_has_one ? "true" : "false") << ",\"attempt\":\""
        << (completed ? "completed" : "incomplete") << "\",\"first_unmet\":";
    if (completed) out << "null}";
    else out << "{\"field\":\"terminal.optimizer.solve\",\"reason\":\"TerminalOptimizer did not return the expected admitted optimum relation.\"}}";
#else
    out << "{\"graph_id\":\"supporting/terminal-optimizer-ts01-profile-v1\","
        << "\"status\":\"backend_unavailable\",\"module_tuple\":{\"terminal_optimizer_provider\":\"csl.convex.highs\"},"
        << "\"first_unmet\":{\"field\":\"build.CSL_ENABLE_HIGHS\",\"reason\":\"HiGHS convex provider is not compiled in this build.\"}}";
#endif
    out << ']';
}

void emit_geometric_reference_candidates(std::ostream& out) {
    const std::vector<Vector> points{{0,0},{1,0},{1,1},{0,1},{0.5,0.5}};
    const auto quick = geometry::quickhull_2d(points);
    const std::vector<Vector> four_dimensional{{0,0,0,0},{1,0,0,0},{0,1,0,0}};
    const auto invalid_quick = geometry::quickhull_2d(four_dimensional);
    const auto legacy = geometry::legacy_btulshor::kpabep(points);
    const geometry::legacy_btulshor::ReachRequest reach_request{
        .a={2,2,{1,0,0,1}},.b={2,1,{1,2}},
        .initial_points={{0,0},{1,1}},.control_points={{0},{1}}};
    const auto reach = geometry::legacy_btulshor::reach(reach_request);
    out << "[";
    if (const auto* result = std::get_if<geometry::QuickHull2D>(&quick)) {
        out << "{\"graph_id\":\"geometry/quickhull2d/square-v1\",\"status\":\"admitted\","
            << "\"identity\":\"csl::geometry::quickhull_2d\",\"dimension\":2,"
            << "\"role\":\"geometric hull reference; no LP provider\",\"active_roles\":{"
            << "\"vertex_lp_provider\":\"not_used\",\"terminal_optimizer\":\"not_used\"},\"retained\":[";
        for (std::size_t i=0;i<result->vertex_indices.size();++i) { if (i) out << ','; out << result->vertex_indices[i]; }
        out << "],\"attempt\":\"completed\",\"first_unmet\":null},";
    } else {
        out << "{\"graph_id\":\"geometry/quickhull2d/square-v1\",\"status\":\"incompatible\","
            << "\"first_unmet\":{\"field\":\"points.dimension\",\"reason\":\"2D reference fixture rejected\"}},";
    }
    out << "{\"graph_id\":\"geometry/quickhull2d/point-cloud-dimension-4-v1\",\"status\":\""
        << (std::holds_alternative<Diagnostics>(invalid_quick) ? "incompatible" : "admitted")
        << "\",\"input_dimension\":4,\"active_roles\":{\"vertex_lp_provider\":\"not_used\","
        << "\"terminal_optimizer\":\"not_used\"},\"first_unmet\":";
    if (const auto* diagnostics=std::get_if<Diagnostics>(&invalid_quick); diagnostics && !diagnostics->empty())
        out << "{\"field\":\"" << escape(diagnostics->front().field) << "\",\"reason\":\""
            << escape(diagnostics->front().explanation) << "\"}}";
    else out << "null}";
    out << ',';
    if (const auto* result=std::get_if<geometry::legacy_btulshor::KpabepResult>(&legacy)) {
        out << "{\"graph_id\":\"legacy-btulshor/kpabep/source-v1\",\"status\":\"admitted\","
            << "\"source_identity\":\"" << geometry::legacy_btulshor::source_kpabep_port().id
            << "\",\"retained_indices\":[";
        for (std::size_t i=0;i<result->retained_indices.size();++i) { if (i) out << ','; out << result->retained_indices[i]; }
        out << "],\"modif_calls\":" << result->modif_calls << ",\"attempt\":\"completed\",\"first_unmet\":null},";
    } else out << "{\"graph_id\":\"legacy-btulshor/kpabep/source-v1\",\"status\":\"implementation_missing\","
        << "\"first_unmet\":{\"field\":\"kpabep.execution\",\"reason\":\"source fixture did not complete\"}},";
    if (const auto* result=std::get_if<geometry::legacy_btulshor::ReachResult>(&reach)) {
        out << "{\"graph_id\":\"legacy-btulshor/reach/source-v1\",\"status\":\"admitted\","
            << "\"source_identity\":\"" << geometry::legacy_btulshor::reach_source_id
            << "\",\"kpabep_source_identity\":\"" << geometry::legacy_btulshor::source_kpabep_port().id
            << "\",\"modif_source_identity\":\"" << geometry::legacy_btulshor::source_modif_port().id
            << "\",\"point_count\":" << result->points.size() << ",\"kpabep_calls\":"
            << result->kpabep_calls << ",\"modif_calls\":" << result->modif_calls
            << ",\"attempt\":\"completed\",\"first_unmet\":null}]";
    } else out << "{\"graph_id\":\"legacy-btulshor/reach/source-v1\",\"status\":\"implementation_missing\","
        << "\"first_unmet\":{\"field\":\"reach.execution\",\"reason\":\"source fixture did not complete\"}}]";
}
}

int main(int argc, char** argv) try {
    std::string inventory_path;
    if (argc == 3 && std::string_view(argv[1]) == "--inventory") inventory_path = argv[2];
    else if (argc != 1) throw std::runtime_error("usage: csl_module_composition_catalogue [--inventory path]");

    const auto providers = compiled_lp_providers();
    std::cout << "{\"schema\":\"csl.module-composition-output/1\","
        << "\"invocation_observation\":\"outer RegisteredLPQueryRunner records plus reducer-specific internal metrics; preparation is separate\","
        << "\"native_probe_scope\":[\"vertex reducers x compiled LP providers on the finite square profile\","
        << "\"TS01 strategy registry on the exact two-step scalar integrator profile\","
        << "\"finite-action nominal profile over exact, box, zonotope, parallelotope and ellipsoid routes\"],"
        << "\"profile\":\"vertex-square-2d-v1\","
        << "\"compiled_backends\":{\"highs\":"
        << (CSL_CATALOGUE_HAS_HIGHS ? "true" : "false")
        << ",\"phase_one\":true,\"qhull\":"
        << (CSL_CATALOGUE_HAS_QHULL ? "true" : "false") << "},\"inventory\":";
    if (inventory_path.empty()) std::cout << "null";
    else std::cout << read_file(inventory_path);
    std::cout << ",\"candidates\":[";
    bool first = true;
    for (const auto& provider : providers) {
        auto catalogue = geometry::make_hull_reducer_catalogue(provider);
        for (const auto& graph : geometry::enumerate_hull_candidates(catalogue,2)) {
            if (!first) std::cout << ',';
            first = false;
            emit_candidate(std::cout,catalogue,graph);
        }
    }
    std::cout << "],\"priority_tie_candidates\":[";
    {
        auto catalogue = geometry::make_hull_reducer_catalogue(priority_tie_provider());
        const auto graphs = geometry::enumerate_hull_candidates(catalogue,2);
        for (std::size_t i = 0; i < graphs.size(); ++i) {
            if (i) std::cout << ',';
            emit_candidate(std::cout,catalogue,graphs[i]);
        }
    }
    std::cout << "],\"backend_unavailable_candidates\":[";
    bool unavailable_first = true;
#if !CSL_CATALOGUE_HAS_HIGHS
    for (const auto& reducer : geometry::make_hull_reducer_catalogue(priority_tie_provider()).reducer_identities()) {
        if (!unavailable_first) std::cout << ',';
        unavailable_first = false;
        std::cout << "{\"graph_id\":\"vertex-square-2d-v1/" << escape(reducer.id.value)
            << "/csl.lp.highs@1.1.0+highs.1.11.0\",\"status\":\"backend_unavailable\","
            << "\"module_tuple\":{\"vertex_reducer\":\"" << escape(reducer.id.value)
            << "\",\"vertex_lp_provider\":\"csl.lp.highs\",\"version\":\"1.1.0+highs.1.11.0\"},"
            << "\"first_unmet\":{\"field\":\"build.CSL_ENABLE_HIGHS\",\"reason\":\"HiGHS provider is not compiled in this build.\"}}";
    }
#endif
#if !CSL_CATALOGUE_HAS_QHULL
    if (!unavailable_first) std::cout << ',';
    std::cout << "{\"graph_id\":\"supporting/qhull-conversion/build-profile-v1\","
        << "\"status\":\"backend_unavailable\",\"module_tuple\":{\"converter\":\"Qhull\","
        << "\"representation\":\"polyhedron.v-to-polyhedron.h\"},\"first_unmet\":{"
        << "\"field\":\"build.CSL_ENABLE_QHULL\",\"reason\":\"Qhull converter target is not compiled in this build.\"}}";
#endif
    std::cout << "],\"representation_candidates\":";
    emit_nominal_profiles(std::cout);
    std::cout << ",\"priority_tie_lp_profile\":";
    emit_priority_tie_lp_profile(std::cout);
    std::cout << ",\"supporting_operation_candidates\":";
    emit_conversion_candidates(std::cout);
    std::cout << ",\"generator_operation_candidates\":";
    emit_generator_operation_candidates(std::cout);
    std::cout << ",\"approximation_candidates\":";
    emit_approximation_candidates(std::cout);
    std::cout << ",\"geometric_reference_candidates\":";
    emit_geometric_reference_candidates(std::cout);
    std::cout << ",\"terminal_optimizer_candidates\":";
    emit_terminal_optimizer_candidates(std::cout);
    std::cout << ",\"controller_candidates\":";
    emit_ts01_candidates(std::cout);
    std::cout << "}\n";
    return 0;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
