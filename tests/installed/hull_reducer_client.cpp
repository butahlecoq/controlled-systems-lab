#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/composition_catalogue.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <csl/geometry/basis_reuse_reducer.hpp>
#include <csl/registry/provider.hpp>
#include <algorithm>
#include <iostream>
#include <set>

int main() {
    using namespace csl;
    auto registration = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(registration))
        return 1;
    auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto lp_provider = [&]() -> std::optional<registry::PreparedProvider<registry::LPPort>> {
        registry::Registry<registry::LPPort> lp_registry;
        if (lp_registry.add(std::move(adapter)))
            return std::nullopt;
        registry::Requirements lp_requirements;
        lp_requirements.output.representation = {"csl.program-result.v1"};
        lp_requirements.output.assurance = Assurance::numerical;
        lp_requirements.output.completeness = registry::Completeness::unestablished;
        auto result = registry::prepare_provider(registry::select_provider(
            lp_registry, registry::Method{{"csl.lp.highs"}, std::nullopt}, lp_requirements));
        if (!std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(result))
            return std::nullopt;
        return std::get<registry::PreparedProvider<registry::LPPort>>(std::move(result));
    }();
    if (!lp_provider)
        return 2;
    registry::RegisteredLPQueryRunner lp(std::move(*lp_provider));

    registry::Registry<registry::HullReducerPort> hull_registry;
    if (hull_registry.add(geometry::make_lp_hull_reducer_registration()))
        return 3;
    const geometry::PointCloud cloud{{"installed-hull"},
                                     {{0, 0}, {1, 0}, {1, 1}, {0, 1}, {0.5, 0.5}}};
    auto catalogue_lp_result = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(catalogue_lp_result))
        return 18;
    auto catalogue = geometry::make_hull_reducer_catalogue(
        std::get<registry::Registration<registry::LPPort>>(std::move(catalogue_lp_result)));
    const auto candidates = geometry::enumerate_hull_candidates(catalogue, 2);
    if (candidates.size() != 10 || catalogue.reducer_identities().size() != 10)
        return 19;
    const auto lp_membership =
        std::find_if(candidates.begin(), candidates.end(), [](const auto &item) {
            return item.vertex_reducer.id.value == "csl.hull.lp-membership";
        });
    if (lp_membership == candidates.end())
        return 22;
    auto candidate = geometry::prepare_hull_candidate(catalogue, *lp_membership, cloud);
    if (const auto *rejected = std::get_if<registry::Rejection>(&candidate)) {
        if (!rejected->diagnostics.empty())
            std::cerr << rejected->diagnostics.front().field << ": "
                      << rejected->diagnostics.front().explanation << '\n';
        return 20;
    }
    auto execution = geometry::run_hull_candidate(
        std::get<geometry::PreparedHullCandidate>(std::move(candidate)));
    if (!std::holds_alternative<geometry::HullReduction>(execution.reduction))
        return 23;
    const auto &candidate_provenance = execution.prepared_providers;
    if (candidate_provenance.size() != 2 || !candidate_provenance[0].actual ||
        !candidate_provenance[1].actual ||
        candidate_provenance[0].actual->id != lp_membership->vertex_reducer.id ||
        candidate_provenance[1].actual->id != lp_membership->vertex_lp.id)
        return 21;
    const auto &candidate_reduction = std::get<geometry::HullReduction>(execution.reduction);
    if (candidate_reduction.status != geometry::ReductionStatus::complete ||
        std::set<std::size_t>(candidate_reduction.retained.begin(),
                              candidate_reduction.retained.end()) !=
            std::set<std::size_t>{0, 1, 2, 3} ||
        execution.outer_lp_runner_queries.empty())
        return 24;
    for (const auto &query : execution.outer_lp_runner_queries) {
        const auto *completed = std::get_if<registry::LPQueryCompleted>(&query);
        if (!completed || !completed->provider.actual ||
            completed->provider.actual->id != lp_membership->vertex_lp.id ||
            completed->provider.actual->version != lp_membership->vertex_lp.version)
            return 25;
    }

    auto hull_prepared_result = registry::prepare_pipeline(registry::select(
        hull_registry, registry::Method{{"csl.hull.lp-membership"}, std::nullopt}, cloud));
    if (!std::holds_alternative<registry::PreparedPipeline<registry::HullReducerPort>>(
            hull_prepared_result))
        return 4;
    auto hull_prepared = std::get<registry::PreparedPipeline<registry::HullReducerPort>>(
        std::move(hull_prepared_result));
    auto hull_workspaces = hull_prepared.create();
    auto result = std::get<0>(hull_workspaces)->run_with(ExecutionContext{}, lp);
    if (!std::holds_alternative<geometry::HullReduction>(result))
        return 5;
    const auto &reduction = std::get<geometry::HullReduction>(result);
    if (reduction.status != geometry::ReductionStatus::complete || reduction.retained.size() != 4 ||
        reduction.removed.size() != 1 || reduction.lp_calls != 5 || lp.records().size() != 5)
        return 6;
    for (const auto &query : lp.records()) {
        const auto *executed = std::get_if<registry::LPQueryCompleted>(&query);
        if (!executed || executed->provider.actual->id.value != "csl.lp.highs")
            return 7;
    }

    // Exercise the installed OPT-06 public header and its phase-one dependency
    // through the exported CSL::hull target. The same registered LP workspace
    // remains available for the reducer's conservative fallback path.
    registry::Registry<registry::HullReducerPort> basis_registry;
    if (basis_registry.add(geometry::make_basis_reuse_hull_reducer_registration()))
        return 8;
    auto basis_prepared_result = registry::prepare_pipeline(registry::select(
        basis_registry, registry::Method{{"csl.hull.phase-one-basis-bulk"}, std::nullopt}, cloud));
    if (!std::holds_alternative<registry::PreparedPipeline<registry::HullReducerPort>>(
            basis_prepared_result))
        return 9;
    auto basis_prepared = std::get<registry::PreparedPipeline<registry::HullReducerPort>>(
        std::move(basis_prepared_result));
    auto basis_workspaces = basis_prepared.create();
    auto basis_result = std::get<0>(basis_workspaces)->run_with(ExecutionContext{}, lp);
    if (!std::holds_alternative<geometry::HullReduction>(basis_result))
        return 10;
    const auto &basis_reduction = std::get<geometry::HullReduction>(basis_result);
    if (basis_reduction.status != geometry::ReductionStatus::complete ||
        !basis_reduction.basis_reuse || basis_reduction.basis_reuse->basis_solves != 1 ||
        basis_reduction.retained.size() != 4)
        return 11;

    auto recursive_provider_result = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(
            recursive_provider_result))
        return 12;
    auto recursive_provider =
        std::get<registry::Registration<registry::LPPort>>(std::move(recursive_provider_result));
    registry::Registry<registry::HullReducerPort> recursive_registry;
    if (recursive_registry.add(
            geometry::make_recursive_hull_reducer_registration(recursive_provider)))
        return 13;
    auto recursive_prepared_result = registry::prepare_pipeline(registry::select(
        recursive_registry, registry::Method{{"csl.hull.recursive-split-merge"}, std::nullopt},
        cloud));
    if (!std::holds_alternative<registry::PreparedPipeline<registry::HullReducerPort>>(
            recursive_prepared_result))
        return 14;
    auto recursive_prepared = std::get<registry::PreparedPipeline<registry::HullReducerPort>>(
        std::move(recursive_prepared_result));
    auto recursive_workspaces = recursive_prepared.create();
    auto seed = optimization::make_linear_program(
        {{{"installed-hull"}, {"recursive-seed"}}, {}, 0.0, {0, 0, {0}, {}, {}}, {}, {}});
    if (!std::holds_alternative<LinearProgram>(seed))
        return 15;
    auto recursive_injected_lp = recursive_provider.factory(std::get<LinearProgram>(seed));
    auto recursive_result =
        std::get<0>(recursive_workspaces)->run_with(ExecutionContext{}, *recursive_injected_lp);
    if (!std::holds_alternative<geometry::HullReduction>(recursive_result))
        return 16;
    const auto &recursive_reduction = std::get<geometry::HullReduction>(recursive_result);
    if (!recursive_reduction.recursive || recursive_reduction.retained.size() != 4 ||
        recursive_reduction.recursive->leaf_nodes != 1)
        return 17;
    std::cout
        << "Installed hull client: canonical square and completed registered LP receipts passed\n";
}
