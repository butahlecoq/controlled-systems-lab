#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/sets/data.hpp>
#include <array>
#include <cmath>
#include <iostream>
#include <variant>

namespace {
template <class T, class... U> T take(std::variant<T, U...> value) {
    if (!std::holds_alternative<T>(value))
        throw 1;
    return std::get<T>(std::move(value));
}
}

int main() {
    using namespace csl;
    auto a = take(numeric::snapshot(Matrix{4, 2, {1, 0, -1, 0, 0, 1, 0, -1}}));
    auto b = take(numeric::snapshot_vector(Vector{1, 0, 1, 0}));
    auto e = take(numeric::snapshot(Matrix{0, 2, {}}));
    auto f = take(numeric::snapshot_vector(Vector{}));
    auto input = take(sets::make_h({{"installed-square"}, 2, {}}, {a, b, e, f})).as_handle();
    auto lp = take(adapters::lp::make_highs_registration());
    auto converter = take(adapters::polyhedral::make_qhull_registration(std::move(lp)));
    registry::Registry<registry::ConversionPort> conversions;
    if (conversions.add(std::move(converter)))
        return 2;
    ConversionRequest request{{{"installed"}, {"square"}, {"square-ideal"}},
                              input,
                              {"csl.polyhedron.v"},
                              Assurance::numerical};
    registry::Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.v"};
    requirements.output.assurance = Assurance::numerical;
    requirements.output.relation = SetRelation::equivalent;
    auto prepared = registry::prepare_pipeline(
        registry::select(conversions, {{"csl.conversion.qhull"}, {}}, request, requirements));
    if (!std::holds_alternative<registry::PreparedPipeline<registry::ConversionPort>>(prepared))
        return 3;
    auto [worker] =
        std::get<registry::PreparedPipeline<registry::ConversionPort>>(prepared).create();
    ExecutionContext context{{}, {}, {}, {1e-8, 1e-8}, "installed-conversion"};
    auto outcome = worker->run(context);
    if (!std::holds_alternative<OperationResult>(outcome))
        return 4;
    auto converted = take(sets::from_handle(std::get<OperationResult>(outcome).output));
    const auto rep = converted.representation();
    if (!std::holds_alternative<sets::VRepresentation>(rep))
        return 5;
    const auto &vertices = std::get<sets::VRepresentation>(rep).vertices;
    bool origin = false, upper = false;
    for (std::size_t i = 0; i < vertices.rows(); ++i) {
        origin = origin || (std::abs(vertices(i, 0)) < 1e-7 && std::abs(vertices(i, 1)) < 1e-7);
        upper =
            upper || (std::abs(vertices(i, 0) - 1) < 1e-7 && std::abs(vertices(i, 1) - 1) < 1e-7);
    }
    if (!origin || !upper)
        return 6;
    std::cout << "Installed Qhull conversion client: H-to-V square vertices passed\n";

    const auto square_vertices = take(numeric::snapshot(Matrix{4, 2, {0, 0, 1, 0, 1, 1, 0, 1}}));
    const auto square_rays = take(numeric::snapshot(Matrix{0, 2, {}}));
    const auto square_v =
        take(sets::make_v({{"installed-square-v"}, 2, {}}, {square_vertices, square_rays}))
            .as_handle();
    auto reverse = take(adapters::polyhedral::make_qhull_registration(
        take(adapters::lp::make_highs_registration())));
    registry::Registry<registry::ConversionPort> reverse_registry;
    if (reverse_registry.add(std::move(reverse)))
        return 7;
    ConversionRequest reverse_request{{{"installed"}, {"square-v-to-h"}, {"square-h"}},
                                      square_v,
                                      {"csl.polyhedron.h"},
                                      Assurance::numerical};
    registry::Requirements reverse_requirements;
    reverse_requirements.output.representation = {"csl.polyhedron.h"};
    reverse_requirements.output.assurance = Assurance::numerical;
    reverse_requirements.output.relation = SetRelation::equivalent;
    auto reverse_pipeline = registry::prepare_pipeline(
        registry::select(reverse_registry, {{"csl.conversion.qhull"}, std::nullopt},
                         reverse_request, reverse_requirements));
    if (!std::holds_alternative<registry::PreparedPipeline<registry::ConversionPort>>(
            reverse_pipeline))
        return 8;
    auto [reverse_worker] =
        std::get<registry::PreparedPipeline<registry::ConversionPort>>(reverse_pipeline).create();
    auto reverse_outcome = reverse_worker->run(context);
    if (!std::holds_alternative<OperationResult>(reverse_outcome))
        return 9;
    const auto reverse_data =
        take(sets::from_handle(std::get<OperationResult>(reverse_outcome).output));
    const auto reverse_representation = reverse_data.representation();
    const auto *inequalities = std::get_if<sets::HRepresentation>(&reverse_representation);
    if (!inequalities || inequalities->inequalities.rows() != 4 ||
        inequalities->upper_bounds.size() != 4)
        return 10;
    for (std::size_t row = 0; row < 4; ++row) {
        const double a = inequalities->inequalities(row, 0), b = inequalities->inequalities(row, 1);
        constexpr double tolerance = 1e-7;
        const double expected_bound = a < 0.0 || b < 0.0 ? 0.0 : 1.0;
        const bool axis_normal =
            (std::abs(std::abs(a) - 1.0) < tolerance && std::abs(b) < tolerance) ||
            (std::abs(a) < tolerance && std::abs(std::abs(b) - 1.0) < tolerance);
        if (std::abs(inequalities->upper_bounds[row] - expected_bound) > 1e-7 || !axis_normal) {
            std::cerr << "Unexpected V-to-H square row " << row << ": " << a << " " << b
                      << " <= " << inequalities->upper_bounds[row] << '\n';
            return 11;
        }
    }
    std::cout << "Installed Qhull conversion client: V-to-H square inequalities passed\n";
    return 0;
}
