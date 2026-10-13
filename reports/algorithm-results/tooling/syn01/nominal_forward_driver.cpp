#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/reachability/nominal_forward.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

using namespace csl;
namespace {
using Json = nlohmann::json;
using Clock = std::chrono::steady_clock;
using namespace csl::registry;
using namespace csl::reachability;

template<class T, class... E> T take(std::variant<T,E...> value) {
    if (!std::holds_alternative<T>(value)) throw std::runtime_error("provider or model setup rejected");
    return std::get<T>(std::move(value));
}
std::uint64_t elapsed(Clock::time_point start) {
    return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count());
}
SetHandle interval(std::string id, double lo, double hi, std::string label="x") {
    auto a=take(numeric::snapshot(Matrix{2,1,{1,-1}}));
    auto b=take(numeric::snapshot_vector(Vector{hi,-lo}));
    auto e=take(numeric::snapshot(Matrix{0,1,{}}));
    auto f=take(numeric::snapshot_vector(Vector{}));
    return take(sets::make_h({{std::move(id)},1,{std::move(label)}},{std::move(a),std::move(b),std::move(e),std::move(f)})).as_handle();
}
Problem integrator() {
    return {{"syn01-integrator"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{}}),{0,1,2},KnownInitial{{0}},
        ContinuousDomain{{interval("u0",0,1,"u"),interval("u1",0,1,"u")}},
        {interval("X0",0,0),interval("X1",0,1),interval("X2",0,2)}, {},{},InformationPattern::nominal_open_loop,
        QuadraticTerminal{{1,1,{2}},{-2},1}};
}
Problem ltv() {
    auto p=integrator();p.initial=KnownInitial{{1}};
    p.states={interval("X0",0,2),interval("X1",3,4),interval("X2",-5,-4)};
    p.model=std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,std::vector<LinearStage>{
        {{1,1,{2}},{1,1,{1}},{1,0,{}},{1}},{{1,1,{-1}},{1,1,{2}},{1,0,{}},{-2}}}}, {}});
    return p;
}
problem::ResolvedProblem resolve(Problem p) {
    return take(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
template<class Port> PreparedProvider<Port> selected(Registration<Port> entry, std::string representation) {
    Registry<Port> registry;Method method{entry.identity.id,entry.identity.version};
    if(registry.add(std::move(entry)))throw std::runtime_error("provider registration failed");
    Requirements requirements;requirements.output.representation={std::move(representation)};
    if constexpr(std::is_same_v<Port,GeometryPort> || std::is_same_v<Port,ConversionPort>)requirements.output.relation=SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry,method,requirements)));
}
struct DependencyBundle { ForwardDependencies providers; Json identities; };
Json identity(const Identity& item) { return {{"id",item.id.value},{"version",item.version}}; }
template<class Port> const Identity& selected_identity(const PreparedProvider<Port>& provider) {
    const auto& actual=provider.provenance().actual;
    if(!actual)throw std::runtime_error("selected provider has no actual identity");
    return *actual;
}
DependencyBundle dependencies() {
    auto lp=take(adapters::lp::make_highs_registration());
    auto converter=take(adapters::polyhedral::make_qhull_registration(lp));
    auto hull=geometry::make_lp_hull_reducer_registration();
    auto projection=geometry::polyhedral::make_projection_registration({geometry::polyhedral::ProjectionOutput::h,{}});
    auto affine=geometry::make_affine_sum_registration({
        selected(hull,""), selected(lp,"csl.program-result.v1"), selected(converter,"csl.polyhedron.v")},{ {},{}});
    auto projection_provider=selected(std::move(projection),"csl.polyhedron.h");
    auto affine_provider=selected(std::move(affine),"csl.polyhedron.v");
    auto conversion_provider=selected(converter,"csl.polyhedron.h");
    Json providers={{"projection",identity(selected_identity(projection_provider))},
                    {"affine_sum",identity(selected_identity(affine_provider))},
                    {"conversion",identity(selected_identity(conversion_provider))},
                    {"lp_backend",identity(lp.identity)},
                    {"hull_reducer",identity(hull.identity)}};
    return {{std::move(projection_provider),std::move(affine_provider),std::move(conversion_provider)},std::move(providers)};
}
struct Bounds { double lower,upper; bool feasible; };
Bounds h_bounds(const SetHandle& set) {
    auto value=take(sets::from_handle(set));auto representation=value.representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h || h->inequalities.cols()!=1 || h->equalities.cols()!=1)throw std::runtime_error("expected scalar H output");
    double lo=-std::numeric_limits<double>::infinity(),hi=std::numeric_limits<double>::infinity();bool feasible=true;
    for(std::size_t row=0;row<h->inequalities.rows();++row){
        const double a=h->inequalities(row,0),b=h->upper_bounds[row];
        if(a>0)hi=std::min(hi,b/a);else if(a<0)lo=std::max(lo,b/a);else if(b<0)feasible=false;
    }
    for(std::size_t row=0;row<h->equalities.rows();++row){
        const double a=h->equalities(row,0),b=h->equality_values[row];
        if(a!=0){const double fixed=b/a;lo=std::max(lo,fixed);hi=std::min(hi,fixed);}else if(b!=0)feasible=false;
    }
    return {lo,hi,feasible};
}
struct Result {
    std::string status{"failed"},outcome{"failed"},detail;
    std::vector<std::array<double,2>> marginals;
    std::map<std::string,std::size_t> operation_counts;
    Json provider_identities=Json::object();
    std::optional<std::uint64_t> setup_ns,solve_ns,oracle_ns,execute_ns;
    std::string setup_state{"not_reached"},solve_state{"not_reached"},oracle_state{"not_reached"},execute_state{"not_reached"};
    bool oracle_passed{};
};
Result run(const std::string& scenario,std::size_t repetition) {
    Result result;const auto total_start=Clock::now();
    const auto setup_start=Clock::now();
    auto solve_start=setup_start,oracle_start=setup_start;
    std::string active_phase="setup";
    try {
        auto p=resolve(scenario=="integrator"?integrator():ltv());
        auto deps=dependencies();result.provider_identities=std::move(deps.identities);
        result.setup_ns=elapsed(setup_start);result.setup_state="available";
        active_phase="solve";
        solve_start=Clock::now();
        auto outcome=nominal_forward(p,{"syn01-tube"},deps.providers,{});
        result.solve_ns=elapsed(solve_start);result.solve_state="available";
        active_phase="oracle";
        oracle_start=Clock::now();
        if(const auto* tube=std::get_if<ForwardTube>(&outcome)){
            result.outcome="forward_tube";
            if(tube->stages.size()!=3)throw std::runtime_error("forward tube has unexpected stage count");
            for(const auto& stage:tube->stages){
                const auto bounds=h_bounds(stage.marginal.output);
                if(!bounds.feasible)throw std::runtime_error("returned marginal H set is infeasible");
                result.marginals.push_back({bounds.lower,bounds.upper});
                for(const auto& provider:stage.providers)if(provider.actual_module)++result.operation_counts[provider.actual_module->value];
            }
            const std::vector<std::array<double,2>> expected=scenario=="integrator"
                ?std::vector<std::array<double,2>>{{0,0},{0,1},{0,2}}
                :std::vector<std::array<double,2>>{{1,1},{3,4},{-5,-4}};
            result.oracle_passed=result.marginals==expected;
            if(!result.oracle_passed)result.detail="complete scalar H-row bounds differ from literal analytic marginals";
            else result.status="passed";
        }else if(const auto* empty=std::get_if<EmptyForwardStage>(&outcome)){
            result.outcome="empty_forward_stage";result.detail="unexpected empty stage "+std::to_string(empty->stage.value);
        }else{
            const auto& failure=std::get<ForwardFailure>(outcome);
            result.outcome=std::holds_alternative<Unsupported>(failure.cause)?"unsupported":"operation_stopped_or_failed";
            result.detail="forward failure at stage "+std::to_string(failure.stage.value);
        }
        result.oracle_ns=elapsed(oracle_start);result.oracle_state="available";
    }catch(const std::exception& error){
        result.detail=error.what();result.outcome="driver_exception";
        if(active_phase=="setup"){result.setup_ns=elapsed(setup_start);result.setup_state="partial";}
        else if(active_phase=="solve"){result.solve_ns=elapsed(solve_start);result.solve_state="partial";}
        else {result.oracle_ns=elapsed(oracle_start);result.oracle_state="partial";}
    }
    result.execute_ns=elapsed(total_start);result.execute_state="available";
    if(result.status=="failed"&&result.detail.empty())result.detail="trial did not produce an oracle-passing forward tube";
    (void)repetition;
    return result;
}
Json event_json(const std::string& scenario,std::size_t repetition,const Result& result) {
    const std::vector<std::array<double,2>> expected=scenario=="integrator"
        ?std::vector<std::array<double,2>>{{0,0},{0,1},{0,2}}
        :std::vector<std::array<double,2>>{{1,1},{3,4},{-5,-4}};
    Json observed=Json::array();for(const auto& pair:result.marginals)observed.push_back({pair[0],pair[1]});
    return {{"schema","csl.syn01-nominal-forward-trial/2"},{"scenario",scenario},{"repetition",repetition},
        {"warmup",repetition==0},{"status",result.status},{"outcome",result.outcome},
        {"expected_marginals",expected},{"observed_marginals",observed},{"oracle_passed",result.oracle_passed},
        {"setup_ns",result.setup_ns?Json(*result.setup_ns):Json(nullptr)},{"setup_state",result.setup_state},
        {"solve_ns",result.solve_ns?Json(*result.solve_ns):Json(nullptr)},{"solve_state",result.solve_state},
        {"oracle_ns",result.oracle_ns?Json(*result.oracle_ns):Json(nullptr)},{"oracle_state",result.oracle_state},
        {"execute_ns",result.execute_ns?Json(*result.execute_ns):Json(nullptr)},{"execute_state",result.execute_state},
        {"provider_identities",result.provider_identities},{"provider_operation_counts",result.operation_counts},
        {"provider_operation_timing_ns",nullptr},{"detail",result.detail}};
}
}
int main() {
    bool all_passed=true;
    try {
        for(std::size_t repetition=0;repetition<8;++repetition){
            const std::array<std::string,2> forward{"integrator","ltv"};
            const std::array<std::string,2> reverse{"ltv","integrator"};
            const auto& order=repetition%2==0?forward:reverse;
            for(const auto& scenario:order){
                const auto result=run(scenario,repetition);
                std::cout<<event_json(scenario,repetition,result).dump()<<'\n';
                all_passed=all_passed&&result.status=="passed"&&result.oracle_passed;
            }
        }
    }catch(const std::exception& error){
        std::cerr<<"SYN-01 driver error: "<<error.what()<<'\n';return 2;
    }
    return all_passed?0:1;
}
