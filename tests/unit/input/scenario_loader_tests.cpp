#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/input/scenario_loader.hpp>
#include <string_view>
#include <csl/sets/data.hpp>
#include <cmath>
#include <algorithm>
#include <tuple>
using namespace csl;
using namespace csl::input;
namespace {
LoadResult load(std::string_view text, const LoadOptions& options = {}) {
    return load_scenario(std::as_bytes(std::span(text.data(),text.size())),options);
}
template<class T,class... R> T accepted(std::variant<R...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
constexpr std::string_view minimal=R"({"schema":"csl.scenario/1","horizon":2,"model":{"kind":"linear_discrete","A":[[1]],"B":[[1]]},"initial_state":[0],"controls":{"kind":"box","lower":[0],"upper":[1]},"objective":{"kind":"terminal_distance","target":[1]}})";
std::string root_member(std::string_view addition) {
    auto result=std::string(minimal);result.pop_back();return result+","+std::string(addition)+"}";
}
std::string replace(std::string input,std::string_view from,std::string_view to) {
    const auto at=input.find(from);REQUIRE(at!=std::string::npos);
    input.replace(at,from.size(),to);return input;
}
}
TEST_CASE("explicit nominal profile equals omission while malformed values never fall back") {
    auto omitted=accepted<LoadedScenario>(load(minimal));
    auto explicit_value=accepted<LoadedScenario>(load(root_member(R"("profile":"nominal_discrete_v1")")));
    CHECK(explicit_value.problem().canonical_bytes()==omitted.problem().canonical_bytes());
    CHECK_FALSE(explicit_value.source()->content.digest()==omitted.source()->content.digest());
    for(const auto value:{"null","false","1","[]","{}","\"\"","\"future_profile\"","\"nominal_discret_v1\""}) {
        auto error=accepted<InputFailure>(load(root_member(std::string("\"profile\":")+value)));
        CHECK(error.category==InputCategory::field);CHECK(error.path=="/profile");CHECK(error.expected=="string \"nominal_discrete_v1\"");
    }
}
TEST_CASE("reserved kinds reject at the authored boundary and typos remain malformed") {
    constexpr std::string_view model=R"({"kind":"linear_discrete","A":[[1]],"B":[[1]]})";
    for(const auto kind:{"linear_continuous","affine_continuous","linear_continuous_ltv","affine_continuous_ltv"}) {
        auto text=replace(std::string(minimal),model,std::string("{\"kind\":\"")+kind+"\"}");
        auto error=accepted<UnsupportedInput>(load(text));
        CHECK(error.path=="/model/kind");CHECK(error.expected=="a discrete transition model; continuous-time input is not supported in v1");
    }
    auto typo=accepted<InputFailure>(load(replace(std::string(minimal),"linear_discrete","linear_continous")));
    CHECK(typo.path=="/model/kind");CHECK(typo.expected=="string model kind from the closed v1 discriminator table");
    for(const auto kind:{"finite","mixed"}) {
        auto text=replace(std::string(minimal),R"({"kind":"box","lower":[0],"upper":[1]})",std::string("{\"kind\":\"")+kind+"\"}");
        auto error=accepted<UnsupportedInput>(load(text));CHECK(error.path=="/controls/kind");
        CHECK(error.expected=="continuous control sets; finite and mixed domains are not supported in v1");
    }
    for(const auto kind:{"sum","mixed"}) {
        auto text=replace(std::string(minimal),R"({"kind":"terminal_distance","target":[1]})",std::string("{\"kind\":\"")+kind+"\"}");
        auto error=accepted<UnsupportedInput>(load(text));CHECK(error.path=="/objective/kind");
        CHECK(error.expected=="one original linear, quadratic or residual-norm objective; sums and mixed objectives are not supported in v1");
    }
}
TEST_CASE("root exclusions and profile precede future model interpretation") {
    auto text=replace(root_member(R"("profile":null)"),"linear_discrete","linear_continuous");
    CHECK(accepted<InputFailure>(load(text)).path=="/profile");
    auto conflict=accepted<InputFailure>(load(root_member(R"("initial_information":{})")));
    CHECK(conflict.path=="/initial_information");CHECK(conflict.expected=="initial_state and initial_information must not coexist");
    CHECK(accepted<UnsupportedInput>(load(root_member(R"("external":null)"))).path=="/external");
    auto unknown=accepted<InputFailure>(load(root_member(R"("surprise":0)")));
    CHECK(unknown.path=="/surprise");
    auto wrong=accepted<InputFailure>(load(replace(std::string(minimal),R"({"kind":"linear_discrete","A":[[1]],"B":[[1]]})","null")));
    CHECK(wrong.path=="/model");CHECK(wrong.expected=="object with required string member \"kind\"");
}
TEST_CASE("short nominal input publishes the original norm and real integrator") {
    auto loaded=accepted<LoadedScenario>(load(minimal));
    auto problem=loaded.problem();
    CHECK(problem.model().horizon()==2);
    auto x1=accepted<Vector>(problem.model().step({0},Vector{0},Vector{.25},{}));
    auto x2=accepted<Vector>(problem.model().step({1},x1,Vector{.75},{}));
    CHECK(x2==Vector{1});
    CHECK(accepted<double>(optimization::evaluate(problem.objective(),x2))==0);
    CHECK(accepted<double>(optimization::evaluate(problem.objective(),Vector{0}))==1);
    CHECK(problem.description()->information==InformationPattern::nominal_open_loop);
    CHECK_FALSE(problem.description()->external);
    CHECK(problem.content()->empty());
    CHECK(loaded.source()->content.bytes().size()==minimal.size());
}
TEST_CASE("affine transitions use nonunit times directly and retain provider identity") {
    auto base=replace(std::string(minimal),R"({"kind":"linear_discrete","A":[[1]],"B":[[1]]})",R"({"kind":"affine_discrete","A":[[3]],"B":[[2]],"offset":[-1]})");
    base=replace(base,R"("initial_state":[0])",R"("initial_state":[2])");
    base.pop_back();base+=R"(,"times":[0,2,5]})";
    auto constant=accepted<LoadedScenario>(load(base));
    auto indexed_text=replace(base,R"({"kind":"affine_discrete","A":[[3]],"B":[[2]],"offset":[-1]})",R"({"kind":"affine_discrete_ltv","stages":[{"A":[[3]],"B":[[2]],"offset":[-1]},{"A":[[3]],"B":[[2]],"offset":[-1]}]})");
    auto indexed=accepted<LoadedScenario>(load(indexed_text));
    for(auto p:{constant.problem(),indexed.problem()}) {
        const auto x1=accepted<Vector>(p.model().step({0},Vector{2},Vector{1},{}));
        CHECK(x1==Vector{7});CHECK(accepted<Vector>(p.model().step({1},x1,Vector{-2},{}))==Vector{16});
        CHECK(p.description()->times==Vector{0,2,5});
    }
    CHECK_FALSE(constant.problem().identity()==indexed.problem().identity());
    CHECK(accepted<InputFailure>(load(replace(base,"[0,2,5]","[0,2,2]"))).path=="/times/2");
    CHECK(accepted<InputFailure>(load(replace(base,R"("B":[[2]])",R"("B":[[2],[3]])"))).path=="/model/B");
    CHECK(accepted<InputFailure>(load(replace(base,R"("offset":[-1])",R"("offset":[])"))).path=="/model/offset");
}

TEST_CASE("literal structural identity composes canonical singleton and linear objective") {
    constexpr auto text=R"({"schema":"csl.scenario/1","horizon":1,"model":{"kind":"linear_discrete","A":[[0]],"B":[[1]]},"initial_state":[2],"controls":{"kind":"singleton","point":[3]},"objective":{"kind":"linear","coefficients":[1]}})";
    auto p=accepted<LoadedScenario>(load(text)).problem();
    CHECK(p.identity().value=="csl.problem.v1.sha256:167962d4127c26ae199032551dceb32e8a04bfed653cfd44e90ad6cc89a36cb4");
    CHECK(p.canonical_bytes().size()==260);
    auto spaced=accepted<LoadedScenario>(load(std::string(" \n")+text+"\n"));
    CHECK(spaced.problem().identity()==p.identity());
    CHECK_FALSE(spaced.source()->content.digest()==accepted<LoadedScenario>(load(text)).source()->content.digest());
    auto changed=accepted<LoadedScenario>(load(replace(text,R"("A":[[0]])",R"("A":[[1]])"))).problem();
    CHECK(changed.identity().value=="csl.problem.v1.sha256:695f976378c20b642302b5d1af88e656bdd50c1828824a92c0088ecc6364f1dc");
    CHECK(accepted<Vector>(changed.model().step({0},Vector{2},Vector{3},{}))==Vector{5});
}
TEST_CASE("quadratic and rectangular residual objectives retain original costs") {
    constexpr auto old=R"({"kind":"terminal_distance","target":[1]})";
    auto q=accepted<LoadedScenario>(load(replace(std::string(minimal),old,R"({"kind":"quadratic","Q":[[2]],"linear":[-6],"offset":9})")));
    CHECK(accepted<double>(optimization::evaluate(q.problem().objective(),Vector{2}))==1);
    auto norm=accepted<LoadedScenario>(load(replace(std::string(minimal),old,R"({"kind":"residual_norm","L":[[1],[0]],"target":[3,-4]})")));
    CHECK(accepted<double>(optimization::evaluate(norm.problem().objective(),Vector{2}))==doctest::Approx(std::sqrt(17.0)));
    auto zero=accepted<LoadedScenario>(load(replace(std::string(minimal),old,R"({"kind":"residual_norm","L":{"rows":0,"cols":1,"values":[]},"target":[]})")));
    CHECK(accepted<double>(optimization::evaluate(zero.problem().objective(),Vector{2}))==0);
    auto bad=accepted<InputFailure>(load(replace(std::string(minimal),old,R"({"kind":"quadratic","Q":[[-2]],"linear":[0]})")));
    REQUIRE(bad.canonical);CHECK(bad.canonical->field=="objective.psd");CHECK(bad.path=="/objective/Q");
}
TEST_CASE("authored domains preserve absent endpoints contradictory rows and V semantics") {
    constexpr auto old=R"({"kind":"box","lower":[0],"upper":[1]})";
    auto all_null=accepted<LoadedScenario>(load(replace(std::string(minimal),old,R"({"kind":"box","lower":[null],"upper":[null]})")));
    const auto set=std::get<SetHandle>(std::get<ContinuousDomain>(all_null.problem().description()->controls).stages[0]);
    const auto h=std::get<sets::HRepresentation>(accepted<sets::SetData>(sets::from_handle(set)).representation());
    CHECK(h.inequalities.rows()==0);CHECK(h.inequalities.cols()==1);
    auto universal=accepted<LoadedScenario>(load(replace(std::string(minimal),old,R"({"kind":"universal"})")));
    CHECK_FALSE(universal.problem().identity()==all_null.problem().identity());
    auto contradiction=accepted<LoadedScenario>(load(replace(std::string(minimal),old,R"({"kind":"polyhedron_h","H":[[1],[-1]],"h":[0,-1],"E":{"rows":0,"cols":1,"values":[]},"e":[]})")));
    CHECK(contradiction.problem().model().horizon()==2);
    for(const auto& [shape,count]:std::initializer_list<std::pair<const char*,std::size_t>>{{R"({"kind":"polyhedron_v","vertices":[[0]],"rays":[[1]]})",1},{R"({"kind":"polyhedron_v","vertices":{"rows":0,"cols":1,"values":[]},"rays":[[1]]})",0}}) {
        auto v=accepted<LoadedScenario>(load(replace(std::string(minimal),old,shape)));
        auto native=accepted<sets::SetData>(sets::from_handle(std::get<SetHandle>(std::get<ContinuousDomain>(v.problem().description()->controls).stages[0])));
        CHECK(std::holds_alternative<sets::VRepresentation>(native.representation()));
        const auto data=std::get<sets::VRepresentation>(native.representation());CHECK(data.vertices.rows()==count);CHECK(data.rays.rows()==1);CHECK(data.rays(0,0)==1);
    }
    auto equality=accepted<LoadedScenario>(load(replace(std::string(minimal),old,R"({"kind":"polyhedron_h","H":{"rows":0,"cols":1,"values":[]},"h":[],"E":[[1],[1]],"e":[0,1]})")));
    auto equality_data=std::get<sets::HRepresentation>(accepted<sets::SetData>(sets::from_handle(std::get<SetHandle>(std::get<ContinuousDomain>(equality.problem().description()->controls).stages[0]))).representation());
    CHECK(equality_data.equalities.rows()==2);CHECK(equality_data.equality_values[0]==0);CHECK(equality_data.equality_values[1]==1);
}
TEST_CASE("T0 indexed dimensions and zero-row matrix widths remain explicit") {
    constexpr auto zero=R"({"schema":"csl.scenario/1","horizon":0,"dimensions":{"state":1,"control":1,"external":0},"model":{"kind":"linear_discrete_ltv","stages":[]},"initial_state":[0],"controls":{"kind":"stages","values":[]},"objective":{"kind":"linear","coefficients":[1]}})";
    auto p=accepted<LoadedScenario>(load(zero)).problem();CHECK(p.model().horizon()==0);CHECK(p.description()->states.size()==1);
    CHECK(std::get<ContinuousDomain>(p.description()->controls).stages.empty());
    auto missing=replace(zero,R"("dimensions":{"state":1,"control":1,"external":0},)","");
    CHECK(accepted<InputFailure>(load(missing)).path=="/dimensions");
    auto r0=accepted<LoadedScenario>(load(R"({"schema":"csl.scenario/1","horizon":1,"model":{"kind":"linear_discrete","A":[],"B":{"rows":0,"cols":1,"values":[]}},"initial_state":[],"controls":{"kind":"singleton","point":[1]},"objective":{"kind":"linear","coefficients":[]}})"));
    CHECK(r0.problem().model().dimensions().control==1);
    CHECK(accepted<Vector>(r0.problem().model().step({0},{},Vector{1},{})).empty());
}

TEST_CASE("requested settings and display metadata are owning intent outside mathematical identity") {
    const auto text=root_member(R"("id":"label","metadata":{"title":"example","description":"retained","state_labels":["x"],"control_labels":["u"],"state_units":["m"],"control_units":["N"],"time_unit":"index"},"run":{"methods":[{"id":"future-method","version":"requested-version"}],"backends":{"lp":{"id":"first"},"convex":{"id":"second","version":"2"},"representation":"chosen-representation"},"witnesses":{"count":3,"distinctness_tolerance":0.25,"directions":[[1],[-1]]},"numerical":{"absolute_tolerance":0.001,"relative_tolerance":0.002},"resources":{"total_threads":4,"outer_workers":2,"threads_per_worker":2,"memory_bytes":1024},"seed":17})");
    auto loaded=accepted<LoadedScenario>(load(text));auto request=loaded.requested_run();auto metadata=loaded.metadata();auto source=loaded.source();
    CHECK(loaded.problem().identity()==accepted<LoadedScenario>(load(minimal)).problem().identity());
    REQUIRE(std::holds_alternative<std::vector<ModuleRequest>>(request->selection));
    CHECK(std::get<std::vector<ModuleRequest>>(request->selection)[0].id.value=="future-method");
    CHECK(request->backends.at(BackendRole::lp).id.value=="first");CHECK_FALSE(request->backends.at(BackendRole::lp).version);
    CHECK(request->representation->value=="chosen-representation");CHECK(request->seed==17);
    CHECK(request->resources->total_threads==4);CHECK(request->witnesses->count==3);
    CHECK((*request->witnesses->directions)[1]==Vector{-1});CHECK(request->numerical->absolute_tolerance==0.001);
    CHECK(source->publication_policy.numerical.absolute_tolerance==1e-8);
    CHECK(metadata->description=="retained");CHECK((*metadata->control_labels)[0]=="u");
    CHECK(accepted<LoadedScenario>(load(replace(text,R"("id":"first")",R"("id":"alternate")"))).problem().identity()==loaded.problem().identity());
    CHECK(accepted<InputFailure>(load(root_member(R"("run":{"comparison":"historical_reachability_vs_joint_trajectory","methods":[{"id":"x"}]})"))).path=="/run/methods");
    CHECK(accepted<InputFailure>(load(root_member(R"("run":{"numerical":{"absolute_tolerance":1}})"))).path=="/run/numerical/relative_tolerance");
    CHECK(accepted<InputFailure>(load(root_member(R"("metadata":{"state_labels":[]})"))).path=="/metadata/state_labels");
}
TEST_CASE("omitted defaults are retained without inventing control bounds or target") {
    auto loaded=accepted<LoadedScenario>(load(minimal));
    const auto records=loaded.defaults();
    auto record=[&](const char* path) {const auto it=std::find_if(records->begin(),records->end(),[&](const auto& d){return d.path==path;});REQUIRE(it!=records->end());return *it;};
    CHECK_FALSE(record("/states").authored);CHECK_FALSE(record("/run").authored);CHECK_FALSE(record("/external").authored);
    CHECK(std::get<ComparisonRequest>(loaded.requested_run()->selection)==ComparisonRequest::historical_reachability_vs_joint_trajectory);
    CHECK(accepted<InputFailure>(load(replace(std::string(minimal),R"(,"target":[1])",""))).path=="/objective/target");
    CHECK(accepted<InputFailure>(load(replace(std::string(minimal),R"(,"lower":[0])",""))).path=="/controls/lower");
    auto explicit_defaults=accepted<LoadedScenario>(load(root_member(R"("times":[0,1,2],"states":{"kind":"universal"},"id":"","metadata":{},"run":{"comparison":"historical_reachability_vs_joint_trajectory"})")));
    CHECK(explicit_defaults.problem().identity()==loaded.problem().identity());
}
TEST_CASE("historical intake retains an explicit nonexecutable record and never invents missing controls") {
    constexpr auto historical=R"({"schema_version":1,"id":"B04-historical","executable":false,"restoration_status":"incomplete_and_inconsistent","unresolved":["controls","model","states","histories"],"execution_gate":"Do not solve","opaque":{"controls":null}})";
    auto h=accepted<HistoricalScenario>(load(historical));CHECK(h.record()->id=="B04-historical");CHECK(h.record()->unresolved.size()==4);
    CHECK(h.record()->execution_gate=="Do not solve");CHECK(h.source()->content.bytes().size()==std::string_view(historical).size());
    CHECK(accepted<InputFailure>(load(replace(historical,"false","true"))).path=="/executable");
    CHECK(accepted<InputFailure>(load(replace(historical,R"(,"execution_gate":"Do not solve")",""))).path=="/execution_gate");
    CHECK(accepted<UnsupportedInput>(load(replace(historical,"B04-historical","unrelated"))).path=="/schema_version");
}
TEST_CASE("strict byte boundary rejects duplicate decoded keys malformed UTF8 and nonfinite or inexact tokens") {
    CHECK(accepted<InputFailure>(load(R"({"a/b":0,"a\u002fb":1})")).path=="/a~1b");
    CHECK(accepted<InputFailure>(load(R"({"x":0,"\u0078":1})")).category==InputCategory::syntax);
    std::string utf8=R"({"id":")";utf8+=char(0xc0);utf8+=R"("})";
    CHECK(accepted<InputFailure>(load(utf8)).category==InputCategory::encoding);
    CHECK(accepted<InputFailure>(load(std::string("\xef\xbb\xbf")+std::string(minimal))).category==InputCategory::encoding);
    CHECK(accepted<InputFailure>(load("{}")).path=="/schema");
    CHECK(accepted<InputFailure>(load("{}")).observed=="missing");
    CHECK(accepted<InputFailure>(load("{}")).expected=="required member");
    CHECK(accepted<InputFailure>(load_scenario({})).category==InputCategory::syntax);
    for(const auto value:{"true","\"1\"","1e999","1e-999","9007199254740993","184467440737095516160"})
        CHECK(std::holds_alternative<InputFailure>(load(replace(std::string(minimal),R"("initial_state":[0])",std::string("\"initial_state\":[")+value+"]"))));
    for(const auto value:{"2.0","-1","true","\"2\""})
        CHECK(accepted<InputFailure>(load(replace(std::string(minimal),R"("horizon":2)",std::string("\"horizon\":")+value))).path=="/horizon");
    CHECK(accepted<InputFailure>(load(replace(std::string(minimal),R"("B":[[1]])",R"("B":[[1]],"guessed_constraint":0)"))).path=="/model/guessed_constraint");
}
TEST_CASE("caller-lowered admission caps and cancellation stop publication") {
    LoadOptions o;o.limits.input_bytes=minimal.size();CHECK(std::holds_alternative<LoadedScenario>(load(minimal,o)));
    CHECK(accepted<InputFailure>(load(std::string(minimal)+" ",o)).category==InputCategory::limit);
    for(const auto field:{&LoadLimits::depth,&LoadLimits::nodes,&LoadLimits::matrix_coefficients,&LoadLimits::dimension,&LoadLimits::horizon,&LoadLimits::expanded_scalars,&LoadLimits::identity_bytes}) {
        o={};o.limits.*field=0;CHECK(accepted<InputFailure>(load(minimal,o)).category==InputCategory::limit);
    }
    o={};o.limits.string_bytes=20;
    CHECK(accepted<InputFailure>(load(root_member("\"id\":\""+std::string(21,'x')+"\""),o)).path=="/id");
    o={};o.limits.description_bytes=3;
    CHECK(accepted<InputFailure>(load(root_member(R"("metadata":{"description":"four"})"),o)).path=="/metadata/description");
    o={};++o.limits.depth;CHECK(accepted<InputFailure>(load(minimal,o)).category==InputCategory::limit);
    std::stop_source stop;stop.request_stop();o={};o.cancellation=stop.get_token();
    CHECK(accepted<OperationStopped>(load(minimal,o)).reason==StopReason::cancelled);
}
TEST_CASE("retained getters own original bytes values and requested intent after input and handle lifetime") {
    const auto retained=[] {
        std::string text=root_member(R"("run":{"seed":41},"metadata":{"title":"owned"})");
        auto value=accepted<LoadedScenario>(load(text));text.assign(text.size(),'x');
        return std::tuple{value.problem(),value.requested_run(),value.metadata(),value.source(),value.defaults()};
    }();
    CHECK(std::get<1>(retained)->seed==41);CHECK(std::get<2>(retained)->title=="owned");CHECK_FALSE(std::get<4>(retained)->empty());
    const auto bytes=std::get<3>(retained)->content.bytes();
    CHECK(accepted<LoadedScenario>(load_scenario(bytes)).problem().identity()==std::get<0>(retained).identity());
    CHECK(accepted<Vector>(std::get<0>(retained).model().step({0},Vector{0},Vector{1},{}))==Vector{1});
}
TEST_CASE("external descriptors are validated but never read and run resource errors remain structured") {
    constexpr auto descriptor=R"({"kind":"external","uri":"file-that-does-not-exist","sha256":"0000000000000000000000000000000000000000000000000000000000000000","rows":1,"cols":1,"layout":"row_major"})";
    auto text=replace(std::string(minimal),"[[1]]",descriptor);
    CHECK(accepted<UnsupportedInput>(load(text)).path=="/model/A");
    CHECK(accepted<InputFailure>(load(replace(text,"row_major","column_major"))).path=="/model/A/layout");
    auto error=accepted<InputFailure>(load(root_member(R"("run":{"resources":{"total_threads":2,"outer_workers":2,"threads_per_worker":2}})")));
    REQUIRE(error.canonical);CHECK(error.canonical->field=="resources");CHECK(error.path=="/run/resources");
    CHECK(accepted<InputFailure>(load(root_member(R"("run":{"seed":-1})"))).path=="/run/seed");
}
TEST_CASE("minimal publication exposes literal matrices constraints and complete sampled histories") {
    auto p=accepted<LoadedScenario>(load(minimal)).problem();const auto d=p.description();auto stage=accepted<model::DynamicsStage>(p.model().stage({0}));
    CHECK(stage.A(0,0)==1);CHECK(stage.B(0,0)==1);CHECK(stage.E.rows()==1);CHECK(stage.E.cols()==0);CHECK(stage.offset[0]==0);
    CHECK(p.model().dimensions().state==1);CHECK(p.model().dimensions().control==1);CHECK(p.model().channel_count()==0);
    CHECK(std::get<KnownInitial>(d->initial).point==Vector{0});REQUIRE(d->states.size()==3);
    for(const auto& state:d->states) CHECK(std::holds_alternative<UniversalSet>(state));
    const auto& controls=std::get<ContinuousDomain>(d->controls).stages;REQUIRE(controls.size()==2);
    auto h=std::get<sets::HRepresentation>(accepted<sets::SetData>(sets::from_handle(std::get<SetHandle>(controls[0]))).representation());
    CHECK(h.inequalities.rows()==2);CHECK(h.inequalities(0,0)==1);CHECK(h.inequalities(1,0)==-1);CHECK(h.upper_bounds[0]==1);CHECK(h.upper_bounds[1]==0);
    const auto objective=std::get<ResidualNormTerminal>(d->objective);CHECK(objective.map.values==Vector{1});CHECK(objective.target==Vector{1});
    for(const auto& u:std::vector<Vector>{{0,1},{1,0},{.25,.75},{0,0}}) {
        const auto first=accepted<Vector>(p.model().step({0},Vector{0},Vector{u[0]},{}));
        const auto last=accepted<Vector>(p.model().step({1},first,Vector{u[1]},{}));
        const bool zero=u==Vector{0,0};CHECK(last==Vector{zero?0.0:1.0});CHECK(accepted<double>(optimization::evaluate(p.objective(),last))==(zero?1.0:0.0));
    }
}
TEST_CASE("stage counts malformed shapes zero-dimensional alternatives and fixed endpoints stay distinct") {
    for(const auto& item:{std::pair{R"("B":[[1]])",R"("B":[[1],[1,2]])"},std::pair{R"("A":[[1]])",R"("A":{"rows":18446744073709551615,"cols":2,"values":[]})"}})
        CHECK(std::holds_alternative<InputFailure>(load(replace(std::string(minimal),item.first,item.second))));
    CHECK(accepted<InputFailure>(load(root_member(R"("states":{"kind":"stages","values":[{"kind":"universal"}]})"))).path=="/states/values");
    CHECK(accepted<InputFailure>(load(replace(std::string(minimal),R"({"kind":"box","lower":[0],"upper":[1]})",R"({"kind":"stages","values":[]})"))).path=="/controls/values");
    CHECK(accepted<InputFailure>(load(replace(std::string(minimal),R"("initial_state":[0],)",""))).path=="/initial_state");
    CHECK(accepted<UnsupportedInput>(load(root_member(R"("observations":[])"))).path=="/observations");
    auto fixed=accepted<LoadedScenario>(load(replace(std::string(minimal),R"("lower":[0])",R"("lower":[1])")));
    auto set=accepted<sets::SetData>(sets::from_handle(std::get<SetHandle>(std::get<ContinuousDomain>(fixed.problem().description()->controls).stages[0])));
    auto h=std::get<sets::HRepresentation>(set.representation());CHECK(h.upper_bounds[0]==1);CHECK(h.upper_bounds[1]==-1);
    constexpr auto zero=R"({"schema":"csl.scenario/1","horizon":0,"model":{"kind":"linear_discrete","A":[],"B":[]},"initial_state":[],"controls":{"kind":"universal"},"states":{"kind":"universal"},"objective":{"kind":"linear","coefficients":[]}})";
    auto universal=accepted<LoadedScenario>(load(zero));auto empty=accepted<LoadedScenario>(load(replace(zero,R"("states":{"kind":"universal"})",R"("states":{"kind":"empty"})")));
    auto singleton=accepted<LoadedScenario>(load(replace(zero,R"("states":{"kind":"universal"})",R"("states":{"kind":"singleton","point":[]})")));
    CHECK_FALSE(universal.problem().identity()==empty.problem().identity());CHECK_FALSE(universal.problem().identity()==singleton.problem().identity());
    CHECK(std::holds_alternative<EmptySet>(empty.problem().description()->states[0]));CHECK(std::holds_alternative<Singleton>(singleton.problem().description()->states[0]));
    CHECK(accepted<InputFailure>(load(std::string(minimal)+" {}")).category==InputCategory::syntax);
    CHECK(accepted<InputFailure>(load("/* comment */"+std::string(minimal))).category==InputCategory::syntax);
    constexpr auto dormant=R"({"schema":"csl.scenario/1","horizon":0,"model":{"kind":"linear_discrete","A":[[1]],"B":{"rows":1,"cols":0,"values":[]}},"initial_state":[0],"controls":{"kind":"universal"},"objective":{"kind":"linear","coefficients":[1]}})";
    CHECK_FALSE(accepted<LoadedScenario>(load(dormant)).problem().identity()==accepted<LoadedScenario>(load(replace(dormant,R"("A":[[1]])",R"("A":[[2]])"))).problem().identity());
}
TEST_CASE("canonical objective policy failures preserve code field and authored path without repair") {
    LoadOptions o;o.objective_policy.assurance=Assurance::validated;
    auto unsupported=accepted<UnsupportedInput>(load(minimal,o));REQUIRE(unsupported.canonical);CHECK(unsupported.canonical->field=="objective.assurance");CHECK(unsupported.path.empty());
    o={};o.objective_policy.numerical.absolute_tolerance=-1;
    auto bad=accepted<InputFailure>(load(minimal,o));REQUIRE(bad.canonical);CHECK(bad.canonical->field=="objective.policy");CHECK(bad.path.empty());
    constexpr auto two=R"({"schema":"csl.scenario/1","horizon":0,"model":{"kind":"linear_discrete","A":[[1,0],[0,1]],"B":{"rows":2,"cols":0,"values":[]}},"initial_state":[0,0],"controls":{"kind":"universal"},"objective":{"kind":"quadratic","Q":[[2,1],[0,2]],"linear":[0,0]}})";
    bad=accepted<InputFailure>(load(two));REQUIRE(bad.canonical);CHECK(bad.canonical->field=="objective.symmetry");CHECK(bad.path=="/objective/Q");
}
