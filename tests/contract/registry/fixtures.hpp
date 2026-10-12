#pragma once
#include <csl/registry/registry.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <cmath>
#include <string>

namespace registry_fixtures {
using namespace csl;
using namespace csl::registry;
inline LinearProgramInput interval_input(double coefficient) {
    return {{{"problem"}, {"interval"}}, {coefficient}, 2, {0,1,{0},{},{}}, {{-1,4}}, {}};
}
inline LinearProgram publish(LinearProgramInput input) {
    return std::get<LinearProgram>(optimization::make_linear_program(input));
}
inline LinearProgram interval_lp(double coefficient) { return publish(interval_input(coefficient)); }
inline ExecutionContext context() {
    return {std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}), {}, {}, {1e-8,1e-8}, "registry-test"};
}
// Two real algorithms on the deliberately bounded one-variable finite interval domain.
class EndpointWorkspace final : public LPWorkspace {
    std::size_t calls_{};
public:
    ProgramOutcome do_solve(const LinearProgram& p, const ExecutionContext&) override {
        ++calls_;
        const double lower = *p.variables()[0].lower, upper = *p.variables()[0].upper;
        const double lower_value = std::fma(p.objective()[0],lower,p.offset());
        const double upper_value = std::fma(p.objective()[0],upper,p.offset());
        const double x = lower_value <= upper_value ? lower : upper;
        const double value = lower_value <= upper_value ? lower_value : upper_value;
        const ProgramBoundEvidence evidence{p.identity(), SymbolicArgument{"finite interval endpoint oracle", "affine objective on a finite interval"}, {}};
        return ProgramResult{Termination::completed, {p.identity(), MathematicalOutcome::optimal,
            SymbolicArgument{"endpoint enumeration", "affine objective on finite interval"}, {}},
            Vector{x}, {ProgramObjectiveBound{value,evidence}, ProgramObjectiveBound{value,evidence}}, std::to_string(calls_)};
    }
};
class SignWorkspace final : public LPWorkspace {
    std::size_t calls_{};
public:
    ProgramOutcome do_solve(const LinearProgram& p, const ExecutionContext&) override {
        ++calls_;
        const double x = p.objective()[0] < 0 ? *p.variables()[0].upper : *p.variables()[0].lower;
        const double value = std::fma(p.objective()[0],x,p.offset());
        const ProgramBoundEvidence evidence{p.identity(), SymbolicArgument{"finite interval endpoint oracle", "affine objective on a finite interval"}, {}};
        return ProgramResult{Termination::completed, {p.identity(), MathematicalOutcome::optimal,
            SymbolicArgument{"coefficient sign", "affine objective on finite interval"}, {}},
            Vector{x}, {ProgramObjectiveBound{value,evidence}, ProgramObjectiveBound{value,evidence}}, std::to_string(calls_)};
    }
};
inline Capability interval_capability(const LinearProgram& p, const Requirements&) {
    // The canonical program already guarantees consistent finite CSR/bounds.
    if (p.objective().size()!=1 || p.constraints().rows()!=0 ||
        !p.variables()[0].lower || !p.variables()[0].upper)
        return Diagnostics{{DiagnosticCode::unsupported,"lp.domain","requires one variable, finite interval and no rows"}};
    const double coefficient = p.objective()[0];
    const double lower = *p.variables()[0].lower, upper = *p.variables()[0].upper;
    const double lower_value = std::fma(coefficient,lower,p.offset());
    const double upper_value = std::fma(coefficient,upper,p.offset());
    if (!std::isfinite(coefficient*lower) || !std::isfinite(coefficient*upper) ||
        !std::isfinite(lower_value) || !std::isfinite(upper_value))
        return Diagnostics{{DiagnosticCode::unsupported,"lp.arithmetic","fixture requires finite endpoint products and objective values"}};
    if (coefficient != 0 && lower != upper && lower_value == upper_value)
        return Diagnostics{{DiagnosticCode::unsupported,"lp.arithmetic","unequal endpoint objectives are indistinguishable in binary64"}};
    return Offer{};
}
inline Registration<LPPort> endpoint_registration() {
    return {{{"endpoint"}, "1.0"}, interval_capability,
        [](const LinearProgram&) { return std::make_unique<EndpointWorkspace>(); }};
}
inline Registration<LPPort> sign_registration() {
    return {{{"sign"}, "2.0"}, interval_capability,
        [](const LinearProgram&) { return std::make_unique<SignWorkspace>(); }};
}
inline StrategyRequest strategy_request() {
    const LinearStage stage{{1,1,{0}},{1,1,{1}},{1,0,{}},{0}};
    Problem problem{{"problem"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,stage},{}}),
        {0,1},KnownInitial{{0}},ContinuousDomain{{UniversalSet{1}}},{UniversalSet{1},UniversalSet{1}}, {},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{3},2}};
    auto resolved=std::get<csl::problem::ResolvedProblem>(csl::problem::resolve(problem,{csl::problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    return {resolved,{{"forward"},{"endpoint"},{"unused-convex"},{"unused-hull"},{},{},{},{},{}},
        {"nominal_open_loop",resolved.identity(),FamilyTarget::candidate_relaxation,{1e-8,1e-8},Assurance::numerical,{},{}}};
}
// Plumbing fixture only: forwards a bounded LP answer as an incumbent, never a full family.
class ForwardFixture final : public SynthesisWorkspace {
    std::unique_ptr<BoundWorkspace<LPPort>> lp_;
public:
    explicit ForwardFixture(std::unique_ptr<BoundWorkspace<LPPort>> lp) : lp_(std::move(lp)) {}
    SynthesisResult solve(const csl::problem::ResolvedProblem& problem, const FamilyRequest&, const ExecutionContext& context) override {
        const auto answer = std::get<ProgramResult>(lp_->run(context));
        const auto id=problem.identity();
        return SynthesisResult{Termination::completed,{id,MathematicalOutcome::undetermined,Unestablished{},{}},
            {},{},{{{id,{}, {*answer.primal},answer.objective.upper->value},
                {id,SymbolicArgument{"fixture LP point", "bounded scalar interval"}}}}, {}};
    }
};
inline StrategyRegistration forward_registration(const Registry<LPPort>& lp, std::string id = "forward") {
    const auto request = std::make_shared<const LinearProgram>(interval_lp(3));
    return {{{std::move(id)},"fixture-1"},
        [](const StrategyRequest& r,const Requirements& requirements) -> Capability {
            auto diagnostics = check_nominal_profile(*r.problem.description(),false,requirements.output.assurance);
            if (!diagnostics.empty()) return diagnostics;
            if (!std::holds_alternative<LinearTerminal>(r.problem.description()->objective))
                return Diagnostics{{DiagnosticCode::unsupported,"objective","fixture requires a linear terminal objective"}};
            return Offer{};
        },
        [&lp,request](const StrategyRequest& r,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
            auto checked = check_pipeline(select(lp,Method{r.configuration.lp,{}},*request));
            if (auto* rejection = std::get_if<Rejection>(&checked)) return *rejection;
            return compose_strategy(std::get<CheckedPipeline<LPPort>>(std::move(checked)),
                [request](auto workers,const StrategyRequest&,const Requirements&) {
                    (void)request; // Retains the borrowed LP until deferred snapshot finishes.
                    return std::make_unique<ForwardFixture>(std::move(std::get<0>(workers)));
                });
        }};
}

// The following adapters exercise callable port plumbing only. Stopped/undetermined
// outcomes deliberately make no mathematical-completeness claim.
class ConvexFixture final : public ConvexWorkspace {
public: ProgramOutcome do_solve(const ConvexProgram& r,const ExecutionContext&) override {
    return ProgramResult{Termination::resource_limit,{r.identity(),MathematicalOutcome::undetermined,Unestablished{},{}}, {},{},r.identity().program.value};
}};
class GeometryFixture final : public SetOperatorWorkspace {
public: OperationOutcome apply(const OperationRequest& r,const ExecutionContext&) override {
    return OperationStopped{StopReason::resource_limit,r.identity.request.value};
}};
class ConversionFixture final : public RepresentationConverterWorkspace {
public: SetTransformOutcome convert(const ConversionRequest& r,const ExecutionContext&) override {
    return OperationStopped{StopReason::resource_limit,r.output.value};
}};
class ApproximationFixture final : public SetApproximatorWorkspace {
public: SetTransformOutcome approximate(const ApproximationRequest& r,const ExecutionContext&) override {
    return OperationStopped{StopReason::resource_limit,std::to_string(r.size_budget)};
}};
class SelectorFixture final : public WitnessSelectorWorkspace {
public: std::variant<WitnessSelection,Unsupported> select(const OptimalFamily&,const WitnessRequest& r,const ExecutionContext&) override {
    return WitnessSelection{{{},r.count,{"selector-fixture"},r.seed},Termination::resource_limit,"fixture"};
}};
class StrategyFixture final : public SynthesisWorkspace {
public: SynthesisResult solve(const csl::problem::ResolvedProblem& p,const FamilyRequest&,const ExecutionContext&) override {
    const auto raw=p.description();
    const auto& stage = std::get<LinearStage>(raw->model->dynamics.stages);
    const auto id=p.identity();
    SynthesisResult result{Termination::resource_limit,{id,MathematicalOutcome::undetermined,Unestablished{},{}},{},{},
        {{{id,{stage.offset},{},std::get<LinearTerminal>(raw->objective).offset},
            {id,SymbolicArgument{"fixture state", "single stage"}}}}, {}};
    result.stop=ScopedOperationStopped{{StopReason::resource_limit,"fixture"},
        RequestProvenance{{"fixture/strategy"},"strategy",{"strategy"},std::string{"fixture-1"},
            ModuleId{"strategy"},std::string{"fixture-1"}},
        {false,false,1,false}};
    return result;
}};
inline OptimalFamily candidate_family() {
    FamilyRequest request{"nominal_open_loop",{"problem"},FamilyTarget::candidate_relaxation,
        {1e-8,1e-8},Assurance::numerical,{"joint"},{}};
    FamilyIdentity identity{{"problem"},request,{{1,1,0},1},{"strategy"},"1",{}};
    auto published=FamilyPublisher::publish(identity,CandidateFamily{
        {identity.coordinates,{"joint"},std::make_shared<const JointRelationPayload>()},
        HeuristicRelationEvidence{"fixture"},Unestablished{}});
    return std::get<OptimalFamily>(std::move(published));
}
class BasisFixture final : public BasisDiagnostics {
public:
    BasisCapabilities capabilities() const override { return {false,false,false}; }
    BasisSnapshotResult snapshot() const override { return BasisUnavailable{BasisUnavailableReason::unsupported,"text fixture only"}; }
    std::string describe_basis() const override { return "fixture basis: column 0"; }
};

struct AllPorts {
    std::array<int,7> factories{};
    Registry<LPPort> lp; Registry<ConvexPort> convex; Registry<GeometryPort> geometry;
    Registry<ConversionPort> conversion; Registry<ApproximationPort> approximation;
    Registry<SelectorPort> selector; Registry<StrategyPort> strategy;
    LinearProgram lp_request = interval_lp(3);
    ConvexProgram convex_request = std::get<ConvexProgram>(optimization::make_convex_program({
        {{"problem"},{"interval"}},QuadraticTerminal{{1,1,{2}},{3},2},{0,1,{0},{},{}},{{-1,4}},{},{}}));
    SetHandle set{{1,{"poly"},SetProperty::yes,SetProperty::yes,SetProperty::yes},std::make_shared<const SetPayload>(),{"set"}};
    GeometryRequestIdentity geometry_id{{"problem"},{"geometry-request"},{"ideal"}};
    OperationRequest geometry_request{geometry_id,{"geometry"},SupportQuery{set,{1}},SetRelation::equivalent,Assurance::numerical};
    ConversionRequest conversion_request{geometry_id,set,{"vertices"},Assurance::numerical};
    ApproximationRequest approximation_request{geometry_id,set,{"box"},SetRelation::outer,17,Assurance::numerical};
    SelectorRequest selector_request{candidate_family(),{3,0.1,{},42}};
    StrategyRequest strategy_request_value = strategy_request();
    AllPorts() {
        auto e = endpoint_registration(); e.factory = [this](const LinearProgram&) { ++factories[0]; return std::make_unique<EndpointWorkspace>(); }; lp.add(e);
        auto capability = [](const auto&,const Requirements&) -> Capability { return Offer{}; };
        convex.add({{{"convex"},"fixture-1"},capability,[this](const ConvexProgram&) { ++factories[1]; return std::make_unique<ConvexFixture>(); }});
        geometry.add({{{"geometry"},"fixture-1"},capability,[this](const OperationRequest&) { ++factories[2]; return std::make_unique<GeometryFixture>(); }});
        conversion.add({{{"conversion"},"fixture-1"},capability,[this](const ConversionRequest&) { ++factories[3]; return std::make_unique<ConversionFixture>(); }});
        approximation.add({{{"approximation"},"fixture-1"},capability,[this](const ApproximationRequest&) { ++factories[4]; return std::make_unique<ApproximationFixture>(); }});
        selector.add({{{"selector"},"fixture-1"},capability,[this](const SelectorRequest&) { ++factories[5]; return std::make_unique<SelectorFixture>(); }});
        strategy.add({{{"strategy"},"fixture-1"},[](const StrategyRequest& r,const Requirements&) -> Capability {
            if (!std::holds_alternative<LinearTerminal>(r.problem.description()->objective))
                return Diagnostics{{DiagnosticCode::unsupported,"objective","plumbing fixture expects a linear objective"}};
            return Offer{};
        },[this](const StrategyRequest&) { ++factories[6]; return std::make_unique<StrategyFixture>(); }});
    }
    auto prepare(Requirements last = {}, Method method = {{"endpoint"},{}}, std::vector<Transition> transitions = {}) {
        return prepare_pipeline(select(lp,std::move(method),lp_request),
            select(convex,Method{{"convex"},{}},convex_request),
            select(geometry,Method{{"geometry"},{}},geometry_request),
            select(conversion,Method{{"conversion"},{}},conversion_request),
            select(approximation,Method{{"approximation"},{}},approximation_request),
            select(selector,Method{{"selector"},{}},selector_request),
            select(strategy,Method{{"strategy"},{}},strategy_request_value,last,std::move(transitions)));
    }
};

// An extension defined entirely outside the product header: no hull semantics.
struct CounterRequest { int value; std::shared_ptr<int> snapshot_count; };
class CounterWorkspace : public ExclusiveWorkspace {
public: virtual int evaluate(const CounterRequest&) = 0;
};
struct CounterPort {
    using Request = CounterRequest; using Workspace = CounterWorkspace;
    static constexpr const char* name = "counter-fixture";
    static Request snapshot(const Request& r) { ++*r.snapshot_count; return r; }
    static int run(Workspace& w,const Request& r,const ExecutionContext&) { return w.evaluate(r); }
};
class CounterFixture final : public CounterWorkspace {
    int base_, calls_{};
public:
    explicit CounterFixture(int base) : base_(base) {}
    int evaluate(const CounterRequest& r) override { return base_ + r.value + ++calls_; }
};
} // namespace registry_fixtures
