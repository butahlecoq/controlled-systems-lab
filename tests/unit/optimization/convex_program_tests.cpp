#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/convex_backend.hpp>
#include <cmath>
#include <limits>
using namespace csl;
using namespace csl::optimization;
namespace {
template<class T> T accepted(ConvexDataResult<T> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
ConvexProgramInput parabola() {
    return {{{"p"},{"parabola"}},QuadraticTerminal{{1,1,{2}},{-6},9},
        {0,1,{0},{},{}},{{0,2}},{},{}};
}
const NumericalPolicy tolerance{1e-9,1e-9};
const Verifier verifier{{"literal-convex"},"1"};
}
TEST_CASE("canonical convex publication owns objective bounds and original cost") {
    auto input=parabola();
    auto p=accepted(make_convex_program(input));
    std::get<QuadraticTerminal>(input.objective).Q.values[0]=200;
    input.variables[0].upper=99;
    const auto copy=std::move(p);
    CHECK(p.quadratic_program().hessian()(0,0)==2);
    CHECK(copy.quadratic_program().variables()[0].upper==2);
    const auto e=accepted(evaluate_primal(copy,Vector{2},tolerance,verifier));
    CHECK(e.original_objective==1);
    CHECK(e.solver_objective==1);
    CHECK(e.residuals.variables.violation==0);
    CHECK(e.residuals.context.subject==copy.identity());
}
TEST_CASE("original norm units retain distinct squared identity and literal KKT multipliers") {
    auto input=parabola(); input.objective=ResidualNormTerminal{{2,1,{1,0}},{3,-4}};
    input.squared_program=ProgramId{"squared"};
    const auto p=accepted(make_convex_program(input));
    REQUIRE(p.reformulation()!=nullptr);
    CHECK(p.quadratic_program().identity().program.value=="squared");
    CHECK(p.identity().program.value=="parabola");
    const auto e=accepted(evaluate_primal(p,Vector{2},tolerance,verifier));
    CHECK(e.original_objective==doctest::Approx(std::sqrt(17.0)));
    CHECK(e.solver_objective==17);
    const auto kkt=accepted(evaluate_dual(p,Vector{2},{{},{},{0},{1/std::sqrt(17.0)}},tolerance,verifier));
    CHECK(kkt.stationarity->violation==doctest::Approx(0));
    CHECK(kkt.signs->violation==0);
    CHECK(kkt.complementarity->violation==0);
    const auto wrong=accepted(evaluate_dual(p,Vector{2},{{},{},{0},{2}},tolerance,verifier));
    CHECK(wrong.stationarity->violation==doctest::Approx(2-1/std::sqrt(17.0)));
}
TEST_CASE("literal quadratic equality stationarity signs and complementarity are independent checks") {
    const auto p=accepted(make_convex_program({{{"p"},{"equality"}},QuadraticTerminal{{2,2,{4,2,2,4}},{-8,-10},17},
        {1,2,{0,2},{0,1},{1,1}},{{{},{}},{{},{}}},{{2,2}},{}}));
    const auto e=accepted(evaluate_primal(p,Vector{.5,1.5},tolerance,verifier)); CHECK(e.original_objective==4.5);
    const auto good=accepted(evaluate_dual(p,Vector{.5,1.5},{{0},{3},{0,0},{0,0}},tolerance,verifier));
    CHECK(good.stationarity->violation==0); CHECK(good.stationarity->scale==6); CHECK(good.complementarity->violation==0);
    const auto q=accepted(make_convex_program(parabola()));
    const auto wrong=accepted(evaluate_dual(q,Vector{1},{{},{},{-2},{1}},tolerance,verifier));
    CHECK(wrong.stationarity->violation==1); CHECK(wrong.signs->violation==2); CHECK(wrong.complementarity->violation==2);
    auto offset=parabola(); std::get<QuadraticTerminal>(offset.objective).offset=99; offset.identity.program={"offset"};
    const auto changed=accepted(make_convex_program(offset));
    CHECK(accepted(evaluate_dual(changed,Vector{2},{{},{},{0},{2}},tolerance,verifier)).stationarity->violation==0);
    CHECK(accepted(evaluate_primal(changed,Vector{2},tolerance,verifier)).original_objective==91);
}
TEST_CASE("zero residual subgradient and singular Hessian are legal without regularization") {
    auto input=parabola(); input.objective=ResidualNormTerminal{{1,1,{1}},{3}}; input.variables={{0,5}}; input.squared_program=ProgramId{"square-zero"};
    const auto p=accepted(make_convex_program(input));
    CHECK(accepted(evaluate_primal(p,Vector{3},tolerance,verifier)).original_objective==0);
    CHECK(accepted(evaluate_dual(p,Vector{3},{{},{},{0},{0}},tolerance,verifier)).stationarity->violation==0);
    const auto singular=accepted(make_convex_program({{{"p"},{"singular"}},QuadraticTerminal{{2,2,{2,0,0,0}},{-2,0},1},
        {0,2,{0},{},{}},{{0,2},{0,1}},{},{}}));
    for(double t:{0.0,.25,1.0}) CHECK(accepted(evaluate_primal(singular,Vector{1,t},tolerance,verifier)).original_objective==0);
    auto linear=accepted(make_convex_program({{{"p"},{"linear"}},LinearTerminal{{-3},7},{0,1,{0},{},{}},{{{},2}},{},{}}));
    CHECK(accepted(evaluate_primal(linear,Vector{2},tolerance,verifier)).original_objective==1);
    CHECK(linear.quadratic_program().hessian()(0,0)==0);
}
TEST_CASE("publication rejects malformed identity geometry reformulation and objective data") {
    auto rejected=[](ConvexProgramInput input) { const auto r=make_convex_program(input); REQUIRE(std::holds_alternative<Diagnostics>(r)); CHECK_FALSE(std::get<Diagnostics>(r).empty()); };
    auto input=parabola(); input.identity.program.value.clear(); rejected(input);
    input=parabola();input.variables[0]={3,2};rejected(input);
    input=parabola();input.variables[0].lower=std::numeric_limits<double>::infinity();rejected(input);
    input=parabola();input.constraints.cols=2;rejected(input);
    input=parabola();input.constraints={1,1,{0,1},{0},{std::numeric_limits<double>::quiet_NaN()}};input.rows={{0,0}};rejected(input);
    input=parabola();input.constraints={1,1,{0,2},{0,0},{1,2}};input.rows={{0,0}};rejected(input);
    input=parabola();input.constraints.row_offsets={1};rejected(input);
    input=parabola();input.squared_program=ProgramId{"unnecessary"};rejected(input);
    input=parabola();input.objective=ResidualNormTerminal{{1,1,{1}},{3}};rejected(input);
    input.squared_program=input.identity.program;rejected(input); input.squared_program=ProgramId{""};rejected(input);
    input=parabola();std::get<QuadraticTerminal>(input.objective).Q.values[0]=-1;rejected(input);
    input=parabola();std::get<QuadraticTerminal>(input.objective).Q.values[0]=-1e-12;
    const auto unresolved=make_convex_program(input); REQUIRE(std::holds_alternative<Diagnostics>(unresolved));
    CHECK(std::get<Diagnostics>(unresolved)[0].code==DiagnosticCode::unsupported);
    ConvexProgramInput asymmetric{{{"p"},{"asymmetric"}},QuadraticTerminal{{2,2,{2,1e-10,0,2}},{0,0},0},{0,2,{0},{},{}},std::vector<Interval>(2),{},{}};
    const auto asym=make_convex_program(asymmetric,{Assurance::numerical,{1e-3,1e-3}});
    REQUIRE(std::holds_alternative<Diagnostics>(asym)); CHECK(std::get<Diagnostics>(asym)[0].field=="convex.symmetry");
}
TEST_CASE("owning views and reformulation survive input and program destruction") {
    auto held=[] {
        auto input=parabola();input.objective=ResidualNormTerminal{{2,1,{1,0}},{3,-4}};input.squared_program=ProgramId{"square-owned"};
        const auto p=accepted(make_convex_program(input));
        std::get<ResidualNormTerminal>(input.objective).map.values[0]=999;
        return std::pair{p.quadratic_program().hessian(),*p.reformulation()};
    }();
    CHECK(held.first(0,0)==2);
    CHECK(std::get<double>(evaluate(held.second.original(),Vector{2}))==doctest::Approx(std::sqrt(17.0)));
    CHECK(std::get<double>(evaluate(held.second.squared(),Vector{2}))==17);
    CHECK(held.second.transformation()==ObjectiveTransformation::residual_norm_squared);
}
TEST_CASE("evaluation rejects malformed multipliers and exposes numerical arithmetic failure") {
    auto input=parabola();input.variables={{{},{}}}; const auto p=accepted(make_convex_program(input));
    CHECK(std::holds_alternative<Diagnostics>(evaluate_dual(p,Vector{2},{{},{},{1},{0}},tolerance,verifier)));
    CHECK(std::holds_alternative<Diagnostics>(evaluate_dual(p,Vector{2},{{},{},{},{0}},tolerance,verifier)));
    CHECK(std::holds_alternative<Diagnostics>(evaluate_primal(p,Vector{},tolerance,verifier)));
    CHECK(std::holds_alternative<Diagnostics>(evaluate_primal(p,Vector{2},{-1,0},verifier)));
    CHECK(std::holds_alternative<OperationStopped>(evaluate_primal(p,Vector{1e308},tolerance,verifier)));
    auto extreme=parabola();extreme.variables={{0,1e308}};extreme.identity.program={"arithmetic"};
    const auto q=accepted(make_convex_program(extreme));
    CHECK(std::holds_alternative<OperationStopped>(evaluate_dual(q,Vector{2},{{},{},{0},{1e308}},tolerance,verifier)));
}
TEST_CASE("overflow in original row activities is a numerical stop rather than malformed input") {
    const auto p=accepted(make_convex_program({{{"p"},{"row-overflow"}},LinearTerminal{{0},0},
        {1,1,{0,1},{0},{2}},{{{}, {}}},{{{}, {}}},{}}));
    auto result=evaluate_primal(p,Vector{1e308},tolerance,verifier);
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::numerical_failure);
}
