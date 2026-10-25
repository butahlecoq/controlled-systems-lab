#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/problem/validator.hpp>
#include <csl/sets/data.hpp>
#include <chrono>
#include <bit>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>

#if !defined(NDEBUG) || defined(_DEBUG)
#error "The T-S01 measurement executable must be compiled as a Release target"
#endif
#if !defined(__cpp_lib_bit_cast)
#error "The T-S01 measurement executable requires the C++20 bit_cast library feature"
#endif

using namespace csl;
using namespace csl::registry;

namespace {
const char* termination_name(Termination value) {
    switch(value) {
        case Termination::completed: return "completed";
        case Termination::cancelled: return "cancelled";
        case Termination::deadline_expired: return "deadline_expired";
        case Termination::resource_limit: return "resource_limit";
        case Termination::numerical_failure: return "numerical_failure";
        case Termination::operation_rejected: return "operation_rejected";
        case Termination::contract_rejected: return "contract_rejected";
    }
    return "unknown";
}
const char* outcome_name(MathematicalOutcome value) {
    switch(value) {
        case MathematicalOutcome::optimal: return "optimal";
        case MathematicalOutcome::infeasible: return "infeasible";
        case MathematicalOutcome::unbounded: return "unbounded";
        case MathematicalOutcome::infimum_not_attained: return "infimum_not_attained";
        case MathematicalOutcome::undetermined: return "undetermined";
    }
    return "unknown";
}

template<class T, class... R> T take(std::variant<T,R...> value) {
    if (!std::holds_alternative<T>(value)) throw std::runtime_error("unexpected diagnostic or unsupported result");
    return std::get<T>(std::move(value));
}

SetHandle interval(std::string id, double lower, double upper) {
    return take(sets::make_h({std::move(id),1,{"u"}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}})),
         take(numeric::snapshot_vector(Vector{upper,-lower})),
         take(numeric::snapshot(Matrix{0,1,{}})),
         take(numeric::snapshot_vector(Vector{}))})).as_handle();
}

Problem source() {
    return {{"ts01-report-fixture"},std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0},TimeDomain::discrete,LinearStage{{1,1,{1}},{1,1,{1}},
            {1,0,{}},{0}}},{}}),{0,1,2},KnownInitial{{0}},
        ContinuousDomain{{interval("u0",0,1),interval("u1",0,1)}},
        {UniversalSet{1},UniversalSet{1},UniversalSet{1}},{},{},
        InformationPattern::nominal_open_loop,
        TerminalObjective{std::in_place_type<QuadraticTerminal>, Matrix{1,1,{2}}, Vector{-2}, 1.0}};
}

SynthesisResult one_run(std::uint64_t& token) {
    auto problem = take(problem::resolve(source(),{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    FamilyRequest family;
    family.profile="ts01_exact_integrator";
    family.objective=problem.identity();
    family.target=FamilyTarget::exact_optimal_relation;
    family.assurance=Assurance::numerical;
    family.representation={"csl.polyhedron.h"};
    StrategyConfiguration configuration;
    configuration.strategy={"csl.synthesis.ts01-analytic"};
    configuration.representation=family.representation;
    StrategyRequest request{std::move(problem),configuration,family,{},{}};

    StrategyRegistry strategies;
    if (strategies.add(synthesis::strategy_ts01::make_registration())) throw std::runtime_error("T-S01 registration was rejected");
    Requirements requirements;
    requirements.output.representation=family.representation;
    requirements.output.family=family.target;
    requirements.output.completeness=Completeness::established;
    auto prepared=take(strategies.prepare(request,requirements));
    auto workspace=prepared.create();
    ExecutionContext context;
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    const auto outcome=workspace->run(context);
    auto result=take(outcome);
    if (result.termination!=Termination::completed || result.outcome.value!=MathematicalOutcome::optimal || !result.family)
        throw std::runtime_error("T-S01 did not return the expected optimal complete family");
    const auto& identity=result.family->identity();
    if (identity.strategy.value!="csl.synthesis.ts01-analytic" || identity.strategy_version!="1" ||
        identity.request.profile!="ts01_exact_integrator" || !identity.lineage.empty())
        throw std::runtime_error("T-S01 result identity differs from the strict profile");
    const auto* complete=std::get_if<CompleteOptimalFamily>(&result.family->outcome());
    if (!complete || complete->assurance!=Assurance::numerical ||
        complete->relation.coordinates!=JointCoordinates{{1,1,0},2})
        throw std::runtime_error("T-S01 complete relation metadata differs");
    if(!result.objective.lower || !result.objective.upper || result.objective.lower->value!=0 || result.objective.upper->value!=0)
        throw std::runtime_error("T-S01 observed objective bounds differ");
    const auto* relation=dynamic_cast<const synthesis::strategy_ts01::ExactJointRelation*>(complete->relation.payload.get());
    if (!relation) throw std::runtime_error("T-S01 relation payload type differs");
    const auto representation=relation->h_polyhedron().representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if (!h || h->inequalities.rows()!=4 || h->inequalities.cols()!=5 ||
        h->upper_bounds.size()!=4 || h->equalities.rows()!=4 || h->equalities.cols()!=5 ||
        h->equality_values.size()!=4) throw std::runtime_error("T-S01 canonical H-representation shape differs");
    const double expected_a[20]={0,0,0,1,0, 0,0,0,-1,0, 0,0,0,0,1, 0,0,0,0,-1};
    const double expected_b[4]={1,0,1,0};
    const double expected_e[20]={1,0,0,0,0, 0,1,0,-1,0, 0,0,1,0,0, 0,0,0,1,1};
    const double expected_f[4]={0,0,1,1};
    for(std::size_t r=0;r<4;++r) {
        if(h->upper_bounds[r]!=expected_b[r] || h->equality_values[r]!=expected_f[r])
            throw std::runtime_error("T-S01 canonical H-representation bounds differ");
        for(std::size_t c=0;c<5;++c)
            if(h->inequalities(r,c)!=expected_a[r*5+c] || h->equalities(r,c)!=expected_e[r*5+c])
                throw std::runtime_error("T-S01 canonical H-representation coefficients differ");
    }
    if(relation->h_polyhedron().metadata()->coordinate_labels!=std::vector<std::string>{"x0","x1","x2","u0","u1"})
        throw std::runtime_error("T-S01 canonical coordinate labels differ");
    const Vector accepted{0,0.25,1,0.25,0.75};
    const Vector rejected{0,0,0,0,0};
    if(!relation->contains(accepted) || relation->contains(rejected))
        throw std::runtime_error("T-S01 exact membership checks failed");
    token=1469598103934665603ull;
    for(double value:accepted) {
        token^=static_cast<std::uint64_t>(std::bit_cast<std::uint64_t>(value));
        token*=1099511628211ull;
    }
    token^=static_cast<std::uint64_t>(h->inequalities.rows()+h->equalities.rows());
    return result;
}

}

int main() {
    constexpr int warmups=1;
    constexpr int repetitions=7;
    int failures=0;
    for(int repetition=-warmups;repetition<repetitions;++repetition) {
        const bool warmup=repetition<0;
        const auto start=std::chrono::steady_clock::now();
        std::uint64_t token=0;
        bool passed=true;
        std::string error;
        SynthesisResult result{};
        try { result=one_run(token); }
        catch(const std::exception& exception) { passed=false;error=exception.what(); }
        const auto end=std::chrono::steady_clock::now();
        const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(end-start).count();
        if(!passed)++failures;
        std::cout<<"{\"schema\":\"csl.syn07-ts01-measurement-event/2\",\"repetition\":"
            <<(warmup?0:repetition+1)<<",\"warmup\":"<<(warmup?"true":"false")
            <<",\"elapsed_ns\":"<<elapsed<<",\"status\":\""<<(passed?"passed":"failed")
            <<"\",\"consumed_result_marker\":"<<token<<",\"termination\":\""<<(passed?termination_name(result.termination):"unavailable")
            <<"\",\"outcome\":\""<<(passed?outcome_name(result.outcome.value):"unavailable")<<"\",\"objective_lower\":"<<(passed?result.objective.lower->value:0)
            <<",\"objective_upper\":"<<(passed?result.objective.upper->value:0)<<",\"residuals_available\":false,\"error\":\""<<error<<"\"}\n";
    }
    return failures==0?0:1;
}
