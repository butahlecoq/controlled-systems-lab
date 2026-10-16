#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/convex/highs.hpp>
#include <algorithm>
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

ProgramResult solve_registered(const ConvexProgram& program,HighsConvexOptions options={}) {
    Registry<ConvexPort> registry;
    REQUIRE_FALSE(registry.add(accepted(make_highs_registration(options))));
    Requirements requirements;
    requirements.output.representation={"csl.program-result.v1"};
    auto plan=accepted(prepare_pipeline(select(registry,Method{{"csl.convex.highs"},{}},program,requirements)));
    auto [workspace]=plan.create();
    ExecutionContext context{std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),
        {},{},{1e-8,1e-8},"test-06-literal"};
    return accepted(workspace->run(context));
}

void check_numerical_point(const ProgramResult& result,const ConvexProgram& program);
void check_reported_original_cost(const ProgramResult& result,double independent_cost);

TEST_CASE("convex publication rejects nonconvex and unresolved quadratic curvature") {
    // A negative 1D Hessian has eigenvalue -2; a tiny negative eigenvalue
    // stays unresolved under the numerical PSD policy, never silently clipped.
    for(const auto [hessian,code]: {
        std::pair{-2.0,DiagnosticCode::invalid_input},
        std::pair{-1e-10,DiagnosticCode::unsupported}}) {
        const auto input=ConvexProgramInput{{{"test-06"},{"curvature-preflight"}},
            QuadraticTerminal{{1,1,{hessian}},{0},0},
            {0,1,{0},{},{}},{{0,1}},{},{}};
        const auto published=make_convex_program(input);
        REQUIRE(std::holds_alternative<Diagnostics>(published));
        const auto& diagnostics=std::get<Diagnostics>(published);
        REQUIRE(diagnostics.size()==1);
        CHECK(diagnostics[0].code==code);
        CHECK(diagnostics[0].field=="objective.psd");
    }
}

TEST_CASE("registered convex port rejects unavailable evidence before creating a workspace") {
    const auto program=accepted(make_convex_program({{{"test-06"},{"unsupported-evidence"}},
        QuadraticTerminal{{1,1,{2}},{-4},4},{0,1,{0},{},{}},{{0,1}},{},{}}));
    Registry<ConvexPort> registry;
    REQUIRE_FALSE(registry.add(accepted(make_highs_registration())));
    Requirements requested;
    requested.output.representation={"csl.program-result.v1"};
    requested.output.assurance=Assurance::validated;
    const auto prepared=prepare_pipeline(select(registry,Method{{"csl.convex.highs"},{}},program,requested));
    REQUIRE(std::holds_alternative<Rejection>(prepared));
    const auto& rejection=std::get<Rejection>(prepared);
    CHECK(rejection.provenance.port=="convex");
    CHECK(rejection.provenance.requested.id.value=="csl.convex.highs");
    REQUIRE(rejection.provenance.actual);
    CHECK(rejection.provenance.actual->id.value=="csl.convex.highs");
    REQUIRE_FALSE(rejection.diagnostics.empty());
    CHECK(rejection.diagnostics[0].code==DiagnosticCode::unsupported);
    CHECK(rejection.diagnostics[0].field=="output.assurance");
}

TEST_CASE("registered convex finite infeasible and QP iteration-limit outcomes stay distinct") {
    const auto finite=accepted(make_convex_program({{{"test-06"},{"status-finite"}},
        QuadraticTerminal{{1,1,{2}},{-4},4},{0,1,{0},{},{}},{{0,1}},{},{}}));
    const auto solved=solve_registered(finite);
    check_numerical_point(solved,finite);
    CHECK(solved.primal->at(0)==doctest::Approx(1).epsilon(1e-8));
    CHECK((solved.primal->at(0)-2)*(solved.primal->at(0)-2)==doctest::Approx(1).epsilon(1e-8));
    CHECK(solved.residuals.primal->variables.violation==doctest::Approx(0).epsilon(1e-8));
    check_reported_original_cost(solved,1);

    // x is within [0,1], while the authored row requires x>=2.
    const auto impossible=accepted(make_convex_program({{{"test-06"},{"status-infeasible"}},
        QuadraticTerminal{{1,1,{2}},{-4},4},
        {1,1,{0,1},{0},{1}},{{0,1}},{{2,{}}},{}}));
    const auto infeasible=solve_registered(impossible);
    INFO(infeasible.raw_diagnostics);
    CHECK(infeasible.termination==Termination::completed);
    CHECK(infeasible.outcome.value==MathematicalOutcome::infeasible);
    CHECK(infeasible.outcome.subject==impossible.identity());
    CHECK(std::holds_alternative<Unestablished>(infeasible.outcome.support));
    CHECK(infeasible.raw_diagnostics.find("phase.feasibility.model_status=8\n")!=std::string::npos);
    CHECK(infeasible.raw_diagnostics.find("phase.qp.api_status=")==std::string::npos);
    if(infeasible.primal) {
        REQUIRE(infeasible.residuals.primal);
        const double x=infeasible.primal->at(0);
        const double independent_cost=(x-2)*(x-2);
        const double row_violation=std::max(0.0,2-x);
        const double variable_violation=std::max({0.0,-x,x-1});
        CHECK(accepted(evaluate(impossible.original_objective(),*infeasible.primal))==doctest::Approx(independent_cost));
        check_reported_original_cost(infeasible,independent_cost);
        CHECK(std::max(row_violation,variable_violation)>=0.5);
        CHECK(infeasible.residuals.primal->context.subject==impossible.identity());
        CHECK(infeasible.residuals.primal->rows.violation==doctest::Approx(row_violation).epsilon(1e-8));
        CHECK(infeasible.residuals.primal->variables.violation==doctest::Approx(variable_violation).epsilon(1e-8));
    }
    CHECK_FALSE(infeasible.objective.lower);
    CHECK_FALSE(infeasible.objective.upper);

    const auto limited=solve_registered(finite,{{},0});
    INFO(limited.raw_diagnostics);
    CHECK(limited.termination==Termination::resource_limit);
    CHECK(limited.outcome.value==MathematicalOutcome::undetermined);
    CHECK(limited.outcome.subject==finite.identity());
    CHECK(std::holds_alternative<Unestablished>(limited.outcome.support));
    CHECK(limited.raw_diagnostics.find("options.qp_iteration_limit=0\n")!=std::string::npos);
    CHECK(limited.raw_diagnostics.find("phase.qp.model_status=14\n")!=std::string::npos);
    CHECK(limited.raw_diagnostics.find("phase.qp.iterations=0\n")!=std::string::npos);
    if(limited.primal) {
        const double x=limited.primal->at(0);
        const double independent_cost=(x-2)*(x-2);
        CHECK(accepted(evaluate(finite.original_objective(),*limited.primal))==doctest::Approx(independent_cost));
        check_reported_original_cost(limited,independent_cost);
        REQUIRE(limited.residuals.primal);
        CHECK(limited.residuals.primal->context.subject==finite.identity());
        CHECK(limited.residuals.primal->variables.violation==doctest::Approx(std::max({0.0,-x,x-1})).epsilon(1e-8));
    }
    if(limited.residuals.dual)
        CHECK(limited.residuals.dual->context.subject==finite.identity());
    CHECK_FALSE(limited.objective.lower);
    CHECK_FALSE(limited.objective.upper);
    CHECK(check_program_result(limited,finite,Assurance::numerical).empty());
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
