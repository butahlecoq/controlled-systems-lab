#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/geometry/approximation.hpp>
#include <csl/sets/data.hpp>

using namespace csl;
using namespace csl::geometry::approximation;

namespace {
sets::SetData take(sets::Result<sets::SetData> value) {
    REQUIRE(std::holds_alternative<sets::SetData>(value));
    return std::get<sets::SetData>(std::move(value));
}
SetHandle set(const char* kind, const char* id, const char* coordinate="x") {
    sets::Description description{{id},1,{coordinate}};
    if (std::string(kind)=="empty") return take(sets::make_empty(description)).as_handle();
    if (std::string(kind)=="universal") return take(sets::make_universal(description)).as_handle();
    const Vector point{1.0};
    auto view=numeric::snapshot_vector(point);
    REQUIRE(std::holds_alternative<numeric::VectorView>(view));
    return take(sets::make_singleton(description,std::get<numeric::VectorView>(view))).as_handle();
}
SetHandle two_points(const char* id) {
    const auto vertices=numeric::snapshot(Matrix{2,1,{0.0,1.0}});
    const auto rays=numeric::snapshot(Matrix{0,1,{}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(vertices));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rays));
    return take(sets::make_v({{id},1,{"x"}},
        {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(rays)})).as_handle();
}
ApproximationRequest request(SetHandle input, SetRelation relation, RepresentationId representation) {
    return {{{"problem/a"},{"approx/a"},{"reference/a"}},std::move(input),std::move(representation),relation,2,Assurance::numerical};
}
class FixedWorkspace final : public SetApproximatorWorkspace {
    OperationResult result_;
public:
    explicit FixedWorkspace(OperationResult result):result_(std::move(result)){}
    SetTransformOutcome approximate(const ApproximationRequest&,const ExecutionContext&) override {return result_;}
};
registry::Registry<registry::ApproximationPort> provider(const ApproximationRequest& request,
    SetHandle output, SetRelation offered, SetRelation returned, EvidenceSupport support=Unestablished{},
    std::optional<GeometryErrorBound> error_bound=std::nullopt) {
    registry::Registry<registry::ApproximationPort> result;
    GeometryEvidence evidence{{request.identity,{request.input.id}},GeometryClaimScope::set_relation,
        std::move(support),{},std::move(error_bound)};
    OperationResult fixed{std::move(output),returned,std::move(evidence)};
    auto added=result.add({{{"fixture.approximation"},"1"},
        [offered](const ApproximationRequest& query,const registry::Requirements&) -> registry::Capability {
            registry::Output output;output.representation=query.output;output.relation=offered;
            return registry::Offer{output};
        },
        [fixed](const ApproximationRequest&) {return std::make_unique<FixedWorkspace>(fixed);}});
    REQUIRE_FALSE(added.has_value());
    return result;
}
auto execute(const registry::Registry<registry::ApproximationPort>& registry,const ApproximationRequest& query) {
    return run_registered(registry,{{"fixture.approximation"},std::nullopt},query,ExecutionContext{});
}
}

TEST_CASE("registered inner approximation admits a structurally empty subset") {
    auto input=set("singleton","reference");
    auto output=set("empty","inner");
    auto query=request(input,SetRelation::inner,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::inner,SetRelation::inner);
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    const auto& admitted=std::get<EnclosedApproximation>(outcome);
    CHECK(admitted.result.relation==SetRelation::inner);
    CHECK(admitted.basis==StructuralBasis::empty_subset);
    CHECK(admitted.result.output.id==SetId{"inner"});
}

TEST_CASE("registered outer approximation admits a universal superset") {
    auto input=set("singleton","reference");
    auto output=set("universal","outer");
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::outer,SetRelation::outer);
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::universal_superset);
}

TEST_CASE("an enclosure cannot change the native coordinate system") {
    auto input=set("singleton","reference","x");
    auto output=set("universal","outer","y");
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::outer,SetRelation::outer);
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("an unproved enclosure is rejected after provider execution") {
    auto input=set("singleton","reference");
    auto output=set("singleton","different");
    auto query=request(input,SetRelation::inner,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::inner,SetRelation::inner,
        SymbolicArgument{"provider assertion","no independent verifier"});
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("elementary enclosure does not authorize a provider error bound") {
    auto input=set("singleton","reference");
    auto output=set("universal","outer");
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::outer,SetRelation::outer,
        SymbolicArgument{"provider bound assertion","unverified"},
        GeometryErrorBound{{"hausdorff"},0.1,"state units"});
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.error_bound");
}

TEST_CASE("native output cannot exceed the requested size budget") {
    auto input=set("singleton","reference");
    auto output=two_points("candidate");
    auto query=request(input,SetRelation::heuristic,output.metadata.representation);
    query.size_budget=1;
    auto methods=provider(query,output,SetRelation::heuristic,SetRelation::heuristic);
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.budget");
    query.size_budget=2;
    CHECK(std::holds_alternative<HeuristicApproximation>(execute(methods,query)));
}

TEST_CASE("declared and returned approximation relations cannot downgrade") {
    auto input=set("singleton","reference");
    auto output=set("universal","outer");
    auto query=request(input,SetRelation::inner,output.metadata.representation);
    auto wrong_offer=provider(query,output,SetRelation::outer,SetRelation::outer);
    auto admission=execute(wrong_offer,query);
    REQUIRE(std::holds_alternative<registry::Rejection>(admission));
    CHECK(std::get<registry::Rejection>(admission).diagnostics[0].field=="output.relation");
    auto wrong_result=provider(query,output,SetRelation::inner,SetRelation::outer);
    auto outcome=execute(wrong_result,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.relation");
}

TEST_CASE("equivalent conversion and heuristic approximation stay separate") {
    auto input=set("singleton","reference");
    auto output=set("singleton","candidate");
    auto equivalent=request(input,SetRelation::equivalent,output.metadata.representation);
    auto methods=provider(equivalent,output,SetRelation::equivalent,SetRelation::equivalent);
    CHECK(std::holds_alternative<registry::Rejection>(execute(methods,equivalent)));
    auto heuristic=request(input,SetRelation::heuristic,output.metadata.representation);
    methods=provider(heuristic,output,SetRelation::heuristic,SetRelation::heuristic);
    auto outcome=execute(methods,heuristic);
    REQUIRE(std::holds_alternative<HeuristicApproximation>(outcome));
    CHECK(std::get<HeuristicApproximation>(outcome).result.output.id==SetId{"candidate"});
}

TEST_CASE("set extrema have directed bounds but no optimizer-family claim") {
    CHECK(objective_bound_side(SetRelation::inner,ObjectiveSense::minimize)==BoundSide::upper);
    CHECK(objective_bound_side(SetRelation::outer,ObjectiveSense::minimize)==BoundSide::lower);
    CHECK(objective_bound_side(SetRelation::inner,ObjectiveSense::maximize)==BoundSide::lower);
    CHECK(objective_bound_side(SetRelation::outer,ObjectiveSense::maximize)==BoundSide::upper);
    CHECK(objective_bound_side(SetRelation::equivalent,ObjectiveSense::maximize)==BoundSide::both);
    CHECK(objective_bound_side(SetRelation::heuristic,ObjectiveSense::minimize)==BoundSide::none);
}
