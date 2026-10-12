#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/verification/trajectory.hpp>
#include <algorithm>
#include <limits>
using namespace csl;
using namespace csl::verification;
namespace {
template<class T,class... Rest> T accepted(std::variant<T,Rest...> result) {
    REQUIRE(std::holds_alternative<T>(result));return std::get<T>(std::move(result));
}
Problem scalar() {
    return {{"authored"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{0}},{1,1,{1}},{1,0,{}},{0}}},{}}),{0,1},KnownInitial{{2}},
        ContinuousDomain{{Singleton{{3}}}},{UniversalSet{1},UniversalSet{1}},{},{},InformationPattern::nominal_open_loop,LinearTerminal{{1},0}};
}
problem::ResolvedProblem resolve(Problem p) {return accepted(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));}
TrajectoryRequest request(const problem::ResolvedProblem& p) {TrajectoryRequest r;r.witness={p.identity(),{{2},{3}},{{3}},3};return r;}
const NamedResidual& residual(const TrajectoryReport& r,const std::string& field) {
    auto found=std::find_if(r.residuals.begin(),r.residuals.end(),[&](const auto& x){return x.field==field;});
    REQUIRE(found!=r.residuals.end());return *found;
}
}
TEST_CASE("literal original trajectory passes without a solver success flag") {
    auto p=resolve(scalar());auto r=verify_trajectory(p,request(p));
    CHECK(r.bindings==CheckStatus::numerical_pass);CHECK(r.feasibility==CheckStatus::numerical_pass);
    CHECK(r.objective==CheckStatus::numerical_pass);REQUIRE(r.recomputed_objective);CHECK(*r.recomputed_objective==3);
    CHECK(r.optimality==CheckStatus::unsupported);CHECK(r.completeness==CheckStatus::unsupported);
    CHECK(r.validated==CheckStatus::unsupported);CHECK(r.membership_queries.empty());
}
TEST_CASE("wrong original transition control and cost each have named residuals") {
    auto p=resolve(scalar());auto q=request(p);q.witness.states[1][0]=4;q.witness.controls[0][0]=5;q.witness.original_objective=9;
    auto r=verify_trajectory(p,q);CHECK(r.feasibility==CheckStatus::violation);CHECK(r.objective==CheckStatus::violation);
    CHECK(residual(r,"dynamics[0][0]").measure.violation==1);
    CHECK(residual(r,"controls[0].singleton[0]").measure.violation==2);
    CHECK(residual(r,"objective").measure.violation==5);
}
TEST_CASE("wrong problem and evidence never pass binding") {
    auto p=resolve(scalar());auto q=request(p);q.witness.problem={"wrong"};
    auto r=verify_trajectory(p,q);CHECK(r.bindings==CheckStatus::invalid_input);CHECK(r.feasibility==CheckStatus::not_checked);
    q=request(p);q.bounds.lower=ObjectiveBound{3,{{"wrong"},CertificateReference{"certificate","untrusted"}}};
    r=verify_trajectory(p,q);CHECK(r.bindings==CheckStatus::invalid_input);REQUIRE(r.input.bounds.lower);
    CHECK(r.input.bounds.lower->evidence.problem.value=="wrong");
}
