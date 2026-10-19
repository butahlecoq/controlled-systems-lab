#include <csl/adapters/lp/highs.hpp>
#include <csl/optimization/lp_backend.hpp>
#include "ReportBuildInfo.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <optional>
#include <span>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {
using namespace csl;
using namespace csl::optimization;
using namespace csl::adapters::lp;
using Clock=std::chrono::steady_clock;

LinearProgram make_problem(std::string id,std::size_t columns,double rhs,bool transfer_cost=false,bool target=false) {
    Vector objective(columns,transfer_cost?1.0:-1.0);
    if(transfer_cost)objective[target?columns-1:0]=target?-2.0:-1.0;
    std::vector<std::size_t> offsets{0,columns},indices(columns);
    std::vector<double> coefficients(columns,1.0);
    for(std::size_t i=0;i<columns;++i)indices[i]=i;
    return std::get<LinearProgram>(make_linear_program({{{"opt12-measure"},{std::move(id)}},std::move(objective),0,
        {1,columns,std::move(offsets),std::move(indices),std::move(coefficients)},
        std::vector<Interval>(columns,Interval{0,{}}),{{{},rhs}}}));
}

std::string quote(const std::string& value);

std::string vector_description(std::span<const double> values) {
    if(values.size()<=1000) {
        std::ostringstream out;out<<'[';
        for(std::size_t i=0;i<values.size();++i) {
            if(i)out<<',';
            out<<std::setprecision(17)<<values[i];
        }
        out<<']';return out.str();
    }
    if(values.size()<3)throw std::runtime_error("large OPT-12 vector is too short for a compact identity");
    const double common=values[values.size()/2];
    std::ostringstream out;out<<"{\"all_columns\":"<<std::setprecision(17)<<common;
    std::size_t overrides=0;
    for(std::size_t i=0;i<values.size();++i)if(values[i]!=common) {
        if(++overrides>4)throw std::runtime_error("large OPT-12 vector is outside the compact fixture profile");
        out<<",\"column_"<<i<<"\":"<<std::setprecision(17)<<values[i];
    }
    out<<'}';return out.str();
}

std::string vector_description(const numeric::VectorView& values) { return vector_description(values.values()); }

double rhs_upper(const LinearProgram& program) {
    if(program.rows().size()!=1||program.rows()[0].lower||!program.rows()[0].upper)
        throw std::runtime_error("OPT-12 fixture must have one upper-bounded constraint");
    return *program.rows()[0].upper;
}

std::string fixture_event(const std::string& scenario,const LinearProgram& source,const LinearProgram& target) {
    const auto source_matrix=std::get<numeric::CsrInput>(source.constraints().descriptor());
    const auto target_matrix=std::get<numeric::CsrInput>(target.constraints().descriptor());
    if(source_matrix.rows!=1||target_matrix.rows!=1||source_matrix.cols!=target_matrix.cols||
        source_matrix.cols!=source.objective().size()||target_matrix.cols!=target.objective().size()||
        source_matrix.cols!=source.variables().size()||target_matrix.cols!=target.variables().size()||
        source_matrix.row_offsets.size()!=2||target_matrix.row_offsets.size()!=2||
        source_matrix.column_indices.size()!=source_matrix.cols||target_matrix.column_indices.size()!=target_matrix.cols||
        source_matrix.row_offsets[0]!=0||target_matrix.row_offsets[0]!=0||
        source_matrix.row_offsets[1]!=source_matrix.cols||target_matrix.row_offsets[1]!=target_matrix.cols)
        throw std::runtime_error("OPT-12 fixture dimensions are inconsistent");
    for(std::size_t i=0;i<source.variables().size();++i) {
        const auto& bound=source.variables()[i];
        const auto& target_bound=target.variables()[i];
        if(bound.lower!=std::optional<double>{0.0}||bound.upper||target_bound.lower!=bound.lower||target_bound.upper!=bound.upper)
            throw std::runtime_error("OPT-12 fixture variable bounds differ from the declared nonnegative domain");
    }
    const auto source_coefficients=source_matrix.values;
    const auto target_coefficients=target_matrix.values;
    if(source_coefficients.size()!=source_matrix.cols||target_coefficients.size()!=target_matrix.cols||
        !std::all_of(source_coefficients.begin(),source_coefficients.end(),[](double value){return value>0.0;})||
        !std::equal(source_coefficients.begin(),source_coefficients.end(),target_coefficients.begin()))
        throw std::runtime_error("OPT-12 fixture coefficients differ from the declared positive row");
    for(std::size_t i=0;i<source_matrix.cols;++i)
        if(source_matrix.column_indices[i]!=i||target_matrix.column_indices[i]!=i)
            throw std::runtime_error("OPT-12 fixture constraint does not cover every column in order");
    std::vector<double> coefficients(source_coefficients.begin(),source_coefficients.end());
    std::ostringstream out;
    const auto source_rhs=rhs_upper(source),target_rhs=rhs_upper(target);
    double best_rate=0.0;
    for(std::size_t i=0;i<target.objective().size();++i)
        best_rate=std::min(best_rate,target.objective()[i]/coefficients[i]);
    const double expected=target_rhs*best_rate+target.offset();
    if(source.offset()!=0.0||target.offset()!=0.0)
        throw std::runtime_error("OPT-12 fixture objective offset is not zero");
    out<<std::setprecision(17)<<"{\"schema\":\"csl.opt12-fixture/1\",\"scenario\":"<<quote(scenario)
        <<",\"fixture\":{\"rows\":"<<source_matrix.rows<<",\"columns\":"<<source_matrix.cols
        <<",\"source_objective\":"<<vector_description(source.objective())
        <<",\"changed_objective\":"<<vector_description(target.objective())
        <<",\"coefficient\":"<<vector_description(std::span<const double>{coefficients})
        <<",\"variable_bounds\":{\"lower\":0,\"upper\":null},\"row_sense\":\"upper\""
        <<",\"source_rhs\":"<<source_rhs<<",\"changed_rhs\":"<<target_rhs
        <<",\"expected_objective\":"<<expected;
    std::vector<std::size_t> changed;
    for(std::size_t i=0;i<source.objective().size();++i)
        if(source.objective()[i]!=target.objective()[i])changed.push_back(i);
    if(!changed.empty()) {
        if(scenario!="transfer-cost"||changed.size()!=2)
            throw std::runtime_error("OPT-12 objective change is outside the declared fixture profile");
        out<<",\"objective_change\":\"";
        for(std::size_t j=0;j<changed.size();++j) {
            if(j)out<<"; ";
            const auto i=changed[j];
            out<<"column "<<i<<": "<<source.objective()[i]<<" to "<<target.objective()[i];
        }
        out<<'"';
    }
    out<<"}}";
    return out.str();
}

std::optional<std::string> field(const std::string& diagnostics,const std::string& key) {
    const std::string prefix="\n"+key+"=";
    const auto start=diagnostics.find(prefix);
    if(start==std::string::npos)return {};
    const auto value=start+prefix.size();
    const auto end=diagnostics.find('\n',value);
    return diagnostics.substr(value,end==std::string::npos?end:end-value);
}

std::vector<std::string> attempts(const std::string& diagnostics) {
    constexpr std::string_view marker="\nwarm_start.rejected_attempt_diagnostics:\n";
    const auto split=diagnostics.find(marker);
    if(split==std::string::npos)return {diagnostics};
    return {diagnostics.substr(0,split),diagnostics.substr(split+marker.size())};
}

std::string quote(const std::string& value);
std::string json_number(const std::optional<std::string>& value);

std::string phase_sum(const std::string& diagnostics,const std::string& key,bool absent_is_zero=false) {
    double sum=0;bool available=false;
    for(const auto& attempt:attempts(diagnostics))if(const auto value=field(attempt,key)) {
        sum+=std::stod(*value);available=true;
    }
    if(!available)return absent_is_zero?"0":"null";
    std::ostringstream out;out<<std::setprecision(17)<<sum;return out.str();
}

std::string attempt_timings(const std::string& diagnostics) {
    std::ostringstream out;out<<'[';bool first=true;
    for(const auto& attempt:attempts(diagnostics)) {
        if(!first)out<<',';
        first=false;
        out<<"{\"model_load_seconds\":"<<json_number(field(attempt,"native.load_seconds"))
            <<",\"basis_transfer_seconds\":"<<json_number(field(attempt,"warm_start.setup_seconds").value_or("0"))
            <<",\"solve_seconds\":"<<json_number(field(attempt,"native.solve_seconds"))
            <<",\"cache_state\":"<<quote(field(attempt,"warm_start.cache_state").value_or("disabled"))
            <<",\"basis_accepted\":"<<(field(attempt,"warm_start.accepted").value_or("false"))
            <<",\"native_run\":"<<(field(attempt,"native_run").value_or("false"))<<'}';
    }
    out<<']';return out.str();
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
    const bool transfer_cost=scenario=="transfer-cost";
    const double source_rhs=columns==1?1.0:(transfer_cost?50000.0:20.0);
    const double target_rhs=columns==1?0.5:(transfer_cost?49999.0:19.0);
    const auto source=make_problem(scenario+"-source",columns,source_rhs,transfer_cost);
    const auto target=make_problem(scenario+"-changed",columns,target_rhs,transfer_cost,transfer_cost);
    std::cout<<fixture_event(scenario,source,target)<<'\n';
    for(std::size_t pair=0;pair<repetitions;++pair) {
        for(unsigned order=0;order<2;++order) {
            const bool warm=(pair%2==0)?order==1:order==0;
            auto registration_result=make_highs_registration({
                .simplex_iteration_limit=std::nullopt,.cross_query_warm_start=warm});
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
            const double expected=transfer_cost?-2.0*target_rhs:(columns==1?-0.5:-19.0);
            if(!primal||std::abs(primal->objective-expected)>1e-9)
                throw std::runtime_error("measured solve differs from the independent literal objective");
            std::cout<<std::setprecision(17)
                <<"{\"schema\":\"csl.opt12-cost-trial/1\",\"scenario\":"<<quote(scenario)
                <<",\"mode\":"<<quote(warm?"warm":"cold")<<",\"pair\":"<<pair
                <<",\"order\":"<<order<<",\"status\":\"verified\",\"expected_objective\":"<<expected
                <<",\"objective\":"<<primal->objective<<",\"wall_ns\":"<<elapsed
                <<",\"model_load_seconds\":"<<phase_sum(result->raw_diagnostics,"native.load_seconds")
                <<",\"basis_transfer_seconds\":"<<phase_sum(result->raw_diagnostics,"warm_start.setup_seconds",true)
                <<",\"solve_seconds\":"<<phase_sum(result->raw_diagnostics,"native.solve_seconds")
                <<",\"native_attempts\":"<<attempt_timings(result->raw_diagnostics)
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
        std::cout<<"{\"schema\":\"csl.opt12-build/1\",\"source_commit\":"<<quote(csl::reporting::build::source_commit)
            <<",\"build_owner_sha256\":"<<quote(csl::reporting::build::build_owner_sha256)
            <<",\"compiler\":"<<quote(csl::reporting::build::compiler)
            <<",\"compiler_version\":"<<quote(csl::reporting::build::compiler_version)
            <<",\"generator\":"<<quote(csl::reporting::build::generator)
            <<",\"architecture\":"<<quote(csl::reporting::build::architecture)
            <<",\"configured_flags\":"<<quote(csl::reporting::build::configured_flags)
            <<",\"release_flags\":"<<quote(csl::reporting::build::release_flags)
            <<",\"configuration\":"<<quote(CSL_OPT12_BUILD_CONFIG)
            <<",\"ndebug\":"
#ifdef NDEBUG
            <<"true"
#else
            <<"false"
#endif
            <<"}\n";
        run_pair("tiny-overhead",1,repetitions);
        run_pair("small-reuse",40,repetitions);
        run_pair("transfer-cost",100000,repetitions);
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<error.what()<<'\n';return 1;
    }
}
