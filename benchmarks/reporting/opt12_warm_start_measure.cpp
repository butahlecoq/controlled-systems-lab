#include <csl/adapters/lp/highs.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using namespace csl;
using namespace csl::optimization;
using namespace csl::adapters::lp;
using Clock=std::chrono::steady_clock;

LinearProgram make_problem(std::string id,std::size_t columns,double rhs) {
    Vector objective(columns,-1.0);
    std::vector<std::size_t> offsets{0,columns},indices(columns);
    std::vector<double> coefficients(columns,1.0);
    for(std::size_t i=0;i<columns;++i)indices[i]=i;
    return std::get<LinearProgram>(make_linear_program({{{"opt12-measure"},{std::move(id)}},std::move(objective),0,
        {1,columns,std::move(offsets),std::move(indices),std::move(coefficients)},
        std::vector<Interval>(columns,Interval{0,{}}),{{{},rhs}}}));
}

std::optional<std::string> field(const std::string& diagnostics,const std::string& key) {
    const std::string prefix="\n"+key+"=";
    const auto start=diagnostics.find(prefix);
    if(start==std::string::npos)return {};
    const auto value=start+prefix.size();
    const auto end=diagnostics.find('\n',value);
    return diagnostics.substr(value,end==std::string::npos?end:end-value);
}

std::string quote(const std::string& value) {
    std::ostringstream out;out<<'"';
    for(unsigned char c:value) {
        if(c=='"')out<<"\\\"";
        else if(c=='\\')out<<"\\\\";
        else if(c=='\n')out<<"\\n";
        else if(c=='\r')out<<"\\r";
        else if(c=='\t')out<<"\\t";
        else if(c<0x20)out<<"\\u00"<<std::hex<<std::setw(2)<<std::setfill('0')<<static_cast<unsigned>(c)<<std::dec;
        else out<<static_cast<char>(c);
    }
    out<<'"';return out.str();
}

std::string json_number(const std::optional<std::string>& value) { return value?*value:"null"; }

void run_pair(const std::string& scenario,std::size_t columns,std::size_t repetitions) {
    const auto source=make_problem(scenario+"-source",columns,columns==1?1.0:20.0);
    const auto target=make_problem(scenario+"-changed",columns,columns==1?0.5:19.0);
    for(std::size_t pair=0;pair<repetitions;++pair) {
        for(unsigned order=0;order<2;++order) {
            const bool warm=(pair%2==0)?order==1:order==0;
            auto registration_result=make_highs_registration({.cross_query_warm_start=warm});
            auto* registration=std::get_if<registry::Registration<registry::LPPort>>(&registration_result);
            if(!registration)throw std::runtime_error("HiGHS LP registration failed");
            auto workspace=registration->factory(warm?source:target);
            ExecutionContext context{std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),{}, {},{1e-8,1e-8},"opt12-measure"};
            if(warm) {
                auto priming=workspace->solve(source,context);
                const auto* primed=std::get_if<ProgramResult>(&priming);
                if(!primed||primed->termination!=Termination::completed||primed->outcome.value!=MathematicalOutcome::optimal||
                    !primed->primal||!check_program_result(*primed,source,Assurance::numerical).empty())
                    throw std::runtime_error("warm workspace priming failed independent result checks");
            }
            const auto started=Clock::now();
            auto outcome=workspace->solve(target,context);
            const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-started).count();
            const auto* result=std::get_if<ProgramResult>(&outcome);
            if(!result||result->termination!=Termination::completed||result->outcome.value!=MathematicalOutcome::optimal||
                !result->primal||!check_program_result(*result,target,Assurance::numerical).empty())
                throw std::runtime_error("measured solve failed independent result checks");
            const auto evaluation=evaluate_primal(target,*result->primal,{1e-8,1e-8},{{"opt12-measure.oracle"},"1"});
            const auto* primal=std::get_if<PrimalEvaluation>(&evaluation);
            const double expected=columns==1?-0.5:-19.0;
            if(!primal||std::abs(primal->objective-expected)>1e-9)
                throw std::runtime_error("measured solve differs from the independent literal objective");
            std::cout<<std::setprecision(17)
                <<"{\"schema\":\"csl.opt12-cost-trial/1\",\"scenario\":"<<quote(scenario)
                <<",\"mode\":"<<quote(warm?"warm":"cold")<<",\"pair\":"<<pair
                <<",\"order\":"<<order<<",\"status\":\"verified\",\"expected_objective\":"<<expected
                <<",\"objective\":"<<primal->objective<<",\"wall_ns\":"<<elapsed
                <<",\"model_load_seconds\":"<<json_number(field(result->raw_diagnostics,"native.load_seconds"))
                <<",\"basis_transfer_seconds\":"<<(warm?json_number(field(result->raw_diagnostics,"warm_start.setup_seconds")):"0")
                <<",\"solve_seconds\":"<<json_number(field(result->raw_diagnostics,"native.solve_seconds"))
                <<",\"simplex_iterations\":"<<json_number(field(result->raw_diagnostics,"native.simplex_iterations"))
                <<",\"cache_state\":"<<quote(field(result->raw_diagnostics,"warm_start.cache_state").value_or("disabled"))
                <<",\"basis_accepted\":"<<(field(result->raw_diagnostics,"warm_start.accepted").value_or("false"))
                <<",\"diagnostics\":"<<quote(result->raw_diagnostics)<<"}\n";
        }
    }
}
}

int main(int argc,char** argv) {
    try {
        const std::size_t repetitions=argc>1?static_cast<std::size_t>(std::stoul(argv[1])):7;
        if(repetitions<5)throw std::invalid_argument("at least five paired repetitions are required");
        run_pair("tiny-overhead",1,repetitions);
        run_pair("small-reuse",40,repetitions);
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<error.what()<<'\n';return 1;
    }
}
