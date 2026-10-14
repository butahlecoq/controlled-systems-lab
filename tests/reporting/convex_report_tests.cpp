#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include "convex_report.hpp"
#include <cmath>
#include <limits>
using namespace csl;
using namespace csl::reporting;
TEST_CASE("nine registered convex report fixtures retain literal original and solver objectives") {
    const auto& fixtures=convex::catalogue(); REQUIRE(fixtures.size()==9);
    const double original[]{1,4.5,std::sqrt(17.0),0,5,0,0};
    const double solver[]{1,4.5,17,0,25,0,0};
    for(std::size_t i=0;i<fixtures.size();++i) {
        const auto result=convex::run_trial(fixtures[i],{}); INFO(fixtures[i].id); INFO(result.error);
        for(const auto& error:result.errors) INFO(error);
        REQUIRE(result.passed()); REQUIRE(result.result); REQUIRE(result.program);
        CHECK(result.result->outcome.subject==fixtures[i].input.identity);
        CHECK(std::holds_alternative<Unestablished>(result.result->outcome.support));
        CHECK_FALSE(result.result->objective.lower); CHECK_FALSE(result.result->objective.upper);
        if(i<7) {
            REQUIRE(result.objective); REQUIRE(result.solver_objective);
            CHECK(*result.objective==doctest::Approx(original[i])); CHECK(*result.solver_objective==doctest::Approx(solver[i]));
            REQUIRE(result.result->residuals.dual); REQUIRE(result.result->residuals.dual->complementarity);
        } else CHECK(result.result->outcome.value==(i==7?MathematicalOutcome::infeasible:MathematicalOutcome::unbounded));
        REQUIRE(result.attempt); CHECK(result.attempt->stamp.attempt()==1);
        CHECK(result.result->raw_diagnostics.find(std::string("native.downstream.hvectorbase_sha256=")+CSL_HIGHS_PATCHED_SOURCE_SHA256)!=std::string::npos);
    }
}
TEST_CASE("convex reporter keeps failure timings and pre-cancelled result without optimal claim") {
    std::stop_source stop;stop.request_stop();
    const auto stopped=convex::run_trial(convex::catalogue()[0],stop.get_token());
    CHECK_FALSE(stopped.passed()); REQUIRE(stopped.result);
    CHECK(stopped.result->termination==Termination::cancelled);
    CHECK(stopped.result->outcome.value==MathematicalOutcome::undetermined);
    auto bad=convex::catalogue()[0];bad.input.identity.program={"invalid-dimension-functional"};bad.input.variables.clear();
    const auto invalid=convex::run_trial(bad,{});
    CHECK_FALSE(invalid.passed()); CHECK_FALSE(invalid.timings[3].available);
    CHECK(invalid.timings[5].includes_unwind);
    bad=convex::catalogue()[0];bad.input.identity.program={"nonfinite-functional"};std::get<QuadraticTerminal>(bad.input.objective).offset=std::numeric_limits<double>::infinity();
    CHECK_FALSE(convex::run_trial(bad,{}).passed());
}
TEST_CASE("convex report owns snapshots and distinct exclusive attempts after input mutation") {
    auto input=convex::catalogue()[2];
    const auto first=convex::run_trial(input,{});const auto second=convex::run_trial(input,{});
    REQUIRE(first.passed()); REQUIRE(second.passed()); REQUIRE(first.attempt); REQUIRE(second.attempt);
    CHECK_FALSE(first.attempt->stamp.workspace()==second.attempt->stamp.workspace());
    std::get<ResidualNormTerminal>(input.input.objective).target[0]=999;
    const auto value=optimization::evaluate_primal(*first.program,*first.result->primal,{1e-8,1e-8},{{"owning-literal"},"1"});
    REQUIRE(std::holds_alternative<optimization::ConvexPrimalEvaluation>(value));
    CHECK(std::get<optimization::ConvexPrimalEvaluation>(value).original_objective==doctest::Approx(std::sqrt(17.0)));
    CHECK(std::get<optimization::ConvexPrimalEvaluation>(value).solver_objective==doctest::Approx(17));
    REQUIRE(first.program->reformulation());
    CHECK(first.program->quadratic_program().identity().program.value=="norm-positive-squared");
}
TEST_CASE("constant wrapper, typed rejection and iteration stops remain distinct from completed native fixtures") {
    auto empty=convex::catalogue()[0];empty.id="constant-functional";
    empty.input={{{"convex-report-functional"},{"constant"}},LinearTerminal{{},7},{1,0,{0,0},{},{}},{},{{0,0}},{}};
    empty.point=Vector{};empty.objective=7;empty.solver_objective=7;
    const auto constant=convex::run_trial(empty,{}); REQUIRE(constant.passed());
    CHECK(constant.result->raw_diagnostics.find("wrapper.decision=constant_rows")!=std::string::npos);
    CHECK(constant.result->primal->empty());
    empty.input.identity.program={"constant-contradiction"};empty.input.rows={{1,1}};empty.expected=MathematicalOutcome::infeasible;empty.point.reset();empty.objective.reset();empty.solver_objective.reset();
    const auto bad=convex::run_trial(empty,{});REQUIRE(bad.passed());CHECK(bad.result->outcome.value==MathematicalOutcome::infeasible);
    auto tiny=convex::catalogue()[0];tiny.input.identity.program={"unsupported-tiny"};tiny.input.constraints={1,1,{0,1},{0},{1e-13}};tiny.input.rows={{0,1}};
    const auto unsupported=convex::run_trial(tiny,{});CHECK(unsupported.harness_status=="unsupported");CHECK_FALSE(unsupported.timings[3].available);
    const auto stopped=convex::run_trial(convex::catalogue()[1],{},{{0},{0}});
    REQUIRE(stopped.result);CHECK(stopped.result->termination==Termination::resource_limit);CHECK(stopped.result->outcome.value==MathematicalOutcome::undetermined);CHECK_FALSE(stopped.passed());
}
TEST_CASE("shared failure boundary records actual cleanup before failure end and preserves owning program") {
    const auto trial=convex::run_trial(convex::catalogue()[0],{});REQUIRE(trial.passed());
    csl::reporting::Interval total;Clock::rep destroyed=0;
    struct Owner { ConvexProgram program;Clock::rep& stamp;~Owner(){stamp=Clock::now().time_since_epoch().count();} };
    CHECK_THROWS_AS(record_failure_unwind(total,[&]{Owner owner{*trial.program,destroyed};throw std::runtime_error("literal failure");}),std::runtime_error);
    CHECK(destroyed>0);CHECK(total.end>=destroyed);CHECK(total.includes_unwind);
    CHECK(trial.program->identity().program.value=="quadratic-boundary");
}
