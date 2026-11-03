#include <csl/synthesis/hybrid_path_program.hpp>
#include <csl/synthesis/hybrid_admission.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <limits>
#include <type_traits>

namespace csl::synthesis {
namespace {
Diagnostics one(Diagnostic diagnostic) { return Diagnostics{std::move(diagnostic)}; }
std::optional<Termination> interruption(const ExecutionContext& context);
std::uint64_t elapsed_wall_nanoseconds(std::chrono::steady_clock::time_point started) {
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now()-started).count();
    return elapsed>0?static_cast<std::uint64_t>(elapsed):0;
}
class CompletedHybridReachabilityStage final : public HybridReachabilityStage {
    HybridPathReachability result_;
public:
    explicit CompletedHybridReachabilityStage(HybridPathReachability result)
        :result_(std::move(result)) {}
    HybridPathReachabilityResult execute(const ExecutionContext& context) && override {
        if(const auto stop=interruption(context))
            return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
                "Hybrid reachability stage stopped before result publication"};
        return std::move(result_);
    }
};
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
std::optional<double> hybrid_matrix_coefficient_floor(const model::HybridSystem& system,
    const model::HybridRequest& request,std::span<const model::HybridPath> paths) {
    // Hybrid flow equations and singleton substitutions add unit coefficients
    // even when all authored matrices contain larger values.
    double minimum=1.0;
    bool complete=true;
    const auto include_values=[&](std::span<const double> values) {
        for(const double value:values)
            if(value!=0) minimum=std::min(minimum,std::abs(value));
    };
    const auto include_matrix=[&](const Matrix& matrix) {
        include_values(matrix.values);
    };
    const auto include_matrix_view=[&](numeric::MatrixView matrix) {
        for(std::size_t row=0;row<matrix.rows();++row)
            for(std::size_t column=0;column<matrix.cols();++column)
                if(const double value=matrix(row,column);value!=0)
                    minimum=std::min(minimum,std::abs(value));
    };
    const auto include_handle=[&](const SetHandle& handle) {
        const auto imported=sets::from_handle(handle);
        const auto* data=std::get_if<sets::SetData>(&imported);
        if(!data) { complete=false; return; }
        const auto representation=data->representation();
        if(const auto* h=std::get_if<sets::HRepresentation>(&representation)) {
            include_matrix_view(h->inequalities);
            include_matrix_view(h->equalities);
        } else if(!std::holds_alternative<sets::SingletonRepresentation>(representation) &&
                  !std::holds_alternative<sets::UniversalRepresentation>(representation) &&
                  !std::holds_alternative<sets::EmptyRepresentation>(representation)) {
            complete=false;
        }
    };
    const auto include_set=[&](const AdmissibleSet& set) {
        std::visit([&](const auto& value) {
            using T=std::decay_t<decltype(value)>;
            if constexpr(std::is_same_v<T,SetHandle>) include_handle(value);
        },set);
    };
    for(const auto& path:paths) {
        for(std::size_t stage=0;stage<path.edges.size();++stage) {
            const auto mode=std::find_if(system.modes.begin(),system.modes.end(),[&](const auto& candidate) {
                return candidate.id==path.modes[stage];
            });
            const auto edge=std::find_if(system.edges.begin(),system.edges.end(),[&](const auto& candidate) {
                return candidate.id==path.edges[stage];
            });
            if(mode==system.modes.end()||edge==system.edges.end()) return {};
            const LinearStage* flow=nullptr;
            if(const auto* constant=std::get_if<LinearStage>(&mode->flow)) flow=constant;
            else if(const auto* varying=std::get_if<std::vector<LinearStage>>(&mode->flow)) {
                if(stage>=varying->size()) return {};
                flow=&(*varying)[stage];
            }
            if(flow==nullptr) return {};
            include_matrix(flow->A); include_matrix(flow->B); include_matrix(flow->E);
            include_set(mode->control_sets[stage]);
            include_set(mode->invariants[stage]); include_set(mode->invariants[stage+1]);
            include_set(edge->guards[stage]);
            include_handle(edge->reset_relations[stage]);
        }
        const auto terminal=std::find_if(system.modes.begin(),system.modes.end(),[&](const auto& candidate) {
            return candidate.id==path.modes.back();
        });
        if(terminal==system.modes.end()) return {};
        include_set(terminal->invariants[system.horizon]);
        const auto objective=std::find_if(request.terminal_objectives.begin(),request.terminal_objectives.end(),
            [&](const auto& candidate) { return candidate.mode==path.modes.back(); });
        if(objective==request.terminal_objectives.end()) return {};
        if(const auto* quadratic=std::get_if<QuadraticTerminal>(&objective->objective))
            include_matrix(quadratic->Q);
        else if(std::holds_alternative<ResidualNormTerminal>(objective->objective))
            complete=false;
    }
    if(!complete) return {};
    // Convex objective normalization may halve matrix coefficients. This
    // conservative reduction keeps the declared lower bound sound.
    return std::nextafter(minimum*0.5,0.0);
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
    const auto operation_plan=model::plan_hybrid_operations(paths);
    if(const auto* diagnostic=std::get_if<Diagnostic>(&operation_plan))
        return Diagnostics{*diagnostic};
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
bool planned_operation_matches(const model::HybridRelationOperationRecord& observed,
    const model::HybridPlannedOperation& planned) {
    if(const auto* mode=std::get_if<model::HybridPlannedModeOperation>(&planned)) {
        model::HybridRelationOperationKind expected{};
        switch(mode->operation) {
        case model::HybridPlannedModeOperationKind::initial_state:
            expected=model::HybridRelationOperationKind::initial_state; break;
        case model::HybridPlannedModeOperationKind::post_state_invariant:
            expected=model::HybridRelationOperationKind::post_state_invariant; break;
        case model::HybridPlannedModeOperationKind::mode_flow:
            expected=model::HybridRelationOperationKind::mode_flow; break;
        case model::HybridPlannedModeOperationKind::continuous_control:
            expected=model::HybridRelationOperationKind::continuous_control; break;
        case model::HybridPlannedModeOperationKind::pre_reset_invariant:
            expected=model::HybridRelationOperationKind::pre_reset_invariant; break;
        }
        return observed.operation==expected && observed.stage==mode->stage &&
            observed.mode==mode->mode && !observed.edge;
    }
    const auto& edge=std::get<model::HybridPlannedEdgeOperation>(planned);
    const auto expected=edge.operation==model::HybridPlannedEdgeOperationKind::transition_guard
        ?model::HybridRelationOperationKind::transition_guard
        :model::HybridRelationOperationKind::reset_relation;
    return observed.operation==expected && observed.stage==edge.stage &&
        !observed.mode && observed.edge==edge.edge;
}
Diagnostics hybrid_operation_trace_errors(const model::HybridPath& path,
    model::HybridRelationLimits limits,
    std::span<const model::HybridRelationOperationRecord> operations,bool require_nonempty,
    std::optional<std::size_t> relation_dimension = std::nullopt) {
    const std::array<model::HybridPath,1> paths{path};
    const auto planned=model::plan_hybrid_operations(paths);
    if(const auto* diagnostic=std::get_if<Diagnostic>(&planned)) return one(*diagnostic);
    const auto& expected=std::get<std::vector<model::HybridPlannedOperation>>(planned);
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
        const bool matrix_elements_decreased=operation.cumulative_matrix_elements<previous_elements;
        const bool matrix_delta_mismatch=matrix_elements_decreased||operation.matrix_elements_added!=
            operation.cumulative_matrix_elements-previous_elements;
        if(operation.implementation_id.empty() || operation.implementation_version.empty() ||
           operation.joint_variables>limits.max_variables || operation.cumulative_rows>limits.max_rows ||
           operation.cumulative_matrix_elements>limits.max_matrix_elements ||
           row_overflow || operation.cumulative_rows!=previous_rows+operation.rows_added ||
           element_overflow || operation.cumulative_matrix_elements!=operation.cumulative_rows*operation.joint_variables ||
           matrix_delta_mismatch || !operation.completed ||
           (joint_variables && operation.joint_variables!=*joint_variables) ||
           (relation_dimension && operation.joint_variables!=*relation_dimension) ||
           !planned_operation_matches(operation,expected_operation))
            return one({DiagnosticCode::evidence_mismatch,"hybrid.adapter.operations",
                "Adapter operation provenance is incomplete, out of path, or exceeds configured limits"});
        joint_variables=operation.joint_variables;
        previous_rows=operation.cumulative_rows;
        previous_elements=operation.cumulative_matrix_elements;
    }
    return {};
}

HybridPathReachabilityResult validate_hybrid_path_reachability_result(
    const HybridReachabilityAdapter& adapter,const model::HybridPath& path,
    model::HybridRelationLimits limits,HybridPathReachabilityResult result) {
    const auto capability=adapter.capabilities();
    if(capability.assurance!=Assurance::numerical)
        return one({DiagnosticCode::unsupported,"hybrid.reachability.assurance",
            "Validated reachability assurance is unsupported until its evidence is carried in the result"});
    if(!capability.retains_branch_labelled_joint_relation)
        return one({DiagnosticCode::unsupported,"hybrid.reachability.branch_relation",
            "Reachability adapter does not declare full branch-labelled joint-relation support"});
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
        if(reachable->projected_state) {
            const auto& projected=*reachable->projected_state;
            const auto projected_representation=projected.terminal_state_set.representation();
            if(projected.terminal_state_set.metadata()->set.dimension!=1 ||
               !std::holds_alternative<sets::HRepresentation>(projected_representation) ||
               projected.maximum_projection_rows==0 ||
               projected.output_rows>projected.maximum_projection_rows ||
               projected.projection_provider.port!="geometry" ||
               !projected.projection_provider.actual ||
               projected.projection_provider.actual->id.value.empty() ||
               projected.projection_evidence.scope!=GeometryClaimScope::set_relation ||
               projected.input_rows!=reachable->relation_operations.back().cumulative_rows)
                return one({DiagnosticCode::evidence_mismatch,"hybrid.reachability.projected_state",
                    "Projected terminal-set evidence has an invalid shape, provider, or row accounting"});
            const auto& terminal=std::get<sets::HRepresentation>(projected_representation);
            if(terminal.inequalities.rows()+terminal.equalities.rows()!=projected.output_rows)
                return one({DiagnosticCode::evidence_mismatch,"hybrid.reachability.projected_rows",
                    "Projected terminal-set row count does not match its retained H representation"});
        }
    }
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&result)) {
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
}

struct HybridAdmissionToken::Storage {
    model::HybridSystem system;
    model::HybridRequest request;
    HybridExecutionSelection selection;
    model::HybridEnumerationLimits enumeration_limits;
    model::HybridRelationLimits relation_limits;
    optimization::ObjectivePolicy objective_policy;
    HybridAdmissionReport report;
};

class HybridAdmissionAccess {
public:
    static HybridAdmissionToken create(model::HybridSystem system,model::HybridRequest request,
        HybridExecutionSelection selection,model::HybridEnumerationLimits enumeration_limits,
        model::HybridRelationLimits relation_limits,optimization::ObjectivePolicy objective_policy,
        HybridAdmissionReport report) {
        using Storage=HybridAdmissionToken::Storage;
        return HybridAdmissionToken{std::make_unique<const Storage>(Storage{
            std::move(system),std::move(request),std::move(selection),enumeration_limits,
            relation_limits,objective_policy,std::move(report)})};
    }
    static const HybridAdmissionToken::Storage& storage(const HybridAdmissionToken& token) {
        return *token.storage_;
    }
};

HybridAdmissionToken::HybridAdmissionToken(std::unique_ptr<const Storage> storage)
    :storage_(std::move(storage)) {}
HybridAdmissionToken::HybridAdmissionToken(HybridAdmissionToken&&) noexcept=default;
HybridAdmissionToken& HybridAdmissionToken::operator=(HybridAdmissionToken&&) noexcept=default;
HybridAdmissionToken::~HybridAdmissionToken()=default;
const HybridAdmissionReport& HybridAdmissionToken::report() const noexcept {
    return storage_->report;
}

HybridAdmissionResult admit_hybrid_request(const model::HybridSystem& system,
    const model::HybridRequest& request,const HybridExecutionSelection& selection,
    model::HybridEnumerationLimits enumeration_limits,model::HybridRelationLimits relation_limits,
    optimization::ObjectivePolicy objective_policy,const ExecutionContext& context) {
    HybridAdmissionReport report;
    if(context.resources) report.requested_resources=*context.resources;
    const auto refuse=[&](std::string field,std::string explanation) -> HybridAdmissionResult {
        report.diagnostics.push_back({DiagnosticCode::unsupported,std::move(field),std::move(explanation)});
        return HybridAdmissionRefused{std::move(report)};
    };
    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
            "Hybrid request admission stopped before profile validation"};
    if(context.resources) {
        auto resource_errors=check_resources(*context.resources);
        report.diagnostics.insert(report.diagnostics.end(),resource_errors.begin(),resource_errors.end());
    }
    if(const auto policy_error=hybrid_objective_policy_error(objective_policy))
        report.diagnostics.push_back(*policy_error);
    const auto profile_errors=model::check_hybrid_profile(system,request);
    report.diagnostics.insert(report.diagnostics.end(),profile_errors.begin(),profile_errors.end());
    if(!report.diagnostics.empty()) return HybridAdmissionRefused{std::move(report)};
    if(!selection.trajectory&&!selection.reachability)
        return refuse("hybrid.admission.selection",
            "At least one trajectory or reachability operation must be selected");
    if(selection.trajectory&&(!selection.lp||!selection.convex))
        return refuse("hybrid.admission.solver_selection",
            "Trajectory admission requires immutable LP and convex provider snapshots");
    if(selection.verifier&&!selection.trajectory)
        return refuse("hybrid.admission.verifier_selection",
            "Family verification admission requires a selected trajectory operation");

    auto enumerated=model::enumerate_hybrid_paths(system,request.initial.mode,
        request.allowed_terminal_modes,enumeration_limits,context.cancellation);
    if(const auto* stopped=std::get_if<OperationStopped>(&enumerated)) return *stopped;
    if(const auto* diagnostic=std::get_if<Diagnostic>(&enumerated))
        return refuse(diagnostic->field,diagnostic->explanation);
    report.paths=std::get<std::vector<model::HybridPath>>(std::move(enumerated));
    if(report.paths.empty())
        return refuse("hybrid.admission.paths","No permitted hybrid path exists for the requested terminal modes");
    auto planned=model::plan_hybrid_operations(report.paths);
    if(const auto* diagnostic=std::get_if<Diagnostic>(&planned))
        return refuse(diagnostic->field,diagnostic->explanation);
    for(const auto& relation:std::get<std::vector<model::HybridPlannedOperation>>(planned)) {
        if(const auto stop=interruption(context))
            return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
                "Hybrid operation ledger derivation stopped between relation obligations"};
        HybridOperationKey key{HybridOperationKind::relation,{},{}};
        std::visit([&](const auto& operation) {
            key.path_index=operation.path_index;
            key.stage=operation.stage;
        },relation);
        report.operations.push_back({key,relation,{},relation_limits.max_rows,
            relation_limits.max_variables,relation_limits.max_matrix_elements,Assurance::numerical});
    }

    const auto record_adapter=[&](HybridOperationKey key,HybridAdmissionAdapterRole role,
        registry::AdmissionStatus decision,Diagnostics diagnostics={},
        std::optional<registry::Provenance> provider={}) {
        report.offers.push_back({std::move(key),role,std::move(provider),decision,diagnostics});
    };

    bool trajectory_admitted=false;
    if(selection.trajectory) {
        const auto operations=preflight_hybrid_trajectory_operations(*selection.trajectory,system,
            request,report.paths,relation_limits,objective_policy,context.cancellation);
        if(const auto* stopped=std::get_if<OperationStopped>(&operations)) return *stopped;
        Diagnostics operation_errors;
        if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&operations)) {
            if(const auto* stopped=std::get_if<OperationStopped>(&failure->failure)) return *stopped;
            operation_errors.push_back(std::get<Diagnostic>(failure->failure));
        } else if(const auto* errors=std::get_if<Diagnostics>(&operations)) operation_errors=*errors;
        const auto capabilities=preflight_hybrid_trajectory_capabilities(*selection.trajectory,
            request,report.paths,objective_policy,context.cancellation);
        if(const auto* stopped=std::get_if<OperationStopped>(&capabilities)) return *stopped;
        if(const auto* errors=std::get_if<Diagnostics>(&capabilities))
            operation_errors.insert(operation_errors.end(),errors->begin(),errors->end());
        trajectory_admitted=operation_errors.empty();
        report.diagnostics.insert(report.diagnostics.end(),operation_errors.begin(),operation_errors.end());
        for(const auto& operation:report.operations)
            record_adapter(operation.key,HybridAdmissionAdapterRole::trajectory,
                trajectory_admitted?registry::AdmissionStatus::supported:registry::AdmissionStatus::unsupported,
                operation_errors);
    }

    if(selection.reachability) {
        for(std::size_t i=0;i<report.paths.size();++i) {
            if(const auto stop=interruption(context))
                return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
                    "Hybrid reachability admission stopped between path obligations"};
            const auto preflight=selection.reachability->preflight(system,request,report.paths[i],
                relation_limits,context.cancellation);
            if(const auto* stopped=std::get_if<OperationStopped>(&preflight)) return *stopped;
            Diagnostics errors;
            if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&preflight)) {
                if(const auto* stopped=std::get_if<OperationStopped>(&failure->failure)) return *stopped;
                errors.push_back(std::get<Diagnostic>(failure->failure));
            } else if(const auto* rejected=std::get_if<Diagnostics>(&preflight)) errors=*rejected;
            const auto capability=selection.reachability->capabilities();
            if(capability.assurance!=Assurance::numerical)
                errors.push_back({DiagnosticCode::unsupported,"hybrid.admission.reachability.assurance",
                    "Selected reachability adapter does not provide numerical assurance"});
            if(!capability.retains_branch_labelled_joint_relation)
                errors.push_back({DiagnosticCode::unsupported,"hybrid.admission.reachability.branch_relation",
                    "Selected reachability adapter does not preserve branch-labelled joint relations"});
            report.diagnostics.insert(report.diagnostics.end(),errors.begin(),errors.end());
            const HybridOperationKey key{HybridOperationKind::relation,i,{}};
            report.operations.push_back({key,{}, {},relation_limits.max_rows,
                relation_limits.max_variables,relation_limits.max_matrix_elements,capability.assurance});
            record_adapter(key,HybridAdmissionAdapterRole::reachability,
                errors.empty()?registry::AdmissionStatus::supported:registry::AdmissionStatus::unsupported,
                errors);
            if(capability.projects_terminal_state) {
                Diagnostics projection_errors=errors;
                if(!capability.projection_provider||!capability.projection_provider->actual||
                   capability.projection_provider->actual->id.value.empty())
                    projection_errors.push_back({DiagnosticCode::evidence_mismatch,
                        "hybrid.admission.projection.provider",
                        "Projected reachability did not expose the selected geometry provider provenance"});
                if(capability.maximum_projection_rows==0)
                    projection_errors.push_back({DiagnosticCode::unsupported,
                        "hybrid.admission.projection.rows",
                        "Projected reachability did not expose a positive geometry row limit"});
                if(relation_limits.max_variables==0)
                    projection_errors.push_back({DiagnosticCode::unsupported,
                        "hybrid.admission.projection.columns",
                        "Projected geometry envelope requires a positive relation variable limit"});
                std::size_t projection_elements=0;
                if(capability.maximum_projection_rows!=0&&relation_limits.max_variables!=0&&
                   capability.maximum_projection_rows>
                       std::numeric_limits<std::size_t>::max()/relation_limits.max_variables) {
                    projection_errors.push_back({DiagnosticCode::unsupported,
                        "hybrid.admission.projection.elements",
                        "Projected geometry envelope matrix extent overflows size_t"});
                } else {
                    projection_elements=capability.maximum_projection_rows*relation_limits.max_variables;
                }
                HybridOperationKey projection_key{HybridOperationKind::projection,i,{}};
                report.operations.push_back({projection_key,{}, {},capability.maximum_projection_rows,
                    relation_limits.max_variables,projection_elements,capability.assurance});
                report.diagnostics.insert(report.diagnostics.end(),projection_errors.begin(),
                    projection_errors.end());
                record_adapter(projection_key,HybridAdmissionAdapterRole::geometry,
                    projection_errors.empty()?registry::AdmissionStatus::supported:
                        registry::AdmissionStatus::unsupported,
                    std::move(projection_errors),capability.projection_provider);
            }
        }
    }

    if(selection.trajectory&&selection.lp&&selection.convex) {
        const auto providers=preflight_hybrid_program_providers(system,request,report.paths,
            relation_limits,*selection.lp,*selection.convex,context.cancellation);
        if(const auto* stopped=std::get_if<OperationStopped>(&providers)) return *stopped;
        if(const auto* errors=std::get_if<Diagnostics>(&providers))
            report.diagnostics.insert(report.diagnostics.end(),errors->begin(),errors->end());
        else {
            const auto& provider_report=std::get<HybridProviderAdmissionReport>(providers);
            if(!provider_report.admitted)
                report.diagnostics.insert(report.diagnostics.end(),provider_report.diagnostics.begin(),
                    provider_report.diagnostics.end());
            for(const auto& attempt:provider_report.attempts) {
                const auto role=attempt.envelope.operation=="hybrid.linear-optimization"
                    ?HybridAdmissionAdapterRole::lp:HybridAdmissionAdapterRole::convex;
                const auto kind=role==HybridAdmissionAdapterRole::lp
                    ?HybridOperationKind::linear_optimization:HybridOperationKind::convex_optimization;
                const HybridOperationKey key{kind,static_cast<std::size_t>(
                    std::find(report.paths.begin(),report.paths.end(),attempt.path)-report.paths.begin()),{}};
                report.operations.push_back({key,{},attempt.envelope.objective,
                    attempt.envelope.maximum_rows,attempt.envelope.maximum_columns,
                    attempt.envelope.maximum_elements,Assurance::numerical});
                record_adapter(key,role,attempt.declaration.status,attempt.declaration.diagnostics,
                    attempt.provider);
            }
        }
    }

    if(selection.verifier) {
        const auto capability=selection.verifier->capabilities();
        Diagnostics errors;
        if(capability.assurance!=Assurance::numerical||
           !capability.checks_original_hybrid_feasibility||
           !capability.checks_global_objective_optimality||
           !capability.checks_continuous_branch_coverage)
            errors.push_back({DiagnosticCode::unsupported,"hybrid.admission.verifier.capabilities",
                "Verifier must declare numerical feasibility, global objective, and continuous coverage checks"});
        if(errors.empty()) {
            HybridVerifierInvocation verifier_invocation(context);
            const auto preflight=selection.verifier->preflight(system,request,report.paths,verifier_invocation);
            if(const auto* stopped=std::get_if<OperationStopped>(&preflight)) return *stopped;
            if(const auto* rejected=std::get_if<Diagnostics>(&preflight)) errors=*rejected;
        }
        const HybridOperationKey key{HybridOperationKind::family_verification,{},{}};
        report.operations.push_back({key,{}, {},relation_limits.max_rows,relation_limits.max_variables,
            relation_limits.max_matrix_elements,capability.assurance});
        report.diagnostics.insert(report.diagnostics.end(),errors.begin(),errors.end());
        record_adapter(key,HybridAdmissionAdapterRole::verifier,
            errors.empty()?registry::AdmissionStatus::supported:registry::AdmissionStatus::unsupported,
            std::move(errors));
    }

    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
            "Hybrid request admission stopped after checking its operation ledger"};
    report.admitted=report.diagnostics.empty()&&(!selection.trajectory||trajectory_admitted);
    if(!report.admitted) return HybridAdmissionRefused{std::move(report)};
    return HybridAdmissionAccess::create(system,request,selection,enumeration_limits,
        relation_limits,objective_policy,std::move(report));
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
    return {true,Assurance::numerical,false,{},0};
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
        std::move(relation.operations),Assurance::numerical,std::nullopt};
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
    return validate_hybrid_path_reachability_result(adapter,path,limits,std::move(result));
}

HybridReachabilityStageResult HybridReachabilityAdapter::stage_path(
    const model::HybridSystem& system,const model::HybridRequest& request,
    const model::HybridPath& path,model::HybridRelationLimits limits,
    const ExecutionContext& context) const {
    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
            "Hybrid reachability preparation stopped before adapter staging"};
    if(capabilities().projects_terminal_state)
        return one({DiagnosticCode::unsupported,"hybrid.reachability.staging",
            "Projected adapters must implement staged concrete preparation for request-wide refinement"});
    auto result=compute_hybrid_path_reachability(*this,system,request,path,limits,context.cancellation);
    if(auto* reachable=std::get_if<HybridPathReachability>(&result)) {
        if(reachable->projected_state)
            return one({DiagnosticCode::evidence_mismatch,"hybrid.reachability.staging_projection",
                "A non-projecting reachability adapter returned projected evidence"});
        return std::make_unique<CompletedHybridReachabilityStage>(std::move(*reachable));
    }
    if(auto* diagnostics=std::get_if<Diagnostics>(&result))
        return HybridReachabilityStageFailure{HybridReachabilityStageOperation::relation,
            std::move(*diagnostics)};
    if(auto* stopped=std::get_if<OperationStopped>(&result)) return *stopped;
    return std::get<model::HybridPathCompositionFailureReport>(std::move(result));
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

HybridProviderAdmissionResult preflight_hybrid_program_providers(
    const model::HybridSystem& system,const model::HybridRequest& request,
    std::span<const model::HybridPath> paths,model::HybridRelationLimits limits,
    const registry::PreparedProvider<registry::LPPort>& lp,
    const registry::PreparedProvider<registry::ConvexPort>& convex,
    std::stop_token cancellation) {
    if(paths.empty())
        return one({DiagnosticCode::invalid_input,"hybrid.provider.paths",
            "Provider admission requires a complete, nonempty hybrid path inventory"});
    const auto planned_operations=model::plan_hybrid_operations(paths);
    if(const auto* error=std::get_if<Diagnostic>(&planned_operations)) return one(*error);
    const auto profile_errors=model::check_hybrid_profile(system,request);
    if(!profile_errors.empty()) return profile_errors;
    HybridProviderAdmissionReport report;
    report.paths.assign(paths.begin(),paths.end());
    report.relation_operations=std::get<std::vector<model::HybridPlannedOperation>>(planned_operations);
    report.attempts.reserve(paths.size());
    const auto coefficient_floor=hybrid_matrix_coefficient_floor(system,request,paths);
    for(const auto& path:paths) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,
                "Hybrid provider admission was cancelled between complete path obligations"};
        if(path.modes.empty())
            return one({DiagnosticCode::invalid_input,"hybrid.provider.path",
                "Provider admission received a path without a terminal mode"});
        auto lifted=model::lift_hybrid_terminal_objective(system,request,path,limits);
        if(const auto* error=std::get_if<Diagnostic>(&lifted)) return one(*error);
        const auto& objective=std::get<TerminalObjective>(lifted);
        registry::RequestEnvelope envelope;
        envelope.maximum_rows=limits.max_rows;
        envelope.maximum_elements=limits.max_matrix_elements;
        const registry::PreparedProvider<registry::LPPort>* selected_lp=nullptr;
        const registry::PreparedProvider<registry::ConvexPort>* selected_convex=nullptr;
        if(const auto* linear=std::get_if<LinearTerminal>(&objective)) {
            envelope.operation="hybrid.linear-optimization";
            envelope.objective="linear";
            envelope.maximum_columns=linear->coefficients.size();
            selected_lp=&lp;
        } else if(const auto* quadratic=std::get_if<QuadraticTerminal>(&objective)) {
            envelope.operation="hybrid.convex-optimization";
            envelope.objective="quadratic";
            envelope.maximum_columns=quadratic->linear.size();
            selected_convex=&convex;
        } else {
            const auto& residual=std::get<ResidualNormTerminal>(objective);
            envelope.operation="hybrid.convex-optimization";
            envelope.objective="residual_norm";
            if(residual.map.cols==std::numeric_limits<std::size_t>::max())
                return one({DiagnosticCode::unsupported,"hybrid.provider.envelope.columns",
                    "Residual-norm program envelope column count overflows size_t"});
            envelope.maximum_columns=residual.map.cols+1;
            selected_convex=&convex;
        }
        if(envelope.maximum_rows!=0 && envelope.maximum_columns>
           std::numeric_limits<std::size_t>::max()/envelope.maximum_rows)
            return one({DiagnosticCode::unsupported,"hybrid.provider.envelope.elements",
                "Conservative solver matrix envelope overflows size_t"});
        envelope.maximum_elements=std::max(envelope.maximum_elements,
            envelope.maximum_rows*envelope.maximum_columns);
        envelope.minimum_nonzero_matrix_coefficient_magnitude=coefficient_floor;
        if(const auto* quadratic=std::get_if<QuadraticTerminal>(&objective)) {
            if(quadratic->Q.rows!=0 && quadratic->Q.cols>
               std::numeric_limits<std::size_t>::max()/quadratic->Q.rows)
                return one({DiagnosticCode::unsupported,"hybrid.provider.envelope.objective_elements",
                    "Conservative quadratic objective matrix envelope overflows size_t"});
            envelope.maximum_elements=std::max(envelope.maximum_elements,
                quadratic->Q.rows*quadratic->Q.cols);
        }
        if(const auto* residual=std::get_if<ResidualNormTerminal>(&objective)) {
            if(residual->map.rows!=0 && residual->map.cols>
               std::numeric_limits<std::size_t>::max()/residual->map.rows)
                return one({DiagnosticCode::unsupported,"hybrid.provider.envelope.objective_elements",
                    "Conservative objective matrix envelope overflows size_t"});
            envelope.maximum_elements=std::max(envelope.maximum_elements,
                residual->map.rows*residual->map.cols);
        }
        const auto& provider=selected_lp?
            selected_lp->provenance():selected_convex->provenance();
        auto declaration=selected_lp?selected_lp->declare_support(envelope):
            selected_convex->declare_support(envelope);
        const bool admitted=declaration.status==registry::AdmissionStatus::supported&&
            declaration.envelope_is_sufficient;
        if(!admitted) {
            const auto status=[&] {
                switch(declaration.status) {
                case registry::AdmissionStatus::supported: return "conditional";
                case registry::AdmissionStatus::unsupported: return "unsupported";
                case registry::AdmissionStatus::unknown: return "unknown";
                case registry::AdmissionStatus::conditional: return "conditional";
                }
                return "unknown";
            }();
            const std::string provider_id=provider.actual?provider.actual->id.value:provider.requested.id.value;
            Diagnostic diagnostic{DiagnosticCode::unsupported,"hybrid.provider.admission",
                "Provider "+provider_id+" returned "+status+" for "+envelope.operation+
                " on "+path_program_id(path).value+
                "; no hybrid relation has been composed"};
            diagnostic.explanation+=" (envelope rows <= "+std::to_string(envelope.maximum_rows)+
                ", columns <= "+std::to_string(envelope.maximum_columns)+
                ", elements <= "+std::to_string(envelope.maximum_elements)+")";
            if(!declaration.diagnostics.empty())
                diagnostic.explanation+="; provider: "+declaration.diagnostics.front().explanation;
            report.diagnostics.push_back(std::move(diagnostic));
        }
        report.attempts.push_back({path,std::move(envelope),provider,std::move(declaration)});
    }
    report.admitted=report.diagnostics.empty();
    return report;
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

HybridPortfolioProgramResult build_hybrid_portfolio_programs(const HybridDirectTrajectoryAdapter& adapter,
    const model::HybridSystem& system,const model::HybridRequest& request,ProblemId problem,
    model::HybridEnumerationLimits enumeration_limits,model::HybridRelationLimits relation_limits,
    const registry::PreparedProvider<registry::LPPort>& lp,
    const registry::PreparedProvider<registry::ConvexPort>& convex,
    optimization::ObjectivePolicy policy,std::stop_token cancellation) {
    if(problem.value.empty())
        return one({DiagnosticCode::invalid_input,"hybrid.program.problem","Problem identity must be nonempty"});
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid portfolio construction was cancelled before request admission"};
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
    auto provider_preflight=preflight_hybrid_program_providers(
        system,request,paths,relation_limits,lp,convex,cancellation);
    if(const auto* errors=std::get_if<Diagnostics>(&provider_preflight)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&provider_preflight)) return *stopped;
    const auto& report=std::get<HybridProviderAdmissionReport>(provider_preflight);
    if(!report.admitted) return report.diagnostics;
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Hybrid portfolio construction was cancelled after complete provider admission"};
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
    optimization::ObjectivePolicy policy,const ExecutionContext& context) {
    if(problem.value.empty()) return one({DiagnosticCode::invalid_input,"hybrid.program.problem",
        "Problem identity must be nonempty"});
    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
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
        request.allowed_terminal_modes,enumeration_limits,context.cancellation);
    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
            "Hybrid verified portfolio construction stopped during path enumeration"};
    if(const auto* diagnostic=std::get_if<Diagnostic>(&enumerated)) return one(*diagnostic);
    if(const auto* stopped=std::get_if<OperationStopped>(&enumerated)) return *stopped;
    const auto& paths=std::get<std::vector<model::HybridPath>>(enumerated);
    if(paths.empty())
        return one({DiagnosticCode::invalid_claim,"hybrid.verification.paths",
            "No allowed hybrid path exists for the requested verifier plan"});
    const auto operation_preflight=preflight_hybrid_trajectory_operations(
        trajectory,system,request,paths,relation_limits,policy,context.cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&operation_preflight))
        return *failure;
    if(const auto* errors=std::get_if<Diagnostics>(&operation_preflight)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&operation_preflight)) return *stopped;
    HybridVerifierInvocation verifier_invocation(context);
    const auto admission=verifier.preflight(system,request,paths,verifier_invocation);
    if(const auto* errors=std::get_if<Diagnostics>(&admission)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&admission)) return *stopped;
    const auto trajectory_preflight=preflight_hybrid_trajectory_capabilities(
        trajectory,request,paths,policy,context.cancellation);
    if(const auto* errors=std::get_if<Diagnostics>(&trajectory_preflight)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&trajectory_preflight)) return *stopped;
    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
            "Hybrid verified portfolio construction was cancelled after verifier preflight"};
    return build_hybrid_portfolio_programs_for_paths(trajectory,system,request,
        std::move(problem),paths,relation_limits,policy,context.cancellation);
}

HybridPortfolioProgramResult build_hybrid_portfolio_programs_with_verifier(
    const HybridFamilyVerificationAdapter& verifier,const HybridDirectTrajectoryAdapter& trajectory,
    const model::HybridSystem& system,const model::HybridRequest& request,ProblemId problem,
    model::HybridEnumerationLimits enumeration_limits,model::HybridRelationLimits relation_limits,
    const registry::PreparedProvider<registry::LPPort>& lp,
    const registry::PreparedProvider<registry::ConvexPort>& convex,
    optimization::ObjectivePolicy policy,const ExecutionContext& context) {
    if(problem.value.empty()) return one({DiagnosticCode::invalid_input,"hybrid.program.problem",
        "Problem identity must be nonempty"});
    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
            "Hybrid verified portfolio construction was cancelled before request admission"};
    const auto profile_errors=model::check_hybrid_profile(system,request);
    if(!profile_errors.empty()) return profile_errors;
    if(const auto policy_error=hybrid_objective_policy_error(policy); policy_error)
        return one(*policy_error);
    const auto verifier_capability=verifier.capabilities();
    if(verifier_capability.assurance!=Assurance::numerical||
       !verifier_capability.checks_original_hybrid_feasibility||
       !verifier_capability.checks_global_objective_optimality||
       !verifier_capability.checks_continuous_branch_coverage)
        return one({DiagnosticCode::unsupported,"hybrid.verification.capabilities",
            "Verifier must declare numerical feasibility, global objective, and continuous coverage checks"});
    const auto enumerated=model::enumerate_hybrid_paths(system,request.initial.mode,
        request.allowed_terminal_modes,enumeration_limits,context.cancellation);
    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
            "Hybrid verified portfolio construction stopped during path enumeration"};
    if(const auto* diagnostic=std::get_if<Diagnostic>(&enumerated)) return one(*diagnostic);
    if(const auto* stopped=std::get_if<OperationStopped>(&enumerated)) return *stopped;
    const auto& paths=std::get<std::vector<model::HybridPath>>(enumerated);
    if(paths.empty())
        return one({DiagnosticCode::invalid_claim,"hybrid.verification.paths",
            "No allowed hybrid path exists for the requested verifier plan"});
    const auto operation_preflight=preflight_hybrid_trajectory_operations(
        trajectory,system,request,paths,relation_limits,policy,context.cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&operation_preflight))
        return *failure;
    if(const auto* errors=std::get_if<Diagnostics>(&operation_preflight)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&operation_preflight)) return *stopped;
    HybridVerifierInvocation verifier_invocation(context);
    const auto verifier_preflight=verifier.preflight(system,request,paths,verifier_invocation);
    if(const auto* errors=std::get_if<Diagnostics>(&verifier_preflight)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&verifier_preflight)) return *stopped;
    const auto trajectory_preflight=preflight_hybrid_trajectory_capabilities(
        trajectory,request,paths,policy,context.cancellation);
    if(const auto* errors=std::get_if<Diagnostics>(&trajectory_preflight)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&trajectory_preflight)) return *stopped;
    auto provider_preflight=preflight_hybrid_program_providers(
        system,request,paths,relation_limits,lp,convex,context.cancellation);
    if(const auto* errors=std::get_if<Diagnostics>(&provider_preflight)) return *errors;
    if(const auto* stopped=std::get_if<OperationStopped>(&provider_preflight)) return *stopped;
    const auto& report=std::get<HybridProviderAdmissionReport>(provider_preflight);
    if(!report.admitted) return report.diagnostics;
    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
            "Hybrid verified portfolio construction was cancelled after complete provider admission"};
    return build_hybrid_portfolio_programs_for_paths(trajectory,system,request,
        std::move(problem),paths,relation_limits,policy,context.cancellation);
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

HybridVerifierInvocation::HybridVerifierInvocation(const ExecutionContext& context)
    :cancellation_(context.cancellation),deadline_(context.deadline),numerical_(context.numerical),
     resources_(context.resources?std::optional<ResourcePolicy>{*context.resources}:std::nullopt),
     run_id_(context.run_id),timing_(context.timing),
     observer_(std::make_shared<execution::BackendThreadObservation>()),
     aggregate_observer_(context.backend_thread_observation) {}

std::optional<OperationStopped> HybridVerifierInvocation::interruption() const noexcept {
    if(cancellation_.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid verifier invocation was cancelled"};
    if(deadline_&&std::chrono::steady_clock::now()>=*deadline_)
        return OperationStopped{StopReason::deadline_expired,"Hybrid verifier invocation deadline expired"};
    return {};
}

OperationStopped HybridVerifierInvocation::stop_result(std::string diagnostics) const {
    if(auto stopped=interruption()) {
        stopped->diagnostics=std::move(diagnostics);
        return *stopped;
    }
    return {StopReason::cancelled,std::move(diagnostics)};
}

void HybridVerifierInvocation::record_backend_threads(std::size_t threads) const noexcept {
    observer_->record(threads);
    if(aggregate_observer_) aggregate_observer_->record(threads);
}

std::optional<std::size_t> HybridVerifierInvocation::observed_backend_threads() const noexcept {
    return observer_->maximum();
}

HybridFamilyVerificationPreflightResult HybridFamilyVerificationAdapter::preflight(
    const model::HybridSystem&,const model::HybridRequest&,std::span<const model::HybridPath>,
    const HybridVerifierInvocation& invocation) const {
    if(const auto stopped=invocation.interruption())
        return *stopped;
    return Diagnostics{{DiagnosticCode::unsupported,"hybrid.verification.preflight",
        "Verifier adapter must explicitly admit its request domain before verified portfolio construction"}};
}

HybridFamilyVerificationResult verify_hybrid_portfolio_family(
    const HybridFamilyVerificationAdapter& adapter,const model::HybridSystem& system,
    const model::HybridRequest& request,std::span<const HybridPathProgram> programs,
    std::span<const HybridPathOptimalFaceCandidate> candidates,
    model::HybridEnumerationLimits enumeration_limits,
    const HybridVerifierInvocation& invocation) {
    const auto numerical_policy=invocation.numerical_policy();
    if(const auto stopped=invocation.interruption()) return *stopped;
    const auto profile_errors=model::check_hybrid_profile(system,request);
    if(const auto stopped=invocation.interruption()) return *stopped;
    if(!profile_errors.empty()) return profile_errors;
    if(!std::isfinite(numerical_policy.absolute_tolerance)||numerical_policy.absolute_tolerance<0||
       !std::isfinite(numerical_policy.relative_tolerance)||numerical_policy.relative_tolerance<0)
        return one({DiagnosticCode::invalid_input,"hybrid.verification.policy",
            "Hybrid verification tolerances must be finite and nonnegative"});
    const auto enumerated=model::enumerate_hybrid_paths(system,request.initial.mode,
        request.allowed_terminal_modes,enumeration_limits,invocation.cancellation_token());
    if(const auto stopped=invocation.interruption()) return *stopped;
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
    if(const auto stopped=invocation.interruption()) return *stopped;
    auto result=adapter.verify(system,request,paths,programs,candidates,invocation);
    if(const auto stopped=invocation.interruption()) return *stopped;
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

namespace {
using HybridPreparedPipeline=std::variant<
    registry::PreparedPipeline<registry::LPPort>,
    registry::PreparedPipeline<registry::ConvexPort>>;

HybridPortfolioExecution execute_prepared_hybrid_branches(
    std::span<const HybridPathProgram> programs,
    std::span<const HybridPreparedPipeline> pipelines,
    std::span<const HybridReachabilityAttempt> reachability,
    const ExecutionContext& context) {
    HybridPortfolioExecution portfolio;
    portfolio.branches.reserve(programs.size());
    for(const auto& attempt:reachability)
        if(const auto* completed=std::get_if<HybridPathReachability>(&attempt.result))
            portfolio.reachability.push_back(*completed);
    portfolio.reachability_attempts.assign(reachability.begin(),reachability.end());
    bool complete=true;
    bool stopped=false;
    for(std::size_t i=0;i<programs.size();++i) {
        const auto& branch=programs[i];
        HybridBranchExecution execution;
        execution.path=branch.path;
        if(context.resources) execution.requested_resources=*context.resources;
        if(stopped) {
            execution.termination=context.cancellation.stop_requested()?Termination::cancelled:Termination::resource_limit;
            execution.diagnostics={{DiagnosticCode::unsupported,"hybrid.execution.not_started",
                "No workspace was created because an earlier branch stopped the coordinated request"}};
            complete=false;
            portfolio.branches.push_back(std::move(execution));
            continue;
        }
        if(const auto stop=interruption(context)) {
            execution.termination=*stop;
            execution.diagnostics={{DiagnosticCode::unsupported,"hybrid.execution.stopped",
                "Branch execution stopped before workspace creation"}};
            stopped=true;
            complete=false;
            portfolio.branches.push_back(std::move(execution));
            continue;
        }
        const auto run=[&]<class Program,class Port>(const Program& program,
            const registry::PreparedPipeline<Port>& pipeline) {
            const auto provenance=pipeline.provenance();
            execution.providers.assign(provenance.begin(),provenance.end());
            const auto provider_started=std::chrono::steady_clock::now();
            auto workspaces=pipeline.create();
            auto branch_context=context;
            auto branch_observation=std::make_shared<csl::execution::BackendThreadObservation>();
            branch_context.backend_thread_observation=branch_observation;
            auto outcome=std::get<0>(workspaces)->run(branch_context);
            execution.provider_elapsed_wall_nanoseconds=elapsed_wall_nanoseconds(provider_started);
            execution.observed_backend_threads=branch_observation->maximum();
            if(context.backend_thread_observation && execution.observed_backend_threads)
                context.backend_thread_observation->record(*execution.observed_backend_threads);
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
            run(*linear,std::get<registry::PreparedPipeline<registry::LPPort>>(pipelines[i]));
        else run(std::get<ConvexProgram>(branch.program),
            std::get<registry::PreparedPipeline<registry::ConvexPort>>(pipelines[i]));
        if(execution.termination==Termination::cancelled||execution.termination==Termination::resource_limit)
            stopped=true;
        portfolio.branches.push_back(std::move(execution));
    }
    portfolio.all_supplied_branches_completed=complete;
    return portfolio;
}
}

HybridPortfolioExecution execute_hybrid_path_programs(
    std::span<const HybridPathProgram> programs,
    const registry::PreparedProvider<registry::LPPort>& lp,
    const registry::PreparedProvider<registry::ConvexPort>& convex,
    const ExecutionContext& context) {
    using PreparedBranch=HybridPreparedPipeline;
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
        if(context.resources) execution.requested_resources=*context.resources;
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

    std::vector<HybridPreparedPipeline> ready;
    ready.reserve(prepared_branches.size());
    for(auto& branch:prepared_branches) ready.push_back(std::move(*branch));
    return execute_prepared_hybrid_branches(programs,ready,{},context);
}

struct HybridPreparedExecution::Storage {
    std::vector<HybridPathProgram> programs;
    std::vector<HybridPreparedPipeline> pipelines;
    std::vector<std::unique_ptr<HybridReachabilityStage>> reachability_stages;
    std::shared_ptr<const HybridReachabilityAdapter> reachability_adapter;
    std::shared_ptr<const HybridFamilyVerificationAdapter> verifier;
    model::HybridSystem system;
    model::HybridRequest request;
    model::HybridEnumerationLimits enumeration_limits;
    model::HybridRelationLimits relation_limits;
    optimization::ObjectivePolicy objective_policy;
    HybridAdmissionReport report;
};

class HybridPreparedAccess {
public:
    static HybridPreparedExecution create(std::vector<HybridPathProgram> programs,
        std::vector<HybridPreparedPipeline> pipelines,
        std::vector<std::unique_ptr<HybridReachabilityStage>> reachability_stages,
        std::shared_ptr<const HybridReachabilityAdapter> reachability_adapter,
        std::shared_ptr<const HybridFamilyVerificationAdapter> verifier,
        model::HybridSystem system,model::HybridRequest request,
        model::HybridEnumerationLimits enumeration_limits,
        model::HybridRelationLimits relation_limits,
        optimization::ObjectivePolicy objective_policy,
        HybridAdmissionReport report) {
        using Storage=HybridPreparedExecution::Storage;
        return HybridPreparedExecution{std::make_unique<const Storage>(Storage{
            std::move(programs),std::move(pipelines),std::move(reachability_stages),
            std::move(reachability_adapter),std::move(verifier),std::move(system),
            std::move(request),enumeration_limits,relation_limits,objective_policy,
            std::move(report)})};
    }
    static const HybridPreparedExecution::Storage& storage(const HybridPreparedExecution& prepared) {
        return *prepared.storage_;
    }
};

HybridPreparedExecution::HybridPreparedExecution(std::unique_ptr<const Storage> storage)
    :storage_(std::move(storage)) {}
HybridPreparedExecution::HybridPreparedExecution(HybridPreparedExecution&&) noexcept=default;
HybridPreparedExecution& HybridPreparedExecution::operator=(HybridPreparedExecution&&) noexcept=default;
HybridPreparedExecution::~HybridPreparedExecution()=default;
const HybridAdmissionReport& HybridPreparedExecution::report() const noexcept {
    return storage_->report;
}

HybridRefinementResult refine_hybrid_request(HybridAdmissionToken token,
    ProblemId problem,const ExecutionContext& context) {
    const auto& admission=HybridAdmissionAccess::storage(token);
    const auto refuse=[&](std::string field,std::string explanation) -> HybridRefinementResult {
        return HybridConcreteRefinementRejected{admission.report,
            {{DiagnosticCode::unsupported,std::move(field),std::move(explanation)}},{},{}};
    };
    if(!admission.report.admitted)
        return refuse("hybrid.refinement.admission","Only a fully admitted request can be refined");
    if(!admission.selection.trajectory&&!admission.selection.reachability)
        return refuse("hybrid.refinement.selection","Refinement requires a selected trajectory or reachability operation");
    if(admission.selection.trajectory&&(!admission.selection.lp||!admission.selection.convex))
        return refuse("hybrid.refinement.trajectory","Trajectory refinement requires LP and convex provider snapshots");
    std::vector<HybridPathProgram> programs;
    if(admission.selection.trajectory) {
        if(problem.value.empty())
            return refuse("hybrid.refinement.problem","Trajectory refinement requires a nonempty problem identity");
        programs.reserve(admission.report.paths.size());
        for(const auto& path:admission.report.paths) {
            if(const auto stop=interruption(context))
                return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
                    "Hybrid refinement stopped between path programs; no workspace was created"};
            auto built=build_hybrid_path_program(*admission.selection.trajectory,admission.system,
                admission.request,path,problem,admission.relation_limits,admission.objective_policy,
                context.cancellation);
            if(const auto* stopped=std::get_if<OperationStopped>(&built)) return *stopped;
            if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&built)) {
                if(const auto* stopped=std::get_if<OperationStopped>(&failure->failure)) return *stopped;
                return HybridConcreteRefinementRejected{admission.report,
                    {std::get<Diagnostic>(failure->failure)},{},{}};
            }
            if(const auto* errors=std::get_if<Diagnostics>(&built))
                return HybridConcreteRefinementRejected{admission.report,*errors,{},{}};
            programs.push_back(std::get<HybridPathProgram>(std::move(built)));
        }
    }

    std::vector<std::unique_ptr<HybridReachabilityStage>> reachability_stages;
    if(admission.selection.reachability) {
        reachability_stages.reserve(admission.report.paths.size());
        for(std::size_t path_index=0;path_index<admission.report.paths.size();++path_index) {
            const auto& path=admission.report.paths[path_index];
            if(const auto stop=interruption(context))
                return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
                    "Hybrid reachability refinement stopped between path stages"};
            auto staged=admission.selection.reachability->stage_path(admission.system,
                admission.request,path,admission.relation_limits,context);
            const auto operation_key=[&](HybridReachabilityStageOperation operation) {
                return HybridOperationKey{
                    operation==HybridReachabilityStageOperation::projection?
                        HybridOperationKind::projection:HybridOperationKind::relation,
                    path_index,{}};
            };
            if(auto* stage=std::get_if<std::unique_ptr<HybridReachabilityStage>>(&staged)) {
                if(!*stage) return HybridConcreteRefinementRejected{admission.report,
                    {{DiagnosticCode::evidence_mismatch,"hybrid.refinement.reachability_stage",
                        "Reachability adapter returned an empty prepared stage"}},path_index,{}};
                reachability_stages.push_back(std::move(*stage));
            } else if(auto* stopped=std::get_if<OperationStopped>(&staged)) {
                return *stopped;
            } else if(auto* stage_failure=std::get_if<HybridReachabilityStageFailure>(&staged)) {
                return HybridConcreteRefinementRejected{admission.report,
                    std::move(stage_failure->diagnostics),path_index,
                    operation_key(stage_failure->operation)};
            } else if(auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&staged)) {
                auto validated=validate_hybrid_path_reachability_result(
                    *admission.selection.reachability,path,admission.relation_limits,*failure);
                if(auto* operation_stopped=std::get_if<OperationStopped>(&validated))
                    return *operation_stopped;
                if(auto* errors=std::get_if<Diagnostics>(&validated))
                    return HybridConcreteRefinementRejected{admission.report,*errors,path_index,
                        operation_key(HybridReachabilityStageOperation::relation)};
                return HybridConcreteRefinementRejected{admission.report,
                    {std::get<Diagnostic>(std::get<model::HybridPathCompositionFailureReport>(validated).failure)},
                    path_index,operation_key(HybridReachabilityStageOperation::relation)};
            } else {
                return HybridConcreteRefinementRejected{admission.report,
                    std::move(std::get<Diagnostics>(staged)),path_index,{}};
            }
        }
    }

    std::vector<HybridPreparedPipeline> pipelines;
    pipelines.reserve(programs.size());
    for(auto& program_result:programs) {
        if(const auto stop=interruption(context))
            return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
                "Concrete hybrid provider preparation stopped before workspace creation"};
        std::optional<HybridPreparedPipeline> pipeline;
        if(const auto* linear=std::get_if<LinearProgram>(&program_result.program)) {
            auto prepared=admission.selection.lp->prepare(*linear);
            if(const auto* rejected=std::get_if<registry::Rejection>(&prepared))
                return HybridConcreteRefinementRejected{admission.report,rejected->diagnostics,{},{}};
            pipeline.emplace(std::get<registry::PreparedPipeline<registry::LPPort>>(std::move(prepared)));
        } else {
            auto prepared=admission.selection.convex->prepare(std::get<ConvexProgram>(program_result.program));
            if(const auto* rejected=std::get_if<registry::Rejection>(&prepared))
                return HybridConcreteRefinementRejected{admission.report,rejected->diagnostics,{},{}};
            pipeline.emplace(std::get<registry::PreparedPipeline<registry::ConvexPort>>(std::move(prepared)));
        }
        pipelines.push_back(std::move(*pipeline));
    }
    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
            "Hybrid refinement stopped before publishing prepared providers; no workspace was created"};
    return HybridPreparedAccess::create(std::move(programs),std::move(pipelines),
        std::move(reachability_stages),admission.selection.reachability,
        admission.selection.verifier,admission.system,admission.request,
        admission.enumeration_limits,admission.relation_limits,admission.objective_policy,
        admission.report);
}

HybridPortfolioExecution execute_hybrid_request(HybridPreparedExecution prepared,
    const ExecutionContext& context) {
    const auto& storage=HybridPreparedAccess::storage(prepared);
    std::vector<HybridReachabilityAttempt> reachability_attempts;
    reachability_attempts.reserve(storage.reachability_stages.size());
    for(std::size_t index=0;index<storage.reachability_stages.size();++index) {
        const auto& path=storage.report.paths[index];
        HybridReachabilityAttempt attempt{path,OperationStopped{
            StopReason::cancelled,"Hybrid reachability stage was not started"},{},std::nullopt};
        if(context.resources) attempt.requested_resources=*context.resources;
        if(const auto stop=interruption(context)) {
            attempt.result=OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
                "Hybrid reachability stage stopped before workspace creation"};
            reachability_attempts.push_back(std::move(attempt));
            continue;
        }
        auto path_context=context;
        auto observation=std::make_shared<csl::execution::BackendThreadObservation>();
        path_context.backend_thread_observation=observation;
        const auto reachability_started=std::chrono::steady_clock::now();
        auto result=std::move(*storage.reachability_stages[index]).execute(path_context);
        attempt.elapsed_wall_nanoseconds=elapsed_wall_nanoseconds(reachability_started);
        attempt.observed_backend_threads=observation->maximum();
        if(context.backend_thread_observation&&attempt.observed_backend_threads)
            context.backend_thread_observation->record(*attempt.observed_backend_threads);
        if(storage.reachability_adapter)
            result=validate_hybrid_path_reachability_result(*storage.reachability_adapter,path,
                storage.relation_limits,std::move(result));
        attempt.result=std::move(result);
        reachability_attempts.push_back(std::move(attempt));
    }
    auto portfolio=execute_prepared_hybrid_branches(storage.programs,storage.pipelines,
        reachability_attempts,context);
    if(storage.verifier) {
        HybridPortfolioVerificationAttempt verification{
            assemble_hybrid_portfolio_optimal_face_candidates(storage.programs,portfolio,
                storage.objective_policy.numerical,context.cancellation),{}, {}};
        verification.resources.requested=context.resources
            ?std::optional<ResourcePolicy>{*context.resources}:std::nullopt;
        verification.resources.disposition=verification.resources.requested
            ?HybridVerifierResourceDisposition::not_invoked
            :HybridVerifierResourceDisposition::not_requested;
        if(auto* candidates=std::get_if<HybridPortfolioOptimalFaceCandidates>(
               &verification.candidates)) {
            if(const auto stop=interruption(context)) {
                verification.verification=OperationStopped{
                    *stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
                    "Hybrid family verification stopped before verifier execution"};
            } else {
                HybridVerifierInvocation invocation(context);
                const auto verifier_started=std::chrono::steady_clock::now();
                auto result=verify_hybrid_portfolio_family(*storage.verifier,storage.system,
                    storage.request,storage.programs,candidates->branches,storage.enumeration_limits,
                    invocation);
                verification.resources.elapsed_wall_nanoseconds=elapsed_wall_nanoseconds(verifier_started);
                if(const auto post_verification_stop=interruption(context))
                    result=OperationStopped{*post_verification_stop==Termination::cancelled?StopReason::cancelled:
                        StopReason::deadline_expired,
                        "Hybrid family verification stopped before result publication"};
                verification.verification=std::move(result);
                verification.resources.observed_backend_threads=invocation.observed_backend_threads();
                if(verification.resources.requested)
                    verification.resources.disposition=HybridVerifierResourceDisposition::requested_but_unenforced;
                else verification.resources.disposition=HybridVerifierResourceDisposition::not_requested;
            }
        }
        portfolio.family_verification=std::move(verification);
    }
    return portfolio;
}

} // namespace csl::synthesis
