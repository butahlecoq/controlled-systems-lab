#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/polyhedral_intersection.hpp>
#include <csl/reachability/nominal_tube.hpp>
#include <csl/reachability/feedback_geometry.hpp>

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
template<class T, class... E> T take(std::variant<T, E...> value) {
    if (!std::holds_alternative<T>(value))
        throw std::runtime_error("Installed nominal-tube consumer setup was rejected.");
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
                  std::is_same_v<Port, csl::registry::ConversionPort>)
        requirements.output.relation = csl::SetRelation::equivalent;
    return take(csl::registry::prepare_provider(
        csl::registry::select_provider(providers, method, requirements)));
}

csl::SetHandle box(std::string id, csl::Vector lower, csl::Vector upper) {
    using namespace csl;
    const auto dimension = lower.size();
    if (dimension != upper.size()) throw std::runtime_error("Invalid box dimensions.");
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
         take(numeric::snapshot_vector({}))})).as_handle();
}

bool contains(const csl::sets::HRepresentation& h, const csl::Vector& point) {
    if (point.size() != h.inequalities.cols()) return false;
    for (std::size_t row = 0; row < h.inequalities.rows(); ++row) {
        double value = 0.0;
        for (std::size_t column = 0; column < point.size(); ++column)
            value += h.inequalities(row, column) * point[column];
        if (value > h.upper_bounds[row] + 1e-10) return false;
    }
    for (std::size_t row = 0; row < h.equalities.rows(); ++row) {
        double value = 0.0;
        for (std::size_t column = 0; column < point.size(); ++column)
            value += h.equalities(row, column) * point[column];
        if (std::abs(value - h.equality_values[row]) > 1e-10) return false;
    }
    return true;
}
}

int main() {
    using namespace csl;
    try {
        auto lp = take(adapters::lp::make_highs_registration());
        auto converter = take(adapters::polyhedral::make_qhull_registration(lp));
        auto affine = geometry::make_affine_sum_registration({
            selected(geometry::make_lp_hull_reducer_registration(), ""),
            selected(lp, "csl.program-result.v1"),
            selected(converter, "csl.polyhedron.v")}, {{}, {}});
        reachability::ForwardDependencies forward{
            selected(geometry::polyhedral::make_projection_registration(), "csl.polyhedron.h"),
            selected(std::move(affine), "csl.polyhedron.v"),
            selected(converter, "csl.polyhedron.h")};
        auto intersection = selected(geometry::polyhedral::make_intersection_registration(),
            "csl.polyhedron.h");

        const auto model = std::make_shared<const SystemModel>(SystemModel{{{2, 2, 0},
            TimeDomain::discrete,
            std::vector<LinearStage>{{{2, 2, {1, 0, 0, 1}}, {2, 2, {1, 0, 0, 1}},
                {2, 0, {}}, {0, 0}}}}, {}});
        const std::vector<std::string> state_labels{"x", "y"};
        Problem source{{"installed-tube"}, model, {0, 1}, KnownInitial{{0.2, 0.4}},
            ContinuousDomain{{box("u0", {-0.2, -0.1}, {0.3, 0.2})}},
            {box("X0", {-1.0, -1.0}, {1.0, 1.0}),
             box("X1", {0.0, 0.1}, {0.8, 0.9})}, {}, {},
            InformationPattern::nominal_open_loop,
            QuadraticTerminal{{2, 2, {2, 0, 0, 2}}, {0, 0}, 0}};
        const auto resolved = take(problem::resolve(source,
            {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
        for (auto family : {reachability::FeedbackFamily::polytope, reachability::FeedbackFamily::box,
                reachability::FeedbackFamily::zonotope, reachability::FeedbackFamily::parallelotope,
                reachability::FeedbackFamily::ellipsoid}) {
            auto outcome=reachability::feedback_geometry(resolved,{"analytic"},
                box("physical-terminal", {0.0, 0.1}, {0.8, 0.9}),family,{},
                {{forward,intersection}, selected(lp,"csl.program-result.v1"), 1000}, {});
            if (auto* failure=std::get_if<reachability::FeedbackGeometryFailure>(&outcome)) {
                std::cerr << "family " << static_cast<int>(family) << " stage " << failure->stage.value << " phase " << static_cast<int>(failure->phase) << "\n";
                std::visit([](const auto& cause) { using T=std::decay_t<decltype(cause)>;
                    if constexpr(std::is_same_v<T,Unsupported>) for(const auto& d:cause.diagnostics) std::cerr << d.field << ": " << d.explanation << "\n";
                    else std::cerr << cause.diagnostics << "\n"; },failure->cause);
                return 2;
            }
            const auto& geometry=std::get<reachability::FeedbackGeometry>(outcome);
            if(geometry.stages.size()!=2) return 3;
            for(const auto& stage:geometry.stages) {
                if(!stage.forward || !stage.backward || !stage.intersection || !stage.forward_h || !stage.backward_h || !stage.intersection_h || !stage.forward_embedding_h || !stage.backward_embedding_h) return 4;
                auto full=take(sets::from_handle(stage.intersection_h->output));
                auto full_repr=full.representation();
                const auto* full_h=std::get_if<sets::HRepresentation>(&full_repr);
                if(!full_h || !contains(*full_h,{0.2,0.4})) return 5;
                const auto& member=stage.intersection->membership;
                if(const auto* h=std::get_if<reachability::FeedbackHMembership>(&member)) {
                    auto data=take(sets::from_handle(h->set)); auto repr=data.representation();
                    auto* rows=std::get_if<sets::HRepresentation>(&repr);
                    if(!rows || !contains(*rows,{0.2,0.4})) return 6;
                } else {
                    Vector center; Matrix factor; bool ball=false;
                    if(const auto* z=std::get_if<reachability::FeedbackZonotopeMembership>(&member)) { center=z->center; factor=z->generators; }
                    else { const auto& e=std::get<reachability::FeedbackEllipsoidMembership>(member); center=e.center; factor=e.factor; ball=true; }
                    double norm=0;
                    for(std::size_t j=0;j<2;++j) {
                        auto d=factor.values[j*factor.cols+j];
                        if(d==0) { if(std::abs(center[j]-Vector{0.2,0.4}[j])>1e-10) return 7; }
                        else { double x=(Vector{0.2,0.4}[j]-center[j])/d; norm+=x*x; if(!ball && std::abs(x)>1+1e-10) return 8; }
                    }
                    if(ball && norm>1+1e-10) return 9;
                }
            }
        }
        std::cout << "Five-family feedback geometry: full-state and family membership passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
