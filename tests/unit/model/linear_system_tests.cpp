#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/model/linear_system.hpp>

#include <future>
#include <limits>
#include <type_traits>

using namespace csl;
using namespace csl::model;
static_assert(!std::is_default_constructible_v<LinearSystem>);

namespace {
template<class T, class... Errors> T accepted(std::variant<T, Errors...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
template<class T, class... Errors>
void rejected(const std::variant<T, Errors...>& result, const char* field,
              DiagnosticCode code = DiagnosticCode::invalid_input) {
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).code == code);
    CHECK(std::get<Diagnostic>(result).field == field);
}
template<class T> void stopped(const EvaluationResult<T>& result) {
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason == StopReason::numerical_failure);
    CHECK_FALSE(std::get<OperationStopped>(result).diagnostics.empty());
}
const Vector grid{10, 20, 40};
LinearStage coefficients(double a = 3) { return {{1,1,{a}}, {1,1,{2}}, {1,0,{}}, {-1}}; }
SystemModel authored() { return {{{1,1,0}, TimeDomain::discrete, coefficients()}, {}}; }
ObservationPoint pre(std::size_t k) { return {{k}, ObservationTiming::before_decision}; }
ObservationPoint post(std::size_t k) { return {{k}, ObservationTiming::after_decision}; }
ObservationStage output(double c = 2) {
    return {{1,1,{c}}, {1,1,{3}}, {1,1,{5}}, {1,1,{7}}, {11}};
}
SystemModel observed() {
    auto result = authored();
    result.dynamics.dimensions.external = 1;
    std::get<LinearStage>(result.dynamics.stages).E = {1,1,{4}};
    result.observations = {{output(), {{{0},post(0),post(0),StageIndex{0}}}}};
    return result;
}
ObservationStage state_only(std::size_t n, Vector map) {
    return {{1,n,std::move(map)}, {1,1,{0}}, {1,0,{}}, {1,0,{}}, {0}};
}
}

// Dropping A/B/offset or treating indexed coefficients as unordered breaks literals.
TEST_CASE("constant and indexed dynamics produce the literal trajectory") {
    auto input = authored();
    SUBCASE("constant") {}
    SUBCASE("indexed") { input.dynamics.stages = std::vector{coefficients(), coefficients()}; }
    const auto system = accepted(snapshot(input, grid));
    Vector x{2};
    Vector states{x[0]};
    x = accepted(system.step({0}, x, Vector{1}, {})); states.push_back(x[0]);
    x = accepted(system.step({1}, x, Vector{-2}, {})); states.push_back(x[0]);
    CHECK(states == Vector{2,7,16});
    CHECK(accepted(system.time({2})) == 40);
    CHECK(system.horizon() == 2);
    CHECK(system.dimensions().control == 1);
}

TEST_CASE("indexed dynamics preserve order and constant views retain one coefficient buffer") {
    auto input = authored();
    const auto constant = accepted(snapshot(input, grid));
    auto first = accepted(constant.stage({0}));
    auto second = accepted(constant.stage({1}));
    CHECK(std::get<numeric::DenseInput>(first.A.descriptor()).storage.data() ==
          std::get<numeric::DenseInput>(second.A.descriptor()).storage.data());
    input.dynamics.stages = std::vector{coefficients(0), coefficients(5)};
    const auto indexed = accepted(snapshot(input, grid));
    CHECK(accepted(indexed.step({0}, Vector{2}, Vector{1}, {})) == Vector{1});
    CHECK(accepted(indexed.step({1}, Vector{2}, Vector{1}, {})) == Vector{11});
}

TEST_CASE("singular and autonomous dynamics retain absent ports") {
    SystemModel input{{{2,0,0}, TimeDomain::discrete,
        LinearStage{{2,2,{0,0,0,1}}, {2,0,{}}, {2,0,{}}, {7,2}}}, {}};
    const auto system = accepted(snapshot(input, grid));
    CHECK(accepted(system.step({0}, Vector{9,3}, {}, {})) == Vector{7,5});
    CHECK(accepted(system.stage({0})).B.cols() == 0);
    rejected(system.step({0}, Vector{9,3}, Vector{0}, {}), "model.step.control");
}

TEST_CASE("rectangular inputs and nonsymmetric maps preserve row and column roles") {
    const LinearStage dynamics{{2,2,{1,2,3,4}},{2,3,{1,0,-1,0,2,1}},{2,1,{2,-3}},{5,-2}};
    const ObservationStage maps{{2,2,{1,2,3,4}},{2,3,{1,0,-1,0,2,1}},
        {2,1,{2,-3}},{2,2,{1,2,3,4}},{5,-2}};
    const SystemModel input{{{2,3,1},TimeDomain::discrete,dynamics},
        {{maps,{{{0},post(0),post(0),StageIndex{0}}}}}};
    const auto system = accepted(snapshot(input,grid));
    CHECK(accepted(system.step({0},Vector{2,-1},Vector{4,3,1},Vector{2})) == Vector{12,1});
    CHECK(accepted(system.observe({0},{0},Vector{2,-1},Vector{4,3,1},Vector{2},Vector{1,-1})).values == Vector{11,0});
}

// Swapping or omitting any observation map changes 21.
TEST_CASE("observation evaluates all maps with explicit source and event times") {
    const auto system = accepted(snapshot(observed(), grid));
    const auto value = accepted(system.observe({0},{0},Vector{2},Vector{1},Vector{2},Vector{-1}));
    CHECK(value.values == Vector{21});
    CHECK(value.metadata.state_time == 10);
    CHECK(value.metadata.measured_time == 20);
    CHECK(value.metadata.available_time == 20);
    CHECK(value.metadata.sample.input_stage->value == 0);
    CHECK(value.metadata.sample.measured_at.timing == ObservationTiming::after_decision);
    CHECK(accepted(system.sample_count({0})) == 1);
    CHECK(accepted(system.step({0},Vector{2},Vector{1},Vector{2})) == Vector{15});
}

TEST_CASE("sample order is authored order including delayed old state and historical inputs") {
    auto input = observed();
    input.observations[0] = {std::vector{output(2),output(4)}, {
        {{0},post(1),pre(2),StageIndex{0}},
        {{1},post(0),post(0),StageIndex{0}}}};
    const auto system = accepted(snapshot(input, grid));
    const auto delayed = accepted(system.observe({0},{0},Vector{2},Vector{1},Vector{2},Vector{-1}));
    CHECK(delayed.values == Vector{21});
    CHECK(delayed.metadata.state_time == 10);
    CHECK(delayed.metadata.measured_time == 40);
    CHECK(delayed.metadata.available_time == 40);
    const auto next = accepted(system.observe({0},{1},Vector{2},Vector{1},Vector{2},Vector{-1}));
    CHECK(next.values == Vector{25});
    CHECK(next.metadata.state_time == 20);
    CHECK(next.metadata.measured_time == 20);
}

TEST_CASE("full partial and absent observation channels remain distinct") {
    SystemModel input{{{2,1,0}, TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}}, {2,1,{0,0}}, {2,0,{}}, {0,0}}}, {}};
    const auto empty = accepted(snapshot(input, grid));
    CHECK(empty.channel_count() == 0);
    rejected(empty.observation({0},{0}), "model.observation.channel");
    input.observations = {
        {ObservationStage{{2,2,{1,0,0,1}}, {2,1,{0,0}}, {2,0,{}}, {2,0,{}}, {0,0}},
            {{{0},pre(0),pre(0),std::nullopt}}},
        {state_only(2,{0,1}), {{{0},pre(0),pre(0),std::nullopt}}}};
    const auto system = accepted(snapshot(input, grid));
    CHECK(accepted(system.observe({0},{0},Vector{8,13},{},{},{})).values == Vector{8,13});
    CHECK(accepted(system.observe({1},{0},Vector{8,13},{},{},{})).values == Vector{13});
    rejected(system.observe({1},{0},Vector{8,13},Vector{0},{},{}), "model.observe.control");
}

TEST_CASE("causality rejects unavailable inputs states and reversed equal-time events") {
    auto input = observed();
    auto& sample = input.observations[0].schedule[0];
    SUBCASE("current control before action") { sample.measured_at = pre(0); }
    SUBCASE("external only before action") {
        std::get<ObservationStage>(input.observations[0].coefficients).control_map.values[0] = 0;
        sample.measured_at = pre(0);
    }
    SUBCASE("next state before transition") { sample.state_stage = {1}; sample.measured_at = pre(0); }
    SUBCASE("availability precedes measurement") { sample.available_at = pre(0); }
    SUBCASE("equal physical time reversed causal order") {
        sample.measured_at = pre(1); sample.available_at = post(0);
    }
    rejected(snapshot(input, grid), "model.observation.causality");
}

TEST_CASE("equal physical times retain ordered post and next pre events") {
    auto input = observed();
    input.observations[0].schedule[0] = {{1},post(0),pre(1),StageIndex{0}};
    const auto system = accepted(snapshot(input, grid));
    const auto record = accepted(system.observation({0},{0}));
    CHECK(record.metadata.measured_time == 20);
    CHECK(record.metadata.available_time == 20);
    CHECK(record.metadata.sample.measured_at.timing == ObservationTiming::after_decision);
    CHECK(record.metadata.sample.available_at.timing == ObservationTiming::before_decision);
    CHECK(accepted(system.observe({0},{0},Vector{2},Vector{1},Vector{2},Vector{-1})).values == Vector{21});
}

TEST_CASE("zero horizon admits terminal observations without inventing actions") {
    auto input = authored();
    input.observations = {{state_only(1,{2}), {{{0},pre(0),pre(0),std::nullopt}}}};
    SUBCASE("constant") {}
    SUBCASE("empty indexed") { input.dynamics.stages = std::vector<LinearStage>{}; }
    const auto system = accepted(snapshot(input, Vector{5}));
    CHECK(system.horizon() == 0);
    CHECK(accepted(system.observe({0},{0},Vector{3},{},{},{})).values == Vector{6});
    rejected(system.step({0},Vector{3},Vector{0},{}), "model.stage");
    rejected(system.stage({0}), "model.stage");
    input.observations[0].schedule[0].available_at = post(0);
    rejected(snapshot(input, Vector{5}), "model.observation.schedule");
}

TEST_CASE("grid validation rejects absent duplicate decreasing or nonfinite times") {
    Vector times;
    SUBCASE("absent") {}
    SUBCASE("duplicate") { times = {1,1}; }
    SUBCASE("decreasing") { times = {2,1}; }
    SUBCASE("nan") { times = {std::numeric_limits<double>::quiet_NaN()}; }
    SUBCASE("infinite") { times = {0,std::numeric_limits<double>::infinity()}; }
    rejected(snapshot(authored(), times), "model.times");
}

TEST_CASE("continuous and unknown time domains are not discretized") {
    auto input = authored();
    input.dynamics.time_domain = TimeDomain::continuous;
    SUBCASE("unknown") { input.dynamics.time_domain = static_cast<TimeDomain>(99); }
    rejected(snapshot(input, grid), "model.time_domain", DiagnosticCode::unsupported);
}

TEST_CASE("malformed dynamics coefficients never publish a snapshot") {
    auto input = authored();
    SUBCASE("stage count") { input.dynamics.stages = std::vector{coefficients()}; }
    SUBCASE("A shape") { std::get<LinearStage>(input.dynamics.stages).A = {1,2,{1,2}}; }
    SUBCASE("B storage") { std::get<LinearStage>(input.dynamics.stages).B.values.clear(); }
    SUBCASE("E shape") { std::get<LinearStage>(input.dynamics.stages).E = {0,0,{}}; }
    SUBCASE("offset size") { std::get<LinearStage>(input.dynamics.stages).offset.clear(); }
    SUBCASE("coefficient nan") { std::get<LinearStage>(input.dynamics.stages).A.values[0] = std::numeric_limits<double>::quiet_NaN(); }
    SUBCASE("offset infinite") { std::get<LinearStage>(input.dynamics.stages).offset[0] = std::numeric_limits<double>::infinity(); }
    SUBCASE("shape product overflow") {
        input.dynamics.dimensions.state = std::numeric_limits<std::size_t>::max();
        std::get<LinearStage>(input.dynamics.stages).A = {input.dynamics.dimensions.state,input.dynamics.dimensions.state,{}};
    }
    rejected(snapshot(input, grid), "model.dynamics.coefficients");
}

TEST_CASE("observation shape count finiteness and declared input dependency are validated") {
    auto input = observed();
    auto& channel = input.observations[0];
    SUBCASE("count") { channel.coefficients = std::vector<ObservationStage>{}; }
    SUBCASE("C shape") { std::get<ObservationStage>(channel.coefficients).state_map.cols = 2; }
    SUBCASE("Du storage") { std::get<ObservationStage>(channel.coefficients).control_map.values.clear(); }
    SUBCASE("Dw shape") { std::get<ObservationStage>(channel.coefficients).external_map.cols = 0; }
    SUBCASE("F shape") { std::get<ObservationStage>(channel.coefficients).error_map.rows = 2; }
    SUBCASE("b shape") { std::get<ObservationStage>(channel.coefficients).offset.clear(); }
    SUBCASE("nonfinite") { std::get<ObservationStage>(channel.coefficients).error_map.values[0] = std::numeric_limits<double>::infinity(); }
    SUBCASE("changing dimensions") {
        channel.schedule.push_back(channel.schedule[0]);
        auto other = output(); other.error_map = {1,0,{}};
        channel.coefficients = std::vector{output(), other};
    }
    SUBCASE("undeclared feedthrough") { channel.schedule[0].input_stage.reset(); }
    rejected(snapshot(input, grid), "model.observation.coefficients");
}

TEST_CASE("invalid schedule indices and phases are rejected") {
    auto input = observed();
    auto& sample = input.observations[0].schedule[0];
    SUBCASE("state") { sample.state_stage = {3}; }
    SUBCASE("input") { sample.input_stage = StageIndex{2}; }
    SUBCASE("measured") { sample.measured_at = pre(3); }
    SUBCASE("available") { sample.available_at = post(2); }
    SUBCASE("unknown phase") { sample.measured_at.timing = static_cast<ObservationTiming>(99); }
    rejected(snapshot(input, grid), "model.observation.schedule");
}

TEST_CASE("empty observation providers and explicit zero dependency preserve metadata") {
    auto input = authored();
    input.observations = {{std::vector<ObservationStage>{}, {}}, {state_only(1,{2}), {}}};
    const auto empty = accepted(snapshot(input, grid));
    CHECK(accepted(empty.sample_count({0})) == 0);
    CHECK(accepted(empty.sample_count({1})) == 0);
    rejected(empty.observation({1},{0}), "model.observation.sample");
    input.observations[1].schedule = {{{0},post(0),post(0),StageIndex{0}}, {{1},post(0),pre(1),StageIndex{0}}};
    const auto system = accepted(snapshot(input, grid));
    CHECK(accepted(system.observe({1},{0},Vector{3},Vector{7},{},{})).values == Vector{6});
    CHECK(accepted(system.observation({1},{0})).metadata.sample.input_stage->value == 0);
    const auto first = accepted(system.observation({1},{0}));
    const auto second = accepted(system.observation({1},{1}));
    CHECK(std::get<numeric::DenseInput>(first.maps.state_map.descriptor()).storage.data() ==
          std::get<numeric::DenseInput>(second.maps.state_map.descriptor()).storage.data());
    rejected(system.observe({1},{0},Vector{3},{},{},{}), "model.observe.control");
}

TEST_CASE("evaluation rejects malformed caller vectors and checked lookups") {
    const auto system = accepted(snapshot(observed(), grid));
    rejected(system.time({3}), "model.time");
    rejected(system.stage({2}), "model.stage");
    rejected(system.sample_count({1}), "model.observation.channel");
    rejected(system.observe({1},{0},Vector{2},Vector{1},Vector{2},Vector{-1}), "model.observation.channel");
    rejected(system.observation({0},{1}), "model.observation.sample");
    rejected(system.step({0},{},Vector{1},Vector{2}), "model.step.state");
    rejected(system.step({0},Vector{2},{},Vector{2}), "model.step.control");
    rejected(system.step({0},Vector{2},Vector{1},{}), "model.step.external");
    rejected(system.observe({0},{0},{},Vector{1},Vector{2},Vector{-1}), "model.observe.state");
    rejected(system.observe({0},{0},Vector{2},{},Vector{2},Vector{-1}), "model.observe.control");
    rejected(system.observe({0},{0},Vector{2},Vector{1},{},Vector{-1}), "model.observe.external");
    rejected(system.observe({0},{0},Vector{2},Vector{1},Vector{2},{}), "model.observe.error");
    rejected(system.step({0},Vector{std::numeric_limits<double>::infinity()},Vector{1},Vector{2}), "model.step.state");
    rejected(system.observe({0},{0},Vector{2},Vector{1},Vector{2},Vector{std::numeric_limits<double>::quiet_NaN()}), "model.observe.error");
}

TEST_CASE("finite arithmetic overflow is a numerical stop and never invalid authored data") {
    const auto huge = std::numeric_limits<double>::max();
    auto input = observed();
    SUBCASE("dynamics product") {
        std::get<LinearStage>(input.dynamics.stages).A.values[0] = huge;
        stopped(accepted(snapshot(input,grid)).step({0},Vector{2},Vector{1},Vector{2}));
    }
    SUBCASE("dynamics sum") {
        auto& stage = std::get<LinearStage>(input.dynamics.stages);
        stage.A.values[0] = huge; stage.offset[0] = huge;
        stopped(accepted(snapshot(input,grid)).step({0},Vector{1},Vector{0},Vector{0}));
    }
    SUBCASE("observation product") {
        std::get<ObservationStage>(input.observations[0].coefficients).external_map.values[0] = huge;
        stopped(accepted(snapshot(input,grid)).observe({0},{0},Vector{2},Vector{1},Vector{2},Vector{-1}));
    }
    SUBCASE("observation sum") {
        auto& stage = std::get<ObservationStage>(input.observations[0].coefficients);
        stage.offset[0] = huge; stage.state_map.values[0] = huge;
        stopped(accepted(snapshot(input,grid)).observe({0},{0},Vector{1},Vector{0},Vector{0},Vector{0}));
    }
}

// Keeping moved buffers or borrowing producer storage instead of copying breaks this test.
TEST_CASE("snapshots and coefficient records survive mutable aliases and producer destruction") {
    auto system = [] {
        auto producer = observed();
        auto* a = std::get<LinearStage>(producer.dynamics.stages).A.values.data();
        auto* c = std::get<ObservationStage>(producer.observations[0].coefficients).state_map.values.data();
        auto moved = std::move(producer);
        Vector times = grid;
        auto retained = accepted(snapshot(std::move(moved),times));
        *a = 99; *c = 99; times[0] = -99;
        return retained;
    }();
    CHECK(accepted(system.step({0},Vector{2},Vector{1},Vector{2})) == Vector{15});
    CHECK(accepted(system.observe({0},{0},Vector{2},Vector{1},Vector{2},Vector{-1})).values == Vector{21});
    CHECK(accepted(system.time({0})) == 10);
    const auto records = [&] {
        auto local = system;
        return std::pair{accepted(local.stage({0})), accepted(local.observation({0},{0}))};
    }();
    auto copy = std::move(system); // source remains a valid retaining handle
    system = accepted(snapshot(authored(),grid));
    CHECK(records.first.A(0,0) == 3);
    CHECK(records.second.maps.external_map(0,0) == 5);
    auto left = std::async(std::launch::async,[copy] { return accepted(copy.step({0},Vector{2},Vector{1},Vector{2})); });
    auto right = std::async(std::launch::async,[copy] { return accepted(copy.step({0},Vector{3},Vector{1},Vector{2})); });
    CHECK(left.get() == Vector{15});
    CHECK(right.get() == Vector{18});
    auto moved_again = std::move(copy);
    CHECK(accepted(copy.step({0},Vector{2},Vector{1},Vector{2})) == Vector{15});
    CHECK(accepted(moved_again.step({0},Vector{2},Vector{1},Vector{2})) == Vector{15});
}

TEST_CASE("coefficient records and evaluated output outlive the final model handle") {
    const auto retained = [] {
        const auto local = accepted(snapshot(observed(),grid));
        return std::pair{accepted(local.stage({0})),accepted(local.observation({0},{0}))};
    }();
    CHECK(accepted(numeric::multiply(retained.first.A,accepted(numeric::snapshot_vector(Vector{2})))) == Vector{6});
    CHECK(accepted(numeric::multiply(retained.second.maps.external_map,accepted(numeric::snapshot_vector(Vector{2})))) == Vector{10});
    const auto value = [] {
        const auto local = accepted(snapshot(observed(),grid));
        return accepted(local.observe({0},{0},Vector{2},Vector{1},Vector{2},Vector{-1}));
    }();
    CHECK(value.values == Vector{21});
    CHECK(value.metadata.state_time == 10);
    CHECK(value.metadata.sample.available_at.stage.value == 0);
}
