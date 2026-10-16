#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/reachability/finite_feedback.hpp>

using namespace csl::reachability::finite_feedback;

TEST_CASE("one action must cover every disturbance successor") {
    const Game game{3, {
        Stage{{true,true,true},1,2,{{{StateIndex{1},StateIndex{2}}},{{StateIndex{1},StateIndex{1}}},{{StateIndex{1},StateIndex{1}}}}}
    }, {true,true,true}, {false,true,false}};
    const auto result=solve(game);
    REQUIRE(std::holds_alternative<Policy>(result));
    const auto& policy=std::get<Policy>(result);
    CHECK_FALSE(policy.winning[0][0]);
    CHECK(policy.admissible_actions[0][0].empty());
    CHECK(policy.winning[0][1]);
}

TEST_CASE("action cannot depend on current disturbance") {
    const Game game{3, {
        Stage{{true,true,true},2,2,{
            {{StateIndex{1},StateIndex{2}},{StateIndex{2},StateIndex{1}}},
            {{StateIndex{1},StateIndex{1}},{StateIndex{1},StateIndex{1}}},
            {{StateIndex{1},StateIndex{1}},{StateIndex{1},StateIndex{1}}}
        }}
    }, {true,true,true}, {false,true,false}};
    const auto result=solve(game);
    REQUIRE(std::holds_alternative<Policy>(result));
    CHECK_FALSE(std::get<Policy>(result).winning[0][0]);
}

TEST_CASE("all feasible actions are retained in catalogue order") {
    const Game game{2, {
        Stage{{true,true},2,1,{
            {{StateIndex{1}},{StateIndex{1}}},
            {{StateIndex{1}},{StateIndex{1}}}
        }}
    }, {true,true}, {false,true}};
    const auto result=solve(game);
    REQUIRE(std::holds_alternative<Policy>(result));
    const auto& policy=std::get<Policy>(result);
    CHECK(policy.winning[0][0]);
    CHECK(policy.admissible_actions[0][0]==std::vector<ActionIndex>{ActionIndex{0},ActionIndex{1}});
}

TEST_CASE("backward recursion permits a later action after observing the next state") {
    const Game game{4, {
        Stage{{true,true,true,true},1,2,{
            {{StateIndex{1},StateIndex{2}}},{{StateIndex{3},StateIndex{3}}},
            {{StateIndex{3},StateIndex{3}}},{{StateIndex{3},StateIndex{3}}}
        }},
        Stage{{true,true,true,true},2,1,{
            {{StateIndex{0}},{StateIndex{0}}},
            {{StateIndex{3}},{StateIndex{0}}},
            {{StateIndex{0}},{StateIndex{3}}},
            {{StateIndex{0}},{StateIndex{0}}}
        }}
    }, {true,true,true,true}, {false,false,false,true}};
    const auto result=solve(game);
    REQUIRE(std::holds_alternative<Policy>(result));
    const auto& policy=std::get<Policy>(result);
    CHECK(policy.winning[0][0]);
    CHECK(policy.admissible_actions[0][0]==std::vector<ActionIndex>{ActionIndex{0}});
    CHECK(policy.admissible_actions[1][1]==std::vector<ActionIndex>{ActionIndex{0}});
    CHECK(policy.admissible_actions[1][2]==std::vector<ActionIndex>{ActionIndex{1}});
}

TEST_CASE("empty action catalogue produces an empty predecessor") {
    const Game game{2, {Stage{{true,true},0,1,{{},{}}}}, {true,true}, {false,true}};
    const auto result=solve(game);
    REQUIRE(std::holds_alternative<Policy>(result));
    CHECK(std::get<Policy>(result).winning[0]==std::vector<bool>{false,false});
    CHECK(std::get<Policy>(result).winning[1]==std::vector<bool>{false,true});
}

TEST_CASE("empty disturbance domain and invalid successor state are rejected") {
    const Game empty_disturbance{1,{Stage{{true},1,0,{{{}}}}},{true},{true}};
    const auto empty_result=solve(empty_disturbance);
    REQUIRE(std::holds_alternative<csl::Diagnostic>(empty_result));
    CHECK(std::get<csl::Diagnostic>(empty_result).code==csl::DiagnosticCode::invalid_input);

    const Game invalid_successor{1,{Stage{{true},1,1,{{{StateIndex{1}}}}}},{true},{true}};
    const auto invalid_result=solve(invalid_successor);
    REQUIRE(std::holds_alternative<csl::Diagnostic>(invalid_result));
    CHECK(std::get<csl::Diagnostic>(invalid_result).code==csl::DiagnosticCode::invalid_input);
}
