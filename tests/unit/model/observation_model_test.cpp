#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/model/linear_system.hpp>

#include <limits>

using namespace csl;
using namespace csl::model;

namespace {
template<class T, class... Errors> T accepted(std::variant<T, Errors...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
template<class T, class... Errors>
void rejected(const std::variant<T, Errors...>& result, const char* field) {
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).code == DiagnosticCode::invalid_input);
    CHECK(std::get<Diagnostic>(result).field == field);
}
ObservationPoint pre(std::size_t k) { return {{k},ObservationTiming::before_decision}; }
ObservationPoint post(std::size_t k) { return {{k},ObservationTiming::after_decision}; }
ObservationStage full() {
    return {{2,2,{1,0,0,1}},{2,1,{0,0}},{2,1,{0,0}},{2,0,{}},{0,0}};
}
ObservationStage partial() {
    return {{1,2,{0,1}},{1,1,{0}},{1,1,{0}},{1,1,{2}},{5}};
}
ObservationStage all_terms() {
    return {{2,2,{2,-1,1,3}},{2,1,{3,-2}},{2,1,{-1,5}},
        {2,2,{1,2,-3,1}},{7,-4}};
}
SystemModel dynamics() {
    return {{{2,1,1},TimeDomain::discrete,LinearStage{
        {2,2,{2,-1,0,3}},{2,1,{1,-2}},{2,1,{4,1}},{-1,5}}}, {}};
}
SystemModel observed() {
    auto input = dynamics();
    input.observations = {{all_terms(),{{{0},post(0),post(0),StageIndex{0}}}}};
    return input;
}
const Vector grid{5,11,23};
void times(const ObservationMetadata& metadata, double state, double measured, double available) {
    CHECK(metadata.state_time == state);
    CHECK(metadata.measured_time == measured);
    CHECK(metadata.available_time == available);
}
}

// Swapping channels, dropping b/F or treating a partial output as identity breaks literals.
TEST_CASE("full partial and noisy channels produce their own independent values") {
    auto input = observed();
    input.observations.insert(input.observations.begin(),
        Observation{partial(),{{{0},pre(0),pre(0),std::nullopt}}});
    input.observations.insert(input.observations.begin(),
        Observation{full(),{{{0},pre(0),pre(0),std::nullopt}}});
    const auto system = accepted(snapshot(input,grid));
    CHECK(system.channel_count() == 3);
    CHECK(accepted(system.sample_count({0})) == 1);
    CHECK(accepted(system.sample_count({1})) == 1);
    CHECK(accepted(system.sample_count({2})) == 1);
    CHECK(accepted(system.observe({0},{0},Vector{3,-2},{},{},{})).values == Vector{3,-2});
    CHECK(accepted(system.observe({1},{0},Vector{3,-2},{},{},Vector{3})).values == Vector{9});
    CHECK(accepted(system.observe({1},{0},Vector{3,-2},{},{},Vector{0})).values == Vector{3});
    CHECK(accepted(system.step({0},Vector{3,-2},Vector{-1},Vector{2})) == Vector{14,3});
    CHECK(accepted(system.observe({2},{0},Vector{3,-2},Vector{-1},Vector{2},Vector{4,-3})).values == Vector{8,-10});
    CHECK(accepted(system.observe({2},{0},Vector{3,-2},Vector{-1},Vector{2},Vector{0,0})).values == Vector{10,5});
    CHECK(accepted(system.step({0},Vector{3,-2},Vector{-1},Vector{2})) == Vector{14,3});
}

TEST_CASE("absence grants no implicit full channel and noiseless partial remains partial") {
    auto input = dynamics();
    const auto absent = accepted(snapshot(input,grid));
    CHECK(absent.channel_count() == 0);
    rejected(absent.sample_count({0}),"model.observation.channel");
    rejected(absent.observation({0},{0}),"model.observation.channel");
    rejected(absent.observe({0},{0},Vector{3,-2},{},{},{}),"model.observation.channel");
    auto maps = partial(); maps.error_map = {1,0,{}}; maps.offset = {0};
    input.observations = {
        {full(),{{{0},pre(0),pre(0),std::nullopt}}},
        {maps,{{{0},pre(0),pre(0),std::nullopt}}}};
    const auto explicit_channels = accepted(snapshot(input,grid));
    CHECK(explicit_channels.channel_count() == 2);
    CHECK(accepted(explicit_channels.observe({0},{0},Vector{3,-2},{},{},{})).values == Vector{3,-2});
    CHECK(accepted(explicit_channels.observe({1},{0},Vector{3,-2},{},{},{})).values == Vector{-2});
}

TEST_CASE("constant and sample indexed observation providers each match literal values") {
    for (bool indexed : {false,true}) {
        CAPTURE(indexed);
        auto input = observed();
        auto& channel = input.observations[0];
        channel.schedule.push_back({{0},post(1),pre(2),StageIndex{0}});
        if (indexed) channel.coefficients = std::vector{all_terms(),all_terms()};
        const auto system = accepted(snapshot(input,grid));
        CHECK(accepted(system.sample_count({0})) == 2);
        CHECK(accepted(system.observe({0},{0},Vector{3,-2},Vector{-1},Vector{2},Vector{4,-3})).values == Vector{8,-10});
        const auto delayed = accepted(system.observe({0},{1},Vector{3,-2},Vector{-1},Vector{2},Vector{4,-3}));
        CHECK(delayed.values == Vector{8,-10});
        times(delayed.metadata,5,23,23);
        CHECK(delayed.metadata.sample.state_stage.value == 0);
        REQUIRE(delayed.metadata.sample.input_stage.has_value());
        CHECK(delayed.metadata.sample.input_stage->value == 0);
        CHECK(delayed.metadata.sample.measured_at.stage.value == 1);
        CHECK(delayed.metadata.sample.measured_at.timing == ObservationTiming::after_decision);
        CHECK(delayed.metadata.sample.available_at.stage.value == 2);
        CHECK(delayed.metadata.sample.available_at.timing == ObservationTiming::before_decision);
    }
}

// Sorting by timestamp or using state stage as coefficient index changes 8/-12.
TEST_CASE("sample indexed coefficients retain authored reverse chronological order") {
    auto input = dynamics();
    const ObservationStage late{{1,2,{1,-2}},{1,1,{0}},{1,1,{0}},{1,0,{}},{3}};
    const ObservationStage early{{1,2,{-2,1}},{1,1,{0}},{1,1,{0}},{1,0,{}},{-4}};
    input.observations = {{std::vector{late,early}, {
        {{0},post(1),pre(2),std::nullopt},
        {{1},post(0),post(0),std::nullopt}}}};
    const auto system = accepted(snapshot(input,grid));
    const auto delayed = accepted(system.observe({0},{0},Vector{1,-2},{},{},{}));
    const auto earlier = accepted(system.observe({0},{1},Vector{1,-6},{},{},{}));
    CHECK(delayed.values == Vector{8});
    CHECK(earlier.values == Vector{-12});
    times(delayed.metadata,5,23,23);
    times(earlier.metadata,11,11,11);
    CHECK(delayed.metadata.sample.state_stage.value == 0);
    CHECK(earlier.metadata.sample.state_stage.value == 1);
    CHECK(delayed.metadata.sample.measured_at.stage.value == 1);
    CHECK(earlier.metadata.sample.measured_at.stage.value == 0);
}

TEST_CASE("current input release and next state release use explicit event phases") {
    auto input = observed();
    SUBCASE("unavailable current control") { input.observations[0].schedule[0].measured_at = pre(0); }
    SUBCASE("unavailable external only") {
        std::get<ObservationStage>(input.observations[0].coefficients).control_map.values = {0,0};
        input.observations[0].schedule[0].measured_at = pre(0);
    }
    SUBCASE("zero maps retain declared input dependency") {
        input.observations[0].coefficients = full();
        input.observations[0].schedule[0].measured_at = pre(0);
    }
    SUBCASE("next state before transition") {
        input.observations[0].coefficients = full();
        input.observations[0].schedule[0] = {{1},pre(0),post(0),std::nullopt};
    }
    rejected(snapshot(input,grid),"model.observation.causality");
    const auto valid = accepted(snapshot(observed(),grid));
    CHECK(accepted(valid.observe({0},{0},Vector{3,-2},Vector{-1},Vector{2},Vector{4,-3})).values == Vector{8,-10});
}

TEST_CASE("post transition and next pre events share time but keep their causal order") {
    auto input = observed();
    input.observations[0].schedule[0].available_at = pre(1);
    const auto system = accepted(snapshot(input,grid));
    const auto value = accepted(system.observe({0},{0},Vector{3,-2},Vector{-1},Vector{2},Vector{4,-3}));
    CHECK(value.values == Vector{8,-10});
    times(value.metadata,5,11,11);
    CHECK(value.metadata.sample.state_stage.value == 0);
    REQUIRE(value.metadata.sample.input_stage.has_value());
    CHECK(value.metadata.sample.input_stage->value == 0);
    CHECK(value.metadata.sample.measured_at.stage.value == 0);
    CHECK(value.metadata.sample.measured_at.timing == ObservationTiming::after_decision);
    CHECK(value.metadata.sample.available_at.stage.value == 1);
    CHECK(value.metadata.sample.available_at.timing == ObservationTiming::before_decision);
    auto& sample = input.observations[0].schedule[0];
    sample.measured_at = pre(1); sample.available_at = post(0);
    rejected(snapshot(input,grid),"model.observation.causality");
}

TEST_CASE("next state and terminal state can be observed after their release") {
    auto input = dynamics();
    input.observations = {{full(),{
        {{1},post(0),post(0),std::nullopt},
        {{2},pre(2),pre(2),std::nullopt}}}};
    const auto system = accepted(snapshot(input,grid));
    const auto next = accepted(system.observe({0},{0},Vector{1,-6},{},{},{}));
    CHECK(next.values == Vector{1,-6});
    times(next.metadata,11,11,11);
    CHECK(next.metadata.sample.state_stage.value == 1);
    CHECK(next.metadata.sample.measured_at.stage.value == 0);
    CHECK(next.metadata.sample.measured_at.timing == ObservationTiming::after_decision);
    const auto terminal = accepted(system.observe({0},{1},Vector{-3,-16},{},{},{}));
    CHECK(terminal.values == Vector{-3,-16});
    times(terminal.metadata,23,23,23);
    CHECK(terminal.metadata.sample.measured_at.stage.value == 2);
    CHECK(terminal.metadata.sample.measured_at.timing == ObservationTiming::before_decision);
    CHECK_FALSE(terminal.metadata.sample.input_stage.has_value());
}

TEST_CASE("undeclared feedthrough rejects while no source requires empty input spans") {
    auto input = observed();
    input.observations[0].schedule[0].input_stage.reset();
    rejected(snapshot(input,grid),"model.observation.coefficients");
    input.observations[0].coefficients = full();
    input.observations[0].schedule[0] = {{0},pre(0),pre(0),std::nullopt};
    const auto system = accepted(snapshot(input,grid));
    CHECK(accepted(system.observe({0},{0},Vector{3,-2},{},{},{})).values == Vector{3,-2});
    rejected(system.observe({0},{0},Vector{3,-2},Vector{0},{},{}),"model.observe.control");
    rejected(system.observe({0},{0},Vector{3,-2},{},Vector{0},{}),"model.observe.external");
    input.observations[0].schedule[0] = {{0},post(0),post(0),StageIndex{0}};
    const auto declared = accepted(snapshot(input,grid));
    CHECK(accepted(declared.observe({0},{0},Vector{3,-2},Vector{0},Vector{0},{})).values == Vector{3,-2});
    rejected(declared.observe({0},{0},Vector{3,-2},{},Vector{0},{}),"model.observe.control");
    rejected(declared.observe({0},{0},Vector{3,-2},Vector{0},{},{}),"model.observe.external");
}

TEST_CASE("malformed observation maps are rejected for constant and indexed coefficients") {
    for (bool indexed : {false,true}) {
        for (int fault = 0; fault != 6; ++fault) {
            CAPTURE(indexed);
            CAPTURE(fault);
            auto maps = all_terms();
            switch (fault) {
            case 0: maps.state_map = {2,1,{2,1}}; break;
            case 1: maps.control_map = {2,2,{3,0,-2,0}}; break;
            case 2: maps.external_map = {2,0,{}}; break;
            case 3: maps.error_map = {1,2,{1,2}}; break;
            case 4: maps.offset = {7}; break;
            case 5: maps.error_map.values.pop_back(); break;
            }
            auto input = observed();
            if (indexed) input.observations[0].coefficients = std::vector{maps};
            else input.observations[0].coefficients = maps;
            rejected(snapshot(input,grid),"model.observation.coefficients");
        }
    }
}

TEST_CASE("sample counts and channel output and error dimensions are validated") {
    auto input = observed();
    auto& channel = input.observations[0];
    SUBCASE("no record") { channel.coefficients = std::vector<ObservationStage>{}; }
    SUBCASE("extra record") { channel.coefficients = std::vector{all_terms(),all_terms()}; }
    SUBCASE("changing output dimension") {
        channel.schedule.push_back(channel.schedule[0]);
        channel.coefficients = std::vector{all_terms(),partial()};
    }
    SUBCASE("changing error dimension") {
        auto maps = all_terms(); maps.error_map = {2,0,{}};
        channel.schedule.push_back(channel.schedule[0]);
        channel.coefficients = std::vector{all_terms(),maps};
    }
    SUBCASE("nonfinite offset") {
        std::get<ObservationStage>(channel.coefficients).offset[0] = std::numeric_limits<double>::infinity();
    }
    rejected(snapshot(input,grid),"model.observation.coefficients");
}

TEST_CASE("schedule stage and phase bounds are checked before publication") {
    auto input = observed();
    auto& sample = input.observations[0].schedule[0];
    SUBCASE("state beyond terminal") { sample.state_stage = {3}; }
    SUBCASE("terminal input") { sample.input_stage = StageIndex{2}; }
    SUBCASE("measurement beyond terminal") { sample.measured_at = pre(3); }
    SUBCASE("terminal post event") { sample.available_at = post(2); }
    SUBCASE("unknown phase") { sample.measured_at.timing = static_cast<ObservationTiming>(99); }
    SUBCASE("maximum state index") { sample.state_stage = {std::numeric_limits<std::size_t>::max()}; }
    rejected(snapshot(input,grid),"model.observation.schedule");
}

TEST_CASE("checked lookup and each observation operand reject malformed calls") {
    const auto system = accepted(snapshot(observed(),grid));
    CHECK(accepted(system.observe({0},{0},Vector{3,-2},Vector{-1},Vector{2},Vector{4,-3})).values == Vector{8,-10});
    rejected(system.sample_count({1}),"model.observation.channel");
    rejected(system.observation({0},{1}),"model.observation.sample");
    rejected(system.observe({1},{0},Vector{3,-2},Vector{-1},Vector{2},Vector{4,-3}),"model.observation.channel");
    rejected(system.observe({0},{1},Vector{3,-2},Vector{-1},Vector{2},Vector{4,-3}),"model.observation.sample");
    for (const Vector& x : {Vector{3},Vector{3,-2,0},Vector{3,std::numeric_limits<double>::quiet_NaN()}})
        rejected(system.observe({0},{0},x,Vector{-1},Vector{2},Vector{4,-3}),"model.observe.state");
    for (const Vector& u : {Vector{},Vector{-1,0},Vector{std::numeric_limits<double>::infinity()}})
        rejected(system.observe({0},{0},Vector{3,-2},u,Vector{2},Vector{4,-3}),"model.observe.control");
    for (const Vector& w : {Vector{},Vector{2,0},Vector{std::numeric_limits<double>::quiet_NaN()}})
        rejected(system.observe({0},{0},Vector{3,-2},Vector{-1},w,Vector{4,-3}),"model.observe.external");
    for (const Vector& v : {Vector{4},Vector{4,-3,0},Vector{4,std::numeric_limits<double>::infinity()}})
        rejected(system.observe({0},{0},Vector{3,-2},Vector{-1},Vector{2},v),"model.observe.error");
}

TEST_CASE("zero horizon supports only terminal pre observations without input sources") {
    auto input = dynamics();
    input.observations = {{full(),{{{0},pre(0),pre(0),std::nullopt}}}};
    const auto system = accepted(snapshot(input,Vector{5}));
    const auto terminal = accepted(system.observe({0},{0},Vector{3,-2},{},{},{}));
    CHECK(terminal.values == Vector{3,-2});
    times(terminal.metadata,5,5,5);
    CHECK(system.horizon() == 0);
    rejected(system.step({0},Vector{3,-2},Vector{0},Vector{0}),"model.stage");
    SUBCASE("post measurement") { input.observations[0].schedule[0].measured_at = post(0); }
    SUBCASE("post availability") { input.observations[0].schedule[0].available_at = post(0); }
    SUBCASE("input dependency") { input.observations[0].schedule[0].input_stage = StageIndex{0}; }
    rejected(snapshot(input,Vector{5}),"model.observation.schedule");
}

TEST_CASE("observation values and schedule survive authored mutation and final handle death") {
    const auto retained = [] {
        auto producer = observed();
        Vector authored_times = grid;
        auto system = accepted(snapshot(producer,authored_times));
        auto& maps = std::get<ObservationStage>(producer.observations[0].coefficients);
        maps.state_map.values.assign(4,99); maps.error_map.values.assign(4,99);
        maps.offset.assign(2,99);
        producer.observations[0].schedule[0] = {{2},pre(2),pre(2),std::nullopt};
        authored_times = {-10,0,1};
        auto record = accepted(system.observation({0},{0}));
        auto value = accepted(system.observe({0},{0},Vector{3,-2},Vector{-1},Vector{2},Vector{4,-3}));
        CHECK(accepted(system.step({0},Vector{3,-2},Vector{-1},Vector{2})) == Vector{14,3});
        return std::pair{record,value};
    }();
    CHECK(retained.second.values == Vector{8,-10});
    times(retained.second.metadata,5,11,11);
    CHECK(retained.second.metadata.sample.state_stage.value == 0);
    REQUIRE(retained.second.metadata.sample.input_stage.has_value());
    CHECK(retained.second.metadata.sample.input_stage->value == 0);
    CHECK(retained.second.metadata.sample.measured_at.timing == ObservationTiming::after_decision);
    CHECK(accepted(numeric::multiply(retained.first.maps.state_map,
        accepted(numeric::snapshot_vector(Vector{3,-2})))) == Vector{8,-3});
    CHECK(accepted(numeric::multiply(retained.first.maps.error_map,
        accepted(numeric::snapshot_vector(Vector{4,-3})))) == Vector{-2,-15});
    times(retained.first.metadata,5,11,11);
}
