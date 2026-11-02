#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/synthesis/b04_c_exact_family.hpp>
#include "synthesis/b04_c_exact_family.hpp"

using namespace csl::synthesis::detail::b04_c;
using namespace csl::synthesis::detail::exact_rational;

namespace {
ExactFamilyPayload trivial_family() {
    ExactFamilyPayload family;
    const Rational zero{};
    Rational one;
    one.numerator = csl::synthesis::detail::exact_h::exact_detail::from_u64(1);
    for (std::size_t row = 0; row < 100; ++row) {
        LinearRow inequality;
        inequality.coefficients.resize(control_dimension, zero);
        inequality.bound = one;
        if (row == 0)
            inequality.coefficients[0] = one;
        family.feasible_controls.push_back(std::move(inequality));
    }
    for (std::size_t coordinate = 0; coordinate < state_dimension; ++coordinate) {
        AffineEquality equality;
        equality.coefficients.resize(control_dimension, zero);
        equality.offset = zero;
        family.terminal_fiber.push_back(std::move(equality));
        family.unique_terminal[coordinate] = zero;
    }
    for (auto& stage : family.history_lift) {
        stage.offset.fill(zero);
        for (auto& row : stage.controls)
            row.fill(zero);
    }
    return family;
}
}

TEST_CASE("exact B04 family membership checks feasibility, fiber, and history lift") {
    auto family = trivial_family();
    Budget budget;
    std::vector<Rational> history(history_dimension);
    CHECK(family.contains(history, budget) == Membership::member);

    Rational one;
    REQUIRE(make_integer(2, one, budget));
    history[state_dimension * (horizon + 1)] = one;
    CHECK(family.contains(history, budget) == Membership::not_member);

    history[state_dimension * (horizon + 1)] = Rational{};
    history[0] = one;
    CHECK(family.contains(history, budget) == Membership::not_member);
}

TEST_CASE("exact B04 family membership rejects malformed relation and history shapes") {
    auto family = trivial_family();
    Budget budget;
    std::vector<Rational> history(history_dimension - 1);
    CHECK(family.contains(history, budget) == Membership::invalid_relation);
    history.resize(history_dimension);
    family.feasible_controls.pop_back();
    CHECK(family.contains(history, budget) == Membership::invalid_relation);
}

TEST_CASE("public B04 query parses exact rational full histories") {
    auto candidate = trivial_family();
    Budget budget;
    Rational one_third, one;
    REQUIRE(make_fraction(1, 3, one_third, budget));
    REQUIRE(make_integer(1, one, budget));
    candidate.terminal_fiber[0].coefficients[0] = one;
    candidate.unique_terminal[0] = one_third;
    candidate.history_lift[horizon].controls[0][0] = one;
    std::vector<Rational> exact_history(history_dimension);
    exact_history[horizon * state_dimension] = one_third;
    exact_history[state_dimension * (horizon + 1)] = one_third;
    Budget query_budget;
    const auto exact_result = candidate.contains(exact_history, query_budget);
    INFO("query operations=" << query_budget.operations << " max bits=" <<
        query_budget.maximum_integer_bits);
    CHECK(exact_result == Membership::member);
    auto family = std::make_shared<const ExactFamilyPayload>(std::move(candidate));
    const csl::JointRelation relation{
        {{state_dimension, 1, 0}, horizon},
        {csl::synthesis::b04_c::exact_family_representation}, family};
    std::vector<csl::synthesis::b04_c::RationalCoordinate> history(
        history_dimension, {"0", "1", 0});
    history[horizon * state_dimension] = {"1", "3", 0};
    history[state_dimension * (horizon + 1)] = {"1", "3", 0};
    CHECK(csl::synthesis::b04_c::contains_exact_history(relation, history) ==
        csl::synthesis::b04_c::HistoryMembership::member);

    history[horizon * state_dimension] = {"1", "2", 0};
    CHECK(csl::synthesis::b04_c::contains_exact_history(relation, history) ==
        csl::synthesis::b04_c::HistoryMembership::not_member);
    const csl::JointRelation unsupported{relation.coordinates,
        relation.representation, {}};
    CHECK(csl::synthesis::b04_c::contains_exact_history(unsupported, history) ==
        csl::synthesis::b04_c::HistoryMembership::unsupported_relation);

    const csl::JointRelation wrong_representation{relation.coordinates,
        {"csl.polyhedron.h"}, relation.payload};
    CHECK(csl::synthesis::b04_c::contains_exact_history(wrong_representation, history) ==
        csl::synthesis::b04_c::HistoryMembership::unsupported_relation);
    const csl::JointRelation wrong_horizon{{{state_dimension, 1, 0}, horizon - 1},
        relation.representation, relation.payload};
    CHECK(csl::synthesis::b04_c::contains_exact_history(wrong_horizon, history) ==
        csl::synthesis::b04_c::HistoryMembership::invalid_input);

    history.pop_back();
    CHECK(csl::synthesis::b04_c::contains_exact_history(relation, history) ==
        csl::synthesis::b04_c::HistoryMembership::invalid_input);
    history.resize(history_dimension, {"0", "1", 0});
    history[0] = {"malformed", "1", 0};
    CHECK(csl::synthesis::b04_c::contains_exact_history(relation, history) ==
        csl::synthesis::b04_c::HistoryMembership::invalid_input);

    const std::string oversized(2467, '9');
    history[0] = {oversized, "1", 0};
    CHECK(csl::synthesis::b04_c::contains_exact_history(relation, history) ==
        csl::synthesis::b04_c::HistoryMembership::resource_limit);
}
