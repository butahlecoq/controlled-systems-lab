#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/model/discretization.hpp>
#include <csl/model/linear_system.hpp>

#include <cmath>
#include <limits>

using namespace csl;
using namespace csl::model;

namespace {
template<class T,class... Others> T take(std::variant<T,Others...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
LinearStage double_integrator() {
    return {{2,2,{0,1,0,0}},{2,1,{0,1}},{2,0,{}},{0,0}};
}
ContinuousAffineModel source(Vector times) {
    return {{2,1,0},std::move(times),HoldConvention::zero_order_hold,double_integrator()};
}
void check_near(double actual,double expected,double tolerance=1e-11) {
    CHECK(std::abs(actual-expected)<=tolerance);
}
}

TEST_CASE("continuous 2D double integrator uses physical durations and ZOH inputs") {
    const auto converted=take<DiscretizedModel>(discretize(source({0,1,3})));
    CHECK(converted.model.dynamics.time_domain==TimeDomain::discrete);
    CHECK(converted.receipt.source_domain==TimeDomain::continuous);
    CHECK(converted.receipt.output_domain==TimeDomain::discrete);
    CHECK(converted.receipt.hold==HoldConvention::zero_order_hold);
    CHECK(converted.receipt.variation==CoefficientVariation::constant_lti);
    CHECK(converted.receipt.method=="rk4_step_doubling");
    REQUIRE(converted.receipt.stages.size()==2);
    CHECK(converted.receipt.stages[0].accepted_steps>0);
    CHECK(converted.receipt.stages[1].accepted_steps>0);
    const auto& stages=std::get<std::vector<LinearStage>>(converted.model.dynamics.stages);
    REQUIRE(stages.size()==2);
    check_near(stages[0].A.values[1],1);check_near(stages[1].A.values[1],2);
    check_near(stages[0].B.values[0],0.5);check_near(stages[0].B.values[1],1);
    check_near(stages[1].B.values[0],2);check_near(stages[1].B.values[1],2);
    CHECK(stages[0].E.rows==2);CHECK(stages[0].E.cols==0);
    const auto discrete=take<LinearSystem>(snapshot(converted.model,converted.times));
    auto x=take<Vector>(discrete.step({0},Vector{0,0},Vector{2},{}));
    CHECK(x==Vector{1,2});
    x=take<Vector>(discrete.step({1},x,Vector{-1},{}));
    check_near(x[0],3);check_near(x[1],0);
}

TEST_CASE("continuous affine forcing and singular generator stay explicit") {
    ContinuousAffineModel input{{1,0,0},{2,5},HoldConvention::zero_order_hold,
        LinearStage{{1,1,{0}},{1,0,{}},{1,0,{}},{2}}};
    auto converted=take<DiscretizedModel>(discretize(input));
    const auto& stage=std::get<std::vector<LinearStage>>(converted.model.dynamics.stages).at(0);
    check_near(stage.A.values[0],1);check_near(stage.offset[0],6);
    CHECK(stage.B.rows==1);CHECK(stage.B.cols==0);
    CHECK(stage.E.rows==1);CHECK(stage.E.cols==0);
}

TEST_CASE("external input is held across the physical interval") {
    ContinuousAffineModel input{{1,0,1},{2,5},HoldConvention::zero_order_hold,
        LinearStage{{1,1,{0}},{1,0,{}},{1,1,{2}},{1}}};
    const auto converted=take<DiscretizedModel>(discretize(input));
    const auto& stage=std::get<std::vector<LinearStage>>(converted.model.dynamics.stages).at(0);
    check_near(stage.E.values[0],6);
    check_near(stage.offset[0],3);
    const auto discrete=take<LinearSystem>(snapshot(converted.model,converted.times));
    check_near(take<Vector>(discrete.step({0},Vector{4},{},Vector{3}))[0],25);
}

TEST_CASE("receipt owns the exact continuous coefficient records") {
    auto input=source({0,1,3});
    const auto converted=take<DiscretizedModel>(discretize(input));
    auto& original=std::get<LinearStage>(input.coefficients);
    original.A.values[1]=100;
    original.B.values[1]=100;
    const auto& saved=std::get<LinearStage>(converted.receipt.source_coefficients);
    CHECK(saved.A.values==Vector{0,1,0,0});
    CHECK(saved.B.values==Vector{0,1});

    const auto value=[](double a) {
        return LinearStage{{1,1,{a}},{1,0,{}},{1,0,{}},{0}};
    };
    ContinuousAffineModel varying{{1,0,0},{0,1},HoldConvention::zero_order_hold,
        std::vector<CoefficientEndpoints>{{value(0),value(1)}}};
    const auto converted_ltv=take<DiscretizedModel>(discretize(varying));
    std::get<std::vector<CoefficientEndpoints>>(varying.coefficients)[0].end.A.values[0]=9;
    const auto& saved_ltv=std::get<std::vector<CoefficientEndpoints>>(
        converted_ltv.receipt.source_coefficients);
    REQUIRE(saved_ltv.size()==1);
    CHECK(saved_ltv[0].start.A.values==Vector{0});
    CHECK(saved_ltv[0].end.A.values==Vector{1});
}

TEST_CASE("piecewise linear LTV coefficients match independent analytic integrals") {
    const LinearStage a0{{1,1,{0}},{1,0,{}},{1,0,{}},{0}};
    const LinearStage a1{{1,1,{1}},{1,0,{}},{1,0,{}},{0}};
    ContinuousAffineModel growth{{1,0,0},{0,1},HoldConvention::zero_order_hold,
        std::vector<CoefficientEndpoints>{{a0,a1}}};
    auto result=take<DiscretizedModel>(discretize(growth));
    CHECK(result.receipt.variation==CoefficientVariation::piecewise_linear_ltv);
    check_near(std::get<std::vector<LinearStage>>(result.model.dynamics.stages)[0].A.values[0],std::exp(0.5),1e-9);

    const LinearStage b0{{1,1,{0}},{1,1,{1}},{1,0,{}},{0}};
    const LinearStage b1{{1,1,{0}},{1,1,{3}},{1,0,{}},{0}};
    ContinuousAffineModel forcing{{1,1,0},{1,3},HoldConvention::zero_order_hold,
        std::vector<CoefficientEndpoints>{{b0,b1}}};
    result=take<DiscretizedModel>(discretize(forcing));
    check_near(std::get<std::vector<LinearStage>>(result.model.dynamics.stages)[0].B.values[0],4,1e-9);
    const auto discrete=take<LinearSystem>(snapshot(result.model,result.times));
    check_near(take<Vector>(discrete.step({0},Vector{1},Vector{2},{}))[0],9,1e-9);
}

TEST_CASE("LTV intervals retain authored order and independent endpoint values") {
    const auto value=[](double b) {
        return LinearStage{{1,1,{0}},{1,1,{b}},{1,0,{}},{0}};
    };
    ContinuousAffineModel input{{1,1,0},{0,1,2},HoldConvention::zero_order_hold,
        std::vector<CoefficientEndpoints>{{value(0),value(1)},
                                          {value(2),value(4)}}};
    const auto result=take<DiscretizedModel>(discretize(input));
    const auto& stages=std::get<std::vector<LinearStage>>(result.model.dynamics.stages);
    REQUIRE(stages.size()==2);
    check_near(stages[0].B.values[0],0.5);
    check_near(stages[1].B.values[0],3);
    const auto discrete=take<LinearSystem>(snapshot(result.model,result.times));
    auto state=take<Vector>(discrete.step({0},Vector{0},Vector{2},{}));
    check_near(state[0],1);
    state=take<Vector>(discrete.step({1},state,Vector{-1},{}));
    check_near(state[0],-2);
}

TEST_CASE("invalid grids, shapes, options and exhausted budgets publish no model") {
    auto input=source({0,1});
    input.times={0,0};
    CHECK(std::holds_alternative<Diagnostic>(discretize(input)));
    input=source({0,1});
    std::get<LinearStage>(input.coefficients).B.cols=2;
    CHECK(std::holds_alternative<Diagnostic>(discretize(input)));
    input=source({0,1});
    IntegrationOptions invalid;invalid.absolute_tolerance=0;
    CHECK(std::holds_alternative<Diagnostic>(discretize(input,invalid)));
    IntegrationOptions limited;limited.max_attempts_per_stage=1;
    ContinuousAffineModel stiff{{1,0,0},{0,10},HoldConvention::zero_order_hold,
        LinearStage{{1,1,{10}},{1,0,{}},{1,0,{}},{0}}};
    CHECK(std::holds_alternative<OperationStopped>(discretize(stiff,limited)));
    std::stop_source cancelled;cancelled.request_stop();
    IntegrationOptions stopped;stopped.cancellation=cancelled.get_token();
    CHECK(std::holds_alternative<OperationStopped>(discretize(input,stopped)));
    std::get<LinearStage>(input.coefficients).A.values[0]=std::numeric_limits<double>::infinity();
    CHECK(std::holds_alternative<Diagnostic>(discretize(input)));
}

TEST_CASE("stage receipt includes rejected local estimates") {
    ContinuousAffineModel growth{{1,0,0},{0,1},HoldConvention::zero_order_hold,
        LinearStage{{1,1,{10}},{1,0,{}},{1,0,{}},{0}}};
    const auto result=take<DiscretizedModel>(discretize(growth));
    REQUIRE(result.receipt.stages.size()==1);
    CHECK(result.receipt.stages[0].rejected_steps>0);
    CHECK(result.receipt.stages[0].max_local_error_estimate>1);
}

TEST_CASE("augmented width overflow and unresolvable physical times refuse") {
    const auto maximum=std::numeric_limits<std::size_t>::max();
    ContinuousAffineModel huge_port{{0,0,maximum},{0,1},HoldConvention::zero_order_hold,
        LinearStage{{0,0,{}},{0,0,{}},{0,maximum,{}},{}}};
    const auto overflow=discretize(huge_port);
    REQUIRE(std::holds_alternative<OperationStopped>(overflow));
    CHECK(std::get<OperationStopped>(overflow).reason==StopReason::resource_limit);

    auto adjacent=source({1,std::nextafter(1.0,2.0)});
    const auto unresolved=discretize(adjacent);
    REQUIRE(std::holds_alternative<OperationStopped>(unresolved));
    CHECK(std::get<OperationStopped>(unresolved).reason==StopReason::numerical_failure);
}
