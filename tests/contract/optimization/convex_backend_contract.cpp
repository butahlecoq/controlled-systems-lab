#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/convex/highs.hpp>
#include <charconv>
#include <cmath>
#include <memory>
#include <string_view>
#include <system_error>
#include <utility>
#include <variant>

using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;
using namespace csl::adapters::convex;

namespace {
template<class T, class... R> T accepted(std::variant<T, R...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}

ProgramResult solve_registered(const ConvexProgram& program) {
    Registry<ConvexPort> registry;
    REQUIRE_FALSE(registry.add(accepted(make_highs_registration())));
    Requirements requirements;
    requirements.output.representation={"csl.program-result.v1"};
    auto plan=accepted(prepare_pipeline(select(registry,Method{{"csl.convex.highs"},{}},program,requirements)));
    auto [workspace]=plan.create();
    ExecutionContext context{std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),
        {},{},{1e-8,1e-8},"test-06-literal"};
    return accepted(workspace->run(context));
}

void check_numerical_point(const ProgramResult& result,const ConvexProgram& program) {
    INFO(result.raw_diagnostics);
    CHECK(result.termination==Termination::completed);
    CHECK(result.outcome.value==MathematicalOutcome::optimal);
    CHECK(result.outcome.subject==program.identity());
    REQUIRE(result.primal);
    REQUIRE(result.residuals.primal);
    REQUIRE(result.residuals.dual);
    REQUIRE(result.residuals.dual->stationarity);
    CHECK(result.residuals.primal->context.subject==program.identity());
    CHECK(result.residuals.dual->context.subject==program.identity());
    CHECK(result.residuals.primal->context.verifier.id.value=="csl.convex.highs.primal");
    CHECK(result.residuals.primal->context.verifier.version=="1");
    CHECK(result.residuals.dual->context.verifier.id.value=="csl.convex.highs.kkt");
    CHECK(result.residuals.dual->context.verifier.version=="1");
    CHECK(result.residuals.primal->rows.violation<=1e-8);
    CHECK(result.residuals.primal->variables.violation<=1e-8);
    CHECK(result.residuals.dual->stationarity->violation<=1e-8);
    CHECK(check_program_result(result,program,Assurance::numerical).empty());
}

void check_reported_original_cost(const ProgramResult& result,double independent_cost) {
    constexpr std::string_view marker="\nobjective.original=";
    const std::string_view raw=result.raw_diagnostics;
    const auto position=raw.rfind(marker); // A retried QP can retain earlier attempts.
    REQUIRE(position!=std::string_view::npos);
    const auto start=position+marker.size();
    const auto end=raw.find_first_of("\r\n",start);
    const auto number=raw.substr(start,end==std::string_view::npos?raw.size()-start:end-start);
    double reported=0;
    const auto [parsed,error]=std::from_chars(number.data(),number.data()+number.size(),reported);
    REQUIRE(error==std::errc{});
    REQUIRE(parsed==number.data()+number.size());
    REQUIRE(std::isfinite(reported));
    // The adapter emits 17 digits; this allows arithmetic rounding in these small QPs.
    CHECK(std::abs(reported-independent_cost)<=1e-12*(1+std::abs(independent_cost)));
}
}

TEST_CASE("registered convex boundary QP returns the hand-solved original cost") {
    // (x-2)^2 = (1/2)(2)x^2 - 4x + 4 on 0 <= x <= 1.
    const auto program=accepted(make_convex_program({{{"test-06"},{"bounded-parabola"}},
        QuadraticTerminal{{1,1,{2}},{-4},4},{0,1,{0},{},{}},{{0,1}},{},{}}));
    const auto result=solve_registered(program);
    check_numerical_point(result,program);
    const double x=result.primal->at(0);
    const double independent_cost=(x-2)*(x-2);
    const double derivative=2*(x-2);
    CHECK(x==doctest::Approx(1).epsilon(1e-8));
    CHECK(independent_cost==doctest::Approx(1).epsilon(1e-8));
    CHECK(derivative==doctest::Approx(-2).epsilon(1e-8));
    CHECK(accepted(evaluate(program.original_objective(),*result.primal))==doctest::Approx(independent_cost));
    check_reported_original_cost(result,independent_cost);
}

TEST_CASE("registered convex singular QP returns one point without claiming its whole optimal segment") {
    // (x+y-1)^2 has distinct zero-cost minimizers (0,1) and (1,0).
    const auto program=accepted(make_convex_program({{{"test-06"},{"coupled-segment"}},
        QuadraticTerminal{{2,2,{2,2,2,2}},{-2,-2},1},
        {0,2,{0},{},{}},{{0,1},{0,1}},{},{}}));
    const auto result=solve_registered(program);
    check_numerical_point(result,program);
    const double x=result.primal->at(0), y=result.primal->at(1);
    const double residual=x+y-1;
    const double independent_cost=residual*residual;
    CHECK(x>=-1e-8); CHECK(x<=1+1e-8);
    CHECK(y>=-1e-8); CHECK(y<=1+1e-8);
    CHECK(residual==doctest::Approx(0).epsilon(1e-8));
    CHECK(independent_cost==doctest::Approx(0).epsilon(1e-8));
    CHECK(accepted(evaluate(program.original_objective(),*result.primal))==doctest::Approx(independent_cost));
    check_reported_original_cost(result,independent_cost);
    CHECK(accepted(evaluate(program.original_objective(),Vector{0,1}))==doctest::Approx(0));
    CHECK(accepted(evaluate(program.original_objective(),Vector{1,0}))==doctest::Approx(0));
    CHECK(std::holds_alternative<Unestablished>(result.outcome.support));
    CHECK_FALSE(result.objective.lower);
    CHECK_FALSE(result.objective.upper);

    Registry<ConvexPort> registry;
    REQUIRE_FALSE(registry.add(accepted(make_highs_registration())));
    Requirements complete_family;
    complete_family.output.representation={"csl.program-result.v1"};
    complete_family.output.family=FamilyTarget::exact_optimal_relation;
    complete_family.output.completeness=Completeness::established;
    CHECK(std::holds_alternative<Rejection>(prepare_pipeline(
        select(registry,Method{{"csl.convex.highs"},{}},program,complete_family))));
}

TEST_CASE("registered unconstrained positive-definite QP respects the translated half-Hessian factor") {
    // Q=[4,2;2,4], q=[-8,-10], c=14: gradient Qz+q vanishes at (1,2).
    const auto program=accepted(make_convex_program({{{"test-06"},{"unconstrained-pd"}},
        QuadraticTerminal{{2,2,{4,2,2,4}},{-8,-10},14},
        {0,2,{0},{},{}},{{{},{}},{{},{}}},{},{}}));
    const auto result=solve_registered(program);
    check_numerical_point(result,program);
    const double x=result.primal->at(0), y=result.primal->at(1);
    const double independent_cost=2*x*x+2*x*y+2*y*y-8*x-10*y+14;
    const double gradient_x=4*x+2*y-8, gradient_y=2*x+4*y-10;
    CHECK(x==doctest::Approx(1).epsilon(1e-8));
    CHECK(y==doctest::Approx(2).epsilon(1e-8));
    CHECK(independent_cost==doctest::Approx(0).epsilon(1e-8));
    CHECK(gradient_x==doctest::Approx(0).epsilon(1e-8));
    CHECK(gradient_y==doctest::Approx(0).epsilon(1e-8));
    CHECK(accepted(evaluate(program.original_objective(),*result.primal))==doctest::Approx(independent_cost));
    check_reported_original_cost(result,independent_cost);
}
