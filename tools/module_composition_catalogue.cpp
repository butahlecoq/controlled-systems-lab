#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/composition_catalogue.hpp>
#include <csl/optimization/phase_one.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <csl/registry/strategy_catalogue.hpp>
#include <csl/sets/data.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>

#include <algorithm>
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

template<class T> T take(numeric::Result<T> result) {
    if (!std::holds_alternative<T>(result)) throw std::runtime_error("numeric snapshot failed");
    return std::get<T>(std::move(result));
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
            out << "{\"status\":\"rejected\",\"first_unmet\":\""
                << (rejected->rejection.diagnostics.empty() ? "unknown" :
                    escape(rejected->rejection.diagnostics.front().field)) << "\"}";
        } else if (const auto* unsupported = std::get_if<registry::LPQuerySolverUnsupported>(&query)) {
            out << "{\"status\":\"unsupported\",\"first_unmet\":\""
                << (unsupported->diagnostics.empty() ? "unknown" :
                    escape(unsupported->diagnostics.front().field)) << "\"}";
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
        << "\",\"reducer_metrics\":";
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
}

int main(int argc, char** argv) try {
    std::string inventory_path;
    if (argc == 3 && std::string_view(argv[1]) == "--inventory") inventory_path = argv[2];
    else if (argc != 1) throw std::runtime_error("usage: csl_module_composition_catalogue [--inventory path]");

    const auto providers = compiled_lp_providers();
    std::cout << "{\"schema\":\"csl.module-composition-output/1\","
        << "\"invocation_observation\":\"outer RegisteredLPQueryRunner records plus reducer-specific internal metrics; preparation is separate\","
        << "\"native_probe_scope\":[\"vertex reducers x compiled LP providers on the finite square profile\","
        << "\"TS01 strategy registry on the exact two-step scalar integrator profile\"],"
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
    std::cout << "],\"controller_candidates\":";
    emit_ts01_candidates(std::cout);
    std::cout << "}\n";
    return 0;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
