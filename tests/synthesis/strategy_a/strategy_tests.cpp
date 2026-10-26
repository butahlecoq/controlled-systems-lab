#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_a/nominal_linear_exact_profile.hpp>
#include <csl/contracts.hpp>
#include <csl/synthesis/ts02_constant_integrator.hpp>
#include <csl/synthesis/ts03_singular_integrator.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/execution/timing_collector.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/problem/temporal_lifts.hpp>
#include "../../../src/registry/compiled_verifiers.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <numeric>

using namespace csl;
using namespace csl::registry;
namespace {
namespace ar = csl::artifacts;
namespace ob = csl::execution::observability;
template<class T,class... E> T take(std::variant<T,E...> value) {
    if(!std::holds_alternative<T>(value))std::visit([](const auto& item) {
        if constexpr(requires {item.diagnostics.begin()->field;})
            for(const auto& d:item.diagnostics)std::cerr<<d.field<<": "<<d.explanation<<'\n';
    },value);
    REQUIRE(std::holds_alternative<T>(value));return std::get<T>(std::move(value));
}
template<class T,class V> T alternative(V value) {
    REQUIRE(std::holds_alternative<T>(value));return std::get<T>(std::move(value));
}
SetHandle interval(std::string id,double lo,double hi,std::string label="x") {
    return take(sets::make_h({{std::move(id)},1,{std::move(label)}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),take(numeric::snapshot_vector(Vector{hi,-lo})),
         take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))})).as_handle();
}
template<class Port> PreparedProvider<Port> selected(Registration<Port> entry,std::string representation) {
    Registry<Port> registry;Method method{entry.identity.id,entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());Requirements requirements;
    requirements.output.representation={std::move(representation)};
    if constexpr(std::is_same_v<Port,GeometryPort> || std::is_same_v<Port,ConversionPort>)
        requirements.output.relation=SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry,method,requirements)));
}
problem::ResolvedProblem integrator(bool constant=false,bool singular=false) {
    QuadraticTerminal objective{};
    objective.Q={1,1,{2}};
    objective.linear={-2};
    objective.offset=1;
    Problem source{{"strategy-a-integrator"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{singular?0.0:1.0}},
            {1,1,{1}},{1,0,{}},{0}}}, {}}),{0,1,2},KnownInitial{{0}},
        ContinuousDomain{{interval("u0",0,1,"u"),interval("u1",0,1,"u")}},
        {interval("X0",0,0),interval("X1",0,1),interval("X2",0,2)}, {},{},
        InformationPattern::nominal_open_loop,std::move(objective)};
    if(constant)source.objective=LinearTerminal{{0},7};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
problem::ResolvedProblem exact_integrator() {
    QuadraticTerminal objective{}; objective.Q={1,1,{2}}; objective.linear={-2}; objective.offset=1;
    Problem source{{"strategy-a-ts01"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}}, {}}),
        {0,1,2},KnownInitial{{0}},ContinuousDomain{{interval("u0",0,1,"u"),interval("u1",0,1,"u")}},
        {UniversalSet{1},UniversalSet{1},UniversalSet{1}}, {},{},InformationPattern::nominal_open_loop,
        std::move(objective)};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
problem::ResolvedProblem exact_ts02_integrator(TerminalObjective objective=LinearTerminal{{0},3},double a=1) {
    Problem source{{"strategy-a-ts02"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{a}},{1,1,{1}},{1,0,{}},{0}}}, {}}),
        {0,1,2},KnownInitial{{0}},ContinuousDomain{{interval("u0",0,1,"u"),interval("u1",0,1,"u")}},
        {UniversalSet{1},UniversalSet{1},UniversalSet{1}}, {},{},InformationPattern::nominal_open_loop,
        std::move(objective)};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
problem::ResolvedProblem exact_ts03_integrator() {
    QuadraticTerminal objective{};objective.Q={1,1,{2}};objective.linear={-2};objective.offset=1;
    return exact_ts02_integrator(TerminalObjective{std::move(objective)},0);
}
problem::ResolvedProblem nominal_linear_exact_integrator(bool constant=false) {
    Problem source{{"strategy-a-nominal-linear-exact"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}}, {}}),
        {0,1,2},KnownInitial{{0}},ContinuousDomain{{interval("nominal-exact-u0",0,1,"u"),
        interval("nominal-exact-u1",0,1,"u")}},
        {interval("nominal-exact-x0",0,0),interval("nominal-exact-x1",0,1),
         interval("nominal-exact-x2",1,2)}, {},{},InformationPattern::nominal_open_loop,
        constant ? TerminalObjective{LinearTerminal{{0},3}} : TerminalObjective{LinearTerminal{{1},0}}};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
SetHandle unit_box_2d(std::string id, std::string first, std::string second) {
    return take(sets::make_h({{std::move(id)},2,{std::move(first),std::move(second)}},
        {take(numeric::snapshot(Matrix{4,2,{1,0,-1,0,0,1,0,-1}})),
         take(numeric::snapshot_vector(Vector{1,0,1,0})),
         take(numeric::snapshot(Matrix{0,2,{}})),
         take(numeric::snapshot_vector(Vector{}))})).as_handle();
}
problem::ResolvedProblem nominal_linear_exact_multivariable() {
    const auto box = unit_box_2d("nominal-exact-box", "p", "v");
    Problem source{{"strategy-a-nominal-linear-exact-multivariable"},
        std::make_shared<const SystemModel>(SystemModel{{
            {2,2,0},TimeDomain::discrete,
            LinearStage{{2,2,{0,0,0,0}},{2,2,{1,0,0,1}},{2,0,{}},{0,0}}}, {}}),
        {0,1,2},KnownInitial{{0,0}},
        ContinuousDomain{{box,box}},
        {unit_box_2d("nominal-exact-x0", "p", "v"),
         unit_box_2d("nominal-exact-x1", "p", "v"),
         unit_box_2d("nominal-exact-x2", "p", "v")}, {},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{1,0},0}};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
problem::ResolvedProblem nominal_linear_exact_three_stage_multivariable() {
    const auto box = unit_box_2d("nominal-exact-three-stage-box", "p", "v");
    Problem source{{"strategy-a-nominal-linear-exact-three-stage"},
        std::make_shared<const SystemModel>(SystemModel{{
            {2,2,0},TimeDomain::discrete,
            LinearStage{{2,2,{0,0,0,0}},{2,2,{1,0,0,1}},{2,0,{}},{0,0}}}, {}}),
        {0,1,2,3},KnownInitial{{0,0}},
        ContinuousDomain{{box,box,box}},
        {UniversalSet{2},UniversalSet{2},UniversalSet{2},UniversalSet{2}}, {},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{1,0},0}};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
problem::ResolvedProblem nominal_linear_exact_affine_offsets() {
    Problem source{{"strategy-a-nominal-linear-exact-affine-offsets"},
        std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
            std::vector<LinearStage>{
                {{1,1,{-1}},{1,1,{1}},{1,0,{}},{0.25}},
                {{1,1,{2}},{1,1,{0}},{1,0,{}},{-0.5}}}}, {}}),
        {0,1,2},KnownInitial{{0.5}},
        ContinuousDomain{{interval("nominal-exact-offset-u0",0,1,"u"),
            interval("nominal-exact-offset-u1",0,1,"u")}},
        {interval("nominal-exact-offset-x0",0.5,0.5),
            interval("nominal-exact-offset-x1",0,1),UniversalSet{1}}, {},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{1},0}};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
problem::ResolvedProblem nominal_linear_exact_cancellation_objective() {
    Problem source{{"strategy-a-nominal-linear-exact-cancellation"},
        std::make_shared<const SystemModel>(SystemModel{
            {{3,1,0},TimeDomain::discrete,LinearStage{{3,3,{1,0,0,0,1,0,0,0,1}},
                {3,1,{0,0,0}},{3,0,{}},{0,0,0}}}, {}}),
        {0,1},KnownInitial{{1,1,1}},
        ContinuousDomain{{interval("nominal-exact-cancellation-control",0,1,"u")}},
        {UniversalSet{3},UniversalSet{3}}, {},{},InformationPattern::nominal_open_loop,
        LinearTerminal{{1e12,0.0001,-1e12},0}};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
problem::ResolvedProblem nominal_linear_exact_thirds() {
    const auto terminal=take(sets::make_h({{"nominal-exact-third-terminal"},1,{"nominal-exact-third-state"}},
        {take(numeric::snapshot(Matrix{2,1,{-3,1}})),
         take(numeric::snapshot_vector(Vector{-1,1})),
         take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))}));
    Problem source{{"strategy-a-nominal-linear-exact-thirds"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{0}},{1,1,{1}},{1,0,{}},{0}}}, {}}),
        {0,1},KnownInitial{{0}},ContinuousDomain{{interval("nominal-exact-third-control",0,1,"u")}},
        {interval("nominal-exact-third-state",0,0,"nominal-exact-third-state"),terminal.as_handle()}, {},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{1},0}};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
problem::ResolvedProblem nominal_linear_exact_unbounded() {
    Problem source{{"strategy-a-nominal-linear-exact-unbounded"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{0}},{1,1,{1}},{1,0,{}},{0}}}, {}}),
        {0,1},KnownInitial{{0}},ContinuousDomain{{UniversalSet{1}}},
        {interval("nominal-exact-unbounded-x0",0,0),UniversalSet{1}}, {},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{1},0}};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
problem::ResolvedProblem nominal_linear_exact_over_stage_cap() {
    constexpr std::size_t horizon=1000;
    std::vector<double> time_grid(horizon+1);
    std::iota(time_grid.begin(),time_grid.end(),0.0);
    std::vector<AdmissibleSet> controls(horizon,UniversalSet{1});
    std::vector<AdmissibleSet> states(horizon+1,UniversalSet{1});
    Problem source{{"strategy-a-nominal-linear-exact-over-cap"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}}, {}}),
        std::move(time_grid),KnownInitial{{0}},ContinuousDomain{std::move(controls)},std::move(states), {},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{1},0}};
    return take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
StrategyRequest request(problem::ResolvedProblem problem) {
    FamilyRequest family;family.objective=problem.identity();family.profile="nominal_open_loop";
    family.representation={"csl.polyhedron.h"};
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.reach-back"};
    return {std::move(problem),configuration,family,"1",{}};
}
StrategyRequest exact_request(problem::ResolvedProblem problem) {
    FamilyRequest family;family.objective=problem.identity();family.profile=synthesis::strategy_ts01::profile_id;
    family.target=FamilyTarget::exact_optimal_relation;family.assurance=Assurance::numerical;
    family.representation={"csl.polyhedron.h"};
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.reach-back"};
    configuration.representation={"csl.polyhedron.h"};
    return {std::move(problem),configuration,family,"1",{}};
}
StrategyRequest exact_ts02_request(problem::ResolvedProblem problem) {
    FamilyRequest family;family.objective=problem.identity();family.profile=synthesis::ts02_constant_integrator_profile;
    family.target=FamilyTarget::exact_optimal_relation;family.assurance=Assurance::numerical;
    family.representation={"csl.polyhedron.h"};
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.reach-back"};
    configuration.representation={"csl.polyhedron.h"};
    return {std::move(problem),configuration,family,"1",{}};
}
StrategyRequest exact_ts03_request(problem::ResolvedProblem problem) {
    auto request=exact_ts02_request(std::move(problem));
    request.family.profile=synthesis::ts03_singular_integrator_profile;
    return request;
}
StrategyRequest nominal_linear_exact_request(problem::ResolvedProblem problem) {
    FamilyRequest family;family.objective=problem.identity();
    family.profile=synthesis::strategy_a::nominal_linear_exact_profile;
    family.target=FamilyTarget::exact_optimal_relation;family.assurance=Assurance::numerical;
    family.representation={"csl.polyhedron.h"};
    StrategyConfiguration configuration;configuration.strategy={"csl.synthesis.reach-back"};
    configuration.representation={"csl.polyhedron.h"};
    return {std::move(problem),configuration,family,"1",{}};
}
class CancelAfterTerminal final : public ConvexWorkspace {
    std::unique_ptr<ConvexWorkspace> inner_;
    std::stop_source stop_;
    ProgramOutcome do_solve(const ConvexProgram& program,const ExecutionContext& context) override {
        auto outcome=inner_->solve(program,context);stop_.request_stop();return outcome;
    }
public:
    CancelAfterTerminal(std::unique_ptr<ConvexWorkspace> inner,std::stop_source stop)
        :inner_(std::move(inner)),stop_(std::move(stop)){}
};
class NumericalFailureAfterTerminal final : public ConvexWorkspace {
    std::unique_ptr<ConvexWorkspace> inner_;
    ProgramOutcome do_solve(const ConvexProgram& program,
        const ExecutionContext& context) override {
        auto outcome=inner_->solve(program,context);
        if(auto* solved=std::get_if<ProgramResult>(&outcome)) {
            solved->termination=Termination::numerical_failure;
            solved->raw_diagnostics+="\ninjected terminal numerical failure after real optimizer result";
        }
        return outcome;
    }
public:
    explicit NumericalFailureAfterTerminal(std::unique_ptr<ConvexWorkspace> inner):inner_(std::move(inner)){}
};
class ResourceLimitAfterTerminal final : public ConvexWorkspace {
    std::unique_ptr<ConvexWorkspace> inner_;
    ProgramOutcome do_solve(const ConvexProgram& program,const ExecutionContext& context) override {
        auto outcome=inner_->solve(program,context);
        if(auto* solved=std::get_if<ProgramResult>(&outcome)) {
            solved->termination=Termination::resource_limit;
            solved->raw_diagnostics+="\ninjected terminal resource limit after real optimizer result";
        }
        return outcome;
    }
public:
    explicit ResourceLimitAfterTerminal(std::unique_ptr<ConvexWorkspace> inner):inner_(std::move(inner)){}
};
class DeadlineResultAfterTerminal final : public ConvexWorkspace {
    std::unique_ptr<ConvexWorkspace> inner_;
    ProgramOutcome do_solve(const ConvexProgram& program,const ExecutionContext& context) override {
        auto outcome=inner_->solve(program,context);
        if(auto* solved=std::get_if<ProgramResult>(&outcome)) {
            solved->termination=Termination::deadline_expired;
            solved->raw_diagnostics+="\ninjected terminal deadline result";
        }
        return outcome;
    }
public:
    explicit DeadlineResultAfterTerminal(std::unique_ptr<ConvexWorkspace> inner):inner_(std::move(inner)){}
};
class DeadlineAfterTerminal final : public ConvexWorkspace {
    std::unique_ptr<ConvexWorkspace> inner_;
    ExecutionContext* caller_context_;
    ProgramOutcome do_solve(const ConvexProgram& program,const ExecutionContext& context) override {
        auto outcome=inner_->solve(program,context);
        if(std::holds_alternative<ProgramResult>(outcome))
            caller_context_->deadline=std::chrono::steady_clock::now();
        return outcome;
    }
public:
    DeadlineAfterTerminal(std::unique_ptr<ConvexWorkspace> inner,ExecutionContext& caller_context)
        :inner_(std::move(inner)),caller_context_(&caller_context){}
};
std::variant<PreparedStrategy,Rejection> admit(const StrategyRequest& request_,bool reject_terminal=false,
    std::optional<std::stop_source> stop_after_terminal={},bool omit_test_verifier=false,
    bool fail_terminal_numerically=false,bool limit_terminal_resources=false,
    ExecutionContext* expire_deadline_after_terminal=nullptr,int* lp_workspace_factories=nullptr,
    bool deadline_terminal_result=false) {
    auto lp=take(adapters::lp::make_highs_registration());
    if(lp_workspace_factories) {
        const auto factory=lp.factory;
        lp.factory=[factory,lp_workspace_factories](const LinearProgram& program) {
            ++*lp_workspace_factories;
            return factory(program);
        };
    }
    auto convex=take(adapters::convex::make_highs_registration());
    auto converter=take(adapters::polyhedral::make_qhull_registration(lp));
    auto projection=geometry::polyhedral::make_projection_registration();
    auto affine=geometry::make_affine_sum_registration({
        selected(geometry::make_lp_hull_reducer_registration(),""),selected(lp,"csl.program-result.v1"),
        selected(converter,"csl.polyhedron.v")});
    if(reject_terminal)convex.capabilities=[](const ConvexProgram&,const Requirements&)->Capability {
        return Diagnostics{{DiagnosticCode::unsupported,"test.terminal","terminal provider rejected generated request"}};
    };
    if(stop_after_terminal) {
        const auto factory=convex.factory;const auto stop=*stop_after_terminal;
        convex.factory=[factory,stop](const ConvexProgram& program) {
            return std::make_unique<CancelAfterTerminal>(factory(program),stop);
        };
    }
    if(fail_terminal_numerically) {
        const auto factory=convex.factory;
        convex.factory=[factory](const ConvexProgram& program) {
            return std::make_unique<NumericalFailureAfterTerminal>(factory(program));
        };
    }
    if(limit_terminal_resources) {
        const auto factory=convex.factory;
        convex.factory=[factory](const ConvexProgram& program) {
            return std::make_unique<ResourceLimitAfterTerminal>(factory(program));
        };
    }
    if(deadline_terminal_result) {
        const auto factory=convex.factory;
        convex.factory=[factory](const ConvexProgram& program) {
            return std::make_unique<DeadlineResultAfterTerminal>(factory(program));
        };
    }
    if(expire_deadline_after_terminal) {
        const auto factory=convex.factory;auto* caller_context=expire_deadline_after_terminal;
        convex.factory=[factory,caller_context](const ConvexProgram& program) {
            return std::make_unique<DeadlineAfterTerminal>(factory(program),*caller_context);
        };
    }
    Registry<GeometryPort> projections,affines;Registry<ConversionPort> conversions;
    Registry<LPPort> lps;Registry<ConvexPort> convexes;
    Method pm{projection.identity.id,projection.identity.version},am{affine.identity.id,affine.identity.version};
    Method cm{converter.identity.id,converter.identity.version},lm{lp.identity.id,lp.identity.version};
    Method qm{convex.identity.id,convex.identity.version};
    REQUIRE_FALSE(projections.add(projection));REQUIRE_FALSE(affines.add(affine));
    REQUIRE_FALSE(conversions.add(converter));REQUIRE_FALSE(lps.add(lp));REQUIRE_FALSE(convexes.add(convex));
    Requirements h,v,program;h.output.representation={"csl.polyhedron.h"};h.output.relation=SetRelation::equivalent;
    v.output.representation={"csl.polyhedron.v"};v.output.relation=SetRelation::equivalent;
    program.output.representation={"csl.program-result.v1"};
    auto providers=take(check_providers(select_provider(projections,pm,h),select_provider(affines,am,v),
        select_provider(conversions,cm,h),select_provider(lps,lm,program),select_provider(convexes,qm,program)));
    auto registration=synthesis::strategy_a::make_registration(std::move(providers));
    if(omit_test_verifier)registration.complete_family_verifier={};
    StrategyRegistry strategies;REQUIRE_FALSE(strategies.add(std::move(registration)));
    Requirements output;output.output.representation={"csl.polyhedron.h"};
    output.output.family=request_.family.target;
    if(!omit_test_verifier)output.output.completeness=request_.family.target==FamilyTarget::exact_optimal_relation?
        Completeness::established:Completeness::unestablished;
    return strategies.prepare(request_,output);
}
PreparedStrategy prepare(const StrategyRequest& request_,bool reject_terminal=false) {
    return take(admit(request_,reject_terminal));
}
SynthesisResult run(const StrategyRequest& request_,bool reject_terminal=false,ExecutionContext context={}) {
    if(!context.resources)context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto prepared=prepare(request_,reject_terminal);auto workspace=prepared.create();
    auto result=take(workspace->run(context));
    std::visit([](const auto& stop) {
        if constexpr(requires {stop.diagnostics.begin()->field;})
            for(const auto& d:stop.diagnostics)std::cerr<<d.field<<": "<<d.explanation<<'\n';
    },result.stop);
    return result;
}
class StrategyTimingClock final : public ob::TimingClock {
    std::int64_t tick_{};
public:
    ar::ClockDomain wall_domain() const override {
        return {{"strategy-test-wall"},ar::ClockMetric::steady_wall,"run",1,1000,
            ar::Available<std::uint64_t>{1},"test-origin"};
    }
    std::optional<ar::ClockDomain> cpu_domain() const override { return {}; }
    ar::Metric<std::int64_t> wall_now() noexcept override {
        const auto value=tick_;tick_+=10;return ar::Available<std::int64_t>{value};
    }
    ar::Metric<std::int64_t> cpu_now() noexcept override {
        return ar::Unavailable{ar::MissingReason::not_supported,{}};
    }
};
std::shared_ptr<ob::TimingCollector> strategy_timing_collector(
    const problem::ResolvedProblem& problem,std::shared_ptr<StrategyTimingClock> clock,
    std::optional<ProgramIdentity> solver_program={},ModuleId solver_backend={"csl.lp.highs"},
    std::string solver_backend_version="1.1.0+highs.1.11.0") {
    ar::ConfigurationInput configuration;
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    configuration.collection={true,ar::CollectionMode::detail,16,10000,16,10000};
    configuration.modules={{"lp",{{"lp"},"1",missing},{}},
        {"strategy",{{"csl.synthesis.reach-back"},"1",missing},{}}};
    configuration.resources={1,1,1,{}};configuration.numerical={1e-8,1e-8};
    configuration.output={ar::OutputKind::synthesis,Assurance::numerical,
        FamilyTarget::exact_optimal_relation,{"csl.polyhedron.h"},{1,0,{},{}}};
    configuration.selector={{"selector"},"1",{}};
    configuration.strategy={{"csl.synthesis.reach-back"},{"lp"},{},{},{},{},{},{"selector"},{"csl.polyhedron.h"}};
    auto resolved=ar::resolve_configuration(configuration);
    REQUIRE(std::holds_alternative<ar::ResolvedConfiguration>(resolved));
    ob::PlanInput input{problem,std::get<ar::ResolvedConfiguration>(std::move(resolved)),{"strategy-run"},
        {{{"strategy-test-wall"},ar::ClockMetric::steady_wall,"run",1,1000,
            ar::Available<std::uint64_t>{1},"test-origin"}}, {},1};
    input.tasks={"solve"};
    input.operations={"strategy-a/run","strategy-a/forward","strategy-a/feasible-preimage",
        "strategy-a/terminal-optimization","strategy-a/terminal-preimage","terminal.program.solve"};
    const std::vector<std::string> phases(input.operations.begin(),input.operations.begin()+5);
    for(std::size_t index=0;index<phases.size();++index) {
        ar::SpanDescriptor span{};span.id={index};
        if(index)span.parent=ar::SpanParent{{0},ar::ParentKind::nested};
        span.shard=0;span.bucket=0;span.task="solve";span.operation=phases[index];
        span.module=configuration.modules.back().implementation;span.clock={"strategy-test-wall"};
        span.requested_assurance=Assurance::numerical;
        span.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
        input.spans.push_back(std::move(span));
    }
    ar::SpanDescriptor solver{};solver.id={5};solver.parent=ar::SpanParent{{3},ar::ParentKind::nested};
    solver.shard=0;solver.bucket=0;solver.task="solve";solver.operation="terminal.program.solve";
    solver.module={ModuleId{"csl.synthesis.terminal-minimizers"},"1",missing};
    solver.backend=std::make_shared<const ar::ModuleIdentity>(ar::ModuleIdentity{
        std::move(solver_backend),std::move(solver_backend_version),missing});
    if(solver_program)solver.program=std::make_shared<const ProgramIdentity>(std::move(*solver_program));
    solver.clock={"strategy-test-wall"};solver.requested_assurance=Assurance::numerical;
    solver.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
    input.spans.push_back(std::move(solver));
    auto plan=ob::make_collection_plan(std::move(input));
    REQUIRE(std::holds_alternative<ob::CollectionPlan>(plan));
    auto collector=ob::make_timing_collector(std::get<ob::CollectionPlan>(std::move(plan)),std::move(clock),{0},{});
    REQUIRE(std::holds_alternative<std::shared_ptr<ob::TimingCollector>>(collector));
    return std::get<std::shared_ptr<ob::TimingCollector>>(std::move(collector));
}
const synthesis::strategy_a::CandidateHistory& payload(const SynthesisResult& result) {
    REQUIRE(result.family);REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& relation=std::get<CandidateFamily>(result.family->outcome()).relation;
    const auto* data=dynamic_cast<const synthesis::strategy_a::CandidateHistory*>(relation.payload.get());
    REQUIRE(data);return *data;
}
bool contains(const sets::SetData& set,const Vector& point) {
    const auto representation=set.representation();const auto& h=std::get<sets::HRepresentation>(representation);
    if(point.size()!=h.equalities.cols())return false;
    for(std::size_t r=0;r<h.inequalities.rows();++r) {
        double lhs=0;for(std::size_t c=0;c<point.size();++c)lhs+=h.inequalities(r,c)*point[c];
        if(lhs>h.upper_bounds[r]+1e-7)return false;
    }
    for(std::size_t r=0;r<h.equalities.rows();++r) {
        double lhs=0;for(std::size_t c=0;c<point.size();++c)lhs+=h.equalities(r,c)*point[c];
        if(std::abs(lhs-h.equality_values[r])>1e-7)return false;
    }
    return true;
}
class TestHRelationPayload final : public JointRelationPayload {
    sets::SetData relation_;
public:
    explicit TestHRelationPayload(sets::SetData relation):relation_(std::move(relation)){}
    const sets::SetData* h_relation_for_recording() const noexcept override { return &relation_; }
};
bool valid_csr(const numeric::MatrixView& matrix) {
    const auto descriptor=matrix.descriptor();
    const auto* csr=std::get_if<numeric::CsrInput>(&descriptor);
    if(!csr||csr->rows==std::numeric_limits<std::size_t>::max()||
        csr->row_offsets.size()!=csr->rows+1||csr->row_offsets.front()!=0||
        csr->row_offsets.back()!=csr->values.size()||csr->values.size()!=csr->column_indices.size())return false;
    for(std::size_t row=0;row<csr->rows;++row) {
        const auto first=csr->row_offsets[row],last=csr->row_offsets[row+1];
        if(first>last||last>csr->values.size())return false;
        for(auto index=first;index<last;++index)
            if(csr->column_indices[index]>=csr->cols||
                (index>first&&csr->column_indices[index-1]>=csr->column_indices[index]))return false;
    }
    return true;
}
bool sparse_h(const sets::SetData& set) {
    const auto representation=set.representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    return h&&valid_csr(h->inequalities)&&valid_csr(h->equalities);
}
std::size_t equality_rank(const sets::HRepresentation& h) {
    std::vector<Vector> rows(h.equalities.rows(),Vector(h.equalities.cols()));
    for(std::size_t r=0;r<rows.size();++r)for(std::size_t c=0;c<rows[r].size();++c)rows[r][c]=h.equalities(r,c);
    std::size_t rank=0;
    for(std::size_t c=0;c<h.equalities.cols() && rank<rows.size();++c) {
        auto pivot=rank;while(pivot<rows.size() && std::abs(rows[pivot][c])<1e-8)++pivot;
        if(pivot==rows.size())continue;
        std::swap(rows[rank],rows[pivot]);const auto divisor=rows[rank][c];
        for(auto& value:rows[rank])value/=divisor;
        for(std::size_t r=rank+1;r<rows.size();++r) {
            const auto factor=rows[r][c];for(std::size_t j=c;j<h.equalities.cols();++j)rows[r][j]-=factor*rows[rank][j];
        }
        ++rank;
    }
    return rank;
}
void entire_segment(const sets::SetData& set,const Vector& base,const Vector& direction,double expected_upper=1) {
    // Independent affine-subspace/interval oracle. Rank four fixes the entire
    // 5-D relation to this line; all substituted rows bound its parameter to
    // exactly [0,1]. This tests the locus rather than a witness sample.
    const auto h=std::get<sets::HRepresentation>(set.representation());
    REQUIRE(equality_rank(h)==4);
    for(std::size_t r=0;r<h.equalities.rows();++r) {
        double value=0,slope=0;for(std::size_t c=0;c<5;++c){value+=h.equalities(r,c)*base[c];slope+=h.equalities(r,c)*direction[c];}
        CHECK(value==doctest::Approx(h.equality_values[r]));CHECK(slope==doctest::Approx(0));
    }
    double lower=-std::numeric_limits<double>::infinity(),upper=std::numeric_limits<double>::infinity();
    for(std::size_t r=0;r<h.inequalities.rows();++r) {
        double value=0,slope=0;for(std::size_t c=0;c<5;++c){value+=h.inequalities(r,c)*base[c];slope+=h.inequalities(r,c)*direction[c];}
        const auto rhs=h.upper_bounds[r]-value;
        if(slope>1e-8)upper=std::min(upper,rhs/slope);
        else if(slope<-1e-8)lower=std::max(lower,rhs/slope);
        else CHECK(rhs>=-1e-8);
    }
    CHECK(lower==doctest::Approx(0));CHECK(upper==doctest::Approx(expected_upper));
}
bool has_inequality(const sets::HRepresentation& h,const Vector& coefficients,double bound) {
    const auto pivot=static_cast<std::size_t>(std::find_if(coefficients.begin(),coefficients.end(),
        [](double value){return value!=0;})-coefficients.begin());
    for(std::size_t r=0;r<h.inequalities.rows();++r) {
        const auto factor=h.inequalities(r,pivot)/coefficients[pivot];
        if(factor<=0 || std::abs(h.upper_bounds[r]-factor*bound)>1e-8)continue;
        bool same=true;for(std::size_t c=0;c<5;++c)if(std::abs(h.inequalities(r,c)-factor*coefficients[c])>1e-8)same=false;
        if(same)return true;
    }
    return false;
}
bool has_equality(const sets::HRepresentation& h,const Vector& coefficients,double value) {
    for(std::size_t row=0;row<h.equalities.rows();++row) {
        bool match=std::abs(h.equality_values[row]-value)<1e-8;
        for(std::size_t col=0;col<h.equalities.cols();++col)
            match=match&&std::abs(h.equalities(row,col)-coefficients[col])<1e-8;
        if(match)return true;
    }
    return false;
}
}
TEST_CASE("T-S01 registered candidate retains u0+u1=1 and rejects the marginal product") {
    const auto query=request(integrator());auto result=run(query);CHECK(result.termination==Termination::completed);
    const auto& history=payload(result);CHECK(history.history.coordinates==JointCoordinates{{1,1,0},2});
    CHECK(history.target==synthesis::strategy_a::PreimageTarget::terminal_candidate);
    CHECK(contains(history.history.relation,{0,0,1,0,1}));
    CHECK(contains(history.history.relation,{0,1,1,1,0}));
    CHECK(contains(history.history.relation,{0,.25,1,.25,.75}));
    CHECK_FALSE(contains(history.history.relation,{0,1,2,1,1}));
    entire_segment(history.history.relation,{0,0,1,0,1},{0,1,0,1,-1});
    REQUIRE(history.terminal);REQUIRE(history.terminal->optimization);
    INFO(history.terminal->optimization->raw_diagnostics);
    CHECK_FALSE(history.terminal->optimization->objective.upper);
    REQUIRE(history.terminal->optimization->primal);
    CHECK(take(optimization::evaluate(query.problem.objective(),
        *history.terminal->optimization->primal))==doctest::Approx(0));
    CHECK(std::holds_alternative<Unestablished>(history.terminal->construction.support));
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    CHECK(result.family->identity().request==query.family);
    CHECK(result.family->identity().lineage.size()==6);
}
TEST_CASE("exact reviewed T-S01 executes registered Strategy A providers and composes the canonical five-coordinate family") {
    const auto query=exact_request(exact_integrator());
    // This test-only registration omits the final compiled verifier so the
    // Strategy A result exposes its actual preimage alongside its proposal.
    // The ordinary registration below must then accept the same proposal.
    auto staged=take(admit(query,false,{},true));
    auto staged_workspace=staged.create();
    auto staged_result=take(staged_workspace->run(ExecutionContext{
        .resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),
        .cancellation={},
        .deadline={},
        .run_id={}}));
    REQUIRE(staged_result.family);
    CHECK(staged_result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK(staged_result.family->identity().request==query.family);
    CHECK(staged_result.family->identity().coordinates==JointCoordinates{{1,1,0},2});
    REQUIRE(staged_result.complete_proposal);
    const auto& proposal=*staged_result.complete_proposal;
    CHECK(proposal.identity.request==query.family);
    CHECK(proposal.identity.coordinates==JointCoordinates{{1,1,0},2});
    CHECK(proposal.identity.lineage==staged_result.family->identity().lineage);
    const auto& staged_history=payload(staged_result);
    CHECK(sparse_h(staged_history.history.relation));
    entire_segment(staged_history.history.relation,{0,0,1,0,1},{0,1,0,1,-1});
    CHECK_FALSE(contains(staged_history.history.relation,{0,1,2,1,1}));
    const auto& staged_complete=proposal.family;
    const auto* staged_exact=dynamic_cast<const synthesis::strategy_ts01::ExactJointRelation*>(staged_complete.relation.payload.get());
    REQUIRE(staged_exact);
    CHECK(sparse_h(staged_exact->h_polyhedron()));
    CHECK(staged_exact->h_polyhedron().metadata()->set.dimension==5);
    CHECK(staged_exact->contains(Vector{0,.25,1,.25,.75}));
    CHECK_FALSE(staged_exact->contains(Vector{0,1,2,1,1}));

    auto result=run(query);
    CHECK(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(result.family->registry_verified());
    CHECK(result.outcome.value==MathematicalOutcome::optimal);
    CHECK(result.family->identity().request==query.family);
    CHECK(result.family->identity().coordinates==JointCoordinates{{1,1,0},2});
    CHECK(result.family->identity().strategy==query.configuration.strategy);
    CHECK(result.family->identity().strategy_version=="1");
    REQUIRE(result.family->identity().lineage.size()==6);
    const auto& lineage=result.family->identity().lineage;
    CHECK(lineage[0].module==query.configuration.strategy);
    CHECK(lineage[1].module==query.configuration.strategy);
    CHECK(lineage[2].module==query.configuration.strategy);
    CHECK(lineage[3].module==ModuleId{"csl.synthesis.control-recovery"});
    CHECK(lineage[4].module==ModuleId{"csl.synthesis.terminal-minimizers"});
    CHECK(lineage[5].module==ModuleId{"csl.synthesis.control-recovery"});
    CHECK(lineage[0].request.value.starts_with("nominal-forward/"));
    CHECK(lineage[0].input.value.ends_with("/initial"));
    CHECK(lineage[0].output==lineage[1].input);
    CHECK(lineage[1].output==lineage[2].input);
    CHECK(lineage[3].request==RequestId{"strategy-a/feasible-preimage"});
    CHECK(lineage[3].input==lineage[2].output);
    CHECK(lineage[4].request.value=="syn02-terminal:"+lineage[2].output.value);
    CHECK(lineage[4].input==lineage[2].output);
    CHECK(lineage[5].input==lineage[4].output);
    REQUIRE(std::holds_alternative<CompleteOptimalFamily>(result.family->outcome()));
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&complete.completeness.support);
    REQUIRE(proof);
    CHECK(proof->verifier==ModuleId{"csl.verifier.ts01-analytic"});
    CHECK(proof->verifier_version=="1");
    CHECK(proof->proof=="TS01-analytic-v1");
    const auto* exact=dynamic_cast<const synthesis::strategy_ts01::ExactJointRelation*>(complete.relation.payload.get());
    REQUIRE(exact);
    CHECK(sparse_h(exact->h_polyhedron()));
    CHECK(exact->h_polyhedron().metadata()->set.dimension==5);
    CHECK(exact->h_polyhedron().metadata()->coordinate_labels==std::vector<std::string>{"x0","x1","x2","u0","u1"});
    // Rank-four affine equalities and substituted H-rows reduce this public relation to
    // the full locus (0,t,1,t,1-t), with the rows bounding t exactly to [0,1].
    entire_segment(exact->h_polyhedron(),{0,0,1,0,1},{0,1,0,1,-1});
    CHECK(exact->contains(Vector{0,0,1,0,1}));
    CHECK(exact->contains(Vector{0,.25,1,.25,.75}));
    CHECK(exact->contains(Vector{0,1,1,1,0}));
    CHECK_FALSE(exact->contains(Vector{0,1,2,1,1}));

}
TEST_CASE("Strategy A rejects validated assurance and the public unverified publisher rejects complete claims") {
    const auto query=exact_request(exact_integrator());

    auto validated=query;
    validated.family.assurance=Assurance::validated;
    CHECK(std::holds_alternative<Rejection>(admit(validated)));

    const auto result=run(query);
    REQUIRE(result.family);
    REQUIRE(result.family->registry_verified());
    REQUIRE(std::holds_alternative<CompleteOptimalFamily>(result.family->outcome()));
    const auto& accepted=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto& identity=result.family->identity();
    const auto publication=FamilyPublisher::publish(identity,accepted);
    REQUIRE(std::holds_alternative<Diagnostics>(publication));
    const auto& diagnostics=std::get<Diagnostics>(publication);
    CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const Diagnostic& diagnostic) {
        return diagnostic.field=="family.completeness";
    }));
}
TEST_CASE("Strategy A exact T-S01 rejects changed profiles and retains candidate on late provider failure") {
    auto query=exact_request(exact_integrator());
    auto wrong=query;wrong.family.profile+="-neighbor";
    CHECK(std::holds_alternative<Rejection>(admit(wrong)));
    auto changed=query;changed.family.objective=integrator(true).identity();
    CHECK(std::holds_alternative<Rejection>(admit(changed)));

    auto result=run(query,true);
    CHECK(result.termination==Termination::operation_rejected);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    CHECK(result.family->identity().request==query.family);
    CHECK(result.family->identity().coordinates==JointCoordinates{{1,1,0},2});
    CHECK(result.family->identity().lineage.size()==4);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    const auto& history=payload(result);
    CHECK(contains(history.history.relation,{0,1,2,1,1}));
    CHECK_FALSE(result.complete_proposal);
    REQUIRE(std::holds_alternative<ScopedRequestRejection>(result.stop));
    const auto& stop=std::get<ScopedRequestRejection>(result.stop);
    CHECK(stop.retained.partial_or_candidate_family);
    CHECK(stop.completed_lineage==result.family->identity().lineage);
    CHECK(stop.completed_lineage.size()==4);
    CHECK(stop.completed_lineage[0].output==stop.completed_lineage[1].input);
    CHECK(stop.completed_lineage[1].output==stop.completed_lineage[2].input);
    CHECK(stop.completed_lineage[3].input==stop.completed_lineage[2].output);
    CHECK(stop.request.actual_module==ModuleId{"csl.convex.highs"});
}
TEST_CASE("registered Strategy A candidate identity mismatches fail at the caller boundary") {
    const auto query=request(integrator());
    const auto result=run(query);
    REQUIRE(result.family);
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& history=payload(result);
    REQUIRE(history.terminal);
    REQUIRE(history.terminal->relation);
    REQUIRE(history.terminal->optimization);

    std::vector<TransformStepIdentity> lineage;
    for(const auto& stage:history.forward.stages) {
        REQUIRE_FALSE(stage.source_factors.empty());
        lineage.push_back({stage.marginal.evidence.reference.identity.request,
            stage.source_factors.front(),stage.marginal.output.id,
            query.configuration.strategy,query.strategy_version});
    }
    const auto feasible_slice=take(sets::from_handle(history.forward.stages.back().marginal.output));
    const auto feasible_history=take(synthesis::recover_joint_history(query.problem,feasible_slice));
    lineage.push_back({{"strategy-a/feasible-preimage"},feasible_slice.metadata()->id,
        feasible_history.relation.metadata()->id,{"csl.synthesis.control-recovery"},"1"});
    const RequestId terminal_request{history.terminal->optimization->outcome.subject.program.value};
    lineage.push_back({terminal_request,feasible_slice.metadata()->id,
        history.terminal->relation->metadata()->id,{"csl.synthesis.terminal-minimizers"},"1"});
    lineage.push_back({{"strategy-a/terminal-preimage"},history.terminal->relation->metadata()->id,
        history.history.relation.metadata()->id,{"csl.synthesis.control-recovery"},"1"});

    const FamilyIdentity expected{query.problem.identity(),query.family,
        query.problem.constraints().coordinates(),query.configuration.strategy,
        query.strategy_version,std::move(lineage)};
    REQUIRE(expected.lineage.size()==6);
    CHECK(check_synthesis_result(result,expected).empty());

    auto expect_identity_rejection=[&](FamilyIdentity mutated) {
        const auto diagnostics=check_synthesis_result(result,mutated);
        CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const Diagnostic& diagnostic) {
            return diagnostic.code==DiagnosticCode::evidence_mismatch && diagnostic.field=="family.identity";
        }));
        CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
        CHECK(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    };

    auto wrong_problem=expected;wrong_problem.problem.value+="-foreign";expect_identity_rejection(wrong_problem);
    auto wrong_request=expected;wrong_request.request.profile+="-foreign";expect_identity_rejection(wrong_request);
    auto wrong_objective=expected;wrong_objective.request.objective=integrator(true).identity();expect_identity_rejection(wrong_objective);
    auto wrong_coordinates=expected;++wrong_coordinates.coordinates.horizon;expect_identity_rejection(wrong_coordinates);
    auto wrong_strategy=expected;wrong_strategy.strategy={"csl.synthesis.foreign"};expect_identity_rejection(wrong_strategy);
    auto wrong_version=expected;wrong_version.strategy_version+="-foreign";expect_identity_rejection(wrong_version);
    auto wrong_lineage=expected;wrong_lineage.lineage.pop_back();expect_identity_rejection(wrong_lineage);
}
TEST_CASE("T-S02 constant objective preserves histories at different terminal points") {
    const auto query=request(integrator(true));auto result=run(query);const auto& history=payload(result);
    CHECK(contains(history.history.relation,{0,0,0,0,0}));
    CHECK(contains(history.history.relation,{0,1,2,1,1}));
    CHECK(contains(history.history.relation,{0,1,1,1,0}));
    CHECK(contains(history.history.relation,{0,0,1,0,1}));
    const auto h=std::get<sets::HRepresentation>(history.history.relation.representation());
    CHECK(equality_rank(h)==3);
    // The four corners span the two-dimensional feasible history plane. Rank
    // three fixes that plane, and these four halfspaces impose exactly [0,1]^2.
    CHECK(has_inequality(h,{0,0,0,1,0},1));CHECK(has_inequality(h,{0,0,0,-1,0},0));
    CHECK(has_inequality(h,{0,0,0,0,1},1));CHECK(has_inequality(h,{0,0,0,0,-1},0));
    CHECK(contains(history.history.relation,{0,.2,.9,.2,.7}));
    CHECK_FALSE(contains(history.history.relation,{0,0,2,0,1}));
    REQUIRE(history.terminal);REQUIRE(history.terminal->optimization);
    CHECK(history.terminal->optimization->outcome.value==MathematicalOutcome::optimal);
    REQUIRE(history.terminal->relation);
    CHECK_FALSE(history.terminal->optimization->objective.upper);
    REQUIRE(history.terminal->optimization->primal);
    CHECK(take(optimization::evaluate(query.problem.objective(),*history.terminal->optimization->primal))==7);
}
TEST_CASE("exact T-S02 selects its analytic verifier and publishes every feasible history") {
    const auto query=exact_ts02_request(exact_ts02_integrator());
    const auto prepared=admit(query);
    REQUIRE(std::holds_alternative<PreparedStrategy>(prepared));
    auto workspace=std::get<PreparedStrategy>(prepared).create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(workspace->run(context));
    CHECK(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(result.family->registry_verified());
    CHECK(result.family->identity().request==query.family);
    CHECK(result.family->identity().coordinates==JointCoordinates{{1,1,0},2});
    CHECK(result.family->identity().strategy==query.configuration.strategy);
    CHECK(result.family->identity().lineage.size()==6);
    CHECK(result.outcome.value==MathematicalOutcome::optimal);
    REQUIRE(result.objective.lower);REQUIRE(result.objective.upper);
    CHECK(result.objective.lower->value==3);CHECK(result.objective.upper->value==3);
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto* exact=dynamic_cast<const synthesis::Ts02ConstantIntegratorRelation*>(complete.relation.payload.get());
    REQUIRE(exact);
    const auto& canonical=exact->h_polyhedron();
    CHECK(canonical.metadata()->id==SetId{"ts02-optimal-histories"});
    CHECK(canonical.metadata()->coordinate_labels==std::vector<std::string>{"x0","x1","x2","u0","u1"});
    CHECK(contains(canonical,{0,0,0,0,0}));
    CHECK(contains(canonical,{0,1,2,1,1}));
    CHECK(contains(canonical,{0,1,1,1,0}));
    CHECK(contains(canonical,{0,0,1,0,1}));
    CHECK(contains(canonical,{0,.2,.9,.2,.7}));
    CHECK(contains(canonical,{0,.4,.9,.4,.5}));
    CHECK_FALSE(contains(canonical,{0,0,2,0,1}));
    CHECK_FALSE(contains(canonical,{1,1,1,0,0}));
    CHECK_FALSE(contains(canonical,{0,-.1,.9,-.1,1}));
    CHECK_FALSE(contains(canonical,{0,1.1,1.1,1.1,0}));
    const auto h=std::get<sets::HRepresentation>(canonical.representation());
    CHECK(equality_rank(h)==3);
    CHECK(has_inequality(h,{0,0,0,1,0},1));CHECK(has_inequality(h,{0,0,0,-1,0},0));
    CHECK(has_inequality(h,{0,0,0,0,1},1));CHECK(has_inequality(h,{0,0,0,0,-1},0));
    CHECK(has_equality(h,{1,0,0,0,0},0));
    CHECK(has_equality(h,{-1,1,0,-1,0},0));
    CHECK(has_equality(h,{0,-1,1,0,-1},0));
    const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&complete.completeness.support);
    REQUIRE(proof);
    CHECK(proof->verifier==ModuleId{synthesis::ts02_constant_integrator_verifier});
    CHECK(proof->verifier_version=="1");
    CHECK(proof->proof==synthesis::ts02_constant_integrator_proof);
}
TEST_CASE("public Strategy A exact T-S02 family equals the analytic feasible-history relation") {
    const auto query=exact_ts02_request(exact_ts02_integrator());
    auto workspace=take(admit(query)).create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(workspace->run(context));

    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto* relation=dynamic_cast<const synthesis::Ts02ConstantIntegratorRelation*>(
        complete.relation.payload.get());
    REQUIRE(relation);

    // Independently, the model defines every feasible history by x0=0,
    // x1=u0, x2=x1+u1 and the two control bounds. The objective is the
    // constant 3, so every point in this relation is optimal. These seven
    // rows are the whole relation, rather than a finite set of witnesses.
    const auto polyhedron=relation->h_polyhedron();
    CHECK(sparse_h(polyhedron));
    const auto representation=polyhedron.representation();
    const auto& actual=std::get<sets::HRepresentation>(representation);
    REQUIRE(actual.inequalities.rows()==4);
    REQUIRE(actual.equalities.rows()==3);
    CHECK(actual.inequalities.cols()==5);
    CHECK(actual.equalities.cols()==5);
    CHECK(has_inequality(actual,{0,0,0,1,0},1));
    CHECK(has_inequality(actual,{0,0,0,-1,0},0));
    CHECK(has_inequality(actual,{0,0,0,0,1},1));
    CHECK(has_inequality(actual,{0,0,0,0,-1},0));
    CHECK(has_equality(actual,{1,0,0,0,0},0));
    CHECK(has_equality(actual,{-1,1,0,-1,0},0));
    CHECK(has_equality(actual,{0,-1,1,0,-1},0));
    REQUIRE(result.objective.lower);
    REQUIRE(result.objective.upper);
    CHECK(result.objective.lower->value==3);
    CHECK(result.objective.upper->value==3);
}
TEST_CASE("public Strategy A exact T-S03 preserves every history under a unique terminal minimizer") {
    const auto query=exact_ts03_request(exact_ts03_integrator());
    auto result=run(query);
    CHECK(result.termination==Termination::completed);
    CHECK(result.outcome.value==MathematicalOutcome::optimal);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(result.family->registry_verified());
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto* relation=dynamic_cast<const synthesis::Ts03SingularIntegratorRelation*>(complete.relation.payload.get());
    REQUIRE(relation);
    const auto polyhedron=relation->h_polyhedron();
    CHECK(sparse_h(polyhedron));
    const auto representation=polyhedron.representation();
    const auto& actual=std::get<sets::HRepresentation>(representation);
    REQUIRE(actual.inequalities.rows()==2);
    REQUIRE(actual.equalities.rows()==4);
    CHECK(actual.inequalities.cols()==5);
    CHECK(actual.equalities.cols()==5);
    CHECK(has_inequality(actual,{0,0,0,1,0},1));
    CHECK(has_inequality(actual,{0,0,0,-1,0},0));
    CHECK(has_equality(actual,{1,0,0,0,0},0));
    CHECK(has_equality(actual,{0,1,0,-1,0},0));
    CHECK(has_equality(actual,{0,0,1,0,0},1));
    CHECK(has_equality(actual,{0,0,0,0,1},1));
    for(const Vector& point:std::vector<Vector>{{0,0,1,0,1},{0,.25,1,.25,1},{0,1,1,1,1}})
        CHECK(contains(polyhedron,point));
    CHECK_FALSE(contains(polyhedron,{0,1,1,1,0}));
    REQUIRE(result.objective.lower);REQUIRE(result.objective.upper);
    CHECK(result.objective.lower->value==0);CHECK(result.objective.upper->value==0);
    const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&complete.completeness.support);
    REQUIRE(proof);CHECK(proof->verifier==ModuleId{synthesis::ts03_singular_integrator_verifier});
    CHECK(proof->proof==synthesis::ts03_singular_integrator_proof);
}
TEST_CASE("T-S03 verifier profile rejects changed dynamics and objective") {
    for(const auto& problem:std::vector<problem::ResolvedProblem>{
        exact_ts02_integrator(TerminalObjective{QuadraticTerminal{{1,1,{2}},{-2},1}},1),
        exact_ts02_integrator(TerminalObjective{LinearTerminal{{0},3}},0)}) {
        const auto admitted=admit(exact_ts03_request(problem));
        REQUIRE(std::holds_alternative<Rejection>(admitted));
        CHECK_FALSE(std::get<Rejection>(admitted).diagnostics.empty());
    }
}
TEST_CASE("T-S03 compiled verifier rejects altered completeness evidence") {
    const auto query=exact_ts03_request(exact_ts03_integrator());
    auto workspace=take(admit(query,false,{},true)).create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto result=take(workspace->run(context));
    REQUIRE(result.complete_proposal);
    const auto verifier=detail::find_compiled_verifier(ModuleId{synthesis::ts03_singular_integrator_verifier},"1");
    REQUIRE(verifier);
    auto frozen=query;frozen.lineage=result.complete_proposal->identity.lineage;
    const auto verified=verifier->verify(frozen,*result.complete_proposal);
    for(const auto& diagnostic:verified)std::cerr<<diagnostic.field<<": "<<diagnostic.explanation<<'\n';
    CHECK(verified.empty());
    auto altered=*result.complete_proposal;
    auto* proof=std::get_if<RegisteredCompletenessEvidence>(&altered.family.completeness.support);
    REQUIRE(proof);proof->proof="altered-ts03-proof";
    CHECK_FALSE(verifier->verify(frozen,altered).empty());
}
TEST_CASE("nominal linear exact profile verifies the complete optimal history face") {
    const auto query=nominal_linear_exact_request(nominal_linear_exact_integrator());
    const auto result=run(query);
    CHECK(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(result.family->registry_verified());
    CHECK(result.outcome.value==MathematicalOutcome::optimal);
    REQUIRE(result.objective.lower);REQUIRE(result.objective.upper);
    CHECK(result.objective.lower->value==1);CHECK(result.objective.upper->value==1);
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&complete.completeness.support);
    REQUIRE(proof);
    CHECK(proof->verifier==ModuleId{"csl.verifier.strategy-a.nominal-linear-exact"});
    CHECK(proof->verifier_version=="1");
    CHECK(proof->proof=="nominal-linear-exact-v1");
    REQUIRE(complete.relation.payload);
    const auto* relation=complete.relation.payload->h_relation_for_recording();
    REQUIRE(relation);
    CHECK(contains(*relation,{0,0,1,0,1}));
    CHECK(contains(*relation,{0,1,1,1,0}));
    CHECK(contains(*relation,{0,.4,1,.4,.6}));
    CHECK_FALSE(contains(*relation,{0,1,2,1,1}));
    CHECK_FALSE(contains(*relation,{0,.4,1.4,.4,1}));
}
TEST_CASE("nominal linear exact profile preserves all feasible histories for a constant objective") {
    const auto result=run(nominal_linear_exact_request(nominal_linear_exact_integrator(true)));
    CHECK(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->registry_verified());
    CHECK(result.objective.lower->value==3);CHECK(result.objective.upper->value==3);
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    REQUIRE(complete.relation.payload);
    const auto* relation=complete.relation.payload->h_relation_for_recording();
    REQUIRE(relation);
    CHECK(contains(*relation,{0,0,1,0,1}));
    CHECK(contains(*relation,{0,1,2,1,1}));
    CHECK(contains(*relation,{0,.4,1.2,.4,.8}));
}
TEST_CASE("nominal linear exact profile verifies a multi-state multi-control optimal history face") {
    const auto result=run(nominal_linear_exact_request(nominal_linear_exact_multivariable()));
    CHECK(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->registry_verified());
    CHECK(result.outcome.value==MathematicalOutcome::optimal);
    REQUIRE(result.objective.lower);REQUIRE(result.objective.upper);
    CHECK(result.objective.lower->value==0);CHECK(result.objective.upper->value==0);
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    CHECK(complete.relation.coordinates.dimensions.state==2);
    CHECK(complete.relation.coordinates.dimensions.control==2);
    CHECK(complete.relation.coordinates.horizon==2);
    REQUIRE(complete.relation.payload);
    const auto* relation=complete.relation.payload->h_relation_for_recording();
    REQUIRE(relation);
    CHECK(relation->metadata()->set.dimension==10);
    const auto h=std::get<sets::HRepresentation>(relation->representation());
    CHECK(equality_rank(h)==7);
    CHECK(contains(*relation,{0,0,0,0,0,0,0,0,0,0}));
    CHECK(contains(*relation,{0,0,1,1,0,1,1,1,0,1}));
    CHECK(contains(*relation,{0,0,.25,.75,0,.5,.25,.75,0,.5}));
    CHECK_FALSE(contains(*relation,{0,0,1,1,.5,1,1,1,.5,1}));
    CHECK_FALSE(contains(*relation,{0,0,1,1,0,1,.5,1,0,1}));
}
TEST_CASE("nominal linear exact profile recovers a three-stage joint optimal history relation") {
    const auto result=run(nominal_linear_exact_request(
        nominal_linear_exact_three_stage_multivariable()));
    CHECK(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(result.family->registry_verified());
    CHECK(result.outcome.value==MathematicalOutcome::optimal);
    REQUIRE(result.objective.lower);REQUIRE(result.objective.upper);
    CHECK(result.objective.lower->value==0);CHECK(result.objective.upper->value==0);
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    CHECK(complete.relation.coordinates.dimensions.state==2);
    CHECK(complete.relation.coordinates.dimensions.control==2);
    CHECK(complete.relation.coordinates.horizon==3);
    REQUIRE(complete.relation.payload);
    const auto* relation=complete.relation.payload->h_relation_for_recording();
    REQUIRE(relation);
    CHECK(relation->metadata()->set.dimension==14);
    const auto h=std::get<sets::HRepresentation>(relation->representation());
    CHECK(equality_rank(h)==9);

    // The terminal p objective fixes the final p control to zero. Earlier p
    // controls and all v controls still generate multiple three-stage histories.
    CHECK(contains(*relation,{0,0,0,1,0,0.5,0,0,0,1,0,0.5,0,0}));
    CHECK(contains(*relation,{0,0,0,0.25,0,0.25,0,0.25,0,0.25,0,0.25,0,0.25}));
    CHECK(contains(*relation,{0,0,0.25,0.25,0.5,0.5,0,0.75,
        0.25,0.25,0.5,0.5,0,0.75}));
    // This is feasible for the original problem, but has positive terminal p
    // and therefore is outside the complete optimal relation.
    CHECK_FALSE(contains(*relation,{0,0,0,0,0,0,0.25,0,
        0,0,0,0,0.25,0}));
    CHECK_FALSE(contains(*relation,{0,0,0,1,0,1.25,0,1.5,0,1,0,0.5,0,0}));
}
TEST_CASE("nominal linear exact profile preserves affine offsets and a free control fiber") {
    const auto result=run(nominal_linear_exact_request(nominal_linear_exact_affine_offsets()));
    CHECK(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->registry_verified());
    CHECK(result.outcome.value==MathematicalOutcome::optimal);
    REQUIRE(result.objective.lower);REQUIRE(result.objective.upper);
    CHECK(result.objective.lower->value==-0.5);
    CHECK(result.objective.upper->value==-0.5);

    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    REQUIRE(complete.relation.payload);
    const auto* relation=complete.relation.payload->h_relation_for_recording();
    REQUIRE(relation);
    CHECK(relation->metadata()->set.dimension==5);
    const auto h=std::get<sets::HRepresentation>(relation->representation());
    CHECK(equality_rank(h)==4);
    // x1=u0-0.25 and x2=2*u0-1. The intermediate bound gives u0>=0.25,
    // so minimizing x2 fixes u0=0.25 while u1 remains free in [0,1].
    CHECK(contains(*relation,{0.5,0,-0.5,0.25,0}));
    CHECK(contains(*relation,{0.5,0,-0.5,0.25,1}));
    CHECK(contains(*relation,{0.5,0,-0.5,0.25,0.4}));
    CHECK_FALSE(contains(*relation,{0.5,0.25,0,0.5,0.4}));
    CHECK_FALSE(contains(*relation,{0.5,0,-0.5,0.25,1.2}));
}
TEST_CASE("nominal linear exact evidence derives the dyadic optimum without rounded accumulation") {
    const auto bounds=registry::detail::strategy_a_nominal_linear_exact_optimum_bounds(
        nominal_linear_exact_cancellation_objective());
    REQUIRE(bounds);
    CHECK(bounds->first==0.0001);
    CHECK(bounds->second==0.0001);
    CHECK((1e12+0.0001)-1e12!=bounds->first);
}
TEST_CASE("nominal linear exact verifier rejects changed optimum evidence") {
    const auto query=nominal_linear_exact_request(nominal_linear_exact_integrator());
    auto staged=take(admit(query,false,{},true)).create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto result=take(staged->run(context));
    REQUIRE(result.complete_proposal);
    const auto verifier=detail::find_compiled_verifier(
        ModuleId{"csl.verifier.strategy-a.nominal-linear-exact"},"1");
    REQUIRE(verifier);
    auto frozen=query;frozen.lineage=result.complete_proposal->identity.lineage;
    const auto initial_diagnostics=verifier->verify(frozen,*result.complete_proposal);
    CHECK(initial_diagnostics.empty());
    auto altered=*result.complete_proposal;
    altered.family.optimum.bounds.upper->value=2;
    const auto diagnostics=verifier->verify(frozen,altered);
    CHECK_FALSE(diagnostics.empty());
}
TEST_CASE("nominal linear exact verifier rejects a candidate that omits optimal histories") {
    const auto query=nominal_linear_exact_request(nominal_linear_exact_integrator());
    auto staged=take(admit(query,false,{},true)).create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto result=take(staged->run(context));
    REQUIRE(result.complete_proposal);
    const auto verifier=detail::find_compiled_verifier(
        ModuleId{"csl.verifier.strategy-a.nominal-linear-exact"},"1");
    REQUIRE(verifier);
    auto frozen=query;frozen.lineage=result.complete_proposal->identity.lineage;

    const auto inequalities=take(numeric::snapshot(Matrix{4,5,{
        0,0,0,1,0, 0,0,0,-1,0, 0,0,0,0,1, 0,0,0,0,-1}}));
    const auto upper=take(numeric::snapshot_vector(Vector{0.5,0,1,0}));
    const auto equalities=take(numeric::snapshot(Matrix{4,5,{
        1,0,0,0,0, -1,1,0,-1,0, 0,-1,1,0,-1, 0,0,1,0,0}}));
    const auto values=take(numeric::snapshot_vector(Vector{0,0,0,1}));
    auto omitted=take(sets::make_h({{"nominal-exact-omits-half"},5,{"x0","x1","x2","u0","u1"}},
        {inequalities,upper,equalities,values}));
    CHECK(contains(omitted,{0,0,1,0,1}));
    CHECK_FALSE(contains(omitted,{0,1,1,1,0}));
    auto altered=*result.complete_proposal;
    altered.family.relation.payload=std::make_shared<const TestHRelationPayload>(std::move(omitted));
    CHECK_FALSE(verifier->verify(frozen,altered).empty());
}
TEST_CASE("nominal linear exact verifier encloses a non-dyadic optimum") {
    const auto query=nominal_linear_exact_request(nominal_linear_exact_thirds());
    const auto bounds=registry::detail::strategy_a_nominal_linear_exact_optimum_bounds(query.problem);
    REQUIRE(bounds);
    CHECK(bounds->first==1.0/3.0);
    CHECK(bounds->second==std::nextafter(1.0/3.0,1.0));
    const auto generated=run(query);
    CHECK(generated.termination==Termination::completed);
    REQUIRE(generated.family);
    CHECK(generated.family->registry_verified());
    REQUIRE(generated.objective.lower);
    REQUIRE(generated.objective.upper);
    CHECK(generated.objective.lower->value==bounds->first);
    CHECK(generated.objective.upper->value==bounds->second);
    const auto& generated_complete=std::get<CompleteOptimalFamily>(generated.family->outcome());
    REQUIRE(generated_complete.relation.payload);
    const auto* generated_relation=generated_complete.relation.payload->h_relation_for_recording();
    REQUIRE(generated_relation);
    CHECK(contains(*generated_relation,{0,1.0/3.0,1.0/3.0}));
    const JointCoordinates coordinates{query.problem.model().dimensions(),query.problem.model().horizon()};
    const FamilyIdentity identity{query.problem.identity(),query.family,coordinates,
        {"csl.synthesis.reach-back"},"1",
        detail::strategy_a_nominal_linear_exact_lineage(query.problem.identity(),1)};
    auto relation=take(sets::make_h({{"nominal-exact-third-face"},3,{"x0","x1","u0"}},
        {take(numeric::snapshot(Matrix{2,3,{0,0,1,0,0,-1}})),
         take(numeric::snapshot_vector(Vector{1,0})),
         take(numeric::snapshot(Matrix{3,3,{1,0,0,0,1,-1,0,3,0}})),
         take(numeric::snapshot_vector(Vector{0,0,1}))}));
    const SymbolicArgument statement{"outward objective bounds", "Adjacent binary64 values enclose the exact rational optimum one third."};
    const ClaimEvidence claim{query.problem.identity(),statement};
    const ObjectiveBound rounded_lower{bounds->first,claim};
    const ObjectiveBound rounded_upper{bounds->second,claim};
    CompleteOptimalFamily candidate{{coordinates,query.family.representation,
            std::make_shared<const TestHRelationPayload>(std::move(relation))},
        {claim,{rounded_lower,rounded_upper}},
        {identity,RegisteredCompletenessEvidence{{"csl.verifier.strategy-a.nominal-linear-exact"},
            "1","nominal-linear-exact-v1"}},Assurance::numerical};
    CompleteFamilyProposal proposal{identity,std::move(candidate)};
    auto frozen=query;frozen.lineage=identity.lineage;
    const auto verifier=detail::find_compiled_verifier(
        ModuleId{"csl.verifier.strategy-a.nominal-linear-exact"},"1");
    REQUIRE(verifier);
    CHECK(verifier->verify(frozen,proposal).empty());
}
TEST_CASE("nominal linear exact verifier rejects a claimed optimum for an unbounded history set") {
    const auto query=nominal_linear_exact_request(nominal_linear_exact_unbounded());
    const JointCoordinates coordinates{query.problem.model().dimensions(),query.problem.model().horizon()};
    const FamilyIdentity identity{query.problem.identity(),query.family,coordinates,
        {"csl.synthesis.reach-back"},"1",
        detail::strategy_a_nominal_linear_exact_lineage(query.problem.identity(),1)};
    auto relation=take(sets::make_h({{"nominal-exact-fabricated-point"},3,{"x0","x1","u0"}},
        {take(numeric::snapshot(Matrix{0,3,{}})),
         take(numeric::snapshot_vector(Vector{})),
         take(numeric::snapshot(Matrix{3,3,{1,0,0,0,1,-1,0,0,1}})),
         take(numeric::snapshot_vector(Vector{0,0,0}))}));
    const SymbolicArgument statement{"fabricated bounded point", "One feasible history does not bound the problem."};
    const ClaimEvidence claim{query.problem.identity(),statement};
    const ObjectiveBound bound{0,claim};
    CompleteOptimalFamily candidate{{coordinates,query.family.representation,
            std::make_shared<const TestHRelationPayload>(std::move(relation))},
        {claim,{bound,bound}},
        {identity,RegisteredCompletenessEvidence{{"csl.verifier.strategy-a.nominal-linear-exact"},
            "1","nominal-linear-exact-v1"}},Assurance::numerical};
    CompleteFamilyProposal proposal{identity,std::move(candidate)};
    auto frozen=query;frozen.lineage=identity.lineage;
    const auto verifier=detail::find_compiled_verifier(
        ModuleId{"csl.verifier.strategy-a.nominal-linear-exact"},"1");
    REQUIRE(verifier);
    CHECK_FALSE(verifier->verify(frozen,proposal).empty());
}
TEST_CASE("nominal linear exact profile rejects an unreviewed materialization cap") {
    auto query=nominal_linear_exact_request(nominal_linear_exact_integrator());
    query.family.materialization_limit=1;
    const auto admitted=admit(query);
    REQUIRE(std::holds_alternative<Rejection>(admitted));
    CHECK_FALSE(std::get<Rejection>(admitted).diagnostics.empty());
}
TEST_CASE("nominal linear exact profile rejects a horizon exceeding its variable-width cap") {
    const auto query=nominal_linear_exact_request(nominal_linear_exact_over_stage_cap());
    const auto admitted=admit(query);
    REQUIRE(std::holds_alternative<Rejection>(admitted));
    CHECK_FALSE(std::get<Rejection>(admitted).diagnostics.empty());
}
TEST_CASE("exact T-S02 recovered preimage contains the entire feasible control box") {
    const auto query=exact_ts02_request(exact_ts02_integrator());
    auto workspace=take(admit(query,false,{},true)).create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(workspace->run(context));
    const auto& history=payload(result);
    CHECK(history.target==synthesis::strategy_a::PreimageTarget::terminal_candidate);
    REQUIRE(result.complete_proposal);
    const auto h=std::get<sets::HRepresentation>(history.history.relation.representation());
    CHECK(equality_rank(h)==3);
    // Affine rows attaining their maximum on these four vertices admit every
    // point (0,s,s+t,s,t), s,t in [0,1], by convexity. The three dynamics
    // equalities and literal control bounds exclude every other history.
    for(const Vector& point:std::vector<Vector>{{0,0,0,0,0},{0,1,1,1,0},{0,0,1,0,1},{0,1,2,1,1}})
        CHECK(contains(history.history.relation,point));
    CHECK(has_equality(h,{1,0,0,0,0},0));
    CHECK(has_equality(h,{-1,1,0,-1,0},0));
    CHECK(has_equality(h,{0,-1,1,0,-1},0));
    CHECK(has_inequality(h,{0,0,0,1,0},1));CHECK(has_inequality(h,{0,0,0,-1,0},0));
    CHECK(has_inequality(h,{0,0,0,0,1},1));CHECK(has_inequality(h,{0,0,0,0,-1},0));
}
TEST_CASE("exact T-S02 rejects requests outside its reviewed model and objective at admission") {
    for(const auto& problem:std::vector<problem::ResolvedProblem>{
        exact_ts02_integrator(LinearTerminal{{0},7}),
        exact_ts02_integrator(LinearTerminal{{1},3}),
        exact_ts02_integrator(LinearTerminal{{0},3},0)}) {
        const auto admitted=admit(exact_ts02_request(problem));
        REQUIRE(std::holds_alternative<Rejection>(admitted));
        CHECK_FALSE(std::get<Rejection>(admitted).diagnostics.empty());
    }
}
TEST_CASE("exact T-S02 verifier rejects altered Strategy A bindings and payloads") {
    const auto query=exact_ts02_request(exact_ts02_integrator());
    const auto result=run(query);
    REQUIRE(result.family);
    const auto& complete=std::get<CompleteOptimalFamily>(result.family->outcome());
    const CompleteFamilyProposal proposal{result.family->identity(),complete};
    auto frozen=query;frozen.lineage=result.family->identity().lineage;
    const auto verifier=registry::detail::find_compiled_verifier({synthesis::ts02_constant_integrator_verifier},"1");
    REQUIRE(verifier);
    CHECK(verifier->verify(frozen,proposal).empty());
    const auto rejected=[&](const StrategyRequest& request,const CompleteFamilyProposal& altered,std::string field) {
        const auto diagnostics=verifier->verify(request,altered);
        CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[&](const Diagnostic& diagnostic) {
            return diagnostic.field==field;
        }));
    };
    auto wrong_lineage=frozen;wrong_lineage.lineage.pop_back();
    rejected(wrong_lineage,proposal,"ts02.verifier.profile");
    auto wrong_model=frozen;wrong_model.problem=exact_ts02_integrator(LinearTerminal{{0},3},0);
    rejected(wrong_model,proposal,"ts02.verifier.profile");
    auto wrong_objective=frozen;wrong_objective.problem=exact_ts02_integrator(LinearTerminal{{0},4});
    rejected(wrong_objective,proposal,"ts02.verifier.profile");
    auto wrong_binding=proposal;wrong_binding.identity.lineage.front().output={"foreign-output"};
    rejected(frozen,wrong_binding,"ts02.verifier.binding");
    auto wrong_bounds=proposal;wrong_bounds.family.optimum.bounds.upper->value=4;
    rejected(frozen,wrong_bounds,"ts02.verifier.optimum");
    auto wrong_payload=proposal;wrong_payload.family.relation.payload=std::make_shared<const JointRelationPayload>();
    rejected(frozen,wrong_payload,"ts02.verifier.relation");
    const auto* exact=dynamic_cast<const synthesis::Ts02ConstantIntegratorRelation*>(complete.relation.payload.get());
    REQUIRE(exact);
    auto h=std::get<sets::HRepresentation>(exact->h_polyhedron().representation());
    h.upper_bounds=take(numeric::snapshot_vector(Vector{2,0,1,0}));
    auto enlarged=take(sets::make_h({{"ts02-optimal-histories"},5,{"x0","x1","x2","u0","u1"}},h));
    wrong_payload.family.relation.payload=std::make_shared<const synthesis::Ts02ConstantIntegratorRelation>(std::move(enlarged));
    rejected(frozen,wrong_payload,"ts02.verifier.relation");
}
TEST_CASE("exact T-S02 preserves the reviewed constant quadratic and residual norm objectives") {
    for(const auto& objective:std::vector<TerminalObjective>{
        QuadraticTerminal{{1,1,{0}},{0},3},ResidualNormTerminal{{1,1,{0}},{3}}}) {
        const auto result=run(exact_ts02_request(exact_ts02_integrator(objective)));
        REQUIRE(result.termination==Termination::completed);
        REQUIRE(result.family);
        CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
        CHECK(result.family->registry_verified());
        REQUIRE(result.objective.lower);REQUIRE(result.objective.upper);
        CHECK(result.objective.lower->value==3);CHECK(result.objective.upper->value==3);
    }
}
TEST_CASE("exact T-S02 freezes the selected registration version during preparation") {
    auto query=exact_ts02_request(exact_ts02_integrator());query.strategy_version.clear();
    const auto result=run(query);
    REQUIRE(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::exact_optimal_relation);
    CHECK(result.family->registry_verified());
    CHECK(result.family->identity().strategy_version=="1");
}
TEST_CASE("T-S03 singular A keeps free earlier controls with a unique terminal minimizer") {
    // Reproduce an ordinary preceding Strategy A call that exits at the late
    // terminal provider boundary, then exercise the real T-S03 user result.
    const auto rejected=run(request(integrator()),true);
    CHECK(rejected.termination==Termination::operation_rejected);
    REQUIRE(rejected.family);
    const auto& rejected_history=payload(rejected);
    CHECK(contains(rejected_history.history.relation,{0,1,2,1,1}));
    auto result=run(request(integrator(false,true)));const auto& history=payload(result);
    CHECK(result.termination==Termination::completed);
    CHECK(contains(history.history.relation,{0,0,1,0,1}));
    CHECK(contains(history.history.relation,{0,1,1,1,1}));
    CHECK_FALSE(contains(history.history.relation,{0,1,0,1,0}));
    entire_segment(history.history.relation,{0,0,1,0,1},{0,1,0,1,0});
}
TEST_CASE("late terminal admission rejection retains a feasible candidate and scoped lineage") {
    auto result=run(request(integrator()),true);
    CHECK(result.termination==Termination::operation_rejected);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());CHECK_FALSE(result.complete_proposal);CHECK_FALSE(result.partial_proposal);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK_FALSE(result.family->registry_verified());CHECK_FALSE(result.family->partial_registry_verified());
    const auto& history=payload(result);CHECK(contains(history.history.relation,{0,1,2,1,1}));
    REQUIRE(history.terminal);
    const SetId final_slice{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward2/project/output"};
    CHECK(history.terminal->construction.feasible_slice==final_slice);
    const auto generated_request=RequestId{"syn02-terminal:nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward2/project/output"};
    REQUIRE(std::holds_alternative<ScopedRequestRejection>(result.stop));
    const auto& stop=std::get<ScopedRequestRejection>(result.stop);
    CHECK(stop.request.request==generated_request);
    CHECK(stop.request.port=="convex");
    CHECK(stop.request.requested_module==ModuleId{"csl.convex.highs"});
    CHECK(stop.request.requested_version==std::optional<std::string>{"1.0.0+highs.1.11.0"});
    CHECK(stop.request.actual_module==ModuleId{"csl.convex.highs"});
    CHECK(stop.request.actual_version==std::optional<std::string>{"1.0.0+highs.1.11.0"});
    CHECK_FALSE(stop.retained.lower_bound);CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);CHECK(stop.retained.partial_or_candidate_family);
    const SetId initial{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward0/initial"};
    const SetId reachable0{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward0/project/output"};
    const SetId reachable1{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward1/project/output"};
    const SetId reachable2{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward2/project/output"};
    const SetId recovered{"recovery/joint-history/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf9142:nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward2/project/output"};
    const std::vector<TransformStepIdentity> expected_lineage{
        {{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward0/stage"},initial,reachable0,{"csl.synthesis.reach-back"},"1"},
        {{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward1/stage"},reachable0,reachable1,{"csl.synthesis.reach-back"},"1"},
        {{"nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward2/stage"},reachable1,reachable2,{"csl.synthesis.reach-back"},"1"},
        {{"strategy-a/feasible-preimage"},reachable2,recovered,{"csl.synthesis.control-recovery"},"1"}};
    CHECK(stop.completed_lineage==expected_lineage);
    CHECK(stop.completed_lineage==result.family->identity().lineage);
    REQUIRE(stop.diagnostics.size()==1);
    CHECK(stop.diagnostics[0].code==DiagnosticCode::unsupported);
    CHECK(stop.diagnostics[0].field=="test.terminal");
    CHECK(stop.diagnostics[0].explanation=="terminal provider rejected generated request");
    CHECK(history.terminal->construction.feasible_slice==history.forward.stages.back().marginal.output.id);
}
TEST_CASE("post-terminal cancellation keeps scoped optimizer and completed terminal lineage") {
    const auto query=request(integrator());std::stop_source stop_source;
    auto prepared=take(admit(query,false,stop_source));auto workspace=prepared.create();
    ExecutionContext context;context.cancellation=stop_source.get_token();
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto result=take(workspace->run(context));
    CHECK(result.termination==Termination::cancelled);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());CHECK_FALSE(result.complete_proposal);CHECK_FALSE(result.partial_proposal);
    REQUIRE(result.family);CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK_FALSE(result.family->registry_verified());CHECK_FALSE(result.family->partial_registry_verified());
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& candidate=std::get<CandidateFamily>(result.family->outcome());
    REQUIRE(std::holds_alternative<HeuristicRelationEvidence>(candidate.relation_to_target));
    CHECK(std::get<HeuristicRelationEvidence>(candidate.relation_to_target).method==
        "binary64 feasible-history preimage of forward terminal slice; objective has not restricted this candidate");
    CHECK(std::holds_alternative<Unestablished>(candidate.feasibility));
    const auto& history=payload(result);REQUIRE(history.terminal);REQUIRE(history.terminal->relation);
    CHECK(history.target==synthesis::strategy_a::PreimageTarget::forward_terminal_slice);
    CHECK(contains(*history.terminal->relation,{1.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{0.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{2.0}));
    CHECK(std::holds_alternative<Unestablished>(history.terminal->construction.support));
    REQUIRE(history.terminal->optimum);
    CHECK(history.terminal->optimum->optimum.problem==query.problem.identity());
    CHECK(std::holds_alternative<Unestablished>(history.terminal->optimum->optimum.support));
    CHECK_FALSE(history.terminal->optimum->bounds.lower);CHECK_FALSE(history.terminal->optimum->bounds.upper);
    REQUIRE(history.terminal->optimization);
    CHECK(history.terminal->optimization->termination==Termination::completed);
    CHECK(history.terminal->optimization->outcome.value==MathematicalOutcome::optimal);
    CHECK_FALSE(history.terminal->optimization->objective.lower);
    CHECK_FALSE(history.terminal->optimization->objective.upper);
    CHECK(history.terminal->optimization->raw_diagnostics.find("bounds=unavailable")!=std::string::npos);
    CHECK(contains(history.history.relation,{0,1,2,1,1})); // unrecovered feasible candidate stays correctly scoped
    const auto& lineage=result.family->identity().lineage;
    REQUIRE(lineage.size()==5);
    CHECK(lineage.back().output==history.terminal->relation->metadata()->id);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(result.stop));
    const auto& stop=std::get<ScopedOperationStopped>(result.stop);
    CHECK(stop.stop.reason==StopReason::cancelled);
    CHECK(stop.stop.diagnostics=="Cancelled between Strategy A phases.");
    CHECK(stop.request.request==RequestId{"strategy-a/terminal-preimage"});
    CHECK(stop.request.port=="strategy");
    CHECK(stop.request.requested_module==ModuleId{"csl.synthesis.reach-back"});
    CHECK(stop.request.requested_version=="1");
    CHECK(stop.request.actual_module==ModuleId{"csl.synthesis.reach-back"});
    CHECK(stop.request.actual_version=="1");
    CHECK_FALSE(stop.retained.lower_bound);CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);CHECK(stop.retained.partial_or_candidate_family);
    // Strategy A publishes no caller-visible timing spans on this stop; timing evidence remains a #89 dependency.
    CHECK(result.spans.empty());
}
TEST_CASE("post-terminal deadline expiry retains the completed slice and unestablished candidate") {
    const auto query=request(integrator());
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto prepared=take(admit(query,false,{},false,false,false,&context));auto workspace=prepared.create();
    auto result=take(workspace->run(context));
    CHECK(result.termination==Termination::deadline_expired);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());CHECK_FALSE(result.complete_proposal);CHECK_FALSE(result.partial_proposal);
    REQUIRE(result.family);CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK_FALSE(result.family->registry_verified());CHECK_FALSE(result.family->partial_registry_verified());
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& candidate=std::get<CandidateFamily>(result.family->outcome());
    REQUIRE(std::holds_alternative<HeuristicRelationEvidence>(candidate.relation_to_target));
    CHECK(std::get<HeuristicRelationEvidence>(candidate.relation_to_target).method==
        "binary64 feasible-history preimage of forward terminal slice; objective has not restricted this candidate");
    CHECK(std::holds_alternative<Unestablished>(candidate.feasibility));
    const auto& history=payload(result);CHECK(history.target==synthesis::strategy_a::PreimageTarget::forward_terminal_slice);
    CHECK(contains(history.history.relation,{0,1,2,1,1}));
    REQUIRE(history.terminal);REQUIRE(history.terminal->relation);
    CHECK(contains(*history.terminal->relation,{1.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{0.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{2.0}));
    CHECK(std::holds_alternative<Unestablished>(history.terminal->construction.support));
    REQUIRE(history.terminal->optimum);
    CHECK(history.terminal->optimum->optimum.problem==query.problem.identity());
    CHECK(std::holds_alternative<Unestablished>(history.terminal->optimum->optimum.support));
    CHECK_FALSE(history.terminal->optimum->bounds.lower);CHECK_FALSE(history.terminal->optimum->bounds.upper);
    REQUIRE(history.terminal->optimization);
    CHECK(history.terminal->termination==Termination::completed);
    CHECK(history.terminal->optimization->termination==Termination::completed);
    CHECK(history.terminal->optimization->outcome.value==MathematicalOutcome::optimal);
    CHECK_FALSE(history.terminal->optimization->objective.lower);
    CHECK_FALSE(history.terminal->optimization->objective.upper);
    CHECK(history.terminal->optimization->outcome.subject.problem==query.problem.identity());
    CHECK(history.terminal->optimization->outcome.subject.program.value==
        "syn02-terminal:nominal-forward/86:csl.problem.v1.sha256:b98b5e966ad430ce2e0c8934cc88badcb7eeda9cffb168485606786dba96faf918:strategy-a/forward2/project/output");
    const auto& lineage=result.family->identity().lineage;
    REQUIRE(lineage.size()==5);
    CHECK(lineage.back().output==history.terminal->relation->metadata()->id);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(result.stop));
    const auto& stop=std::get<ScopedOperationStopped>(result.stop);
    CHECK(stop.stop.reason==StopReason::deadline_expired);
    CHECK(stop.stop.diagnostics=="Deadline expired between Strategy A phases.");
    CHECK(stop.request.request==RequestId{"strategy-a/terminal-preimage"});
    CHECK(stop.request.port=="strategy");
    CHECK(stop.request.requested_module==ModuleId{"csl.synthesis.reach-back"});
    CHECK(stop.request.requested_version=="1");
    CHECK(stop.request.actual_module==ModuleId{"csl.synthesis.reach-back"});
    CHECK(stop.request.actual_version=="1");
    CHECK_FALSE(stop.retained.lower_bound);CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);CHECK(stop.retained.partial_or_candidate_family);
    // Strategy A emits no caller-visible timing spans on this stop; timing coverage remains a #89 dependency.
    CHECK(result.spans.empty());
}
TEST_CASE("registered terminal resource limit retains only the unestablished feasible candidate") {
    const auto query=request(integrator());
    auto prepared=take(admit(query,false,{},false,false,true));auto workspace=prepared.create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(workspace->run(context));
    CHECK(result.termination==Termination::resource_limit);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());CHECK_FALSE(result.complete_proposal);CHECK_FALSE(result.partial_proposal);
    REQUIRE(result.family);CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK_FALSE(result.family->registry_verified());CHECK_FALSE(result.family->partial_registry_verified());
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& candidate=std::get<CandidateFamily>(result.family->outcome());
    REQUIRE(std::holds_alternative<HeuristicRelationEvidence>(candidate.relation_to_target));
    CHECK(std::get<HeuristicRelationEvidence>(candidate.relation_to_target).method==
        "binary64 feasible-history preimage of forward terminal slice; objective has not restricted this candidate");
    CHECK(std::holds_alternative<Unestablished>(candidate.feasibility));
    const auto& history=payload(result);
    CHECK(history.target==synthesis::strategy_a::PreimageTarget::forward_terminal_slice);
    CHECK(contains(history.history.relation,{0,1,2,1,1}));
    REQUIRE(history.terminal);REQUIRE(history.terminal->relation);
    CHECK(contains(*history.terminal->relation,{1.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{0.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{2.0}));
    CHECK(std::holds_alternative<Unestablished>(history.terminal->construction.support));
    REQUIRE(history.terminal->optimum);
    CHECK(std::holds_alternative<Unestablished>(history.terminal->optimum->optimum.support));
    CHECK_FALSE(history.terminal->optimum->bounds.lower);CHECK_FALSE(history.terminal->optimum->bounds.upper);
    REQUIRE(history.terminal->optimization);
    CHECK(history.terminal->termination==Termination::resource_limit);
    CHECK(history.terminal->optimization->termination==Termination::resource_limit);
    CHECK(history.terminal->optimization->outcome.value==MathematicalOutcome::optimal);
    CHECK(history.terminal->optimization->raw_diagnostics.find(
        "injected terminal resource limit after real optimizer result")!=std::string::npos);
    CHECK_FALSE(history.terminal->optimization->objective.lower);
    CHECK_FALSE(history.terminal->optimization->objective.upper);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(result.stop));
    const auto& stop=std::get<ScopedOperationStopped>(result.stop);
    CHECK(stop.stop.reason==StopReason::resource_limit);
    CHECK(stop.stop.diagnostics=="Terminal optimization stopped; slice-scoped evidence retained.");
    CHECK(stop.request.port=="convex");
    CHECK(stop.request.request==RequestId{"syn02-terminal:"+history.terminal->construction.feasible_slice.value});
    CHECK(stop.request.requested_module==ModuleId{"csl.convex.highs"});
    CHECK(stop.request.actual_module==ModuleId{"csl.convex.highs"});
    CHECK(stop.request.actual_version==std::optional<std::string>{"1.0.0+highs.1.11.0"});
    CHECK_FALSE(stop.retained.lower_bound);CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);CHECK(stop.retained.partial_or_candidate_family);
    // Strategy A emits no caller-visible timing spans on this stop; timing coverage remains a #89 dependency.
    CHECK(result.spans.empty());
}
TEST_CASE("registered terminal provider deadline preserves its termination without caller deadline") {
    const auto query=request(integrator());
    auto prepared=take(admit(query,false,{},false,false,false,nullptr,nullptr,true));
    auto workspace=prepared.create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(workspace->run(context));
    CHECK(result.termination==Termination::deadline_expired);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(result.stop));
    CHECK(std::get<ScopedOperationStopped>(result.stop).stop.reason==StopReason::deadline_expired);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
}
TEST_CASE("registered terminal numerical failure retains the feasible candidate and scoped optimizer evidence") {
    const auto query=request(integrator());
    auto prepared=take(admit(query,false,{},false,true));auto workspace=prepared.create();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(workspace->run(context));
    CHECK(result.termination==Termination::numerical_failure);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.objective.lower);CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());CHECK_FALSE(result.complete_proposal);
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    REQUIRE(std::holds_alternative<CandidateFamily>(result.family->outcome()));
    const auto& candidate=std::get<CandidateFamily>(result.family->outcome());
    CHECK(std::holds_alternative<HeuristicRelationEvidence>(candidate.relation_to_target));
    CHECK(std::holds_alternative<Unestablished>(candidate.feasibility));
    const auto& history=payload(result);
    CHECK(history.target==synthesis::strategy_a::PreimageTarget::forward_terminal_slice);
    CHECK(contains(history.history.relation,{0,1,2,1,1}));
    REQUIRE(history.terminal);REQUIRE(history.terminal->relation);
    CHECK(history.terminal->relation->metadata()->id.value==
        history.terminal->construction.feasible_slice.value+":terminal-candidate");
    CHECK(std::holds_alternative<Unestablished>(history.terminal->construction.support));
    CHECK(contains(*history.terminal->relation,{1.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{0.0}));
    CHECK_FALSE(contains(*history.terminal->relation,{2.0}));
    REQUIRE(history.terminal->optimization);
    CHECK(history.terminal->optimization->termination==Termination::numerical_failure);
    CHECK(history.terminal->optimization->raw_diagnostics.find(
        "injected terminal numerical failure after real optimizer result")!=std::string::npos);
    CHECK(history.terminal->optimization->outcome.value==MathematicalOutcome::optimal);
    const auto& optimizer=*history.terminal->optimization;
    CHECK(optimizer.outcome.subject.problem==query.problem.identity());
    CHECK(optimizer.outcome.subject.program.value==
        "syn02-terminal:"+history.terminal->construction.feasible_slice.value);
    CHECK(std::holds_alternative<Unestablished>(optimizer.outcome.support));
    CHECK_FALSE(optimizer.objective.lower);CHECK_FALSE(optimizer.objective.upper);
    CHECK(optimizer.raw_diagnostics.find("bounds=unavailable")!=std::string::npos);
    REQUIRE(optimizer.residuals.primal);
    CHECK(optimizer.residuals.primal->context.subject==optimizer.outcome.subject);
    CHECK(optimizer.residuals.primal->context.verifier.id==ModuleId{"csl.convex.highs.primal"});
    CHECK(optimizer.residuals.primal->context.verifier.version=="1");
    CHECK(optimizer.residuals.primal->context.absolute_tolerance==query.family.numerical.absolute_tolerance);
    CHECK(optimizer.residuals.primal->context.relative_tolerance==query.family.numerical.relative_tolerance);
    REQUIRE(optimizer.primal);
    REQUIRE(optimizer.primal->size()==1);
    const auto terminal_state=optimizer.primal->front();
    const auto primal_tolerance=optimizer.residuals.primal->context.absolute_tolerance+
        optimizer.residuals.primal->context.relative_tolerance;
    CHECK(std::abs(terminal_state-1.0)<=primal_tolerance);
    CHECK(terminal_state>=0.0);CHECK(terminal_state<=2.0);
    CHECK(optimizer.residuals.primal->rows.violation<=
        optimizer.residuals.primal->context.absolute_tolerance+
        optimizer.residuals.primal->context.relative_tolerance*optimizer.residuals.primal->rows.scale);
    CHECK(optimizer.residuals.primal->rows.scale==doctest::Approx(2.0));
    CHECK(optimizer.residuals.primal->variables.violation<=
        optimizer.residuals.primal->context.absolute_tolerance+
        optimizer.residuals.primal->context.relative_tolerance*optimizer.residuals.primal->variables.scale);
    CHECK(optimizer.residuals.primal->variables.scale==1.0);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(result.stop));
    const auto& stop=std::get<ScopedOperationStopped>(result.stop);
    CHECK(stop.stop.reason==StopReason::numerical_failure);
    CHECK(stop.stop.diagnostics=="Terminal optimization stopped; slice-scoped evidence retained.");
    CHECK(stop.request.port=="convex");
    CHECK(stop.request.actual_module==ModuleId{"csl.convex.highs"});
    CHECK_FALSE(stop.retained.lower_bound);CHECK_FALSE(stop.retained.upper_bound);
    CHECK(stop.retained.incumbents==0);CHECK(stop.retained.partial_or_candidate_family);
    CHECK(result.spans.empty());
}
TEST_CASE("coverage and materialization requests fail closed at strategy preparation") {
    auto query=request(integrator());
    for(auto target:{FamilyTarget::exact_optimal_relation,FamilyTarget::partial_relation}) {
        query.family.target=target;const auto rejected=alternative<Rejection>(admit(query));
        CHECK(rejected.diagnostics[0].field=="strategy_a.coverage");
        CHECK(rejected.provenance.actual->id==ModuleId{"csl.synthesis.reach-back"});
    }
    query.family.target=FamilyTarget::candidate_relaxation;query.family.materialization_limit=20;
    CHECK(alternative<Rejection>(admit(query)).diagnostics[0].field=="strategy_a.capacity");
    query.family.materialization_limit.reset();query.family.assurance=Assurance::validated;
    CHECK(alternative<Rejection>(admit(query)).diagnostics[0].field=="family");
}
TEST_CASE("registered Strategy A preserves its prepared numerical policy in the public result") {
    auto query=request(integrator());
    query.family.assurance=Assurance::numerical;
    query.family.numerical={1e-7,2e-7};
    auto prepared=prepare(query);

    auto matching_workspace=prepared.create();
    ExecutionContext matching_context;
    matching_context.numerical={1e-7,2e-7};
    matching_context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto result=take(matching_workspace->run(matching_context));
    REQUIRE(result.family);
    CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
    CHECK(result.family->identity().request.numerical.absolute_tolerance==1e-7);
    CHECK(result.family->identity().request.numerical.relative_tolerance==2e-7);
    CHECK(result.family->identity().request.numerical==(NumericalPolicy{1e-7,2e-7}));

    auto mismatched_workspace=prepared.create();
    ExecutionContext mismatched_context;
    mismatched_context.numerical={1e-6,2e-7};
    mismatched_context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto mismatch=mismatched_workspace->run(mismatched_context);
    REQUIRE(std::holds_alternative<SynthesisResult>(mismatch));
    const auto& rejected=std::get<SynthesisResult>(mismatch);
    CHECK(rejected.termination==Termination::contract_rejected);
    CHECK(rejected.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(std::holds_alternative<ContractValidationFailure>(rejected.stop));
    const auto& failure=std::get<ContractValidationFailure>(rejected.stop);
    REQUIRE(failure.diagnostics.size()==1);
    CHECK(failure.diagnostics.front().code==DiagnosticCode::invalid_input);
    CHECK(failure.diagnostics.front().field=="family.numerical");
    CHECK(failure.diagnostics.front().explanation==
        "ExecutionContext numerical policy differs from the prepared family request");
    CHECK_FALSE(failure.retained.lower_bound);
    CHECK_FALSE(failure.retained.upper_bound);
    CHECK(failure.retained.incumbents==0);
    CHECK_FALSE(failure.retained.partial_or_candidate_family);
    CHECK_FALSE(rejected.objective.lower);
    CHECK_FALSE(rejected.objective.upper);
    CHECK_FALSE(rejected.family);
    CHECK(rejected.incumbents.empty());
    CHECK(rejected.spans.empty());
    CHECK(check_synthesis_result(rejected,prepared.expected_synthesis_identity()).empty());
}
TEST_CASE("stage constraints restrict the joint locus without separating histories") {
    auto source=*integrator().description();source.states[1]=interval("restricted-X1",0,.5);
    auto problem=take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    auto result=run(request(problem));const auto& history=payload(result);
    entire_segment(history.history.relation,{0,0,1,0,1},{0,1,0,1,-1},.5);
    CHECK_FALSE(contains(history.history.relation,{0,1,1,1,0}));
}
TEST_CASE("cancellation and deadline retain distinct scoped stops and no mathematical claim") {
    const auto query=request(integrator());std::stop_source source;source.request_stop();
    ExecutionContext context;context.cancellation=source.get_token();auto cancelled=run(query,false,context);
    CHECK(cancelled.termination==Termination::cancelled);
    CHECK(cancelled.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(cancelled.stop));
    CHECK(std::get<ScopedOperationStopped>(cancelled.stop).stop.reason==StopReason::cancelled);
    context={};context.deadline=std::chrono::steady_clock::now();auto expired=run(query,false,context);
    CHECK(expired.termination==Termination::deadline_expired);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(expired.stop));
    CHECK(std::get<ScopedOperationStopped>(expired.stop).stop.reason==StopReason::deadline_expired);
    CHECK(std::get<ScopedOperationStopped>(expired.stop).stop.diagnostics.find("deadline")!=std::string::npos);
}
TEST_CASE("unsupported authored finite controls and declared temporal coupling reject in preparation") {
    auto source=*integrator().description();source.controls=FiniteDomain{1,{{0},{1}}};
    auto problem=take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    CHECK(alternative<Rejection>(admit(request(problem))).diagnostics[0].field=="controls");
    source=*integrator().description();source.temporal=TemporalConstraints{{1,5,{0,1},{0},{1}},{{0,0}}};
    problem=take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    CHECK(alternative<Rejection>(admit(request(problem))).diagnostics[0].field=="strategy_a.temporal");
}

TEST_CASE("Strategy A rejects noncompact vertex-ray controls before creating a downstream workspace") {
    auto source=*integrator().description();
    const auto ray=take(sets::make_v({{"unbounded-control"},1,{"u"}},
        {take(numeric::snapshot(Matrix{1,1,{0}})),take(numeric::snapshot(Matrix{1,1,{1}}))})).as_handle();
    CHECK(ray.metadata.bounded==SetProperty::unknown);
    const auto representation=std::get<sets::VRepresentation>(take(sets::from_handle(ray)).representation());
    CHECK(representation.vertices(0,0)==0);
    CHECK(representation.rays(0,0)==1);
    source.controls=ContinuousDomain{{ray,interval("u1",0,1,"u")}};
    const auto problem=take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));

    int lp_workspace_factories=0;
    const auto admission=admit(request(problem),false,{},false,false,false,nullptr,&lp_workspace_factories);
    REQUIRE(std::holds_alternative<Rejection>(admission));
    const auto& rejection=std::get<Rejection>(admission);
    REQUIRE(rejection.diagnostics.size()==1);
    CHECK(rejection.diagnostics[0].code==DiagnosticCode::unsupported);
    CHECK(rejection.diagnostics[0].field=="strategy_a.controls");
    CHECK(rejection.diagnostics[0].explanation=="Native H, singleton, empty or universal control factors required.");
    CHECK(lp_workspace_factories==0);
}

TEST_CASE("empty temporal constraints do not disable Strategy A capability") {
    auto source=*integrator().description();
    source.temporal=TemporalConstraints{{0,5,{0},{},{}},{}};
    const auto empty=take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));

    auto prepared=admit(request(empty));
    REQUIRE(std::holds_alternative<PreparedStrategy>(prepared));

    const auto result=run(request(empty));
    CHECK(result.termination==Termination::completed);
    const auto& history=payload(result);
    CHECK(history.target==synthesis::strategy_a::PreimageTarget::terminal_candidate);
    CHECK(history.history.coordinates==JointCoordinates{{1,1,0},2});
    CHECK(contains(history.history.relation,{0,0,1,0,1}));
    CHECK(contains(history.history.relation,{0,1,1,1,0}));
}

TEST_CASE("Strategy A admits and runs a slew-memory transformed integrator") {
    auto source=*exact_integrator().description();
    source.id={"ext03-stage-a-slew"};
    source.controls=ContinuousDomain{{interval("slew-u0",-1,1,"u"),interval("slew-u1",-1,1,"u")}};
    source.states={interval("slew-x0",-2,2,"x"),interval("slew-x1",-2,2,"x"),interval("slew-x2",-2,2,"x")};
    source.objective=QuadraticTerminal{{1,1,{2}},{0},0};
    const auto lifted=problem::lift_one_step_slew(source,{
        problem::RateLimitedFirstAction{{0},interval("slew-d0",-.25,.25,"du")},
        {interval("slew-d1",-.25,.25,"du")}});
    REQUIRE(std::holds_alternative<problem::SlewMemoryLift>(lifted));
    const auto resolved=take(problem::resolve(std::get<problem::SlewMemoryLift>(lifted).problem,
        {problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    const auto prepared=admit(request(resolved));
    REQUIRE(std::holds_alternative<PreparedStrategy>(prepared));
    const auto result=run(request(resolved));
    CHECK(result.termination==Termination::completed);
    REQUIRE(result.family);
    CHECK(result.family->identity().coordinates==JointCoordinates{{2,1,0},2});
    CHECK(result.outcome.value!=MathematicalOutcome::infeasible);
}

TEST_CASE("nonempty temporal coupling remains an unsupported Strategy A request") {
    auto source=*integrator().description();
    source.temporal=TemporalConstraints{{1,5,{0,1},{0},{1}},{{0,0}}};
    const auto coupled=take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    const auto rejection=alternative<Rejection>(admit(request(coupled)));
    REQUIRE(rejection.diagnostics.size()==1);
    CHECK(rejection.diagnostics[0].code==DiagnosticCode::unsupported);
    CHECK(rejection.diagnostics[0].field=="strategy_a.temporal");
}

TEST_CASE("empty reachable stage stays undetermined without authored infeasibility evidence") {
    auto source=*integrator().description();
    source.states[2]=interval("impossible-X2",3,4);
    const auto problem=take(problem::resolve(source,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));

    const auto result=run(request(problem));

    CHECK(result.termination==Termination::completed);
    CHECK(result.outcome.subject==problem.identity());
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK(std::holds_alternative<Unestablished>(result.outcome.support));
    REQUIRE(result.outcome.assumptions.size()==2);
    CHECK(result.outcome.assumptions[0]==
        "forward recurrence, terminal construction and joint-history coverage remain unestablished");
    CHECK(result.outcome.assumptions[1]==
        "forward stage 2 compiled empty; authored infeasibility is not independently established");
    CHECK_FALSE(result.family);
    CHECK_FALSE(result.objective.lower);
    CHECK_FALSE(result.objective.upper);
    CHECK(result.incumbents.empty());
    CHECK(std::holds_alternative<std::monostate>(result.stop));
}

TEST_CASE("Strategy A publishes planned wall spans for its run and mathematical phases") {
    auto problem=exact_ts02_integrator();
    const auto reference=run(request(problem));
    const auto& reference_history=payload(reference);
    REQUIRE(reference_history.terminal);
    REQUIRE(reference_history.terminal->optimization);
    const auto terminal_program=reference_history.terminal->optimization->outcome.subject;
    auto clock=std::make_shared<StrategyTimingClock>();
    auto collector=strategy_timing_collector(problem,clock,terminal_program);
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    context.run_id="strategy-run";context.timing=collector;

    const auto result=run(exact_ts02_request(problem),false,std::move(context));
    REQUIRE(result.termination==Termination::completed);
    CHECK(result.spans.empty()); // Legacy seconds are not populated from collector ticks.
    auto report=collector->snapshot();
    REQUIRE(std::holds_alternative<ob::TimingReport>(report));
    const auto& timing=std::get<ob::TimingReport>(report);
    REQUIRE(timing.spans.size()==6);
    REQUIRE(std::holds_alternative<ar::Available<std::uint64_t>>(timing.run_wall_ticks));
    CHECK(std::get<ar::Available<std::uint64_t>>(timing.run_wall_ticks).value==110);
    for(std::size_t index=1;index<5;++index) {
        if(index==3)continue;
        REQUIRE(std::holds_alternative<ar::Available<std::uint64_t>>(timing.spans[index].inclusive_wall_ticks));
        CHECK(std::get<ar::Available<std::uint64_t>>(timing.spans[index].inclusive_wall_ticks).value==10);
    }
    CHECK(timing.spans[5].id==ar::SpanId{5});
    CHECK(std::get<ar::Available<std::uint64_t>>(timing.spans[3].inclusive_wall_ticks).value==30);
    CHECK(std::get<ar::Available<std::uint64_t>>(timing.spans[5].inclusive_wall_ticks).value==10);
    CHECK(std::get<ar::ReturnedSpan>(timing.observations.description().spans[5].status).termination==Termination::completed);
    const auto& solver=timing.observations.description().spans[5].descriptor;
    CHECK(solver.operation=="terminal.program.solve");
    REQUIRE(solver.backend);
    CHECK(solver.backend->id==ModuleId{"csl.lp.highs"});
    CHECK(solver.backend->version=="1.1.0+highs.1.11.0");
    REQUIRE(solver.program);
    CHECK(*solver.program==terminal_program);
    REQUIRE(reference_history.terminal->optimization->primal);
    CHECK(solver.input_size==reference_history.terminal->optimization->primal->size());
    CHECK(solver.output_size==reference_history.terminal->optimization->primal->size());

    auto wrong_program=terminal_program;
    wrong_program.program.value+="-wrong";
    auto mismatch_clock=std::make_shared<StrategyTimingClock>();
    auto mismatch_collector=strategy_timing_collector(problem,mismatch_clock,wrong_program);
    ExecutionContext mismatch_context;
    mismatch_context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    mismatch_context.run_id="strategy-run-mismatched-program";mismatch_context.timing=mismatch_collector;
    const auto mismatch_result=run(exact_ts02_request(problem),false,std::move(mismatch_context));
    REQUIRE(mismatch_result.termination==Termination::completed);
    const auto mismatch_report=mismatch_collector->snapshot();
    REQUIRE(std::holds_alternative<ob::TimingReport>(mismatch_report));
    const auto& mismatch_timing=std::get<ob::TimingReport>(mismatch_report);
    REQUIRE(mismatch_timing.spans.size()==6);
    CHECK(std::holds_alternative<ar::Unavailable>(mismatch_timing.spans[5].inclusive_wall_ticks));
    CHECK(std::holds_alternative<ar::IncompleteSpan>(
        mismatch_timing.observations.description().spans[5].status));
}

TEST_CASE("Strategy A records the selected convex backend for a quadratic terminal solve") {
    auto problem=integrator();
    const auto query=request(problem);
    const auto reference=run(query);
    const auto& reference_history=payload(reference);
    REQUIRE(reference_history.terminal);
    REQUIRE(reference_history.terminal->optimization);
    REQUIRE(reference_history.terminal->provider);
    REQUIRE(reference_history.terminal->provider->actual);
    const auto terminal_program=reference_history.terminal->optimization->outcome.subject;
    CHECK(reference_history.terminal->provider->actual->id==ModuleId{"csl.convex.highs"});
    CHECK(reference_history.terminal->provider->actual->version=="1.0.0+highs.1.11.0");

    auto clock=std::make_shared<StrategyTimingClock>();
    auto collector=strategy_timing_collector(problem,clock,terminal_program,
        ModuleId{"csl.convex.highs"},"1.0.0+highs.1.11.0");
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    context.run_id="strategy-run";context.timing=collector;
    const auto result=run(query,false,std::move(context));
    REQUIRE(result.termination==Termination::completed);
    const auto report=collector->snapshot();
    REQUIRE(std::holds_alternative<ob::TimingReport>(report));
    const auto& timing=std::get<ob::TimingReport>(report);
    REQUIRE(timing.spans.size()==6);
    REQUIRE(std::holds_alternative<ar::Available<std::uint64_t>>(timing.spans[5].inclusive_wall_ticks));
    CHECK(std::get<ar::Available<std::uint64_t>>(timing.spans[5].inclusive_wall_ticks).value==10);
    CHECK(std::get<ar::ReturnedSpan>(timing.observations.description().spans[5].status).termination==Termination::completed);
    const auto& solver=timing.observations.description().spans[5].descriptor;
    REQUIRE(solver.program);
    CHECK(*solver.program==terminal_program);
    REQUIRE(solver.backend);
    CHECK(solver.backend->id==ModuleId{"csl.convex.highs"});
    CHECK(solver.backend->version=="1.0.0+highs.1.11.0");
}

TEST_CASE("Strategy A timing retains a stopped root and leaves unentered phases unavailable") {
    auto problem=exact_ts02_integrator();
    auto clock=std::make_shared<StrategyTimingClock>();
    auto collector=strategy_timing_collector(problem,clock);
    std::stop_source cancellation;cancellation.request_stop();
    ExecutionContext context;context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    context.run_id="strategy-run";context.timing=collector;context.cancellation=cancellation.get_token();

    const auto result=run(exact_ts02_request(problem),false,std::move(context));
    CHECK(result.termination==Termination::cancelled);
    CHECK(result.spans.empty());
    auto report=collector->snapshot();
    REQUIRE(std::holds_alternative<ob::TimingReport>(report));
    const auto& timing=std::get<ob::TimingReport>(report);
    REQUIRE(timing.spans.size()==6);
    REQUIRE(std::holds_alternative<ar::Available<std::uint64_t>>(timing.spans[0].inclusive_wall_ticks));
    CHECK(std::get<ar::Available<std::uint64_t>>(timing.spans[0].inclusive_wall_ticks).value==30);
    for(std::size_t index=2;index<5;++index) {
        REQUIRE(std::holds_alternative<ar::Unavailable>(timing.spans[index].inclusive_wall_ticks));
        CHECK(std::get<ar::Unavailable>(timing.spans[index].inclusive_wall_ticks).reason==ar::MissingReason::incomplete_span);
    }
    CHECK(std::holds_alternative<ar::Unavailable>(timing.run_wall_ticks));
    CHECK(std::get<ar::Unavailable>(timing.run_wall_ticks).reason==ar::MissingReason::incomplete_span);
}
