#include <csl/controllers/continuous_policy.hpp>

#include <iostream>

int main() {
    using namespace csl;
    using namespace csl::model;
    const SystemModel authored{{{1, 1, 0}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{0}}, {1,0,{}}, {0}}}, {}};
    const auto system = snapshot(authored, Vector{0, 1});
    if (!std::holds_alternative<LinearSystem>(system)) return 1;

    const auto inequalities = numeric::snapshot(Matrix{2,1,{1,-1}});
    const auto upper_bounds = numeric::snapshot_vector(Vector{1,1});
    const auto equalities = numeric::snapshot(Matrix{0,1,{}});
    const auto equality_values = numeric::snapshot_vector(Vector{});
    if (!std::holds_alternative<numeric::MatrixView>(inequalities) ||
        !std::holds_alternative<numeric::VectorView>(upper_bounds) ||
        !std::holds_alternative<numeric::MatrixView>(equalities) ||
        !std::holds_alternative<numeric::VectorView>(equality_values)) return 2;
    auto set = sets::make_h({{"installed-joint-h"}, 1, {"x0"}},
        {std::get<numeric::MatrixView>(inequalities),
         std::get<numeric::VectorView>(upper_bounds),
         std::get<numeric::MatrixView>(equalities),
         std::get<numeric::VectorView>(equality_values)});
    if (!std::holds_alternative<sets::SetData>(set)) return 3;
    const auto domain = controllers::make_joint_h_uncertainty(
        std::get<LinearSystem>(system), std::get<sets::SetData>(std::move(set)));
    if (!std::holds_alternative<controllers::JointHUncertainty>(domain)) return 4;
    if (std::get<controllers::JointHUncertainty>(domain).layout().total_dimension != 1) return 5;

    std::cout << "Installed continuous policy client: joint H domain layout passed\n";
}
