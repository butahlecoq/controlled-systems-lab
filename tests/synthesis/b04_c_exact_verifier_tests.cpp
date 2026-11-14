#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <iostream>
#include <algorithm>

#include <csl/synthesis/b04_c_exact_family.hpp>
#include "../../src/registry/compiled_verifiers.hpp"
#include "../../src/registry/strategy_a_lineage.hpp"
#include "../../src/synthesis/b04_c_exact_family.hpp"

using namespace csl;

namespace {
std::string decimal(const synthesis::detail::exact_rational::Integer &input) {
    using namespace synthesis::detail::exact_rational;
    auto value = input;
    const bool negative = value.negative;
    value.negative = false;
    auto divisor = synthesis::detail::exact_rational::exact_h::exact_detail::from_u64(10);
    Budget budget;
    std::string result;
    if (synthesis::detail::exact_rational::exact_h::exact_detail::is_zero(value))
        return "0";
    while (!synthesis::detail::exact_rational::exact_h::exact_detail::is_zero(value)) {
        Integer quotient, remainder;
        REQUIRE(divide_magnitude(value, divisor, quotient, remainder, budget));
        result.push_back(static_cast<char>('0' + remainder.words.front()));
        value = std::move(quotient);
    }
    if (negative)
        result.push_back('-');
    std::reverse(result.begin(), result.end());
    return result;
}

SetHandle h_box(std::string id, std::size_t dimension, Vector rows, Vector bounds,
                std::vector<std::string> labels) {
    Matrix inequalities{rows.size() / dimension, dimension, std::move(rows)};
    const auto snapshot_matrix = numeric::snapshot(std::move(inequalities));
    const auto snapshot_bounds = numeric::snapshot_vector(std::move(bounds));
    const auto equalities = numeric::snapshot(Matrix{0, dimension, {}});
    const auto equality_values = numeric::snapshot_vector({});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(snapshot_matrix));
    REQUIRE(std::holds_alternative<numeric::VectorView>(snapshot_bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(equality_values));
    auto data = sets::make_h({{std::move(id)}, dimension, std::move(labels)},
                             {std::get<numeric::MatrixView>(snapshot_matrix),
                              std::get<numeric::VectorView>(snapshot_bounds),
                              std::get<numeric::MatrixView>(equalities),
                              std::get<numeric::VectorView>(equality_values)});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

SetHandle phase_box(std::size_t stage) {
    return h_box("b04-c-phase-" + std::to_string(stage), 4,
                 {1, 0, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 0, 0, -1, 0}, {1224, -1176, 468, -432},
                 {"x1", "x2", "x3", "x4"});
}

SetHandle control_box(std::size_t stage) {
    return h_box("b04-c-control-" + std::to_string(stage), 1, {1, -1}, {1, 1}, {"u"});
}

problem::ResolvedProblem b04_c_problem() {
    constexpr double dt = 25.0 / 4.0;
    Matrix A{4, 4, {1, 0, 0, 0, -dt, 1, 0, 0, 0, 0, 1, 0, 0, 0, -dt, 1}};
    Matrix B{4, 1, {2208.0 / 110.0, 0, -1152.0 / 110.0, 0}};
    Matrix E{4, 0, {}};
    Vector times(17);
    for (std::size_t stage = 0; stage < times.size(); ++stage)
        times[stage] = static_cast<double>(stage) * dt;
    std::vector<AdmissibleSet> controls, states;
    for (std::size_t stage = 0; stage < 16; ++stage)
        controls.push_back(control_box(stage));
    for (std::size_t stage = 0; stage <= 16; ++stage)
        states.push_back(phase_box(stage));
    const Matrix objective_map{
        5, 4, {-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1, 0, 1, 0, -(8.0 / 3.0)}};
    Problem source{{"b04-c-exact-dyadic-20261102"},
                   std::make_shared<const SystemModel>(SystemModel{
                       {{4, 1, 0},
                        TimeDomain::discrete,
                        LinearStage{std::move(A), std::move(B), std::move(E), {0, 0, 0, 0}}},
                       {}}),
                   std::move(times),
                   KnownInitial{{1220.28265395983, 119500, 440.005764648976, 45300}},
                   ContinuousDomain{std::move(controls)},
                   std::move(states),
                   {},
                   {},
                   InformationPattern::nominal_open_loop,
                   ResidualNormTerminal{
                       objective_map, {-1200, 0, -450, 0, 0}, {1, 1, 64.0 / 9.0, 64.0 / 9.0, 1}}};
    auto resolved =
        problem::resolve(source, {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved));
    return std::get<problem::ResolvedProblem>(std::move(resolved));
}

registry::StrategyRequest b04_c_request(problem::ResolvedProblem resolved) {
    FamilyRequest family;
    family.profile = synthesis::b04_c::exact_family_profile;
    family.objective = resolved.identity();
    family.target = FamilyTarget::exact_optimal_relation;
    family.assurance = Assurance::numerical;
    family.representation = {synthesis::b04_c::exact_family_representation};
    StrategyConfiguration configuration;
    configuration.strategy = {"csl.synthesis.reach-back"};
    configuration.representation = family.representation;
    auto lineage = synthesis::strategy_a::detail::expected_b04_c_exact_lineage(resolved.identity());
    return {std::move(resolved), std::move(configuration), std::move(family), "1",
            std::move(lineage)};
}
}

TEST_CASE(
    "B04-C exact family is admitted by the compiled verifier against a prepared Strategy A request") {
    auto request = b04_c_request(b04_c_problem());
    REQUIRE(registry::detail::strategy_a_b04_c_exact_profile_valid(
        request.problem, request.family, request.configuration.representation));
    auto built = registry::detail::build_b04_c_exact_family(request);
    if (const auto *errors = std::get_if<Diagnostics>(&built))
        for (const auto &error : *errors)
            std::cerr << error.field << ": " << error.explanation << '\n';
    REQUIRE(std::holds_alternative<registry::detail::B04CExactFamilyBuild>(built));
    const auto &exact = std::get<registry::detail::B04CExactFamilyBuild>(built);
    CHECK(exact.objective_lower > 30.8985);
    CHECK(exact.objective_upper < 30.8995);
    const auto *payload =
        dynamic_cast<const synthesis::detail::b04_c::ExactFamilyPayload *>(exact.relation.get());
    REQUIRE(payload);
    std::vector<synthesis::detail::exact_rational::Rational> history(
        synthesis::detail::b04_c::history_dimension);
    const auto controls_offset = 4 * (synthesis::detail::b04_c::horizon + 1);
    for (std::size_t control = 0; control < synthesis::detail::b04_c::control_dimension; ++control)
        history[controls_offset + control] = payload->optimal_controls[control];
    synthesis::detail::exact_rational::Budget query_budget;
    query_budget.max_operations = 2'000'000;
    for (std::size_t stage = 0; stage <= synthesis::detail::b04_c::horizon; ++stage)
        for (std::size_t coordinate = 0; coordinate < 4; ++coordinate) {
            auto &state = history[stage * 4 + coordinate];
            state = payload->history_lift[stage].offset[coordinate];
            for (std::size_t control = 0; control < synthesis::detail::b04_c::control_dimension;
                 ++control) {
                synthesis::detail::exact_rational::Rational product, sum;
                REQUIRE(synthesis::detail::exact_rational::multiply(
                    payload->history_lift[stage].controls[coordinate][control],
                    payload->optimal_controls[control], product, query_budget));
                REQUIRE(synthesis::detail::exact_rational::add(state, product, sum, query_budget));
                state = std::move(sum);
            }
        }
    CHECK(payload->contains(history, query_budget) == synthesis::detail::b04_c::Membership::member);
    std::vector<std::string> numerators, denominators;
    numerators.reserve(history.size());
    denominators.reserve(history.size());
    for (const auto &value : history) {
        numerators.push_back(decimal(value.numerator));
        denominators.push_back(decimal(value.denominator));
    }
    std::vector<synthesis::b04_c::RationalCoordinate> public_history;
    public_history.reserve(history.size());
    for (std::size_t index = 0; index < history.size(); ++index)
        public_history.push_back(
            {numerators[index], denominators[index], history[index].binary_exponent});
    CHECK(synthesis::b04_c::contains_exact_history(
              JointRelation{{{4, 1, 0}, 16}, request.family.representation, exact.relation},
              public_history) == synthesis::b04_c::HistoryMembership::member);
    auto outside = history;
    synthesis::detail::exact_rational::Rational one, changed;
    REQUIRE(synthesis::detail::exact_rational::make_integer(1, one, query_budget));
    REQUIRE(synthesis::detail::exact_rational::add(outside[0], one, changed, query_budget));
    outside[0] = std::move(changed);
    CHECK(payload->contains(outside, query_budget) ==
          synthesis::detail::b04_c::Membership::not_member);
    const FamilyIdentity identity{
        request.problem.identity(),     request.family,           {{4, 1, 0}, 16},
        request.configuration.strategy, request.strategy_version, request.lineage};
    const SymbolicArgument derivation{
        "B04-C exact represented-dyadic KKT and full-history fiber",
        "All 100 hard inequalities are strictly feasible at the exact witness and the exact gradient of the convex weighted squared terminal objective is zero, proving global optimality. The positive weighted residual map is injective in terminal state, so the optimum terminal state is unique. The complete optimizer family is exactly the feasible 16-control polytope intersected with that terminal fiber and lifted affinely to all 84 canonical history coordinates. A separate exact feasible history lies in the rounding box of the published terminal row. The source variant remains B04-c-exact-dyadic-20261102; no historical reproduction claim is made."};
    const ClaimEvidence claim{request.problem.identity(), derivation};
    const OptimumEvidence optimum{claim,
                                  ObjectiveEvidence{ObjectiveBound{exact.objective_lower, claim},
                                                    ObjectiveBound{exact.objective_upper, claim}}};
    CompleteOptimalFamily family{
        {identity.coordinates, request.family.representation, exact.relation},
        optimum,
        {identity, RegisteredCompletenessEvidence{{"csl.verifier.strategy-a.b04-c-exact-dyadic"},
                                                  "1",
                                                  "B04-C-exact-dyadic-complete-family-v1"}},
        Assurance::numerical};
    CompleteFamilyProposal proposal{identity, std::move(family)};
    auto verifier = registry::detail::find_compiled_verifier(
        {"csl.verifier.strategy-a.b04-c-exact-dyadic"}, "1");
    REQUIRE(verifier);
    CHECK(verifier->verify(request, proposal).empty());

    auto tampered = proposal;
    std::get<RegisteredCompletenessEvidence>(tampered.family.completeness.support).proof = "forged";
    CHECK_FALSE(verifier->verify(request, tampered).empty());
    tampered = proposal;
    tampered.family.relation.coordinates.horizon = 15;
    CHECK_FALSE(verifier->verify(request, tampered).empty());
}
