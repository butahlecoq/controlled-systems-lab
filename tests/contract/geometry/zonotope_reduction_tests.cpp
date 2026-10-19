#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/geometry/zonotope_reduction.hpp>
#include <csl/geometry/approximation.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/generator_sets.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <stop_token>

using namespace csl;
using namespace csl::geometry::approximation;

namespace {
template<class T,class... Alternatives> T take(std::variant<T,Alternatives...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
sets::GeneratorSet generator(const char* id,Vector center,Matrix columns,
                             std::vector<sets::FactorId> factors,Matrix equalities = {},
                             Vector values = {}) {
    if(equalities.rows==0)equalities.cols=factors.size();
    return take(sets::make_generator_set({{id},std::move(center),std::move(columns),
        std::move(factors),std::move(equalities),std::move(values),{"x","y"}}));
}
}

TEST_CASE("exact registered conversion removes only zero generator columns") {
    const auto source=generator("source",{1,2},{2,3,{2,0,0,0,0,3}},
        {{"x-factor"},{"zero"},{"y-factor"}});
    auto registration=make_zero_generator_removal_registration({"removed"});
    registry::Registry<registry::ConversionPort> entries;
    const registry::Method method{registration.identity.id,registration.identity.version};
    REQUIRE_FALSE(entries.add(std::move(registration)).has_value());
    registry::Requirements requirements;
    requirements.output.representation={"csl.zonotope"};
    requirements.output.relation=SetRelation::equivalent;
    auto selected=take(registry::prepare_provider(registry::select_provider(entries,method,requirements)));
    ConversionRequest query{{{"app03"},{"zero-removal"},{"same-physical-set"}},
        source.as_handle(),{"csl.zonotope"},Assurance::numerical};
    auto prepared=take(selected.prepare(query));
    auto [workspace]=prepared.create();
    auto result=take(workspace->run(ExecutionContext{}));
    CHECK(result.relation==SetRelation::equivalent);
    CHECK(check_geometry_evidence(result.evidence,query).empty());
    auto output=take(sets::from_generator_handle(result.output));
    CHECK(output.id()==SetId{"removed"});
    CHECK(output.center()==Vector{1,2});
    CHECK(output.generators().values==Vector{2,0,0,3});
    CHECK(output.factor_ids()==std::vector<sets::FactorId>{{"x-factor"},{"y-factor"}});
}

TEST_CASE("budgeted registered cover has exact analytic 2D support") {
    const auto source=generator("source",{0,0},{2,3,{1,0,0.5,0,1,0.5}},
        {{"x-factor"},{"y-factor"},{"diagonal"}});
    auto registration=make_axis_cover_registration({"cover"});
    registry::Registry<registry::ApproximationPort> entries;
    const registry::Method method{registration.identity.id,registration.identity.version};
    REQUIRE_FALSE(entries.add(std::move(registration)).has_value());
    ApproximationRequest query{{{"app03"},{"axis-cover"},{"source-physical-set"}},
        source.as_handle(),{"csl.zonotope"},SetRelation::outer,2,Assurance::numerical};
    auto outcome=run_registered(entries,method,query,ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    const auto& admitted=std::get<EnclosedApproximation>(outcome);
    CHECK(admitted.basis==StructuralBasis::generator_axis_cover);
    auto output=take(sets::from_generator_handle(admitted.result.output));
    CHECK(output.id()==SetId{"cover"});
    CHECK(output.factor_ids().size()==2);
    CHECK(output.generators().values==Vector{1.5,0,0,1.5});
    // Complete 2D cube-corner oracle: every source corner lies in the output
    // box, whose exact support in direction (1,-1) is 3 versus source 2.
    for(unsigned mask=0;mask<8;++mask) {
        const double a=(mask&1)?1.0:-1.0;
        const double b=(mask&2)?1.0:-1.0;
        const double c=(mask&4)?1.0:-1.0;
        const double x=a+0.5*c;
        const double y=b+0.5*c;
        CHECK(x>=-1.5);
        CHECK(x<=1.5);
        CHECK(y>=-1.5);
        CHECK(y<=1.5);
    }
    const auto analytic_support=[](const sets::GeneratorSet& set) {
        double value=set.center()[0]-set.center()[1];
        for(std::size_t factor=0;factor<set.factor_ids().size();++factor)
            value+=std::abs(set.generators().values[factor]-
                set.generators().values[set.factor_ids().size()+factor]);
        return value;
    };
    CHECK(analytic_support(source)==2.0);
    CHECK(analytic_support(output)==3.0);
    CHECK(admitted.result.evidence.reference.identity==query.identity);
    CHECK(admitted.result.evidence.reference.inputs==std::vector<SetId>{source.id()});
}

TEST_CASE("outer reduction retains a shared factor and records equality relaxation") {
    const auto source=generator("constrained",{0,0},
        {2,4,{2,0,0.5,0.25,0,1,0.5,0.25}},
        {{"shared"},{"vertical"},{"diagonal"},{"small"}},
        {1,4,{0,1,0,0}},{0});
    auto registration=make_axis_cover_registration({"outer"});
    registry::Registry<registry::ApproximationPort> entries;
    const registry::Method method{registration.identity.id,registration.identity.version};
    REQUIRE_FALSE(entries.add(std::move(registration)).has_value());
    ApproximationRequest query{{{"app03"},{"constrained-cover"},{"source"}},
        source.as_handle(),{"csl.zonotope"},SetRelation::outer,3,Assurance::numerical};
    auto outcome=run_registered(entries,method,query,ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    auto output=take(sets::from_generator_handle(std::get<EnclosedApproximation>(outcome).result.output));
    CHECK(output.factor_ids().size()==3);
    CHECK(output.factor_ids()[0]==sets::FactorId{"shared"});
    CHECK(output.generators().values==Vector{2,0.75,0,0,0,1.75});
    CHECK(output.equalities().rows==0);
    const auto& assumptions=std::get<EnclosedApproximation>(outcome).result.evidence.assumptions;
    CHECK(std::find(assumptions.begin(),assumptions.end(),
        "Input factor equalities were relaxed.")!=assumptions.end());

    query.size_budget=1;
    outcome=run_registered(entries,method,query,ExecutionContext{});
    REQUIRE(std::holds_alternative<Unsupported>(outcome));

    query.direction=SetRelation::inner;
    outcome=run_registered(entries,method,query,ExecutionContext{});
    REQUIRE(std::holds_alternative<registry::Rejection>(outcome));
}

TEST_CASE("zero-factor and stopped reductions retain explicit outcomes") {
    const auto singleton=generator("singleton",{1,2},{2,0,{}},{});
    auto registration=make_axis_cover_registration({"outer"});
    registry::Registry<registry::ApproximationPort> entries;
    const registry::Method method{registration.identity.id,registration.identity.version};
    REQUIRE_FALSE(entries.add(std::move(registration)).has_value());
    ApproximationRequest query{{{"app03"},{"singleton-cover"},{"singleton"}},
        singleton.as_handle(),{"csl.zonotope"},SetRelation::outer,0,Assurance::numerical};
    auto outcome=run_registered(entries,method,query,ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    auto output=take(sets::from_generator_handle(std::get<EnclosedApproximation>(outcome).result.output));
    CHECK(output.factor_ids().empty());
    CHECK(output.center()==Vector{1,2});

    std::stop_source cancellation;
    cancellation.request_stop();
    ExecutionContext context;
    context.cancellation=cancellation.get_token();
    outcome=run_registered(entries,method,query,context);
    REQUIRE(std::holds_alternative<OperationStopped>(outcome));
    CHECK(std::get<OperationStopped>(outcome).reason==StopReason::cancelled);
    context={};
    context.deadline=std::chrono::steady_clock::now()-std::chrono::seconds(1);
    outcome=run_registered(entries,method,query,context);
    REQUIRE(std::holds_alternative<OperationStopped>(outcome));
    CHECK(std::get<OperationStopped>(outcome).reason==StopReason::deadline_expired);
}
