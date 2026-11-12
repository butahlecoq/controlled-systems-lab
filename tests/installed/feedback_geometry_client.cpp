#include <csl/reachability/bounded_h_support.hpp>
#include <csl/reachability/feedback_geometry.hpp>
#include <csl/geometry/polyhedral_intersection.hpp>
#include <csl/geometry/generator_adapter.hpp>
#if CSL_INSTALLED_FEEDBACK_WITH_HIGHS
#include <csl/adapters/lp/highs.hpp>
#endif
#include <cmath>
#include <memory>
#include <stdexcept>
#include <type_traits>
#include <variant>
#include <iostream>
namespace {
template<class T, class... E> T take(std::variant<T, E...> value) {
    if (!std::holds_alternative<T>(value)) throw std::runtime_error("Installed feedback setup rejected.");
    return std::get<T>(std::move(value));
}
template<class Port> csl::registry::PreparedProvider<Port> selected(
        csl::registry::Registration<Port> entry, std::string representation) {
    csl::registry::Registry<Port> registry;
    const csl::registry::Method method{entry.identity.id, entry.identity.version};
    if (registry.add(std::move(entry))) throw std::runtime_error("Provider registration rejected.");
    csl::registry::Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (!std::is_same_v<Port, csl::registry::LPPort>)
        requirements.output.relation = csl::SetRelation::equivalent;
    return take(csl::registry::prepare_provider(csl::registry::select_provider(registry, method, requirements)));
}
class UnavailableLP final : public csl::LPWorkspace {
    csl::ProgramOutcome do_solve(const csl::LinearProgram&, const csl::ExecutionContext&) override {
        return csl::Unsupported{{{csl::DiagnosticCode::unsupported, "installed.lp.unavailable",
            "This core-package fixture deliberately has no LP solver."}}};
    }
};
csl::registry::Registration<csl::registry::LPPort> unavailable_lp() {
    return {{{"installed.unavailable-lp"}, "1"},
        [](const csl::LinearProgram&, const csl::registry::Requirements& r)->csl::registry::Capability {
            return csl::registry::Offer{r.output};
        }, [](const csl::LinearProgram&) { return std::make_unique<UnavailableLP>(); }};
}
bool coordinator() {
    using namespace csl;
    using namespace csl::reachability;
    auto projection = selected(geometry::polyhedral::make_projection_registration(), "csl.polyhedron.h");
    auto intersection = selected(geometry::polyhedral::make_intersection_registration(), "csl.polyhedron.h");
    // The coordinator uses native H projection and family kernels. These other
    // ForwardDependencies ports are required by the shared type but never called.
    auto conversion = selected(geometry::generators::make_v_conversion_registration(4), "csl.polyhedron.v");
    const auto model = std::make_shared<const SystemModel>(SystemModel{{{2, 1, 0},
        TimeDomain::discrete, std::vector<LinearStage>{{{2, 2, {1,0,0,1}},
            {2, 1, {1,0}}, {2, 0, {}}, {0,0}}}}, {}});
    Problem source{{"installed-feedback"}, model, {0,1}, KnownInitial{{0.25,0.5}},
        ContinuousDomain{{Singleton{{0.75}}}}, {UniversalSet{2}, UniversalSet{2}}, {}, {},
        InformationPattern::nominal_open_loop, QuadraticTerminal{{2,2,{2,0,0,2}}, {0,0}, 0}};
    auto resolved = take(problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
    auto terminal = take(sets::make_universal({{"installed-terminal"},2,{}})).as_handle();
    for (auto family : {FeedbackFamily::polytope, FeedbackFamily::box, FeedbackFamily::zonotope,
                       FeedbackFamily::parallelotope, FeedbackFamily::ellipsoid}) {
        auto stopped = feedback_geometry(resolved, {"installed-stop"}, terminal, family, {},
            {{{projection, intersection, conversion}, intersection},
             selected(unavailable_lp(), "csl.program-result.v1"), 64}, {});
        const auto* failure = std::get_if<FeedbackGeometryFailure>(&stopped);
        if (!failure || failure->stage.value != 0 || failure->phase != FeedbackGeometryPhase::forward ||
            failure->prefix.stages.size() != 2 || !failure->prefix.stages[0].forward_h ||
            failure->pending_providers.size() != 2 || failure->pending_support_calls.size() != 1) return false;
        const auto* unsupported = std::get_if<Unsupported>(&failure->cause);
        const auto* lp = std::get_if<registry::LPQuerySolverUnsupported>(&failure->pending_support_calls[0]);
        if (!unsupported || unsupported->diagnostics.empty() ||
            unsupported->diagnostics[0].field != "installed.lp.unavailable" || !lp || !lp->provider.actual ||
            lp->provider.actual->id.value != "installed.unavailable-lp") return false;
        for (const auto& provider : failure->pending_providers)
            if (!provider.actual_module || provider.actual_module->value != "csl.geometry.polyhedral-intersection") return false;
#if CSL_INSTALLED_FEEDBACK_WITH_HIGHS
        auto outcome = feedback_geometry(resolved, {"installed-positive"}, terminal, family, {},
            {{{projection, intersection, conversion}, intersection},
             selected(take(adapters::lp::make_highs_registration()), "csl.program-result.v1"), 64}, {});
        const auto* result = std::get_if<FeedbackGeometry>(&outcome);
        if (!result || result->stages.size() != 2) return false;
        for (const auto& stage : result->stages) {
            if (!stage.forward || !stage.backward || !stage.intersection || !stage.intersection_h ||
                stage.intersection->family != family || stage.intersection->support_certificates.empty()) return false;
            const Vector point = stage.stage.value == 0 ? Vector{0.25,0.5} : Vector{1,0.5};
            auto data = take(sets::from_handle(stage.intersection_h->output));
            auto representation = data.representation();
            const auto* h = std::get_if<sets::HRepresentation>(&representation);
            if (!h) return false;
            for (std::size_t i=0; i<h->inequalities.rows(); ++i)
                if (h->inequalities(i,0)*point[0]+h->inequalities(i,1)*point[1] > h->upper_bounds[i]+1e-9) return false;
            for (std::size_t i=0; i<h->equalities.rows(); ++i)
                if (std::abs(h->equalities(i,0)*point[0]+h->equalities(i,1)*point[1]-h->equality_values[i]) > 1e-9) return false;
        }
#endif
    }
    return true;
}
}
int main() {
    using namespace csl;
    using namespace csl::reachability;
    BoundedHSupportInput input{{1,2,{1,1}},{1},{0,2,{}},{},{-2,-2},{2,2},{1,1}};
    auto support=residual_corrected_support(input,{0.9},{});
    if (!std::holds_alternative<SupportUpperBound>(support)) return 1;
    auto value=std::get<SupportUpperBound>(support);
    if (value.value<1.3 || value.value>1.300000001 || value.inequality_multipliers.size()!=1) return 2;
    auto result=axis_enclosure(FeedbackFamily::ellipsoid,{"installed"},{-1,-2},{1,2},{"x","y"});
    if (!std::holds_alternative<FeedbackMembership>(result)) return 3;
    const auto* ellipsoid=std::get_if<FeedbackEllipsoidMembership>(&std::get<FeedbackMembership>(result));
    if (!ellipsoid || ellipsoid->factor.rows!=2 || ellipsoid->factor.cols!=2) return 4;
    if (!coordinator()) return 5;
#if CSL_INSTALLED_FEEDBACK_WITH_HIGHS
    std::cout << "Installed feedback geometry: five-family positive coordinator passed\n";
#endif
    std::cout << "Installed feedback geometry client: corrected support, ellipsoid factor and coordinator stop passed\n";
    return 0;
}
