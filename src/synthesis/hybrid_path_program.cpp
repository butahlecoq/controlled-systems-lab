#include <csl/synthesis/hybrid_path_program.hpp>

#include <algorithm>
#include <cmath>
#include <limits>

namespace csl::synthesis {
namespace {
Diagnostics one(Diagnostic diagnostic) { return Diagnostics{std::move(diagnostic)}; }
std::optional<Termination> interruption(const ExecutionContext& context) {
    if(context.cancellation.stop_requested()) return Termination::cancelled;
    if(context.deadline && std::chrono::steady_clock::now()>=*context.deadline)
        return Termination::resource_limit;
    return {};
}
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

HybridPortfolioProgramResult build_hybrid_portfolio_programs(const model::HybridSystem& system,
    const model::HybridRequest& request,ProblemId problem,model::HybridEnumerationLimits enumeration_limits,
    model::HybridRelationLimits relation_limits,optimization::ObjectivePolicy policy,
    std::stop_token cancellation) {
    if(problem.value.empty()) return one({DiagnosticCode::invalid_input,"hybrid.program.problem","Problem identity must be nonempty"});
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid portfolio construction was cancelled before profile admission"};
    const auto profile_errors=model::check_hybrid_profile(system,request);
    if(!profile_errors.empty()) return profile_errors;
    const auto enumerated=model::enumerate_hybrid_paths(system,request.initial.mode,
        request.allowed_terminal_modes,enumeration_limits,cancellation);
    if(const auto* diagnostic=std::get_if<Diagnostic>(&enumerated)) return one(*diagnostic);
    if(const auto* stopped=std::get_if<OperationStopped>(&enumerated)) return *stopped;
    const auto& paths=std::get<std::vector<model::HybridPath>>(enumerated);
    std::vector<HybridPathProgram> programs;
    programs.reserve(paths.size());
    for(const auto& path:paths) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Hybrid portfolio construction stopped between edge paths; no programs were published"};
        auto built=build_hybrid_path_program(system,request,path,problem,relation_limits,policy,cancellation);
        if(const auto* errors=std::get_if<Diagnostics>(&built)) return *errors;
        if(const auto* stopped=std::get_if<OperationStopped>(&built)) return *stopped;
        programs.push_back(std::get<HybridPathProgram>(std::move(built)));
    }
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid portfolio construction was cancelled before publication"};
    return programs;
}

HybridPortfolioObjectiveAnalysis compare_hybrid_portfolio_objective_bounds(
    std::span<const HybridPathProgram> programs,const HybridPortfolioExecution& execution,
    NumericalPolicy policy) {
    if(!std::isfinite(policy.absolute_tolerance)||policy.absolute_tolerance<0||
       !std::isfinite(policy.relative_tolerance)||policy.relative_tolerance<0)
        return one({DiagnosticCode::invalid_input,"hybrid.objective.policy",
            "Objective comparison tolerances must be finite and nonnegative"});
    if(programs.empty())
        return one({DiagnosticCode::invalid_input,"hybrid.objective.branches",
            "At least one branch program is required for objective comparison"});
    if(execution.branches.size()!=programs.size())
        return one({DiagnosticCode::evidence_mismatch,"hybrid.objective.branches",
            "Execution branch count does not match the supplied programs"});

    std::vector<double> lower_bounds(programs.size());
    std::vector<double> upper_bounds(programs.size());
    std::vector<std::size_t> unresolved;
    for(std::size_t i=0;i<programs.size();++i) {
        const auto& program=programs[i];
        const auto& branch=execution.branches[i];
        if(branch.path!=program.path)
            return one({DiagnosticCode::evidence_mismatch,"hybrid.objective.path",
                "Execution branch order or path does not match the supplied programs"});
        if(!branch.result || branch.termination!=Termination::completed ||
           branch.outcome!=MathematicalOutcome::optimal ||
           branch.result->termination!=Termination::completed ||
           branch.result->outcome.value!=MathematicalOutcome::optimal ||
           !execution.all_supplied_branches_completed) {
            unresolved.push_back(i);
            continue;
        }
        auto validate=[&]<class Program>(const Program& p) {
            return optimization::check_program_result(*branch.result,p,Assurance::numerical);
        };
        const auto diagnostics=std::visit(validate,program.program);
        if(!diagnostics.empty()) return diagnostics;
        const auto& bounds=branch.result->objective;
        if(!bounds.lower || !bounds.upper) {
            unresolved.push_back(i);
            continue;
        }
        auto established=[](const ProgramObjectiveBound& bound) {
            return std::holds_alternative<NumericalCheck>(bound.evidence.support) ||
                std::holds_alternative<SymbolicArgument>(bound.evidence.support);
        };
        if(!established(*bounds.lower)||!established(*bounds.upper)) {
            unresolved.push_back(i);
            continue;
        }
        lower_bounds[i]=bounds.lower->value;
        upper_bounds[i]=bounds.upper->value;
    }
    if(!unresolved.empty()) return HybridPortfolioObjectiveIncomplete{std::move(unresolved)};

    const auto global_lower=*std::min_element(lower_bounds.begin(),lower_bounds.end());
    const auto global_upper=*std::min_element(upper_bounds.begin(),upper_bounds.end());
    std::vector<model::HybridPath> potentially_optimal;
    std::vector<HybridPortfolioBoundSource> lower_sources,upper_sources;
    for(std::size_t i=0;i<programs.size();++i) {
        const auto& evidence=execution.branches[i].result->objective;
        if(lower_bounds[i]==global_lower)
            lower_sources.push_back({programs[i].path,*evidence.lower});
        if(upper_bounds[i]==global_upper)
            upper_sources.push_back({programs[i].path,*evidence.upper});
        const double scale=std::max({1.0,std::abs(lower_bounds[i]),std::abs(global_upper)});
        const double normalized_gap=lower_bounds[i]/scale-global_upper/scale;
        const bool within_tolerance=normalized_gap<=policy.relative_tolerance ||
            normalized_gap-policy.relative_tolerance<=policy.absolute_tolerance/scale;
        if(within_tolerance)
            potentially_optimal.push_back(programs[i].path);
    }
    return HybridPortfolioObjectiveBounds{global_lower,global_upper,
        std::move(potentially_optimal),std::move(lower_sources),std::move(upper_sources),policy};
}

HybridPortfolioExecution execute_hybrid_path_programs(
    std::span<const HybridPathProgram> programs,
    const registry::PreparedProvider<registry::LPPort>& lp,
    const registry::PreparedProvider<registry::ConvexPort>& convex,
    const ExecutionContext& context) {
    using PreparedBranch = std::variant<registry::PreparedPipeline<registry::LPPort>,
        registry::PreparedPipeline<registry::ConvexPort>>;
    HybridPortfolioExecution portfolio;
    portfolio.branches.reserve(programs.size());
    std::vector<std::optional<PreparedBranch>> prepared_branches;
    prepared_branches.reserve(programs.size());
    bool admitted=true;
    std::optional<Termination> preflight_interruption;

    // Admit every branch before creating any solver workspace. A rejection in
    // a later branch must not leave earlier branches partially executed.
    for(const auto& branch:programs) {
        HybridBranchExecution execution;
        execution.path=branch.path;
        auto prepare=[&]<class Program,class Port>(const Program& program,
            const registry::PreparedProvider<Port>& provider)->std::optional<PreparedBranch> {
            if(const auto stop=interruption(context)) {
                execution.termination=*stop;
                preflight_interruption=*stop;
                return {};
            }
            auto selection=provider.prepare(program);
            if(const auto* rejection=std::get_if<registry::Rejection>(&selection)) {
                execution.termination=Termination::operation_rejected;
                execution.providers.push_back(rejection->provenance);
                execution.diagnostics=rejection->diagnostics;
                admitted=false;
                return {};
            }
            auto pipeline=std::get<registry::PreparedPipeline<Port>>(std::move(selection));
            const auto provenance=pipeline.provenance();
            execution.providers.assign(provenance.begin(),provenance.end());
            if(const auto stop=interruption(context)) {
                execution.termination=*stop;
                preflight_interruption=*stop;
                return {};
            }
            return PreparedBranch{std::move(pipeline)};
        };
        std::optional<PreparedBranch> selection;
        if(const auto* linear=std::get_if<LinearProgram>(&branch.program)) selection=prepare(*linear,lp);
        else selection=prepare(std::get<ConvexProgram>(branch.program),convex);
        prepared_branches.push_back(std::move(selection));
        portfolio.branches.push_back(std::move(execution));
    }

    if(!admitted || preflight_interruption) {
        for(std::size_t i=0;i<portfolio.branches.size();++i) {
            auto& branch=portfolio.branches[i];
            if(!branch.diagnostics.empty() || branch.termination==Termination::cancelled ||
               branch.termination==Termination::resource_limit) continue;
            if(preflight_interruption) {
                branch.termination=*preflight_interruption;
                branch.diagnostics={{DiagnosticCode::unsupported,"hybrid.portfolio.preflight_interrupted",
                    "No branch was executed because portfolio admission was cancelled or its deadline expired"}};
            } else {
                branch.termination=Termination::operation_rejected;
                branch.diagnostics={{DiagnosticCode::unsupported,"hybrid.portfolio.admission",
                    "No branch was executed because complete portfolio admission did not succeed"}};
            }
        }
        return portfolio;
    }

    bool complete=true;
    for(std::size_t i=0;i<programs.size();++i) {
        const auto& branch=programs[i];
        auto& execution=portfolio.branches[i];
        auto run=[&]<class Program,class Port>(const Program& program,
            registry::PreparedPipeline<Port>& pipeline) {
            if(const auto stop=interruption(context)) {
                execution.termination=*stop;
                complete=false;
                return;
            }
            auto workspaces=pipeline.create();
            auto outcome=std::get<0>(workspaces)->run(context);
            if(const auto* unsupported=std::get_if<Unsupported>(&outcome)) {
                execution.termination=Termination::operation_rejected;
                execution.diagnostics=unsupported->diagnostics;
                complete=false;
                return;
            }
            auto result=std::get<ProgramResult>(std::move(outcome));
            auto diagnostics=optimization::check_program_result(result,program,Assurance::numerical);
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
        if(const auto* linear=std::get_if<LinearProgram>(&branch.program))
            run(*linear,std::get<registry::PreparedPipeline<registry::LPPort>>(*prepared_branches[i]));
        else run(std::get<ConvexProgram>(branch.program),
            std::get<registry::PreparedPipeline<registry::ConvexPort>>(*prepared_branches[i]));
    }
    portfolio.all_supplied_branches_completed=complete;
    return portfolio;
}

} // namespace csl::synthesis
