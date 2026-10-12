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
#include <array>
#include <cmath>
#include <iomanip>
#include <sstream>
#include <string_view>

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
        static_cast<std::uint64_t>(report.optimality)*37u+
        static_cast<std::uint64_t>(report.completeness)*31u+
        static_cast<std::uint64_t>(report.validated)*41u+
        report.residuals.size();
    if(report.recomputed_objective) token^=std::bit_cast<std::uint64_t>(*report.recomputed_objective);
    for(const auto& residual:report.residuals) {
        for(const auto character:residual.field)token=token*1099511628211ULL ^ static_cast<unsigned char>(character);
        token=token*1099511628211ULL ^ std::bit_cast<std::uint64_t>(residual.measure.violation);
        token=token*1099511628211ULL ^ std::bit_cast<std::uint64_t>(residual.measure.scale);
        token=token*1099511628211ULL ^ std::bit_cast<std::uint64_t>(residual.tolerance);
        token^=static_cast<std::uint64_t>(residual.satisfied);
    }
    return token;
}

struct ExpectedResidual {std::string_view field;double violation,scale;bool satisfied;};
constexpr std::array<ExpectedResidual,10> valid_residuals{{
    {"initial[0]",0,0,true},{"states[0].singleton[0]",0,0,true},
    {"states[2].singleton[0]",0,1,true},{"controls[0].inequalities[0]",0,1,true},
    {"controls[0].inequalities[1]",0,0.25,true},{"dynamics[0][0]",0,0.25,true},
    {"controls[1].inequalities[0]",0,1,true},{"controls[1].inequalities[1]",0,0.75,true},
    {"dynamics[1][0]",0,1,true},{"objective",0,1,true}}};
constexpr std::array<ExpectedResidual,10> violating_residuals{{
    {"initial[0]",0,0,true},{"states[0].singleton[0]",0,0,true},
    {"states[2].singleton[0]",0,1,true},{"controls[0].inequalities[0]",0,1,true},
    {"controls[0].inequalities[1]",0,0.25,true},{"dynamics[0][0]",0,0.25,true},
    {"controls[1].inequalities[0]",0.25,1.25,false},
    {"controls[1].inequalities[1]",0,1.25,true},
    {"dynamics[1][0]",0.5,1.5,false},{"objective",0,1,true}}};

bool expected_report(const TrajectoryReport& report,bool violating) {
    if(report.bindings!=CheckStatus::numerical_pass ||
       report.feasibility!=(violating?CheckStatus::violation:CheckStatus::numerical_pass) ||
       report.objective!=CheckStatus::numerical_pass || report.optimality!=CheckStatus::unsupported ||
       report.completeness!=CheckStatus::unsupported || report.validated!=CheckStatus::unsupported ||
       report.recomputed_objective!=1.0 || report.termination!=Termination::completed ||
       report.residuals.size()!=valid_residuals.size())return false;
    const auto& expected=violating?violating_residuals:valid_residuals;
    for(std::size_t i=0;i<expected.size();++i) {
        const auto& actual=report.residuals[i];const auto& literal=expected[i];
        if(actual.field!=literal.field || actual.measure.violation!=literal.violation ||
           actual.measure.scale!=literal.scale || actual.satisfied!=literal.satisfied ||
           std::abs(actual.tolerance-(1e-8+1e-8*literal.scale))>1e-20)return false;
    }
    return true;
}

std::string json_string(const std::string& value) {
    std::string encoded="\"";
    constexpr char hex[]="0123456789abcdef";
    for(unsigned char c:value) {
        if(c=='"'||c=='\\') {encoded+='\\';encoded+=static_cast<char>(c);}
        else if(c<0x20) {encoded+="\\u00";encoded+=hex[c>>4];encoded+=hex[c&15];}
        else encoded+=static_cast<char>(c);
    }
    return encoded+'"';
}

std::string residual_json(const TrajectoryReport& report) {
    std::ostringstream out;out<<std::setprecision(17)<<'[';
    for(std::size_t i=0;i<report.residuals.size();++i) {
        if(i)out<<',';
        const auto& r=report.residuals[i];
        out<<"{\"field\":"<<json_string(r.field)<<",\"violation\":"<<r.measure.violation
           <<",\"scale\":"<<r.measure.scale<<",\"tolerance\":"<<r.tolerance
           <<",\"satisfied\":"<<(r.satisfied?"true":"false")<<'}';
    }
    out<<']';return out.str();
}

bool emit_case(const problem::ResolvedProblem& problem,const char* label,
               TrajectoryRequest request,std::uint64_t batch,std::uint64_t warmups,std::uint64_t trials) {
    const bool violating=std::string_view(label)=="violating";
    for(std::uint64_t round=0;round<warmups+trials;++round) {
        const auto begin=std::chrono::steady_clock::now();
        std::uint64_t token=0,attempted=0,checked=0,failures=0;
        TrajectoryReport last;
        for(std::uint64_t iteration=0;iteration<batch;++iteration) {
            ++attempted;
            try {
                last=verify_trajectory(problem,request);
                ++checked;
                token^=consume(last)+(iteration*0x9e3779b97f4a7c15ULL);
                if(!expected_report(last,violating)) {
                    ++failures;
                    std::cout<<"{\"event\":\"call_failure\",\"fixture\":\""<<label
                             <<"\",\"round\":"<<round<<",\"iteration\":"<<iteration
                             <<",\"reason\":\"literal oracle mismatch\",\"residuals\":"
                             <<residual_json(last)<<"}\n";
                }
            } catch(const std::exception& error) {
                ++failures;
                std::cout<<"{\"event\":\"call_failure\",\"fixture\":\""<<label
                         <<"\",\"round\":"<<round<<",\"iteration\":"<<iteration
                         <<",\"reason\":"<<json_string(error.what())<<"}\n";
                break;
            }
        }
        const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now()-begin).count();
        std::cout<<"{\"event\":\"trial\",\"fixture\":\""<<label<<"\",\"round\":"<<round
            <<",\"warmup\":"<<(round<warmups?"true":"false")
            <<",\"batch\":"<<batch<<",\"attempted_calls\":"<<attempted
            <<",\"checked_calls\":"<<checked<<",\"failures\":"<<failures
            <<",\"elapsed_ns\":"<<elapsed
            <<",\"bindings\":\""<<status(last.bindings)<<"\",\"feasibility\":\""<<status(last.feasibility)
            <<"\",\"objective\":\""<<status(last.objective)<<"\",\"optimality\":\""<<status(last.optimality)
            <<"\",\"completeness\":\""<<status(last.completeness)<<"\",\"validated\":\""<<status(last.validated)
            <<"\",\"recomputed_objective\":"<<(last.recomputed_objective?*last.recomputed_objective:0)
            <<",\"residual_count\":"<<last.residuals.size()<<",\"residuals\":"<<residual_json(last)
            <<",\"observation_token\":"<<token<<"}\n";
        std::cout.flush();
        if(failures || attempted!=batch || checked!=batch || elapsed<=0)return false;
    }
    return true;
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
        std::cout<<"{\"event\":\"header\",\"schema\":\"csl.syn06-verifier-raw/2\",\"batch\":"<<batch
            <<",\"warmups\":"<<warmups<<",\"trials_per_fixture\":"<<trials
            <<",\"timer_overhead_median_ns\":"<<timer_samples[timer_samples.size()/2]<<"}\n";
        if(!emit_case(problem,"valid",request,batch,warmups,trials))return 2;
        request.witness.controls[1][0]=1.25;
        if(!emit_case(problem,"violating",request,batch,warmups,trials))return 2;
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<error.what()<<'\n';return 1;
    }
}
