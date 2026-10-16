#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/controllers/observed_replay.hpp>

using namespace csl;
using namespace csl::model;
using namespace csl::controllers;

namespace {
ObservationPoint pre(std::size_t k) { return {{k}, ObservationTiming::before_decision}; }
ObservationPoint post(std::size_t k) { return {{k}, ObservationTiming::after_decision}; }

LinearSystem system_with_partial_noisy_and_delayed_samples() {
    SystemModel authored{{{2,1,0},TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}},{2,1,{1,0}},{2,0,{}},{0,0}}},
        {
            {ObservationStage{{1,2,{1,0}},{1,1,{0}},{1,0,{}},{1,1,{1}},{0}},
                {{{0},pre(0),pre(0),std::nullopt}}},
            {ObservationStage{{1,2,{0,1}},{1,1,{0}},{1,0,{}},{1,0,{}},{0}},
                {{{1},post(0),pre(1),std::nullopt}}}
        }};
    auto result = snapshot(authored,Vector{0,1,2});
    REQUIRE(std::holds_alternative<LinearSystem>(result));
    return std::get<LinearSystem>(std::move(result));
}
}

// Releasing the delayed sample at after(0), or exposing x0[1] before its
// observation, changes the literal action and terminal state.
TEST_CASE("pre-decision estimates consume only released partial noisy history") {
    const auto system = system_with_partial_noisy_and_delayed_samples();
    ReplayInputs inputs{{1,7},{{},{}},{{{3}},{{}}}};
    const auto estimate=[](StageIndex, std::span<const ReleasedObservation> history) {
        return Vector{history.empty() ? 0.0 : history.back().value.values[0],0};
    };
    const auto decide=[](StageIndex stage,std::span<const ReleasedObservation> history,
        std::span<const double> estimate_value) {
        CHECK(history.size() == (stage.value == 0 ? 1u : 2u));
        return Vector{stage.value == 0 ? estimate_value[0]-3 : estimate_value[0]};
    };
    const auto result = replay_observed_policy(system,inputs,estimate,decide);
    REQUIRE(std::holds_alternative<ReplayRecord>(result));
    const auto& record=std::get<ReplayRecord>(result);
    CHECK(record.states == std::vector<Vector>{{1,7},{2,7},{9,7}});
    REQUIRE(record.decisions.size() == 2);
    CHECK(record.decisions[0].estimate == Vector{4,0});
    CHECK(record.decisions[0].action == Vector{1});
    CHECK(record.decisions[1].estimate == Vector{7,0});
    CHECK(record.decisions[1].action == Vector{7});
    CHECK(record.decisions[0].available.size() == 1);
    CHECK(record.decisions[1].available.size() == 2);
    CHECK(record.released[0].value.values == Vector{4});
    CHECK(record.released[1].value.values == Vector{7});
    CHECK(record.released[1].released_at.stage.value == 1);
    CHECK(record.released[1].released_at.timing == ObservationTiming::before_decision);
    CHECK(record.inputs.initial_state == Vector{1,7});
    CHECK(record.inputs.measurement_errors[0][0] == Vector{3});
}

TEST_CASE("no channel supplies no implicit full-state observation") {
    SystemModel authored{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}}, {}};
    const auto system=std::get<LinearSystem>(snapshot(authored,Vector{0,1}));
    const ReplayInputs inputs{{5},{{}}, {}};
    const auto result=replay_observed_policy(system,inputs,
        [](StageIndex,std::span<const ReleasedObservation> history) {
            CHECK(history.empty());
            return Vector{0};
        },
        [](StageIndex,std::span<const ReleasedObservation> history,std::span<const double>) {
            CHECK(history.empty());
            return Vector{2};
        });
    REQUIRE(std::holds_alternative<ReplayRecord>(result));
    const auto& record=std::get<ReplayRecord>(result);
    CHECK(record.states == std::vector<Vector>{{5},{7}});
    CHECK(record.released.empty());
}

TEST_CASE("malformed sampled noise is rejected without a positive evidence record") {
    const auto system=system_with_partial_noisy_and_delayed_samples();
    const ReplayInputs inputs{{1,7},{{},{}},{{{}},{{}}}};
    const auto result=replay_observed_policy(system,inputs,
        [](StageIndex,std::span<const ReleasedObservation>) { return Vector{0}; },
        [](StageIndex,std::span<const ReleasedObservation>,std::span<const double>) { return Vector{1}; });
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field == "model.observe.error");
}

TEST_CASE("missing estimator is a diagnostic before invoking controller") {
    SystemModel authored{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}}, {}};
    const auto system=std::get<LinearSystem>(snapshot(authored,Vector{0,1}));
    const ReplayInputs inputs{{5},{{}}, {}};
    const auto result=replay_observed_policy(system,inputs,Estimator{},
        [](StageIndex,std::span<const ReleasedObservation>,std::span<const double>) {
            return Vector{2};
        });
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field == "controllers.callbacks");
}
