#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/synthesis/strategy_a/nominal_linear_exact_profile.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>

#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <variant>
#include <vector>

namespace {
using namespace csl;
using namespace csl::registry;

template<class T, class... Errors>
T take(std::variant<T, Errors...> value, const char* stage) {
    if (auto* result = std::get_if<T>(&value)) return std::move(*result);
    throw std::runtime_error(std::string(stage) + " was rejected");
}

template<class Port>
PreparedProvider<Port> selected(Registration<Port> registration, std::string representation) {
    Registry<Port> registry;
    const Method method{registration.identity.id, registration.identity.version};
    if (registry.add(std::move(registration))) throw std::runtime_error("provider registration failed");
    Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, GeometryPort> || std::is_same_v<Port, ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry, method, requirements)), "provider selection");
}

sets::SetData h_set(SetId id, std::vector<std::string> labels,
    Matrix inequalities, Vector upper_bounds) {
    const auto columns = inequalities.cols;
    return take(sets::make_h({std::move(id), labels.size(), std::move(labels)},
        {take(numeric::snapshot(inequalities), "H rows"),
         take(numeric::snapshot_vector(upper_bounds), "H bounds"),
         take(numeric::snapshot(Matrix{0, columns, {}}), "equalities"),
         take(numeric::snapshot_vector(Vector{}), "equality bounds")}), "H set");
}
}

int main() try {
    using namespace csl;
    const auto initial = take(sets::make_singleton({{"initial-point"}, 2, {"x", "y"}},
        take(numeric::snapshot_vector(Vector{0, 0}), "initial point")), "initial set");
    const auto controls = h_set({"unit-square"}, {"u", "v"},
        Matrix{4, 2, {-1, 0, 1, 0, 0, -1, 0, 1}}, Vector{0, 1, 0, 1});
    const auto target = h_set({"upper-triangle"}, {"x", "y"},
        Matrix{5, 2, {-1, -1, 1, 0, 0, 1, -1, 0, 0, -1}},
        Vector{-1, 1, 1, 0, 0});
    const auto model = std::make_shared<const SystemModel>(SystemModel{
        {{2, 2, 0}, TimeDomain::discrete,
         LinearStage{{2, 2, {0, 0, 0, 0}}, {2, 2, {1, 0, 0, 1}},
             {2, 0, {}}, {0, 0}}}, {}});
    const Problem source{{"nominal-linear-exact-2d"}, model, {0, 1}, KnownInitial{{0, 0}},
        ContinuousDomain{{controls.as_handle()}}, {initial.as_handle(), target.as_handle()}, {}, {},
        InformationPattern::nominal_open_loop, LinearTerminal{{1, 1}, 0}};
    const auto resolved = take(problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}), "problem resolution");

    auto lp = take(adapters::lp::make_highs_registration(), "LP registration");
    auto convex = take(adapters::convex::make_highs_registration(), "convex registration");
    auto converter = take(adapters::polyhedral::make_qhull_registration(lp), "conversion registration");
    auto projection = geometry::polyhedral::make_projection_registration();
    auto affine = geometry::make_affine_sum_registration({
        selected(geometry::make_lp_hull_reducer_registration(), ""),
        selected(lp, "csl.program-result.v1"), selected(converter, "csl.polyhedron.v")});
    Registry<GeometryPort> projections, affines;
    Registry<ConversionPort> conversions;
    Registry<LPPort> lps;
    Registry<ConvexPort> convexes;
    const Method pm{projection.identity.id, projection.identity.version};
    const Method am{affine.identity.id, affine.identity.version};
    const Method cm{converter.identity.id, converter.identity.version};
    const Method lm{lp.identity.id, lp.identity.version};
    const Method qm{convex.identity.id, convex.identity.version};
    if (projections.add(projection) || affines.add(affine) || conversions.add(converter) ||
        lps.add(lp) || convexes.add(convex)) throw std::runtime_error("module registration failed");
    Requirements h, v, program;
    h.output.representation = {"csl.polyhedron.h"}; h.output.relation = SetRelation::equivalent;
    v.output.representation = {"csl.polyhedron.v"}; v.output.relation = SetRelation::equivalent;
    program.output.representation = {"csl.program-result.v1"};
    auto providers = take(check_providers(select_provider(projections, pm, h),
        select_provider(affines, am, v), select_provider(conversions, cm, h),
        select_provider(lps, lm, program), select_provider(convexes, qm, program)), "providers");
    StrategyRegistry strategies;
    if (strategies.add(synthesis::strategy_a::make_registration(std::move(providers))))
        throw std::runtime_error("Strategy A registration failed");

    FamilyRequest family;
    family.profile = synthesis::strategy_a::nominal_linear_exact_profile;
    family.objective = resolved.identity();
    family.target = FamilyTarget::exact_optimal_relation;
    family.assurance = Assurance::numerical;
    family.representation = {"csl.polyhedron.h"};
    StrategyConfiguration configuration;
    configuration.strategy = {"csl.synthesis.reach-back"};
    configuration.representation = family.representation;
    const StrategyRequest request{resolved, configuration, family, "1", {}};
    Requirements output;
    output.output.representation = family.representation;
    output.output.family = family.target;
    output.output.completeness = Completeness::established;
    auto prepared = take(strategies.prepare(request, output), "Strategy A preparation");
    auto workspace = prepared.create();
    ExecutionContext context;
    context.numerical = family.numerical;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    auto result = take(workspace->run(context), "Strategy A run");
    if (!result.family || !result.family->registry_verified() || !result.objective.lower ||
        !result.objective.upper || result.objective.lower->value != 1 || result.objective.upper->value != 1)
        throw std::runtime_error("expected registered complete optimal face with objective 1");
    std::cout << "profile=" << family.profile << "\n"
              << "state_dimension=2 control_dimension=2 horizon=1\n"
              << "terminal_constraint=x+y>=1; 0<=x,y<=1\n"
              << "objective=minimize x+y\n"
              << "exact_optimum=1 optimal_face={(x,y): x+y=1, 0<=x,y<=1}\n"
              << "verified_complete_family=true assurance=numerical\n";
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
