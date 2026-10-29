#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/geometry/reachable_plan.hpp>
#include <csl/sets/data.hpp>

using namespace csl;
using namespace csl::geometry::approximation;

namespace {
template<class T, class... Other> T take(std::variant<T, Other...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

problem::ResolvedProblem scalar_problem() {
    Problem authored{{"authored"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{0}},{1,1,{1}},{1,0,{}},{0}}},{}}),{0,1},KnownInitial{{2}},
        ContinuousDomain{{Singleton{{3}}}},{UniversalSet{1},UniversalSet{1}},{},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{1},0}};
    return take(problem::resolve(authored,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}

SetHandle singleton(const char* id,double value) {
    auto point=take(numeric::snapshot_vector(Vector{value}));
    return take(sets::make_singleton({{id},1,{"x"}},point)).as_handle();
}

SetHandle interval(const char* id,double lower,double upper) {
    auto rows=take(numeric::snapshot(Matrix{2,1,{1,-1}}));
    auto bounds=take(numeric::snapshot_vector(Vector{upper,-lower}));
    auto no_rows=take(numeric::snapshot(Matrix{0,1,{}}));
    auto no_values=take(numeric::snapshot_vector(Vector{}));
    return take(sets::make_h({{id},1,{"x"}},{rows,bounds,no_rows,no_values})).as_handle();
}

SetHandle constrained_inner(const char* id) {
    auto rows=take(numeric::snapshot(Matrix{4,1,{1,-1,1,-1}}));
    auto bounds=take(numeric::snapshot_vector(Vector{4,-2,3,-3}));
    auto no_rows=take(numeric::snapshot(Matrix{0,1,{}}));
    auto no_values=take(numeric::snapshot_vector(Vector{}));
    return take(sets::make_h({{id},1,{"x"}},{rows,bounds,no_rows,no_values})).as_handle();
}

SetHandle v_interval(const char* id) {
    auto vertices=take(numeric::snapshot(Matrix{2,1,{2,4}}));
    auto rays=take(numeric::snapshot(Matrix{0,1,{}}));
    return take(sets::make_v({{id},1,{"x"}},{vertices,rays})).as_handle();
}

SetHandle empty_v_with_ray(const char* id) {
    auto vertices=take(numeric::snapshot(Matrix{0,1,{}}));
    auto rays=take(numeric::snapshot(Matrix{1,1,{1}}));
    return take(sets::make_v({{id},1,{"x"}},{vertices,rays})).as_handle();
}

class FixedWorkspace final : public SetApproximatorWorkspace {
    SetTransformOutcome result_;
public:
    explicit FixedWorkspace(SetTransformOutcome value):result_(std::move(value)){}
    SetTransformOutcome approximate(const ApproximationRequest&,const ExecutionContext&) override {return result_;}
};

registry::Registry<registry::ApproximationPort> provider_outcome(const ApproximationRequest& query,
                                                                SetTransformOutcome result) {
    registry::Registry<registry::ApproximationPort> methods;
    auto error=methods.add({{{"fixture.approximation"},"1"},
        [](const ApproximationRequest& q,const registry::Requirements&) -> registry::Capability {
            registry::Output offer;offer.representation=q.output;offer.relation=q.direction;
            return registry::Offer{offer};
        },
        [result](const ApproximationRequest&) {return std::make_unique<FixedWorkspace>(result);}});
    REQUIRE_FALSE(error.has_value());
    return methods;
}

registry::Registry<registry::ApproximationPort> provider(const ApproximationRequest& query,SetHandle output) {
    return provider_outcome(query,OperationResult{output,query.direction,
        {{query.identity,{query.input.id}},GeometryClaimScope::set_relation,Unestablished{},{},{}}});
}

ApproximationRequest query(const problem::ResolvedProblem& problem,SetHandle reference,SetHandle output) {
    return {{problem.identity(),{"approx/stage1"},{"declared/stage1"}},reference,
        output.metadata.representation,SetRelation::inner,4,Assurance::numerical};
}

Witness witness(const problem::ResolvedProblem& problem) {
    return {problem.identity(),{{2},{3}},{{3}},3};
}

StageSetReference binding(const problem::ResolvedProblem& problem,SetHandle reference) {
    return {problem.identity(),StageIndex{1},reference,{0},{"declared/stage1"}};
}

PlanCheck check(const problem::ResolvedProblem& problem,const StageSetReference& stage,
                const ApproximationRequest& request,SetHandle output,const Witness& plan) {
    return check_inner_state_plan(problem,stage,provider(request,output),
        {{"fixture.approximation"},std::nullopt},request,plan);
}
}

TEST_CASE("admitted inner stage point and verified original trajectory yield its original objective") {
    const auto problem=scalar_problem();
    const auto reference=interval("stage1",2,4), inner=singleton("inner",3);
    const auto request=query(problem,reference,inner);
    const auto report=check(problem,binding(problem,reference),request,inner,witness(problem));
    REQUIRE(report.numerical_achievable_value);
    CHECK(*report.numerical_achievable_value==3);
    CHECK(report.membership==verification::CheckStatus::numerical_pass);
    REQUIRE(report.trajectory);
    CHECK(report.trajectory->bindings==verification::CheckStatus::numerical_pass);
    CHECK(report.trajectory->feasibility==verification::CheckStatus::numerical_pass);
    CHECK(report.trajectory->objective==verification::CheckStatus::numerical_pass);
    REQUIRE(report.approximation);
    CHECK(std::holds_alternative<EnclosedApproximation>(*report.approximation));
}

TEST_CASE("an outer reachable enclosure cannot provide an achievable control witness") {
    const auto problem=scalar_problem();
    const auto reference=interval("outer-reference",2,4);
    const auto outer=interval("outer-enclosure",1,5);
    auto request=query(problem,reference,outer);
    request.direction=SetRelation::outer;

    const auto outer_result=run_registered(provider(request,outer),
        {{"fixture.approximation"},std::nullopt},request,ExecutionContext{});
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outer_result));

    const auto report=check_inner_state_plan(problem,binding(problem,reference),
        provider(request,outer),{{"fixture.approximation"},std::nullopt},request,witness(problem));
    CHECK(report.membership==verification::CheckStatus::invalid_input);
    CHECK_FALSE(report.approximation);
    CHECK_FALSE(report.trajectory);
    CHECK_FALSE(report.numerical_achievable_value);
}

TEST_CASE("selected stage state membership and ordered coordinate map gate the achievable value") {
    const auto problem=scalar_problem();
    const auto reference=interval("stage1",2,4), inner=singleton("inner",3);
    const auto request=query(problem,reference,inner);
    auto stage=binding(problem,reference);
    stage.stage={0};
    const auto stage_zero_state_outside_inner=check(problem,stage,request,inner,witness(problem));
    CHECK_FALSE(stage_zero_state_outside_inner.numerical_achievable_value);
    CHECK(stage_zero_state_outside_inner.membership==verification::CheckStatus::violation);
    stage=binding(problem,reference);
    stage.state_coordinates={1};
    const auto wrong_map=check(problem,stage,request,inner,witness(problem));
    CHECK_FALSE(wrong_map.numerical_achievable_value);
    CHECK(wrong_map.membership==verification::CheckStatus::invalid_input);
}

TEST_CASE("mismatched problem and reference set bindings fail closed") {
    const auto problem=scalar_problem();
    const auto reference=interval("stage1",2,4), inner=singleton("inner",3);
    const auto request=query(problem,reference,inner);
    auto stage=binding(problem,reference);
    stage.problem={"different"};
    const auto wrong_problem=check(problem,stage,request,inner,witness(problem));
    CHECK_FALSE(wrong_problem.numerical_achievable_value);
    CHECK(wrong_problem.membership==verification::CheckStatus::invalid_input);
    stage=binding(problem,interval("other",2,4));
    const auto wrong_reference=check(problem,stage,request,inner,witness(problem));
    CHECK_FALSE(wrong_reference.numerical_achievable_value);
    CHECK(wrong_reference.membership==verification::CheckStatus::invalid_input);
    stage=binding(problem,reference);
    stage.reference_id={"other/stage1"};
    const auto wrong_identity=check(problem,stage,request,inner,witness(problem));
    CHECK_FALSE(wrong_identity.numerical_achievable_value);
    CHECK(wrong_identity.membership==verification::CheckStatus::invalid_input);
}

TEST_CASE("inner membership cannot replace an invalid original trajectory") {
    const auto problem=scalar_problem();
    const auto reference=interval("stage1",2,4), inner=singleton("inner",3);
    const auto request=query(problem,reference,inner);
    auto plan=witness(problem);plan.controls[0][0]=5;
    const auto report=check(problem,binding(problem,reference),request,inner,plan);
    CHECK(report.membership==verification::CheckStatus::numerical_pass);
    REQUIRE(report.trajectory);
    CHECK(report.trajectory->feasibility==verification::CheckStatus::violation);
    CHECK_FALSE(report.numerical_achievable_value);
}

TEST_CASE("native V membership remains unsupported without a verified membership oracle") {
    const auto problem=scalar_problem();
    const auto reference=v_interval("stage1");
    const auto request=query(problem,reference,reference);
    const auto report=check(problem,binding(problem,reference),request,reference,witness(problem));
    CHECK(report.membership==verification::CheckStatus::unsupported);
    CHECK_FALSE(report.numerical_achievable_value);
}

TEST_CASE("an admitted zero-vertex V inner set has no member even when it stores a ray") {
    const auto problem=scalar_problem();
    const auto reference=interval("stage1",2,4), inner=empty_v_with_ray("empty-inner");
    const auto request=query(problem,reference,inner);
    const auto report=check(problem,binding(problem,reference),request,inner,witness(problem));
    REQUIRE(report.approximation);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(*report.approximation));
    CHECK(std::get<EnclosedApproximation>(*report.approximation).basis==StructuralBasis::empty_subset);
    CHECK(report.membership==verification::CheckStatus::violation);
    CHECK_FALSE(report.trajectory);
    CHECK_FALSE(report.numerical_achievable_value);
}

TEST_CASE("native H membership checks stored binary64 rows before reporting a plan") {
    const auto problem=scalar_problem();
    const auto reference=interval("stage1",2,4);
    const auto inner=constrained_inner("inner");
    const auto request=query(problem,reference,inner);
    const auto accepted=check(problem,binding(problem,reference),request,inner,witness(problem));
    CHECK(accepted.membership==verification::CheckStatus::numerical_pass);
    REQUIRE(accepted.numerical_achievable_value);
    CHECK(*accepted.numerical_achievable_value==3);

    auto outside=witness(problem);outside.states[1][0]=2;
    const auto rejected=check(problem,binding(problem,reference),request,inner,outside);
    CHECK(rejected.membership==verification::CheckStatus::violation);
    CHECK_FALSE(rejected.numerical_achievable_value);
}

TEST_CASE("an unadmitted provider relation does not reach trajectory publication") {
    const auto problem=scalar_problem();
    const auto reference=interval("stage1",2,4);
    const auto outside=singleton("outside",5);
    const auto request=query(problem,reference,outside);
    const auto report=check(problem,binding(problem,reference),request,outside,witness(problem));
    CHECK_FALSE(report.numerical_achievable_value);
    CHECK_FALSE(report.trajectory);
    CHECK(report.membership==verification::CheckStatus::unsupported);
}

TEST_CASE("original objective mismatch blocks publication despite valid stage membership") {
    const auto problem=scalar_problem();
    const auto reference=interval("stage1",2,4), inner=singleton("inner",3);
    const auto request=query(problem,reference,inner);
    auto plan=witness(problem);plan.original_objective=8;
    const auto report=check(problem,binding(problem,reference),request,inner,plan);
    CHECK(report.membership==verification::CheckStatus::numerical_pass);
    REQUIRE(report.trajectory);
    CHECK(report.trajectory->objective==verification::CheckStatus::violation);
    REQUIRE(report.trajectory->recomputed_objective);
    CHECK(*report.trajectory->recomputed_objective==3);
    CHECK_FALSE(report.numerical_achievable_value);
}

TEST_CASE("a different resolved problem identity in approximation request is rejected") {
    const auto problem=scalar_problem();
    const auto reference=interval("stage1",2,4), inner=singleton("inner",3);
    auto request=query(problem,reference,inner);
    request.identity.problem={"different"};
    const auto report=check(problem,binding(problem,reference),request,inner,witness(problem));
    CHECK(report.membership==verification::CheckStatus::invalid_input);
    CHECK_FALSE(report.numerical_achievable_value);
}

TEST_CASE("unsupported initial-state quantifier cannot publish a stage-reference claim") {
    auto authored=*scalar_problem().description();
    authored.initial=InitialSet{Singleton{{2}},SetQuantifier::existential};
    const auto problem=take(problem::resolve(authored,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    const auto reference=interval("stage1",2,4), inner=singleton("inner",3);
    const auto request=query(problem,reference,inner);
    const auto report=check(problem,binding(problem,reference),request,inner,witness(problem));
    CHECK(report.membership==verification::CheckStatus::unsupported);
    CHECK_FALSE(report.numerical_achievable_value);
}

TEST_CASE("provider stop remains a stop and cannot yield an achievable value") {
    const auto problem=scalar_problem();
    const auto reference=interval("stage1",2,4), inner=singleton("inner",3);
    const auto request=query(problem,reference,inner);
    const auto methods=provider_outcome(request,OperationStopped{StopReason::resource_limit,"fixture cap"});
    const auto report=check_inner_state_plan(problem,binding(problem,reference),methods,
        {{"fixture.approximation"},std::nullopt},request,witness(problem));
    CHECK(report.termination==Termination::resource_limit);
    CHECK_FALSE(report.numerical_achievable_value);
    REQUIRE(report.approximation);
    CHECK(std::holds_alternative<OperationStopped>(*report.approximation));
}
