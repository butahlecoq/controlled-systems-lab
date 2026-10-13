#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/reachability/nominal_forward.hpp>

#include <cmath>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <variant>
#include <vector>

namespace {
template<class T, class... E> T take(std::variant<T, E...> value) {
    if (!std::holds_alternative<T>(value)) throw std::runtime_error("Installed nominal-forward client setup rejected.");
    return std::get<T>(std::move(value));
}

template<class Port> csl::registry::PreparedProvider<Port> selected(
        csl::registry::Registration<Port> registration, std::string representation) {
    csl::registry::Registry<Port> providers;
    const csl::registry::Method method{registration.identity.id, registration.identity.version};
    if (providers.add(std::move(registration))) throw std::runtime_error("Provider registration rejected.");
    csl::registry::Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, csl::registry::GeometryPort> ||
                  std::is_same_v<Port, csl::registry::ConversionPort>) {
        requirements.output.relation = csl::SetRelation::equivalent;
    }
    return take(csl::registry::prepare_provider(
        csl::registry::select_provider(providers, method, requirements)));
}

csl::SetHandle interval(std::string id, double low, double high) {
    using namespace csl;
    const auto matrix = take(numeric::snapshot(Matrix{2, 1, {1, -1}}));
    const auto bounds = take(numeric::snapshot_vector(Vector{high, -low}));
    const auto equalities = take(numeric::snapshot(Matrix{0, 1, {}}));
    const auto equality_values = take(numeric::snapshot_vector(Vector{}));
    return take(sets::make_h({{std::move(id)}, 1, {"x"}},
        {matrix, bounds, equalities, equality_values})).as_handle();
}
}

int main() {
    using namespace csl;
    try {
        auto lp = take(adapters::lp::make_highs_registration());
        auto converter = take(adapters::polyhedral::make_qhull_registration(lp));
        const auto affine = geometry::make_affine_sum_registration({
            selected(geometry::make_lp_hull_reducer_registration(), ""),
            selected(lp, "csl.program-result.v1"),
            selected(converter, "csl.polyhedron.v")}, {{}, {}});
        const reachability::ForwardDependencies dependencies{
            selected(geometry::polyhedral::make_projection_registration(
                {geometry::polyhedral::ProjectionOutput::h}), "csl.polyhedron.h"),
            selected(affine, "csl.polyhedron.v"),
            selected(converter, "csl.polyhedron.h")};

        const auto model = std::make_shared<const SystemModel>(SystemModel{{{1, 1, 0}, TimeDomain::discrete,
            LinearStage{{1, 1, {1}}, {1, 1, {1}}, {1, 0, {}}, {0}}}, {}});
        Problem problem{{"installed-integrator"}, model, {0, 1, 2}, KnownInitial{{0}},
            ContinuousDomain{{interval("u0", 0, 1), interval("u1", 0, 1)}},
            {interval("X0", 0, 0), interval("X1", 0, 1), interval("X2", 0, 2)},
            {}, {}, InformationPattern::nominal_open_loop,
            QuadraticTerminal{{1, 1, {2}}, {-2}, 1}};
        const auto resolved = take(problem::resolve(problem,
            {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
        const auto result = reachability::nominal_forward(resolved, {"installed"}, dependencies, {});
        if (!std::holds_alternative<reachability::ForwardTube>(result)) return 2;
        const auto& tube = std::get<reachability::ForwardTube>(result);
        if (tube.stages.size() != 3) return 3;
        const auto final = take(sets::from_handle(tube.stages.back().marginal.output));
        const auto rep = final.representation();
        const auto* h = std::get_if<sets::HRepresentation>(&rep);
        if (!h || final.metadata()->coordinate_labels != std::vector<std::string>{"x"}) return 4;
        double low = -std::numeric_limits<double>::infinity();
        double high = std::numeric_limits<double>::infinity();
        for (std::size_t row = 0; row < h->inequalities.rows(); ++row) {
            const double a = h->inequalities(row, 0), b = h->upper_bounds[row];
            if (a > 0) high = std::min(high, b / a);
            else if (a < 0) low = std::max(low, b / a);
            else if (b < 0) return 5;
        }
        if (low != 0.0 || high != 2.0 ||
            !std::holds_alternative<Unestablished>(tube.stages.back().marginal.evidence.support)) return 6;
        std::cout << "Installed nominal-forward client: provider-backed integrator tube and authored labels passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
