#include <csl/adapters/convex/highs.hpp>
#include <nlohmann/json.hpp>
#include <chrono>
#include <fstream>
#include <iostream>
#include <stdexcept>

using nlohmann::json;
using namespace csl;
using namespace csl::optimization;
using namespace csl::registry;

json diagnostics(const Diagnostics& values) {
    auto result=json::array();
    for(const auto& value:values)
        result.push_back({{"code",static_cast<int>(value.code)},
                          {"field",value.field},{"explanation",value.explanation}});
    return result;
}
std::vector<Interval> intervals(const json& array) {
    std::vector<Interval> result;
    for(const auto& row:array) {
        if(!row.is_array() || row.size()!=2) throw std::runtime_error("interval width must be two");
        result.push_back({row[0].is_null()?std::nullopt:std::optional(row[0].get<double>()),
                          row[1].is_null()?std::nullopt:std::optional(row[1].get<double>())});
    }
    return result;
}
const char* termination_name(Termination value) {
    switch(value) {
    case Termination::completed:return "completed";
    case Termination::cancelled:return "cancelled";
    case Termination::deadline_expired:return "deadline_expired";
    case Termination::resource_limit:return "resource_limit";
    case Termination::numerical_failure:return "numerical_failure";
    case Termination::operation_rejected:return "operation_rejected";
    case Termination::contract_rejected:return "contract_rejected";
    }
    return "unknown";
}
const char* outcome_name(MathematicalOutcome value) {
    switch(value) {
    case MathematicalOutcome::optimal:return "optimal";
    case MathematicalOutcome::infeasible:return "infeasible";
    case MathematicalOutcome::unbounded:return "unbounded";
    case MathematicalOutcome::infimum_not_attained:return "infimum_not_attained";
    case MathematicalOutcome::undetermined:return "undetermined";
    }
    return "unknown";
}
int main(int argc,char** argv) try {
    if(argc!=2) throw std::runtime_error("usage: csl_mpc11_affine program.json");
    const auto setup_start=std::chrono::steady_clock::now();
    std::ifstream file(argv[1]);
    const auto input=json::parse(file);
    if(input.at("schema")!="csl.mpc11.affine-program/1") throw std::runtime_error("unsupported program schema");
    const auto diagonal=input.at("q_diagonal").get<Vector>();
    const auto n=diagonal.size();
    if(n==0 || n>4096) throw std::runtime_error("unsupported variable count");
    Vector hessian(n*n,0);
    for(std::size_t i=0;i<n;++i)hessian[i*n+i]=diagonal[i];
    const auto& matrix=input.at("constraints");
    SparseMatrix constraints{matrix.at("rows").get<std::size_t>(),n,
        matrix.at("row_offsets").get<std::vector<std::size_t>>(),
        matrix.at("column_indices").get<std::vector<std::size_t>>(),matrix.at("values").get<Vector>()};
    const auto made=make_convex_program({{{input.at("case_id").get<std::string>()},
        {input.at("program_id").get<std::string>()}},
        QuadraticTerminal{{n,n,std::move(hessian)},input.at("linear").get<Vector>(),input.at("offset").get<double>()},
        std::move(constraints),intervals(input.at("variables")),intervals(input.at("rows")),{}});
    json output={{"schema","csl.mpc11.affine-result/1"},{"case_id",input.at("case_id")},
        {"program_id",input.at("program_id")},{"program_sha256",input.at("program_sha256")},
        {"formulation","public-CSL-ConvexProgram-joint-state-control-history"},
        {"assurance","numerical-binary64"},{"family_coverage","not-established"}};
    if(const auto* errors=std::get_if<Diagnostics>(&made)) {
        output["termination"]="contract_rejected";output["diagnostics"]=diagnostics(*errors);
        std::cout<<output.dump()<<'\n';return 0;
    }
    const auto* program=std::get_if<ConvexProgram>(&made);
    if(!program)throw std::runtime_error("program creation stopped");
    Registry<ConvexPort> registry;
    const auto registration=adapters::convex::make_highs_registration();
    if(!std::holds_alternative<Registration<ConvexPort>>(registration))throw std::runtime_error("registration rejected");
    if(registry.add(std::get<Registration<ConvexPort>>(registration)))throw std::runtime_error("registration collision");
    Requirements requirements;requirements.output.representation={"csl.program-result.v1"};
    const auto preparation=prepare_pipeline(select(registry,{{"csl.convex.highs"},{}},*program,requirements));
    if(const auto* rejection=std::get_if<Rejection>(&preparation)) {
        output["termination"]="operation_rejected";output["diagnostics"]=diagnostics(rejection->diagnostics);
        std::cout<<output.dump()<<'\n';return 0;
    }
    const auto& prepared=std::get<PreparedPipeline<ConvexPort>>(preparation);
    const auto actual=prepared.provenance()[0].actual.value();
    output["provider"]={{"id",actual.id.value},{"version",actual.version}};
    auto [workspace]=prepared.create();
    const auto solve_start=std::chrono::steady_clock::now();
    ExecutionContext context{std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),{},{},{1e-8,1e-8},"mpc11-affine"};
    context.deadline=solve_start+std::chrono::seconds(290);
    const auto outcome=workspace->run(context);
    const auto solve_end=std::chrono::steady_clock::now();
    output["setup_ns"]=std::chrono::duration_cast<std::chrono::nanoseconds>(solve_start-setup_start).count();
    output["solve_ns"]=std::chrono::duration_cast<std::chrono::nanoseconds>(solve_end-solve_start).count();
    if(const auto* unsupported=std::get_if<Unsupported>(&outcome)) {
        output["termination"]="operation_rejected";output["diagnostics"]=diagnostics(unsupported->diagnostics);
    } else {
        const auto& result=std::get<ProgramResult>(outcome);
        output["termination"]=termination_name(result.termination);output["mathematical_outcome"]=outcome_name(result.outcome.value);
        output["evidence_support"]="unestablished-native-claim";
        output["raw_diagnostics"]=result.raw_diagnostics;
        output["contract_diagnostics"]=diagnostics(check_program_result(result,*program,Assurance::numerical));
        if(result.primal) {
            output["primal"]=*result.primal;
            const auto evaluation=evaluate_primal(*program,*result.primal,{1e-8,1e-8},{{"mpc11.literal-q-check"},"1"});
            if(const auto* checked=std::get_if<ConvexPrimalEvaluation>(&evaluation))
                output["primal_check"]={{"objective",checked->original_objective},
                    {"row_violation",checked->residuals.rows.violation},{"variable_violation",checked->residuals.variables.violation}};
        }
        if(result.residuals.dual) {
            const auto& dual=*result.residuals.dual;
            auto measure=[](const auto& item)->json {return item?json{{"violation",item->violation},{"scale",item->scale}}:json(nullptr);};
            output["dual_residuals"]={{"stationarity",measure(dual.stationarity)},
                {"signs",measure(dual.signs)},{"complementarity",measure(dual.complementarity)}};
        }
    }
    std::cout<<output.dump()<<'\n';return 0;
} catch(const std::exception& error) {
    std::cerr<<error.what()<<'\n';return 1;
}
