#include <csl/synthesis/hybrid_path_program.hpp>

#include <algorithm>
#include <limits>
#include <type_traits>

namespace csl::synthesis {
namespace {
Diagnostics one(Diagnostic diagnostic) { return Diagnostics{std::move(diagnostic)}; }
ProgramId path_program_id(const model::HybridPath& path) {
    std::string value="hybrid-path";
    for(const auto& edge:path.edges)
        value += ":"+std::to_string(edge.value.size())+":"+edge.value;
    return ProgramId{std::move(value)};
}
}

HybridPathProgramResult build_hybrid_path_program(const model::HybridSystem& system,
    const model::HybridRequest& request, const model::HybridPath& path, ProblemId problem,
    model::HybridRelationLimits limits, optimization::ObjectivePolicy policy,
    std::stop_token cancellation) {
    if(problem.value.empty()) return one({DiagnosticCode::invalid_input,"hybrid.program.problem","Problem identity must be nonempty"});
    if(cancellation.stop_requested()) return OperationStopped{StopReason::cancelled,"Hybrid path program construction was cancelled before relation composition"};
    auto composed=model::compose_hybrid_path_relation(system,request,path,limits,cancellation);
    if(const auto* diagnostic=std::get_if<Diagnostic>(&composed)) return one(*diagnostic);
    if(const auto* stopped=std::get_if<OperationStopped>(&composed)) return *stopped;
    auto lifted=model::lift_hybrid_terminal_objective(system,request,path,limits);
    if(const auto* diagnostic=std::get_if<Diagnostic>(&lifted)) return one(*diagnostic);
    auto relation=std::get<sets::SetData>(std::move(composed));
    const auto representation=relation.representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h) return one({DiagnosticCode::unsupported,"hybrid.program.relation","Direct path program requires its composed H relation"});
    if(cancellation.stop_requested()) return OperationStopped{StopReason::cancelled,"Hybrid path program construction was cancelled before program assembly"};
    if(h->inequalities.rows()>std::numeric_limits<std::size_t>::max()-h->equalities.rows())
        return one({DiagnosticCode::unsupported,"hybrid.program.rows","Joint relation row count overflows size_t"});
    const auto row_count=h->inequalities.rows()+h->equalities.rows();
    if(row_count==std::numeric_limits<std::size_t>::max())
        return one({DiagnosticCode::unsupported,"hybrid.program.rows","Joint relation cannot represent its CSR row offsets"});
    SparseMatrix constraints{row_count,h->inequalities.cols(),std::vector<std::size_t>{0},{},{}};
    std::vector<Interval> row_bounds;
    row_bounds.reserve(row_count);
    constraints.row_offsets.reserve(row_count+1);
    auto add_rows=[&](numeric::MatrixView matrix,numeric::VectorView rhs,bool equality)->bool {
        for(std::size_t i=0;i<matrix.rows();++i) {
            if(cancellation.stop_requested()) return false;
            for(std::size_t j=0;j<matrix.cols();++j) {
                const double value=matrix(i,j);
                if(value!=0) { constraints.column_indices.push_back(j); constraints.values.push_back(value); }
            }
            constraints.row_offsets.push_back(constraints.values.size());
            row_bounds.push_back(equality?Interval{rhs[i],rhs[i]}:Interval{std::nullopt,rhs[i]});
        }
        return true;
    };
    if(!add_rows(h->inequalities,h->upper_bounds,false)||!add_rows(h->equalities,h->equality_values,true))
        return OperationStopped{StopReason::cancelled,"Hybrid path program assembly was cancelled; no program was returned"};
    std::vector<Interval> variables(constraints.cols);
    const ProgramIdentity identity{std::move(problem),path_program_id(path)};
    std::optional<std::variant<LinearProgram,ConvexProgram>> program;
    if(const auto* linear=std::get_if<LinearTerminal>(&std::get<TerminalObjective>(lifted))) {
        auto made=optimization::make_linear_program({identity,linear->coefficients,linear->offset,
            std::move(constraints),std::move(variables),std::move(row_bounds)});
        if(const auto* errors=std::get_if<Diagnostics>(&made)) return *errors;
        program=std::variant<LinearProgram,ConvexProgram>{std::get<LinearProgram>(std::move(made))};
    } else {
        const auto& objective=std::get<TerminalObjective>(lifted);
        std::optional<ProgramId> squared;
        if(std::holds_alternative<ResidualNormTerminal>(objective))
            squared=ProgramId{identity.program.value+":norm-square"};
        auto made=optimization::make_convex_program({identity,objective,std::move(constraints),
            std::move(variables),std::move(row_bounds),std::move(squared)},policy);
        if(const auto* errors=std::get_if<Diagnostics>(&made)) return *errors;
        if(const auto* stopped=std::get_if<OperationStopped>(&made)) return *stopped;
        program=std::variant<LinearProgram,ConvexProgram>{std::get<ConvexProgram>(std::move(made))};
    }
    if(cancellation.stop_requested()) return OperationStopped{StopReason::cancelled,"Hybrid path program construction was cancelled before publication"};
    return HybridPathProgram{path,std::move(relation),std::get<TerminalObjective>(std::move(lifted)),std::move(*program)};
}

HybridPortfolioExecution execute_hybrid_path_programs(
    std::span<const HybridPathProgram> programs,
    const registry::PreparedProvider<registry::LPPort>& lp,
    const registry::PreparedProvider<registry::ConvexPort>& convex,
    const ExecutionContext& context) {
    HybridPortfolioExecution portfolio;
    portfolio.branches.reserve(programs.size());
    bool complete=true;
    for(const auto& branch:programs) {
        HybridBranchExecution execution;
        execution.path=branch.path;
        auto run=[&]<class Program,class Port>(const Program& program,
            const registry::PreparedProvider<Port>& provider) {
            if(context.cancellation.stop_requested() ||
               (context.deadline && std::chrono::steady_clock::now()>=*context.deadline)) {
                execution.termination=context.cancellation.stop_requested()?
                    Termination::cancelled:Termination::resource_limit;
                complete=false;
                return;
            }
            auto prepared=provider.prepare(program);
            if(const auto* rejection=std::get_if<registry::Rejection>(&prepared)) {
                execution.termination=Termination::operation_rejected;
                execution.providers.push_back(rejection->provenance);
                execution.diagnostics=rejection->diagnostics;
                complete=false;
                return;
            }
            auto pipeline=std::get<registry::PreparedPipeline<Port>>(std::move(prepared));
            const auto provenance=pipeline.provenance();
            execution.providers.assign(provenance.begin(),provenance.end());
            auto workspaces=pipeline.create();
            auto outcome=std::get<0>(workspaces)->run(context);
            if(const auto* unsupported=std::get_if<Unsupported>(&outcome)) {
                execution.termination=Termination::operation_rejected;
                execution.diagnostics=unsupported->diagnostics;
                complete=false;
                return;
            }
            auto result=std::get<ProgramResult>(std::move(outcome));
            Diagnostics diagnostics;
            if constexpr(std::is_same_v<Program,LinearProgram>)
                diagnostics=optimization::check_program_result(result,program,Assurance::numerical);
            else
                diagnostics=optimization::check_program_result(result,program,Assurance::numerical);
            if(!diagnostics.empty()) {
                execution.termination=Termination::contract_rejected;
                execution.diagnostics=std::move(diagnostics);
                complete=false;
                return;
            }
            execution.termination=result.termination;
            execution.outcome=result.outcome.value;
            if(result.termination!=Termination::completed) complete=false;
            execution.result=std::move(result);
        };
        if(const auto* linear=std::get_if<LinearProgram>(&branch.program)) run(*linear,lp);
        else run(std::get<ConvexProgram>(branch.program),convex);
        portfolio.branches.push_back(std::move(execution));
    }
    portfolio.all_supplied_branches_completed=complete;
    return portfolio;
}

} // namespace csl::synthesis
