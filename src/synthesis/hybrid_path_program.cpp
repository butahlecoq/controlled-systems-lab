#include <csl/synthesis/hybrid_path_program.hpp>

#include <algorithm>
#include <cmath>
#include <limits>

namespace csl::synthesis {
namespace {
Diagnostics one(Diagnostic diagnostic) { return Diagnostics{std::move(diagnostic)}; }
std::optional<Diagnostic> hybrid_objective_policy_error(optimization::ObjectivePolicy policy) {
    if(policy.assurance!=Assurance::numerical && policy.assurance!=Assurance::validated)
        return Diagnostic{DiagnosticCode::invalid_input,"hybrid.adapter.objective_policy",
            "Hybrid objective assurance value is unknown"};
    if(!std::isfinite(policy.numerical.absolute_tolerance)||
       policy.numerical.absolute_tolerance<0||
       !std::isfinite(policy.numerical.relative_tolerance)||
       policy.numerical.relative_tolerance<0)
        return Diagnostic{DiagnosticCode::invalid_input,"hybrid.adapter.objective_policy",
            "Hybrid objective tolerances must be finite and nonnegative"};
    if(policy.assurance==Assurance::validated)
        return Diagnostic{DiagnosticCode::unsupported,"hybrid.adapter.objective_policy",
            "Hybrid objective construction currently supports numerical assurance only"};
    return {};
}
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
Diagnostics hybrid_path_admission_errors(const model::HybridSystem& system,
    const model::HybridRequest& request, const model::HybridPath& path) {
    auto errors=model::check_hybrid_profile(system,request);
    if(!errors.empty()) return errors;
    if(path.edges.size()!=system.horizon || path.modes.size()!=path.edges.size()+1 || path.modes.empty() ||
       path.modes.front()!=request.initial.mode ||
       std::find(request.allowed_terminal_modes.begin(),request.allowed_terminal_modes.end(),path.modes.back())==
           request.allowed_terminal_modes.end())
        return one({DiagnosticCode::invalid_input,"hybrid.adapter.path",
            "Adapter path does not match the admitted horizon, initial mode, and terminal modes"});
    for(std::size_t i=0;i<path.edges.size();++i) {
        const auto edge=std::find_if(system.edges.begin(),system.edges.end(),[&](const auto& candidate) {
            return candidate.id==path.edges[i];
        });
        if(edge==system.edges.end() || edge->source!=path.modes[i] || edge->target!=path.modes[i+1])
            return one({DiagnosticCode::invalid_input,"hybrid.adapter.path_edge",
                "Adapter path contains an unknown or disconnected edge"});
    }
    return {};
}
using HybridTrajectoryPortfolioPreflightResult =
    std::variant<std::monostate,Diagnostics,OperationStopped>;
using HybridTrajectoryOperationPreflightResult = std::variant<std::monostate,
    model::HybridPathCompositionFailureReport,Diagnostics,OperationStopped>;

HybridTrajectoryOperationPreflightResult preflight_hybrid_trajectory_operations(
    const HybridDirectTrajectoryAdapter& adapter,const model::HybridSystem& system,
    const model::HybridRequest& request,std::span<const model::HybridPath> paths,
    model::HybridRelationLimits limits,optimization::ObjectivePolicy policy,
    std::stop_token cancellation) {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid trajectory operation preflight was cancelled before adapter admission"};
    if(const auto policy_error=hybrid_objective_policy_error(policy); policy_error)
        return Diagnostics{*policy_error};
    const auto evidence_rejection=[&](const model::HybridPath& path,Diagnostic diagnostic) {
        return HybridTrajectoryOperationPreflightResult{model::HybridPathCompositionFailureReport{
            path,limits,{},std::move(diagnostic)}};
    };
    const auto result=adapter.preflight(system,request,paths,limits,policy,cancellation);
    if(const auto* failure=std::get_if<HybridDirectTrajectoryPreflightFailure>(&result)) {
        if(paths.empty())
            return Diagnostics{{DiagnosticCode::evidence_mismatch,
                "hybrid.adapter.preflight_inventory",
                "Direct-trajectory preflight was invoked without a requested path"}};
        if(std::find(paths.begin(),paths.end(),failure->path)==paths.end())
            return evidence_rejection(paths.front(),Diagnostic{DiagnosticCode::evidence_mismatch,
                "hybrid.adapter.preflight_path",
                "Direct-trajectory preflight returned a failure for a path outside the request"});
        if(failure->limits.max_variables!=limits.max_variables||
           failure->limits.max_rows!=limits.max_rows||
           failure->limits.max_matrix_elements!=limits.max_matrix_elements)
            return evidence_rejection(failure->path,Diagnostic{DiagnosticCode::evidence_mismatch,
                "hybrid.adapter.preflight_limits",
                "Direct-trajectory preflight failure report lost the configured relation limits"});
        if(failure->diagnostic.field.empty()||failure->diagnostic.explanation.empty())
            return evidence_rejection(failure->path,Diagnostic{DiagnosticCode::evidence_mismatch,
                "hybrid.adapter.preflight_diagnostics",
                "Direct-trajectory preflight failure did not include a complete primary diagnostic"});
        return model::HybridPathCompositionFailureReport{failure->path,failure->limits,
            failure->relation_operations,failure->diagnostic};
    }
    if(const auto* stopped=std::get_if<OperationStopped>(&result)) return *stopped;
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid trajectory construction was cancelled after adapter preflight"};
    return std::monostate{};
}

HybridTrajectoryPortfolioPreflightResult preflight_hybrid_trajectory_capabilities(
    const HybridDirectTrajectoryAdapter& adapter,const model::HybridRequest& request,
    std::span<const model::HybridPath> paths,optimization::ObjectivePolicy policy,
    std::stop_token cancellation) {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid trajectory capability preflight was cancelled before adapter admission"};
    if(const auto policy_error=hybrid_objective_policy_error(policy); policy_error)
        return one(*policy_error);
    const auto capability=adapter.capabilities();
    if(capability.assurance!=Assurance::numerical)
        return one({DiagnosticCode::unsupported,"hybrid.adapter.assurance",
            "Validated adapter assurance is unsupported until its evidence is carried in the result"});
    if(!capability.preserves_branch_labelled_joint_relation)
        return one({DiagnosticCode::unsupported,"hybrid.adapter.branch_relation",
            "Direct-trajectory adapter does not declare branch-labelled joint-relation support"});
    for(const auto& path:paths) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,
                "Hybrid trajectory capability preflight was cancelled between edge paths"};
        if(path.modes.empty())
            return one({DiagnosticCode::invalid_input,"hybrid.adapter.path",
                "Trajectory capability preflight received a path without a terminal mode"});
        const auto& terminal_mode=path.modes.back();
        const auto objective=std::find_if(request.terminal_objectives.begin(),
            request.terminal_objectives.end(),[&](const auto& candidate) {
                return candidate.mode==terminal_mode;
            });
        if(objective==request.terminal_objectives.end())
            return one({DiagnosticCode::invalid_input,"hybrid.adapter.objective",
                "No terminal objective is defined for candidate path "+path_program_id(path).value+
                " at terminal stage "+std::to_string(path.edges.size())});
        const bool supported=std::visit([&](const auto& value) {
            using T=std::decay_t<decltype(value)>;
            if constexpr(std::is_same_v<T,LinearTerminal>) return capability.linear_objectives;
            else return capability.convex_objectives;
        },objective->objective);
        if(!supported)
            return one({DiagnosticCode::unsupported,"hybrid.portfolio.objective",
                "Direct-trajectory adapter does not support the terminal objective for mode "+
                terminal_mode.value+" on candidate path "+path_program_id(path).value+
                " at terminal stage "+std::to_string(path.edges.size())});
    }
    return std::monostate{};
}
bool same_limits(model::HybridRelationLimits left,model::HybridRelationLimits right) {
    return left.max_variables==right.max_variables && left.max_rows==right.max_rows &&
        left.max_matrix_elements==right.max_matrix_elements;
}
Diagnostics hybrid_operation_trace_errors(const model::HybridPath& path,
    model::HybridRelationLimits limits,
    std::span<const model::HybridRelationOperationRecord> operations,bool require_nonempty,
    std::optional<std::size_t> relation_dimension = std::nullopt) {
    struct ExpectedOperation {
        model::HybridRelationOperationKind kind;
        std::size_t stage;
        std::optional<model::HybridModeId> mode;
        std::optional<model::HybridEdgeId> edge;
    };
    std::vector<ExpectedOperation> expected;
    expected.push_back({model::HybridRelationOperationKind::initial_state,0,path.modes.front(),{}});
    for(std::size_t stage=0;stage<=path.edges.size();++stage) {
        expected.push_back({model::HybridRelationOperationKind::post_state_invariant,stage,path.modes[stage],{}});
        if(stage==path.edges.size()) continue;
        expected.push_back({model::HybridRelationOperationKind::mode_flow,stage,path.modes[stage],{}});
        expected.push_back({model::HybridRelationOperationKind::continuous_control,stage,path.modes[stage],{}});
        expected.push_back({model::HybridRelationOperationKind::pre_reset_invariant,stage+1,path.modes[stage],{}});
        expected.push_back({model::HybridRelationOperationKind::transition_guard,stage,{},path.edges[stage]});
        expected.push_back({model::HybridRelationOperationKind::reset_relation,stage,{},path.edges[stage]});
    }
    if((require_nonempty && operations.empty()) || operations.size()>expected.size() ||
       (require_nonempty && operations.size()!=expected.size()))
        return one({DiagnosticCode::evidence_mismatch,"hybrid.adapter.operations",
            "Adapter operation trace is empty, incomplete, or longer than the path operation plan"});
    std::size_t previous_rows=0,previous_elements=0;
    std::optional<std::size_t> joint_variables;
    for(std::size_t i=0;i<operations.size();++i) {
        const auto& operation=operations[i];
        const auto& expected_operation=expected[i];
        const bool row_overflow=operation.rows_added>std::numeric_limits<std::size_t>::max()-previous_rows;
        const bool element_overflow=operation.cumulative_rows!=0 &&
            operation.joint_variables>std::numeric_limits<std::size_t>::max()/operation.cumulative_rows;
        if(operation.implementation_id.empty() || operation.implementation_version.empty() ||
           operation.joint_variables>limits.max_variables || operation.cumulative_rows>limits.max_rows ||
           operation.cumulative_matrix_elements>limits.max_matrix_elements ||
           row_overflow || operation.cumulative_rows!=previous_rows+operation.rows_added ||
           element_overflow || operation.cumulative_matrix_elements!=operation.cumulative_rows*operation.joint_variables ||
           operation.cumulative_matrix_elements<previous_elements ||
           (joint_variables && operation.joint_variables!=*joint_variables) ||
           (relation_dimension && operation.joint_variables!=*relation_dimension) ||
           operation.operation!=expected_operation.kind || operation.stage!=expected_operation.stage ||
           operation.mode!=expected_operation.mode || operation.edge!=expected_operation.edge)
            return one({DiagnosticCode::evidence_mismatch,"hybrid.adapter.operations",
                "Adapter operation provenance is incomplete, out of path, or exceeds configured limits"});
        joint_variables=operation.joint_variables;
        previous_rows=operation.cumulative_rows;
        previous_elements=operation.cumulative_matrix_elements;
    }
    return {};
}
}

namespace {
HybridPathProgramResult build_joint_hybrid_path_program(const model::HybridSystem& system,
    const model::HybridRequest& request, const model::HybridPath& path, ProblemId problem,
    model::HybridRelationLimits limits, optimization::ObjectivePolicy policy,
    std::stop_token cancellation) {
    if(problem.value.empty()) return one({DiagnosticCode::invalid_input,"hybrid.program.problem","Problem identity must be nonempty"});
    if(cancellation.stop_requested()) return OperationStopped{StopReason::cancelled,"Hybrid path program construction was cancelled before relation composition"};
    auto composed=model::compose_hybrid_path_relation_with_report(system,request,path,limits,cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&composed)) {
        return *failure;
    }
    auto lifted=model::lift_hybrid_terminal_objective(system,request,path,limits);
    if(const auto* diagnostic=std::get_if<Diagnostic>(&lifted)) return one(*diagnostic);
    auto composition=std::get<model::HybridComposedPathRelation>(std::move(composed));
    auto relation=std::move(composition.relation);
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
    return HybridPathProgram{path,std::move(relation),std::get<TerminalObjective>(std::move(lifted)),
        std::move(*program),composition.limits,std::move(composition.operations)};
}
}

HybridDirectTrajectoryCapabilities JointHDirectTrajectoryAdapter::capabilities() const noexcept {
    return {true,true,true,Assurance::numerical};
}

HybridReachabilityPreflightResult HybridReachabilityAdapter::preflight(
    const model::HybridSystem&,const model::HybridRequest&,const model::HybridPath&,
    model::HybridRelationLimits,std::stop_token cancellation) const {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid reachability preflight was cancelled before adapter admission"};
    return Diagnostics{{DiagnosticCode::unsupported,"hybrid.reachability.preflight",
        "Reachability adapter must implement preflight before it can be used"}};
}

HybridReachabilityCapabilities JointHReachabilityAdapter::capabilities() const noexcept {
    return {true,Assurance::numerical};
}

HybridReachabilityPreflightResult JointHReachabilityAdapter::preflight(
    const model::HybridSystem& system,const model::HybridRequest& request,
    const model::HybridPath& path,model::HybridRelationLimits limits,
    std::stop_token cancellation) const {
    return model::preflight_hybrid_path_relations(system,request,
        std::span<const model::HybridPath>(&path,1),limits,cancellation);
}

HybridPathReachabilityResult JointHReachabilityAdapter::compose_path(
    const model::HybridSystem& system,const model::HybridRequest& request,
    const model::HybridPath& path,model::HybridRelationLimits limits,
    std::stop_token cancellation) const {
    auto composed=model::compose_hybrid_path_relation_with_report(system,request,path,limits,cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&composed)) return *failure;
    auto relation=std::get<model::HybridComposedPathRelation>(std::move(composed));
    return HybridPathReachability{path,std::move(relation.relation),relation.limits,
        std::move(relation.operations),Assurance::numerical};
}

HybridPathReachabilityResult compute_hybrid_path_reachability(
    const HybridReachabilityAdapter& adapter,const model::HybridSystem& system,
    const model::HybridRequest& request,const model::HybridPath& path,
    model::HybridRelationLimits limits,std::stop_token cancellation) {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid reachability was cancelled before profile admission"};
    const auto admission=hybrid_path_admission_errors(system,request,path);
    if(!admission.empty()) return admission;
    const auto path_preflight=adapter.preflight(system,request,path,limits,cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&path_preflight)) {
        if(failure->path!=path)
            return one({DiagnosticCode::evidence_mismatch,"hybrid.reachability.preflight_path",
                "Reachability preflight returned a failure report for a different path"});
        if(!same_limits(failure->limits,limits))
            return one({DiagnosticCode::evidence_mismatch,"hybrid.reachability.preflight_limits",
                "Reachability preflight failure report lost the configured relation limits"});
        return *failure;
    }
    if(const auto* errors=std::get_if<Diagnostics>(&path_preflight)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&path_preflight)) return *stopped;
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid reachability was cancelled after adapter preflight"};
    const auto capability=adapter.capabilities();
    if(capability.assurance!=Assurance::numerical)
        return one({DiagnosticCode::unsupported,"hybrid.reachability.assurance",
            "Validated reachability assurance is unsupported until its evidence is carried in the result"});
    if(!capability.retains_branch_labelled_joint_relation)
        return one({DiagnosticCode::unsupported,"hybrid.reachability.branch_relation",
            "Reachability adapter does not declare full branch-labelled joint-relation support"});
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid reachability was cancelled after capability admission"};
    auto result=adapter.compose_path(system,request,path,limits,cancellation);
    if(const auto* reachable=std::get_if<HybridPathReachability>(&result)) {
        if(reachable->path!=path)
            return one({DiagnosticCode::evidence_mismatch,"hybrid.reachability.path",
                "Reachability adapter returned a relation for a different path"});
        if(!same_limits(reachable->relation_limits,limits))
            return one({DiagnosticCode::evidence_mismatch,"hybrid.reachability.limits",
                "Reachability adapter returned limits different from those requested"});
        if(reachable->assurance!=capability.assurance)
            return one({DiagnosticCode::evidence_mismatch,"hybrid.reachability.assurance",
                "Reachability result assurance does not match its declared capability"});
        const auto trace_errors=hybrid_operation_trace_errors(path,limits,reachable->relation_operations,true,
            reachable->joint_relation.metadata()->set.dimension);
        if(!trace_errors.empty()) return trace_errors;
    }
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&result);
       failure) {
        if(failure->path!=path)
            return one({DiagnosticCode::evidence_mismatch,"hybrid.reachability.failure_path",
                "Reachability adapter returned a failure report for a different path"});
        if(!same_limits(failure->limits,limits))
            return one({DiagnosticCode::evidence_mismatch,"hybrid.reachability.failure_limits",
                "Reachability failure report lost the configured relation limits"});
        const auto trace_errors=hybrid_operation_trace_errors(path,limits,failure->operations,false);
        if(!trace_errors.empty()) return trace_errors;
    }
    return result;
}

HybridPathProgramResult JointHDirectTrajectoryAdapter::build_path(
    const model::HybridSystem& system, const model::HybridRequest& request,
    const model::HybridPath& path, ProblemId problem, model::HybridRelationLimits limits,
    optimization::ObjectivePolicy policy, std::stop_token cancellation) const {
    return build_joint_hybrid_path_program(system, request, path, std::move(problem), limits,
        policy, cancellation);
}

HybridDirectTrajectoryPreflightResult HybridDirectTrajectoryAdapter::preflight(
    const model::HybridSystem& system,const model::HybridRequest& request,
    std::span<const model::HybridPath> paths,model::HybridRelationLimits limits,
    optimization::ObjectivePolicy,std::stop_token cancellation) const {
    const auto result=model::preflight_hybrid_path_relations(system,request,paths,limits,cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&result)) {
        if(const auto* diagnostic=std::get_if<Diagnostic>(&failure->failure))
            return HybridDirectTrajectoryPreflightFailure{failure->path,failure->limits,
                failure->operations,*diagnostic};
        return std::get<OperationStopped>(failure->failure);
    }
    if(const auto* diagnostics=std::get_if<Diagnostics>(&result)) {
        const auto path=paths.empty()?model::HybridPath{}:paths.front();
        if(diagnostics->empty())
            return HybridDirectTrajectoryPreflightFailure{path,limits,{},Diagnostic{
                DiagnosticCode::evidence_mismatch,"hybrid.adapter.preflight_diagnostics",
                "Built-in direct-trajectory preflight returned an empty diagnostic list"}};
        return HybridDirectTrajectoryPreflightFailure{path,limits,{},diagnostics->front()};
    }
    if(const auto* stopped=std::get_if<OperationStopped>(&result)) return *stopped;
    return std::monostate{};
}

namespace {
HybridPathProgramResult dispatch_hybrid_path_program(
    const HybridDirectTrajectoryAdapter& adapter,const model::HybridSystem& system,
    const model::HybridRequest& request,const model::HybridPath& path,ProblemId problem,
    model::HybridRelationLimits limits,optimization::ObjectivePolicy policy,
    std::stop_token cancellation) {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid path program construction was cancelled before adapter dispatch"};
    auto built=adapter.build_path(system,request,path,std::move(problem),limits,policy,cancellation);
    if(const auto* program=std::get_if<HybridPathProgram>(&built)) {
        if(program->path!=path)
            return one({DiagnosticCode::evidence_mismatch,"hybrid.adapter.path",
                "Direct-trajectory adapter returned a program for a different path"});
        if(!same_limits(program->relation_limits,limits))
            return one({DiagnosticCode::evidence_mismatch,"hybrid.adapter.limits",
                "Direct-trajectory adapter returned limits different from those requested"});
        const auto trace_errors=hybrid_operation_trace_errors(path,limits,program->relation_operations,true,
            program->joint_relation.metadata()->set.dimension);
        if(!trace_errors.empty()) return trace_errors;
    }
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&built)) {
        if(failure->path!=path)
            return one({DiagnosticCode::evidence_mismatch,"hybrid.adapter.failure_path",
                "Direct-trajectory adapter returned a failure report for a different path"});
        if(!same_limits(failure->limits,limits))
            return one({DiagnosticCode::evidence_mismatch,"hybrid.adapter.failure_limits",
                "Direct-trajectory failure report lost the configured relation limits"});
        const auto trace_errors=hybrid_operation_trace_errors(path,limits,failure->operations,false);
        if(!trace_errors.empty()) return trace_errors;
    }
    return built;
}
}

HybridPathProgramResult build_hybrid_path_program(const HybridDirectTrajectoryAdapter& adapter,
    const model::HybridSystem& system, const model::HybridRequest& request,
    const model::HybridPath& path, ProblemId problem, model::HybridRelationLimits limits,
    optimization::ObjectivePolicy policy, std::stop_token cancellation) {
    if(problem.value.empty())
        return one({DiagnosticCode::invalid_input,"hybrid.program.problem","Problem identity must be nonempty"});
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid path program construction was cancelled before profile admission"};
    const auto admission=hybrid_path_admission_errors(system,request,path);
    if(!admission.empty()) return admission;
    if(const auto policy_error=hybrid_objective_policy_error(policy); policy_error)
        return one(*policy_error);
    const std::array<model::HybridPath,1> paths{path};
    const auto operation_preflight=preflight_hybrid_trajectory_operations(
        adapter,system,request,paths,limits,policy,cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&operation_preflight))
        return *failure;
    if(const auto* errors=std::get_if<Diagnostics>(&operation_preflight)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&operation_preflight)) return *stopped;
    const auto capability=adapter.capabilities();
    if(capability.assurance!=Assurance::numerical)
        return one({DiagnosticCode::unsupported,"hybrid.adapter.assurance",
            "Validated adapter assurance is unsupported until its evidence is carried in the result"});
    if(!capability.preserves_branch_labelled_joint_relation)
        return one({DiagnosticCode::unsupported,"hybrid.adapter.branch_relation",
            "Direct-trajectory adapter does not declare branch-labelled joint-relation support"});
    if(!path.modes.empty()) {
        const auto objective=std::find_if(request.terminal_objectives.begin(),request.terminal_objectives.end(),
            [&](const auto& candidate) { return candidate.mode==path.modes.back(); });
        if(objective==request.terminal_objectives.end())
            return one({DiagnosticCode::invalid_input,"hybrid.adapter.objective",
                "No terminal objective is defined for the requested path's final mode"});
        const bool supported=std::visit([&](const auto& value) {
            using T=std::decay_t<decltype(value)>;
            if constexpr(std::is_same_v<T,LinearTerminal>) return capability.linear_objectives;
            else return capability.convex_objectives;
        },objective->objective);
        if(!supported)
            return one({DiagnosticCode::unsupported,"hybrid.adapter.objective",
                "Direct-trajectory adapter does not declare support for this terminal objective"});
    }
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid path program construction was cancelled after capability admission"};
    return dispatch_hybrid_path_program(adapter,system,request,path,std::move(problem),limits,
        policy,cancellation);
}

HybridPathProgramResult build_hybrid_path_program(const model::HybridSystem& system,
    const model::HybridRequest& request, const model::HybridPath& path, ProblemId problem,
    model::HybridRelationLimits limits, optimization::ObjectivePolicy policy,
    std::stop_token cancellation) {
    const JointHDirectTrajectoryAdapter adapter;
    return build_hybrid_path_program(adapter, system, request, path, std::move(problem), limits,
        policy, cancellation);
}

namespace {
HybridPortfolioProgramResult build_hybrid_portfolio_programs_for_paths(
    const HybridDirectTrajectoryAdapter& adapter,const model::HybridSystem& system,
    const model::HybridRequest& request,ProblemId problem,std::span<const model::HybridPath> paths,
    model::HybridRelationLimits relation_limits,optimization::ObjectivePolicy policy,
    std::stop_token cancellation) {
    std::vector<HybridPathProgram> programs;
    programs.reserve(paths.size());
    for(const auto& path:paths) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,
                "Hybrid portfolio construction stopped between edge paths; no programs were published"};
        auto built=dispatch_hybrid_path_program(adapter,system,request,path,problem,
            relation_limits,policy,cancellation);
        if(const auto* errors=std::get_if<Diagnostics>(&built)) return *errors;
        if(const auto* stopped=std::get_if<OperationStopped>(&built)) return *stopped;
        if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&built)) return *failure;
        programs.push_back(std::get<HybridPathProgram>(std::move(built)));
    }
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid portfolio construction was cancelled before publication"};
    return programs;
}
}

HybridPortfolioProgramResult build_hybrid_portfolio_programs(const HybridDirectTrajectoryAdapter& adapter,
    const model::HybridSystem& system,
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
    if(paths.empty())
        return one({DiagnosticCode::invalid_claim,"hybrid.portfolio.paths",
            "No allowed hybrid path exists for the requested terminal modes"});
    const auto operation_preflight=preflight_hybrid_trajectory_operations(
        adapter,system,request,paths,relation_limits,policy,cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&operation_preflight))
        return *failure;
    if(const auto* errors=std::get_if<Diagnostics>(&operation_preflight)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&operation_preflight)) return *stopped;
    const auto trajectory_preflight=preflight_hybrid_trajectory_capabilities(
        adapter,request,paths,policy,cancellation);
    if(const auto* errors=std::get_if<Diagnostics>(&trajectory_preflight)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&trajectory_preflight)) return *stopped;
    return build_hybrid_portfolio_programs_for_paths(adapter,system,request,
        std::move(problem),paths,relation_limits,policy,cancellation);
}

HybridPortfolioProgramResult build_hybrid_portfolio_programs(const model::HybridSystem& system,
    const model::HybridRequest& request, ProblemId problem,
    model::HybridEnumerationLimits enumeration_limits, model::HybridRelationLimits relation_limits,
    optimization::ObjectivePolicy policy, std::stop_token cancellation) {
    const JointHDirectTrajectoryAdapter adapter;
    return build_hybrid_portfolio_programs(adapter, system, request, std::move(problem),
        enumeration_limits, relation_limits, policy, cancellation);
}

HybridPortfolioProgramResult build_hybrid_portfolio_programs_with_verifier(
    const HybridFamilyVerificationAdapter& verifier,const HybridDirectTrajectoryAdapter& trajectory,
    const model::HybridSystem& system,const model::HybridRequest& request,ProblemId problem,
    model::HybridEnumerationLimits enumeration_limits,model::HybridRelationLimits relation_limits,
    optimization::ObjectivePolicy policy,std::stop_token cancellation) {
    if(problem.value.empty()) return one({DiagnosticCode::invalid_input,"hybrid.program.problem",
        "Problem identity must be nonempty"});
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid verified portfolio construction was cancelled before profile admission"};
    const auto profile_errors=model::check_hybrid_profile(system,request);
    if(!profile_errors.empty()) return profile_errors;
    if(const auto policy_error=hybrid_objective_policy_error(policy); policy_error)
        return one(*policy_error);
    const auto capability=verifier.capabilities();
    if(capability.assurance!=Assurance::numerical||
       !capability.checks_original_hybrid_feasibility||
       !capability.checks_global_objective_optimality||
       !capability.checks_continuous_branch_coverage)
        return one({DiagnosticCode::unsupported,"hybrid.verification.capabilities",
            "Verifier must declare numerical feasibility, global objective, and continuous coverage checks"});
    const auto enumerated=model::enumerate_hybrid_paths(system,request.initial.mode,
        request.allowed_terminal_modes,enumeration_limits,cancellation);
    if(const auto* diagnostic=std::get_if<Diagnostic>(&enumerated)) return one(*diagnostic);
    if(const auto* stopped=std::get_if<OperationStopped>(&enumerated)) return *stopped;
    const auto& paths=std::get<std::vector<model::HybridPath>>(enumerated);
    if(paths.empty())
        return one({DiagnosticCode::invalid_claim,"hybrid.verification.paths",
            "No allowed hybrid path exists for the requested verifier plan"});
    const auto operation_preflight=preflight_hybrid_trajectory_operations(
        trajectory,system,request,paths,relation_limits,policy,cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&operation_preflight))
        return *failure;
    if(const auto* errors=std::get_if<Diagnostics>(&operation_preflight)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&operation_preflight)) return *stopped;
    const auto admission=verifier.preflight(system,request,paths,cancellation);
    if(const auto* errors=std::get_if<Diagnostics>(&admission)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&admission)) return *stopped;
    const auto trajectory_preflight=preflight_hybrid_trajectory_capabilities(
        trajectory,request,paths,policy,cancellation);
    if(const auto* errors=std::get_if<Diagnostics>(&trajectory_preflight)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&trajectory_preflight)) return *stopped;
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid verified portfolio construction was cancelled after verifier preflight"};
    return build_hybrid_portfolio_programs_for_paths(trajectory,system,request,
        std::move(problem),paths,relation_limits,policy,cancellation);
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

HybridPathOptimalFaceResult build_hybrid_path_optimal_face_candidate(
    const HybridPathProgram& branch,const ProgramResult& result,NumericalPolicy policy,
    std::stop_token cancellation) {
    if(!std::isfinite(policy.absolute_tolerance)||policy.absolute_tolerance<0||
       !std::isfinite(policy.relative_tolerance)||policy.relative_tolerance<0)
        return one({DiagnosticCode::invalid_input,"hybrid.optimal_face.policy",
            "Optimal-face tolerances must be finite and nonnegative"});
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid optimal-face construction was cancelled before validation"};
    if(result.termination!=Termination::completed||result.outcome.value!=MathematicalOutcome::optimal||!result.primal)
        return one({DiagnosticCode::invalid_claim,"hybrid.optimal_face.anchor",
            "A completed optimal solver result with a primal anchor is required"});
    auto validate=[&]<class Program>(const Program& program) {
        return optimization::check_program_result(result,program,Assurance::numerical);
    };
    const auto validation=std::visit(validate,branch.program);
    if(!validation.empty()) return validation;
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid optimal-face construction was cancelled after result validation"};
    const auto representation=branch.joint_relation.representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h) return one({DiagnosticCode::unsupported,"hybrid.optimal_face.representation",
        "Optimal-face construction requires the admitted joint H relation"});
    const auto dimension=branch.joint_relation.metadata()->set.dimension;
    if(result.primal->size()!=dimension)
        return one({DiagnosticCode::evidence_mismatch,"hybrid.optimal_face.dimension",
            "Solver anchor dimension differs from the joint branch relation"});
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid optimal-face construction was cancelled before primal evaluation"};

    auto within_policy=[&](double violation,double scale) {
        if(!std::isfinite(violation)||!std::isfinite(scale)||violation<0||scale<0) return false;
        if(violation<=policy.absolute_tolerance) return true;
        if(scale==0) return false;
        return (violation-policy.absolute_tolerance)/scale<=policy.relative_tolerance;
    };
    auto relation_satisfied=[&](numeric::MatrixView matrix,numeric::VectorView rhs,bool equality) {
        for(std::size_t i=0;i<matrix.rows();++i) {
            if(cancellation.stop_requested()) return false;
            double activity=0,scale=std::abs(rhs[i]);
            for(std::size_t j=0;j<dimension;++j) {
                if(cancellation.stop_requested()) return false;
                const double contribution=matrix(i,j)*(*result.primal)[j];
                if(!std::isfinite(contribution)) return false;
                activity+=contribution;
                scale+=std::abs(contribution);
            }
            if(!std::isfinite(activity)||!std::isfinite(scale)) return false;
            const double violation=equality?std::abs(activity-rhs[i]):std::max(0.0,activity-rhs[i]);
            if(!within_policy(violation,scale)) return false;
        }
        return true;
    };
    if(!relation_satisfied(h->inequalities,h->upper_bounds,false)||
       !relation_satisfied(h->equalities,h->equality_values,true)) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Hybrid optimal-face construction was cancelled while checking the source relation"};
        return one({DiagnosticCode::invalid_claim,"hybrid.optimal_face.source_relation",
            "Solver anchor does not satisfy the supplied joint relation within the requested numerical policy"});
    }

    std::optional<OperationStopped> evaluation_stop;
    auto check_residuals=[&](const PrimalResiduals& residuals)->Diagnostics {
        if(residuals.rows.violation>policy.absolute_tolerance+policy.relative_tolerance*residuals.rows.scale||
           residuals.variables.violation>policy.absolute_tolerance+policy.relative_tolerance*residuals.variables.scale)
            return one({DiagnosticCode::invalid_claim,"hybrid.optimal_face.feasibility",
                "Solver anchor does not satisfy the branch program within the requested numerical policy"});
        return {};
    };
    const auto evaluation_diagnostics=std::visit([&]<class Program>(const Program& program)->Diagnostics {
        if constexpr(std::is_same_v<Program,LinearProgram>) {
            auto evaluated=optimization::evaluate_primal(program,*result.primal,policy,
                Verifier{ModuleId{"hybrid-optimal-face-primal"},"1"});
            if(const auto* errors=std::get_if<Diagnostics>(&evaluated)) return *errors;
            const auto& checked=std::get<optimization::PrimalEvaluation>(evaluated);
            return check_residuals(checked.residuals);
        } else {
            auto evaluated=optimization::evaluate_primal(program,*result.primal,policy,
                Verifier{ModuleId{"hybrid-optimal-face-primal"},"1"});
            if(const auto* stopped=std::get_if<OperationStopped>(&evaluated)) {
                evaluation_stop=*stopped;
                return {};
            }
            if(const auto* errors=std::get_if<Diagnostics>(&evaluated)) return *errors;
            const auto& checked=std::get<optimization::ConvexPrimalEvaluation>(evaluated);
            return check_residuals(checked.residuals);
        }
    },branch.program);
    if(evaluation_stop) return *evaluation_stop;
    if(!evaluation_diagnostics.empty()) return evaluation_diagnostics;
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid optimal-face construction was cancelled after primal evaluation"};

    Matrix equalities{h->equalities.rows(),dimension,{}};
    Vector rhs;
    rhs.reserve(h->equality_values.size());
    for(std::size_t i=0;i<h->equality_values.size();++i) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Hybrid optimal-face construction was cancelled while copying the joint relation"};
        rhs.push_back(h->equality_values[i]);
    }
    for(std::size_t i=0;i<h->equalities.rows();++i) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Hybrid optimal-face construction was cancelled while copying the joint relation"};
        for(std::size_t j=0;j<dimension;++j) {
            if(cancellation.stop_requested())
                return OperationStopped{StopReason::cancelled,"Hybrid optimal-face construction was cancelled while copying the joint relation"};
            equalities.values.push_back(h->equalities(i,j));
        }
    }
    std::string characterization;
    auto append=[&](std::span<const double> row)->bool {
        if(cancellation.stop_requested()) return false;
        if(row.size()!=dimension) return false;
        double value=0;
        for(std::size_t j=0;j<dimension;++j) {
            if(!std::isfinite(row[j])) return false;
            value+=row[j]*(*result.primal)[j];
        }
        if(!std::isfinite(value)) return false;
        equalities.values.insert(equalities.values.end(),row.begin(),row.end());
        rhs.push_back(value);
        ++equalities.rows;
        return true;
    };
    bool rows_built=std::visit([&](const auto& objective)->bool {
        using T=std::decay_t<decltype(objective)>;
        if constexpr(std::is_same_v<T,LinearTerminal>) {
            characterization="joint feasible relation intersected with the linear objective level through the solver anchor";
            return append(objective.coefficients);
        } else if constexpr(std::is_same_v<T,QuadraticTerminal>) {
            if(objective.Q.rows!=dimension||objective.Q.cols!=dimension||objective.linear.size()!=dimension||
               (dimension!=0&&dimension>std::numeric_limits<std::size_t>::max()/dimension)||
               objective.Q.values.size()!=dimension*dimension)
                return false;
            characterization="joint feasible relation intersected with Hx=Ha and q'x=q'a for the convex quadratic objective";
            for(std::size_t i=0;i<dimension;++i) {
                Vector row(dimension);
                for(std::size_t j=0;j<dimension;++j)
                    row[j]=objective.Q.values[i*dimension+j]/2+objective.Q.values[j*dimension+i]/2;
                if(!append(row)) return false;
            }
            return append(objective.linear);
        } else {
            if(objective.map.cols!=dimension||objective.target.size()!=objective.map.rows||
               (dimension!=0&&objective.map.rows>std::numeric_limits<std::size_t>::max()/dimension)||
               objective.map.values.size()!=objective.map.rows*dimension) return false;
            characterization="joint feasible relation intersected with Lx=La for the residual-norm objective";
            for(std::size_t i=0;i<objective.map.rows;++i) {
                Vector row(dimension);
                for(std::size_t j=0;j<dimension;++j) row[j]=objective.map.values[i*dimension+j];
                if(!append(row)) return false;
            }
            return true;
        }
    },branch.lifted_objective);
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid optimal-face construction was cancelled; no candidate relation was published"};
    if(!rows_built)
        return one({DiagnosticCode::invalid_claim,"hybrid.optimal_face.equations",
            "Objective optimal-face equations could not be constructed from the admitted dimensions and finite anchor"});
    auto matrix=numeric::snapshot(equalities);
    auto values=numeric::snapshot_vector(rhs);
    if(!std::holds_alternative<numeric::MatrixView>(matrix)||!std::holds_alternative<numeric::VectorView>(values))
        return one({DiagnosticCode::invalid_claim,"hybrid.optimal_face.arithmetic",
            "Optimal-face equations contain nonfinite binary64 values"});
    const auto& metadata=*branch.joint_relation.metadata();
    auto relation=sets::make_h({SetId{metadata.id.value+":optimal-face-candidate"},dimension,
        metadata.coordinate_labels},{h->inequalities,h->upper_bounds,
        std::get<numeric::MatrixView>(matrix),std::get<numeric::VectorView>(values)});
    if(const auto* errors=std::get_if<Diagnostic>(&relation)) return one(*errors);
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid optimal-face construction was cancelled before publication"};
    return HybridPathOptimalFaceCandidate{branch.path,std::get<sets::SetData>(std::move(relation)),
        *result.primal,result,{},std::move(characterization),
        {"the solver anchor is a true global minimizer of the convex lifted objective",
         "the appended objective equations characterize every minimizer on the branch relation",
         "family completeness and global cross-branch optimality remain unverified"}};
}

HybridPortfolioOptimalFaceAnalysis assemble_hybrid_portfolio_optimal_face_candidates(
    std::span<const HybridPathProgram> programs,const HybridPortfolioExecution& execution,
    NumericalPolicy policy,std::stop_token cancellation) {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid portfolio face assembly was cancelled before objective comparison"};
    for(std::size_t i=0;i<programs.size();++i)
        for(std::size_t j=i+1;j<programs.size();++j)
            if(programs[i].path==programs[j].path)
                return one({DiagnosticCode::evidence_mismatch,"hybrid.optimal_face.path",
                    "Duplicate branch paths make execution provenance ambiguous"});
    const auto comparison=compare_hybrid_portfolio_objective_bounds(programs,execution,policy);
    if(const auto* errors=std::get_if<Diagnostics>(&comparison)) return *errors;
    if(const auto* incomplete=std::get_if<HybridPortfolioObjectiveIncomplete>(&comparison)) return *incomplete;
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid portfolio face assembly was cancelled after objective comparison"};
    auto bounds=std::get<HybridPortfolioObjectiveBounds>(comparison);
    std::vector<HybridPathOptimalFaceCandidate> candidates;
    candidates.reserve(bounds.potentially_optimal_paths.size());
    for(const auto& path:bounds.potentially_optimal_paths) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Hybrid portfolio face assembly was cancelled; no partial candidate list was returned"};
        const auto found=std::find_if(programs.begin(),programs.end(),[&](const auto& program) {
            return program.path==path;
        });
        if(found==programs.end())
            return one({DiagnosticCode::evidence_mismatch,"hybrid.optimal_face.path",
                "A potentially optimal path has no corresponding branch program"});
        const auto index=static_cast<std::size_t>(std::distance(programs.begin(),found));
        auto candidate=build_hybrid_path_optimal_face_candidate(*found,
            *execution.branches[index].result,policy,cancellation);
        if(const auto* errors=std::get_if<Diagnostics>(&candidate)) return *errors;
        if(const auto* stopped=std::get_if<OperationStopped>(&candidate)) return *stopped;
        auto face=std::get<HybridPathOptimalFaceCandidate>(std::move(candidate));
        face.providers=execution.branches[index].providers;
        candidates.push_back(std::move(face));
    }
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid portfolio face assembly was cancelled before publication"};
    return HybridPortfolioOptimalFaceCandidates{std::move(bounds),std::move(candidates)};
}

HybridFamilyVerificationPreflightResult HybridFamilyVerificationAdapter::preflight(
    const model::HybridSystem&,const model::HybridRequest&,std::span<const model::HybridPath>,
    std::stop_token cancellation) const {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid verifier admission was cancelled before dispatch"};
    return Diagnostics{{DiagnosticCode::unsupported,"hybrid.verification.preflight",
        "Verifier adapter must explicitly admit its request domain before verified portfolio construction"}};
}

HybridFamilyVerificationResult verify_hybrid_portfolio_family(
    const HybridFamilyVerificationAdapter& adapter,const model::HybridSystem& system,
    const model::HybridRequest& request,std::span<const HybridPathProgram> programs,
    std::span<const HybridPathOptimalFaceCandidate> candidates,
    model::HybridEnumerationLimits enumeration_limits,NumericalPolicy numerical_policy,
    std::stop_token cancellation) {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid family verification was cancelled before profile admission"};
    const auto profile_errors=model::check_hybrid_profile(system,request);
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid family verification was cancelled during profile admission"};
    if(!profile_errors.empty()) return profile_errors;
    if(!std::isfinite(numerical_policy.absolute_tolerance)||numerical_policy.absolute_tolerance<0||
       !std::isfinite(numerical_policy.relative_tolerance)||numerical_policy.relative_tolerance<0)
        return one({DiagnosticCode::invalid_input,"hybrid.verification.policy",
            "Hybrid verification tolerances must be finite and nonnegative"});
    const auto enumerated=model::enumerate_hybrid_paths(system,request.initial.mode,
        request.allowed_terminal_modes,enumeration_limits,cancellation);
    if(const auto* diagnostic=std::get_if<Diagnostic>(&enumerated)) return one(*diagnostic);
    if(const auto* stopped=std::get_if<OperationStopped>(&enumerated)) return *stopped;
    const auto& paths=std::get<std::vector<model::HybridPath>>(enumerated);
    if(paths.empty())
        return one({DiagnosticCode::invalid_claim,"hybrid.verification.paths",
            "No allowed hybrid path exists to verify"});
    if(programs.size()!=paths.size())
        return one({DiagnosticCode::evidence_mismatch,"hybrid.verification.programs",
            "Branch programs do not cover the complete enumerated path inventory"});
    for(std::size_t i=0;i<paths.size();++i)
        if(programs[i].path!=paths[i])
            return one({DiagnosticCode::evidence_mismatch,"hybrid.verification.program_path",
                "Branch programs must match the complete enumerated path order exactly"});
    for(std::size_t i=0;i<paths.size();++i) {
        const auto trace_errors=hybrid_operation_trace_errors(paths[i],programs[i].relation_limits,
            programs[i].relation_operations,true,programs[i].joint_relation.metadata()->set.dimension);
        if(!trace_errors.empty()) return trace_errors;
    }
    for(std::size_t i=0;i<candidates.size();++i) {
        if(std::find(paths.begin(),paths.end(),candidates[i].path)==paths.end())
            return one({DiagnosticCode::evidence_mismatch,"hybrid.verification.candidate_path",
                "A candidate family branch is outside the enumerated path inventory"});
        for(std::size_t j=i+1;j<candidates.size();++j)
            if(candidates[i].path==candidates[j].path)
                return one({DiagnosticCode::evidence_mismatch,"hybrid.verification.candidate_duplicate",
                    "Duplicate candidate paths make family coverage ambiguous"});
    }
    const auto capability=adapter.capabilities();
    if(capability.assurance!=Assurance::numerical)
        return one({DiagnosticCode::unsupported,"hybrid.verification.assurance",
            "Validated hybrid-family verification is unavailable until certificate evidence is supported"});
    if(!capability.checks_original_hybrid_feasibility||
       !capability.checks_global_objective_optimality||
       !capability.checks_continuous_branch_coverage)
        return one({DiagnosticCode::unsupported,"hybrid.verification.capabilities",
            "Verifier must declare original feasibility, global objective, and continuous coverage checks"});
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid family verification was cancelled before verifier dispatch"};
    auto result=adapter.verify(system,request,paths,programs,candidates,numerical_policy,cancellation);
    if(const auto* stopped=std::get_if<OperationStopped>(&result)) return *stopped;
    if(const auto* diagnostics=std::get_if<Diagnostics>(&result)) return *diagnostics;
    auto report=std::get<HybridFamilyVerificationReport>(std::move(result));
    if(report.verifier_id.empty()||report.verifier_version.empty()||
       report.assurance!=capability.assurance||report.numerical_policy!=numerical_policy||
       report.enumerated_paths!=paths||report.branches.size()!=paths.size())
        return one({DiagnosticCode::evidence_mismatch,"hybrid.verification.report",
            "Verifier report identity, policy, assurance, or path inventory does not match the request"});
    for(std::size_t i=0;i<paths.size();++i)
        if(report.branches[i].path!=paths[i])
            return one({DiagnosticCode::evidence_mismatch,"hybrid.verification.branch_path",
                "Verifier report must contain each enumerated path exactly once and in order"});
    for(std::size_t i=0;i<paths.size();++i) {
        // These observations come from the admitted program/candidate inputs,
        // not from the replaceable verifier, so an adapter cannot omit or
        // rewrite the operation and provider lineage in its report.
        report.branches[i].relation_limits=programs[i].relation_limits;
        report.branches[i].relation_operations=programs[i].relation_operations;
        const auto candidate=std::find_if(candidates.begin(),candidates.end(),[&](const auto& value) {
            return value.path==paths[i];
        });
        report.branches[i].candidate_providers=candidate==candidates.end()
            ?std::vector<registry::Provenance>{}:candidate->providers;
    }
    const auto adjudicated=[](HybridVerificationStatus status) {
        return status==HybridVerificationStatus::established||
            status==HybridVerificationStatus::refuted;
    };
    if(report.complete_family_coverage==HybridVerificationStatus::established&&
       std::any_of(report.branches.begin(),report.branches.end(),[](const auto& branch) {
           return branch.continuous_coverage!=HybridVerificationStatus::established;
       }))
        return one({DiagnosticCode::evidence_mismatch,"hybrid.verification.consistency",
            "Established complete coverage requires established coverage for every enumerated path"});
    if(report.complete_family_coverage==HybridVerificationStatus::established&&
       report.global_objective_optimality!=HybridVerificationStatus::established)
        return one({DiagnosticCode::evidence_mismatch,"hybrid.verification.consistency",
            "Established complete-family coverage requires established global objective optimality"});
    if(report.global_objective_optimality==HybridVerificationStatus::established&&
       std::any_of(report.branches.begin(),report.branches.end(),[&](const auto& branch) {
           return !adjudicated(branch.feasibility)||!adjudicated(branch.objective_optimality);
       }))
        return one({DiagnosticCode::evidence_mismatch,"hybrid.verification.consistency",
            "Established global optimality requires feasibility and objective adjudication for every enumerated path"});
    if(report.global_objective_optimality==HybridVerificationStatus::established&&
       std::none_of(report.branches.begin(),report.branches.end(),[](const auto& branch) {
           return branch.feasibility==HybridVerificationStatus::established&&
               branch.objective_optimality==HybridVerificationStatus::established;
       }))
        return one({DiagnosticCode::evidence_mismatch,"hybrid.verification.consistency",
            "Established global optimality requires at least one feasible branch marked optimal"});
    return report;
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
