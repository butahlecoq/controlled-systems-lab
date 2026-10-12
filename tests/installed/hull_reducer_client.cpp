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
    auto workspace = adapter.factory(std::get<LinearProgram>(seed));
    const geometry::PointCloud cloud{{"installed-hull"}, {{0,0},{1,0},{1,1},{0,1},{0.5,0.5}}};
    auto result = geometry::reduce_hull(cloud, *workspace, {});
    if (!std::holds_alternative<geometry::HullReduction>(result)) return 3;
    const auto& reduction = std::get<geometry::HullReduction>(result);
    if (reduction.status != geometry::ReductionStatus::complete || reduction.retained.size() != 4 ||
        reduction.removed.size() != 1 || reduction.lp_calls != 5) return 4;
    std::cout << "Installed hull client: adapter-neutral reduction and certified removal passed\n";
}
