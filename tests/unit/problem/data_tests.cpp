#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/problem/domains.hpp>
#include <csl/problem/constraints.hpp>
#include <csl/problem/initial_information.hpp>

#include <future>
#include <limits>
#include <type_traits>

using namespace csl;
using namespace csl::problem;
static_assert(!std::is_default_constructible_v<ControlDomains>);
static_assert(!std::is_default_constructible_v<Constraints>);
static_assert(!std::is_default_constructible_v<InitialData>);
static_assert(!std::is_default_constructible_v<ExternalData>);

namespace {
template<class T, class... E> T accepted(std::variant<T,E...> result) {
    if (auto error = std::get_if<Diagnostic>(&result)) INFO(error->field << ": " << error->explanation);
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
template<class T> void rejected(const Result<T>& result, const char* field,
                                DiagnosticCode code = DiagnosticCode::invalid_input) {
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    const auto& error = std::get<Diagnostic>(result);
    CHECK(error.code == code);
    CHECK(error.field == field);
    CHECK_FALSE(error.explanation.empty());
}
SystemModel authored(Dimensions d) {
    return {{d,TimeDomain::discrete,LinearStage{
        {d.state,d.state,Vector(d.state*d.state)},
        {d.state,d.control,Vector(d.state*d.control)},
        {d.state,d.external,Vector(d.state*d.external)},Vector(d.state)}}, {}};
}
model::LinearSystem system(Dimensions d = {1,1,0}, std::size_t horizon = 2) {
    Vector times(horizon+1);
    for (std::size_t i=0;i<times.size();++i) times[i]=static_cast<double>(i);
    return accepted(model::snapshot(authored(d),times));
}
sets::SetData interval(const char* id = "interval") {
    return accepted(sets::make_v({{id},1,{}}, {
        accepted(numeric::snapshot(Matrix{2,1,{-1,1}})),
        accepted(numeric::snapshot(Matrix{0,1,{}}))}));
}
TemporalConstraints history() {
    return {{2,7,{0,3,5},{0,3,4,4,6},{-2,1,1,-1,1}},{{7,7},{-0.25,0.25}}};
}
std::vector<AdmissibleSet> states(std::size_t n=1, std::size_t t=2) {
    return std::vector<AdmissibleSet>(t+1,UniversalSet{n});
}
}

// Normalizing elementary sets would erase the empty versus R^0 distinction.
TEST_CASE("zero ports retain elementary and finite action identities") {
    const auto model = system({1,0,0});
    ControlDomain input = ContinuousDomain{{UniversalSet{0},Singleton{{}}}};
    const auto domains = accepted(snapshot_controls(input,model));
    CHECK(domains.dimension()==0);
    CHECK(domains.horizon()==2);
    const auto& stage = std::get<ContinuousDomain>(*domains.description()).stages;
    CHECK(std::get<UniversalSet>(stage[0]).dimension==0);
    CHECK(std::get<Singleton>(stage[1]).point==Vector{});
    std::get<ContinuousDomain>(input).stages[0]=EmptySet{0};
    auto empty = accepted(snapshot_controls(input,model)).description();
    CHECK(std::get<EmptySet>(std::get<ContinuousDomain>(*empty).stages[0]).dimension==0);
    CHECK(std::holds_alternative<UniversalSet>(stage[0]));
    auto one = accepted(snapshot_controls(FiniteDomain{0,{{}}},model)).description();
    auto none = accepted(snapshot_controls(FiniteDomain{0,{}},model)).description();
    CHECK(std::get<FiniteDomain>(*one).catalogue==std::vector<Vector>{{}});
    CHECK(std::get<FiniteDomain>(*none).catalogue.empty());
    auto zero = accepted(snapshot_controls(ContinuousDomain{{Singleton{{0}},Singleton{{0}}}},system())).description();
    CHECK(std::get<Singleton>(std::get<ContinuousDomain>(*zero).stages[0]).point==Vector{0});
}

// An off-by-one or interleaved x/u layout breaks these independent offsets.
TEST_CASE("state and control stages have literal joint offsets and checked boundaries") {
    const auto model = system({2,1,0});
    auto data=accepted(snapshot_constraints(states(2),std::nullopt,model));
    CHECK(data.joint_dimension()==8);
    CHECK(data.coordinates().dimensions.state==2);
    CHECK(data.coordinates().dimensions.control==1);
    CHECK(data.coordinates().horizon==2);
    CHECK(accepted(data.state_offset({0}))==0);
    CHECK(accepted(data.state_offset({1}))==2);
    CHECK(accepted(data.state_offset({2}))==4);
    CHECK(accepted(data.control_offset({0}))==6);
    CHECK(accepted(data.control_offset({1}))==7);
    rejected(data.state_offset({3}),"problem.state_stage");
    rejected(data.control_offset({2}),"problem.control_stage");
    rejected(data.control_offset({std::numeric_limits<std::size_t>::max()}),"problem.control_stage");
    for (const auto count : {1U,3U})
        rejected(snapshot_controls(ContinuousDomain{std::vector<AdmissibleSet>(count,UniversalSet{1})},model),"problem.controls.stages");
    for (const auto count : {2U,4U})
        rejected(snapshot_constraints(std::vector<AdmissibleSet>(count,UniversalSet{2}),{},model),"problem.states.stages");
    rejected(snapshot_constraints(states(1),{},model),"problem.states[0].dimension");
    const auto terminal=system({2,0,0},0);
    auto zero=accepted(snapshot_constraints(states(2,0),{},terminal));
    CHECK(zero.joint_dimension()==2);
    CHECK(accepted(zero.state_offset({0}))==0);
    rejected(zero.control_offset({0}),"problem.control_stage");
    CHECK(accepted(snapshot_controls(FiniteDomain{0,{}},terminal)).horizon()==0);
    const auto huge=system({0,std::numeric_limits<std::size_t>::max(),0});
    rejected(snapshot_constraints(states(0),{},huge),"problem.temporal.coordinates");
}

// Producer mutation, deduplication, convexification or a wrong mixed split breaks this.
TEST_CASE("finite and mixed domains retain catalogue order and explicit dimensions") {
    ControlDomain producer=FiniteDomain{1,{{-1},{1},{-1}}};
    const auto retained=accepted(snapshot_controls(std::move(producer),system())).description();
    std::get<FiniteDomain>(producer).catalogue.assign(100,Vector{42});
    CHECK(std::get<FiniteDomain>(*retained).catalogue==std::vector<Vector>{{-1},{1},{-1}});
    MixedDomain mixed{{{UniversalSet{2},Singleton{{3,4}}}},{1,{{-2},{2}}}};
    const auto data=accepted(snapshot_controls(mixed,system({1,3,0}))).description();
    CHECK(std::get<MixedDomain>(*data).discrete.dimension==1);
    CHECK(std::get<MixedDomain>(*data).discrete.catalogue==std::vector<Vector>{{-2},{2}});
    CHECK(std::get<Singleton>(std::get<MixedDomain>(*data).continuous.stages[1]).point==Vector{3,4});
    mixed.discrete.catalogue.clear();
    CHECK(std::get<MixedDomain>(*accepted(snapshot_controls(mixed,system({1,3,0}))).description()).discrete.catalogue.empty());
    mixed.discrete.dimension=4;
    rejected(snapshot_controls(mixed,system({1,3,0})),"problem.controls.dimension");
    rejected(snapshot_controls(FiniteDomain{2,{}},system()),"problem.controls.dimension");
    rejected(snapshot_controls(FiniteDomain{1,{{1,2}}},system()),"problem.controls.catalogue[0]");
    rejected(snapshot_controls(FiniteDomain{1,{{std::numeric_limits<double>::infinity()}}},system()),"problem.controls.catalogue[0]");
    rejected(snapshot_controls(ContinuousDomain{{UniversalSet{2},UniversalSet{1}}},system()),"problem.controls.stages[0].dimension");
    auto degenerate=accepted(snapshot_controls(MixedDomain{{{UniversalSet{1},UniversalSet{1}}},{0,{{}}}},system())).description();
    CHECK(std::get<MixedDomain>(*degenerate).discrete.dimension==0);
    auto finite_only=accepted(snapshot_controls(MixedDomain{{{UniversalSet{0},UniversalSet{0}}},{1,{{2}}}},system())).description();
    CHECK(std::get<MixedDomain>(*finite_only).discrete.catalogue==std::vector<Vector>{{2}});
}

TEST_CASE("initial information retains point versus quantified singleton after producer mutation") {
    InitialInformation producer=KnownInitial{{2}};
    auto point=accepted(snapshot_initial(std::move(producer),system())).description();
    std::get<KnownInitial>(producer).point[0]=99;
    CHECK(std::get<KnownInitial>(*point).point==Vector{2});
    for (auto q : {SetQuantifier::existential,SetQuantifier::universal}) {
        auto set=accepted(snapshot_initial(InitialSet{Singleton{{2}},q},system())).description();
        CHECK(std::get<InitialSet>(*set).quantifier==q);
        CHECK(std::get<Singleton>(std::get<InitialSet>(*set).set).point==Vector{2});
    }
    rejected(snapshot_initial(InitialSet{UniversalSet{1}},system()),"problem.initial.quantifier");
    rejected(snapshot_initial(InitialSet{UniversalSet{1},static_cast<SetQuantifier>(99)},system()),"problem.initial.quantifier");
    rejected(snapshot_initial(KnownInitial{{1,2}},system()),"problem.initial.dimension");
    rejected(snapshot_initial(KnownInitial{{std::numeric_limits<double>::quiet_NaN()}},system()),"problem.initial.point");
    rejected(snapshot_initial(InitialSet{UniversalSet{2},SetQuantifier::universal},system()),"problem.initial.dimension");
    rejected(snapshot_initial(InitialSet{Singleton{{std::numeric_limits<double>::infinity()}},SetQuantifier::universal},system()),"problem.initial.point");
}

// Full, partial or missing observation data must not convert a set into knowledge.
TEST_CASE("observation channels do not redefine initial information") {
    for (const auto channels : {0,1,2}) {
        auto raw=authored({2,0,0});
        if (channels) {
            const auto rows=channels==1 ? 2U : 1U;
            ObservationStage maps{{rows,2,channels==1 ? Vector{1,0,0,1} : Vector{1,0}},
                {rows,0,{}},{rows,0,{}},{rows,0,{}},Vector(rows)};
            ObservationSample sample{{0},{{0},ObservationTiming::before_decision},
                {{0},ObservationTiming::before_decision},{}};
            raw.observations={Observation{maps,{sample}}};
        }
        const auto model=accepted(model::snapshot(raw,Vector{0,1,2}));
        auto data=accepted(snapshot_initial(InitialSet{UniversalSet{2},SetQuantifier::universal},model)).description();
        CHECK(std::get<InitialSet>(*data).quantifier==SetQuantifier::universal);
        CHECK(std::get<UniversalSet>(std::get<InitialSet>(*data).set).dimension==2);
        CHECK(accepted(snapshot_initial(KnownInitial{{2,3}},model)).description()->index()==0);
    }
}

TEST_CASE("external roles and known forcing remain explicit including zero stages and zero ports") {
    const auto model=system({1,0,1});
    std::optional<ExternalInput> producer=KnownExternalSequence{{{3},{-4}}};
    auto data=accepted(snapshot_external(std::move(producer),model));
    std::get<KnownExternalSequence>(*producer).stages[0][0]=99;
    CHECK(data.horizon()==2);
    CHECK(data.dimension()==1);
    CHECK(std::get<KnownExternalSequence>(**data.description()).stages==std::vector<Vector>{{3},{-4}});
    auto absent=accepted(snapshot_external({},system({1,0,0}))).description();
    CHECK_FALSE(absent->has_value());
    auto present=accepted(snapshot_external(KnownExternalSequence{{{}, {}}},system({1,0,0}))).description();
    CHECK(std::get<KnownExternalSequence>(**present).stages==std::vector<Vector>{{},{}});
    for (auto q : {SetQuantifier::existential,SetQuantifier::universal}) {
        auto ex=accepted(snapshot_external(ExogenousExternalInput{{UniversalSet{1},EmptySet{1}},q},model)).description();
        CHECK(std::get<ExogenousExternalInput>(**ex).quantifier==q);
        CHECK(std::holds_alternative<EmptySet>(std::get<ExogenousExternalInput>(**ex).stages[1]));
        auto zero=accepted(snapshot_external(ExogenousExternalInput{{},q},system({1,0,1},0))).description();
        CHECK(std::get<ExogenousExternalInput>(**zero).stages.empty());
        CHECK(std::get<ExogenousExternalInput>(**zero).quantifier==q);
    }
    producer=AdversarialExternalInput{{UniversalSet{1},UniversalSet{1}},SetQuantifier::universal,"game/policy-information-v1"};
    auto adversary=accepted(snapshot_external(std::move(producer),model)).description();
    std::get<AdversarialExternalInput>(*producer).semantics_reference="changed";
    CHECK(std::get<AdversarialExternalInput>(**adversary).semantics_reference=="game/policy-information-v1");
    CHECK(std::get<AdversarialExternalInput>(**adversary).quantifier==SetQuantifier::universal);
    auto zero_adversary=accepted(snapshot_external(AdversarialExternalInput{{},SetQuantifier::existential,"empty/game"},system({1,0,0},0))).description();
    CHECK(std::get<AdversarialExternalInput>(**zero_adversary).semantics_reference=="empty/game");
}

TEST_CASE("malformed external information is distinguished from unsupported profile") {
    const auto model=system({1,0,1});
    rejected(snapshot_external({},model),"problem.external.port");
    rejected(snapshot_external(KnownExternalSequence{{{1}}},model),"problem.external.stages");
    rejected(snapshot_external(KnownExternalSequence{{{1,2},{3}}},model),"problem.external.stages[0].dimension");
    rejected(snapshot_external(KnownExternalSequence{{{std::numeric_limits<double>::infinity()},{3}}},model),"problem.external.stages[0].point");
    rejected(snapshot_external(ExogenousExternalInput{{UniversalSet{1},UniversalSet{1}}},model),"problem.external.quantifier");
    rejected(snapshot_external(ExogenousExternalInput{{UniversalSet{1},UniversalSet{1}},static_cast<SetQuantifier>(9)},model),"problem.external.quantifier");
    rejected(snapshot_external(ExogenousExternalInput{{UniversalSet{1}},SetQuantifier::universal},model),"problem.external.stages");
    rejected(snapshot_external(ExogenousExternalInput{{UniversalSet{2},UniversalSet{1}},SetQuantifier::universal},model),"problem.external.stages[0].dimension");
    rejected(snapshot_external(AdversarialExternalInput{{UniversalSet{1},UniversalSet{1}},SetQuantifier::universal,{}},model),"problem.external.semantics_reference");
}

// Reused factor identity is not correlation; V endpoints are not a nonconvex set.
TEST_CASE("exogenous Cartesian factors retain endpoints and unknown unbounded bounded metadata") {
    const auto unknown=accepted(sets::make_h({{"unknown"},1,{}},{
        accepted(numeric::snapshot(Matrix{0,1,{}})),accepted(numeric::snapshot_vector({})),
        accepted(numeric::snapshot(Matrix{0,1,{}})),accepted(numeric::snapshot_vector({}))}));
    const auto universal=accepted(sets::make_universal({{"universal"},1,{}}));
    auto property=accepted(snapshot_external(ExogenousExternalInput{{unknown.as_handle(),universal.as_handle(),interval().as_handle()},SetQuantifier::universal},system({1,0,1},3))).description();
    const auto& factors=std::get<ExogenousExternalInput>(**property).stages;
    CHECK(std::get<SetHandle>(factors[0]).metadata.bounded==SetProperty::unknown);
    CHECK(std::get<SetHandle>(factors[1]).metadata.bounded==SetProperty::no);
    CHECK(std::get<SetHandle>(factors[2]).metadata.bounded==SetProperty::yes);
    for (bool reuse : {true,false}) {
        auto retained=[&] {
            auto left=interval("left").as_handle();
            auto right=reuse ? left : interval("right").as_handle();
            std::optional<ExternalInput> input=ExogenousExternalInput{{left,right},SetQuantifier::universal};
            auto result=accepted(snapshot_external(input,system({1,0,1}))).description();
            std::get<ExogenousExternalInput>(*input).stages.clear();
            return result;
        }();
        const auto& stages=std::get<ExogenousExternalInput>(**retained).stages;
        auto a=std::get<sets::VRepresentation>(accepted(sets::from_handle(std::get<SetHandle>(stages[0]))).representation()).vertices;
        auto b=std::get<sets::VRepresentation>(accepted(sets::from_handle(std::get<SetHandle>(stages[1]))).representation()).vertices;
        CHECK(a(0,0)==-1); CHECK(a(1,0)==1); CHECK(b(0,0)==-1); CHECK(b(1,0)==1);
        Vector endpoint_differences;
        for (std::size_t i=0;i<2;++i) for (std::size_t j=0;j<2;++j) endpoint_differences.push_back(a(i,0)-b(j,0));
        CHECK(endpoint_differences==Vector{0,-2,2,0});
        // Diagonal fixed-parameter restriction is different data, not represented here.
        CHECK(Vector{a(0,0)-b(0,0),a(1,0)-b(1,0)}==Vector{0,0});
    }
}

// Dropping nonadjacent rows, aliasing producer CSR or mixing coordinate blocks fails.
TEST_CASE("temporal full history and row bounds outlive every producer and outer handle") {
    auto owners=[] {
        auto input=history();
        auto state=states(1,3);
        state[0]=Singleton{{2}};
        auto data=accepted(snapshot_constraints(state,input,system({1,1,0},3)));
        input.joint_map.values.assign(100,99); input.joint_map.column_indices.clear(); input.bounds.clear();
        std::get<Singleton>(state[0]).point[0]=99;
        return std::pair{*data.temporal(),data.states()};
    }();
    const auto& temporal=owners.first;
    CHECK(std::get<Singleton>((*owners.second)[0]).point==Vector{2});
    CHECK(temporal.joint_map.rows()==2); CHECK(temporal.joint_map.cols()==7);
    CHECK(temporal.bounds->at(0).lower==7); CHECK(temporal.bounds->at(0).upper==7);
    CHECK(temporal.bounds->at(1).lower==-0.25); CHECK(temporal.bounds->at(1).upper==0.25);
    CHECK(accepted(numeric::multiply(temporal.joint_map,accepted(numeric::snapshot_vector(Vector{1,0,0,8,1,0,1.25}))))==Vector{7,0.25});
    CHECK(accepted(numeric::multiply(temporal.joint_map,accepted(numeric::snapshot_vector(Vector{1,0,0,8,1,0,0.5}))))==Vector{7,-0.5});
    const auto csr=std::get<numeric::CsrInput>(temporal.joint_map.descriptor());
    CHECK(std::vector<std::size_t>(csr.row_offsets.begin(),csr.row_offsets.end())==std::vector<std::size_t>{0,3,5});
    CHECK(std::vector<std::size_t>(csr.column_indices.begin(),csr.column_indices.end())==std::vector<std::size_t>{0,3,4,4,6});
}

TEST_CASE("temporal absence zero rows contradiction and interval errors remain distinct") {
    const auto model=system({1,1,0},3);
    CHECK_FALSE(accepted(snapshot_constraints(states(1,3),{},model)).temporal().has_value());
    auto empty=accepted(snapshot_constraints(states(1,3),TemporalConstraints{{0,7,{0},{},{}},{}},model)).temporal();
    REQUIRE(empty.has_value()); CHECK(empty->joint_map.cols()==7); CHECK(empty->bounds->empty());
    auto contradiction=accepted(snapshot_constraints(states(1,3),TemporalConstraints{{2,7,{0,0,0},{},{}},{{1,1},{std::nullopt,std::nullopt}}},model)).temporal();
    CHECK(contradiction->bounds->at(0).lower==1); CHECK_FALSE(contradiction->bounds->at(1).lower.has_value());
    CHECK_FALSE(contradiction->bounds->at(1).upper.has_value());
    auto mutually_exclusive=accepted(snapshot_constraints(states(1,3),TemporalConstraints{{2,7,{0,1,2},{0,0},{1,1}},{{1,1},{2,2}}},model)).temporal();
    CHECK(mutually_exclusive->bounds->at(1).upper==2);
    auto input=history();
    SUBCASE("width") { input.joint_map.cols=6; rejected(snapshot_constraints(states(1,3),input,model),"problem.temporal.shape"); }
    SUBCASE("count") { input.bounds.clear(); rejected(snapshot_constraints(states(1,3),input,model),"problem.temporal.bounds"); }
    SUBCASE("reversed") { input.bounds[1]={1,-1}; rejected(snapshot_constraints(states(1,3),input,model),"problem.temporal.bounds[1]"); }
    SUBCASE("infinite") { input.bounds[0].lower=std::numeric_limits<double>::infinity(); rejected(snapshot_constraints(states(1,3),input,model),"problem.temporal.bounds[0]"); }
    SUBCASE("nan") { input.bounds[0].upper=std::numeric_limits<double>::quiet_NaN(); rejected(snapshot_constraints(states(1,3),input,model),"problem.temporal.bounds[0]"); }
    SUBCASE("CSR") { input.joint_map.row_offsets[0]=1; rejected(snapshot_constraints(states(1,3),input,model),"problem.temporal.shape"); }
    SUBCASE("duplicate CSR columns") { input.joint_map.column_indices[1]=0; rejected(snapshot_constraints(states(1,3),input,model),"problem.temporal.shape"); }
    SUBCASE("nonfinite CSR") { input.joint_map.values[0]=std::numeric_limits<double>::infinity(); rejected(snapshot_constraints(states(1,3),input,model),"problem.temporal.shape"); }
}

TEST_CASE("native set import preserves evidence and rejects mutable foreign payload promises") {
    auto h=accepted(sets::make_h({{"lower-dimensional"},2,{"x","y"}},{
        accepted(numeric::snapshot(Matrix{2,2,{1,0,-1,0}})),accepted(numeric::snapshot_vector(Vector{2,1})),
        accepted(numeric::snapshot(Matrix{1,2,{0,1}})),accepted(numeric::snapshot_vector(Vector{0}))},
        sets::AffineDimensionClaim{sets::DimensionValue{1},CertificateReference{"claim","not-verified"}}));
    auto data=accepted(snapshot_initial(InitialSet{h.as_handle(),SetQuantifier::universal},system({2,0,0}))).description();
    auto retained=accepted(sets::from_handle(std::get<SetHandle>(std::get<InitialSet>(*data).set)));
    CHECK(retained.metadata()->set.bounded==SetProperty::unknown);
    CHECK(retained.metadata()->affine_dimension->origin==sets::DimensionOrigin::supplied);
    CHECK(std::get<CertificateReference>(retained.metadata()->affine_dimension->claim.support).verifier=="not-verified");
    CHECK(std::get<sets::DimensionValue>(retained.metadata()->affine_dimension->claim.value).value==1);
    auto handle=h.as_handle(); handle.metadata.bounded=SetProperty::yes;
    rejected(snapshot_initial(InitialSet{handle,SetQuantifier::universal},system({2,0,0})),"problem.initial.sets.handle.metadata");
    struct Foreign : SetPayload {};
    handle=h.as_handle(); handle.payload=std::make_shared<Foreign>();
    rejected(snapshot_initial(InitialSet{handle,SetQuantifier::universal},system({2,0,0})),"problem.initial.sets.handle.payload",DiagnosticCode::unsupported);
    handle.payload.reset();
    rejected(snapshot_initial(InitialSet{handle,SetQuantifier::universal},system({2,0,0})),"problem.initial.sets.handle.payload",DiagnosticCode::unsupported);
}

// Each reader owns retained storage; producer/outer owners are already destroyed.
TEST_CASE("copied moved and assigned handles keep independent immutable reader ownership") {
    auto owners=[] {
        ControlDomain raw=FiniteDomain{1,{{-1},{1}}};
        auto a=accepted(snapshot_controls(raw,system()));
        auto b=a;
        auto moved=std::move(a);
        auto assigned=accepted(snapshot_controls(FiniteDomain{1,{{9}}},system()));
        assigned=b;
        raw=FiniteDomain{1,{{100}}};
        CHECK(std::get<FiniteDomain>(*a.description()).catalogue==std::vector<Vector>{{-1},{1}});
        return std::vector{b.description(),moved.description(),assigned.description()};
    }();
    std::vector<std::future<Vector>> readers;
    for (const auto& owner : owners) readers.push_back(std::async(std::launch::async,[owner] {
        const auto& entries=std::get<FiniteDomain>(*owner).catalogue;
        return Vector{entries[0][0],entries[1][0]};
    }));
    owners.clear();
    for (auto& reader : readers) CHECK(reader.get()==Vector{-1,1});
}

TEST_CASE("nominal guard remains capability-only for retained future information") {
    auto raw=std::make_shared<SystemModel>(authored({1,1,0}));
    Problem p{{"nominal"},raw,{0,1},KnownInitial{{0}},ContinuousDomain{{EmptySet{1}}},
        {UniversalSet{1},EmptySet{1}},TemporalConstraints{{0,3,{0},{},{}},{}},{},InformationPattern::nominal_open_loop,LinearTerminal{{0},0}};
    CHECK(check_nominal_profile(p,false,Assurance::numerical).empty());
    std::string field;
    SUBCASE("finite") { p.controls=FiniteDomain{1,{{-1},{1}}}; field="controls"; }
    SUBCASE("mixed") { p.controls=MixedDomain{{{UniversalSet{0}}},{1,{{1}}}}; field="controls"; }
    SUBCASE("set") { p.initial=InitialSet{Singleton{{0}},SetQuantifier::universal}; field="initial"; }
    SUBCASE("external zero-dimensional") { p.external=KnownExternalSequence{{{}}}; field="external"; }
    SUBCASE("external positive zero forcing") { raw->dynamics.dimensions.external=1; std::get<LinearStage>(raw->dynamics.stages).E={1,1,{0}}; p.external=KnownExternalSequence{{{0}}}; field="external"; }
    SUBCASE("feedback") { p.information=InformationPattern::feedback; field="information"; }
    SUBCASE("temporal") { p.temporal=TemporalConstraints{{1,3,{0,0},{},{}},{{0,0}}}; field="temporal"; }
    SUBCASE("continuous") { raw->dynamics.time_domain=TimeDomain::continuous; field="time_domain"; }
    SUBCASE("singular inverse") { field="dynamics.inverse"; }
    const auto errors=check_nominal_profile(p,field=="dynamics.inverse",Assurance::numerical);
    REQUIRE(errors.size()==1); CHECK(errors[0].code==DiagnosticCode::unsupported); CHECK(errors[0].field==field);
}
