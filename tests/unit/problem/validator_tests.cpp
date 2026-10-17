#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/problem/validator.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <limits>
#include <functional>
#include <algorithm>
#include <cmath>
using namespace csl;
using namespace csl::problem;
using namespace csl::registry;
namespace {
template<class T,class... R> T accepted(std::variant<T,R...> result) {
    REQUIRE(std::holds_alternative<T>(result)); return std::get<T>(std::move(result));
}
ResolutionContext context() {return {UncertaintyStructure::stage_product_uncoupled,{},{}};}
StrategyAdmission prepare_strategy(const ResolvedProblem& p,const StrategyRegistry& registry,
    const StrategyConfiguration& configuration,const Requirements& requirements={},
    std::optional<std::string> version={}) {
    FamilyRequest family{"nominal_open_loop",p.identity(),FamilyTarget::candidate_relaxation,
        {1e-8,1e-8},Assurance::numerical,{},{}};
    return csl::problem::prepare_strategy(p,registry,configuration,family,requirements,std::move(version));
}
Problem scalar() {
    return {{"authored"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{0}},{1,1,{1}},{1,0,{}},{0}}},{}}),{0,1},KnownInitial{{2}},
        ContinuousDomain{{Singleton{{3}}}},{UniversalSet{1},UniversalSet{1}},{},{},InformationPattern::nominal_open_loop,LinearTerminal{{1},0}};
}
std::vector<std::byte> unhex(std::string_view text) {
    std::vector<std::byte> result;
    auto digit=[](char c){return c>='0' && c<='9'?c-'0':c-'a'+10;};
    for(std::size_t i=0;i<text.size();i+=2) result.push_back(static_cast<std::byte>(16*digit(text[i])+digit(text[i+1])));
    return result;
}
const std::string scalar_digest="167962d4127c26ae199032551dceb32e8a04bfed653cfd44e90ad6cc89a36cb4";
const std::string scalar_hex=
    "43534c2d50524f424c454d000000000100000000000000000100000000000000"
    "010000000000000000000000000000000200000000000000003ff00000000000"
    "0000000000000000000100000000000000010000000000000000000000000000"
    "000100000000000000013ff00000000000000000000000000001000000000000"
    "0000000000000000000100000000000000000000000000000000000000000000"
    "0000014000000000000000000000000000000001020000000000000001400800"
    "0000000000000000000000000201000000000000000101000000000000000100"
    "00000000000000000000013ff000000000000000000000000000000000000000"
    "00000000";
class FixedControl final : public LPWorkspace {
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext&) override {
        return ProgramResult{Termination::completed,{p.identity(),MathematicalOutcome::optimal,Unestablished{},{}},Vector{3},{},"literal fixed control"};
    }
};
class BoundControl final : public LPWorkspace {
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext&) override {
        const auto value=*p.variables().at(0).lower;
        return ProgramResult{Termination::completed,{p.identity(),MathematicalOutcome::optimal,Unestablished{},{}},Vector{value},{} ,"singleton bound provider"};
    }
};
class Forward final : public SynthesisWorkspace {
    std::unique_ptr<BoundWorkspace<LPPort>> control_;
public:
    explicit Forward(std::unique_ptr<BoundWorkspace<LPPort>> control):control_(std::move(control)) {}
    SynthesisResult solve(const ResolvedProblem& problem,const FamilyRequest&,const ExecutionContext& c) override {
        const auto& p=*problem.description();
        const auto u=*accepted(control_->run(c)).primal;
        const auto model=accepted(model::snapshot(*p.model,p.times));
        const auto x0=std::get<KnownInitial>(p.initial).point;
        const auto x1=accepted(model.step({0},x0,u,{}));
        const auto objective=accepted(optimization::snapshot(p.objective));
        const auto cost=accepted(optimization::evaluate(objective,x1));
        const auto id=problem.identity();
        return SynthesisResult{Termination::completed,{id,MathematicalOutcome::undetermined,Unestablished{},{}},{},{},
            {{{id,{x0,x1},{u},cost},{id,SymbolicArgument{"fixture", "fixed control trajectory"}}}}, {}};
    }
};
struct Strategies {
    Registry<LPPort> lp;
    StrategyRegistry strategies;
    std::shared_ptr<int> factories=std::make_shared<int>(0);
    Strategies() {
        lp.add({{{"endpoint-a"},"1"},[](const LinearProgram&,const Requirements&) -> Capability {return Offer{};},
            [count=factories](const LinearProgram&) {++*count;return std::make_unique<FixedControl>();}});
        lp.add({{{"endpoint-b"},"1"},[](const LinearProgram&,const Requirements&) -> Capability {return Offer{};},
            [count=factories](const LinearProgram&) {++*count;return std::make_unique<BoundControl>();}});
        for(const std::string profile:{"forward","inverse","compact","full-dimensional","nominal","stagewise","square-safe"}) strategies.add({{{profile},"1"},
            [profile](const StrategyRequest& request,const Requirements& requirements) -> Capability {
                const auto& p=*request.problem.description();
                if(profile=="inverse" && std::get<LinearStage>(p.model->dynamics.stages).A.values[0]==0)
                    return Diagnostics{{DiagnosticCode::unsupported,"strategy.inverse","requires nonsingular scalar A"}};
                if(profile=="forward" || profile=="inverse" || profile=="nominal") {
                    auto diagnostics=check_nominal_profile(p,false,requirements.output.assurance);
                    if(!diagnostics.empty()) return diagnostics;
                }
                if(profile=="stagewise" && p.temporal && p.temporal->joint_map.rows)
                    return Diagnostics{{DiagnosticCode::unsupported,"strategy.history","requires stagewise constraints"}};
                if(profile=="square-safe") {
                    const auto* residual=std::get_if<ResidualNormTerminal>(&p.objective);
                    // Pure narrow arithmetic admission; no reformulation allocation/eigensolver.
                    if(!residual || residual->map.rows!=1 || residual->map.cols!=1 || residual->target!=Vector{0} ||
                        std::abs(residual->map.values[0])>std::sqrt(std::numeric_limits<double>::max()/2))
                        return Diagnostics{{DiagnosticCode::unsupported,"strategy.objective","requires a scalar zero-target residual with representable squared coefficient"}};
                }
                if(profile=="compact" || profile=="full-dimensional") {
                    const auto& set=std::get<ContinuousDomain>(p.controls).stages.at(0);
                    bool supported=false;
                    if(profile=="compact") {
                        supported=std::holds_alternative<Singleton>(set) || std::holds_alternative<EmptySet>(set);
                        if(const auto* h=std::get_if<SetHandle>(&set)) supported=h->metadata.bounded==SetProperty::yes;
                    } else if(const auto* h=std::get_if<SetHandle>(&set)) {
                        const auto metadata=accepted(sets::from_handle(*h)).metadata();
                        if(metadata->affine_dimension) {
                            const auto* dimension=std::get_if<sets::DimensionValue>(&metadata->affine_dimension->claim.value);
                            // This fixture requires dimension established by the representation definition.
                            supported=dimension && dimension->value==metadata->set.dimension && metadata->affine_dimension->origin==sets::DimensionOrigin::definition;
                        }
                    } else supported=std::holds_alternative<UniversalSet>(set);
                    if(!supported) return Diagnostics{{DiagnosticCode::unsupported,"strategy.domain",profile+" restriction not established"}};
                }
                return Offer{};
            },
            [this](const StrategyRequest& request,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
                auto operand=std::make_shared<const LinearProgram>(std::get<LinearProgram>(optimization::make_linear_program(
                    {{request.problem.identity(),{"fixed-control"}},{0},0,{0,1,{0},{},{}},{{3,3}},{}})));
                auto checked=check_pipeline(select(lp,Method{request.configuration.lp,{}},*operand));
                if(auto* r=std::get_if<Rejection>(&checked)) return *r;
                return compose_strategy(std::get<CheckedPipeline<LPPort>>(checked),[operand,count=factories](auto workers,const StrategyRequest&,const Requirements&) {
                    (void)operand; ++*count; return std::make_unique<Forward>(std::move(std::get<0>(workers)));
                });
            }});
    }
};
StrategyConfiguration configuration(const char* strategy="forward",const char* lp="endpoint-a") {
    return {{strategy},{lp},{},{},{},{},{},{},{}};
}
void edit_model(Problem& p,const std::function<void(SystemModel&)>& edit) {
    auto model=std::make_shared<SystemModel>(*p.model);edit(*model);p.model=std::move(model);
}
Problem nonfuel_affine_substitution() {
    auto p=scalar();
    edit_model(p,[](SystemModel& model) {auto& stage=std::get<LinearStage>(model.dynamics.stages);stage.A.values[0]=2;stage.offset={1};});
    return p;
}
ResolvedProblem published(const Problem& p) {return accepted(resolve(p,context()));}
void diagnostic(const Problem& p,DiagnosticCode code) {
    const auto result=resolve(p,context());REQUIRE(std::holds_alternative<Diagnostic>(result));CHECK(std::get<Diagnostic>(result).code==code);
}
Problem zero() {
    return {{"zero"},std::make_shared<const SystemModel>(SystemModel{{{0,0,0},TimeDomain::discrete,
        LinearStage{{0,0,{}},{0,0,{}},{0,0,{}},{}}},{}}),{0},KnownInitial{{}},ContinuousDomain{{}},
        {UniversalSet{0}},{},{},InformationPattern::nominal_open_loop,LinearTerminal{{},0}};
}
numeric::MatrixView matrix(Matrix value) {return accepted(numeric::snapshot(value));}
numeric::VectorView vector(Vector value) {return accepted(numeric::snapshot_vector(value));}
SetHandle equality_set() {
    return accepted(sets::make_h({{"equality"},1,{}},{matrix({0,1,{}}),vector({}),matrix({1,1,{1}}),vector({3})},
        sets::AffineDimensionClaim{sets::DimensionValue{0},Unestablished{}})).as_handle();
}
}
TEST_CASE("resolved singular scalar data owns exact mathematical bytes and literal identity") {
    auto input=scalar(); auto producer=std::make_shared<SystemModel>(*input.model);input.model=producer;
    const auto p=accepted(resolve(input,context()));
    std::get<LinearStage>(producer->dynamics.stages).A.values[0]=99;
    std::get<KnownInitial>(input.initial).point[0]=999;
    CHECK(p.identity().value=="csl.problem.v1.sha256:"+scalar_digest);
    CHECK(p.canonical_bytes()==unhex(scalar_hex));
    CHECK(p.canonical_bytes().size()==260);
    const auto terminal=accepted(p.model().step({0},Vector{2},Vector{3},{}));
    CHECK(terminal==Vector{3});CHECK(accepted(optimization::evaluate(p.objective(),terminal))==3);
    CHECK(p.authored_label()=="authored");CHECK(p.description()->id==p.identity());
}
TEST_CASE("resolved publication distinguishes invalid data and unsupported semantic intake") {
    auto p=scalar();p.times={0,0};
    auto malformed=resolve(p,context());REQUIRE(std::holds_alternative<Diagnostic>(malformed));
    CHECK(std::get<Diagnostic>(malformed).code==DiagnosticCode::invalid_input);
    auto c=context();c.uncertainty=UncertaintyStructure::correlated_history;
    auto unsupported=resolve(p,c);REQUIRE(std::holds_alternative<Diagnostic>(unsupported));
    CHECK(std::get<Diagnostic>(unsupported).code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostic>(unsupported).field=="problem.uncertainty.structure");
}
TEST_CASE("actual strategy admission rejects inverse assumptions without changing mathematical identity") {
    const auto p=accepted(resolve(scalar(),context()));Strategies registry;
    auto rejection=prepare_strategy(p,registry.strategies,configuration("inverse"));
    REQUIRE(std::holds_alternative<Rejection>(rejection));CHECK(*registry.factories==0);
    for(const char* backend:{"endpoint-a","endpoint-b"}) {
        auto plan=accepted(prepare_strategy(p,registry.strategies,configuration("forward",backend)));
        CHECK(plan.problem().identity()==p.identity());
        CHECK(plan.preparation().provenance()[1].actual->id.value==backend);
        const auto answer=accepted(plan.preparation().create()->run({}));
        REQUIRE(answer.incumbents.size()==1);CHECK(answer.incumbents[0].witness.states.back()==Vector{3});
        CHECK(answer.incumbents[0].witness.original_objective==3);CHECK(answer.incumbents[0].witness.problem==p.identity());CHECK_FALSE(answer.family);
    }
    CHECK(p.identity().value=="csl.problem.v1.sha256:"+scalar_digest);
}
TEST_CASE("nonfuel affine problem substitutes independent LP providers through the public strategy path") {
    const auto p=accepted(resolve(nonfuel_affine_substitution(),context()));Strategies registry;
    for(const char* backend:{"endpoint-a","endpoint-b"}) {
        auto plan=accepted(prepare_strategy(p,registry.strategies,configuration("forward",backend)));
        CHECK(plan.problem().identity()==p.identity());
        CHECK(plan.preparation().provenance()[1].actual->id.value==backend);
        const auto answer=accepted(plan.preparation().create()->run({}));
        REQUIRE(answer.incumbents.size()==1);
        CHECK(answer.incumbents[0].witness.controls==std::vector<Vector>{{3}});
        CHECK(answer.incumbents[0].witness.states==std::vector<Vector>{{2},{8}});
        CHECK(answer.incumbents[0].witness.original_objective==8);
        CHECK(answer.incumbents[0].witness.problem==p.identity());
        CHECK_FALSE(answer.family);
    }
}
TEST_CASE("uncertain initial quantifiers retain identity and reject before workspace creation") {
    Strategies registry;
    const auto known=published(scalar());
    std::vector<ResolvedProblem> uncertain;
    for(const auto quantifier:{SetQuantifier::existential,SetQuantifier::universal}) {
        auto input=scalar();
        input.initial=InitialSet{Singleton{{2}},quantifier};
        auto resolved=published(input);
        CHECK(std::get<InitialSet>(*resolved.initial().description()).quantifier==quantifier);
        CHECK(resolved.identity()!=known.identity());
        const auto admission=prepare_strategy(resolved,registry.strategies,configuration("forward"));
        REQUIRE(std::holds_alternative<Rejection>(admission));
        const auto& diagnostics=std::get<Rejection>(admission).diagnostics;
        REQUIRE(diagnostics.size()==1);
        CHECK(diagnostics[0].code==DiagnosticCode::unsupported);
        CHECK(diagnostics[0].field=="initial");
        CHECK(*registry.factories==0);
        uncertain.push_back(std::move(resolved));
    }
    CHECK(uncertain[0].identity()!=uncertain[1].identity());

    const auto admitted=accepted(prepare_strategy(known,registry.strategies,configuration("forward")));
    CHECK(*registry.factories==0);
    const auto result=accepted(admitted.preparation().create()->run({}));
    REQUIRE(result.incumbents.size()==1);
    CHECK(result.incumbents[0].witness.states==std::vector<Vector>{{2},{3}});
    CHECK(result.incumbents[0].witness.original_objective==3);
}
TEST_CASE("resolved content SHA256 matches independent padding and multiblock literal vectors") {
    const std::pair<std::size_t,const char*> vectors[]={
        {0,"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
        {55,"9f4390f8d30c2dd92ec9f095b65e2b9ae9b0a925a5258e241c9f1e910f734318"},
        {56,"b35439a4ac6f0948b6d6f9e3c6af0f5f590ce20f1bde7090ef7970686ec6738a"},
        {63,"7d3e74a05d7db15bce4ad9ec0658ea98e3f06eeecf16b4c6fff2da457ddc2f34"},
        {64,"ffe054fe7ae0cb6dc65c3af9b61d5209f439851db43d0ba5997337df154668eb"},
        {65,"635361c48bb9eab14198e76ea8ab7f1a41685d6ad62aa9146d301d4f17eb0ae0"},
        {1000,"41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3"}};
    for(const auto& [size,digest]:vectors) {
        std::vector<std::byte> bytes(size,std::byte{0x61});
        const auto content=accepted(snapshot_content(bytes));CHECK(hex(content.digest())==digest);CHECK(content.bytes().size()==size);
    }
    const auto abc=accepted(snapshot_content(unhex("616263")));
    CHECK(hex(abc.digest())=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
}
TEST_CASE("zero-dimensional publication has independent literal bytes and survives all producer owners") {
    const auto p=published(zero());
    const auto expected=unhex("43534c2d50524f424c454d00000000010000000000000000000000000000000000000000000000000000000000000000010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010100000000000000000000000000000000000000000000000000000000000000000000000000");
    CHECK(p.canonical_bytes()==expected);CHECK(p.canonical_bytes().size()==186);
    CHECK(p.identity().value=="csl.problem.v1.sha256:2320a9f596bfa8f5bdd8aa6d272ca96fe5ff229411b65e1ab3e6f469a27f815e");
    auto copy=p;auto rvalue=std::move(copy);CHECK(copy.identity()==p.identity());CHECK(rvalue.identity()==p.identity());
    const auto description=[] {return published(scalar()).description();}();
    CHECK(std::get<KnownInitial>(description->initial).point==Vector{2});
    const auto owned=[] {return published(scalar()).objective();}();
    CHECK(accepted(optimization::evaluate(owned,Vector{3}))==3);
    auto labelled=scalar();labelled.id={"independently allocated label"};CHECK(published(labelled).identity()==published(scalar()).identity());
}
TEST_CASE("changed scalar dynamics has an independently fixed digest and terminal cost") {
    auto input=scalar();edit_model(input,[](auto& m){std::get<LinearStage>(m.dynamics.stages).A.values={1};});
    const auto p=published(input);
    CHECK(p.identity().value=="csl.problem.v1.sha256:695f976378c20b642302b5d1af88e656bdd50c1828824a92c0088ecc6364f1dc");
    const auto terminal=accepted(p.model().step({0},Vector{2},Vector{3},{}));CHECK(terminal==Vector{5});
    CHECK(accepted(optimization::evaluate(p.objective(),terminal))==5);
}
TEST_CASE("one immutable dynamics model serves distinct constrained objective requests") {
    const auto shared_model = std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{2}},{1,1,{1}},{1,0,{}},{0}}},{}});
    Problem first{{"first-request"},shared_model,{0,1},KnownInitial{{1}},
        ContinuousDomain{{Singleton{{2}}}},{UniversalSet{1},Singleton{{4}}},{},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{1},0}};
    Problem second{{"second-request"},shared_model,{0,1},KnownInitial{{1}},
        ContinuousDomain{{Singleton{{5}}}},{UniversalSet{1},Singleton{{7}}},{},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{-2},20}};

    auto first_context=context();
    first_context.objective_policy.numerical={1e-4,2e-4};
    auto second_context=context();
    second_context.objective_policy.numerical={1e-9,3e-9};
    const auto first_resolved=accepted(resolve(first,first_context));
    const auto second_resolved=accepted(resolve(second,second_context));

    CHECK(first.model==shared_model);
    CHECK(second.model==shared_model);
    CHECK((first_resolved.model().dimensions()==Dimensions{1,1,0}));
    CHECK((second_resolved.model().dimensions()==Dimensions{1,1,0}));
    CHECK(first_resolved.identity()!=second_resolved.identity());
    CHECK(first_resolved.objective().policy().numerical.absolute_tolerance==1e-4);
    CHECK(first_resolved.objective().policy().numerical.relative_tolerance==2e-4);
    CHECK(second_resolved.objective().policy().numerical.absolute_tolerance==1e-9);
    CHECK(second_resolved.objective().policy().numerical.relative_tolerance==3e-9);

    // x[1] = 2*x[0] + u[0]: the two requests define distinct feasible
    // singleton terminal sections in the joint (state, control) coordinates.
    const auto first_terminal=accepted(first_resolved.model().step({0},Vector{1},Vector{2},{}));
    const auto second_terminal=accepted(second_resolved.model().step({0},Vector{1},Vector{5},{}));
    CHECK(first_terminal==Vector{4});
    CHECK(second_terminal==Vector{7});
    CHECK(std::get<Singleton>(first_resolved.constraints().states()->at(1)).point==Vector{4});
    CHECK(std::get<Singleton>(second_resolved.constraints().states()->at(1)).point==Vector{7});
    CHECK(std::get<Singleton>(std::get<ContinuousDomain>(*first_resolved.controls().description()).stages[0]).point==Vector{2});
    CHECK(std::get<Singleton>(std::get<ContinuousDomain>(*second_resolved.controls().description()).stages[0]).point==Vector{5});
    CHECK(accepted(optimization::evaluate(first_resolved.objective(),first_terminal))==4);
    CHECK(accepted(optimization::evaluate(second_resolved.objective(),second_terminal))==6);
    CHECK_FALSE(first_terminal==std::get<Singleton>(second_resolved.constraints().states()->at(1)).point);
    CHECK_FALSE(second_terminal==std::get<Singleton>(first_resolved.constraints().states()->at(1)).point);

    // Resolving under per-request settings must leave both authored requests
    // and the shared immutable dynamics payload untouched.
    CHECK(first.model==shared_model);
    CHECK(second.model==shared_model);
    CHECK(std::get<LinearStage>(shared_model->dynamics.stages).A.values==Vector{2});
    CHECK(std::get<LinearStage>(shared_model->dynamics.stages).B.values==Vector{1});
    CHECK(std::get<Singleton>(first.states[1]).point==Vector{4});
    CHECK(std::get<Singleton>(second.states[1]).point==Vector{7});
    CHECK(std::get<Singleton>(std::get<ContinuousDomain>(first.controls).stages[0]).point==Vector{2});
    CHECK(std::get<Singleton>(std::get<ContinuousDomain>(second.controls).stages[0]).point==Vector{5});
    CHECK(std::get<LinearTerminal>(first.objective).coefficients==Vector{1});
    CHECK(std::get<LinearTerminal>(second.objective).coefficients==Vector{-2});
    CHECK(std::get<LinearTerminal>(first.objective).offset==0);
    CHECK(std::get<LinearTerminal>(second.objective).offset==20);
}
TEST_CASE("content roots match literals and distinguish bytes from display paths") {
    auto bytes=unhex("31");auto content=accepted(snapshot_content(bytes));bytes[0]=std::byte{0x32};
    CHECK(hex(content.digest())=="6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b");
    CHECK(content.bytes()[0]==std::byte{0x31});
    std::vector<ContentBinding> bindings{{"dynamics/B/constant",content,"missing://location-one"}};
    auto c=context();c.external_content=bindings;
    const auto first=accepted(resolve(scalar(),c));
    auto expected=unhex(scalar_hex);expected.resize(expected.size()-8);
    const auto suffix=unhex("0000000000000001000000000000001364796e616d6963732f422f636f6e7374616e7400000000000000016b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b");
    expected.insert(expected.end(),suffix.begin(),suffix.end());CHECK(first.canonical_bytes()==expected);
    CHECK(first.canonical_bytes().size()==327);
    CHECK(first.identity().value=="csl.problem.v1.sha256:ade9632753f13fa2790071c5fcff8dea139ebb28314a2f2942a9de0ace1e7c79");
    bindings[0].source_location="nonexistent://other";CHECK(accepted(resolve(scalar(),c)).identity()==first.identity());
    bindings[0].content=accepted(snapshot_content(bytes));
    CHECK(accepted(resolve(scalar(),c)).identity().value=="csl.problem.v1.sha256:de2be880f1fa27c99593d7b0f3c90b475050452a1d7b2c0ab3a68960b6413d68");
    CHECK(first.content()->at(0).source_location=="missing://location-one");
    CHECK(first.content()->at(0).content.bytes()[0]==std::byte{0x31});
    auto bad=snapshot_content(bytes,content.digest());REQUIRE(std::holds_alternative<Diagnostic>(bad));CHECK(std::get<Diagnostic>(bad).field=="problem.content.digest");
    CHECK(accepted(snapshot_content(unhex("31"),content.digest())).digest()==content.digest());
    auto moved=std::move(content);CHECK(content.digest()==moved.digest());
    bindings.push_back({"A",moved,""});c.external_content=bindings;const auto sorted=accepted(resolve(scalar(),c));
    std::reverse(bindings.begin(),bindings.end());c.external_content=bindings;CHECK(accepted(resolve(scalar(),c)).identity()==sorted.identity());
    CHECK(sorted.content()->front().key=="A");
    for(const std::string& key:std::vector<std::string>{"","space key","a\\b",std::string(1,static_cast<char>(0xff))}) {
        bindings={{key,moved,""}};c.external_content=bindings;const auto result=resolve(scalar(),c);
        REQUIRE(std::holds_alternative<Diagnostic>(result));CHECK(std::get<Diagnostic>(result).code==DiagnosticCode::invalid_input);
    }
    bindings={{"same",moved,""},{"same",moved,""}};c.external_content=bindings;
    REQUIRE(std::holds_alternative<Diagnostic>(resolve(scalar(),c)));
}
TEST_CASE("boundary validation preserves distinct invalid unsupported and numerical publication outcomes") {
    using Edit=std::function<void(Problem&)>;
    const std::vector<Edit> invalid={
        [](auto& p){p.model.reset();},[](auto& p){p.times={0,0};},[](auto& p){p.times={};},
        [](auto& p){edit_model(p,[](auto& m){std::get<LinearStage>(m.dynamics.stages).B.values={};});},
        [](auto& p){edit_model(p,[](auto& m){m.dynamics.stages=std::vector<LinearStage>{};});},
        [](auto& p){p.states.pop_back();},[](auto& p){p.controls=ContinuousDomain{};},
        [](auto& p){p.initial=KnownInitial{{1,2}};},[](auto& p){p.objective=LinearTerminal{{1,2},0};},
        [](auto& p){p.objective=LinearTerminal{{std::numeric_limits<double>::infinity()},0};},
        [](auto& p){p.information=static_cast<InformationPattern>(42);},
        [](auto& p){edit_model(p,[](auto& m){m.dynamics.time_domain=static_cast<TimeDomain>(42);});},
        [](auto& p){p.initial=InitialSet{UniversalSet{1},SetQuantifier::unspecified};},
        [](auto& p){p.temporal=TemporalConstraints{{1,3,{0,1},{3},{1}},{{0,1}}};}
    };
    for(std::size_t i=0;i<invalid.size();++i) {CAPTURE(i);auto p=scalar();invalid[i](p);diagnostic(p,DiagnosticCode::invalid_input);}
    auto continuous=scalar();edit_model(continuous,[](auto& m){m.dynamics.time_domain=TimeDomain::continuous;});diagnostic(continuous,DiagnosticCode::unsupported);
    struct Opaque final:SetPayload {};
    auto opaque=scalar();opaque.states[0]=SetHandle{{1,{"opaque"},SetProperty::unknown,SetProperty::unknown,SetProperty::unknown},std::make_shared<Opaque>(),{"opaque"}};
    diagnostic(opaque,DiagnosticCode::unsupported);
    auto missing=context();missing.uncertainty=UncertaintyStructure::unspecified;
    REQUIRE(std::holds_alternative<Diagnostic>(resolve(scalar(),missing)));
    for(auto structure:{UncertaintyStructure::correlated_history,UncertaintyStructure::fixed_parameter,UncertaintyStructure::initial_external_coupling,UncertaintyStructure::state_or_parameter_dependent_dynamics}) {
        auto p=scalar();p.times={};auto c=context();c.uncertainty=structure;const auto result=resolve(p,c);
        REQUIRE(std::holds_alternative<Diagnostic>(result));CHECK(std::get<Diagnostic>(result).code==DiagnosticCode::unsupported);
        CHECK(std::get<Diagnostic>(result).field=="problem.uncertainty.structure");
    }
}
TEST_CASE("finite mixed and empty domains publish exact authored choices without convex relaxation") {
    auto p=scalar();p.controls=FiniteDomain{1,{{-1},{1},{-1}}};const auto finite=published(p);
    CHECK(std::get<FiniteDomain>(*finite.controls().description()).catalogue==std::vector<Vector>{{-1},{1},{-1}});
    CHECK(finite.identity()!=published(scalar()).identity());
    p.controls=FiniteDomain{1,{{1},{-1},{-1}}};const auto reordered=published(p);CHECK(reordered.identity()!=finite.identity());
    CHECK(std::get<FiniteDomain>(*reordered.controls().description()).catalogue==std::vector<Vector>{{1},{-1},{-1}});
    p.controls=FiniteDomain{1,{{-1},{1}}};const auto unique=published(p);CHECK(unique.identity()!=finite.identity());
    CHECK(std::get<FiniteDomain>(*unique.controls().description()).catalogue==std::vector<Vector>{{-1},{1}});
    p.controls=FiniteDomain{1,{{-2},{1},{-1}}};const auto changed_entry=published(p);CHECK(changed_entry.identity()!=finite.identity());
    CHECK(std::get<FiniteDomain>(*changed_entry.controls().description()).catalogue[0]==Vector{-2});
    p.controls=FiniteDomain{1,{}};CHECK(std::get<FiniteDomain>(*published(p).controls().description()).catalogue.empty());
    p.states={EmptySet{1},UniversalSet{1}};CHECK(std::holds_alternative<EmptySet>(published(p).constraints().states()->front()));
    p.temporal=TemporalConstraints{{1,3,{0,0},{},{}},{{1,1}}};CHECK(published(p).constraints().temporal()->bounds->at(0).lower==1);
    auto mixed=scalar();edit_model(mixed,[](auto& m){m.dynamics.dimensions.control=2;std::get<LinearStage>(m.dynamics.stages).B={1,2,{2,3}};});
    mixed.controls=MixedDomain{{{Singleton{{4}}}},{1,{{-1},{1},{-1}}}};const auto resolved=published(mixed);
    CHECK(accepted(resolved.model().step({0},Vector{2},Vector{4,-1},{}))==Vector{5});
    CHECK(std::get<MixedDomain>(*resolved.controls().description()).discrete.catalogue.size()==3);
    auto t0=zero();t0.controls=FiniteDomain{0,{}};const auto empty=published(t0);t0.controls=FiniteDomain{0,{{}}};
    CHECK(empty.identity()!=published(t0).identity());
}
TEST_CASE("configured restrictions belong to actual strategy admission not mathematical publication") {
    Strategies registry;
    const auto restricted=[&](const Problem& input,const char* strategy,bool admit) {
        const auto p=published(input);const auto result=prepare_strategy(p,registry.strategies,configuration(strategy));
        CHECK(std::holds_alternative<PreparedResolvedStrategy>(result)==admit);CHECK(*registry.factories==0);
    };
    auto p=scalar();p.controls=ContinuousDomain{{UniversalSet{1}}};restricted(p,"compact",false);restricted(p,"full-dimensional",true);
    const auto unknown=accepted(sets::make_h({{"unknown"},1,{}},{matrix({0,1,{}}),vector({}),matrix({0,1,{}}),vector({})})).as_handle();
    CHECK(unknown.metadata.bounded==SetProperty::unknown);
    p.controls=ContinuousDomain{{unknown}};restricted(p,"compact",false);restricted(p,"full-dimensional",false);
    const auto unchecked=accepted(sets::make_h({{"unchecked"},1,{}},{matrix({0,1,{}}),vector({}),matrix({0,1,{}}),vector({})},
        sets::AffineDimensionClaim{sets::DimensionValue{1},Unestablished{}})).as_handle();
    p.controls=ContinuousDomain{{unchecked}};restricted(p,"full-dimensional",false);
    p.controls=ContinuousDomain{{equality_set()}};restricted(p,"full-dimensional",false);
    const auto retained=std::get<SetHandle>(std::get<ContinuousDomain>(*published(p).controls().description()).stages[0]);
    const auto equality=std::get<sets::HRepresentation>(accepted(sets::from_handle(retained)).representation());
    CHECK(equality.equalities(0,0)==1);CHECK(equality.equality_values[0]==3);
    p.controls=ContinuousDomain{{Singleton{{3}}}};restricted(p,"compact",true);restricted(p,"full-dimensional",false);
    const auto vertices=accepted(sets::make_v({{"bounded"},1,{}},{matrix({2,1,{-1,1}}),matrix({0,1,{}})})).as_handle();
    CHECK(vertices.metadata.bounded==SetProperty::yes);p.controls=ContinuousDomain{{vertices}};restricted(p,"compact",true);
    p=scalar();p.controls=FiniteDomain{1,{{3}}};restricted(p,"nominal",false);
    p=scalar();p.controls=MixedDomain{{{Singleton{{3}}}},{0,{{}}}};restricted(p,"nominal",false);
    p=scalar();p.information=InformationPattern::feedback;restricted(p,"nominal",false);
    p=scalar();p.initial=InitialSet{Singleton{{2}},SetQuantifier::existential};restricted(p,"nominal",false);
}
TEST_CASE("quantifiers external roles and matched content remain declared data not a game interpreter") {
    auto p=scalar();edit_model(p,[](auto& m){m.dynamics.dimensions.external=1;std::get<LinearStage>(m.dynamics.stages).E={1,1,{2}};});
    p.external=KnownExternalSequence{{{4}}};const auto known=published(p);
    CHECK(accepted(known.model().step({0},Vector{2},Vector{3},Vector{4}))==Vector{11});
    edit_model(p,[](auto& m){std::get<LinearStage>(m.dynamics.stages).E.values[0]=3;});const auto changed_e=published(p);
    CHECK(changed_e.identity()!=known.identity());CHECK(accepted(changed_e.model().step({0},Vector{2},Vector{3},Vector{4}))==Vector{15});
    p.external=ExogenousExternalInput{{UniversalSet{1}},SetQuantifier::existential};const auto existential=published(p);
    CHECK(existential.identity()!=known.identity());
    CHECK(std::get<ExogenousExternalInput>(**existential.external().description()).quantifier==SetQuantifier::existential);
    p.external=ExogenousExternalInput{{UniversalSet{1}},SetQuantifier::universal};const auto universal=published(p);
    CHECK(universal.identity()!=existential.identity());
    CHECK(std::get<ExogenousExternalInput>(**universal.external().description()).quantifier==SetQuantifier::universal);
    p.initial=InitialSet{Singleton{{2}},SetQuantifier::existential};const auto initial=published(p);
    CHECK(initial.identity()!=universal.identity());CHECK(std::get<InitialSet>(*initial.initial().description()).quantifier==SetQuantifier::existential);
    p.initial=InitialSet{Singleton{{2}},SetQuantifier::universal};const auto initial_universal=published(p);CHECK(initial_universal.identity()!=initial.identity());
    CHECK(std::get<InitialSet>(*initial_universal.initial().description()).quantifier==SetQuantifier::universal);
    p.external=AdversarialExternalInput{{UniversalSet{1}},SetQuantifier::universal,"game/declared-v1"};
    const auto missing=resolve(p,context());REQUIRE(std::holds_alternative<Diagnostic>(missing));CHECK(std::get<Diagnostic>(missing).field=="problem.external.semantics_reference");
    const std::vector<ContentBinding> bindings{{"game/declared-v1",accepted(snapshot_content(unhex("67616d65"))),"display-only"}};
    auto c=context();c.external_content=bindings;const auto game=accepted(resolve(p,c));
    CHECK(std::get<AdversarialExternalInput>(**game.external().description()).semantics_reference=="game/declared-v1");
    Strategies registry;CHECK(std::holds_alternative<Rejection>(prepare_strategy(game,registry.strategies,configuration("nominal"))));CHECK(*registry.factories==0);
    auto t0=zero();t0.external=ExogenousExternalInput{{},SetQuantifier::universal};const auto empty_product=published(t0);
    CHECK(std::get<ExogenousExternalInput>(**empty_product.external().description()).stages.empty());CHECK(empty_product.identity()!=published(zero()).identity());
}
TEST_CASE("temporal full history retains joint coordinates literal multiplication and structural presence") {
    auto p=scalar();p.times={0,1,2,3};p.controls=ContinuousDomain{{UniversalSet{1},UniversalSet{1},UniversalSet{1}}};p.states.assign(4,UniversalSet{1});
    const auto absent=published(p);
    p.temporal=TemporalConstraints{{0,7,{0},{},{}},{}};CHECK(published(p).identity()!=absent.identity());
    p.temporal=TemporalConstraints{{2,7,{0,3,5},{0,3,4,4,6},{-2,1,1,-1,1}},{{7,7},{-.25,.25}}};
    const auto resolved=published(p);const auto history=*resolved.constraints().temporal();
    CHECK(resolved.constraints().joint_dimension()==7);CHECK(accepted(resolved.constraints().state_offset({3}))==3);CHECK(accepted(resolved.constraints().control_offset({2}))==6);
    CHECK(accepted(numeric::multiply(history.joint_map,vector({1,0,0,8,1,0,1.25})))==Vector{7,.25});
    CHECK(accepted(numeric::multiply(history.joint_map,vector({1,0,0,8,1,0,.5})))==Vector{7,-.5});
    CHECK(history.bounds->at(0).lower==7);CHECK(history.bounds->at(1).upper==.25);
    p.temporal->joint_map.values[0]=-3;const auto changed_map=published(p);CHECK(changed_map.identity()!=resolved.identity());CHECK(changed_map.constraints().temporal()->joint_map(0,0)==-3);
    p.temporal->joint_map.values[0]=-2;p.temporal->bounds[1].upper=.5;const auto changed_bound=published(p);CHECK(changed_bound.identity()!=resolved.identity());CHECK(changed_bound.constraints().temporal()->bounds->at(1).upper==.5);
    CHECK(history.joint_map(0,0)==-2);CHECK(history.bounds->at(1).upper==.25);
    Strategies registry;CHECK(std::holds_alternative<Rejection>(prepare_strategy(resolved,registry.strategies,configuration("stagewise"))));CHECK(*registry.factories==0);
}
TEST_CASE("objective authority separates PSD rejection numerical stop and explicit reformulation") {
    auto p=scalar();p.objective=QuadraticTerminal{{1,1,{-1}},{0},0};diagnostic(p,DiagnosticCode::invalid_input);
    p.objective=QuadraticTerminal{{1,1,{-1e-12}},{0},0};diagnostic(p,DiagnosticCode::unsupported);
    p.objective=QuadraticTerminal{{1,1,{std::numeric_limits<double>::max()}},{0},0};
    auto c=context();c.objective_policy.numerical={std::numeric_limits<double>::max(),1};const auto stopped=resolve(p,c);
    REQUIRE(std::holds_alternative<OperationStopped>(stopped));CHECK(std::get<OperationStopped>(stopped).reason==StopReason::numerical_failure);
    p.objective=QuadraticTerminal{{1,1,{0}},{0},7};const auto constant=published(p);CHECK(accepted(optimization::evaluate(constant.objective(),Vector{999}))==7);
    p.objective=ResidualNormTerminal{{2,1,{1,2}},{0,0}};const auto rectangular=published(p);CHECK(accepted(optimization::evaluate(rectangular.objective(),Vector{0}))==0);
    p.objective=ResidualNormTerminal{{1,1,{1e200}},{0}};const auto large=published(p);CHECK(accepted(optimization::evaluate(large.objective(),Vector{1}))==1e200);
    const auto transform=optimization::square_residual_norm(large.objective());REQUIRE(std::holds_alternative<OperationStopped>(transform));
    CHECK(std::get<OperationStopped>(transform).reason==StopReason::numerical_failure);
    Strategies registry;CHECK(std::holds_alternative<Rejection>(prepare_strategy(large,registry.strategies,configuration("square-safe"))));CHECK(*registry.factories==0);
    auto small=scalar();small.objective=ResidualNormTerminal{{1,1,{2}},{0}};
    CHECK(std::holds_alternative<PreparedResolvedStrategy>(prepare_strategy(published(small),registry.strategies,configuration("square-safe"))));CHECK(*registry.factories==0);
    c=context();c.objective_policy.numerical={1e-6,1e-6};CHECK(accepted(resolve(p,c)).identity()==large.identity());
}
TEST_CASE("prepared actual dependency graph survives registries and rejected late dependencies create nothing") {
    const auto p=published(scalar());Strategies registry;
    CHECK(std::holds_alternative<Rejection>(prepare_strategy(p,registry.strategies,configuration("forward","missing"))));CHECK(*registry.factories==0);
    CHECK(std::holds_alternative<Rejection>(prepare_strategy(p,registry.strategies,configuration(),{},"missing-version")));CHECK(*registry.factories==0);
    const auto prepared=[] {Strategies temporary;return accepted(prepare_strategy(published(scalar()),temporary.strategies,configuration()));}();
    const auto answer=accepted(prepared.preparation().create()->run({}));REQUIRE(answer.incumbents.size()==1);
    CHECK(answer.incumbents[0].witness.states==std::vector<Vector>{{2},{3}});CHECK(answer.incumbents[0].witness.controls==std::vector<Vector>{{3}});
    CHECK(answer.outcome.subject==prepared.problem().identity());CHECK_FALSE(answer.family);
}
TEST_CASE("native set logical layout normalizes while representation row order and metadata remain explicit") {
    auto p=scalar();edit_model(p,[](auto& m){m.dynamics.dimensions.control=2;std::get<LinearStage>(m.dynamics.stages).B={1,2,{1,1}};});
    const auto handle=[](numeric::MatrixView coefficients,const char* label) {
        return accepted(sets::make_h({{label},2,{"a","b"}},{coefficients,vector({3,7}),matrix({0,2,{}}),vector({})})).as_handle();
    };
    const auto row=handle(matrix({2,2,{1,2,3,4}}),"row");
    const Vector column{1,3,2,4};const auto col=handle(accepted(numeric::snapshot(numeric::DenseInput{column,2,2,1,2,numeric::DenseLayout::column_major})),"col");
    const auto sparse=handle(accepted(numeric::snapshot(SparseMatrix{2,2,{0,2,4},{0,1,0,1},{1,2,3,4}})),"sparse");
    const Vector padding{1,99,2,99,3,99,4};const auto strided=handle(accepted(numeric::snapshot(numeric::DenseInput{padding,2,2,4,2,numeric::DenseLayout::strided})),"strided");
    p.controls=ContinuousDomain{{row}};const auto expected=published(p);
    for(const auto& h:{col,sparse,strided}) {
        p.controls=ContinuousDomain{{h}};const auto actual=published(p);CHECK(actual.identity()==expected.identity());CHECK(actual.canonical_bytes()==expected.canonical_bytes());
        const auto retained=std::get<SetHandle>(std::get<ContinuousDomain>(*actual.controls().description()).stages[0]);
        CHECK(std::get<sets::HRepresentation>(accepted(sets::from_handle(retained)).representation()).inequalities(1,0)==3);
    }
    const auto vrow=accepted(sets::make_v({{"v-row"},2,{}},{matrix({2,2,{1,2,3,4}}),matrix({0,2,{}})})).as_handle();
    const auto vcolumn=accepted(sets::make_v({{"v-col"},2,{}},{accepted(numeric::snapshot(numeric::DenseInput{column,2,2,1,2,numeric::DenseLayout::column_major})),matrix({0,2,{}})})).as_handle();
    p.controls=ContinuousDomain{{vrow}};const auto vlayout=published(p);p.controls=ContinuousDomain{{vcolumn}};
    CHECK(published(p).canonical_bytes()==vlayout.canonical_bytes());
    CHECK(std::get<sets::VRepresentation>(accepted(sets::from_handle(vcolumn)).representation()).vertices(1,1)==4);
    p.controls=ContinuousDomain{{handle(matrix({2,2,{3,4,1,2}}),"reordered")}};CHECK(published(p).identity()!=expected.identity());
    auto elementary=scalar();elementary.controls=ContinuousDomain{{Singleton{{3}}}};
    auto native=scalar();native.controls=ContinuousDomain{{accepted(sets::make_singleton({{"point"},1,{}},vector({3}))).as_handle()}};
    CHECK(published(native).identity()!=published(elementary).identity());
    auto vertices=scalar();const auto vhandle=[](Vector v) {return accepted(sets::make_v({{"v"},1,{}},{matrix({2,1,std::move(v)}),matrix({0,1,{}})})).as_handle();};
    vertices.controls=ContinuousDomain{{vhandle({-1,1})}};const auto v1=published(vertices);
    vertices.controls=ContinuousDomain{{vhandle({1,-1})}};CHECK(published(vertices).identity()!=v1.identity());
    auto bad=row;bad.metadata.dimension=3;p.controls=ContinuousDomain{{bad}};diagnostic(p,DiagnosticCode::invalid_input);
}
TEST_CASE("sparse native H and V gaps empty rows and signed zero retain literal root identities") {
    auto p=scalar();edit_model(p,[](auto& m){m.dynamics.dimensions.control=5;std::get<LinearStage>(m.dynamics.stages).B={1,5,{1,1,1,1,1}};});
    const auto dense=matrix({4,5,{0,2,0,-3,0, 0,0,0,0,0, 4,0,0,0,0, 0,5,0,0,0}});
    const auto sparse=accepted(numeric::snapshot(SparseMatrix{4,5,{0,2,2,4,5},{1,3,0,2,1},{2,-3,4,-0.0,5}}));
    // Independent struct/hashlib reference over literal mathematical fields, not product output.
    const char* digests[]={"4c9cfc7a18bc7c22e828511decdc7a2d3b37ca7749a41de0ab2b58abe8045b16",
                           "1f60feadeece0620d9283079541758e43b51315494e979edc5c10efd989a50da"};
    for(int representation=0;representation<2;++representation) {
        CAPTURE(representation);
        const auto handle=[&](numeric::MatrixView coefficients) {
            if(representation==0) return accepted(sets::make_h({{"gaps-H"},5,{}},
                {coefficients,vector({7,8,9,10}),matrix({0,5,{}}),vector({})})).as_handle();
            return accepted(sets::make_v({{"gaps-V"},5,{}},{coefficients,matrix({0,5,{}})})).as_handle();
        };
        p.controls=ContinuousDomain{{handle(dense)}};const auto logical=published(p);
        p.controls=ContinuousDomain{{handle(sparse)}};const auto actual=published(p);
        CHECK(actual.canonical_bytes()==logical.canonical_bytes());
        CHECK(actual.canonical_bytes().size()==(representation==0?525:477));
        CHECK(actual.identity().value==std::string("csl.problem.v1.sha256:")+digests[representation]);
        CHECK(logical.identity()==actual.identity());
        const auto retained=accepted(sets::from_handle(std::get<SetHandle>(std::get<ContinuousDomain>(*actual.controls().description()).stages[0])));
        const auto coefficients=representation==0?std::get<sets::HRepresentation>(retained.representation()).inequalities:
                                                  std::get<sets::VRepresentation>(retained.representation()).vertices;
        const auto csr=std::get<numeric::CsrInput>(coefficients.descriptor());
        CHECK(csr.rows==4);CHECK(csr.cols==5);CHECK(csr.values.size()==5);
        CHECK(csr.row_offsets[1]==2);CHECK(csr.row_offsets[2]==2);CHECK(csr.column_indices[3]==2);
        CHECK(std::signbit(csr.values[3]));CHECK(coefficients(0,3)==-3);CHECK(coefficients(1,4)==0);
        CHECK(coefficients(2,0)==4);CHECK(coefficients(3,1)==5);CHECK(coefficients(3,4)==0);
        if(representation==0) CHECK(std::get<sets::HRepresentation>(retained.representation()).upper_bounds[3]==10);
        CHECK(accepted(actual.model().step({0},Vector{2},Vector{1,2,3,4,5},{}))==Vector{15});
    }
}
TEST_CASE("zero-width native vertices retain row counts without nonexistent coordinate traversal") {
    auto p=zero();const auto rows=std::numeric_limits<std::size_t>::max();
    const auto vertices=accepted(sets::make_v({{"many-empty-points"},0,{}},{matrix({rows,0,{}}),matrix({0,0,{}})})).as_handle();
    p.states={vertices};const auto data=published(p);CHECK(data.canonical_bytes().size()==219);
    const auto h=std::get<SetHandle>(data.constraints().states()->front());
    const auto retained=std::get<sets::VRepresentation>(accepted(sets::from_handle(h)).representation());
    CHECK(retained.vertices.rows()==rows);CHECK(retained.vertices.cols()==0);CHECK(data.identity()!=published(zero()).identity());
}
TEST_CASE("signed zero normalizes and dormant provider structure remains mathematical identity") {
    auto p=scalar();const auto baseline=published(p);
    edit_model(p,[](auto& m){auto& s=std::get<LinearStage>(m.dynamics.stages);s.A.values[0]=-0.0;s.offset[0]=-0.0;});
    p.times[0]=-0.0;std::get<LinearTerminal>(p.objective).offset=-0.0;CHECK(published(p).identity()==baseline.identity());
    edit_model(p,[](auto& m){m.dynamics.stages=std::vector{std::get<LinearStage>(m.dynamics.stages)};});
    const auto indexed=published(p);CHECK(indexed.identity()!=baseline.identity());CHECK(accepted(indexed.model().step({0},Vector{2},Vector{3},{}))==Vector{3});
    auto t0=scalar();t0.times={0};t0.controls=ContinuousDomain{};t0.states={UniversalSet{1}};const auto dormant=published(t0);
    edit_model(t0,[](auto& m){std::get<LinearStage>(m.dynamics.stages).A.values[0]=7;});
    CHECK(published(t0).identity()!=dormant.identity());CHECK(published(t0).model().horizon()==0);
    edit_model(t0,[](auto& m){m.observations={{ObservationStage{{1,1,{2}},{1,1,{0}},{1,0,{}},{1,0,{}},{0}}, {}}};});
    const auto empty_schedule=published(t0);CHECK(accepted(empty_schedule.model().sample_count({0}))==0);
    edit_model(t0,[](auto& m){std::get<ObservationStage>(m.observations[0].coefficients).state_map.values[0]=3;});
    CHECK(published(t0).identity()!=empty_schedule.identity());
    edit_model(t0,[](auto& m){std::get<ObservationStage>(m.observations[0].coefficients).state_map.values[0]=std::numeric_limits<double>::quiet_NaN();});
    diagnostic(t0,DiagnosticCode::invalid_input);
}
TEST_CASE("observation maps events initial values dynamics and objective each change retained semantics") {
    auto p=scalar();edit_model(p,[](auto& m){m.observations={{ObservationStage{{1,1,{2}},{1,1,{0}},{1,0,{}},{1,0,{}},{1}},
        {{{0},{{0},ObservationTiming::before_decision},{{0},ObservationTiming::before_decision},{}}}}};});
    const auto observation=published(p);CHECK(accepted(observation.model().observe({0},{0},Vector{2},{},{},{})).values==Vector{5});
    edit_model(p,[](auto& m){std::get<ObservationStage>(m.observations[0].coefficients).state_map.values[0]=3;});
    CHECK(published(p).identity()!=observation.identity());CHECK(accepted(published(p).model().observe({0},{0},Vector{2},{},{},{})).values==Vector{7});
    p=*observation.description();edit_model(p,[](auto& m){m.observations[0].schedule[0].available_at={{1},ObservationTiming::before_decision};});
    const auto late=published(p);CHECK(late.identity()!=observation.identity());CHECK(accepted(late.model().observation({0},{0})).metadata.available_time==1);
    edit_model(p,[](auto& m){m.observations[0].schedule[0].state_stage={2};});diagnostic(p,DiagnosticCode::invalid_input);
    p=*observation.description();edit_model(p,[](auto& m){auto& s=m.observations[0].schedule[0];s.measured_at={{1},ObservationTiming::before_decision};});diagnostic(p,DiagnosticCode::invalid_input);
    const auto baseline=published(scalar());
    p=scalar();edit_model(p,[](auto& m){std::get<LinearStage>(m.dynamics.stages).B.values[0]=2;});
    CHECK(published(p).identity()!=baseline.identity());CHECK(accepted(published(p).model().step({0},Vector{2},Vector{3},{}))==Vector{6});
    p=scalar();edit_model(p,[](auto& m){std::get<LinearStage>(m.dynamics.stages).offset[0]=4;});
    CHECK(published(p).identity()!=baseline.identity());CHECK(accepted(published(p).model().step({0},Vector{2},Vector{3},{}))==Vector{7});
    p=scalar();p.times[1]=2;CHECK(published(p).identity()!=baseline.identity());CHECK(accepted(published(p).model().time({1}))==2);
    p=scalar();p.initial=KnownInitial{{4}};CHECK(published(p).identity()!=baseline.identity());CHECK(std::get<KnownInitial>(*published(p).initial().description()).point==Vector{4});
    p=scalar();p.states[1]=Singleton{{3}};CHECK(published(p).identity()!=baseline.identity());CHECK(std::get<Singleton>(published(p).constraints().states()->at(1)).point==Vector{3});
    p=scalar();p.information=InformationPattern::feedback;CHECK(published(p).identity()!=baseline.identity());CHECK(published(p).description()->information==InformationPattern::feedback);
    p=scalar();p.objective=LinearTerminal{{2},1};CHECK(published(p).identity()!=baseline.identity());CHECK(accepted(optimization::evaluate(published(p).objective(),Vector{3}))==7);
}
