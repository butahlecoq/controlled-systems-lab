#include <csl/geometry/approximation.hpp>
#include <csl/geometry/box_parallelotope.hpp>
#include <csl/sets/data.hpp>

#include <cmath>
#include <iostream>
#include <utility>
#include <variant>
#include <vector>

int main() {
    using namespace csl;
    using namespace csl::geometry::approximation;

    constexpr std::size_t dimension = 4;
    std::vector<double> corners;
    corners.reserve(16 * dimension);
    for (unsigned mask = 0; mask < 16; ++mask)
        for (std::size_t axis = 0; axis < dimension; ++axis)
            corners.push_back((mask & (1U << axis)) ? 1.0 : -1.0);

    const auto vertices = numeric::snapshot(Matrix{16, dimension, std::move(corners)});
    const auto rays = numeric::snapshot(Matrix{0, dimension, {}});
    if (!std::holds_alternative<numeric::MatrixView>(vertices) ||
        !std::holds_alternative<numeric::MatrixView>(rays))
        return 1;
    const auto source = sets::make_v({{"installed-buryatia-dim4"}, dimension,
        {"x1", "x2", "x3", "x4"}},
        {std::get<numeric::MatrixView>(vertices), std::get<numeric::MatrixView>(rays)});
    if (!std::holds_alternative<sets::SetData>(source)) return 2;

    const ApproximationRequest request{{{"installed-buryatia-dim4-problem"},
        {"dim4-parallelotope-request"}, {"dim4-source-box"}},
        std::get<sets::SetData>(source).as_handle(), {"csl.polyhedron.h"},
        SetRelation::outer, 8, Assurance::numerical};
    const Matrix orientation{dimension, dimension,
        {1.0, 0.25, 0.0, 0.0,
         0.0, 1.0, 0.25, 0.0,
         0.0, 0.0, 1.0, 0.25,
         0.25, 0.0, 0.0, 1.0}};
    registry::Registry<registry::ApproximationPort> methods;
    if (methods.add(make_parallelotope_registration({"installed-dim4-output"}, orientation)))
        return 3;
    const auto result = run_registered(methods,
        {{"csl.approximation.parallelotope"}, std::nullopt}, request, ExecutionContext{});
    if (!std::holds_alternative<EnclosedApproximation>(result)) return 4;
    const auto& enclosed = std::get<EnclosedApproximation>(result);
    if (enclosed.basis != StructuralBasis::v_h_containment) return 5;

    const auto native = sets::from_handle(enclosed.result.output);
    if (!std::holds_alternative<sets::SetData>(native)) return 6;
    const auto representation = std::get<sets::SetData>(native).representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h || h->inequalities.rows() != 8 || h->inequalities.cols() != dimension ||
        h->upper_bounds.size() != 8)
        return 7;
    for (std::size_t index = 0; index < h->upper_bounds.size(); ++index)
        if (std::abs(h->upper_bounds[index] - 1.25) > 1e-14) return 8;

    std::cout << "Installed Buryatia Dim4 client: 4D parallelotope enclosure passed\n";
}
