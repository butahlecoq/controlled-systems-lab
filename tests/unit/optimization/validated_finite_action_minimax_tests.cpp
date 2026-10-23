#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/validated_finite_action_minimax.hpp>
#include <cfenv>
#include <limits>

TEST_CASE("validated minimax public API types are available") {
    CHECK(std::variant_size_v<csl::optimization::ValidatedFiniteActionMinimaxOutcome> == 7);
}

namespace {
using namespace csl;
using namespace csl::optimization;
template<class T> T take(std::variant<T, Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
sets::SetData singleton(std::string id,double x) {
    return take(sets::make_singleton({{std::move(id)},1,{"x"}},
        take(numeric::snapshot_vector(Vector{x}))));
}
sets::SetData equality(std::string id,double coefficient,double target) {
    return take(sets::make_h({{std::move(id)},1,{"x"}},
        {take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{})),
         take(numeric::snapshot(Matrix{1,1,{coefficient}})),
         take(numeric::snapshot_vector(Vector{target}))}));
}
optimization::Objective linear() {
    auto result=optimization::snapshot(LinearTerminal{{1},0});
    REQUIRE(std::holds_alternative<optimization::Objective>(result));
    return std::get<optimization::Objective>(std::move(result));
}
ValidatedFiniteActionMinimaxRequest zero_horizon(sets::SetData initial,
        sets::SetData safe) {
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{0}},{1,1,{1}},{0}}},{}};
    const auto system=take(model::snapshot(authored,Vector{0}));
    return {{"p"},{"r"},system,std::move(initial),{1,{}},{},{std::move(safe)},linear()};
}
}

TEST_CASE("zero-horizon exact equality has a zero-width validated bound") {
    auto h=equality("eq",1,0);
    const auto outcome=validated_finite_action_minimax(
        zero_horizon(singleton("x0",0),h),{1,1,100});
    REQUIRE(std::holds_alternative<ValidatedMinimaxBounds>(outcome));
    const auto& bounds=std::get<ValidatedMinimaxBounds>(outcome);
    CHECK(bounds.lower()==0.0);
    CHECK(bounds.upper()==0.0);
    CHECK(bounds.exact_value());
    REQUIRE(bounds.plans().size()==1);
    CHECK(std::holds_alternative<ValidatedPlanFeasible>(bounds.plans()[0]));
}

TEST_CASE("strict singleton violation is infeasible and equality overlap stays unresolved") {
    const auto infeasible=validated_finite_action_minimax(
        zero_horizon(singleton("x0",0),singleton("safe-point",1)),{1,1,100});
    REQUIRE(std::holds_alternative<ValidatedMinimaxInfeasible>(infeasible));
    const auto& all_bad=std::get<ValidatedMinimaxInfeasible>(infeasible);
    REQUIRE(all_bad.plans().size()==1);
    const auto& bad=std::get<ValidatedPlanInfeasible>(all_bad.plans()[0]);
    CHECK(bad.witness.history.initial_vertex==0);
    CHECK(bad.witness.kind==ConstraintKind::singleton_coordinate);
    CHECK(bad.witness.residual.lower<0);
    CHECK(bad.witness.residual.upper<0);

    const auto unresolved=validated_finite_action_minimax(
        zero_horizon(singleton("x01",0.1),equality("rounded-boundary",0.1,0.01)),
        {1,1,100});
    REQUIRE(std::holds_alternative<ValidatedMinimaxUnresolved>(unresolved));
    const auto& pending=std::get<ValidatedMinimaxUnresolved>(unresolved);
    REQUIRE(pending.plans().size()==1);
    CHECK(std::holds_alternative<ValidatedPlanUnresolved>(pending.plans()[0]));
    CHECK(std::get<ValidatedPlanUnresolved>(pending.plans()[0]).first_overlap.residual.lower<=0);
    CHECK(std::get<ValidatedPlanUnresolved>(pending.plans()[0]).first_overlap.residual.upper>=0);
}

TEST_CASE("empty catalogues and empty scenarios have separate validated outcomes") {
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{0}},{1,1,{1}},{0}}},{}};
    const auto system=take(model::snapshot(authored,Vector{0,1}));
    const auto disturbance=singleton("w",0);
    const auto safe0=equality("safe0",1,0),safe1=equality("safe1",1,0);
    ValidatedFiniteActionMinimaxRequest input{{"p"},{"r"},system,singleton("x0",0),
        {1,{}},{disturbance},{safe0,safe1},linear()};
    CHECK(std::holds_alternative<ValidatedMinimaxEmptyCatalogue>(
        validated_finite_action_minimax(input,{1,1,100})));
    input.initial=take(sets::make_empty({{"no-x"},1,{"x"}}));
    CHECK(std::holds_alternative<ValidatedMinimaxNoScenarios>(
        validated_finite_action_minimax(input,{1,1,100})));
    input.initial=singleton("x0-again",0);
    input.disturbances[0]=take(sets::make_empty({{"no-w"},1,{"w"}}));
    CHECK(std::holds_alternative<ValidatedMinimaxNoScenarios>(
        validated_finite_action_minimax(input,{1,1,100})));
}

TEST_CASE("linear objective bounds enclose the maximum on a terminal segment") {
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{0}},{1,1,{1}},{0}}},{}};
    const auto system=take(model::snapshot(authored,Vector{0}));
    const auto segment=take(sets::make_v({{"segment"},1,{"x"}},
        {take(numeric::snapshot(Matrix{2,1,{-1,1}})),
         take(numeric::snapshot(Matrix{0,1,{}}))}));
    const auto universal=take(sets::make_universal({{"all"},1,{"x"}}));
    ValidatedFiniteActionMinimaxRequest input{{"p"},{"segment"},system,segment,
        {1,{}},{},{universal},linear()};
    const auto result=validated_finite_action_minimax(input,{1,2,100});
    REQUIRE(std::holds_alternative<ValidatedMinimaxBounds>(result));
    CHECK(std::get<ValidatedMinimaxBounds>(result).lower()==1.0);
    CHECK(std::get<ValidatedMinimaxBounds>(result).upper()==1.0);
}

TEST_CASE("catalogue fold keeps feasible upper bounds and excludes proven violations") {
    const SystemModel authored{{{1,1,1},TimeDomain::discrete,
        LinearStage{{1,1,{0}},{1,1,{1}},{1,1,{0}},{0}}},{}};
    const auto system=take(model::snapshot(authored,Vector{0,1}));
    auto safe=take(sets::make_h({{"x-le-zero"},1,{"x"}},
        {take(numeric::snapshot(Matrix{1,1,{1}})),
         take(numeric::snapshot_vector(Vector{0})),
         take(numeric::snapshot(Matrix{0,1,{}})),
         take(numeric::snapshot_vector(Vector{}))}));
    ValidatedFiniteActionMinimaxRequest input{{"p"},{"mixed"},system,singleton("x0",0),
        {1,{{0},{1}}},{singleton("w",0)},{safe,safe},linear()};
    const auto result=validated_finite_action_minimax(input,{2,1,100});
    REQUIRE(std::holds_alternative<ValidatedMinimaxBounds>(result));
    const auto& bounds=std::get<ValidatedMinimaxBounds>(result);
    CHECK(bounds.lower()==0);
    CHECK(bounds.upper()==0);
    REQUIRE(bounds.plans().size()==2);
    CHECK(std::holds_alternative<ValidatedPlanFeasible>(bounds.plans()[0]));
    CHECK(std::holds_alternative<ValidatedPlanInfeasible>(bounds.plans()[1]));
}

TEST_CASE("operation caps and cancellation stop without partial ledger") {
    auto input=zero_horizon(singleton("x0",0),equality("safe",1,0));
    const auto limited=validated_finite_action_minimax(input,{1,1,0});
    REQUIRE(std::holds_alternative<OperationStopped>(limited));
    CHECK(std::get<OperationStopped>(limited).reason==StopReason::resource_limit);
    std::stop_source source;
    source.request_stop();
    ExecutionContext context{};
    context.cancellation=source.get_token();
    const auto cancelled=validated_finite_action_minimax(input,{1,1,100},context);
    REQUIRE(std::holds_alternative<OperationStopped>(cancelled));
    CHECK(std::get<OperationStopped>(cancelled).reason==StopReason::cancelled);
}

TEST_CASE("two-dimensional finite catalogue matches a literal analytic fixture") {
    const SystemModel authored{{{2,2,2},TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}},{2,2,{1,0,0,1}},{2,2,{1,0,0,1}},{0,0}}},{}};
    const auto system=take(model::snapshot(authored,Vector{0,1}));
    const auto initial=take(sets::make_singleton({{"x0-2d"},2,{"x","y"}},
        take(numeric::snapshot_vector(Vector{0,0}))));
    const auto disturbances=take(sets::make_v({{"w-square"},2,{"wx","wy"}},
        {take(numeric::snapshot(Matrix{4,2,{-0.25,-0.25,-0.25,0.25,
                                           0.25,-0.25,0.25,0.25}})),
         take(numeric::snapshot(Matrix{0,2,{}}))}));
    const auto safe=take(sets::make_h({{"safe-square"},2,{"x","y"}},
        {take(numeric::snapshot(Matrix{4,2,{1,0,-1,0,0,1,0,-1}})),
         take(numeric::snapshot_vector(Vector{0.5,0.5,0.5,0.5})),
         take(numeric::snapshot(Matrix{0,2,{}})),
         take(numeric::snapshot_vector(Vector{}))}));
    auto objective=optimization::snapshot(ResidualNormTerminal{
        {2,2,{1,0,0,1}},{0,0}});
    REQUIRE(std::holds_alternative<optimization::Objective>(objective));
    ValidatedFiniteActionMinimaxRequest input{{"p-2d"},{"analytic-2d"},system,initial,
        {2,{{0,0},{1,0}}},{disturbances},{safe,safe},
        std::get<optimization::Objective>(std::move(objective))};
    const auto result=validated_finite_action_minimax(input,{2,4,10000});
    REQUIRE(std::holds_alternative<ValidatedMinimaxBounds>(result));
    const auto& bounds=std::get<ValidatedMinimaxBounds>(result);
    CHECK(bounds.lower()<=std::sqrt(1.0/8.0));
    CHECK(bounds.upper()>=std::sqrt(1.0/8.0));
    REQUIRE(bounds.plans().size()==2);
    CHECK(std::holds_alternative<ValidatedPlanFeasible>(bounds.plans()[0]));
    REQUIRE(std::holds_alternative<ValidatedPlanInfeasible>(bounds.plans()[1]));
    const auto& witness=std::get<ValidatedPlanInfeasible>(bounds.plans()[1]).witness;
    CHECK(witness.stage==1);
    CHECK(witness.history.initial_vertex==0);
    CHECK(witness.history.disturbance_vertices==std::vector<std::size_t>{0});
    CHECK(witness.residual.lower>0);
}

TEST_CASE("unresolved plans lower the global bound but cannot supply its upper bound") {
    const SystemModel authored{{{2,1,1},TimeDomain::discrete,
        LinearStage{{2,2,{0,0,0,0}},{2,1,{-5,0.1}},{2,1,{0,0}},{1,0}}},{}};
    const auto system=take(model::snapshot(authored,Vector{0,1}));
    const auto initial=take(sets::make_singleton({{"x0-mixed"},2,{"x","y"}},
        take(numeric::snapshot_vector(Vector{0,0}))));
    const auto disturbance=take(sets::make_singleton({{"w-mixed"},1,{"w"}},
        take(numeric::snapshot_vector(Vector{0}))));
    const auto safe=take(sets::make_h({{"mixed-safe"},2,{"x","y"}},
        {take(numeric::snapshot(Matrix{2,2,{1,0,0,1}})),
         take(numeric::snapshot_vector(Vector{1,0.01})),
         take(numeric::snapshot(Matrix{0,2,{}})),
         take(numeric::snapshot_vector(Vector{}))}));
    auto cost=optimization::snapshot(LinearTerminal{{1,0},0});
    REQUIRE(std::holds_alternative<optimization::Objective>(cost));
    ValidatedFiniteActionMinimaxRequest input{{"p"},{"mixed-evidence"},system,initial,
        {1,{{0},{0.1}}},{disturbance},{take(sets::make_universal({{"all0"},2,{"x","y"}})),safe},
        std::get<optimization::Objective>(std::move(cost))};
    const auto result=validated_finite_action_minimax(input,{2,1,1000});
    REQUIRE(std::holds_alternative<ValidatedMinimaxBounds>(result));
    const auto& bounds=std::get<ValidatedMinimaxBounds>(result);
    REQUIRE(bounds.plans().size()==2);
    CHECK(std::holds_alternative<ValidatedPlanFeasible>(bounds.plans()[0]));
    CHECK(std::holds_alternative<ValidatedPlanUnresolved>(bounds.plans()[1]));
    CHECK(bounds.lower()>0.49);
    CHECK(bounds.lower()<0.51);
    CHECK(bounds.upper()==1.0);
}

TEST_CASE("quadratic objective and non-nearest rounding are rejected") {
    auto input=zero_horizon(singleton("x0",0),equality("safe",1,0));
    auto quadratic=optimization::snapshot(QuadraticTerminal{{1,1,{2}},{0},0});
    REQUIRE(std::holds_alternative<optimization::Objective>(quadratic));
    input.objective=std::get<optimization::Objective>(std::move(quadratic));
    CHECK(std::holds_alternative<Unsupported>(
        validated_finite_action_minimax(input,{1,1,100})));
    input.objective=linear();
    const int previous=std::fegetround();
    REQUIRE(std::fesetround(FE_DOWNWARD)==0);
    const auto result=validated_finite_action_minimax(input,{1,1,100});
    CHECK(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::numerical_failure);
    CHECK(std::fesetround(previous)==0);
}

TEST_CASE("finite input overflow stops without a partial catalogue") {
    const auto huge=std::numeric_limits<double>::max();
    auto input=zero_horizon(singleton("x0-max",huge),
        take(sets::make_universal({{"all"},1,{"x"}})));
    auto cost=optimization::snapshot(LinearTerminal{{2},0});
    REQUIRE(std::holds_alternative<optimization::Objective>(cost));
    input.objective=std::get<optimization::Objective>(std::move(cost));
    const auto result=validated_finite_action_minimax(input,{1,1,100});
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::numerical_failure);
}
