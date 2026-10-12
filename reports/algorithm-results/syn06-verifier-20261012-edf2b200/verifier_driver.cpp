#include <csl/verification/trajectory.hpp>
#include <bit>
#include <chrono>
#include <cstdint>
#include <exception>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>
#include <algorithm>

namespace {
using namespace csl;
using namespace csl::verification;

std::uint64_t parse_count(const char* arg) {
    const std::string text(arg);
    if (text.empty() || text.find_first_not_of("0123456789") != std::string::npos)
        throw std::invalid_argument("counts must be positive decimal integers");
    const auto value=std::stoull(text);
    if (value==0 || value>10000000) throw std::invalid_argument("count outside 1..10000000");
    return value;
}

Problem fixture() {
    // Literal integrator: x[0]=0, x[k+1]=x[k]+u[k], 0<=u[k]<=1,
    // x[2]=1, original objective x[2]. No optimization claim is supplied.
    const auto unit=std::get<sets::SetData>(sets::make_h({{"unit-control"},1,{}},
        {std::get<numeric::MatrixView>(numeric::snapshot(Matrix{2,1,{1,-1}})),
         std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{1,0})),
         std::get<numeric::MatrixView>(numeric::snapshot(Matrix{0,1,{}})),
         std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{}))})).as_handle();
    return {{"syn06-two-control-integrator"},
        std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
            std::vector<LinearStage>{
                {{1,1,{1}},{1,1,{1}},{1,0,{}},{0}},
                {{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}}}, {}}),
        {0,1,2},KnownInitial{{0}},ContinuousDomain{{unit,unit}},
        {Singleton{{0}},UniversalSet{1},Singleton{{1}}},{},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{1},0}};
}

const char* status(CheckStatus value) {
    switch(value) {
    case CheckStatus::not_checked:return "not_checked";
    case CheckStatus::numerical_pass:return "numerical_pass";
    case CheckStatus::violation:return "violation";
    case CheckStatus::invalid_input:return "invalid_input";
    case CheckStatus::unsupported:return "unsupported";
    }
    throw std::logic_error("unknown verification status");
}

std::uint64_t consume(const TrajectoryReport& report) {
    std::uint64_t token=static_cast<std::uint64_t>(report.feasibility)*17u+
        static_cast<std::uint64_t>(report.objective)*29u+
        static_cast<std::uint64_t>(report.completeness)*31u+
        report.residuals.size();
    if(report.recomputed_objective) token^=std::bit_cast<std::uint64_t>(*report.recomputed_objective);
    for(const auto& residual:report.residuals) {
        token=token*1099511628211ULL ^ std::bit_cast<std::uint64_t>(residual.measure.violation);
        token^=static_cast<std::uint64_t>(residual.satisfied);
    }
    return token;
}

void emit_case(const problem::ResolvedProblem& problem,const char* label,
               TrajectoryRequest request,std::uint64_t batch,std::uint64_t warmups,std::uint64_t trials) {
    const auto expected=std::string(label)=="valid"?CheckStatus::numerical_pass:CheckStatus::violation;
    for(std::uint64_t round=0;round<warmups+trials;++round) {
        const auto begin=std::chrono::steady_clock::now();
        std::uint64_t token=0;
        TrajectoryReport last;
        for(std::uint64_t iteration=0;iteration<batch;++iteration) {
            last=verify_trajectory(problem,request);
            token^=consume(last)+(iteration*0x9e3779b97f4a7c15ULL);
        }
        const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now()-begin).count();
        if(last.bindings!=CheckStatus::numerical_pass || last.feasibility!=expected ||
            last.objective!=CheckStatus::numerical_pass || last.completeness!=CheckStatus::unsupported ||
            last.recomputed_objective!=1.0 || last.termination!=Termination::completed || elapsed<=0)
            throw std::runtime_error("verifier output differs from literal fixture oracle");
        std::cout<<"{\"event\":\"trial\",\"fixture\":\""<<label<<"\",\"round\":"<<round
            <<",\"warmup\":"<<(round<warmups?"true":"false")
            <<",\"batch\":"<<batch<<",\"elapsed_ns\":"<<elapsed
            <<",\"bindings\":\""<<status(last.bindings)<<"\",\"feasibility\":\""<<status(last.feasibility)
            <<"\",\"objective\":\""<<status(last.objective)<<"\",\"completeness\":\""<<status(last.completeness)
            <<"\",\"recomputed_objective\":1,\"residual_count\":"<<last.residuals.size()
            <<",\"observation_token\":"<<token<<"}\n";
    }
}
} // namespace

int main(int argc,char** argv) {
    try {
        if(argc!=4) throw std::invalid_argument("usage: csl_syn06_verifier_report BATCH WARMUPS TRIALS");
        const auto batch=parse_count(argv[1]);
        const auto warmups=parse_count(argv[2]);
        const auto trials=parse_count(argv[3]);
        auto result=problem::resolve(fixture(),{problem::UncertaintyStructure::stage_product_uncoupled,{},{}});
        if(!std::holds_alternative<problem::ResolvedProblem>(result)) throw std::runtime_error("fixture failed to resolve");
        auto problem=std::get<problem::ResolvedProblem>(std::move(result));
        TrajectoryRequest request;
        request.witness={problem.identity(),{{0},{0.25},{1}},{{0.25},{0.75}},1};
        std::vector<std::int64_t> timer_samples;
        timer_samples.reserve(10001);
        for(int i=0;i<10001;++i) {
            const auto begin=std::chrono::steady_clock::now();
            timer_samples.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now()-begin).count());
        }
        std::ranges::sort(timer_samples);
        std::cout<<"{\"event\":\"header\",\"schema\":\"csl.syn06-verifier-raw/1\",\"batch\":"<<batch
            <<",\"warmups\":"<<warmups<<",\"trials_per_fixture\":"<<trials
            <<",\"timer_overhead_median_ns\":"<<timer_samples[timer_samples.size()/2]<<"}\n";
        emit_case(problem,"valid",request,batch,warmups,trials);
        request.witness.controls[1][0]=1.25;
        emit_case(problem,"violating",request,batch,warmups,trials);
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<error.what()<<'\n';return 1;
    }
}
