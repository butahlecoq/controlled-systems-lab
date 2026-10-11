#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/linear_program.hpp>
#include <future>
#include <limits>
using namespace csl;
using namespace csl::optimization;
static_assert(!std::is_default_constructible_v<LinearProgram>);
namespace {
template<class T> T accepted(Result<T> result) {
    REQUIRE(std::holds_alternative<T>(result)); return std::get<T>(std::move(result));
}
LinearProgramInput triangle() {
    return {{{"problem"},{"triangle"}}, {-1,-2},0,{1,2,{0,2},{0,1},{1,1}},{{0,{}},{0,{}}},{{{},1}}};
}
const Verifier verifier{{"literal-check"},"1"};
const NumericalPolicy tolerance{1e-9,1e-9};
}
TEST_CASE("immutable LP evaluates the literal optimum, violation and offset") {
    auto input=triangle(); auto p=accepted(make_linear_program(input));
    const auto good=accepted(evaluate_primal(p,Vector{0,1},tolerance,verifier));
    CHECK(good.objective == -2); CHECK(good.residuals.rows.violation == 0);
    CHECK(good.residuals.variables.violation == 0);
    const auto bad=accepted(evaluate_primal(p,Vector{1,1},tolerance,verifier));
    CHECK(bad.objective == -3); CHECK(bad.residuals.rows.violation == 1);
    CHECK(bad.residuals.rows.scale == 2);
    input.offset=7; input.identity.program={"offset"};
    CHECK(accepted(evaluate_primal(accepted(make_linear_program(input)),Vector{0,1},tolerance,verifier)).objective == 5);
}
TEST_CASE("copies and async consumers retain private coefficients after producer mutation and exit") {
    auto p=[] { auto input=triangle(); auto result=accepted(make_linear_program(input));
        input.objective[1]=999; input.constraints.values[0]=999; input.rows[0].upper=-999;
        return result; }();
    const auto copy=p; const auto moved=std::move(p);
    CHECK(copy.objective().values().data() == moved.objective().values().data());
    auto worker=std::async(std::launch::async,[copy] { return accepted(evaluate_primal(copy,Vector{0,1},tolerance,verifier)).objective; });
    CHECK(worker.get() == -2);
    CHECK(accepted(evaluate_primal(p,Vector{0,1},tolerance,verifier)).objective == -2);
}
TEST_CASE("free fixed equality and empty dimensions preserve mathematical data") {
    LinearProgramInput input{{{"p"},{"eq"}},{1,2},4,{1,2,{0,2},{0,1},{1,1}},{{{},{}},{2,2}},{{3,3}}};
    const auto p=accepted(make_linear_program(input));
    const auto evaluation=accepted(evaluate_primal(p,Vector{1,2},tolerance,verifier));
    CHECK(evaluation.objective == 9); CHECK(evaluation.residuals.rows.violation == 0);
    CHECK(evaluation.residuals.variables.violation == 0);
    LinearProgramInput zero{{{"p"},{"zero"}},{},7,{1,0,{0,0},{},{}},{},{{1,{}}}};
    const auto z=accepted(evaluate_primal(accepted(make_linear_program(zero)),Vector{},tolerance,verifier));
    CHECK(z.objective == 7); CHECK(z.residuals.rows.violation == 1);
    zero.constraints={0,0,{0},{},{}}; zero.rows.clear();
    zero.identity.program={"zero-unconstrained"};
    CHECK(accepted(evaluate_primal(accepted(make_linear_program(zero)),Vector{},tolerance,verifier)).residuals.rows.violation == 0);
    LinearProgramInput contradictory{{{"p"},{"infeasible"}},{0},0,{2,1,{0,1,2},{0,0},{1,1}},{{{},{}}},{{{},0},{1,{}}}};
    const auto c=accepted(make_linear_program(contradictory));
    CHECK(accepted(evaluate_primal(c,Vector{0},tolerance,verifier)).residuals.rows.violation == 1);
    LinearProgramInput ray{{{"p"},{"ray"}},{-1},0,{0,1,{0},{},{}},{{0,{}}},{}};
    CHECK(accepted(evaluate_primal(accepted(make_linear_program(ray)),Vector{10},tolerance,verifier)).objective == -10);
}
TEST_CASE("malformed authored data and nonfinite evaluation fail at the seam") {
    auto invalid=[&](LinearProgramInput input) { auto r=make_linear_program(input); REQUIRE(std::holds_alternative<Diagnostics>(r)); CHECK_FALSE(std::get<Diagnostics>(r).empty()); };
    auto input=triangle(); input.variables[0]={2,1}; invalid(input);
    input=triangle(); input.rows[0].upper=std::numeric_limits<double>::infinity(); invalid(input);
    input=triangle(); input.objective.pop_back(); invalid(input);
    input=triangle(); input.constraints.column_indices={1,0}; invalid(input);
    input=triangle(); input.constraints.row_offsets={0,9}; invalid(input);
    input=triangle(); input.offset=std::numeric_limits<double>::quiet_NaN(); invalid(input);
    input=triangle(); input.identity.program.value.clear(); invalid(input);
    const auto p=accepted(make_linear_program(triangle()));
    CHECK(std::holds_alternative<Diagnostics>(evaluate_primal(p,Vector{1},tolerance,verifier)));
    CHECK(std::holds_alternative<Diagnostics>(evaluate_primal(p,Vector{0,1},{-1,0},verifier)));
    CHECK(std::holds_alternative<Diagnostics>(evaluate_primal(p,Vector{0,std::numeric_limits<double>::max()},tolerance,verifier)));
}

TEST_CASE("primal checks reject overflowing tolerance comparisons instead of accepting everything") {
    const auto p=accepted(make_linear_program(triangle()));
    const auto r=evaluate_primal(p,Vector{1,1},{0,std::numeric_limits<double>::max()},verifier);
    REQUIRE(std::holds_alternative<Diagnostics>(r));
    CHECK(std::get<Diagnostics>(r)[0].field == "lp.primal.arithmetic");
}
