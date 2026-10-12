#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <iostream>

int main() {
    using namespace csl;
    auto registration = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(registration)) return 1;
    auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto seed = optimization::make_linear_program({{{"installed"},{"hull-seed"}}, {}, 0,
        {0,0,{0},{},{}}, {}, {}});
    if (!std::holds_alternative<LinearProgram>(seed)) return 2;
    registry::Registry<registry::LPPort> lp_registry;
    if (lp_registry.add(std::move(adapter))) return 3;
    registry::Requirements lp_requirements;
    lp_requirements.output.representation = {"csl.program-result.v1"};
    lp_requirements.output.assurance = Assurance::numerical;
    lp_requirements.output.completeness = registry::Completeness::unestablished;
    auto lp_prepared_result = registry::prepare_pipeline(registry::select(lp_registry,
        registry::Method{{"csl.lp.highs"}, std::nullopt}, std::get<LinearProgram>(seed), lp_requirements));
    if (!std::holds_alternative<registry::PreparedPipeline<registry::LPPort>>(lp_prepared_result)) return 4;
    auto lp_prepared = std::get<registry::PreparedPipeline<registry::LPPort>>(std::move(lp_prepared_result));
    auto lp_workspaces = lp_prepared.create();
    registry::LPWorkspaceView lp(*std::get<0>(lp_workspaces));

    registry::Registry<registry::HullReducerPort> hull_registry;
    if (hull_registry.add(geometry::make_lp_hull_reducer_registration())) return 5;
    const geometry::PointCloud cloud{{"installed-hull"}, {{0,0},{1,0},{1,1},{0,1},{0.5,0.5}}};
    auto hull_prepared_result = registry::prepare_pipeline(registry::select(hull_registry,
        registry::Method{{"csl.hull.lp-membership"}, std::nullopt}, cloud));
    if (!std::holds_alternative<registry::PreparedPipeline<registry::HullReducerPort>>(hull_prepared_result)) return 6;
    auto hull_prepared = std::get<registry::PreparedPipeline<registry::HullReducerPort>>(std::move(hull_prepared_result));
    auto hull_workspaces = hull_prepared.create();
    auto result = std::get<0>(hull_workspaces)->run_with(ExecutionContext{}, lp);
    if (!std::holds_alternative<geometry::HullReduction>(result)) return 7;
    const auto& reduction = std::get<geometry::HullReduction>(result);
    if (reduction.status != geometry::ReductionStatus::complete || reduction.retained.size() != 4 ||
        reduction.removed.size() != 1 || reduction.lp_calls != 5) return 8;
    std::cout << "Installed hull client: registered reducer and independently selected LP provider passed\n";
}
