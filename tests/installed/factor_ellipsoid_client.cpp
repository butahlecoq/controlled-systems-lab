#include <csl/geometry/ellipsoidal.hpp>

#include <cmath>
#include <iostream>
#include <variant>

int main() {
    using namespace csl;
    using namespace csl::geometry::ellipsoidal;
    const auto singleton = make_factor_ellipsoid({1.0, -1.0}, Matrix{2, 0, {}});
    if (!std::holds_alternative<FactorEllipsoid>(singleton))
        return 1;
    const auto control = make_factor_ellipsoid({0.0, 0.0}, Matrix{2, 1, {0.25, -0.5}});
    if (!std::holds_alternative<FactorEllipsoid>(control))
        return 2;
    const auto sum = outer_minkowski_sum(std::get<FactorEllipsoid>(singleton),
                                         std::get<FactorEllipsoid>(control), 1.0);
    if (!std::holds_alternative<FactorEllipsoid>(sum))
        return 3;
    const auto &enclosure = std::get<FactorEllipsoid>(sum);
    if (enclosure.center != Vector{1.0, -1.0} || enclosure.factor.rows != 2 ||
        enclosure.factor.cols != 1)
        return 4;

    const auto image = affine_image(enclosure, Matrix{2, 2, {2, 1, -1, 3}}, {0.5, -0.25});
    if (!std::holds_alternative<FactorEllipsoid>(image))
        return 5;
    const auto &transformed = std::get<FactorEllipsoid>(image);
    const double expected_factor = -1.75;
    if (std::abs(transformed.center[0] - 1.5) > 1e-14 ||
        std::abs(transformed.center[1] + 4.25) > 1e-14 || transformed.factor.rows != 2 ||
        transformed.factor.cols != 1 || std::abs(transformed.factor.values[0]) > 1e-14 ||
        std::abs(transformed.factor.values[1] - expected_factor) > 1e-14)
        return 6;

    std::cout
        << "Installed factor-ellipsoid client: singleton Minkowski enclosure and affine image passed\n";
}
