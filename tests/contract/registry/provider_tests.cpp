#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/registry/provider.hpp>
#include "fixtures.hpp"
using namespace csl;
using namespace csl::registry;
using namespace registry_fixtures;
static_assert(!std::is_default_constructible_v<PreparedProvider<LPPort>>);
static_assert(!std::is_default_constructible_v<CheckedProviders<LPPort>>);
template<class T> concept HasPerQueryRequirements = requires(const T& p,const LinearProgram& r) {p.prepare(r,Requirements{});};
static_assert(!HasPerQueryRequirements<PreparedProvider<LPPort>>);

template<class T,class... U> T accepted(std::variant<T,U...> result) {
    REQUIRE(std::holds_alternative<T>(result));return std::get<T>(std::move(result));
}
TEST_CASE("one frozen registered LP provider prepares different owned requests after source exit") {
    auto provider=[] {
        Registry<LPPort> source;source.add(endpoint_registration());source.add(sign_registration());
        auto method=Method{{"endpoint"},"1.0"};Requirements requirements;
        auto result=accepted(prepare_provider(select_provider(source,method,requirements)));
        method.id={"sign"};requirements.scalar=Scalar::exact;
        return result;
    }();
    CHECK(provider.provenance().actual->id.value=="endpoint");
    CHECK(provider.provenance().actual->version=="1.0");
    CHECK(provider.requirements().scalar==Scalar::binary64);
    for(double objective:{3.0,-2.0}) {
        auto prepared=accepted(provider.prepare(interval_lp(objective)));
        CHECK(prepared.provenance()[0].actual->id.value=="endpoint");
        auto workspaces=prepared.create();
        const auto result=std::get<ProgramResult>(std::get<0>(workspaces)->run(context()));
        CHECK(result.primal==std::optional<Vector>{{objective>0?-1.0:4.0}});
        CHECK(result.objective.upper->value==(objective>0?-1.0:-6.0));
    }
}
TEST_CASE("generated request rechecks domain arithmetic offer and basis before factory") {
    int factories=0;
    Registry<LPPort> source;auto entry=endpoint_registration();
    entry.factory=[&](const LinearProgram&){++factories;return std::make_unique<EndpointWorkspace>();};
    source.add(entry);
    auto provider=accepted(prepare_provider(select_provider(source,Method{{"endpoint"},{}})));
    auto unbounded=interval_input(1);unbounded.variables[0].upper.reset();
    auto overflow=interval_input(-std::numeric_limits<double>::max());overflow.variables[0]={2,3};
    for(const auto& input:{unbounded,overflow}) {
        const auto rejected=provider.prepare(publish(input));
        REQUIRE(std::holds_alternative<Rejection>(rejected));
        CHECK(std::get<Rejection>(rejected).provenance.actual->id.value=="endpoint");
        CHECK(std::get<Rejection>(rejected).diagnostics[0].field==(input.variables[0].upper?"lp.arithmetic":"lp.domain"));
    }
    CHECK(factories==0);
    auto workers=accepted(provider.prepare(interval_lp(1))).create();
    CHECK(factories==1);
    CHECK(std::get<ProgramResult>(std::get<0>(workers)->run(context())).primal==std::optional<Vector>{{-1}});
}
TEST_CASE("known unsupported provider declarations reject without copying callbacks") {
    struct CountCopy {
        std::shared_ptr<int> copies;
        explicit CountCopy(std::shared_ptr<int> p):copies(std::move(p)){}
        CountCopy(const CountCopy& other):copies(other.copies){++*copies;}
        std::unique_ptr<LPWorkspace> operator()(const LinearProgram&)const{return std::make_unique<EndpointWorkspace>();}
    };
    auto copies=std::make_shared<int>(0);Registry<LPPort> source;auto entry=endpoint_registration();entry.factory=CountCopy{copies};source.add(std::move(entry));*copies=0;
    for(const auto scalar:{Scalar::binary32,Scalar::exact,Scalar::interval}) {
        Requirements q;q.scalar=scalar;auto r=check_providers(select_provider(source,Method{{"endpoint"},{}},q));
        REQUIRE(std::holds_alternative<Rejection>(r));CHECK(std::get<Rejection>(r).diagnostics[0].field=="scalar");
    }
    Requirements validated;validated.output.assurance=Assurance::validated;
    CHECK(std::holds_alternative<Rejection>(check_providers(select_provider(source,Method{{"endpoint"},{}},validated))));
    Requirements basis;basis.basis_diagnostics=true;
    CHECK(std::holds_alternative<Rejection>(check_providers(select_provider(source,Method{{"endpoint"},{}},basis))));
    auto wrong=check_providers(select_provider(source,Method{{"endpoint"},"9"}));
    REQUIRE(std::holds_alternative<Rejection>(wrong));CHECK(std::get<Rejection>(wrong).diagnostics[0].field=="method.version");
    CHECK(std::holds_alternative<Rejection>(check_providers(select_provider(source,Method{{"missing"},{}}))));
    CHECK(*copies==0);
    auto valid=accepted(check_providers(select_provider(source,Method{{"endpoint"},"1.0"})));
    CHECK(*copies==0);auto frozen=valid.snapshot();CHECK(*copies>0);
    CHECK(std::get<0>(frozen).provenance().actual->version=="1.0");
}

class GeneratedFixture final : public SynthesisWorkspace {
    std::unique_ptr<BoundWorkspace<CounterPort>> fixed_;
    PreparedProvider<LPPort> generated_;
public:
    GeneratedFixture(std::unique_ptr<BoundWorkspace<CounterPort>> f,PreparedProvider<LPPort> p):fixed_(std::move(f)),generated_(std::move(p)){}
    SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest&,const ExecutionContext& context) override {
        const auto fixed=fixed_->run(context);
        auto workers=accepted(generated_.prepare(interval_lp(-2))).create();
        const auto lp=std::get<ProgramResult>(std::get<0>(workers)->run(context));
        const auto id=problem.identity();
        return SynthesisResult{Termination::completed,{id,MathematicalOutcome::undetermined,Unestablished{},{}},{},{},
            {{{id,{{static_cast<double>(fixed)}},{*lp.primal},lp.objective.upper->value},
                {id,SymbolicArgument{"fixture", "bounded LP sample"}}}}, {}};
    }
};
TEST_CASE("mixed fixed and generated strategy owns both after enclosing preparation") {
    auto snapshots=std::make_shared<int>(0);
    auto prepared=[&] {
        Registry<CounterPort> fixed;fixed.add({{{"counter"},"1"},[](const CounterRequest&,const Requirements&)->Capability{return Offer{};},
            [](const CounterRequest&){return std::make_unique<CounterFixture>(10);}});
        Registry<LPPort> generated;generated.add(endpoint_registration());
        auto numeric=std::make_shared<const CounterRequest>(CounterRequest{20,snapshots});
        StrategyRegistry strategies;
        strategies.add({{{"forward"},"mixed-1"},[](const StrategyRequest&,const Requirements&)->Capability{return Offer{};},
            [&](const StrategyRequest&,const Requirements&)->std::variant<StrategyPlan,Rejection>{
                auto f=accepted(check_pipeline(select(fixed,Method{{"counter"},{}},*numeric)));
                auto g=accepted(check_providers(select_provider(generated,Method{{"endpoint"},"1.0"})));
                CHECK(*snapshots==0);
                return compose_strategy(std::move(f),std::move(g),[numeric](auto workers,auto providers,const StrategyRequest&,const Requirements&){
                    return std::make_unique<GeneratedFixture>(std::move(std::get<0>(workers)),std::get<0>(providers));
                });
            }});
        return accepted(strategies.prepare(strategy_request()));
    }();
    CHECK(*snapshots==1);
    REQUIRE(prepared.provenance().size()==3);
    CHECK(prepared.provenance()[1].actual->id.value=="counter");
    CHECK(prepared.provenance()[2].actual->id.value=="endpoint");
    const auto result=std::get<SynthesisResult>(prepared.create()->run(context()));
    REQUIRE(result.incumbents.size()==1);CHECK(result.incumbents[0].witness.states==std::vector<Vector>{{31}});
    CHECK(result.incumbents[0].witness.controls==std::vector<Vector>{{4}});CHECK(result.incumbents[0].witness.original_objective==-6);
}
TEST_CASE("later outer dependency rejection snapshots neither fixed data nor generated callbacks") {
    struct CopyProbe {
        std::shared_ptr<int> copies;
        explicit CopyProbe(std::shared_ptr<int> c):copies(std::move(c)){}
        CopyProbe(const CopyProbe& o):copies(o.copies){++*copies;}
        std::unique_ptr<LPWorkspace> operator()(const LinearProgram&)const{return std::make_unique<EndpointWorkspace>();}
    };
    auto copies=std::make_shared<int>(0),snapshots=std::make_shared<int>(0);
    Registry<LPPort> lp;auto entry=endpoint_registration();entry.factory=CopyProbe{copies};lp.add(std::move(entry));
    Registry<CounterPort> fixed;fixed.add({{{"counter"},"1"},[](const CounterRequest&,const Requirements&)->Capability{return Offer{};},
        [](const CounterRequest&){return std::make_unique<CounterFixture>(10);}});
    CounterRequest request{20,snapshots};*copies=0;
    StrategyRegistry strategies;
    strategies.add({{{"forward"},"reject-late"},[](const StrategyRequest&,const Requirements&)->Capability{return Offer{};},
        [&](const StrategyRequest&,const Requirements&)->std::variant<StrategyPlan,Rejection>{
            auto f=check_pipeline(select(fixed,Method{{"counter"},{}},request));
            REQUIRE(std::holds_alternative<CheckedPipeline<CounterPort>>(f));
            auto g=check_providers(select_provider(lp,Method{{"endpoint"},{}}),select_provider(lp,Method{{"absent"},{}}));
            REQUIRE(std::holds_alternative<Rejection>(g));return std::get<Rejection>(g);
        }});
    const auto rejected=strategies.prepare(strategy_request());
    REQUIRE(std::holds_alternative<Rejection>(rejected));CHECK(std::get<Rejection>(rejected).provenance.requested.id.value=="absent");
    CHECK(*copies==0);CHECK(*snapshots==0);
    // The accepted case above also exercises the actual mixed composition overload.
}
TEST_CASE("frozen output requirements and basis cannot be lowered by generated requests") {
    Registry<LPPort> lp;auto entry=endpoint_registration();int basis_calls=0;
    entry.basis_factory=[&](const LinearProgram&,LPWorkspace&){++basis_calls;return std::make_unique<BasisFixture>();};lp.add(entry);
    Requirements requested;requested.basis_diagnostics=true;
    auto provider=accepted(prepare_provider(select_provider(lp,Method{{"endpoint"},{}},requested)));
    requested.basis_diagnostics=false;
    CHECK(provider.requirements().basis_diagnostics);
    auto workers=accepted(provider.prepare(interval_lp(3))).create();
    CHECK(basis_calls==1);REQUIRE(std::get<0>(workers)->basis());CHECK(std::get<0>(workers)->basis()->describe_basis()=="fixture basis: column 0");
    Requirements incompatible;incompatible.output.representation={"required-shape"};
    auto conditional=accepted(prepare_provider(select_provider(lp,Method{{"endpoint"},{}},incompatible)));
    const auto rejected=conditional.prepare(interval_lp(1));
    REQUIRE(std::holds_alternative<Rejection>(rejected));CHECK(std::get<Rejection>(rejected).diagnostics[0].field=="output.representation");
}
TEST_CASE("concrete provider rejects before custom request snapshot or factory") {
    auto snapshots=std::make_shared<int>(0);int factories=0;
    Registry<CounterPort> registry;registry.add({{{"limited"},"1"},[](const CounterRequest& r,const Requirements&)->Capability{
        if(r.value>10)return Diagnostics{{DiagnosticCode::unsupported,"value","too large"}};return Offer{};},
        [&](const CounterRequest&){++factories;return std::make_unique<CounterFixture>(10);}});
    auto provider=accepted(prepare_provider(select_provider(registry,Method{{"limited"},{}})));
    const auto rejected=provider.prepare({11,snapshots});REQUIRE(std::holds_alternative<Rejection>(rejected));
    CHECK(std::get<Rejection>(rejected).diagnostics[0].field=="value");CHECK(*snapshots==0);CHECK(factories==0);
    auto workers=accepted(provider.prepare({3,snapshots})).create();CHECK(*snapshots==1);CHECK(factories==1);
    CHECK(std::get<0>(workers)->run(context())==14);
}

TEST_CASE("generated selection stays conditional and immutable callback configuration survives") {
    auto snapshots=std::make_shared<int>(0);
    auto provider=[&]{
        int source=20;auto immutable=std::make_shared<const int>(source);
        Registry<CounterPort> registry;
        registry.add({{{"owned"},"7"},[](const CounterRequest&,const Requirements&)->Capability{return Offer{};},
            [immutable](const CounterRequest&){return std::make_unique<CounterFixture>(*immutable);}});
        auto p=accepted(prepare_provider(select_provider(registry,Method{{"owned"},"7"})));
        source=99;CHECK(source==99);return p;
    }();
    auto first=accepted(provider.prepare({2,snapshots})).create();
    auto second=accepted(provider.prepare({8,snapshots})).create();
    CHECK(std::get<0>(first)->run(context())==23);CHECK(std::get<0>(second)->run(context())==29);
    CHECK(*snapshots==2);
    Registry<LPPort> lp;lp.add(endpoint_registration());Requirements full;full.output.completeness=Completeness::established;
    auto conditional=accepted(prepare_provider(select_provider(lp,Method{{"endpoint"},{}},full)));
    auto denied=conditional.prepare(interval_lp(1));REQUIRE(std::holds_alternative<Rejection>(denied));
    CHECK(std::get<Rejection>(denied).diagnostics[0].field=="output.completeness");
}

TEST_CASE("generated LP workspace receives caller cancellation context") {
    class CancellationAwareWorkspace final : public LPWorkspace {
    public:
        ProgramOutcome do_solve(const LinearProgram& program,const ExecutionContext& execution) override {
            if (execution.cancellation.stop_requested())
                return ProgramResult{Termination::cancelled,
                    {program.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},
                    {},{},"generated solve observed cancellation"};
            return ProgramResult{Termination::completed,
                {program.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},
                {},{},"generated solve did not observe cancellation"};
        }
    };
    Registry<LPPort> registry;
    registry.add({{{"cancellation-aware"},"1"},interval_capability,
        [](const LinearProgram&){return std::make_unique<CancellationAwareWorkspace>();}});
    const auto provider=accepted(prepare_provider(select_provider(registry,Method{{"cancellation-aware"},"1"})));
    const auto prepared=accepted(provider.prepare(interval_lp(2.0)));
    auto workspaces=prepared.create();

    auto execution=context();
    const auto completed=std::get<ProgramResult>(std::get<0>(workspaces)->run(execution));
    CHECK(completed.termination==Termination::completed);
    CHECK(completed.raw_diagnostics=="generated solve did not observe cancellation");

    std::stop_source cancellation;
    cancellation.request_stop();
    execution.cancellation=cancellation.get_token();
    const auto result=std::get<ProgramResult>(std::get<0>(workspaces)->run(execution));
    CHECK(result.termination==Termination::cancelled);
    CHECK(result.raw_diagnostics=="generated solve observed cancellation");
}

TEST_CASE("checked generated declarations can precede a rejecting fixed dependency without snapshots") {
    auto snapshots=std::make_shared<int>(0);int copies=0;
    struct Probe {
        int* copies;
        explicit Probe(int& n):copies(&n){}
        Probe(const Probe& p):copies(p.copies){++*copies;}
        std::unique_ptr<LPWorkspace> operator()(const LinearProgram&)const{return std::make_unique<EndpointWorkspace>();}
    };
    Registry<LPPort> lp;auto entry=endpoint_registration();entry.factory=Probe{copies};lp.add(std::move(entry));copies=0;
    auto providers=accepted(check_providers(select_provider(lp,Method{{"endpoint"},{}})));
    Registry<CounterPort> fixed;fixed.add({{{"counter"},"1"},[](const CounterRequest&,const Requirements&)->Capability{return Offer{};},
        [](const CounterRequest&){return std::make_unique<CounterFixture>(10);}});
    CounterRequest request{20,snapshots};auto input=interval_input(1);input.variables[0].upper.reset();auto unsupported=publish(input);
    auto rejected=check_pipeline(select(fixed,Method{{"counter"},{}},request),select(lp,Method{{"endpoint"},{}},unsupported));
    REQUIRE(std::holds_alternative<Rejection>(rejected));CHECK(std::get<Rejection>(rejected).diagnostics[0].field=="lp.domain");
    CHECK(copies==0);CHECK(*snapshots==0);CHECK(providers.provenance()[0].actual->id.value=="endpoint");
}
