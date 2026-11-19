#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/polyhedral_intersection.hpp>
#include <csl/reachability/nominal_tube.hpp>

#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

namespace {
template <class T, class... E> T take(std::variant<T, E...> value) {
    if (!std::holds_alternative<T>(value))
        throw std::runtime_error("Installed nominal-tube consumer setup was rejected.");
    return std::get<T>(std::move(value));
}

template <class Port>
csl::registry::PreparedProvider<Port> selected(csl::registry::Registration<Port> registration,
                                               std::string representation) {
    csl::registry::Registry<Port> providers;
    const csl::registry::Method method{registration.identity.id, registration.identity.version};
    if (providers.add(std::move(registration)))
        throw std::runtime_error("Provider registration rejected.");
    csl::registry::Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, csl::registry::GeometryPort> ||
                  std::is_same_v<Port, csl::registry::ConversionPort>)
        requirements.output.relation = csl::SetRelation::equivalent;
    return take(csl::registry::prepare_provider(
        csl::registry::select_provider(providers, method, requirements)));
}

csl::SetHandle box(std::string id, csl::Vector lower, csl::Vector upper) {
    using namespace csl;
    const auto dimension = lower.size();
    if (dimension != upper.size())
        throw std::runtime_error("Invalid box dimensions.");
    Matrix rows{2 * dimension, dimension, Vector(2 * dimension * dimension, 0.0)};
    Vector rhs(2 * dimension, 0.0);
    for (std::size_t coordinate = 0; coordinate < dimension; ++coordinate) {
        rows.values[(2 * coordinate) * dimension + coordinate] = 1.0;
        rhs[2 * coordinate] = upper[coordinate];
        rows.values[(2 * coordinate + 1) * dimension + coordinate] = -1.0;
        rhs[2 * coordinate + 1] = -lower[coordinate];
    }
    return take(sets::make_h({{std::move(id)}, dimension, {"x", "y"}},
                             {take(numeric::snapshot(rows)), take(numeric::snapshot_vector(rhs)),
                              take(numeric::snapshot(Matrix{0, dimension, {}})),
                              take(numeric::snapshot_vector({}))}))
        .as_handle();
}

bool contains(const csl::sets::HRepresentation &h, const csl::Vector &point) {
    if (point.size() != h.inequalities.cols())
        return false;
    for (std::size_t row = 0; row < h.inequalities.rows(); ++row) {
        double value = 0.0;
        for (std::size_t column = 0; column < point.size(); ++column)
            value += h.inequalities(row, column) * point[column];
        if (value > h.upper_bounds[row] + 1e-10)
            return false;
    }
    for (std::size_t row = 0; row < h.equalities.rows(); ++row) {
        double value = 0.0;
        for (std::size_t column = 0; column < point.size(); ++column)
            value += h.equalities(row, column) * point[column];
        if (std::abs(value - h.equality_values[row]) > 1e-10)
            return false;
    }
    return true;
}
}

int main() {
    using namespace csl;
    try {
        auto lp = take(adapters::lp::make_highs_registration());
        auto converter = take(adapters::polyhedral::make_qhull_registration(lp));
        auto affine = geometry::make_affine_sum_registration(
            {selected(geometry::make_lp_hull_reducer_registration(), ""),
             selected(lp, "csl.program-result.v1"), selected(converter, "csl.polyhedron.v")},
            {{}, {}});
        reachability::ForwardDependencies forward{
            selected(geometry::polyhedral::make_projection_registration(), "csl.polyhedron.h"),
            selected(std::move(affine), "csl.polyhedron.v"),
            selected(converter, "csl.polyhedron.h")};
        auto intersection =
            selected(geometry::polyhedral::make_intersection_registration(), "csl.polyhedron.h");

        const auto model = std::make_shared<const SystemModel>(
            SystemModel{{{2, 2, 0},
                         TimeDomain::discrete,
                         std::vector<LinearStage>{
                             {{2, 2, {1, 0, 0, 1}}, {2, 2, {1, 0, 0, 1}}, {2, 0, {}}, {0, 0}}}},
                        {}});
        const std::vector<std::string> state_labels{"x", "y"};
        Problem source{{"installed-tube"},
                       model,
                       {0, 1},
                       KnownInitial{{0.2, 0.4}},
                       ContinuousDomain{{box("u0", {-0.2, -0.1}, {0.3, 0.2})}},
                       {box("X0", {-1.0, -1.0}, {1.0, 1.0}), box("X1", {0.0, 0.1}, {0.8, 0.9})},
                       {},
                       {},
                       InformationPattern::nominal_open_loop,
                       QuadraticTerminal{{2, 2, {2, 0, 0, 2}}, {0, 0}, 0}};
        const auto resolved = take(problem::resolve(
            source, {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
        const auto result = reachability::nominal_tube(
            resolved, {"installed"}, box("physical-terminal", {0.4, 0.5}, {0.5, 0.7}),
            {std::move(forward), std::move(intersection)}, {});
        if (!std::holds_alternative<reachability::NominalTube>(result))
            return 2;
        const auto &tube = std::get<reachability::NominalTube>(result);
        if (tube.stages.size() != 2 || !tube.stages[0].intersection || !tube.stages[1].intersection)
            return 3;
        const auto final = take(sets::from_handle(tube.stages[1].intersection->output));
        const auto representation = final.representation();
        const auto *h = std::get_if<sets::HRepresentation>(&representation);
        if (!h || final.metadata()->coordinate_labels != state_labels ||
            !contains(*h, {0.45, 0.55}) || contains(*h, {0.35, 0.55}))
            return 4;
        const auto initial = take(sets::from_handle(tube.stages[0].intersection->output));
        const auto initial_representation = initial.representation();
        const auto *initial_h = std::get_if<sets::HRepresentation>(&initial_representation);
        if (!initial_h || !contains(*initial_h, {0.2, 0.4}) ||
            !std::holds_alternative<Unestablished>(tube.stages[1].intersection->evidence.support))
            return 5;
        std::cout
            << "Installed nominal-tube client: exported H stages and point membership passed\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
