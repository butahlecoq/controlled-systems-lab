#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/problem/validator.hpp>
#include <csl/registry/registry.hpp>
#include <csl/sets/data.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <iomanip>
#include <memory>
#include <stdexcept>
#include <string>

#if !defined(NDEBUG) || defined(_DEBUG)
#error "The Strategy A measurement executable must be compiled as a Release target"
#endif
#if !defined(__cpp_lib_bit_cast)
#error "The Strategy A measurement executable requires the C++20 bit_cast library feature"
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
    return {{"syn04-ts01-strategy-a"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{}}),
        {0,1,2},KnownInitial{{0}},ContinuousDomain{{interval("u0"),interval("u1")}},
        {UniversalSet{1},UniversalSet{1},UniversalSet{1}},{},{},
        InformationPattern::nominal_open_loop,QuadraticTerminal{{1,1,{2}},{-2},1}};
}
struct RunObservation { std::uint64_t token; std::string lp_provider; std::string convex_provider; std::string providers_json; std::string lineage_json; std::string completeness_verifier; std::string completeness_verifier_version; double witness_objective; double max_residual; double abs_tolerance; double rel_tolerance; std::string residual_verifier; };
template<class Port> PreparedProvider<Port> selected(Registration<Port> entry,std::string representation) {
    Registry<Port> registry;Method method{entry.identity.id,entry.identity.version};
    require(!registry.add(std::move(entry)),"Strategy A subprovider registration failed");
    Requirements requirements;requirements.output.representation={std::move(representation)};
    if constexpr(std::is_same_v<Port,GeometryPort>||std::is_same_v<Port,ConversionPort>)
        requirements.output.relation=SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry,method,requirements)));
}
double independently_check_original_trajectory(const Vector& point) {
    require(point.size()==5,"independent trajectory coordinates differ");
    const double x0=point[0],x1=point[1],x2=point[2],u0=point[3],u1=point[4];
    double residual=std::abs(x0);
    residual=std::max(residual,std::abs(x1-x0-u0));
    residual=std::max(residual,std::abs(x2-x1-u1));
    residual=std::max(residual,std::max(0.0,-u0));
    residual=std::max(residual,std::max(0.0,u0-1.0));
    residual=std::max(residual,std::max(0.0,-u1));
    residual=std::max(residual,std::max(0.0,u1-1.0));
    const double original_objective=(x2-1.0)*(x2-1.0);
    require(original_objective==0,"independent canonical family member is not an optimizer");
    residual=std::max(residual,std::abs(original_objective));
    require(std::isfinite(residual)&&residual<=1e-8,"independent original trajectory residual exceeds tolerance");
    return residual;
}
RunObservation one_run() {
    auto resolved=take(problem::resolve(source(),{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    FamilyRequest family;
    family.profile=synthesis::strategy_ts01::profile_id;
    family.objective=resolved.identity();
    family.target=FamilyTarget::exact_optimal_relation;
    family.assurance=Assurance::numerical;
    family.representation={"csl.polyhedron.h"};

    auto lp_registration=take(adapters::lp::make_highs_registration());
    auto convex_registration=take(adapters::convex::make_highs_registration());
    auto converter_registration=take(adapters::polyhedral::make_qhull_registration(lp_registration));
    auto projection_registration=geometry::polyhedral::make_projection_registration();
    auto hull_provider=selected(geometry::make_lp_hull_reducer_registration(),"");
    auto affine_lp_provider=selected(lp_registration,"csl.program-result.v1");
    auto affine_converter_provider=selected(converter_registration,"csl.polyhedron.v");
    const auto nested_hull_identity=hull_provider.provenance().actual->id.value+"@"+hull_provider.provenance().actual->version;
    require(nested_hull_identity=="csl.hull.lp-membership@1.0.0","affine hull provider identity/version differs");
    auto affine_registration=geometry::make_affine_sum_registration({
        std::move(hull_provider),std::move(affine_lp_provider),std::move(affine_converter_provider)});
    Registry<GeometryPort> projections,affines;Registry<ConversionPort> conversions;
    Registry<LPPort> lp;Registry<ConvexPort> convex;
    const Method projection_method{projection_registration.identity.id,projection_registration.identity.version};
    const Method affine_method{affine_registration.identity.id,affine_registration.identity.version};
    const Method converter_method{converter_registration.identity.id,converter_registration.identity.version};
    const Method lp_method{lp_registration.identity.id,lp_registration.identity.version};
    const Method convex_method{convex_registration.identity.id,convex_registration.identity.version};
    require(!projections.add(std::move(projection_registration)),"projection registration was rejected");
    require(!affines.add(std::move(affine_registration)),"affine/sum registration was rejected");
    require(!conversions.add(std::move(converter_registration)),"Qhull conversion registration was rejected");
    require(!lp.add(std::move(lp_registration)),"registered HiGHS LP provider was rejected");
    require(!convex.add(std::move(convex_registration)),"registered HiGHS convex provider was rejected");
    Requirements h_output,v_output,program;h_output.output.representation={"csl.polyhedron.h"};h_output.output.relation=SetRelation::equivalent;
    v_output.output.representation={"csl.polyhedron.v"};v_output.output.relation=SetRelation::equivalent;
    program.output.representation={"csl.program-result.v1"};
    auto providers=take(check_providers(select_provider(projections,projection_method,h_output),
        select_provider(affines,affine_method,v_output),select_provider(conversions,converter_method,h_output),
        select_provider(lp,lp_method,program),select_provider(convex,convex_method,program)));
    StrategyRegistry strategies;
    require(!strategies.add(synthesis::strategy_a::make_registration(std::move(providers))),"registered Strategy A was rejected");

    StrategyConfiguration configuration;
    configuration.strategy={"csl.synthesis.reach-back"};
    configuration.representation=family.representation;
    StrategyRequest request{std::move(resolved),configuration,family,"1"};
    Requirements requirements;
    requirements.output.representation=family.representation;
    requirements.output.family=family.target;
    requirements.output.completeness=Completeness::established;
    auto prepared=take(strategies.prepare(request,requirements));
    require(prepared.provenance().size()>=6,"Strategy A registered provider provenance is incomplete");
    std::vector<std::string> actual_providers;
    for(const auto& item:prepared.provenance()) if(item.actual) actual_providers.push_back(item.actual->id.value+"@"+item.actual->version);
    actual_providers.push_back(nested_hull_identity);
    const auto has_provider=[&](const std::string& id) {return std::find(actual_providers.begin(),actual_providers.end(),id)!=actual_providers.end();};
    require(has_provider("csl.geometry.polyhedral-projection@1.0.0"),"actual projection provider is missing");
    require(has_provider("csl.geometry.affine-sum@1.0.0"),"actual affine/sum provider is missing");
    require(has_provider("csl.conversion.qhull@1.0.0+qhull.8.0.2"),"actual Qhull conversion provider is missing");
    const auto lp_identity="csl.lp.highs@1.0.0+highs.1.11.0";
    const auto convex_identity="csl.convex.highs@1.0.0+highs.1.11.0";
    require(has_provider(lp_identity),"actual registered LP provider identity/version differs");
    require(has_provider(convex_identity),"actual registered convex provider identity/version differs");
    std::string providers_json="[";
    for(std::size_t i=0;i<actual_providers.size();++i) {
        if(i)providers_json+=",";
        providers_json+="\""+json_escape(actual_providers[i])+"\"";
    }
    providers_json+="]";
    auto workspace=prepared.create();
    ExecutionContext context;
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    auto result=take(workspace->run(context));
    require(result.termination==Termination::completed,"StrategyPort run did not complete");
    require(result.outcome.value==MathematicalOutcome::optimal,"StrategyPort outcome is not optimal");
    require(result.family.has_value(),"verified complete family is missing");
    require(result.family->target()==FamilyTarget::exact_optimal_relation,"result is not a complete optimal relation");
    require(result.family->registry_verified(),"complete family lacks compiled verifier acceptance");
    require(result.family->identity().strategy.value=="csl.synthesis.reach-back"&&result.family->identity().strategy_version=="1",
        "result identity differs from registered Strategy A");
    require(result.family->identity().request.profile==synthesis::strategy_ts01::profile_id,"result profile differs from T-S01");
    require(result.family->identity().lineage.size()==6,"Strategy A result lineage is incomplete");
    require(result.family->identity().lineage[3].module.value=="csl.synthesis.control-recovery"&&
        result.family->identity().lineage[4].module.value=="csl.synthesis.terminal-minimizers"&&
        result.family->identity().lineage[5].module.value=="csl.synthesis.control-recovery",
        "Strategy A did not execute forward reachability, terminal minimization, and both recovery phases");
    std::string lineage_json="[";
    const auto& lineage=result.family->identity().lineage;
    for(std::size_t i=0;i<lineage.size();++i) {
        if(i)lineage_json+=",";
        lineage_json+="\""+json_escape(lineage[i].module.value+"@"+lineage[i].version)+"\"";
    }
    lineage_json+="]";
    const auto* complete=std::get_if<CompleteOptimalFamily>(&result.family->outcome());
    require(complete&&complete->assurance==Assurance::numerical,"verified numerical complete-family evidence is missing");
    const auto* registered_completeness=std::get_if<RegisteredCompletenessEvidence>(&complete->completeness.support);
    require(registered_completeness&&registered_completeness->verifier.value=="csl.verifier.ts01-analytic"&&
        registered_completeness->verifier_version=="1","complete-family verifier identity differs");
    require(complete->completeness.binding==result.family->identity(),"completeness evidence is not bound to the result identity");
    require(complete->relation.coordinates==JointCoordinates{{1,1,0},2},"canonical relation coordinates differ");
    require(result.objective.lower&&result.objective.upper&&result.objective.lower->value==0&&result.objective.upper->value==0,
        "T-S01 optimum bounds differ from zero");
    const auto* relation=dynamic_cast<const synthesis::strategy_ts01::ExactJointRelation*>(complete->relation.payload.get());
    require(relation,"complete relation payload is not the verified T-S01 relation");
    const Vector anchor{0,0.25,1,0.25,0.75};
    require(relation->contains(anchor),"canonical interior representative is outside the published complete relation");
    const double independent_residual=independently_check_original_trajectory(anchor);
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
    require(independent_residual>=0,"independent original trajectory check did not run");
    return {token,lp_identity,convex_identity,providers_json,lineage_json,registered_completeness->verifier.value,registered_completeness->verifier_version,0,independent_residual,
        1e-8,1e-8,"syn03-strategy-a-independent-original-check/1"};
}
}
int main() {
    std::cout<<std::setprecision(17);
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
        std::cout<<"{\"schema\":\"csl.syn03-strategy-a-ts01-measurement-event/1\",\"repetition\":"
            <<(warmup?0:repetition+1)<<",\"warmup\":"<<(warmup?"true":"false")
            <<",\"elapsed_ns\":"<<elapsed<<",\"status\":\""<<(passed?"passed":"failed")
            <<"\",\"consumed_result_marker\":"<<observation.token<<",\"result_disposition\":\""
            <<(passed?"complete_optimal_family":"unavailable")<<"\",\"lp_provider\":\""
            <<(passed?json_escape(observation.lp_provider):"")<<"\",\"convex_provider\":\""
            <<(passed?json_escape(observation.convex_provider):"")<<"\",\"providers\":"<<(passed?observation.providers_json:"[]")<<",\"lineage\":"<<(passed?observation.lineage_json:"[]")<<",\"termination\":\""<<(passed?"completed":"unavailable")
            <<"\",\"outcome\":\""<<(passed?"optimal":"unavailable")<<"\",\"registry_verified\":"<<(passed?"true":"false")
            <<",\"assurance\":\""<<(passed?"numerical":"unavailable")<<"\",\"canonical_relation_checked\":"<<(passed?"true":"false")
            <<",\"completeness_verifier\":\""<<(passed?json_escape(observation.completeness_verifier):"")
            <<"\",\"completeness_verifier_version\":\""<<(passed?json_escape(observation.completeness_verifier_version):"")<<"\""
            <<",\"representative_coordinates\":"<<(passed?"[0,0.25,1,0.25,0.75]":"[]")
            <<",\"trajectory_objective\":"<<(passed?observation.witness_objective:0)
            <<",\"trajectory_max_residual\":"<<(passed?observation.max_residual:0)<<",\"absolute_tolerance\":"<<(passed?observation.abs_tolerance:0)
            <<",\"relative_tolerance\":"<<(passed?observation.rel_tolerance:0)<<",\"residual_verifier\":\""
            <<(passed?json_escape(observation.residual_verifier):"")<<"\",\"error\":\""<<json_escape(error)<<"\"}\n";
    }
    return failures==0?0:1;
}
