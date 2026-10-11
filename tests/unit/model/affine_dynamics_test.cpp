#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/model/linear_system.hpp>
#include <csl/sets/data.hpp>

#include <limits>

using namespace csl;
using namespace csl::model;

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
LinearStage scalar() { return {{1,1,{3}}, {1,1,{2}}, {1,0,{}}, {-1}}; }
SystemModel scalar_model() { return {{{1,1,0}, TimeDomain::discrete, scalar()}, {}}; }
LinearStage first() {
    return {{2,2,{2,-1,0,3}}, {2,1,{1,-2}}, {2,1,{4,1}}, {-1,5}};
}
LinearStage second() {
    return {{2,2,{0,2,-1,1}}, {2,1,{-3,2}}, {2,1,{1,-2}}, {4,-3}};
}
SystemModel varying() {
    return {{{2,1,1}, TimeDomain::discrete, std::vector{first(),second()}}, {}};
}
const Vector grid{10,13,29};
}

// Dropping affine terms, reusing the wrong stage or scaling by dt changes these literals.
TEST_CASE("each scalar provider gives the fixed trajectory on unit and nonunit grids") {
    for (bool indexed : {false,true}) {
        for (const Vector& times : {Vector{0,1,2},grid}) {
            CAPTURE(indexed);
            CAPTURE(times);
            auto input = scalar_model();
            if (indexed) input.dynamics.stages = std::vector{scalar(),scalar()};
            const auto system = accepted(snapshot(input,times));
            const auto x1 = accepted(system.step({0},Vector{2},Vector{1},{}));
            CHECK(x1 == Vector{7});
            const auto x2 = accepted(system.step({1},x1,Vector{-2},{}));
            CHECK(x2 == Vector{16});
            CHECK(Vector{2,x1[0],x2[0]} == Vector{2,7,16});
            CHECK(system.horizon() == 2);
            CHECK(accepted(system.time({0})) == times[0]);
            CHECK(accepted(system.time({1})) == times[1]);
            CHECK(accepted(system.time({2})) == times[2]);
        }
    }
}

TEST_CASE("varying asymmetric coefficients preserve stage input and coordinate roles") {
    const auto system = accepted(snapshot(varying(),grid));
    const auto x1 = accepted(system.step({0},Vector{1,-2},Vector{2},Vector{-1}));
    CHECK(x1 == Vector{1,-6});
    CHECK(accepted(system.step({1},x1,Vector{-1},Vector{2})) == Vector{-3,-16});
}

TEST_CASE("singular autonomous transitions do not impose inverse strategy assumptions") {
    const SystemModel input{{{2,0,0},TimeDomain::discrete,
        LinearStage{{2,2,{0,1,0,0}},{2,0,{}},{2,0,{}},{1,-2}}}, {}};
    const auto system = accepted(snapshot(input,grid));
    const auto x1 = accepted(system.step({0},Vector{2,3},{},{}));
    CHECK(x1 == Vector{4,-2});
    CHECK(accepted(system.step({1},x1,{},{})) == Vector{-1,-2});
}

// A zero map must not erase a positive-dimensional physical port.
TEST_CASE("absent and present ports require different input vectors") {
    const SystemModel absent{{{1,0,0},TimeDomain::discrete,
        LinearStage{{1,1,{2}},{1,0,{}},{1,0,{}},{1}}}, {}};
    const auto no_ports = accepted(snapshot(absent,grid));
    CHECK(no_ports.dimensions().control == 0);
    CHECK(no_ports.dimensions().external == 0);
    CHECK(accepted(no_ports.step({0},Vector{3},{},{})) == Vector{7});
    rejected(no_ports.step({0},Vector{3},Vector{0},{}),"model.step.control");
    rejected(no_ports.step({0},Vector{3},{},Vector{0}),"model.step.external");

    SystemModel present{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{2}},{1,1,{3}},{1,1,{-2}},{1}}}, {}};
    const auto ports = accepted(snapshot(present,grid));
    CHECK(ports.dimensions().control == 1);
    CHECK(ports.dimensions().external == 1);
    CHECK(accepted(ports.step({0},Vector{3},Vector{0},Vector{0})) == Vector{7});
    CHECK(accepted(ports.step({0},Vector{3},Vector{4},Vector{-3})) == Vector{25});
    CHECK(accepted(ports.step({0},Vector{3},Vector{-5},Vector{2})) == Vector{-12});
    rejected(ports.step({0},Vector{3},{},Vector{0}),"model.step.control");
    rejected(ports.step({0},Vector{3},Vector{0},{}),"model.step.external");

    auto& maps = std::get<LinearStage>(present.dynamics.stages);
    maps.B.values = {0}; maps.E.values = {0};
    const auto zero_maps = accepted(snapshot(present,grid));
    CHECK(zero_maps.dimensions().control == 1);
    CHECK(zero_maps.dimensions().external == 1);
    CHECK(accepted(zero_maps.step({0},Vector{3},Vector{4},Vector{-3})) == Vector{7});
    rejected(zero_maps.step({0},Vector{3},{},Vector{0}),"model.step.control");
    rejected(zero_maps.step({0},Vector{3},Vector{0},{}),"model.step.external");
}

// Exercise factories and the handle seam; authored variant identities alone prove nothing.
TEST_CASE("positive dimensional singleton universal and empty representations survive roundtrip") {
    const auto point = accepted(numeric::snapshot_vector(Vector{0}));
    const auto singleton = accepted(sets::from_handle(accepted(sets::make_singleton(
        {{"zero-input"},1,{"u"}},point)).as_handle()));
    const auto universal = accepted(sets::from_handle(accepted(sets::make_universal(
        {{"free-input"},1,{"u"}})).as_handle()));
    const auto empty = accepted(sets::from_handle(accepted(sets::make_empty(
        {{"empty-input"},1,{"u"}})).as_handle()));
    CHECK(singleton.metadata()->set.dimension == 1);
    CHECK(singleton.metadata()->set.bounded == SetProperty::yes);
    REQUIRE(std::holds_alternative<sets::SingletonRepresentation>(singleton.representation()));
    CHECK(std::get<sets::SingletonRepresentation>(singleton.representation()).point[0] == 0);
    CHECK(universal.metadata()->set.dimension == 1);
    CHECK(universal.metadata()->set.bounded == SetProperty::no);
    CHECK(std::holds_alternative<sets::UniversalRepresentation>(universal.representation()));
    CHECK(empty.metadata()->set.dimension == 1);
    CHECK(std::holds_alternative<sets::EmptyRepresentation>(empty.representation()));

    // The model does not receive or enforce a domain: storing {0} does not erase the port.
    const auto system = accepted(snapshot(scalar_model(),grid));
    CHECK(system.dimensions().control == singleton.metadata()->set.dimension);
    CHECK(accepted(system.step({0},Vector{2},Vector{0},{})) == Vector{5});
    CHECK(accepted(system.step({0},Vector{2},Vector{4},{})) == Vector{13});
    rejected(system.step({0},Vector{2},{},{}),"model.step.control");
}

TEST_CASE("all dynamics coefficient shapes are validated in constant and indexed providers") {
    for (bool indexed : {false,true}) {
        for (int fault = 0; fault != 4; ++fault) {
            CAPTURE(indexed);
            CAPTURE(fault);
            auto maps = first();
            switch (fault) {
            case 0: maps.A = {2,1,{2,0}}; break;
            case 1: maps.B = {1,1,{1}}; break;
            case 2: maps.E = {2,2,{4,0,1,0}}; break;
            case 3: maps.offset = {-1}; break;
            }
            auto input = varying();
            if (indexed) input.dynamics.stages = std::vector{first(),maps};
            else input.dynamics.stages = maps;
            rejected(snapshot(input,grid),"model.dynamics.coefficients");
        }
    }
}

TEST_CASE("indexed providers have exactly T transitions and malformed storage is rejected") {
    auto input = varying();
    SUBCASE("one transition") { input.dynamics.stages = std::vector{first()}; }
    SUBCASE("three transitions") { input.dynamics.stages = std::vector{first(),second(),first()}; }
    SUBCASE("missing A storage") { std::get<std::vector<LinearStage>>(input.dynamics.stages)[1].A.values.pop_back(); }
    SUBCASE("extra B storage") { std::get<std::vector<LinearStage>>(input.dynamics.stages)[1].B.values.push_back(0); }
    SUBCASE("nonfinite E") { std::get<std::vector<LinearStage>>(input.dynamics.stages)[1].E.values[0] = std::numeric_limits<double>::infinity(); }
    rejected(snapshot(input,grid),"model.dynamics.coefficients");
}

TEST_CASE("state time and transition bounds differ at T and at maximum index") {
    const auto system = accepted(snapshot(varying(),grid));
    CHECK(accepted(system.time({2})) == 29);
    CHECK(accepted(system.stage({1})).A(0,1) == 2);
    CHECK(accepted(system.step({1},Vector{1,-6},Vector{-1},Vector{2})) == Vector{-3,-16});
    for (const auto index : {std::size_t{3},std::numeric_limits<std::size_t>::max()})
        rejected(system.time({index}),"model.time");
    for (const auto index : {std::size_t{2},std::numeric_limits<std::size_t>::max()}) {
        rejected(system.stage({index}),"model.stage");
        rejected(system.step({index},Vector{1,-6},Vector{-1},Vector{2}),"model.stage");
    }
}

TEST_CASE("evaluation checks each finite input dimension independently") {
    const auto system = accepted(snapshot(varying(),grid));
    CHECK(accepted(system.step({0},Vector{1,-2},Vector{2},Vector{-1})) == Vector{1,-6});
    for (const Vector& x : {Vector{1},Vector{1,-2,0},Vector{1,std::numeric_limits<double>::infinity()}})
        rejected(system.step({0},x,Vector{2},Vector{-1}),"model.step.state");
    for (const Vector& u : {Vector{},Vector{2,0},Vector{std::numeric_limits<double>::quiet_NaN()}})
        rejected(system.step({0},Vector{1,-2},u,Vector{-1}),"model.step.control");
    for (const Vector& w : {Vector{},Vector{-1,0},Vector{std::numeric_limits<double>::infinity()}})
        rejected(system.step({0},Vector{1,-2},Vector{2},w),"model.step.external");
}

TEST_CASE("zero horizon preserves one state time without inventing a transition") {
    auto input = scalar_model();
    SUBCASE("valid constant") {}
    SUBCASE("empty indexed") { input.dynamics.stages = std::vector<LinearStage>{}; }
    const auto system = accepted(snapshot(input,Vector{5}));
    CHECK(system.horizon() == 0);
    CHECK(accepted(system.time({0})) == 5);
    rejected(system.time({1}),"model.time");
    rejected(system.stage({0}),"model.stage");
    rejected(system.step({0},Vector{2},Vector{1},{}),"model.stage");
}

TEST_CASE("zero horizon still validates constant records and indexed stage count") {
    auto input = scalar_model();
    SUBCASE("nonempty indexed") { input.dynamics.stages = std::vector{scalar()}; }
    SUBCASE("malformed constant") { std::get<LinearStage>(input.dynamics.stages).offset.clear(); }
    rejected(snapshot(input,Vector{5}),"model.dynamics.coefficients");
}

TEST_CASE("invalid grids are diagnosed separately from unsupported continuous data") {
    const auto input = scalar_model();
    CHECK(accepted(accepted(snapshot(input,grid)).step({0},Vector{2},Vector{1},{})) == Vector{7});
    for (const Vector& times : {Vector{},Vector{5,5},Vector{5,4},
        Vector{0,std::numeric_limits<double>::infinity()},
        Vector{std::numeric_limits<double>::quiet_NaN()}})
        rejected(snapshot(input,times),"model.times");
    for (const auto domain : {TimeDomain::continuous,static_cast<TimeDomain>(99)}) {
        auto unsupported = input;
        unsupported.dynamics.time_domain = domain;
        rejected(snapshot(unsupported,grid),"model.time_domain",DiagnosticCode::unsupported);
    }
}

TEST_CASE("indexed snapshot retains both stages after producer and grid mutation") {
    const auto system = [] {
        auto producer = varying();
        Vector times = grid;
        auto result = accepted(snapshot(producer,times));
        for (auto& maps : std::get<std::vector<LinearStage>>(producer.dynamics.stages)) {
            maps.A.values.assign(4,99); maps.B.values.assign(2,99);
            maps.E.values.assign(2,99); maps.offset.assign(2,99);
        }
        times = {-1,0,1};
        return result;
    }();
    const auto x1 = accepted(system.step({0},Vector{1,-2},Vector{2},Vector{-1}));
    CHECK(x1 == Vector{1,-6});
    CHECK(accepted(system.step({1},x1,Vector{-1},Vector{2})) == Vector{-3,-16});
    CHECK(accepted(system.time({0})) == 10);
    CHECK(accepted(system.time({1})) == 13);
    CHECK(accepted(system.time({2})) == 29);
}
