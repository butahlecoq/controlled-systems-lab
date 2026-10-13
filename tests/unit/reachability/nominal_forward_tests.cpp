#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/reachability/nominal_forward.hpp>
#include <stop_token>
using namespace csl;
using namespace csl::registry;
using namespace csl::reachability;
namespace {
template<class T,class... E> T take(std::variant<T,E...> value) {
    REQUIRE(std::holds_alternative<T>(value)); return std::get<T>(std::move(value));
}
template<class T,class V> T alternative(V value) {
    REQUIRE(std::holds_alternative<T>(value)); return std::get<T>(std::move(value));
}
SetHandle interval(std::string id,double lo,double hi,std::string label="x") {
    return take(sets::make_h({{std::move(id)},1,{std::move(label)}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),take(numeric::snapshot_vector(Vector{hi,-lo})),
         take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))})).as_handle();
}
PreparedProvider<GeometryPort> provider(std::optional<std::size_t> limit={}) {
    Registry<GeometryPort> r; auto entry=geometry::polyhedral::make_projection_registration({geometry::polyhedral::ProjectionOutput::h,limit});
    Method method{entry.identity.id,entry.identity.version}; REQUIRE_FALSE(r.add(std::move(entry)).has_value());
    Requirements req;req.output.representation={"csl.polyhedron.h"};req.output.relation=SetRelation::equivalent;
    return take(prepare_provider(select_provider(r,method,req)));
}
class CancelAfterFeasibility final : public SetOperatorWorkspace {
    std::unique_ptr<SetOperatorWorkspace> inner_;
    std::stop_source stop_;
public:
    CancelAfterFeasibility(std::unique_ptr<SetOperatorWorkspace> inner,std::stop_source stop)
        :inner_(std::move(inner)),stop_(std::move(stop)) {}
    OperationOutcome apply(const OperationRequest& request,const ExecutionContext& context) override {
        auto result=inner_->apply(request,context);
        if(request.identity.request.value.ends_with("2/feasibility"))stop_.request_stop();
        return result;
    }
};
PreparedProvider<GeometryPort> cancelling_provider(std::stop_source stop) {
    auto entry=geometry::polyhedral::make_projection_registration();auto factory=entry.factory;
    entry.factory=[factory,stop](const OperationRequest& request) {
        return std::make_unique<CancelAfterFeasibility>(factory(request),stop);
    };
    Registry<GeometryPort> registry;Method method{entry.identity.id,entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());Requirements req;
    req.output.representation={"csl.polyhedron.h"};req.output.relation=SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry,method,req)));
}
Problem integrator() {
    return {{"integrator"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{}}),{0,1,2},KnownInitial{{0}},
        ContinuousDomain{{interval("u0",0,1,"u"),interval("u1",0,1,"u")}},
        {interval("X0",0,0),interval("X1",0,1),interval("X2",0,2)}, {},{},InformationPattern::nominal_open_loop,
        QuadraticTerminal{{1,1,{2}},{-2},1}};
}
problem::ResolvedProblem resolved(Problem p) {return take(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));}
NominalForwardOutcome run(Problem p,ExecutionContext context={}) {return nominal_forward(resolved(std::move(p)),{"tube"},provider(),context);}
bool contains(const SetHandle& set,double x) {
    const auto data=take(sets::from_handle(set));const auto rep=data.representation();
    if(std::holds_alternative<sets::EmptyRepresentation>(rep))return false;
    const auto& h=std::get<sets::HRepresentation>(rep);
    for(std::size_t r=0;r<h.inequalities.rows();++r)if(h.inequalities(r,0)*x>h.upper_bounds[r])return false;
    for(std::size_t r=0;r<h.equalities.rows();++r)if(h.equalities(r,0)*x!=h.equality_values[r])return false;
    return true;
}
void range(const SetHandle& set,double lo,double hi) {
    CHECK(contains(set,lo));CHECK(contains(set,(lo+hi)/2));CHECK(contains(set,hi));
    CHECK_FALSE(contains(set,lo-0.125));CHECK_FALSE(contains(set,hi+0.125));
}
}
TEST_CASE("two step integrator returns literal reachable marginals and recovery factors") {
    auto p=resolved(integrator());auto result=nominal_forward(p,{"tube"},provider(),{});
    REQUIRE(std::holds_alternative<ForwardTube>(result)); const auto& tube=std::get<ForwardTube>(result);
    REQUIRE(tube.stages.size()==3);CHECK(tube.problem==p.identity());
    range(tube.stages[0].marginal.output,0,0);range(tube.stages[1].marginal.output,0,1);range(tube.stages[2].marginal.output,0,2);
    CHECK(tube.stages[2].state_coordinates==std::vector<std::size_t>{0});
    CHECK(tube.stages[2].control_coordinates==std::vector<std::size_t>{1});
    CHECK(tube.stages[2].next_coordinates==std::vector<std::size_t>{2});
    CHECK(tube.stages[2].source_factors[0]==tube.stages[1].marginal.output.id);
    CHECK(take(sets::from_handle(tube.stages[2].marginal.output)).metadata()->coordinate_labels==std::vector<std::string>{"x"});
    CHECK(tube.stages[2].marginal.relation==SetRelation::equivalent);
    CHECK(std::holds_alternative<Unestablished>(tube.stages[2].marginal.evidence.support));
    CHECK(tube.stages[2].providers[0].actual_module==std::optional<ModuleId>{{"csl.geometry.polyhedral-projection"}});
}
TEST_CASE("LTV uses authored stage order offset and next constraints") {
    auto p=integrator();p.initial=KnownInitial{{1}};p.states={interval("X0",0,2),interval("X1",3,4),interval("X2",-5,-4)};
    p.model=std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,std::vector<LinearStage>{
        {{1,1,{2}},{1,1,{1}},{1,0,{}},{1}},{{1,1,{-1}},{1,1,{2}},{1,0,{}},{-2}}}}, {}});
    auto tube=take<ForwardTube>(run(p));range(tube.stages[0].marginal.output,1,1);
    range(tube.stages[1].marginal.output,3,4);range(tube.stages[2].marginal.output,-5,-4);
}
TEST_CASE("initial constraints can empty stage zero with scoped evidence") {
    auto p=integrator();p.states[0]=interval("X0",1,2);auto result=alternative<EmptyForwardStage>(run(p));
    CHECK(result.stage.value==0);REQUIRE(result.prefix.stages.size()==1);
    CHECK(result.evidence.reference.identity.problem==result.prefix.problem);
}
TEST_CASE("incompatible final constraint returns explicit empty stage and completed prefix") {
    auto p=integrator();p.states[2]=interval("X2",3,4);auto result=alternative<EmptyForwardStage>(run(p));
    CHECK(result.stage.value==2);REQUIRE(result.prefix.stages.size()==3);range(result.prefix.stages[1].marginal.output,0,1);
}
TEST_CASE("cancellation and deadline are typed stops without success stages") {
    std::stop_source stop;stop.request_stop();ExecutionContext context;context.cancellation=stop.get_token();
    auto result=alternative<ForwardFailure>(run(integrator(),context));CHECK(result.prefix.stages.empty());
    CHECK(std::get<OperationStopped>(result.cause).reason==StopReason::cancelled);
    context={};context.deadline=std::chrono::steady_clock::now();result=alternative<ForwardFailure>(run(integrator(),context));
    CHECK(std::get<OperationStopped>(result.cause).reason==StopReason::deadline_expired);
}
TEST_CASE("declared temporal coupling is rejected before propagation") {
    auto p=integrator();p.temporal=TemporalConstraints{{1,5,{0,1},{0},{1}},{{0,0}}};
    auto result=alternative<ForwardFailure>(run(p));CHECK(result.prefix.stages.empty());
    CHECK(std::get<Unsupported>(result.cause).diagnostics[0].field=="forward.temporal");
}
TEST_CASE("stop after final feasibility preserves completed child evidence without publishing a stage") {
    auto p=resolved(integrator());std::stop_source stop;ExecutionContext context;context.cancellation=stop.get_token();
    auto result=alternative<ForwardFailure>(nominal_forward(p,{"tube"},cancelling_provider(stop),context));
    CHECK(std::get<OperationStopped>(result.cause).reason==StopReason::cancelled);
    CHECK(result.stage.value==2);CHECK(result.prefix.stages.size()==2);CHECK(result.completed_lineage.size()==2);
    REQUIRE(result.active_request);CHECK(result.active_request->identity.request.value.ends_with("2/feasibility"));
}
