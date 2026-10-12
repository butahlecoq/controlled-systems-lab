#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <csl/registry/provider.hpp>
#include <iostream>

int main() {
    using namespace csl;
    auto registration = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(registration)) return 1;
    auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto lp_provider = [&]() -> std::optional<registry::PreparedProvider<registry::LPPort>> {
        registry::Registry<registry::LPPort> lp_registry;
        if (lp_registry.add(std::move(adapter))) return std::nullopt;
        registry::Requirements lp_requirements;
        lp_requirements.output.representation = {"csl.program-result.v1"};
        lp_requirements.output.assurance = Assurance::numerical;
        lp_requirements.output.completeness = registry::Completeness::unestablished;
        auto result = registry::prepare_provider(registry::select_provider(lp_registry,
            registry::Method{{"csl.lp.highs"}, std::nullopt}, lp_requirements));
        if (!std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(result)) return std::nullopt;
        return std::get<registry::PreparedProvider<registry::LPPort>>(std::move(result));
    }();
    if (!lp_provider) return 2;
    registry::RegisteredLPQueryRunner lp(std::move(*lp_provider));

    registry::Registry<registry::HullReducerPort> hull_registry;
    if (hull_registry.add(geometry::make_lp_hull_reducer_registration())) return 3;
    const geometry::PointCloud cloud{{"installed-hull"}, {{0,0},{1,0},{1,1},{0,1},{0.5,0.5}}};
    auto hull_prepared_result = registry::prepare_pipeline(registry::select(hull_registry,
        registry::Method{{"csl.hull.lp-membership"}, std::nullopt}, cloud));
    if (!std::holds_alternative<registry::PreparedPipeline<registry::HullReducerPort>>(hull_prepared_result)) return 4;
    auto hull_prepared = std::get<registry::PreparedPipeline<registry::HullReducerPort>>(std::move(hull_prepared_result));
    auto hull_workspaces = hull_prepared.create();
    auto result = std::get<0>(hull_workspaces)->run_with(ExecutionContext{}, lp);
    if (!std::holds_alternative<geometry::HullReduction>(result)) return 5;
    const auto& reduction = std::get<geometry::HullReduction>(result);
    if (reduction.status != geometry::ReductionStatus::complete || reduction.retained.size() != 4 ||
        reduction.removed.size() != 1 || reduction.lp_calls != 5 || lp.records().size() != 5) return 6;
    for (const auto& query : lp.records()) {
        const auto* executed = std::get_if<registry::LPQueryCompleted>(&query);
        if (!executed || executed->provider.actual->id.value != "csl.lp.highs") return 7;
    }
    std::cout << "Installed hull client: each membership LP passed registered-provider admission\n";
}
