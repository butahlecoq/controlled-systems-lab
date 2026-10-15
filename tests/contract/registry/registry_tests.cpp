#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/registry/registry.hpp>
#include <limits>
#include "fixtures.hpp"

using namespace csl;
using namespace csl::registry;
using namespace registry_fixtures;
static_assert(!std::is_default_constructible_v<PreparedPipeline<LPPort>>);
static_assert(!std::is_default_constructible_v<PreparedStrategy>);
static_assert(!std::is_copy_constructible_v<BoundWorkspace<LPPort>>);

namespace {
// A plugin may omit provenance, misreport it, or return a foreign witness.
// These tests exercise the public boundary, not a concrete selection algorithm.
class AdversarialSelectorWorkspace final : public WitnessSelectorWorkspace {
public:
    std::optional<FamilyIdentity> reported_source;
    ProblemId witness_problem{"problem"};
    std::variant<WitnessSelection,Unsupported> select(const OptimalFamily&,
        const WitnessRequest& request,const ExecutionContext&) override {
        return WitnessSelection{{{{witness_problem,{{0},{1}},{{1}},5}},
            request.count,{"adversarial-selector"},request.seed,reported_source},
            Termination::resource_limit,"selection search budget exhausted"};
    }
};

using CompletenessSupport = decltype(CompletenessEvidence{}.support);

class MalformedCompletenessProposal final : public SynthesisWorkspace {
    CompletenessSupport support_;
public:
    explicit MalformedCompletenessProposal(CompletenessSupport support) : support_(std::move(support)) {}

    SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest& request,
        const ExecutionContext&) override {
        const auto id=problem.identity();
        const ModuleId strategy{"synthetic-completeness-guard"};
        const std::string version{"1"};
        const FamilyIdentity identity{id,request,problem.constraints().coordinates(),strategy,version,{}};
        const JointRelation relation{identity.coordinates,request.representation,
            std::make_shared<const JointRelationPayload>()};
        const ClaimEvidence optimum{id,SymbolicArgument{"synthetic optimum","fixture objective"}};
        const ObjectiveBound bound{0,optimum};
        CompleteOptimalFamily complete{relation,{optimum,{bound,bound}},
            {identity,std::move(support_)},Assurance::numerical};
        SynthesisResult result{Termination::completed,
            {id,MathematicalOutcome::optimal,optimum.support,{}},{bound,bound},{},{},{},{}};
        result.complete_proposal=CompleteFamilyProposal{identity,std::move(complete)};
        return result;
    }
};
}

TEST_CASE("public selector binds omitted provenance without promoting a candidate family") {
    AdversarialSelectorWorkspace workspace;
    const auto original=candidate_family();
    auto identity=original.identity();
    identity.lineage={{{"transform/1"},{"source"},{"joint"},{"converter"},"1"}};
    auto published=FamilyPublisher::publish(identity,original.outcome());
    REQUIRE(std::holds_alternative<OptimalFamily>(published));
    const SelectorRequest request{std::get<OptimalFamily>(std::move(published)),{3,0.001,{{1}},29}};
    const auto answer=SelectorPort::run(workspace,request,context());
    REQUIRE(std::holds_alternative<WitnessSelection>(answer));
    const auto& selection=std::get<WitnessSelection>(answer);
    REQUIRE(selection.batch.source_family.has_value());
    CHECK(*selection.batch.source_family==request.family.identity());
    CHECK(selection.batch.source_family->problem.value=="problem");
    CHECK(selection.batch.source_family->request.profile=="nominal_open_loop");
    CHECK(selection.batch.source_family->request.target==FamilyTarget::candidate_relaxation);
    CHECK(selection.batch.source_family->coordinates==JointCoordinates{{1,1,0},1});
    CHECK(selection.batch.source_family->strategy.value=="strategy");
    CHECK(selection.batch.source_family->strategy_version=="1");
    REQUIRE(selection.batch.source_family->lineage.size()==1);
    CHECK(selection.batch.source_family->lineage[0].request.value=="transform/1");
    CHECK(selection.batch.source_family->lineage[0].input.value=="source");
    CHECK(selection.batch.source_family->lineage[0].output.value=="joint");
    CHECK(selection.batch.source_family->lineage[0].module.value=="converter");
    CHECK(selection.batch.source_family->lineage[0].version=="1");
    CHECK(selection.batch.requested==3);
    CHECK(selection.batch.seed==std::optional<std::size_t>{29});
    CHECK(selection.batch.selector.value=="adversarial-selector");
    REQUIRE(selection.batch.witnesses.size()==1);
    const auto& witness=selection.batch.witnesses[0];
    CHECK(witness.problem.value=="problem");
    CHECK(witness.states==std::vector<Vector>{{0},{1}});
    CHECK(witness.controls==std::vector<Vector>{{1}});
    CHECK(witness.original_objective==5);
    CHECK(selection.termination==Termination::resource_limit);
    CHECK(selection.diagnostics=="selection search budget exhausted");
    CHECK(request.family.target()==FamilyTarget::candidate_relaxation);
    REQUIRE(std::holds_alternative<CandidateFamily>(request.family.outcome()));
    const auto& candidate=std::get<CandidateFamily>(request.family.outcome());
    CHECK(candidate.relation.coordinates==JointCoordinates{{1,1,0},1});
    CHECK(candidate.relation.representation.value=="joint");
    REQUIRE(std::holds_alternative<HeuristicRelationEvidence>(candidate.relation_to_target));
    CHECK(std::get<HeuristicRelationEvidence>(candidate.relation_to_target).method=="fixture");
    CHECK(std::holds_alternative<Unestablished>(candidate.feasibility));
    CHECK_FALSE(request.family.registry_verified());
}

TEST_CASE("public selector rejects conflicting source identity even for the same problem") {
    AdversarialSelectorWorkspace workspace;
    const SelectorRequest request{candidate_family(),{3,0.001,{{1}},29}};
    // Establish successful selection before trying independent identity conflicts.
    workspace.reported_source=request.family.identity();
    const auto accepted=SelectorPort::run(workspace,request,context());
    REQUIRE(std::holds_alternative<WitnessSelection>(accepted));
    REQUIRE(std::get<WitnessSelection>(accepted).batch.witnesses.size()==1);
    CHECK(std::get<WitnessSelection>(accepted).batch.witnesses[0].original_objective==5);
    std::vector<FamilyIdentity> conflicts;
    auto add=[&](auto mutation){auto id=request.family.identity();mutation(id);conflicts.push_back(std::move(id));};
    add([](auto& id){id.problem={"foreign-problem"};});
    add([](auto& id){id.request.profile="foreign-profile";});
    add([](auto& id){id.request.target=FamilyTarget::partial_relation;});
    add([](auto& id){id.coordinates.horizon=2;});
    add([](auto& id){id.strategy={"foreign-strategy"};});
    add([](auto& id){id.strategy_version="2";});
    add([](auto& id){id.lineage={{{"transform/1"},{"source"},{"target"},{"converter"},"1"}};});
    for (const auto& conflict:conflicts) {
        workspace.reported_source=conflict;
        const auto rejected=SelectorPort::run(workspace,request,context());
        REQUIRE(std::holds_alternative<Unsupported>(rejected));
        const auto& diagnostics=std::get<Unsupported>(rejected).diagnostics;
        REQUIRE(diagnostics.size()==1);
        CHECK(diagnostics[0].code==DiagnosticCode::evidence_mismatch);
        CHECK(diagnostics[0].field=="selection.source_family");
    }
}

TEST_CASE("public selector rejects a witness from another problem") {
    AdversarialSelectorWorkspace workspace;
    const SelectorRequest request{candidate_family(),{3,0.001,{{1}},29}};
    const auto accepted=SelectorPort::run(workspace,request,context());
    REQUIRE(std::holds_alternative<WitnessSelection>(accepted));
    REQUIRE(std::get<WitnessSelection>(accepted).batch.witnesses.size()==1);
    CHECK(std::get<WitnessSelection>(accepted).batch.witnesses[0].states==std::vector<Vector>{{0},{1}});
    workspace.witness_problem={"foreign-problem"};
    const auto rejected=SelectorPort::run(workspace,request,context());
    REQUIRE(std::holds_alternative<Unsupported>(rejected));
    const auto& diagnostics=std::get<Unsupported>(rejected).diagnostics;
    REQUIRE(diagnostics.size()==1);
    CHECK(diagnostics[0].code==DiagnosticCode::evidence_mismatch);
    CHECK(diagnostics[0].field=="selection.witness.problem");
}

TEST_CASE("direct family publication rejects malformed effective numerical policies") {
    const auto original=candidate_family();
    for (const auto policy:std::vector<NumericalPolicy>{{-1,0},{0,-1},
        {std::numeric_limits<double>::infinity(),0},{0,std::numeric_limits<double>::infinity()},
        {std::numeric_limits<double>::quiet_NaN(),0},{0,std::numeric_limits<double>::quiet_NaN()}}) {
        auto identity=original.identity();identity.request.numerical=policy;
        const auto published=FamilyPublisher::publish(identity,original.outcome());
        REQUIRE(std::holds_alternative<Diagnostics>(published));
        const auto& diagnostics=std::get<Diagnostics>(published);
        CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const auto& d){
            return d.code==DiagnosticCode::invalid_input && d.field=="family.numerical";
        }));
    }
    auto zero=original.identity();zero.request.numerical={0,0};
    const auto accepted=FamilyPublisher::publish(zero,original.outcome());
    REQUIRE(std::holds_alternative<OptimalFamily>(accepted));
    CHECK(std::get<OptimalFamily>(accepted).identity().request.numerical==NumericalPolicy{0,0});
    CHECK(original.identity().request.numerical==NumericalPolicy{1e-8,1e-8});
}

TEST_CASE("direct strategy admission rejects malformed effective requests before execution") {
    class ObservedWorkspace final : public SynthesisWorkspace {
    public:
        std::size_t attempts{};
        SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest&,
            const ExecutionContext&) override {
            ++attempts;
            return {Termination::completed,{problem.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},
                {},{},{},{}};
        }
    } workspace;
    auto request=strategy_request();request.strategy_version="1";
    for (const auto policy:std::vector<NumericalPolicy>{{-1,0},{0,-1},
        {std::numeric_limits<double>::infinity(),0},{0,std::numeric_limits<double>::infinity()}}) {
        request.family.numerical=policy;auto execution=context();execution.numerical=policy;
        const auto rejected=StrategyPort::run(workspace,request,execution);
        REQUIRE(std::holds_alternative<Unsupported>(rejected));
        REQUIRE_FALSE(std::get<Unsupported>(rejected).diagnostics.empty());
        CHECK(std::get<Unsupported>(rejected).diagnostics[0].field=="family.numerical");
        CHECK(workspace.attempts==0);
    }
    request.family.numerical={0,0};auto execution=context();execution.numerical={0,0};
    const auto objective=request.family.objective;
    request.family.objective={"another-objective"};
    auto rejected=StrategyPort::run(workspace,request,execution);
    REQUIRE(std::holds_alternative<Unsupported>(rejected));
    CHECK(std::get<Unsupported>(rejected).diagnostics[0].field=="family.objective");
    CHECK(workspace.attempts==0);
    request.family.objective=objective;request.family.profile.clear();
    rejected=StrategyPort::run(workspace,request,execution);
    REQUIRE(std::holds_alternative<Unsupported>(rejected));
    CHECK(std::get<Unsupported>(rejected).diagnostics[0].field=="family.profile");
    CHECK(workspace.attempts==0);
    request.family.profile="nominal_open_loop";
    rejected=StrategyPort::run(workspace,request,context());
    REQUIRE(std::holds_alternative<Unsupported>(rejected));
    CHECK(std::get<Unsupported>(rejected).diagnostics[0].field=="family.numerical");
    CHECK(workspace.attempts==0);
    const auto accepted=StrategyPort::run(workspace,request,execution);
    REQUIRE(std::holds_alternative<SynthesisResult>(accepted));
    CHECK(std::get<SynthesisResult>(accepted).termination==Termination::completed);
    CHECK(workspace.attempts==1);
}

TEST_CASE("prepared strategy rejects a mismatched execution policy and preserves matching solve evidence") {
    class PolicyObservingWorkspace final : public SynthesisWorkspace {
    public:
        SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest&,
            const ExecutionContext& context) override {
            const auto id=problem.identity();
            SynthesisResult result{Termination::completed,
                {id,MathematicalOutcome::undetermined,Unestablished{},{}},{},{},{},{}};
            result.objective.upper=ObjectiveBound{5,
                {id,NumericalCheck{context.numerical.absolute_tolerance,
                    context.numerical.relative_tolerance,0,ModuleId{"policy-observer"}}}};
            return result;
        }
    };
    StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add({{{"policy-observer"},"1"},
        [](const StrategyRequest&,const Requirements&) -> Capability { return Offer{}; },
        [](const StrategyRequest&,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
            return compose_strategy(std::get<0>(check_pipeline()),
                [](auto,const StrategyRequest&,const Requirements&) {
                    return std::make_unique<PolicyObservingWorkspace>();
                });
        }}));
    auto request=strategy_request();
    request.configuration.strategy={"policy-observer"};
    request.family.numerical={0.125,0.25};
    auto prepared=strategies.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(prepared));
    auto workspace=std::get<PreparedStrategy>(std::move(prepared)).create();

    auto mismatched=context();
    mismatched.numerical={0.5,0.25};
    const auto rejected=workspace->run(mismatched);
    REQUIRE(std::holds_alternative<Unsupported>(rejected));
    REQUIRE(std::get<Unsupported>(rejected).diagnostics.size()==1);
    CHECK(std::get<Unsupported>(rejected).diagnostics[0].code==DiagnosticCode::invalid_input);
    CHECK(std::get<Unsupported>(rejected).diagnostics[0].field=="family.numerical");

    auto matching=context();
    matching.numerical={0.125,0.25};
    const auto accepted=workspace->run(matching);
    REQUIRE(std::holds_alternative<SynthesisResult>(accepted));
    const auto& result=std::get<SynthesisResult>(accepted);
    REQUIRE(result.objective.upper.has_value());
    const auto* observed=std::get_if<NumericalCheck>(&result.objective.upper->evidence.support);
    REQUIRE(observed!=nullptr);
    CHECK(observed->absolute_tolerance==0.125);
    CHECK(observed->relative_tolerance==0.25);
    CHECK(observed->max_residual==0);
    CHECK(observed->verifier.value=="policy-observer");
}

TEST_CASE("scoped provider provenance is checked without erasing retained evidence") {
    class RetainedWorkspace final : public SynthesisWorkspace {
    public:
        RequestProvenance provenance{{"generated/geometry/8"},"geometry",{"provider"},std::string{"2"},
            ModuleId{"provider"},std::string{"2"}};
        bool rejected{true};
        StopReason reason{StopReason::numerical_failure};
        SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest& request,
            const ExecutionContext&) override {
            const auto id=problem.identity();
            const ClaimEvidence support{id,SymbolicArgument{"synthetic retained evidence","literal fixture only"}};
            const std::vector<TransformStepIdentity> lineage{{{"transform/1"},{"source"},{"relation"},{"converter"},"1"}};
            const FamilyIdentity identity{id,request,problem.constraints().coordinates(),{"forward"},"1",lineage};
            const JointRelation relation{identity.coordinates,request.representation,std::make_shared<const JointRelationPayload>()};
            auto family=std::get<OptimalFamily>(FamilyPublisher::publish(identity,CandidateFamily{
                relation,HeuristicRelationEvidence{"synthetic retained relation"},Unestablished{}}));
            SynthesisResult result{Termination::operation_rejected,
                {id,MathematicalOutcome::undetermined,Unestablished{},{}},
                {ObjectiveBound{0,support},ObjectiveBound{5,support}},std::move(family),
                {{{id,{{0},{1}},{{1}},5},support}},{{0,{},ModuleId{"forward"},0,1}}};
            if (rejected)
                result.stop=ScopedRequestRejection{provenance,
                    {{DiagnosticCode::unsupported,"geometry.generated","literal provider rejection"}},lineage,
                    {true,true,1,true}};
            else {
                result.termination=reason==StopReason::resource_limit?Termination::resource_limit:
                    reason==StopReason::numerical_failure?Termination::numerical_failure:Termination::cancelled;
                result.stop=ScopedOperationStopped{{reason,"literal provider stop"},provenance,{true,true,1,true}};
            }
            return result;
        }
    };
    auto request=strategy_request();request.strategy_version="1";
    const RequestProvenance full{{"generated/geometry/8"},"geometry",{"provider"},std::string{"2"},
        ModuleId{"provider"},std::string{"2"}};
    auto unknown=full;unknown.actual_module.reset();unknown.actual_version.reset();
    RetainedWorkspace workspace;workspace.provenance=unknown;
    const auto admitted=StrategyPort::run(workspace,request,context());
    REQUIRE(std::holds_alternative<SynthesisResult>(admitted));
    const auto& original=std::get<SynthesisResult>(admitted);
    CHECK(original.termination==Termination::operation_rejected);
    REQUIRE(original.family);
    const auto saved_identity=original.family->identity();
    REQUIRE(std::holds_alternative<ScopedRequestRejection>(original.stop));
    CHECK_FALSE(std::get<ScopedRequestRejection>(original.stop).request.actual_module);
    std::vector<RequestProvenance> malformed;
    auto add=[&](auto mutation){auto p=full;mutation(p);malformed.push_back(std::move(p));};
    add([](auto& p){p.requested_module.value.clear();});
    add([](auto& p){p.requested_version=std::string{};});
    add([](auto& p){p.actual_module.reset();});
    add([](auto& p){p.actual_version.reset();});
    add([](auto& p){p.actual_module=ModuleId{};});
    add([](auto& p){p.actual_version=std::string{};});
    for (const auto is_rejection:{true,false}) {
        workspace.rejected=is_rejection;
        for (const auto& provenance:malformed) {
            workspace.provenance=provenance;
            const auto answer=StrategyPort::run(workspace,request,context());
            REQUIRE(std::holds_alternative<SynthesisResult>(answer));
            const auto& result=std::get<SynthesisResult>(answer);
            CHECK(result.termination==Termination::contract_rejected);
            REQUIRE(std::holds_alternative<ContractValidationFailure>(result.stop));
            const auto& failure=std::get<ContractValidationFailure>(result.stop);
            CHECK(std::any_of(failure.diagnostics.begin(),failure.diagnostics.end(),[](const auto& d){
                return d.field=="result.stop.provenance" && d.code==DiagnosticCode::invalid_claim;
            }));
            REQUIRE(result.family);
            CHECK(result.family->identity()==saved_identity);
            CHECK(result.family->target()==FamilyTarget::candidate_relaxation);
            REQUIRE(result.objective.lower);CHECK(result.objective.lower->value==0);
            REQUIRE(result.objective.upper);CHECK(result.objective.upper->value==5);
            REQUIRE(result.incumbents.size()==1);CHECK(result.incumbents[0].witness.original_objective==5);
            REQUIRE(result.spans.size()==1);CHECK(result.spans[0].end_seconds==1);
            CHECK(failure.retained.lower_bound);CHECK(failure.retained.upper_bound);
            CHECK(failure.retained.incumbents==1);CHECK(failure.retained.partial_or_candidate_family);
            const auto& source=std::visit([](const auto& stop)->const RequestProvenance&{
                using T=std::decay_t<decltype(stop)>;
                if constexpr(std::is_same_v<T,std::monostate>) throw std::logic_error("missing source stop");
                else return stop.request;
            },failure.source_stop);
            CHECK(source.request.value=="generated/geometry/8");CHECK(source.port=="geometry");
            CHECK(source.requested_module==provenance.requested_module);
            CHECK(source.requested_version==provenance.requested_version);
            CHECK(source.actual_module==provenance.actual_module);CHECK(source.actual_version==provenance.actual_version);
            if (is_rejection) {
                REQUIRE(std::holds_alternative<ScopedRequestRejection>(failure.source_stop));
                const auto& stopped=std::get<ScopedRequestRejection>(failure.source_stop);
                CHECK(stopped.completed_lineage==saved_identity.lineage);
                REQUIRE(stopped.diagnostics.size()==1);
                CHECK(stopped.diagnostics[0].explanation=="literal provider rejection");
            } else {
                REQUIRE(std::holds_alternative<ScopedOperationStopped>(failure.source_stop));
                CHECK(std::get<ScopedOperationStopped>(failure.source_stop).stop.reason==StopReason::numerical_failure);
            }
        }
    }
    workspace.provenance=full;workspace.rejected=false;
    for (const auto reason:{StopReason::cancelled,StopReason::deadline_expired,StopReason::resource_limit,StopReason::numerical_failure}) {
        workspace.reason=reason;
        const auto answer=StrategyPort::run(workspace,request,context());
        REQUIRE(std::holds_alternative<SynthesisResult>(answer));
        const auto& result=std::get<SynthesisResult>(answer);
        REQUIRE(std::holds_alternative<ScopedOperationStopped>(result.stop));
        CHECK(std::get<ScopedOperationStopped>(result.stop).stop.reason==reason);
        REQUIRE(result.family);CHECK(result.family->identity()==saved_identity);
        REQUIRE(result.objective.lower);CHECK(result.objective.lower->value==0);
        REQUIRE(result.objective.upper);CHECK(result.objective.upper->value==5);
        REQUIRE(result.incumbents.size()==1);CHECK(result.incumbents[0].witness.original_objective==5);
    }
    CHECK(original.termination==Termination::operation_rejected);
    CHECK(original.family->identity()==saved_identity);
}

TEST_CASE("configuration selects two working bounded LP algorithms") {
    Registry<LPPort> registry;
    REQUIRE_FALSE(registry.add(endpoint_registration()).has_value());
    REQUIRE_FALSE(registry.add(sign_registration()).has_value());
    for (const auto& id : {"endpoint", "sign"}) {
        auto request = interval_lp(3);
        auto result = prepare_pipeline(select(registry, Method{{id}, {}}, request));
        REQUIRE(std::holds_alternative<PreparedPipeline<LPPort>>(result));
        auto plan = std::get<PreparedPipeline<LPPort>>(std::move(result));
        CHECK(plan.provenance()[0].requested.id.value == id);
        REQUIRE(plan.provenance()[0].actual.has_value());
        CHECK(plan.provenance()[0].actual->id.value == id);
        CHECK(plan.provenance()[0].actual->version == (std::string(id) == "endpoint" ? "1.0" : "2.0"));
        auto workspaces = plan.create();
        auto answer = std::get<0>(workspaces)->run(context());
        REQUIRE(std::holds_alternative<ProgramResult>(answer));
        const auto& solved = std::get<ProgramResult>(answer);
        CHECK(solved.primal == std::optional<Vector>{{-1}});
        REQUIRE(solved.objective.upper.has_value());
        CHECK(solved.objective.upper->value == -1);
    }
}

TEST_CASE("negative and zero coefficients and genuinely unsupported LPs") {
    Registry<LPPort> registry;
    registry.add(endpoint_registration()); registry.add(sign_registration());
    for (const auto& id : {"endpoint","sign"}) {
        for (const auto coefficient : {-2.0,0.0}) {
            const auto request = interval_lp(coefficient);
            auto result = prepare_pipeline(select(registry,Method{{id},{}},request));
            REQUIRE(std::holds_alternative<PreparedPipeline<LPPort>>(result));
            auto workers = std::get<PreparedPipeline<LPPort>>(result).create();
            const auto answer = std::get<0>(workers)->run(context());
            REQUIRE(std::holds_alternative<ProgramResult>(answer));
            const auto& solved = std::get<ProgramResult>(answer);
            CHECK(solved.primal == (coefficient < 0 ? std::optional<Vector>{{4}} : std::optional<Vector>{{-1}}));
            CHECK(solved.objective.upper->value == (coefficient < 0 ? -6 : 2));
        }
        auto input = interval_input(3);
        input.variables[0].upper.reset();
        const auto request = publish(input);
        auto result = prepare_pipeline(select(registry,Method{{id},{}},request));
        REQUIRE(std::holds_alternative<Rejection>(result));
        const auto& rejection = std::get<Rejection>(result);
        CHECK(rejection.provenance.actual->id.value == id);
        CHECK(rejection.diagnostics[0].field == "lp.domain");
    }
}

TEST_CASE("bounded LP preflight rejects overflow and rounded unequal endpoint ties before factories") {
    std::array<int,2> factories{};
    Registry<LPPort> registry;
    auto endpoint = endpoint_registration();
    endpoint.factory = [&](const LinearProgram&) { ++factories[0]; return std::make_unique<EndpointWorkspace>(); };
    auto sign = sign_registration();
    sign.factory = [&](const LinearProgram&) { ++factories[1]; return std::make_unique<SignWorkspace>(); };
    registry.add(endpoint); registry.add(sign);
    auto overflow = interval_input(-std::numeric_limits<double>::max());
    overflow.variables[0] = {2,3};
    auto rounded_tie = interval_input(-1); rounded_tie.offset = 1e20;
    auto underflow = interval_input(std::numeric_limits<double>::denorm_min());
    underflow.variables[0] = {0,0.5}; underflow.offset = 0;
    for (const auto& input : {overflow,rounded_tie,underflow}) {
        const auto request = publish(input);
        for (const auto& id : {"endpoint","sign"}) {
            CAPTURE(std::string(id)); CAPTURE(request.objective()[0]); CAPTURE(request.offset());
            auto result = prepare_pipeline(select(registry,Method{{id},{}},request));
            CHECK(std::holds_alternative<Rejection>(result));
            if (!std::holds_alternative<Rejection>(result)) continue;
            const auto& rejection = std::get<Rejection>(result);
            CHECK(rejection.provenance.requested.id.value == id);
            CHECK(rejection.provenance.actual->id.value == id);
            CHECK(rejection.provenance.actual->version == (std::string(id)=="endpoint" ? "1.0" : "2.0"));
            CHECK(rejection.diagnostics[0].code == DiagnosticCode::unsupported);
            CHECK(rejection.diagnostics[0].field == "lp.arithmetic");
            CHECK_FALSE(rejection.diagnostics[0].explanation.empty());
            CHECK(factories == std::array<int,2>{0,0});
        }
    }
}

TEST_CASE("constant objectives and degenerate intervals remain legitimate bounded LP inputs") {
    Registry<LPPort> registry;
    registry.add(endpoint_registration()); registry.add(sign_registration());
    auto constant = interval_input(0); constant.offset = 1e20;
    auto degenerate = interval_input(-1); degenerate.variables[0] = {4,4}; degenerate.offset = 1e20;
    for (const auto& id : {"endpoint","sign"}) {
        for (const auto& input : {constant,degenerate}) {
            const auto request = publish(input);
            auto result = prepare_pipeline(select(registry,Method{{id},{}},request));
            REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
            auto workers = std::get<0>(result).create();
            const auto answer = std::get<ProgramResult>(std::get<0>(workers)->run(context()));
            CHECK(answer.primal == (request.objective()[0] == 0 ? std::optional<Vector>{{-1}} : std::optional<Vector>{{4}}));
            CHECK(answer.objective.upper->value == 1e20);
            CHECK(answer.outcome.value == MathematicalOutcome::optimal);
        }
    }
}

TEST_CASE("snapshots retain full requests after source exit and workspaces mutate independently") {
    auto plan = [] {
        Registry<LPPort> registry;
        registry.add(endpoint_registration());
        auto input = interval_input(3);
        const auto request = publish(input);
        auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request));
        auto prepared = std::get<PreparedPipeline<LPPort>>(std::move(result));
        input.objective[0] = -200;
        input.variables[0] = {100,200};
        return prepared;
    }();
    auto first = plan.create(), second = plan.create();
    auto a = std::get<ProgramResult>(std::get<0>(first)->run(context()));
    auto b = std::get<ProgramResult>(std::get<0>(first)->run(context()));
    auto c = std::get<ProgramResult>(std::get<0>(second)->run(context()));
    CHECK(a.raw_diagnostics == "1"); CHECK(b.raw_diagnostics == "2"); CHECK(c.raw_diagnostics == "1");
    CHECK(b.primal == std::optional<Vector>{{-1}}); CHECK(c.objective.upper->value == -1);
}

TEST_CASE("unsupported requested profiles reject before factories with actual provenance") {
    int factories = 0;
    Registry<LPPort> registry;
    auto entry = endpoint_registration();
    entry.factory = [&](const LinearProgram&) { ++factories; return std::make_unique<EndpointWorkspace>(); };
    registry.add(entry);
    const auto request = interval_lp(3);
    std::vector<std::pair<Requirements,std::string>> cases;
    Requirements scalar; scalar.scalar = Scalar::exact; cases.push_back({scalar,"scalar"});
    Requirements representation; representation.output.representation = {"unsupported"}; cases.push_back({representation,"output.representation"});
    Requirements assurance; assurance.output.assurance = Assurance::validated; cases.push_back({assurance,"output.assurance"});
    Requirements relation; relation.output.relation = SetRelation::equivalent; cases.push_back({relation,"output.relation"});
    Requirements family; family.output.family = FamilyTarget::exact_optimal_relation; cases.push_back({family,"output.family"});
    Requirements basis; basis.basis_diagnostics = true; cases.push_back({basis,"basis"});
    for (const auto& [requirements, field] : cases) {
        auto result = prepare_pipeline(select(registry,Method{{"endpoint"},"1.0"},request,requirements));
        REQUIRE(std::holds_alternative<Rejection>(result));
        const auto& rejection = std::get<Rejection>(result);
        CHECK(rejection.provenance.requested.id.value == "endpoint");
        CHECK(rejection.provenance.actual->id.value == "endpoint");
        CHECK(rejection.provenance.actual->version == "1.0");
        CHECK(rejection.diagnostics[0].field == field);
        CHECK_FALSE(rejection.diagnostics[0].explanation.empty());
        CHECK(factories == 0);
    }
}

TEST_CASE("unknown duplicate and version mismatch retain requested and resolved identities") {
    Registry<LPPort> registry;
    registry.add(endpoint_registration());
    auto duplicate = endpoint_registration(); duplicate.identity.version = "9.0";
    const auto rejected = registry.add(duplicate);
    REQUIRE(rejected.has_value());
    CHECK(rejected->provenance.requested.version == "9.0");
    CHECK(rejected->provenance.actual->version == "1.0");
    const auto request = interval_lp(3);
    auto unknown = prepare_pipeline(select(registry,Method{{"missing"},"7"},request));
    REQUIRE(std::holds_alternative<Rejection>(unknown));
    CHECK_FALSE(std::get<Rejection>(unknown).provenance.actual.has_value());
    CHECK(std::get<Rejection>(unknown).provenance.requested.id.value == "missing");
    auto version = prepare_pipeline(select(registry,Method{{"endpoint"},"2.0"},request));
    REQUIRE(std::holds_alternative<Rejection>(version));
    CHECK(std::get<Rejection>(version).provenance.actual->version == "1.0");
}

TEST_CASE("downstream transition rejects before any workspace exists") {
    int factories = 0;
    Registry<LPPort> registry;
    auto entry = endpoint_registration();
    entry.factory = [&](const LinearProgram&) { ++factories; return std::make_unique<EndpointWorkspace>(); };
    registry.add(entry);
    const auto request = interval_lp(3);
    Output unavailable; unavailable.representation = {"unavailable"};
    auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request),
        select(registry,Method{{"endpoint"},{}},request,{},{{0,unavailable}}));
    REQUIRE(std::holds_alternative<Rejection>(result));
    CHECK(std::get<Rejection>(result).provenance.actual->id.value == "endpoint");
    CHECK(std::get<Rejection>(result).diagnostics[0].field == "transition.representation");
    CHECK(factories == 0);
}

TEST_CASE("registered strategy planners hide tuple types from the configuration-only caller") {
    Registry<LPPort> lp;
    lp.add(endpoint_registration()); lp.add(sign_registration());
    StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(forward_registration(lp)).has_value());
    REQUIRE_FALSE(strategies.add(forward_registration(lp,"second-forward")).has_value());
    for (const auto& strategy : {"forward","second-forward"}) {
        for (const auto& backend : {"endpoint","sign"}) {
            auto request = strategy_request();
            request.configuration.strategy = {strategy}; request.configuration.lp = {backend};
            auto result = strategies.prepare(request);
            REQUIRE(std::holds_alternative<PreparedStrategy>(result));
            auto plan = std::get<PreparedStrategy>(std::move(result));
            CHECK(plan.provenance()[0].actual->id.value == strategy);
            CHECK(plan.provenance()[1].actual->id.value == backend);
            auto workspace = plan.create();
            auto answer = workspace->run(context());
            REQUIRE(std::holds_alternative<SynthesisResult>(answer));
            const auto& solved = std::get<SynthesisResult>(answer);
            CHECK(solved.incumbents[0].witness.controls == std::vector<Vector>{{-1}});
            CHECK(solved.incumbents[0].witness.original_objective == -1);
            CHECK_FALSE(solved.family.has_value());
        }
    }
}

TEST_CASE("all existing ports execute through typed factories and rejection constructs none") {
    AllPorts ports;
    Requirements invalid; invalid.scalar = Scalar::interval;
    auto rejected = ports.prepare(invalid);
    REQUIRE(std::holds_alternative<Rejection>(rejected));
    CHECK(std::get<Rejection>(rejected).provenance.actual->id.value == "strategy");
    CHECK(std::get<Rejection>(rejected).diagnostics[0].field == "scalar");
    CHECK(ports.factories == std::array<int,7>{0,0,0,0,0,0,0});
    auto result = ports.prepare();
    REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
    auto workers = std::get<0>(result).create();
    CHECK(std::get<ProgramResult>(std::get<0>(workers)->run(context())).objective.upper->value == -1);
    CHECK(std::get<ProgramResult>(std::get<1>(workers)->run(context())).raw_diagnostics == "interval");
    CHECK(std::get<OperationStopped>(std::get<2>(workers)->run(context())).diagnostics == "geometry-request");
    CHECK(std::get<OperationStopped>(std::get<3>(workers)->run(context())).diagnostics == "vertices");
    CHECK(std::get<OperationStopped>(std::get<4>(workers)->run(context())).diagnostics == "17");
    CHECK(std::get<WitnessSelection>(std::get<5>(workers)->run(context())).batch.requested == 3);
    CHECK(std::get<SynthesisResult>(std::get<6>(workers)->run(context())).incumbents[0].witness.original_objective == 2);
    CHECK(ports.factories == std::array<int,7>{1,1,1,1,1,1,1});
}

TEST_CASE("optional basis is executable only when requested") {
    Registry<LPPort> registry;
    auto entry = endpoint_registration();
    entry.basis_factory = [](const LinearProgram&,LPWorkspace&) { return std::make_unique<BasisFixture>(); };
    registry.add(entry);
    Requirements requirements; requirements.basis_diagnostics = true;
    const auto request = interval_lp(3);
    auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request,requirements));
    REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
    auto workers = std::get<0>(result).create();
    REQUIRE(std::get<0>(workers)->basis() != nullptr);
    CHECK(std::get<0>(workers)->basis()->describe_basis() == "fixture basis: column 0");
    CHECK(std::get<ProgramResult>(std::get<0>(workers)->run(context())).primal == std::optional<Vector>{{-1}});
}

TEST_CASE("basis diagnostics observe their own LP workspace after the prepared plan exits") {
    struct StatefulLP final : LPWorkspace {
        int calls{};
        std::shared_ptr<std::vector<std::string>> destruction;
        explicit StatefulLP(std::shared_ptr<std::vector<std::string>> log) : destruction(std::move(log)) {}
        ~StatefulLP() override { destruction->push_back("workspace"); }
        ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext&) override {
            ++calls;
            return ProgramResult{Termination::completed,{p.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},
                {},{},std::to_string(calls)};
        }
    };
    struct BoundBasis final : BasisDiagnostics {
        const StatefulLP& workspace;
        explicit BoundBasis(const StatefulLP& w) : workspace(w) {}
        ~BoundBasis() override { workspace.destruction->push_back("basis@"+std::to_string(workspace.calls)); }
        BasisCapabilities capabilities() const override { return {true,false,false}; }
        BasisSnapshotResult snapshot() const override {
            if(!workspace.last_attempt()) return BasisUnavailable{BasisUnavailableReason::not_solved,"no attempt"};
            return BasisSnapshot{{workspace.last_attempt()->stamp,0},{},{}};
        }
        std::string describe_basis() const override { return "solve "+std::to_string(workspace.calls); }
    };
    struct ConnectBasis {
        std::unique_ptr<BasisDiagnostics> operator()(const LinearProgram&,LPWorkspace& workspace) const {
            return std::make_unique<BoundBasis>(dynamic_cast<const StatefulLP&>(workspace));
        }
    };
    const auto destruction = std::make_shared<std::vector<std::string>>();
    auto workers = [&] {
        Registry<LPPort> registry;
        auto entry = endpoint_registration();
        entry.factory = [destruction](const LinearProgram&) { return std::make_unique<StatefulLP>(destruction); };
        entry.basis_factory = ConnectBasis{};
        registry.add(entry);
        const auto request = interval_lp(3);
        Requirements requirements; requirements.basis_diagnostics = true;
        auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request,requirements));
        REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
        const auto& plan = std::get<0>(result);
        return std::pair{plan.create(),plan.create()};
    }();
    auto& first = std::get<0>(workers.first);
    auto& second = std::get<0>(workers.second);
    REQUIRE(first->basis()); REQUIRE(second->basis());
    CHECK(first->basis()->describe_basis() == "solve 0");
    CHECK(std::get<ProgramResult>(first->run(context())).raw_diagnostics == "1");
    CHECK(first->basis()->describe_basis() == "solve 1");
    CHECK(second->basis()->describe_basis() == "solve 0");
    CHECK(std::get<ProgramResult>(first->run(context())).raw_diagnostics == "2");
    CHECK(first->basis()->describe_basis() == "solve 2");
    first.reset();
    CHECK(*destruction == std::vector<std::string>{"basis@2","workspace"});
    CHECK(std::get<ProgramResult>(second->run(context())).raw_diagnostics == "1");
    CHECK(second->basis()->describe_basis() == "solve 1");
    second.reset();
    CHECK(*destruction == std::vector<std::string>{"basis@2","workspace","basis@1","workspace"});

    destruction->clear();
    Registry<LPPort> throwing_registry;
    auto throwing_entry = endpoint_registration();
    throwing_entry.factory = [destruction](const LinearProgram&) { return std::make_unique<StatefulLP>(destruction); };
    throwing_entry.basis_factory = [](const LinearProgram& request,LPWorkspace& workspace) -> std::unique_ptr<BasisDiagnostics> {
        auto diagnostic = ConnectBasis{}(request,workspace);
        throw std::runtime_error("basis connection failure");
    };
    throwing_registry.add(throwing_entry);
    const auto request = interval_lp(3);
    Requirements requirements; requirements.basis_diagnostics = true;
    auto result = prepare_pipeline(select(throwing_registry,Method{{"endpoint"},{}},request,requirements));
    REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
    CHECK_THROWS_WITH_AS(std::get<0>(result).create(),"basis connection failure",std::runtime_error);
    CHECK(*destruction == std::vector<std::string>{"basis@0","workspace"});
}

TEST_CASE("a null LP factory fails before invoking a basis connection") {
    struct CountConnection {
        int& calls;
        std::unique_ptr<BasisDiagnostics> operator()(const LinearProgram&,LPWorkspace&) const {
            ++calls; return std::make_unique<BasisFixture>();
        }
    };
    int connections = 0;
    Registry<LPPort> registry;
    auto entry = endpoint_registration();
    entry.factory = [](const LinearProgram&) -> std::unique_ptr<LPWorkspace> { return {}; };
    entry.basis_factory = CountConnection{connections};
    registry.add(entry);
    const auto request = interval_lp(3);
    Requirements requirements; requirements.basis_diagnostics = true;
    auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request,requirements));
    REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
    CHECK_THROWS_WITH_AS(std::get<0>(result).create(),"registered factory returned a null workspace",std::logic_error);
    CHECK(connections == 0);
}

TEST_CASE("a custom port extends registry without product dispatch and freezes only after acceptance") {
    const auto snapshots = std::make_shared<int>(0);
    auto plan = [&] {
        Registry<CounterPort> registry;
        int source_configuration = 10;
        const auto configuration = std::make_shared<const int>(source_configuration);
        registry.add({{{"counter"},"3"},[](const CounterRequest&,const Requirements&) -> Capability { return Offer{}; },
            [configuration](const CounterRequest&) { return std::make_unique<CounterFixture>(*configuration); }});
        CounterRequest request{20,snapshots};
        Registry<LPPort> lp; lp.add(endpoint_registration());
        auto input = interval_input(3); input.variables[0].upper.reset();
        const auto unsupported = publish(input);
        auto rejection = prepare_pipeline(select(registry,Method{{"counter"},{}},request),select(lp,Method{{"endpoint"},{}},unsupported));
        REQUIRE(std::holds_alternative<Rejection>(rejection));
        CHECK(std::get<Rejection>(rejection).provenance.actual->id.value == "endpoint");
        CHECK(*snapshots == 0);
        auto result = prepare_pipeline(select(registry,Method{{"counter"},{}},request));
        REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
        source_configuration = 999; request.value = 800;
        CHECK(source_configuration == 999);
        return std::get<0>(std::move(result));
    }();
    CHECK(*snapshots == 1);
    auto first = plan.create(), second = plan.create();
    CHECK(std::get<0>(first)->run(context()) == 31);
    CHECK(std::get<0>(first)->run(context()) == 32);
    CHECK(std::get<0>(second)->run(context()) == 31);
}

TEST_CASE("strategy snapshots copy mutable model aliases and authored objective values") {
    auto plan = [] {
        Registry<StrategyPort> registry;
        registry.add({{{"capture"},"1"},[](const StrategyRequest&,const Requirements&) -> Capability { return Offer{}; },
            [](const StrategyRequest&) { return std::make_unique<StrategyFixture>(); }});
        auto request = strategy_request();
        auto raw = *request.problem.description();
        auto model = std::make_shared<SystemModel>(*raw.model);
        raw.model = model;
        request.problem = std::get<csl::problem::ResolvedProblem>(csl::problem::resolve(raw,{csl::problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
        request.family.objective=request.problem.identity();
        auto result = prepare_pipeline(select(registry,Method{{"capture"},{}},request));
        std::get<LinearStage>(model->dynamics.stages).offset[0] = 999;
        std::get<LinearTerminal>(raw.objective).offset = 888;
        return std::get<0>(std::move(result));
    }();
    auto workers = plan.create();
    const auto solved = std::get<SynthesisResult>(std::get<0>(workers)->run(context()));
    CHECK(solved.incumbents[0].witness.states == std::vector<Vector>{{0},{0}});
    CHECK(solved.incumbents[0].witness.original_objective == 2);
}

TEST_CASE("T-M03 unsupported profiles stay capability rejection rather than infeasibility") {
    Registry<LPPort> lp; lp.add(endpoint_registration());
    StrategyRegistry registry; registry.add(forward_registration(lp));
    auto inverse = forward_registration(lp,"inverse");
    inverse.capabilities = [](const StrategyRequest& r,const Requirements& requirements) -> Capability {
        return check_nominal_profile(*r.problem.description(),true,requirements.output.assurance);
    };
    registry.add(inverse);
    auto request = strategy_request();
    REQUIRE(check_model_shape(request.problem.description()->model->dynamics,1).empty());
    auto forward = registry.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(forward));
    CHECK(std::get<SynthesisResult>(std::get<PreparedStrategy>(forward).create()->run(context())).incumbents[0].witness.original_objective == -1);
    std::vector<std::pair<StrategyRequest,std::string>> cases;
    auto modified = request; modified.configuration.strategy = {"inverse"}; cases.push_back({modified,"dynamics.inverse"});
    auto add_case=[&](const Problem& raw,const char* field) {
        auto resolution=csl::problem::resolve(raw,{csl::problem::UncertaintyStructure::stage_product_uncoupled,{},{}});
        if (auto* diagnostic=std::get_if<Diagnostic>(&resolution)) {
            CHECK((diagnostic->code==DiagnosticCode::unsupported || diagnostic->code==DiagnosticCode::invalid_input));
            CHECK_FALSE(diagnostic->field.empty());
            return;
        }
        auto input=request;
        input.problem=std::get<csl::problem::ResolvedProblem>(std::move(resolution));
        input.family.objective=input.problem.identity();
        cases.push_back({std::move(input),field});
    };
    auto raw=*request.problem.description(); raw.controls = FiniteDomain{1,{{0},{1}}}; add_case(raw,"controls");
    raw=*request.problem.description(); raw.controls = MixedDomain{ContinuousDomain{{UniversalSet{0}}},FiniteDomain{1,{{0}}}}; add_case(raw,"controls");
    raw=*request.problem.description(); raw.information = InformationPattern::feedback; add_case(raw,"information");
    raw=*request.problem.description(); raw.temporal = TemporalConstraints{{1,1,{0,1},{0},{1}},{{0,1}}}; add_case(raw,"temporal");
    raw=*request.problem.description(); auto continuous = std::make_shared<SystemModel>(*raw.model);
    continuous->dynamics.time_domain = TimeDomain::continuous; raw.model = continuous; add_case(raw,"time_domain");
    raw=*request.problem.description(); raw.objective = ResidualNormTerminal{{1,1,{1}},{0}}; add_case(raw,"objective");
    raw=*request.problem.description(); raw.controls = ContinuousDomain{{SetHandle{{1,{"poly"},SetProperty::unknown,SetProperty::yes,SetProperty::unknown},{},{"unknown"}}}}; add_case(raw,"controls");
    for (const auto& [input,field] : cases) {
        auto result = registry.prepare(input);
        REQUIRE(std::holds_alternative<Rejection>(result));
        const auto& rejection = std::get<Rejection>(result);
        CHECK(rejection.provenance.actual->id.value == input.configuration.strategy.value);
        CHECK(rejection.provenance.actual->version == "fixture-1");
        CHECK(rejection.diagnostics[0].field == field);
        CHECK(rejection.diagnostics[0].code == DiagnosticCode::unsupported);
    }
}

TEST_CASE("exact family target and equivalent relation cannot establish completeness") {
    Registry<LPPort> registry;
    auto entry = endpoint_registration();
    entry.capabilities = [](const LinearProgram&,const Requirements&) -> Capability {
        Output output; output.family = FamilyTarget::exact_optimal_relation;
        output.relation = SetRelation::equivalent; output.completeness = Completeness::unestablished;
        return Offer{output};
    };
    registry.add(entry);
    Requirements requirements; requirements.output.family = FamilyTarget::exact_optimal_relation;
    requirements.output.relation = SetRelation::equivalent; requirements.output.completeness = Completeness::established;
    const auto request = interval_lp(3);
    auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request,requirements));
    REQUIRE(std::holds_alternative<Rejection>(result));
    CHECK(std::get<Rejection>(result).provenance.actual->version == "1.0");
    CHECK(std::get<Rejection>(result).diagnostics[0].field == "output.completeness");
}

TEST_CASE("a required unavailable hull execution rejects while unused hull selection stays optional") {
    Registry<LPPort> lp; lp.add(endpoint_registration());
    StrategyRegistry strategies;
    strategies.add(forward_registration(lp));
    auto hull = forward_registration(lp,"needs-hull");
    hull.planner = [](const StrategyRequest& r,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
        return Rejection{{"hull",{r.configuration.hull,{}},{}},
            {{DiagnosticCode::unsupported,"hull","no executable hull port exists in revision 1.1"}}};
    };
    strategies.add(hull);
    auto request = strategy_request();
    auto accepted = strategies.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(accepted));
    CHECK(std::get<SynthesisResult>(std::get<PreparedStrategy>(accepted).create()->run(context())).incumbents[0].witness.original_objective == -1);
    request.configuration.strategy = {"needs-hull"};
    auto rejected = strategies.prepare(request);
    REQUIRE(std::holds_alternative<Rejection>(rejected));
    CHECK(std::get<Rejection>(rejected).provenance.port == "hull");
    CHECK(std::get<Rejection>(rejected).provenance.requested.id.value == "unused-hull");
    CHECK_FALSE(std::get<Rejection>(rejected).provenance.actual.has_value());
    CHECK(std::get<Rejection>(rejected).diagnostics[0].field == "hull");
}

TEST_CASE("workspace creation failure cleans every earlier unique workspace") {
    struct Tracked final : CounterWorkspace {
        int& alive;
        explicit Tracked(int& count) : alive(count) { ++alive; }
        ~Tracked() override { --alive; }
        int evaluate(const CounterRequest& r) override { return r.value; }
    };
    int alive = 0, attempted = 0, observed_alive = 0;
    Registry<CounterPort> registry;
    auto capability = [](const CounterRequest&,const Requirements&) -> Capability { return Offer{}; };
    registry.add({{{"first"},"1"},capability,[&](const CounterRequest&) { return std::make_unique<Tracked>(alive); }});
    registry.add({{{"throws"},"1"},capability,[&](const CounterRequest&) -> std::unique_ptr<CounterWorkspace> {
        ++attempted; observed_alive = alive; throw std::runtime_error("factory failure");
    }});
    const CounterRequest request{7,std::make_shared<int>(0)};
    auto result = prepare_pipeline(select(registry,Method{{"first"},{}},request),select(registry,Method{{"throws"},{}},request));
    REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
    CHECK_THROWS_WITH_AS(std::get<0>(result).create(),"factory failure",std::runtime_error);
    CHECK(attempted == 1); CHECK(observed_alive == 1); CHECK(alive == 0);
}

TEST_CASE("empty diagnostic rejection cannot lose an actionable reason") {
    Registry<LPPort> registry;
    auto entry = endpoint_registration();
    entry.capabilities = [](const LinearProgram&,const Requirements&) -> Capability { return Diagnostics{}; };
    registry.add(entry);
    const auto request = interval_lp(3);
    auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request));
    REQUIRE(std::holds_alternative<Rejection>(result));
    CHECK_FALSE(std::get<Rejection>(result).diagnostics.empty());
}

TEST_CASE("all-port factory counts stay zero across capability and registration rejection classes") {
    AllPorts ports;
    std::vector<std::pair<Requirements,std::string>> cases;
    Requirements r; r.output.representation = {"unavailable"}; cases.push_back({r,"output.representation"});
    r = {}; r.scalar = Scalar::binary32; cases.push_back({r,"scalar"});
    r = {}; r.output.assurance = Assurance::validated; cases.push_back({r,"output.assurance"});
    r = {}; r.output.relation = SetRelation::inner; cases.push_back({r,"output.relation"});
    r = {}; r.output.family = FamilyTarget::exact_optimal_relation; cases.push_back({r,"output.family"});
    r = {}; r.output.completeness = Completeness::established; cases.push_back({r,"output.completeness"});
    r = {}; r.basis_diagnostics = true; cases.push_back({r,"basis"});
    for (const auto& [requirements,field] : cases) {
        auto result = ports.prepare(requirements);
        REQUIRE(std::holds_alternative<Rejection>(result));
        CHECK(std::get<Rejection>(result).provenance.actual->id.value == "strategy");
        CHECK(std::get<Rejection>(result).diagnostics[0].field == field);
        CHECK(ports.factories == std::array<int,7>{0,0,0,0,0,0,0});
    }
    auto raw=*ports.strategy_request_value.problem.description();
    raw.objective = ResidualNormTerminal{{1,1,{1}},{0}};
    ports.strategy_request_value.problem=std::get<csl::problem::ResolvedProblem>(csl::problem::resolve(raw,{csl::problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    ports.strategy_request_value.family.objective=ports.strategy_request_value.problem.identity();
    auto objective = ports.prepare();
    REQUIRE(std::holds_alternative<Rejection>(objective));
    CHECK(std::get<Rejection>(objective).diagnostics[0].field == "objective");
    ports.strategy_request_value = strategy_request();
    auto unknown = ports.prepare({},{{"unknown"},{}});
    REQUIRE(std::holds_alternative<Rejection>(unknown));
    CHECK_FALSE(std::get<Rejection>(unknown).provenance.actual.has_value());
    auto duplicate = ports.lp.add(endpoint_registration());
    REQUIRE(duplicate.has_value()); CHECK(duplicate->provenance.actual->id.value == "endpoint");
    Output mismatch; mismatch.relation = SetRelation::outer;
    auto transition = ports.prepare({},{{"endpoint"},{}},{{3,mismatch}});
    REQUIRE(std::holds_alternative<Rejection>(transition));
    CHECK(std::get<Rejection>(transition).diagnostics[0].field == "transition.relation");
    CHECK(ports.factories == std::array<int,7>{0,0,0,0,0,0,0});
}

TEST_CASE("strategy registry rejects validated family assurance before planning") {
    StrategyRegistry strategies;
    strategies.add({{{"numerical-only"},"1.0"},
        [](const StrategyRequest&,const Requirements&) -> Capability { return Offer{}; },
        [](const StrategyRequest&,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
            return Rejection{{"planner",{{"unexpected-planner"},std::string{"1.0"}},{}},
                {{DiagnosticCode::unsupported,"planner.reached","planning must not run for validated assurance"}}};
        }});

    auto request=strategy_request();
    request.configuration.strategy={"numerical-only"};
    request.family.assurance=Assurance::validated;
    Requirements requirements;
    requirements.output.family=request.family.target;
    requirements.output.assurance=Assurance::validated;

    const auto prepared=strategies.prepare(request,requirements,std::string{"1.0"});
    REQUIRE(std::holds_alternative<Rejection>(prepared));
    const auto& rejection=std::get<Rejection>(prepared);
    CHECK(rejection.provenance.port=="strategy");
    CHECK(rejection.provenance.requested.id.value=="numerical-only");
    CHECK(rejection.provenance.requested.version==std::optional<std::string>{"1.0"});
    REQUIRE(rejection.provenance.actual.has_value());
    CHECK(rejection.provenance.actual->id.value=="numerical-only");
    CHECK(rejection.provenance.actual->version=="1.0");
    REQUIRE(rejection.diagnostics.size()==1);
    CHECK(rejection.diagnostics[0].code==DiagnosticCode::unsupported);
    CHECK(rejection.diagnostics[0].field=="family.assurance");
    CHECK(rejection.diagnostics[0].explanation=="Validated family evidence is not implemented");
}

TEST_CASE("public prepared strategy rejects completeness claims without the selected verifier proof") {
    // CompletenessEvidence has its own three-alternative schema. Numerical residuals and
    // unchecked certificates are representable as coverage claims, while only the selected
    // compiled verifier's opaque proof may authorize publication.
    const std::vector<std::pair<std::string,CompletenessSupport>> unsupported{
        {"residual-only numerical coverage",NumericalCoverageEvidence{
            "binary64 residual observation",{1e-8,1e-8},{"residual-check"},
            "max residual was observed; no error bound or coverage proof"}},
        {"unchecked certificate reference",ValidatedCoverageEvidence{
            "unreviewed-certificate",{"unchecked-verifier"},"binary64"}},
        {"proof from a different verifier",RegisteredCompletenessEvidence{
            {"other-verifier"},"99","untrusted proof payload"}}
    };

    for (const auto& [case_name,support]:unsupported) {
        CAPTURE(case_name);
        auto request=strategy_request();
        request.configuration.strategy={"synthetic-completeness-guard"};
        request.strategy_version="1";
        request.family.target=FamilyTarget::exact_optimal_relation;
        request.family.representation={"synthetic-joint-relation"};
        Requirements requirements;
        requirements.output.representation=request.family.representation;
        requirements.output.family=FamilyTarget::exact_optimal_relation;
        requirements.output.completeness=Completeness::established;

        StrategyRegistry registry;
        StrategyRegistration registration{
            {{"synthetic-completeness-guard"},"1"},
            [](const StrategyRequest& prepared,const Requirements&) -> Capability {
                Output output;
                output.representation=prepared.family.representation;
                output.assurance=Assurance::numerical;
                output.family=FamilyTarget::exact_optimal_relation;
                output.completeness=Completeness::established;
                return Offer{std::move(output)};
            },
            [support](const StrategyRequest&,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
                auto checked=std::get<CheckedPipeline<>>(check_pipeline());
                return compose_strategy(std::move(checked),[support](auto,const StrategyRequest&,
                    const Requirements&) {
                    return std::make_unique<MalformedCompletenessProposal>(support);
                });
            },
            StrategyRegistration::CompleteFamilyVerifierKey{
                {"csl.verifier.ts02-constant-integrator"},"1"}
        };
        REQUIRE_FALSE(registry.add(std::move(registration)).has_value());

        const auto prepared=registry.prepare(request,requirements);
        REQUIRE(std::holds_alternative<PreparedStrategy>(prepared));
        auto execution=context();
        execution.numerical=request.family.numerical;
        const auto answer=std::get<PreparedStrategy>(prepared).create()->run(execution);
        REQUIRE(std::holds_alternative<SynthesisResult>(answer));
        const auto& rejected=std::get<SynthesisResult>(answer);
        CHECK(rejected.termination==Termination::contract_rejected);
        CHECK_FALSE(rejected.family.has_value());
        CHECK_FALSE(rejected.complete_proposal.has_value());
        CHECK_FALSE(rejected.partial_proposal.has_value());
        CHECK(rejected.outcome.subject==request.problem.identity());
        CHECK(rejected.outcome.value==MathematicalOutcome::undetermined);
        CHECK(std::holds_alternative<Unestablished>(rejected.outcome.support));
        CHECK_FALSE(rejected.objective.lower.has_value());
        CHECK_FALSE(rejected.objective.upper.has_value());
        REQUIRE(std::holds_alternative<ContractValidationFailure>(rejected.stop));
        const auto& diagnostics=std::get<ContractValidationFailure>(rejected.stop).diagnostics;
        REQUIRE(diagnostics.size()==1);
        CHECK(diagnostics[0].code==DiagnosticCode::evidence_mismatch);
        CHECK(diagnostics[0].field=="family.proposal.verifier");
        CHECK(diagnostics[0].explanation==
            "Proposal proof payload does not match the frozen strategy registration");
    }
}

TEST_CASE("runtime strategy extension adds a different typed dependency tuple without changing the caller") {
    struct CustomStrategy final : SynthesisWorkspace {
        std::unique_ptr<BoundWorkspace<CounterPort>> counter;
        explicit CustomStrategy(std::unique_ptr<BoundWorkspace<CounterPort>> w) : counter(std::move(w)) {}
        SynthesisResult solve(const csl::problem::ResolvedProblem& p,const FamilyRequest&,const ExecutionContext& c) override {
            const auto id=p.identity();
            SynthesisResult result{Termination::resource_limit,{id,MathematicalOutcome::undetermined,Unestablished{},{}},{},{},
                {{{id,{}, {},static_cast<double>(counter->run(c))},
                    {id,SymbolicArgument{"fixture", "counter sample"}}}}, {}};
            result.stop=ScopedOperationStopped{{StopReason::resource_limit,"counter fixture"},
                RequestProvenance{{"fixture/custom"},"strategy",{"custom-strategy"},std::string{"7"},
                    ModuleId{"custom-strategy"},std::string{"7"}},{false,false,1,false}};
            return result;
        }
    };
    auto prepared = [] {
        Registry<LPPort> lp; lp.add(endpoint_registration());
        Registry<CounterPort> custom;
        custom.add({{{"counter"},"3"},[](const CounterRequest&,const Requirements&) -> Capability { return Offer{}; },
            [](const CounterRequest&) { return std::make_unique<CounterFixture>(10); }});
        const auto operand = std::make_shared<const CounterRequest>(CounterRequest{20,std::make_shared<int>(0)});
        StrategyRegistry strategies; strategies.add(forward_registration(lp));
        strategies.add({{{"custom-strategy"},"7"},[](const StrategyRequest&,const Requirements&) -> Capability { return Offer{}; },
            [&custom,operand](const StrategyRequest&,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
                auto checked = check_pipeline(select(custom,Method{{"counter"},{}},*operand));
                if (auto* rejected = std::get_if<Rejection>(&checked)) return *rejected;
                return compose_strategy(std::get<0>(std::move(checked)),[operand](auto workers,const StrategyRequest&,const Requirements&) {
                    (void)operand; // Keeps the borrowed operand alive through deferred snapshot.
                    return std::make_unique<CustomStrategy>(std::move(std::get<0>(workers)));
                });
            }});
        std::vector<PreparedStrategy> result;
        for (const auto& id : {"forward","custom-strategy"}) {
            auto request = strategy_request(); request.configuration.strategy = {id};
            auto plan = strategies.prepare(request);
            REQUIRE(std::holds_alternative<PreparedStrategy>(plan));
            request.configuration.strategy = {"mutated"};
            request.family.profile = "mutated after snapshot";
            result.push_back(std::get<PreparedStrategy>(std::move(plan)));
        }
        return result;
    }();
    const std::array<double,2> expected{-1,31};
    for (std::size_t i=0;i<prepared.size();++i) {
        auto workspace = prepared[i].create();
        const auto answer = std::get<SynthesisResult>(workspace->run(context()));
        CHECK(answer.incumbents[0].witness.original_objective == expected[i]);
    }
    CHECK(prepared[1].provenance()[1].actual->id.value == "counter");
    CHECK(prepared[1].provenance()[1].actual->version == "3");
}

TEST_CASE("preflight never copies a factory numeric configuration before a downstream rejection") {
    struct Configuration {
        std::shared_ptr<int> copies;
        Vector values{10};
        explicit Configuration(std::shared_ptr<int> count) : copies(std::move(count)) {}
        Configuration(const Configuration& other) : copies(other.copies), values(other.values) { ++*copies; }
    };
    auto copies = std::make_shared<int>(0);
    const Configuration configuration{copies};
    Registry<CounterPort> registry;
    registry.add({{{"counter"},"1"},[](const CounterRequest&,const Requirements&) -> Capability { return Offer{}; },
        [configuration](const CounterRequest&) { return std::make_unique<CounterFixture>(static_cast<int>(configuration.values[0])); }});
    *copies = 0;
    const CounterRequest request{20,std::make_shared<int>(0)};
    auto rejected = prepare_pipeline(select(registry,Method{{"counter"},{}},request),
        select(registry,Method{{"missing"},{}},request));
    REQUIRE(std::holds_alternative<Rejection>(rejected));
    CHECK(std::get<Rejection>(rejected).provenance.requested.id.value == "missing");
    CHECK(*copies == 0);
}

TEST_CASE("erased strategy retains the complete immutable requested output profile") {
    Registry<LPPort> lp; lp.add(endpoint_registration());
    StrategyRegistry registry;
    auto entry = forward_registration(lp);
    entry.capabilities = [](const StrategyRequest&,const Requirements&) -> Capability {
        Output output; output.family = FamilyTarget::partial_relation;
        output.completeness = Completeness::unestablished;
        return Offer{output};
    };
    registry.add(entry);
    auto request = strategy_request();
    request.family.target=FamilyTarget::partial_relation;
    Requirements requirements;
    requirements.output.family = FamilyTarget::partial_relation;
    requirements.output.completeness = Completeness::unestablished;
    auto result = registry.prepare(request,requirements);
    REQUIRE(std::holds_alternative<PreparedStrategy>(result));
    requirements.output.family = FamilyTarget::exact_optimal_relation;
    requirements.output.completeness = Completeness::established;
    const auto& retained = std::get<PreparedStrategy>(result).requirements();
    CHECK(retained.output.family == FamilyTarget::partial_relation);
    CHECK(retained.output.completeness == Completeness::unestablished);
}

TEST_CASE("runtime builder observes retained requirements and request after every source exits") {
    class ProfileFixture final : public SynthesisWorkspace {
        std::unique_ptr<BoundWorkspace<LPPort>> dependency_;
        std::vector<std::string> configuration_;
    public:
        ProfileFixture(std::unique_ptr<BoundWorkspace<LPPort>> dependency,const StrategyRequest& request,const Requirements& requirements)
            : dependency_(std::move(dependency)), configuration_{
                requirements.output.family == FamilyTarget::partial_relation &&
                requirements.output.completeness == Completeness::unestablished ? "partial/unestablished" : "lost profile",
                std::get<LinearTerminal>(request.problem.description()->objective).offset == 2 ? "original request" : "lost request"} {}
        SynthesisResult solve(const csl::problem::ResolvedProblem& p,const FamilyRequest&,const ExecutionContext&) override {
            SynthesisResult result{Termination::resource_limit,
                {p.identity(),MathematicalOutcome::undetermined,Unestablished{},configuration_},{},{},{},{}};
            result.stop=ScopedOperationStopped{{StopReason::resource_limit,"profile fixture"},
                RequestProvenance{{"fixture/profile"},"strategy",{"profile"},std::string{"1"},
                    ModuleId{"profile"},std::string{"1"}}, {}};
            return result;
        }
    };
    auto prepared = [] {
        Registry<LPPort> lp; lp.add(endpoint_registration());
        const auto operand = std::make_shared<const LinearProgram>(interval_lp(3));
        StrategyRegistry registry;
        registry.add({{{"profile"},"1"},[](const StrategyRequest&,const Requirements&) -> Capability {
            Output output; output.family = FamilyTarget::partial_relation; output.completeness = Completeness::unestablished;
            return Offer{output};
        },[&lp,operand](const StrategyRequest&,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
            auto checked = check_pipeline(select(lp,Method{{"endpoint"},{}},*operand));
            if (auto* rejected = std::get_if<Rejection>(&checked)) return *rejected;
            return compose_strategy(std::get<0>(std::move(checked)),[operand](auto workers,const StrategyRequest& request,const Requirements& requirements) {
                (void)operand;
                return std::make_unique<ProfileFixture>(std::move(std::get<0>(workers)),request,requirements);
            });
        }});
        auto request = strategy_request(); request.configuration.strategy = {"profile"};
        request.family.target=FamilyTarget::partial_relation;
        Requirements requirements; requirements.output.family = FamilyTarget::partial_relation;
        requirements.output.completeness = Completeness::unestablished;
        auto result = registry.prepare(request,requirements);
        REQUIRE(std::holds_alternative<PreparedStrategy>(result));
        requirements.output.family = FamilyTarget::exact_optimal_relation;
        requirements.output.completeness = Completeness::established;
        request.family.profile = "mutated after snapshot";
        return std::get<PreparedStrategy>(std::move(result));
    }();
    const auto answer = std::get<SynthesisResult>(prepared.create()->run(context()));
    CHECK(answer.outcome.assumptions == std::vector<std::string>{"partial/unestablished","original request"});
}

TEST_CASE("public strategy outcome keeps candidate, partial, rejection and retained evidence distinct") {
    class Synthetic final : public SynthesisWorkspace {
    public:
        SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest& request,
            const ExecutionContext&) override {
            const auto id=problem.identity();
            const ClaimEvidence support{id,SymbolicArgument{"synthetic fixture assertion","literal fixture only"}};
            FamilyIdentity identity{id,request,problem.constraints().coordinates(),{"synthetic"},"1",{}};
            const JointRelation relation{identity.coordinates,request.representation,std::make_shared<const JointRelationPayload>()};
            SynthesisResult result{Termination::completed,
                {id,MathematicalOutcome::undetermined,Unestablished{},{}},{},{},
                {{{id,{{0},{1}},{{1}},5},support}}, {}};
            if (request.profile=="late-provider-rejection" || request.profile=="malformed-provider-rejection" ||
                request.profile=="malformed-lineage-rejection") {
                result.termination=Termination::operation_rejected;
                result.stop=ScopedRequestRejection{
                    RequestProvenance{{"generated/lp/7"},"lp",{"endpoint"},std::string{"1.0"},
                        ModuleId{"endpoint"},std::string{"1.0"}},
                    {{DiagnosticCode::unsupported,"lp.generated","provider rejected generated request"}},
                    {{{"transform/4"},{"input/set"},{"output/set"},{"converter"},"2"}},
                    {false,false,1,false}};
                if (request.profile=="malformed-lineage-rejection") {
                    auto& lineage=std::get<ScopedRequestRejection>(result.stop).completed_lineage;
                    lineage.push_back({{"transform/5"},{"output/set"},{"final/set"},{"projector"},"3"});
                    lineage.push_back({{"transform/4"},{"other/input"},{"other/output"},{"converter"},"2"});
                }
                if (request.profile=="malformed-provider-rejection") {
                    auto wrong=identity;wrong.strategy={"other-strategy"};
                    result.family=std::get<OptimalFamily>(FamilyPublisher::publish(wrong,CandidateFamily{
                        relation,HeuristicRelationEvidence{"synthetic"},Unestablished{}}));
                }
                return result;
            }
            if (request.profile=="user-cancel" || request.profile=="deadline") {
                const auto reason=request.profile=="deadline"?StopReason::deadline_expired:StopReason::cancelled;
                result.termination=Termination::cancelled;
                result.spans.push_back({0,{},ModuleId{"synthetic"},0,1});
                result.stop=ScopedOperationStopped{{reason,"synthetic stop"},
                    RequestProvenance{{"generated/step/3"},"strategy",{"synthetic"},std::string{"1"},
                        ModuleId{"synthetic"},std::string{"1"}}, {false,false,1,false}};
                return result;
            }
            if (request.profile=="resource-limit") {
                result.termination=Termination::resource_limit;
                result.objective={ObjectiveBound{4,support},ObjectiveBound{5,support}};
                auto candidate=FamilyPublisher::publish(identity,CandidateFamily{relation,
                    HeuristicRelationEvidence{"synthetic"},
                    WitnessFeasibilityEvidence{result.incumbents[0].witness,support}});
                result.family=std::get<OptimalFamily>(std::move(candidate));
                result.spans.push_back({0,{},ModuleId{"synthetic"},0,1});
                result.stop=ScopedOperationStopped{{StopReason::resource_limit,"synthetic resource budget exhausted"},
                    RequestProvenance{{"generated/step/4"},"strategy",{"synthetic"},std::string{"1"},
                        ModuleId{"synthetic"},std::string{"1"}}, {true,true,1,true}};
                return result;
            }
            if (request.target==FamilyTarget::candidate_relaxation) {
                if (request.profile=="outcome-identity-mismatch") result.outcome.subject={"other-problem"};
                auto candidate_identity=identity;
                if (request.profile=="candidate-identity-mismatch") candidate_identity.strategy={"other-strategy"};
                auto published=FamilyPublisher::publish(candidate_identity,CandidateFamily{relation,
                    HeuristicRelationEvidence{"synthetic"},WitnessFeasibilityEvidence{result.incumbents[0].witness,support}});
                result.family=std::get<OptimalFamily>(std::move(published));
            } else if (request.target==FamilyTarget::partial_relation) {
                auto refused=FamilyPublisher::publish(identity,PartialOptimalFamily{relation,{support,{}},
                    {support,"literal subset proof"},{"one supported witness"}});
                result.termination=Termination::contract_rejected;
                result.stop=ContractValidationFailure{std::get<Diagnostics>(std::move(refused)),
                    {false,false,1,false},{}};
            } else {
                result.outcome={id,MathematicalOutcome::optimal,support.support,{}};
                if (request.profile=="lineage-mismatch")
                    identity.lineage.push_back({{"generated/transform/1"},{"input/set"},
                        {"output/set"},{"converter"},"2"});
                auto refused=FamilyPublisher::publish(identity,CompleteOptimalFamily{relation,{support,{}},
                    {FamilyIdentity{id,request,problem.constraints().coordinates(),{"synthetic"},"1",{}},
                        NumericalCoverageEvidence{"unreviewed",request.numerical,{"fixture"},""}},
                    Assurance::numerical});
                result.termination=Termination::contract_rejected;
                result.stop=ContractValidationFailure{std::get<Diagnostics>(std::move(refused)),
                    {false,false,1,false},{}};
            }
            return result;
        }
    };
    StrategyRegistry registry;
    REQUIRE_FALSE(registry.add({{{"synthetic"},"1"},
        [](const StrategyRequest& request,const Requirements&) -> Capability {
            Output output;output.family=request.family.target;return Offer{output};
        },[](const StrategyRequest&,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
            return compose_strategy(std::get<CheckedPipeline<>>(check_pipeline()),
                [](auto,const StrategyRequest&,const Requirements&) {return std::make_unique<Synthetic>();});
        }}));
    for (const auto target:{FamilyTarget::candidate_relaxation,FamilyTarget::partial_relation,
        FamilyTarget::exact_optimal_relation}) {
        auto request=strategy_request();request.configuration.strategy={"synthetic"};request.family.target=target;
        Requirements requirements;requirements.output.family=target;
        auto preparation=registry.prepare(request,requirements);
        REQUIRE(std::holds_alternative<PreparedStrategy>(preparation));
        auto answer=std::get<PreparedStrategy>(std::move(preparation)).create()->run(context());
        REQUIRE(std::holds_alternative<SynthesisResult>(answer));
        const auto& result=std::get<SynthesisResult>(answer);
        REQUIRE(result.incumbents.size()==1);
        CHECK(result.incumbents[0].witness.original_objective==5);
        CHECK(result.incumbents[0].feasibility.problem==request.problem.identity());
        if (target!=FamilyTarget::candidate_relaxation) {
            CHECK(result.termination==Termination::contract_rejected);
            CHECK_FALSE(result.family.has_value());
            REQUIRE(std::holds_alternative<ContractValidationFailure>(result.stop));
            CHECK(std::get<ContractValidationFailure>(result.stop).retained.incumbents==1);
            if (target==FamilyTarget::partial_relation) {
                const auto& diagnostics=std::get<ContractValidationFailure>(result.stop).diagnostics;
                CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const auto& value){
                    return value.field=="family.partial.optimality" && value.code==DiagnosticCode::unsupported;
                }));
            }
        } else {
            CHECK(result.termination==Termination::completed);
            REQUIRE(result.family.has_value());
            CHECK(result.family->target()==target);
            CHECK(result.family->identity().request==request.family);
            const auto& candidate=std::get<CandidateFamily>(result.family->outcome());
            CHECK(std::holds_alternative<WitnessFeasibilityEvidence>(candidate.feasibility));
        }
    }
    auto request=strategy_request();request.configuration.strategy={"synthetic"};
    request.family.profile="late-provider-rejection";
    auto preparation=registry.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(preparation));
    const auto answer=std::get<PreparedStrategy>(std::move(preparation)).create()->run(context());
    REQUIRE(std::holds_alternative<SynthesisResult>(answer));
    const auto& result=std::get<SynthesisResult>(answer);
    CHECK(result.termination==Termination::operation_rejected);
    REQUIRE(std::holds_alternative<ScopedRequestRejection>(result.stop));
    const auto& rejection=std::get<ScopedRequestRejection>(result.stop);
    CHECK(rejection.request.request.value=="generated/lp/7");
    CHECK(rejection.request.port=="lp");
    CHECK(rejection.diagnostics[0].field=="lp.generated");
    CHECK(rejection.completed_lineage[0].request.value=="transform/4");
    CHECK(rejection.retained.incumbents==1);
    CHECK(result.incumbents[0].witness.original_objective==5);
    request.family.profile="malformed-lineage-rejection";
    auto malformed_lineage_prepared=registry.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(malformed_lineage_prepared));
    auto malformed_lineage_answer=
        std::get<PreparedStrategy>(std::move(malformed_lineage_prepared)).create()->run(context());
    REQUIRE(std::holds_alternative<SynthesisResult>(malformed_lineage_answer));
    const auto& malformed_lineage=std::get<SynthesisResult>(malformed_lineage_answer);
    CHECK(malformed_lineage.termination==Termination::contract_rejected);
    CHECK(malformed_lineage.incumbents.size()==1);
    CHECK(malformed_lineage.incumbents[0].witness.original_objective==5);
    REQUIRE(std::holds_alternative<ContractValidationFailure>(malformed_lineage.stop));
    const auto& lineage_failure=std::get<ContractValidationFailure>(malformed_lineage.stop);
    CHECK(std::any_of(lineage_failure.diagnostics.begin(),lineage_failure.diagnostics.end(),[](const auto& d){
        return d.field=="result.stop.rejection.lineage" && d.code==DiagnosticCode::invalid_claim;
    }));
    REQUIRE(std::holds_alternative<ScopedRequestRejection>(lineage_failure.source_stop));
    const auto& preserved=std::get<ScopedRequestRejection>(lineage_failure.source_stop);
    CHECK(preserved.request.request.value=="generated/lp/7");
    CHECK(preserved.request.port=="lp");
    CHECK(preserved.request.requested_module.value=="endpoint");
    CHECK(preserved.request.requested_version==std::optional<std::string>{"1.0"});
    CHECK(preserved.request.actual_module==std::optional<ModuleId>{ModuleId{"endpoint"}});
    CHECK(preserved.request.actual_version==std::optional<std::string>{"1.0"});
    REQUIRE(preserved.completed_lineage.size()==3);
    CHECK(preserved.completed_lineage[0].request.value=="transform/4");
    CHECK(preserved.completed_lineage[0].input.value=="input/set");
    CHECK(preserved.completed_lineage[0].output.value=="output/set");
    CHECK(preserved.completed_lineage[0].module.value=="converter");
    CHECK(preserved.completed_lineage[0].version=="2");
    CHECK(preserved.completed_lineage[1].request.value=="transform/5");
    CHECK(preserved.completed_lineage[1].input.value=="output/set");
    CHECK(preserved.completed_lineage[1].output.value=="final/set");
    CHECK(preserved.completed_lineage[1].module.value=="projector");
    CHECK(preserved.completed_lineage[1].version=="3");
    CHECK(preserved.completed_lineage[2].request.value=="transform/4");
    CHECK(preserved.completed_lineage[2].input.value=="other/input");
    CHECK(preserved.completed_lineage[2].output.value=="other/output");
    CHECK(preserved.completed_lineage[2].module.value=="converter");
    CHECK(preserved.completed_lineage[2].version=="2");
    request.family.profile="malformed-provider-rejection";
    auto malformed_provider=registry.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(malformed_provider));
    auto malformed_answer=std::get<PreparedStrategy>(std::move(malformed_provider)).create()->run(context());
    REQUIRE(std::holds_alternative<SynthesisResult>(malformed_answer));
    const auto& malformed_result=std::get<SynthesisResult>(malformed_answer);
    CHECK(malformed_result.termination==Termination::contract_rejected);
    REQUIRE(std::holds_alternative<ContractValidationFailure>(malformed_result.stop));
    const auto& original_stop=std::get<ContractValidationFailure>(malformed_result.stop).source_stop;
    REQUIRE(std::holds_alternative<ScopedRequestRejection>(original_stop));
    CHECK(std::get<ScopedRequestRejection>(original_stop).request.request.value=="generated/lp/7");
    CHECK(std::get<ScopedRequestRejection>(original_stop).completed_lineage[0].request.value=="transform/4");
    CHECK_FALSE(malformed_result.family.has_value());
    request.family.profile="lineage-mismatch";
    request.family.target=FamilyTarget::exact_optimal_relation;
    Requirements exact;exact.output.family=FamilyTarget::exact_optimal_relation;
    auto malformed=registry.prepare(request,exact);
    REQUIRE(std::holds_alternative<PreparedStrategy>(malformed));
    auto mismatch=std::get<PreparedStrategy>(std::move(malformed)).create()->run(context());
    REQUIRE(std::holds_alternative<SynthesisResult>(mismatch));
    const auto& rejected=std::get<SynthesisResult>(mismatch);
    CHECK(rejected.termination==Termination::contract_rejected);
    CHECK_FALSE(rejected.family.has_value());
    const auto& diagnostic=std::get<ContractValidationFailure>(rejected.stop).diagnostics;
    CHECK(std::any_of(diagnostic.begin(),diagnostic.end(),[](const auto& value){
        return value.field=="family.completeness.binding";
    }));
    request.family.target=FamilyTarget::candidate_relaxation;
    request.family.profile="candidate-identity-mismatch";
    auto candidate_prepared=registry.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(candidate_prepared));
    auto candidate_answer=std::get<PreparedStrategy>(std::move(candidate_prepared)).create()->run(context());
    REQUIRE(std::holds_alternative<SynthesisResult>(candidate_answer));
    const auto& candidate_rejected=std::get<SynthesisResult>(candidate_answer);
    CHECK(candidate_rejected.termination==Termination::contract_rejected);
    CHECK_FALSE(candidate_rejected.family.has_value());
    REQUIRE(std::holds_alternative<ContractValidationFailure>(candidate_rejected.stop));
    CHECK(std::get<ContractValidationFailure>(candidate_rejected.stop).retained.incumbents==1);
    CHECK(std::holds_alternative<std::monostate>(std::get<ContractValidationFailure>(candidate_rejected.stop).source_stop));
    request.family.profile="outcome-identity-mismatch";
    auto outcome_prepared=registry.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(outcome_prepared));
    auto outcome_answer=std::get<PreparedStrategy>(std::move(outcome_prepared)).create()->run(context());
    REQUIRE(std::holds_alternative<SynthesisResult>(outcome_answer));
    const auto& outcome_rejected=std::get<SynthesisResult>(outcome_answer);
    CHECK(outcome_rejected.termination==Termination::contract_rejected);
    CHECK(outcome_rejected.outcome.subject==request.problem.identity());
    CHECK(outcome_rejected.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(outcome_rejected.family.has_value());
    CHECK(outcome_rejected.family->identity().request==request.family);
    for (const auto& [profile,reason]:{
        std::pair{"user-cancel",StopReason::cancelled},
        std::pair{"deadline",StopReason::deadline_expired}}) {
        request.family.profile=profile;
        auto prepared=registry.prepare(request);
        REQUIRE(std::holds_alternative<PreparedStrategy>(prepared));
        auto stopped=std::get<PreparedStrategy>(std::move(prepared)).create()->run(context());
        REQUIRE(std::holds_alternative<SynthesisResult>(stopped));
        const auto& value=std::get<SynthesisResult>(stopped);
        CHECK(value.termination==Termination::cancelled);
        REQUIRE(std::holds_alternative<ScopedOperationStopped>(value.stop));
        CHECK(std::get<ScopedOperationStopped>(value.stop).stop.reason==reason);
        CHECK(value.incumbents[0].witness.original_objective==5);
        CHECK(value.spans.size()==1);
    }
    request.family.target=FamilyTarget::candidate_relaxation;
    request.family.profile="resource-limit";
    auto limited_prepared=registry.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(limited_prepared));
    const auto limited_answer=std::get<PreparedStrategy>(std::move(limited_prepared)).create()->run(context());
    REQUIRE(std::holds_alternative<SynthesisResult>(limited_answer));
    const auto& limited=std::get<SynthesisResult>(limited_answer);
    CHECK(limited.termination==Termination::resource_limit);
    CHECK(limited.outcome.subject==request.problem.identity());
    CHECK(limited.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(limited.objective.lower.has_value());
    CHECK(limited.objective.lower->value==4);
    CHECK(limited.objective.lower->evidence.problem==request.problem.identity());
    REQUIRE(std::holds_alternative<SymbolicArgument>(limited.objective.lower->evidence.support));
    CHECK(std::get<SymbolicArgument>(limited.objective.lower->evidence.support).reference=="synthetic fixture assertion");
    CHECK(std::get<SymbolicArgument>(limited.objective.lower->evidence.support).assumptions=="literal fixture only");
    REQUIRE(limited.objective.upper.has_value());
    CHECK(limited.objective.upper->value==5);
    CHECK(limited.objective.upper->evidence.problem==request.problem.identity());
    REQUIRE(std::holds_alternative<SymbolicArgument>(limited.objective.upper->evidence.support));
    CHECK(std::get<SymbolicArgument>(limited.objective.upper->evidence.support).reference=="synthetic fixture assertion");
    CHECK(std::get<SymbolicArgument>(limited.objective.upper->evidence.support).assumptions=="literal fixture only");
    REQUIRE(limited.incumbents.size()==1);
    CHECK(limited.incumbents[0].witness.original_objective==5);
    CHECK(limited.incumbents[0].feasibility.problem==request.problem.identity());
    REQUIRE(std::holds_alternative<SymbolicArgument>(limited.incumbents[0].feasibility.support));
    CHECK(std::get<SymbolicArgument>(limited.incumbents[0].feasibility.support).reference=="synthetic fixture assertion");
    CHECK(std::get<SymbolicArgument>(limited.incumbents[0].feasibility.support).assumptions=="literal fixture only");
    REQUIRE(limited.family.has_value());
    CHECK(limited.family->target()==FamilyTarget::candidate_relaxation);
    CHECK(limited.family->identity().request==request.family);
    const auto& feasibility=std::get<CandidateFamily>(limited.family->outcome()).feasibility;
    REQUIRE(std::holds_alternative<WitnessFeasibilityEvidence>(feasibility));
    const auto& candidate_witness=std::get<WitnessFeasibilityEvidence>(feasibility);
    CHECK(candidate_witness.witness.problem==request.problem.identity());
    CHECK(candidate_witness.witness.states==std::vector<Vector>{{0},{1}});
    CHECK(candidate_witness.witness.controls==std::vector<Vector>{{1}});
    CHECK(candidate_witness.witness.original_objective==5);
    CHECK(candidate_witness.support.problem==request.problem.identity());
    REQUIRE(std::holds_alternative<SymbolicArgument>(candidate_witness.support.support));
    CHECK(std::get<SymbolicArgument>(candidate_witness.support.support).reference=="synthetic fixture assertion");
    CHECK(std::get<SymbolicArgument>(candidate_witness.support.support).assumptions=="literal fixture only");
    REQUIRE(limited.spans.size()==1);
    CHECK(limited.spans[0].module==ModuleId{"synthetic"});
    CHECK(limited.spans[0].start_seconds==0);
    CHECK(limited.spans[0].end_seconds==1);
    REQUIRE(std::holds_alternative<ScopedOperationStopped>(limited.stop));
    const auto& scoped=std::get<ScopedOperationStopped>(limited.stop);
    CHECK(scoped.stop.reason==StopReason::resource_limit);
    CHECK(scoped.stop.diagnostics=="synthetic resource budget exhausted");
    CHECK(scoped.request.request.value=="generated/step/4");
    CHECK(scoped.request.port=="strategy");
    CHECK(scoped.request.requested_module==ModuleId{"synthetic"});
    CHECK(scoped.request.requested_version==std::optional<std::string>{"1"});
    CHECK(scoped.request.actual_module==std::optional<ModuleId>{ModuleId{"synthetic"}});
    CHECK(scoped.request.actual_version==std::optional<std::string>{"1"});
    CHECK(scoped.retained.lower_bound);
    CHECK(scoped.retained.upper_bound);
    CHECK(scoped.retained.incumbents==1);
    CHECK(scoped.retained.partial_or_candidate_family);
}

TEST_CASE("prepared strategy rejects malformed operation-rejection result combinations at the public boundary") {
    enum class Malformation { missing_scoped_rejection, incompatible_termination, complete_claim_after_rejection };
    class MalformedWorkspace final : public SynthesisWorkspace {
        Malformation malformation_;
    public:
        explicit MalformedWorkspace(Malformation malformation) : malformation_(malformation) {}
        SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest& request,
            const ExecutionContext&) override {
            const auto id=problem.identity();
            SynthesisResult result{Termination::operation_rejected,
                {id,MathematicalOutcome::undetermined,Unestablished{},{}},{},{},{},{}};
            if (malformation_!=Malformation::missing_scoped_rejection) {
                result.stop=ScopedRequestRejection{
                    RequestProvenance{{"generated/lp/7"},"lp",{"endpoint"},std::string{"1.0"},
                        ModuleId{"endpoint"},std::string{"1.0"}},
                    {{DiagnosticCode::unsupported,"lp.generated","provider rejected generated request"}},
                    {},{false,false,0,false}};
            }
            if (malformation_==Malformation::incompatible_termination)
                result.termination=Termination::completed;
            if (malformation_==Malformation::complete_claim_after_rejection) {
                const auto coordinates=problem.constraints().coordinates();
                const FamilyIdentity identity{id,request,coordinates,{"malformed"},"1",{}};
                const ClaimEvidence optimum{id,SymbolicArgument{"synthetic optimum","test fixture"}};
                const CompleteOptimalFamily family{
                    {coordinates,request.representation,std::make_shared<const JointRelationPayload>()},
                    {optimum,{}},
                    {identity,NumericalCoverageEvidence{"synthetic",request.numerical,{"fixture"},""}},
                    Assurance::numerical};
                result.complete_proposal=CompleteFamilyProposal{identity,family};
            }
            return result;
        }
    };

    const auto check_rejected=[&](Malformation malformation,const std::string& expected_field,
        DiagnosticCode expected_code) {
        StrategyRegistry strategies;
        REQUIRE_FALSE(strategies.add({{{"malformed"},"1"},
            [](const StrategyRequest& request,const Requirements&) -> Capability {
                Output output;output.family=request.family.target;return Offer{output};
            },
            [malformation](const StrategyRequest&,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
                return compose_strategy(std::get<CheckedPipeline<>>(check_pipeline()),
                    [malformation](auto,const StrategyRequest&,const Requirements&) {
                        return std::make_unique<MalformedWorkspace>(malformation);
                    });
            }}));
        auto request=strategy_request();
        request.configuration.strategy={"malformed"};
        if (malformation==Malformation::complete_claim_after_rejection)
            request.family.target=FamilyTarget::exact_optimal_relation;
        Requirements requirements;
        requirements.output.family=request.family.target;
        auto prepared=strategies.prepare(request,requirements);
        REQUIRE(std::holds_alternative<PreparedStrategy>(prepared));
        const auto answer=std::get<PreparedStrategy>(std::move(prepared)).create()->run(context());
        REQUIRE(std::holds_alternative<SynthesisResult>(answer));
        const auto& result=std::get<SynthesisResult>(answer);
        CHECK(result.termination==Termination::contract_rejected);
        CHECK_FALSE(result.family.has_value());
        REQUIRE(std::holds_alternative<ContractValidationFailure>(result.stop));
        const auto& failure=std::get<ContractValidationFailure>(result.stop);
        REQUIRE(failure.diagnostics.size()==1);
        CHECK(failure.diagnostics[0].code==expected_code);
        CHECK(failure.diagnostics[0].field==expected_field);
        if (malformation==Malformation::complete_claim_after_rejection) {
            REQUIRE(std::holds_alternative<ScopedRequestRejection>(failure.source_stop));
            const auto& rejection=std::get<ScopedRequestRejection>(failure.source_stop);
            CHECK(rejection.request.request.value=="generated/lp/7");
            CHECK(rejection.diagnostics[0].field=="lp.generated");
        }
    };

    SUBCASE("operation_rejected without scoped request rejection") {
        check_rejected(Malformation::missing_scoped_rejection,"result.stop",DiagnosticCode::invalid_claim);
    }
    SUBCASE("scoped request rejection under completed termination") {
        check_rejected(Malformation::incompatible_termination,"result.stop",DiagnosticCode::invalid_claim);
    }
    SUBCASE("complete-family proposal after generated-request rejection") {
        check_rejected(Malformation::complete_claim_after_rejection,"family.proposal",DiagnosticCode::unsupported);
    }
}

TEST_CASE("public strategy rejects unbounded outcomes that retain a finite lower bound") {
    class ContradictoryOutcome final : public SynthesisWorkspace {
    public:
        SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest&,
            const ExecutionContext&) override {
            const auto id=problem.identity();
            const ClaimEvidence support{id,SymbolicArgument{
                "state is fixed at zero by the fixture dynamics",
                "B=0, x0=0 and zero offset imply x1=0; the terminal objective is identically zero"}};
            const ClaimEvidence upper_support{id,SymbolicArgument{
                "the zero objective is at most five", "literal independent upper-bound fixture"}};
            return {Termination::completed,
                {id,MathematicalOutcome::unbounded,
                    SymbolicArgument{"synthetic outcome claim","used only to test evidence consistency"},{}},
                {ObjectiveBound{0,support},ObjectiveBound{5,upper_support}},{},{},{}};
        }
    } workspace;

    const LinearStage stage{{1,1,{0}},{1,1,{0}},{1,0,{}},{0}};
    const Problem bounded_problem{{"bounded-lower-bound-fixture"},
        std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,stage},{}}),
        {0,1},KnownInitial{{0}},ContinuousDomain{{UniversalSet{1}}},
        {UniversalSet{1},UniversalSet{1}},{},{},InformationPattern::nominal_open_loop,
        LinearTerminal{{1},0}};
    auto request=strategy_request();
    request.problem=std::get<csl::problem::ResolvedProblem>(csl::problem::resolve(
        bounded_problem,{csl::problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    request.configuration.strategy={"contradictory-outcome-fixture"};
    request.family.objective=request.problem.identity();
    request.strategy_version="1";

    const auto answer=StrategyPort::run(workspace,request,context());
    REQUIRE(std::holds_alternative<SynthesisResult>(answer));
    const auto& result=std::get<SynthesisResult>(answer);
    CHECK(result.termination==Termination::contract_rejected);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(result.objective.lower.has_value());
    CHECK(result.objective.lower->value==0);
    REQUIRE(result.objective.upper.has_value());
    CHECK(result.objective.upper->value==5);
    CHECK(result.objective.upper->evidence.problem==request.problem.identity());
    REQUIRE(std::holds_alternative<SymbolicArgument>(result.objective.upper->evidence.support));
    CHECK(std::get<SymbolicArgument>(result.objective.upper->evidence.support).reference==
        "the zero objective is at most five");
    REQUIRE(std::holds_alternative<ContractValidationFailure>(result.stop));
    const auto& failure=std::get<ContractValidationFailure>(result.stop);
    REQUIRE(failure.diagnostics.size()==1);
    CHECK(failure.diagnostics[0].code==DiagnosticCode::invalid_claim);
    CHECK(failure.diagnostics[0].field=="result.outcome.unbounded");
    CHECK(failure.retained.lower_bound);
    CHECK(failure.retained.upper_bound);
}

TEST_CASE("public strategy accepts an unbounded outcome without a supported lower bound") {
    class UnboundedOutcome final : public SynthesisWorkspace {
    public:
        SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest&,
            const ExecutionContext&) override {
            const auto id=problem.identity();
            return {Termination::completed,
                {id,MathematicalOutcome::unbounded,
                    SymbolicArgument{"synthetic outcome claim","used only to test absence of conflicting bound evidence"},{}},
                {},{},{},{}};
        }
    } workspace;

    auto request=strategy_request();
    request.configuration.strategy={"unbounded-without-bound-fixture"};
    request.strategy_version="1";
    const auto answer=StrategyPort::run(workspace,request,context());
    REQUIRE(std::holds_alternative<SynthesisResult>(answer));
    const auto& result=std::get<SynthesisResult>(answer);
    CHECK(result.termination==Termination::completed);
    CHECK(result.outcome.value==MathematicalOutcome::unbounded);
    CHECK_FALSE(result.objective.lower.has_value());
    CHECK(std::holds_alternative<std::monostate>(result.stop));
}

TEST_CASE("public strategy passes through a supported infeasible outcome") {
    class InfeasibleOutcome final : public SynthesisWorkspace {
    public:
        SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest&,
            const ExecutionContext&) override {
            return {Termination::completed,
                {problem.identity(),MathematicalOutcome::infeasible,
                    SymbolicArgument{"synthetic infeasibility claim","contract pass-through fixture only"},{}},
                {},{},{},{}};
        }
    } workspace;

    auto request=strategy_request();
    request.configuration.strategy={"infeasible-outcome-pass-through-fixture"};
    request.strategy_version="1";
    const auto answer=StrategyPort::run(workspace,request,context());
    REQUIRE(std::holds_alternative<SynthesisResult>(answer));
    const auto& result=std::get<SynthesisResult>(answer);
    CHECK(result.termination==Termination::completed);
    CHECK(result.outcome.subject==request.problem.identity());
    CHECK(result.outcome.value==MathematicalOutcome::infeasible);
    REQUIRE(std::holds_alternative<SymbolicArgument>(result.outcome.support));
    CHECK(std::get<SymbolicArgument>(result.outcome.support).reference=="synthetic infeasibility claim");
    CHECK(std::get<SymbolicArgument>(result.outcome.support).assumptions=="contract pass-through fixture only");
    CHECK(result.outcome.assumptions.empty());
    CHECK_FALSE(result.objective.lower.has_value());
    CHECK_FALSE(result.objective.upper.has_value());
    CHECK_FALSE(result.family.has_value());
    CHECK(result.incumbents.empty());
    CHECK(std::holds_alternative<std::monostate>(result.stop));
}

TEST_CASE("public strategy passes through a supported infimum-not-attained outcome") {
    class InfimumNotAttainedOutcome final : public SynthesisWorkspace {
    public:
        SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest&,
            const ExecutionContext&) override {
            return {Termination::completed,
                {problem.identity(),MathematicalOutcome::infimum_not_attained,
                    SymbolicArgument{"synthetic unattained-infimum claim","contract pass-through fixture only"},{}},
                {},{},{},{}};
        }
    } workspace;

    auto request=strategy_request();
    request.configuration.strategy={"infimum-not-attained-outcome-pass-through-fixture"};
    request.strategy_version="1";
    const auto answer=StrategyPort::run(workspace,request,context());
    REQUIRE(std::holds_alternative<SynthesisResult>(answer));
    const auto& result=std::get<SynthesisResult>(answer);
    CHECK(result.termination==Termination::completed);
    CHECK(result.outcome.subject==request.problem.identity());
    CHECK(result.outcome.value==MathematicalOutcome::infimum_not_attained);
    REQUIRE(std::holds_alternative<SymbolicArgument>(result.outcome.support));
    CHECK(std::get<SymbolicArgument>(result.outcome.support).reference=="synthetic unattained-infimum claim");
    CHECK(std::get<SymbolicArgument>(result.outcome.support).assumptions=="contract pass-through fixture only");
    CHECK(result.outcome.assumptions.empty());
    CHECK_FALSE(result.objective.lower.has_value());
    CHECK_FALSE(result.objective.upper.has_value());
    CHECK_FALSE(result.family.has_value());
    CHECK(result.incumbents.empty());
    CHECK(std::holds_alternative<std::monostate>(result.stop));
}

TEST_CASE("public strategy removes an unsupported lower bound without discarding supported unbounded evidence") {
    class UnsupportedLowerBound final : public SynthesisWorkspace {
    public:
        SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest&,
            const ExecutionContext&) override {
            const auto id=problem.identity();
            const ClaimEvidence unsupported_bound{id,Unestablished{}};
            return {Termination::completed,
                {id,MathematicalOutcome::unbounded,
                    SymbolicArgument{"unbounded objective claim", "literal fixture outcome support"},{}},
                {ObjectiveBound{-1,unsupported_bound}},{},{},{}};
        }
    } workspace;

    auto request=strategy_request();
    request.configuration.strategy={"unbounded-with-unsupported-lower-bound-fixture"};
    request.strategy_version="1";
    const auto answer=StrategyPort::run(workspace,request,context());
    REQUIRE(std::holds_alternative<SynthesisResult>(answer));
    const auto& result=std::get<SynthesisResult>(answer);
    CHECK(result.termination==Termination::contract_rejected);
    CHECK(result.outcome.value==MathematicalOutcome::unbounded);
    CHECK(std::holds_alternative<SymbolicArgument>(result.outcome.support));
    CHECK(std::get<SymbolicArgument>(result.outcome.support).reference=="unbounded objective claim");
    CHECK_FALSE(result.objective.lower.has_value());
    REQUIRE(std::holds_alternative<ContractValidationFailure>(result.stop));
    const auto& failure=std::get<ContractValidationFailure>(result.stop);
    REQUIRE(failure.diagnostics.size()==1);
    CHECK(failure.diagnostics[0].code==DiagnosticCode::evidence_mismatch);
    CHECK(failure.diagnostics[0].field=="result.objective");
    CHECK_FALSE(failure.retained.lower_bound);
    CHECK_FALSE(failure.retained.upper_bound);
}
