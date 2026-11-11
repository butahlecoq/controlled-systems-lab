#include <csl/geometry/composition_catalogue.hpp>

#include <csl/geometry/basis_reuse_reducer.hpp>

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace csl::geometry {
namespace {

void add_reducer(registry::Registry<registry::HullReducerPort>& registry,
        registry::Registration<registry::HullReducerPort> entry) {
    if (const auto rejection = registry.add(std::move(entry)))
        throw std::logic_error("Built-in hull catalogue contains a duplicate or invalid registration");
}

std::string graph_id(const HullCandidateGraph& graph) {
    return "vertex-cloud-d" + std::to_string(graph.input_dimension) + "-v1/" + graph.vertex_reducer.id.value + "@" +
        graph.vertex_reducer.version + "/" + graph.vertex_lp.id.value + "@" +
        graph.vertex_lp.version;
}

registry::Rejection rejected(std::string requested_id, std::string requested_version,
        std::string field, std::string reason) {
    return {{registry::HullReducerPort::name,
        {ModuleId{std::move(requested_id)},std::move(requested_version)},{}},
        {{DiagnosticCode::unsupported,std::move(field),std::move(reason)}}};
}

bool same_graph(const HullCandidateGraph& left, const HullCandidateGraph& right) {
    return left.id == right.id && left.vertex_reducer.id == right.vertex_reducer.id &&
        left.vertex_reducer.version == right.vertex_reducer.version &&
        left.vertex_lp.id == right.vertex_lp.id && left.vertex_lp.version == right.vertex_lp.version &&
        left.input_dimension == right.input_dimension &&
        left.representation == right.representation && left.controller == right.controller &&
        left.supporting_operations == right.supporting_operations &&
        left.terminal_optimizer == right.terminal_optimizer && left.request_profile == right.request_profile;
}

} // namespace

HullReducerCatalogue make_hull_reducer_catalogue(registry::Registration<registry::LPPort> lp) {
    registry::Registry<registry::HullReducerPort> reducers;
    add_reducer(reducers,make_lp_hull_reducer_registration());
    add_reducer(reducers,make_basis_reuse_hull_reducer_registration(lp));
    add_reducer(reducers,make_ordered_hull_reducer_registration());
    add_reducer(reducers,make_itis17_a43_hull_reducer_registration());
    add_reducer(reducers,make_itis17_a43_paper_hull_reducer_registration(A43PivotRule::phase_one_order));
    add_reducer(reducers,make_itis17_a43_paper_hull_reducer_registration(A43PivotRule::largest_norm_tie));
    add_reducer(reducers,make_itis17_a44_hull_reducer_registration());
    add_reducer(reducers,make_itis17_a44_paper_hull_reducer_registration());
    add_reducer(reducers,make_grouped_hull_reducer_registration());
    add_reducer(reducers,make_recursive_hull_reducer_registration(lp));
    return HullReducerCatalogue{std::move(reducers),std::move(lp)};
}

std::vector<HullCandidateGraph> enumerate_hull_candidates(const HullReducerCatalogue& catalogue,
        std::size_t input_dimension) {
    auto reducers = catalogue.reducer_identities();
    std::sort(reducers.begin(),reducers.end(),[](const auto& left,const auto& right) {
        return left.id.value < right.id.value;
    });
    const auto lp = catalogue.vertex_lp_identity();
    std::vector<HullCandidateGraph> result;
    result.reserve(reducers.size());
    for (const auto& reducer : reducers) {
        HullCandidateGraph graph;
        graph.vertex_reducer = reducer;
        graph.vertex_lp = lp;
        graph.input_dimension = input_dimension;
        graph.request_profile = "finite-binary64-point-cloud-v1";
        graph.id = graph_id(graph);
        result.push_back(std::move(graph));
    }
    return result;
}

std::variant<PreparedHullCandidate,registry::Rejection> prepare_hull_candidate(
        const HullReducerCatalogue& catalogue, const HullCandidateGraph& graph,
        const PointCloud& request) {
    const auto candidates = enumerate_hull_candidates(catalogue,graph.input_dimension);
    const auto declared = std::find_if(candidates.begin(),candidates.end(),[&](const auto& candidate) {
        return candidate.id == graph.id;
    });
    if (declared == candidates.end() || !same_graph(*declared,graph))
        return rejected(graph.vertex_reducer.id.value,graph.vertex_reducer.version,
            "candidate.graph","Candidate is not in the canonical compiled hull catalogue");
    const bool invalid_point = std::any_of(request.points.begin(),request.points.end(),[&](const Vector& point) {
        return point.size() != graph.input_dimension ||
            std::any_of(point.begin(),point.end(),[](double coordinate) { return !std::isfinite(coordinate); });
    });
    if (request.problem.value.empty() || invalid_point)
        return rejected(graph.vertex_reducer.id.value,graph.vertex_reducer.version,
            "candidate.profile","The request must be a finite point cloud with the candidate's pinned dimension");

    auto reducer_preparation = registry::prepare_pipeline(registry::select(catalogue.reducers_,
        {graph.vertex_reducer.id,graph.vertex_reducer.version},request));
    if (const auto* rejection = std::get_if<registry::Rejection>(&reducer_preparation))
        return *rejection;

    registry::Registry<registry::LPPort> lp_registry;
    if (const auto rejection = lp_registry.add(catalogue.vertex_lp_))
        return *rejection;
    auto lp_preparation = registry::prepare_provider(registry::select_provider(lp_registry,
        {graph.vertex_lp.id,graph.vertex_lp.version}));
    if (const auto* rejection = std::get_if<registry::Rejection>(&lp_preparation))
        return *rejection;

    auto prepared_reducer = std::get<registry::PreparedPipeline<registry::HullReducerPort>>(
        std::move(reducer_preparation));
    auto prepared_lp = std::get<registry::PreparedProvider<registry::LPPort>>(std::move(lp_preparation));
    const auto reducer_provenance = prepared_reducer.provenance();
    std::vector<registry::Provenance> provenance{reducer_provenance.begin(),reducer_provenance.end()};
    provenance.push_back(prepared_lp.provenance());
    if (!provenance[0].actual || !provenance[1].actual ||
        provenance[0].actual->id != graph.vertex_reducer.id ||
        provenance[0].actual->version != graph.vertex_reducer.version ||
        provenance[1].actual->id != graph.vertex_lp.id ||
        provenance[1].actual->version != graph.vertex_lp.version)
        return rejected(graph.vertex_reducer.id.value,graph.vertex_reducer.version,
            "candidate.provider_identity","Prepared provider identity differs from the pinned candidate tuple");
    return PreparedHullCandidate{graph,std::move(prepared_reducer),std::move(prepared_lp),std::move(provenance)};
}

HullCandidateExecution run_hull_candidate(PreparedHullCandidate candidate,
        const ExecutionContext& context) {
    auto workspaces = candidate.reducer.create();
    registry::RegisteredLPQueryRunner runner(std::move(candidate.vertex_lp));
    auto reduction = std::get<0>(workspaces)->run_with(context,runner);
    return {std::move(candidate.graph),std::move(candidate.provenance),std::move(reduction),
        runner.records()};
}

} // namespace csl::geometry
