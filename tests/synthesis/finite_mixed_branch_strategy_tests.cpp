#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/synthesis/finite_mixed_branch.hpp>
#include <csl/synthesis/strategy_a/nominal_linear_exact_profile.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>

#include <array>
#include <string>

using namespace csl;
using namespace csl::synthesis;

namespace {
numeric::MatrixView matrix(Matrix value) {
    auto result = numeric::snapshot(value);
    REQUIRE(std::holds_alternative<numeric::MatrixView>(result));
    return std::get<numeric::MatrixView>(std::move(result));
}

numeric::VectorView vector(Vector value) {
    auto result = numeric::snapshot_vector(value);
    REQUIRE(std::holds_alternative<numeric::VectorView>(result));
    return std::get<numeric::VectorView>(std::move(result));
}

template<class T, class... Errors>
T take(std::variant<T, Errors...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

SetHandle interval(std::string id, double lo, double hi, std::string label = "x") {
    auto result = sets::make_h({{std::move(id)}, 1, {std::move(label)}},
        {matrix({2, 1, {1, -1}}), vector({hi, -lo}),
         matrix({0, 1, {}}), vector({})});
    REQUIRE(std::holds_alternative<sets::SetData>(result));
    return std::get<sets::SetData>(std::move(result)).as_handle();
}

template<class Port>
registry::PreparedProvider<Port> selected(registry::Registration<Port> registration,
                                           std::string representation) {
    registry::Registry<Port> provider_registry;
    const registry::Method method{registration.identity.id, registration.identity.version};
    REQUIRE_FALSE(provider_registry.add(std::move(registration)).has_value());
    registry::Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, registry::GeometryPort> ||
                  std::is_same_v<Port, registry::ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(registry::prepare_provider(registry::select_provider(
        provider_registry, method, requirements)));
}

struct ExactLinearStrategyFixture {
    registry::Registry<registry::GeometryPort> projections, affines;
    registry::Registry<registry::ConversionPort> conversions;
    registry::Registry<registry::LPPort> lps;
    registry::Registry<registry::ConvexPort> convexes;
    registry::StrategyRegistry strategies;

    ExactLinearStrategyFixture() {
        auto lp = take(adapters::lp::make_highs_registration());
        auto convex = take(adapters::convex::make_highs_registration());
        auto converter = take(adapters::polyhedral::make_qhull_registration(lp));
        auto projection = geometry::polyhedral::make_projection_registration();
        auto affine = geometry::make_affine_sum_registration({
            selected(geometry::make_lp_hull_reducer_registration(), ""),
            selected(lp, "csl.program-result.v1"), selected(converter, "csl.polyhedron.v")});
        const registry::Method pm{projection.identity.id, projection.identity.version};
        const registry::Method am{affine.identity.id, affine.identity.version};
        const registry::Method cm{converter.identity.id, converter.identity.version};
        const registry::Method lm{lp.identity.id, lp.identity.version};
        const registry::Method qm{convex.identity.id, convex.identity.version};
        REQUIRE_FALSE(projections.add(projection).has_value());
        REQUIRE_FALSE(affines.add(affine).has_value());
        REQUIRE_FALSE(conversions.add(converter).has_value());
        REQUIRE_FALSE(lps.add(lp).has_value());
        REQUIRE_FALSE(convexes.add(convex).has_value());
        registry::Requirements h, v, program;
        h.output.representation = {"csl.polyhedron.h"}; h.output.relation = SetRelation::equivalent;
        v.output.representation = {"csl.polyhedron.v"}; v.output.relation = SetRelation::equivalent;
        program.output.representation = {"csl.program-result.v1"};
        auto providers = take(registry::check_providers(
            registry::select_provider(projections, pm, h), registry::select_provider(affines, am, v),
            registry::select_provider(conversions, cm, h), registry::select_provider(lps, lm, program),
            registry::select_provider(convexes, qm, program)));
        REQUIRE_FALSE(strategies.add(synthesis::strategy_a::make_registration(std::move(providers))).has_value());
    }
};

problem::ResolvedProblem mixed_linear_tie_problem() {
    const auto controls = take(sets::make_h({{"mixed-continuous-interval"}, 1, {"u"}},
        {matrix({2, 1, {1, -1}}), vector({1, 1}), matrix({0, 1, {}}), vector({})}));
    const auto terminal = take(sets::make_h({{"mixed-terminal-halfline"}, 1, {"x1"}},
        {matrix({1, 1, {-1}}), vector({0}), matrix({0, 1, {}}), vector({})}));
    Problem source{{"mixed-linear-tie"},
        std::make_shared<const SystemModel>(SystemModel{{{1, 2, 0}, TimeDomain::discrete,
            LinearStage{{1, 1, {0}}, {1, 2, {1, 1}}, {1, 0, {}}, {0}}}, {}}),
        {0, 1}, KnownInitial{{0}},
        MixedDomain{ContinuousDomain{{controls.as_handle()}}, FiniteDomain{1, {{-1}, {1}, {-1}}}},
        {interval("mixed-initial-state", 0.0, 0.0, "x1"), terminal.as_handle()}, {}, {},
        InformationPattern::nominal_open_loop, LinearTerminal{{1}, 0}};
    auto resolved = problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved));
    return std::get<problem::ResolvedProblem>(std::move(resolved));
}
}

TEST_CASE("mixed branch solve runs registered continuous solvers and retains verified source families") {
    const auto source = mixed_linear_tie_problem();
    ExactLinearStrategyFixture strategy_fixture;
    FiniteMixedBranchSolveRequest request;
    request.strategy.strategy = {"csl.synthesis.reach-back"};
    request.strategy.representation = {"csl.polyhedron.h"};
    request.family.profile = synthesis::strategy_a::nominal_linear_exact_profile;
    request.family.objective = source.identity();
    request.family.target = FamilyTarget::exact_optimal_relation;
    request.family.assurance = Assurance::numerical;
    request.family.representation = {"csl.polyhedron.h"};
    request.resolution = {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}};
    request.branches_per_page = 2;
    ExecutionContext context;
    context.numerical = request.family.numerical;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});

    const auto outcome = solve_finite_mixed_branch_portfolio(
        source, strategy_fixture.strategies, request, context);
    REQUIRE(std::holds_alternative<FiniteMixedBranchSolveResult>(outcome));
    const auto& solved = std::get<FiniteMixedBranchSolveResult>(outcome);
    for (const auto& evaluation : solved.portfolio.evaluations)
        if (const auto* failed = std::get_if<FailedFiniteMixedBranch>(&evaluation.branch))
            for (const auto& diagnostic : failed->diagnostics)
                CHECK_MESSAGE(false, diagnostic.field << ": " << diagnostic.explanation);
    CHECK(solved.history_enumeration_complete);
    CHECK(solved.every_branch_solved);
    CHECK(solved.portfolio.complete);
    REQUIRE(solved.portfolio.optimum.has_value());
    CHECK(*solved.portfolio.optimum == doctest::Approx(0.0));
    REQUIRE(solved.portfolio.optimal_evaluation_indices == std::vector<std::size_t>{0, 1, 2});
    CHECK(solved.portfolio.all_selected_relations_present);
    for (std::size_t index = 0; index < solved.portfolio.evaluations.size(); ++index) {
        const auto& evaluation = solved.portfolio.evaluations[index];
        REQUIRE(std::holds_alternative<FiniteMixedBranchProblem>(evaluation.branch));
        CHECK(std::get<FiniteMixedBranchProblem>(evaluation.branch).history ==
            FiniteActionHistory{{index}});
        REQUIRE(evaluation.verified_continuous_family.has_value());
        CHECK(evaluation.verified_continuous_family->registry_verified());
        REQUIRE(evaluation.source_relation.has_value());
        CHECK(evaluation.source_relation->metadata()->set.dimension == 4);
        const auto h = std::get<sets::HRepresentation>(evaluation.source_relation->representation());
        REQUIRE(h.equalities.rows() >= 1);
        const auto discrete_row = h.equalities.rows() - 1;
        CHECK(h.equalities(discrete_row, 3) == 1.0);
        const std::array<double, 3> expected_discrete{-1.0, 1.0, -1.0};
        CHECK(h.equality_values[discrete_row] == expected_discrete[index]);
    }
}
