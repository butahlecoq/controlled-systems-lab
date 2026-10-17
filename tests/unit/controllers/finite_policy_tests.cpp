#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/controllers/finite_policy.hpp>

using namespace csl;
using namespace csl::model;
using namespace csl::controllers;

namespace {
ObservationPoint before(std::size_t stage) {
    return {{stage}, ObservationTiming::before_decision};
}

ReleasedObservation observed(std::size_t channel, std::size_t sample,
    std::size_t stage, Vector values) {
    const ObservationSample sample_metadata{{stage}, before(stage), before(stage), std::nullopt};
    const ObservationMetadata metadata{sample_metadata, static_cast<double>(stage),
        static_cast<double>(stage), static_cast<double>(stage)};
    return {{channel}, {sample}, before(stage), {std::move(values), metadata}};
}

LinearSystem scalar_sensor() {
    SystemModel authored{{{1, 1, 0}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{0}}, {1,0,{}}, {0}}},
        {{ObservationStage{{1,1,{1}}, {1,1,{0}}, {1,0,{}}, {1,0,{}}, {0}},
            {{{0}, before(0), before(0), std::nullopt}}}}};
    auto result = snapshot(authored, Vector{0,1});
    REQUIRE(std::holds_alternative<LinearSystem>(result));
    return std::get<LinearSystem>(std::move(result));
}

LinearSystem partial_sensor() {
    SystemModel authored{{{2, 1, 0}, TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}}, {2,1,{0,0}}, {2,0,{}}, {0,0}}},
        {{ObservationStage{{1,2,{1,0}}, {1,1,{0}}, {1,0,{}}, {1,0,{}}, {0}},
            {{{0}, before(0), before(0), std::nullopt}}}}};
    auto result = snapshot(authored, Vector{0,1});
    REQUIRE(std::holds_alternative<LinearSystem>(result));
    return std::get<LinearSystem>(std::move(result));
}

ReplayInputs scenario(Vector initial) {
    return {std::move(initial), {{}}, {{{}}}};
}
}

TEST_CASE("finite observation policy rejects conflicting actions for one history") {
    const auto history = std::vector<ReleasedObservation>{observed(0, 0, 0, {3})};
    auto result = make_finite_observation_policy({
        {{0}, history, {1}},
        {{0}, history, {2}}
    });
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field == "controllers.policy.nonanticipativity");
}

TEST_CASE("finite universal policy reuses one action for indistinguishable initial states") {
    const auto system = partial_sensor();
    const auto history = std::vector<ReleasedObservation>{observed(0, 0, 0, {0})};
    auto built = make_finite_observation_policy({{{0}, history, {4}}});
    REQUIRE(std::holds_alternative<FiniteObservationPolicy>(built));

    const FinitePolicyFamilyRequest request{SetQuantifier::universal,
        {scenario({0,2}), scenario({0,9})}};
    const auto result = replay_finite_policy_family(system, request,
        std::get<FiniteObservationPolicy>(built));
    REQUIRE(std::holds_alternative<FinitePolicyFamilyEvidence>(result));
    const auto& evidence = std::get<FinitePolicyFamilyEvidence>(result);
    CHECK(evidence.initial_quantifier == SetQuantifier::universal);
    REQUIRE(evidence.scenarios.size() == 2);
    CHECK(evidence.scenarios[0].inputs.initial_state == Vector{0,2});
    CHECK(evidence.scenarios[1].inputs.initial_state == Vector{0,9});
    CHECK(evidence.scenarios[0].decisions[0].action == Vector{4});
    CHECK(evidence.scenarios[1].decisions[0].action == Vector{4});
    CHECK(evidence.scenarios[0].decisions[0].available[0].value.values == Vector{0});
    CHECK(evidence.scenarios[1].decisions[0].available[0].value.values == Vector{0});
}

TEST_CASE("finite policy may branch after a released observation distinguishes scenarios") {
    const auto system = scalar_sensor();
    auto built = make_finite_observation_policy({
        {{0}, {observed(0, 0, 0, {1})}, {-2}},
        {{0}, {observed(0, 0, 0, {5})}, {7}}
    });
    REQUIRE(std::holds_alternative<FiniteObservationPolicy>(built));

    const FinitePolicyFamilyRequest request{SetQuantifier::existential,
        {scenario({1}), scenario({5})}};
    const auto result = replay_finite_policy_family(system, request,
        std::get<FiniteObservationPolicy>(built));
    REQUIRE(std::holds_alternative<FinitePolicyFamilyEvidence>(result));
    const auto& evidence = std::get<FinitePolicyFamilyEvidence>(result);
    CHECK(evidence.initial_quantifier == SetQuantifier::existential);
    REQUIRE(evidence.scenarios.size() == 2);
    CHECK(evidence.scenarios[0].decisions[0].action == Vector{-2});
    CHECK(evidence.scenarios[1].decisions[0].action == Vector{7});
}

TEST_CASE("finite policy evaluation rejects unspecified quantifiers and uncovered histories") {
    const auto system = scalar_sensor();
    auto empty_policy = make_finite_observation_policy({});
    REQUIRE(std::holds_alternative<FiniteObservationPolicy>(empty_policy));

    const FinitePolicyFamilyRequest unspecified{SetQuantifier::unspecified,
        {scenario({1})}};
    auto result = replay_finite_policy_family(system, unspecified,
        std::get<FiniteObservationPolicy>(empty_policy));
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field == "controllers.policy.initial_quantifier");

    const FinitePolicyFamilyRequest explicit_request{SetQuantifier::universal,
        {scenario({1})}};
    result = replay_finite_policy_family(system, explicit_request,
        std::get<FiniteObservationPolicy>(empty_policy));
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field == "controllers.policy.missing_rule");
}
