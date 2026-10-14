#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/problem/validator.hpp>
#include <csl/registry/registry.hpp>
#include <csl/sets/data.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

#if !defined(NDEBUG) || defined(_DEBUG)
#error "The Strategy B measurement executable must be compiled as a Release target"
#endif
#if !defined(__cpp_lib_bit_cast)
#error "The Strategy B measurement executable requires the C++20 bit_cast library feature"
#endif

using namespace csl;
using namespace csl::registry;

namespace {
template<class T,class... R> T take(std::variant<T,R...> value) {
    if(!std::holds_alternative<T>(value)) throw std::runtime_error("unexpected diagnostic or unsupported result");
    return std::get<T>(std::move(value));
}
void require(bool condition,const char* message) { if(!condition) throw std::runtime_error(message); }
std::string json_escape(const std::string& value) {
    std::string out;
    for(const unsigned char ch:value) {
        if(ch=='"'||ch=='\\') { out.push_back('\\');out.push_back(static_cast<char>(ch)); }
        else if(ch=='\n') out+="\\n";
        else if(ch=='\r') out+="\\r";
        else if(ch=='\t') out+="\\t";
        else if(ch>=0x20) out.push_back(static_cast<char>(ch));
    }
    return out;
}
SetHandle interval(std::string id) {
    return take(sets::make_h({{std::move(id)},1,{"u"}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),take(numeric::snapshot_vector(Vector{1,0})),
         take(numeric::snapshot(Matrix{0,1,{}})),take(numeric::snapshot_vector(Vector{}))})).as_handle();
}
Problem source() {
    return {{"syn04-ts01-strategy-b"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{}}),
        {0,1,2},KnownInitial{{0}},ContinuousDomain{{interval("u0"),interval("u1")}},
        {UniversalSet{1},UniversalSet{1},UniversalSet{1}},{},{},
        InformationPattern::nominal_open_loop,QuadraticTerminal{{1,1,{2}},{-2},1}};
}
struct RunObservation { std::uint64_t token; std::string lp_provider; std::string convex_provider; };
RunObservation one_run() {
    auto resolved=take(problem::resolve(source(),{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    FamilyRequest family;
    family.profile=synthesis::strategy_ts01::profile_id;
    family.objective=resolved.identity();
    family.target=FamilyTarget::exact_optimal_relation;
    family.assurance=Assurance::numerical;
    family.representation={"csl.polyhedron.h"};

    Registry<LPPort> lp;
    Registry<ConvexPort> convex;
    auto lp_registration=take(adapters::lp::make_highs_registration());
    auto convex_registration=take(adapters::convex::make_highs_registration());
    const auto lp_id=lp_registration.identity.id;
    const auto convex_id=convex_registration.identity.id;
    require(!lp.add(std::move(lp_registration)),"registered HiGHS LP provider was rejected");
    require(!convex.add(std::move(convex_registration)),"registered HiGHS convex provider was rejected");
    StrategyRegistry strategies;
    require(!strategies.add(synthesis::strategy_b::make_registration(lp,convex)),"registered Strategy B was rejected");

    StrategyConfiguration configuration;
    configuration.strategy={"csl.synthesis.strategy-b"};
    configuration.lp=lp_id;
    configuration.convex=convex_id;
    configuration.representation=family.representation;
    StrategyRequest request{std::move(resolved),configuration,family,"1"};
    Requirements requirements;
    requirements.output.representation=family.representation;
    requirements.output.family=family.target;
    requirements.output.completeness=Completeness::established;
    auto prepared=take(strategies.prepare(request,requirements));
    require(prepared.provenance().size()==3,"prepared provider provenance is incomplete");
    require(prepared.provenance()[1].actual && prepared.provenance()[2].actual,"actual provider identity is unavailable");
    require(prepared.provenance()[1].actual->id.value.find("highs")!=std::string::npos,"LP route did not use a HiGHS provider");
    require(prepared.provenance()[2].actual->id.value.find("highs")!=std::string::npos,"convex route did not use a HiGHS provider");
    const auto lp_identity=prepared.provenance()[1].actual->id.value+"@"+prepared.provenance()[1].actual->version;
    const auto convex_identity=prepared.provenance()[2].actual->id.value+"@"+prepared.provenance()[2].actual->version;
    require(lp_identity=="csl.lp.highs@1.0.0+highs.1.11.0","actual LP provider identity/version differs");
    require(convex_identity=="csl.convex.highs@1.0.0+highs.1.11.0","actual convex provider identity/version differs");
    auto workspace=prepared.create();
    ExecutionContext context;
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto result=take(workspace->run(context));
    require(result.termination==Termination::completed,"StrategyPort run did not complete");
    require(result.outcome.value==MathematicalOutcome::optimal,"StrategyPort outcome is not optimal");
    require(result.family.has_value(),"verified complete family is missing");
    require(result.family->target()==FamilyTarget::exact_optimal_relation,"result is not a complete optimal relation");
    require(result.family->registry_verified(),"complete family lacks compiled verifier acceptance");
    require(result.family->identity().strategy.value=="csl.synthesis.strategy-b"&&result.family->identity().strategy_version=="1",
        "result identity differs from registered Strategy B");
    require(result.family->identity().request.profile==synthesis::strategy_ts01::profile_id,"result profile differs from T-S01");
    require(result.family->identity().lineage.size()==2,"Strategy B result lineage is incomplete");
    const auto* complete=std::get_if<CompleteOptimalFamily>(&result.family->outcome());
    require(complete&&complete->assurance==Assurance::numerical,"verified numerical complete-family evidence is missing");
    require(complete->completeness.binding==result.family->identity(),"completeness evidence is not bound to the result identity");
    require(complete->relation.coordinates==JointCoordinates{{1,1,0},2},"canonical relation coordinates differ");
    require(result.objective.lower&&result.objective.upper&&result.objective.lower->value==0&&result.objective.upper->value==0,
        "T-S01 optimum bounds differ from zero");
    const auto* relation=dynamic_cast<const synthesis::strategy_ts01::ExactJointRelation*>(complete->relation.payload.get());
    require(relation,"complete relation payload is not the verified T-S01 relation");
    const auto representation=relation->h_polyhedron().representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    require(h&&h->inequalities.rows()==4&&h->inequalities.cols()==5&&h->equalities.rows()==4&&h->equalities.cols()==5,
        "canonical H-relation dimensions differ");
    const double a[20]={0,0,0,1,0,0,0,0,-1,0,0,0,0,0,1,0,0,0,0,-1};
    const double b[4]={1,0,1,0};
    const double e[20]={1,0,0,0,0,0,1,0,-1,0,0,0,1,0,0,0,0,0,1,1};
    const double f[4]={0,0,1,1};
    for(std::size_t row=0;row<4;++row) {
        require(h->upper_bounds[row]==b[row]&&h->equality_values[row]==f[row],"canonical H-relation bounds differ");
        for(std::size_t column=0;column<5;++column)
            require(h->inequalities(row,column)==a[row*5+column]&&h->equalities(row,column)==e[row*5+column],
                "canonical H-relation coefficients differ");
    }
    require(relation->h_polyhedron().metadata()->coordinate_labels==std::vector<std::string>{"x0","x1","x2","u0","u1"},
        "canonical coordinate labels differ");
    const std::array<Vector,3> members{{{0,0,1,0,1},{0,0.25,1,0.25,0.75},{0,1,1,1,0}}};
    for(const auto& point:members) require(relation->contains(point),"canonical relation rejected a required member");
    const Vector rejected0{0,0,0,0,0},rejected1{0,1,2,1,1};
    require(!relation->contains(rejected0)&&!relation->contains(rejected1),"canonical relation accepted a nonoptimal history");
    std::uint64_t token=1469598103934665603ull;
    for(double value:Vector{0,0.25,1,0.25,0.75}) { token^=std::bit_cast<std::uint64_t>(value);token*=1099511628211ull; }
    token^=static_cast<std::uint64_t>(h->inequalities.rows()+h->equalities.rows());
    return {token,lp_identity,convex_identity};
}
}
int main() {
    constexpr int warmups=1;
    constexpr int repetitions=7;
    int failures=0;
    for(int repetition=-warmups;repetition<repetitions;++repetition) {
        const bool warmup=repetition<0;
        const auto start=std::chrono::steady_clock::now();
        RunObservation observation{};bool passed=true;std::string error;
        try { observation=one_run(); }
        catch(const std::exception& exception) { passed=false;error=exception.what(); }
        const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
        if(!passed) ++failures;
        std::cout<<"{\"schema\":\"csl.syn04-strategy-b-ts01-measurement-event/1\",\"repetition\":"
            <<(warmup?0:repetition+1)<<",\"warmup\":"<<(warmup?"true":"false")
            <<",\"elapsed_ns\":"<<elapsed<<",\"status\":\""<<(passed?"passed":"failed")
            <<"\",\"consumed_result_marker\":"<<observation.token<<",\"result_disposition\":\""
            <<(passed?"complete_optimal_family":"unavailable")<<"\",\"lp_provider\":\""
            <<(passed?json_escape(observation.lp_provider):"")<<"\",\"convex_provider\":\""
            <<(passed?json_escape(observation.convex_provider):"")<<"\",\"error\":\""<<json_escape(error)<<"\"}\n";
    }
    return failures==0?0:1;
}
