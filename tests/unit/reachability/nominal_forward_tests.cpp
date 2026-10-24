#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/reachability/nominal_forward.hpp>
#include <csl/execution/timing_collector.hpp>
#include <csl/execution/instrumented_operation.hpp>
#include <algorithm>
#include <csl/geometry/affine_sum.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <array>
#include <limits>
#include <iostream>
#include <stop_token>
#include <type_traits>
using namespace csl;
using namespace csl::registry;
using namespace csl::reachability;
static_assert(std::is_aggregate_v<ForwardFailure>);
namespace {
template<class V> void explain(const V& value) {
    std::visit([](const auto& item) {
        if constexpr(requires {item.explanation;})std::cerr<<item.field<<": "<<item.explanation<<'\n';
        if constexpr(requires {item.diagnostics.begin()->field;})for(const auto& d:item.diagnostics)std::cerr<<d.field<<": "<<d.explanation<<'\n';
        if constexpr(requires {item.cause;})std::visit([](const auto& cause) {
            if constexpr(requires {cause.diagnostics.begin()->field;})for(const auto& d:cause.diagnostics)std::cerr<<d.field<<": "<<d.explanation<<'\n';
        },item.cause);
    },value);
}
template<class T,class... E> T take(std::variant<T,E...> value) {
    if(!std::holds_alternative<T>(value))explain(value);
    REQUIRE(std::holds_alternative<T>(value)); return std::get<T>(std::move(value));
}
template<class T,class V> T alternative(V value) {
    if(!std::holds_alternative<T>(value))explain(value);
    REQUIRE(std::holds_alternative<T>(value)); return std::get<T>(std::move(value));
}
SetHandle interval(std::string id,double lo,double hi,std::string label="x") {
    return take(sets::make_h({{std::move(id)},1,label.empty()?std::vector<std::string>{}:std::vector<std::string>{std::move(label)}},
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
template<class Port> PreparedProvider<Port> selected(Registration<Port> entry,std::string representation) {
    Registry<Port> registry;Method method{entry.identity.id,entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());Requirements req;
    req.output.representation={std::move(representation)};
    if constexpr(std::is_same_v<Port,GeometryPort> || std::is_same_v<Port,ConversionPort>)req.output.relation=SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry,method,req)));
}
ForwardDependencies dependencies(PreparedProvider<GeometryPort> projection=provider(),bool reject_affine=false) {
    auto lp=take(adapters::lp::make_highs_registration());
    auto converter=take(adapters::polyhedral::make_qhull_registration(lp));
    auto affine=geometry::make_affine_sum_registration({selected(geometry::make_lp_hull_reducer_registration(),""),
        selected(lp,"csl.program-result.v1"),selected(converter,"csl.polyhedron.v")},{ {},{}});
    if(reject_affine)affine.capabilities=[](const OperationRequest&,const Requirements&) -> Capability {
        return Diagnostics{{DiagnosticCode::unsupported,"selected.affine","Selected affine provider rejects this operation."}};
    };
    return {std::move(projection),selected(std::move(affine),"csl.polyhedron.v"),selected(converter,"csl.polyhedron.h")};
}
Problem integrator() {
    return {{"integrator"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{}}),{0,1,2},KnownInitial{{0}},
        ContinuousDomain{{interval("u0",0,1,"u"),interval("u1",0,1,"u")}},
        {interval("X0",0,0),interval("X1",0,1),interval("X2",0,2)}, {},{},InformationPattern::nominal_open_loop,
        QuadraticTerminal{{1,1,{2}},{-2},1}};
}
problem::ResolvedProblem resolved(Problem p) {return take(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));}
NominalForwardOutcome run(Problem p,ExecutionContext context={}) {return nominal_forward(resolved(std::move(p)),{"tube"},dependencies(),context);}
class TimingClock final : public execution::observability::TimingClock {
    std::int64_t tick_{};
public:
    artifacts::ClockDomain wall_domain() const override {
        return {{"wall"},artifacts::ClockMetric::steady_wall,"run",1,1000,
            artifacts::Available<std::uint64_t>{1},"nominal-forward-test"};
    }
    std::optional<artifacts::ClockDomain> cpu_domain() const override {return {};}
    artifacts::Metric<std::int64_t> wall_now() noexcept override {
        const auto result=tick_;tick_+=10;return artifacts::Available<std::int64_t>{result};
    }
    artifacts::Metric<std::int64_t> cpu_now() noexcept override {
        return artifacts::Unavailable{artifacts::MissingReason::not_supported,{}};
    }
};
void range(const SetHandle& set,double lo,double hi,std::vector<std::string> expected_labels={"x"}) {
    // Complete independent 1-D H oracle: every halfspace contributes an
    // endpoint, every nonzero equality fixes both endpoints. No sampled points
    // can hide an omitted cut or a small endpoint error.
    const auto data=take(sets::from_handle(set));const auto rep=data.representation();
    CHECK(data.metadata()->coordinate_labels==expected_labels);
    const auto& h=std::get<sets::HRepresentation>(rep);
    double lower=-std::numeric_limits<double>::infinity(),upper=std::numeric_limits<double>::infinity();
    bool feasible=true;
    for(std::size_t r=0;r<h.inequalities.rows();++r) {
        const auto a=h.inequalities(r,0),b=h.upper_bounds[r];
        if(a>0)upper=std::min(upper,b/a);else if(a<0)lower=std::max(lower,b/a);else if(b<0)feasible=false;
    }
    for(std::size_t r=0;r<h.equalities.rows();++r) {
        const auto a=h.equalities(r,0),b=h.equality_values[r];
        if(a!=0){lower=std::max(lower,b/a);upper=std::min(upper,b/a);}else if(b!=0)feasible=false;
    }
    CHECK(feasible);CHECK(lower==lo);CHECK(upper==hi);
}
bool contains_h(const SetHandle& set,const Vector& point) {
    const auto data=take(sets::from_handle(set));
    const auto representation=data.representation();
    if(std::holds_alternative<sets::EmptyRepresentation>(representation))return false;
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    REQUIRE(h);
    for(std::size_t row=0;row<h->inequalities.rows();++row) {
        double value=0;
        for(std::size_t column=0;column<point.size();++column)value+=h->inequalities(row,column)*point[column];
        if(value>h->upper_bounds[row])return false;
    }
    for(std::size_t row=0;row<h->equalities.rows();++row) {
        double value=0;
        for(std::size_t column=0;column<point.size();++column)value+=h->equalities(row,column)*point[column];
        if(value!=h->equality_values[row])return false;
    }
    return true;
}
}
TEST_CASE("nominal forward records the matching projection provider span") {
    namespace ar=artifacts;
    namespace ob=execution::observability;
    auto p=resolved(integrator());
    auto selected_dependencies=dependencies();
    const auto backend=*selected_dependencies.projection.provenance().actual;
    const auto problem_id=p.identity().value;
    const std::string task="nominal-forward/"+std::to_string(problem_id.size())+":"+
        problem_id+"4:tube0/project";
    ar::ConfigurationInput configuration;
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    configuration.collection={true,ar::CollectionMode::detail,8,4096,8,1024};
    configuration.modules={{"geometry",{{backend.id},backend.version,missing},{}},
        {"strategy",{{"csl.reachability.nominal-forward"},"0.1.0",missing},{}}};
    configuration.resources={1,1,1,{}};configuration.numerical={0,0};
    configuration.output={ar::OutputKind::program,Assurance::numerical,
        FamilyTarget::candidate_relaxation,{"csl.polyhedron.h"},{1,0,{},{}}};
    configuration.selector={{"first"},"1",{}};
    configuration.strategy={ModuleId{"csl.reachability.nominal-forward"},ModuleId{},ModuleId{},ModuleId{},
        backend.id,ModuleId{},ModuleId{},ModuleId{"first"},RepresentationId{"csl.polyhedron.h"}};
    auto resolved_configuration=take(ar::resolve_configuration(std::move(configuration)));
    const auto clock_domain=ar::ClockDomain{{"wall"},ar::ClockMetric::steady_wall,"run",1,1000,
        ar::Available<std::uint64_t>{1},"nominal-forward-test"};
    ob::PlanInput plan_input{p,resolved_configuration,{"instrumented-forward"},{clock_domain},{},1};
    plan_input.tasks={"run",task};plan_input.operations={"operation.run","geometry.projection"};
    ar::SpanDescriptor root{};root.id={0};root.task="run";root.operation="operation.run";
    root.module=resolved_configuration.description().modules.back().implementation;
    root.clock={"wall"};root.requested_assurance=Assurance::numerical;
    root.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
    ar::SpanDescriptor projection{};projection.id={1};projection.parent=ar::SpanParent{{0},ar::ParentKind::nested};
    projection.task=task;projection.operation="geometry.projection";
    projection.module=root.module;
    projection.backend=std::make_shared<const ar::ModuleIdentity>(
        ar::ModuleIdentity{backend.id,backend.version,missing});
    projection.clock={"wall"};projection.stage=0;
    projection.requested_assurance=Assurance::numerical;
    projection.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
    projection.observation_source="src/reachability/nominal_forward.cpp";
    plan_input.spans={std::move(root),std::move(projection)};
    auto plan=take(ob::make_collection_plan(std::move(plan_input)));
    auto probe_timer=take(ob::make_timing_collector(plan,std::make_shared<TimingClock>(),{0},{{1}}));
    ExecutionContext probe_context;probe_context.run_id="instrumented-forward";probe_context.timing=probe_timer;
    auto probe=ob::start_operation_timing(probe_context,{task,"geometry.projection",
        {ModuleId{"csl.reachability.nominal-forward"},"0.1.0",missing},
        ar::ModuleIdentity{backend.id,backend.version,missing},{},0,{}});
    REQUIRE(probe);
    probe->close_not_called(ar::NotCalledReason::task_not_admitted);
    auto timer=take(ob::make_timing_collector(plan,std::make_shared<TimingClock>(),{0},{{1}}));
    ExecutionContext context;context.run_id="instrumented-forward";context.timing=timer;
    auto root_scope=take(timer->start({0},context));
    const auto result=nominal_forward(p,{"tube"},selected_dependencies,context);
    REQUIRE(std::holds_alternative<ForwardTube>(result));
    root_scope.close(Termination::completed);
    const auto report=take(timer->snapshot());
    REQUIRE(report.spans.size()==2);
    REQUIRE(std::holds_alternative<ar::Available<std::uint64_t>>(report.spans[1].inclusive_wall_ticks));
    CHECK(std::get<ar::Available<std::uint64_t>>(report.spans[1].inclusive_wall_ticks).value==10);
    CHECK(std::holds_alternative<ar::ReturnedObservation>(report.observations.description().spans[1].execution));
    REQUIRE(std::holds_alternative<ar::ReturnedSpan>(report.observations.description().spans[1].status));
    CHECK(std::get<ar::ReturnedSpan>(report.observations.description().spans[1].status).termination==Termination::completed);
}
TEST_CASE("two step integrator returns literal reachable marginals and recovery factors") {
    auto p=resolved(integrator());auto result=nominal_forward(p,{"tube"},dependencies(),{});
    if(!std::holds_alternative<ForwardTube>(result))explain(result);
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
    CHECK(std::holds_alternative<Unestablished>(tube.stages[2].recovery_evidence.support));
    CHECK(tube.stages[2].providers[0].actual_module==std::optional<ModuleId>{{"csl.geometry.affine-sum"}});
    CHECK(tube.stages[2].providers.back().actual_module==std::optional<ModuleId>{{"csl.geometry.polyhedral-projection"}});
    REQUIRE(tube.stages[2].operation_lineage.size()==6);
    REQUIRE(tube.stages[2].coordinate_lineage.size()==3);
    const auto& maps=tube.stages[2].coordinate_lineage;
    CHECK(maps[0].source.id==tube.stages[1].marginal.output.id);
    CHECK(maps[0].coordinates==std::vector<std::size_t>{0});
    CHECK(take(sets::from_handle(maps[0].source)).metadata()->coordinate_labels==std::vector<std::string>{"x"});
    CHECK(take(sets::from_handle(maps[0].target)).metadata()->coordinate_labels.empty());
    CHECK(maps[1].source.id==SetId{"u1"});
    CHECK(take(sets::from_handle(maps[1].source)).metadata()->coordinate_labels==std::vector<std::string>{"u"});
    CHECK(maps[1].coordinates==std::vector<std::size_t>{0});
    CHECK(tube.stages[2].operation_lineage[0].reference.inputs==std::vector<SetId>{maps[0].target.id});
    CHECK(tube.stages[2].operation_lineage[1].reference.inputs==std::vector<SetId>{maps[1].target.id});
    CHECK(maps[2].coordinates==std::vector<std::size_t>{0});
    CHECK(take(sets::from_handle(maps[2].source)).metadata()->coordinate_labels.empty());
    CHECK(take(sets::from_handle(maps[2].target)).metadata()->coordinate_labels==std::vector<std::string>{"x"});
    range(maps[0].source,0,1);range(maps[0].target,0,1,{});
    range(maps[1].source,0,1,{"u"});range(maps[1].target,0,1,{});
    range(maps[2].source,0,2,{});range(maps[2].target,0,2);
    CHECK(tube.stages[2].operation_lineage[0].reference.identity.request.value.ends_with("2/affine-state"));
}
TEST_CASE("clipped T-S01 chain retains literal marginals and stage shape counts") {
    auto problem=integrator();
    problem.states[1]=interval("X1-clipped",0,0.5);
    const auto resolved_problem=resolved(std::move(problem));
    const auto outcome=nominal_forward(resolved_problem,{"clipped-tube"},dependencies(),{});
    if(!std::holds_alternative<ForwardTube>(outcome))explain(outcome);
    REQUIRE(std::holds_alternative<ForwardTube>(outcome));
    const auto& tube=std::get<ForwardTube>(outcome);
    REQUIRE(tube.stages.size()==3);
    range(tube.stages[0].marginal.output,0,0);
    range(tube.stages[1].marginal.output,0,0.5);
    range(tube.stages[2].marginal.output,0,1.5);

    const auto shape=[](const SetHandle& set) {
        const auto data=take(sets::from_handle(set));
        const auto representation=data.representation();
        const auto* h=std::get_if<sets::HRepresentation>(&representation);
        REQUIRE(h);
        return std::array<std::size_t,5>{data.metadata()->set.dimension,
            h->inequalities.rows(),h->equalities.rows(),
            h->inequalities.rows()*h->inequalities.cols(),
            h->equalities.rows()*h->equalities.cols()};
    };
    using Shape=std::array<std::size_t,5>;
    const Shape stage1_joint{3,6,2,18,6},stage1_propagation{1,4,0,4,0},
        stage1_marginal{1,4,0,4,0},stage2_joint{3,8,1,24,3},
        stage2_propagation{1,4,0,4,0},stage2_marginal{1,4,0,4,0};
    CHECK(shape(tube.stages[1].joint_factor)==stage1_joint);
    CHECK(shape(tube.stages[1].propagation_factor)==stage1_propagation);
    CHECK(shape(tube.stages[1].marginal.output)==stage1_marginal);
    CHECK(shape(tube.stages[2].joint_factor)==stage2_joint);
    CHECK(shape(tube.stages[2].propagation_factor)==stage2_propagation);
    CHECK(shape(tube.stages[2].marginal.output)==stage2_marginal);
    CHECK(tube.stages[2].operation_lineage.size()==6);
}
TEST_CASE("a terminal singleton does not claim a complete trajectory history") {
    auto p=integrator();
    p.states[2]=interval("X2-terminal",1,1);
    const auto tube=take<ForwardTube>(run(std::move(p)));
    REQUIRE(tube.stages.size()==3);
    range(tube.stages[2].marginal.output,1,1);

    // The same terminal state has at least two distinct valid control histories.
    CHECK(contains_h(tube.stages[1].joint_factor,{0,0,0}));
    CHECK(contains_h(tube.stages[2].joint_factor,{0,1,1}));
    CHECK(contains_h(tube.stages[1].joint_factor,{0,1,1}));
    CHECK(contains_h(tube.stages[2].joint_factor,{1,0,1}));

    for(std::size_t stage=1;stage<tube.stages.size();++stage) {
        const auto& result=tube.stages[stage].marginal;
        CHECK(result.relation==SetRelation::equivalent);
        CHECK(result.evidence.scope==GeometryClaimScope::set_relation);
        CHECK(std::holds_alternative<Unestablished>(result.evidence.support));
        CHECK(std::find(result.evidence.assumptions.begin(),result.evidence.assumptions.end(),
            "stage marginal only; no optimality or joint-history completeness claim")!=result.evidence.assumptions.end());
        CHECK(tube.stages[stage].recovery_evidence.scope==GeometryClaimScope::set_relation);
        CHECK(std::holds_alternative<Unestablished>(tube.stages[stage].recovery_evidence.support));
        CHECK(tube.stages[stage].recovery_evidence.assumptions.back()==
            "compiled [x,u,y] authored transition rows retained for future recovery; no provider or validated recovery theorem asserted");
        REQUIRE(tube.stages[stage].operation_lineage.size()==tube.stages[stage].providers.size());
        for(std::size_t operation=0;operation<tube.stages[stage].operation_lineage.size();++operation) {
            const auto& evidence=tube.stages[stage].operation_lineage[operation];
            CHECK(evidence.scope==GeometryClaimScope::set_relation);
            CHECK(tube.stages[stage].providers[operation].request==evidence.reference.identity.request);
        }
    }
}
TEST_CASE("LTV uses authored stage order offset and next constraints") {
    auto p=integrator();p.initial=KnownInitial{{1}};p.states={interval("X0",0,2),interval("X1",3,4),interval("X2",-5,-4)};
    p.model=std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,std::vector<LinearStage>{
        {{1,1,{2}},{1,1,{1}},{1,0,{}},{1}},{{1,1,{-1}},{1,1,{2}},{1,0,{}},{-2}}}}, {}});
    auto tube=take<ForwardTube>(run(p));range(tube.stages[0].marginal.output,1,1);
    range(tube.stages[1].marginal.output,3,4);range(tube.stages[2].marginal.output,-5,-4);
    REQUIRE(tube.stages[2].coordinate_lineage.size()==3);
    range(tube.stages[2].coordinate_lineage[2].source,-6,-3,{});
    range(tube.stages[2].coordinate_lineage[2].target,-6,-3);
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
    auto result=alternative<ForwardFailure>(run(integrator(),context));CHECK(result.prefix.stages.empty());CHECK_FALSE(result.partial_relation);
    CHECK(std::get<OperationStopped>(result.cause).reason==StopReason::cancelled);
    context={};context.deadline=std::chrono::steady_clock::now();result=alternative<ForwardFailure>(run(integrator(),context));
    CHECK(std::get<OperationStopped>(result.cause).reason==StopReason::deadline_expired);CHECK_FALSE(result.partial_relation);
}
TEST_CASE("declared temporal coupling is rejected before propagation") {
    auto p=integrator();p.temporal=TemporalConstraints{{1,5,{0,1},{0},{1}},{{0,0}}};
    auto result=alternative<ForwardFailure>(run(p));CHECK(result.prefix.stages.empty());
    CHECK(std::get<Unsupported>(result.cause).diagnostics[0].field=="forward.temporal");
}
TEST_CASE("stop after final feasibility preserves completed child evidence without publishing a stage") {
    auto p=resolved(integrator());std::stop_source stop;ExecutionContext context;context.cancellation=stop.get_token();
    auto result=alternative<ForwardFailure>(nominal_forward(p,{"tube"},dependencies(cancelling_provider(stop)),context));
    CHECK(std::get<OperationStopped>(result.cause).reason==StopReason::cancelled);
    CHECK(result.stage.value==2);CHECK(result.prefix.stages.size()==2);CHECK(result.completed_lineage.size()==6);
    REQUIRE(result.partial_relation);
    CHECK(result.partial_relation->stage.value==2);
    CHECK(result.partial_relation->source_coordinates==std::vector<std::size_t>{0});
    CHECK(result.partial_relation->projection_source.metadata.dimension==1);
    range(result.partial_relation->marginal.output,0,2);
    CHECK(result.partial_relation->marginal.relation==SetRelation::equivalent);
    CHECK(result.partial_relation->marginal.evidence.scope==GeometryClaimScope::set_relation);
    CHECK(std::holds_alternative<Unestablished>(result.partial_relation->marginal.evidence.support));
    CHECK(result.partial_relation->marginal.evidence.reference.identity.problem==p.identity());
    CHECK(result.partial_relation->marginal.evidence.reference.identity.request.value.ends_with("2/stage"));
    REQUIRE(result.active_request);CHECK(result.active_request->identity.request.value.ends_with("2/feasibility"));
}
TEST_CASE("selected affine provider rejection is retained with stage scope") {
    auto p=resolved(integrator());auto result=alternative<ForwardFailure>(nominal_forward(p,{"tube"},dependencies(provider(),true),{}));
    CHECK(result.stage.value==1);REQUIRE(result.prefix.stages.size()==1);
    CHECK(std::get<Unsupported>(result.cause).diagnostics[0].field=="selected.affine");
    REQUIRE(result.active_request);CHECK(result.active_request->identity.request.value.ends_with("1/affine-state"));
}
