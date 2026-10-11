#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/convex/highs.hpp>
#include <barrier>
#include <future>
#include <cmath>
#include <limits>
using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;
using namespace csl::adapters::convex;
namespace {
template<class T,class... R> T accepted(std::variant<T,R...> r) {
    if constexpr(std::is_same_v<T,ProgramResult>) if(auto* u=std::get_if<Unsupported>(&r))
        for(const auto& d:u->diagnostics) INFO(d.field << ": " << d.explanation);
    REQUIRE(std::holds_alternative<T>(r)); return std::get<T>(std::move(r));
}
ConvexProgramInput parabola(double upper=5) {
    return {{{"native-convex"},{upper==5?"interior":"boundary"}},QuadraticTerminal{{1,1,{2}},{-6},9},{0,1,{0},{},{}},{{0,upper}},{},{}};
}
auto prepare(const ConvexProgram& p,HighsConvexOptions options={}) {
    Registry<ConvexPort> registry;
    REQUIRE_FALSE(registry.add(accepted(make_highs_registration(options))));
    Requirements requirements; requirements.output.representation={"csl.program-result.v1"};
    return accepted(prepare_pipeline(select(registry,Method{{"csl.convex.highs"},{}},p,requirements)));
}
ExecutionContext context() {
    return {std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),{},{},{1e-8,1e-8},"convex-native"};
}
void optimum(const ProgramResult& r,const ConvexProgram& p,double value) {
    INFO(r.raw_diagnostics);
    CHECK(r.termination==Termination::completed);
    CHECK(r.outcome.value==MathematicalOutcome::optimal);
    REQUIRE(r.primal);
    const auto e=accepted(evaluate_primal(p,*r.primal,{1e-8,1e-8},{{"literal"},"1"}));
    CHECK(e.original_objective==doctest::Approx(value));
    CHECK(check_program_result(r,p,Assurance::numerical).empty());
    CHECK(r.outcome.subject==p.identity());
    CHECK(std::holds_alternative<Unestablished>(r.outcome.support));
    CHECK_FALSE(r.objective.lower); CHECK_FALSE(r.objective.upper);
    REQUIRE(r.residuals.primal); REQUIRE(r.residuals.dual);
    REQUIRE(r.residuals.dual->stationarity); REQUIRE(r.residuals.dual->signs); REQUIRE(r.residuals.dual->complementarity);
    for(const auto* m:{&r.residuals.primal->rows,&r.residuals.primal->variables,&*r.residuals.dual->stationarity,&*r.residuals.dual->signs,&*r.residuals.dual->complementarity})
        CHECK(m->violation<=1e-8+1e-8*m->scale);
}
}
TEST_CASE("registered quadratic interior and boundary optima retain original numerical KKT evidence") {
    for(double upper:{5.0,2.0}) {
        const auto p=accepted(make_convex_program(parabola(upper)));
        auto [worker]=prepare(p).create();
        const auto r=accepted(worker->run(context()));
        optimum(r,p,upper==5?0:1);
        CHECK((*r.primal)[0]==doctest::Approx(upper==5?3:2));
        CHECK(worker->last_attempt()->stamp.program().identity()==p.identity());
        CHECK(worker->last_attempt()->stamp.attempt()==1);
    }
}
TEST_CASE("native norm zero residual and constant norm preserve original rather than squared costs") {
    for(int fixture=0;fixture<3;++fixture) {
        auto input=parabola(fixture==1?5:2);
        input.identity.program={"norm-"+std::to_string(fixture)};
        input.squared_program=ProgramId{"squared-"+std::to_string(fixture)};
        if(fixture==0) input.objective=ResidualNormTerminal{{2,1,{1,0}},{3,-4}};
        if(fixture==1) input.objective=ResidualNormTerminal{{1,1,{1}},{3}};
        if(fixture==2) input.objective=ResidualNormTerminal{{2,1,{0,0}},{3,4}};
        const auto p=accepted(make_convex_program(input)); auto [worker]=prepare(p).create();
        const auto r=accepted(worker->run(context()));
        optimum(r,p,fixture==0?std::sqrt(17.0):(fixture==1?0:5));
        if(fixture==1) CHECK(r.raw_diagnostics.find("checked-componentwise-zero")!=std::string::npos);
    }
}
TEST_CASE("native singular semidefinite minimum returns one point in analytic continuum") {
    const auto p=accepted(make_convex_program({{{"native-convex"},{"singular"}},
        QuadraticTerminal{{2,2,{2,0,0,0}},{-2,0},1},{0,2,{0},{},{}},{{0,2},{0,1}},{},{}}));
    auto [worker]=prepare(p).create(); const auto r=accepted(worker->run(context()));
    optimum(r,p,0); CHECK((*r.primal)[0]==doctest::Approx(1));
    CHECK((*r.primal)[1]>=0); CHECK((*r.primal)[1]<=1);
    CHECK(r.raw_diagnostics.find("model.private_zero_row=true")!=std::string::npos);
    CHECK(r.raw_diagnostics.find("start.default_fallback=false")!=std::string::npos);
}
TEST_CASE("native offdiagonal equality respects half Hessian convention and lower dimensional geometry") {
    const auto p=accepted(make_convex_program({{{"native-convex"},{"equality"}},
        QuadraticTerminal{{2,2,{4,2,2,4}},{-8,-10},17},{1,2,{0,2},{0,1},{1,1}},{{{},{}},{{},{}}},{{2,2}},{}}));
    auto [worker]=prepare(p).create(); const auto r=accepted(worker->run(context()));
    optimum(r,p,4.5); CHECK((*r.primal)[0]==doctest::Approx(.5)); CHECK((*r.primal)[1]==doctest::Approx(1.5));
}
TEST_CASE("controlled feasibility retains tiny row and large finite fixed bound") {
    auto tiny=parabola(); tiny.identity.program={"tiny-row"}; tiny.variables={{{},{}}};
    tiny.constraints={1,1,{0,1},{0},{1e-10}}; tiny.rows={{1e-4,1e-4}};
    const auto p=accepted(make_convex_program(tiny)); auto [worker]=prepare(p).create();
    const auto r=accepted(worker->run(context())); optimum(r,p,999994000009.0);
    CHECK((*r.primal)[0]==doctest::Approx(1e6));
    auto large=parabola(); large.identity.program={"large-bound"}; large.objective=QuadraticTerminal{{1,1,{2}},{0},0}; large.variables={{1e21,1e21}};
    const auto q=accepted(make_convex_program(large)); auto [other]=prepare(q).create();
    const auto big=accepted(other->run(context())); optimum(big,q,1e42);
    CHECK((*big.primal)[0]==1e21);
}
TEST_CASE("native infeasible zero Hessian unbounded and singular curvature unbounded keep unestablished outcomes") {
    auto bad=parabola(); bad.identity.program={"infeasible"}; bad.variables={{{},{}}};
    bad.constraints={2,1,{0,1,2},{0,0},{1,1}}; bad.rows={{{},0},{1,{}}};
    const auto p=accepted(make_convex_program(bad)); auto [worker]=prepare(p).create();
    const auto infeasible=accepted(worker->run(context())); INFO(infeasible.raw_diagnostics);
    CHECK(infeasible.termination==Termination::completed); CHECK(infeasible.outcome.value==MathematicalOutcome::infeasible);
    for(bool curvature:{false,true}) {
        ConvexProgramInput input=curvature?ConvexProgramInput{{{"native-convex"},{"curved-ray"}},
            QuadraticTerminal{{2,2,{2,0,0,0}},{0,-1},0},{0,2,{0},{},{}},{{{},{}},{0,{}}},{},{}}:
            ConvexProgramInput{{{"native-convex"},{"linear-ray"}},LinearTerminal{{-1},0},{0,1,{0},{},{}},{{0,{}}},{},{}};
        const auto q=accepted(make_convex_program(input)); auto [ray]=prepare(q).create(); const auto r=accepted(ray->run(context())); INFO(r.raw_diagnostics);
        CHECK(r.termination==Termination::completed); CHECK(r.outcome.value==MathematicalOutcome::unbounded);
        CHECK(std::holds_alternative<Unestablished>(r.outcome.support)); CHECK_FALSE(r.objective.lower); CHECK_FALSE(r.objective.upper);
    }
}
TEST_CASE("zero variable constants and contradictory constant rows bypass native ModelEmpty") {
    for(int fixture=0;fixture<3;++fixture) {
        ConvexProgramInput input{{{"native-convex"},{"empty-"+std::to_string(fixture)}},LinearTerminal{{},7},
            fixture?SparseMatrix{1,0,{0,0},{},{}}:SparseMatrix{0,0,{},{},{}},{},{},{}};
        if(!fixture) input.constraints.row_offsets={0};
        if(fixture) input.rows={{fixture==1?1.0:0.0,fixture==1?std::optional<double>{}:std::optional<double>{0}}};
        const auto p=accepted(make_convex_program(input)); auto [worker]=prepare(p).create(); const auto r=accepted(worker->run(context()));
        if(fixture==1) { CHECK(r.termination==Termination::completed); CHECK(r.outcome.value==MathematicalOutcome::infeasible); CHECK_FALSE(r.primal); }
        else {optimum(r,p,7);CHECK(r.primal->empty());}
        CHECK(r.raw_diagnostics.find("native_run=false")!=std::string::npos);
    }
}
TEST_CASE("pure registered profile boundary uses linear O(n) inputs without native execution") {
    Registry<ConvexPort> registry; registry.add(accepted(make_highs_registration()));
    Requirements req; req.output.representation={"csl.program-result.v1"};
    for(std::size_t n:{4095,4096,4097,46341}) {
        const auto p=accepted(make_convex_program({{{"profile"},{std::to_string(n)}},LinearTerminal{Vector(n,0),0},
            {0,n,{0},{},{}},std::vector<Interval>(n),{},{}}));
        CHECK(std::holds_alternative<numeric::CsrInput>(p.quadratic_program().hessian().descriptor()));
        auto prepared=prepare_pipeline(select(registry,Method{{"csl.convex.highs"},{}},p,req));
        if(n<=4096) CHECK(std::holds_alternative<PreparedPipeline<ConvexPort>>(prepared));
        else {
            REQUIRE(std::holds_alternative<Rejection>(prepared)); const auto& d=std::get<Rejection>(prepared).diagnostics;
            REQUIRE_FALSE(d.empty()); CHECK(d[0].field=="highs.convex.variables");
            CHECK(d[0].explanation.find("4096")!=std::string::npos);
        }
    }
    // Independent integer derivation, not a returned production capacity.
    const std::uint64_t c4096=2*(std::uint64_t{4096}+1);
    CHECK(c4096==8194); CHECK(c4096*c4096==67141636);
    CHECK(c4096*c4096*8==537133088); CHECK(c4096*c4096*16==1074266176);
    CHECK(2*(std::uint64_t{23169}+1)*2*(std::uint64_t{23169}+1)==2147395600);
    CHECK(2*(std::uint64_t{23170}+1)*2*(std::uint64_t{23170}+1)==2147580964);
}
TEST_CASE("registered unsupported requirements and native coefficient limits reject before execution") {
    Registry<ConvexPort> registry; registry.add(accepted(make_highs_registration()));
    const auto p=accepted(make_convex_program(parabola()));
    for(int fixture=0;fixture<7;++fixture) {
        Requirements req; req.output.representation={"csl.program-result.v1"};
        if(fixture==0) req.scalar=Scalar::binary32;
        if(fixture==1) req.output.assurance=Assurance::validated;
        if(fixture==2) req.basis_diagnostics=true;
        if(fixture==3) req.output.representation={"foreign"};
        if(fixture==4) req.output.relation=SetRelation::equivalent;
        if(fixture==5) req.output.family=FamilyTarget::exact_optimal_relation;
        if(fixture==6) req.output.completeness=Completeness::established;
        CHECK(std::holds_alternative<Rejection>(prepare_pipeline(select(registry,Method{{"csl.convex.highs"},{}},p,req))));
    }
    Requirements req; req.output.representation={"csl.program-result.v1"};
    CHECK(std::holds_alternative<Rejection>(prepare_pipeline(select(registry,Method{{"csl.convex.highs"},"foreign"},p,req))));
    for(bool hessian:{false,true}) {
        auto input=parabola(); input.identity.program={hessian?"tiny-Q":"tiny-A"};
        if(hessian) input.objective=QuadraticTerminal{{1,1,{1e-12}},{0},0};
        else {input.constraints={1,1,{0,1},{0},{1e-12}};input.rows={{{},1}};}
        const auto q=accepted(make_convex_program(input));
        CHECK(std::holds_alternative<Rejection>(prepare_pipeline(select(registry,Method{{"csl.convex.highs"},{}},q,req))));
    }
    CHECK(std::holds_alternative<Diagnostics>(make_highs_registration({std::numeric_limits<std::size_t>::max(),{}})));
    auto [worker]=prepare(p).create(); auto c=context(); c.resources={}; CHECK(std::holds_alternative<Unsupported>(worker->run(c)));
    c=context(); c.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,1024}); CHECK(std::holds_alternative<Unsupported>(worker->run(c)));
    CHECK(worker->last_attempt()->stamp.attempt()==2); CHECK(worker->last_attempt()->state==SolveAttemptState::unsupported);
}
TEST_CASE("actual iteration zero limits and preexecution stops preserve undetermined outcomes") {
    const auto p=accepted(make_convex_program(parabola()));
    auto [worker]=prepare(p,{{},0}).create(); const auto q=accepted(worker->run(context())); INFO(q.raw_diagnostics);
    CHECK(q.termination==Termination::resource_limit); CHECK(q.outcome.value==MathematicalOutcome::undetermined);
    CHECK(q.raw_diagnostics.find("phase.qp.model_status=14")!=std::string::npos);
    auto input=parabola(); input.identity.program={"phase-one-work"}; input.variables={{{},{}}};
    input.constraints={1,1,{0,1},{0},{1}}; input.rows={{4,4}};
    const auto p1=accepted(make_convex_program(input)); auto [phase]=prepare(p1,{0,{}}).create(); const auto stopped=accepted(phase->run(context())); INFO(stopped.raw_diagnostics);
    CHECK(stopped.termination==Termination::resource_limit); CHECK(stopped.outcome.value==MathematicalOutcome::undetermined);
    CHECK(stopped.raw_diagnostics.find("phase.feasibility.model_status=14")!=std::string::npos);
    auto [reuse]=prepare(p).create(); optimum(accepted(reuse->run(context())),p,0);
    std::stop_source stop; stop.request_stop(); auto c=context(); c.cancellation=stop.get_token();
    const auto cancelled=accepted(reuse->run(c)); CHECK(cancelled.termination==Termination::cancelled); CHECK_FALSE(cancelled.primal);
    CHECK(cancelled.raw_diagnostics.find("native_run=false")!=std::string::npos);
    c=context(); c.deadline=std::chrono::steady_clock::time_point::min();
    const auto expired=accepted(reuse->run(c)); CHECK(expired.termination==Termination::resource_limit); CHECK_FALSE(expired.primal);
    optimum(accepted(reuse->run(context())),p,0); CHECK(reuse->last_attempt()->stamp.attempt()==4);
}
TEST_CASE("independent concurrent native workspaces retain history after owners disappear") {
    const auto p=accepted(make_convex_program(parabola())); auto plan=prepare(p);
    auto [left]=plan.create(); auto [right]=plan.create(); CHECK(left->workspace_identity()!=right->workspace_identity());
    auto c=context(); c.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{2,2,1,{}});
    std::barrier start(2);
    auto first=std::async(std::launch::async,[&] {start.arrive_and_wait();return accepted(left->run(c));});
    std::future<ProgramResult> second;
    try {second=std::async(std::launch::async,[&] {start.arrive_and_wait();return accepted(right->run(c));});}
    catch(...) {start.arrive_and_drop();throw;}
    optimum(first.get(),p,0); optimum(second.get(),p,0);
    const auto history=*left->last_attempt(); left.reset(); right.reset();
    CHECK(history.stamp.program().identity()==p.identity()); CHECK(history.stamp.program().quadratic_program().hessian()(0,0)==2);
}
TEST_CASE("a finite current native point survives original objective overflow without optimality claim") {
    auto input=parabola();input.identity.program={"overflowing-cost"};input.objective=QuadraticTerminal{{1,1,{2}},{0},0};input.variables={{1e160,1e160}};
    const auto p=accepted(make_convex_program(input));auto [worker]=prepare(p).create();
    const auto r=accepted(worker->run(context()));INFO(r.raw_diagnostics);
    CHECK(r.termination==Termination::numerical_failure);CHECK(r.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(r.primal);CHECK((*r.primal)[0]==1e160);CHECK_FALSE(r.objective.lower);CHECK_FALSE(r.objective.upper);
}
