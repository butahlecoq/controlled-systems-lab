#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/optimization/finite_causal_minimax.hpp>

#include <limits>
#include <variant>

namespace causal = csl::optimization::finite_causal_minimax;

namespace {
causal::Options exact{0.0, 0.0};

causal::Game strict_gap_game() {
    // Exact L13 finite-catalogue fixture: fixed-plan value 2, causal value 1.
    causal::Stage first{1, 2, 3, {true},
        {{{causal::StateId{0}, causal::StateId{1}, causal::StateId{2}},
          {causal::StateId{3}, causal::StateId{4}, causal::StateId{5}}}}};
    causal::Stage second{6, 2, 1, std::vector<bool>(6, true),
        {{{causal::StateId{0}}, {causal::StateId{1}}},
         {{causal::StateId{2}}, {causal::StateId{3}}},
         {{causal::StateId{4}}, {causal::StateId{5}}},
         {{causal::StateId{6}}, {causal::StateId{7}}},
         {{causal::StateId{8}}, {causal::StateId{9}}},
         {{causal::StateId{10}}, {causal::StateId{11}}}}};
    return {{first, second},
        {12, std::vector<bool>(12, true), {4.0, 0.0, 1.0, 1.0, 0.0, 4.0,
                                            2.0, 2.0, 1.0, 5.0, 2.0, 10.0}},
        causal::StateId{0}};
}

causal::Game unsafe_branch_game() {
    causal::Stage stage{1, 1, 2, {true},
        {{{causal::StateId{0}, causal::StateId{1}}}}};
    return {{stage}, {2, {true, false}, {0.0, 0.0}}, causal::StateId{0}};
}

causal::Game tied_actions_game() {
    causal::Stage stage{1, 3, 1, {true},
        {{{causal::StateId{0}}, {causal::StateId{0}}, {causal::StateId{0}}}}};
    return {{stage}, {1, {true}, {2.0}}, causal::StateId{0}};
}

TEST_CASE("finite causal minimax separates a causal policy from a fixed plan") {
    const auto outcome = causal::solve(strict_gap_game(), exact);
    REQUIRE(std::holds_alternative<causal::Result>(outcome));
    const auto& result = std::get<causal::Result>(outcome);
    CHECK(result.initial().feasible);
    CHECK(result.initial().value == doctest::Approx(1.0));
    REQUIRE(result.initial().optimal_actions.size() == 1);
    CHECK(result.initial().optimal_actions[0] == causal::ActionId{0});
}

TEST_CASE("a causal action cannot depend on the current disturbance") {
    // Each action reaches one safe and one unsafe terminal state. Since the
    // action precedes the disturbance, no robust action exists.
    causal::Stage stage{1, 2, 2, {true},
        {{{causal::StateId{0}, causal::StateId{1}},
          {causal::StateId{1}, causal::StateId{0}}}}};
    causal::Game game{{stage}, {2, {true, false}, {0.0, 0.0}}, causal::StateId{0}};
    const auto outcome = causal::solve(game, exact);
    REQUIRE(std::holds_alternative<causal::Result>(outcome));
    const auto& result = std::get<causal::Result>(outcome);
    CHECK_FALSE(result.initial().feasible);
    CHECK(result.initial().optimal_actions.empty());
}

TEST_CASE("one unsafe disturbance branch rejects its action") {
    const auto outcome = causal::solve(unsafe_branch_game(), exact);
    REQUIRE(std::holds_alternative<causal::Result>(outcome));
    const auto& result = std::get<causal::Result>(outcome);
    CHECK_FALSE(result.initial().feasible);
}

TEST_CASE("all tied optimal actions are retained") {
    const auto outcome = causal::solve(tied_actions_game(), exact);
    REQUIRE(std::holds_alternative<causal::Result>(outcome));
    const auto& result = std::get<causal::Result>(outcome);
    REQUIRE(result.initial().optimal_actions.size() == 3);
    CHECK(result.initial().optimal_actions[0] == causal::ActionId{0});
    CHECK(result.initial().optimal_actions[1] == causal::ActionId{1});
    CHECK(result.initial().optimal_actions[2] == causal::ActionId{2});
}

TEST_CASE("absolute and relative tolerance classify near-optimal actions") {
    auto game = tied_actions_game();
    game.terminal.cost[0] = 2.0 + 1e-7;
    game.terminal.cost.push_back(2.0);
    game.terminal.safe_states.push_back(true);
    game.terminal.state_count = 2;
    game.stages[0].next_state[0][1][0] = causal::StateId{1};
    const auto outcome = causal::solve(game, {0.0, 1e-6});
    REQUIRE(std::holds_alternative<causal::Result>(outcome));
    const auto& result = std::get<causal::Result>(outcome);
    CHECK(result.initial().value == doctest::Approx(2.0));
    CHECK(result.initial().optimal_actions.size() == 3);
}

TEST_CASE("invalid transition dimensions and nonfinite costs are rejected") {
    auto game = tied_actions_game();
    game.stages[0].next_state[0].pop_back();
    CHECK(std::holds_alternative<csl::Diagnostic>(causal::solve(game, exact)));

    game = tied_actions_game();
    game.terminal.cost[0] = std::numeric_limits<double>::quiet_NaN();
    CHECK(std::holds_alternative<csl::Diagnostic>(causal::solve(game, exact)));
}
}
