#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/geometry/generator_adapter.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/generator_sets.hpp>

#include <cmath>
#include <string>
#include <utility>

using namespace csl;

namespace {
template<class T, class... Alternatives>
T take(std::variant<T, Alternatives...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}

registry::PreparedProvider<registry::GeometryPort> generator_port() {
    auto registration=geometry::generators::make_operation_registration();
    const registry::Method method{registration.identity.id,registration.identity.version};
    registry::Registry<registry::GeometryPort> entries;
    REQUIRE_FALSE(entries.add(std::move(registration)).has_value());
    registry::Requirements requirements;
    requirements.output.representation={"csl.zonotope"};
    requirements.output.relation=SetRelation::equivalent;
    return take(registry::prepare_provider(registry::select_provider(entries,method,requirements)));
}

sets::GeneratorSet apply(registry::PreparedProvider<registry::GeometryPort>& port,
                         const OperationRequest& request) {
    auto prepared=take(port.prepare(request));
    auto [workspace]=prepared.create();
    const auto result=take(workspace->run({{},{},{},{1e-8,1e-8},"r29-native-reference"}));
    CHECK(result.relation==SetRelation::equivalent);
    CHECK(check_geometry_evidence(result.evidence,request).empty());
    return take(sets::from_generator_handle(result.output));
}

OperationRequest image_request(const sets::GeneratorSet& source,Matrix map,
                               std::string request_id,std::string output_id) {
    return {{{"R29-corrected-scalar-reference"},{std::move(request_id)},{std::move(output_id)}},
        {"csl.geometry.generators.operations"},
        AffineImage{source.as_handle(),std::move(map),{0,0,0,0}},
        SetRelation::equivalent,Assurance::numerical};
}
}

TEST_CASE("registered zonotope operations replay the inferred R29 scalar reference") {
    // R29 p. 108 prints A, B and X0; scalar P(t)=[-1,1] is the explicit
    // editorial interpretation in benchmarks/scenarios/r29-corrected-scalar-reference.json.
    const Matrix a{4,4,{1,0,0,0,-6.5,1,0,0,0,0,1,0,0,0,-6.5,1}};
    const Matrix b{4,1,{4,0,2,0}};
    auto state=take(sets::make_generator_set({{"r29-x0"},{1150,119600,430,44720},
        {4,4,{20,0,0,0,0,500,0,0,0,0,10,0,0,0,0,300}},
        {{"x0.0"},{"x0.1"},{"x0.2"},{"x0.3"}},{0,4,{}},{},{}}));
    auto port=generator_port();
    std::vector<sets::FactorId> expected_ids{{"x0.0"},{"x0.1"},{"x0.2"},{"x0.3"}};

    for(int stage=0;stage<=16;++stage) {
        CHECK(state.center()==Vector{1150,119600-7475.0*stage,430,44720-2795.0*stage});
        CHECK(state.generators().rows==4);
        CHECK(state.generators().cols==static_cast<std::size_t>(4+stage));
        CHECK(state.factor_ids()==expected_ids);
        CHECK(state.equalities().rows==0);
        if(stage==16) break;

        const auto propagated=apply(port,image_request(state,a,
            "state-image-"+std::to_string(stage),"r29-image-"+std::to_string(stage)));
        const auto scalar=take(sets::make_generator_set({
            {"r29-control-"+std::to_string(stage)},{0},{1,1,{1}},
            {{"u."+std::to_string(stage)}},{0,1,{}},{},{}}));
        const auto control_image=apply(port,image_request(scalar,b,
            "control-image-"+std::to_string(stage),"r29-control-image-"+std::to_string(stage)));
        const OperationRequest sum{{{"R29-corrected-scalar-reference"},
            {"stage-sum-"+std::to_string(stage)},{"r29-x-"+std::to_string(stage+1)}},
            {"csl.geometry.generators.operations"},
            MinkowskiSum{propagated.as_handle(),control_image.as_handle()},
            SetRelation::equivalent,Assurance::numerical};
        state=apply(port,sum);
        expected_ids.push_back({"u."+std::to_string(stage)});
    }

    CHECK(state.center()==Vector{1150,0,430,0});
    CHECK(state.factor_ids()==std::vector<sets::FactorId>{
        {"x0.0"},{"x0.1"},{"x0.2"},{"x0.3"},
        {"u.0"},{"u.1"},{"u.2"},{"u.3"},{"u.4"},{"u.5"},{"u.6"},{"u.7"},
        {"u.8"},{"u.9"},{"u.10"},{"u.11"},{"u.12"},{"u.13"},{"u.14"},{"u.15"}});
    // The 20 row-major columns are literal anchors from the independent
    // exact-rational record, not values computed with this native adapter.
    CHECK(state.generators().values==Vector{
        20,0,0,0,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,
        -2080,500,0,0,-390,-364,-338,-312,-286,-260,-234,-208,-182,-156,-130,-104,-78,-52,-26,0,
        0,0,10,0,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,
        0,0,-1040,300,-195,-182,-169,-156,-143,-130,-117,-104,-91,-78,-65,-52,-39,-26,-13,0});

    Vector lower=state.center(),upper=state.center();
    for(std::size_t row=0;row<4;++row)
        for(std::size_t column=0;column<20;++column) {
            const auto radius=std::abs(state.generators().values[row*20+column]);
            lower[row]-=radius;
            upper[row]+=radius;
        }
    CHECK(lower==Vector{1066,-5700,388,-2900});
    CHECK(upper==Vector{1234,5700,472,2900});
}
