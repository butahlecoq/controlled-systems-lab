#include <csl/synthesis/hybrid_path_program.hpp>
#include "hybrid_operation_cpu.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <optional>
#include <sstream>
#include <stdexcept>

namespace csl::synthesis {
namespace {
using Interval = std::pair<double,double>;

std::optional<Termination> interruption(const ExecutionContext& context) {
    if(context.cancellation.stop_requested()) return Termination::cancelled;
    if(context.deadline && std::chrono::steady_clock::now()>=*context.deadline)
        return Termination::resource_limit;
    return {};
}

Diagnostics unsupported(std::string field, std::string explanation) {
    return {{DiagnosticCode::unsupported,std::move(field),std::move(explanation)}};
}

const model::HybridMode* mode(const model::HybridSystem& system,const model::HybridModeId& id) {
    const auto found=std::find_if(system.modes.begin(),system.modes.end(),
        [&](const auto& candidate){return candidate.id==id;});
    return found==system.modes.end()?nullptr:&*found;
}

const model::HybridTransitionEdge* edge(const model::HybridSystem& system,const model::HybridEdgeId& id) {
    const auto found=std::find_if(system.edges.begin(),system.edges.end(),
        [&](const auto& candidate){return candidate.id==id;});
    return found==system.edges.end()?nullptr:&*found;
}

std::optional<Interval> scalar_interval(const AdmissibleSet& set,bool allow_universal) {
    if(std::holds_alternative<UniversalSet>(set))
        return allow_universal?std::optional<Interval>{{-std::numeric_limits<double>::infinity(),
            std::numeric_limits<double>::infinity()}}:std::nullopt;
    const auto* handle=std::get_if<SetHandle>(&set);
    if(!handle) return std::nullopt;
    const auto imported=sets::from_handle(*handle);
    const auto* data=std::get_if<sets::SetData>(&imported);
    if(!data || data->metadata()->set.dimension!=1) return std::nullopt;
    const auto representation=data->representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h || h->inequalities.rows()!=2 || h->equalities.rows()!=0) return std::nullopt;
    const auto a=h->inequalities(0,0),b=h->inequalities(1,0);
    const auto rhs_a=h->upper_bounds[0],rhs_b=h->upper_bounds[1];
    if(a>0.0 && b<0.0 && a==-b && std::isfinite(rhs_a) && std::isfinite(rhs_b)) {
        const Interval interval{-rhs_b/(-b),rhs_a/a};
        if(std::isfinite(interval.first)&&std::isfinite(interval.second)) return interval;
    }
    if(a<0.0 && b>0.0 && -a==b && std::isfinite(rhs_a) && std::isfinite(rhs_b)) {
        const Interval interval{-rhs_a/(-a),rhs_b/b};
        if(std::isfinite(interval.first)&&std::isfinite(interval.second)) return interval;
    }
    return std::nullopt;
}

Diagnostics profile_errors(const model::HybridSystem& system,const model::HybridRequest& request,
    const model::HybridPath& path) {
    if(system.horizon!=1 || path.modes.size()!=2 || path.edges.size()!=1 ||
       path.modes.front()!=request.initial.mode ||
       std::find(request.allowed_terminal_modes.begin(),request.allowed_terminal_modes.end(),path.modes.back())==
           request.allowed_terminal_modes.end())
        return unsupported("hybrid.projected.profile","Projected-state adapter supports exactly one transition on a request-admitted path");
    const auto base=model::check_hybrid_profile(system,request);
    if(!base.empty()) return base;
    const auto* source=mode(system,path.modes[0]);
    const auto* target=mode(system,path.modes[1]);
    const auto* transition=edge(system,path.edges[0]);
    if(!source||!target||!transition||transition->source!=source->id||transition->target!=target->id)
        return {{DiagnosticCode::invalid_input,"hybrid.projected.path","Path edge must connect the selected scalar modes"}};
    if(source->state_dimension!=1 || target->state_dimension!=1 || source->control_dimension!=1 ||
       target->control_dimension!=0 || request.initial.state.size()!=1)
        return unsupported("hybrid.projected.dimensions","Projected-state adapter requires scalar source and target states, one scalar source control, and no target control");
    const auto* flow=std::get_if<LinearStage>(&source->flow);
    if(!flow || flow->A.rows!=1 || flow->A.cols!=1 || flow->B.rows!=1 || flow->B.cols!=1 ||
       flow->E.rows!=1 || flow->E.cols!=0 || flow->offset.size()!=1)
        return unsupported("hybrid.projected.flow","Projected-state adapter requires a constant scalar affine flow stage");
    const auto control=scalar_interval(source->control_sets[0],false);
    if(!control || control->first>=control->second)
        return unsupported("hybrid.projected.control","Source control must be a bounded, non-singleton scalar H interval");
    if(!scalar_interval(source->invariants[0],true)||!scalar_interval(source->invariants[1],true)||
       !scalar_interval(target->invariants[1],true)||!scalar_interval(transition->guards[0],true))
        return unsupported("hybrid.projected.sets","Invariants and guard must be universal or scalar H intervals");
    const auto imported=sets::from_handle(transition->reset_relations[0]);
    const auto* reset=std::get_if<sets::SetData>(&imported);
    if(!reset || reset->metadata()->set.dimension!=2)
        return unsupported("hybrid.projected.reset","Reset must be a scalar H relation over [pre-state, post-state]");
    const auto representation=reset->representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h || h->inequalities.rows()!=0 || h->equalities.rows()!=1 ||
       (h->equalities(0,0)==0.0 && h->equalities(0,1)==0.0) || h->equalities(0,1)==0.0 ||
       !std::isfinite(h->equalities(0,0)) || !std::isfinite(h->equalities(0,1)) ||
       !std::isfinite(h->equality_values[0]))
        return unsupported("hybrid.projected.reset","Reset must be one finite equality with a nonzero post-state coefficient");
    return {};
}

std::size_t h_rows(const sets::SetData& data) {
    const auto rep=data.representation();
    if(const auto* h=std::get_if<sets::HRepresentation>(&rep))
        return h->inequalities.rows()+h->equalities.rows();
    return 0;
}

registry::PreparedProvider<registry::GeometryPort> make_projection_provider(std::size_t maximum_rows) {
    registry::Registry<registry::GeometryPort> providers;
    auto registration=geometry::polyhedral::make_projection_registration(
        {geometry::polyhedral::ProjectionOutput::h,maximum_rows});
    const registry::Method method{registration.identity.id,registration.identity.version};
    if(const auto failure=providers.add(std::move(registration)))
        throw std::logic_error("Built-in hybrid projection provider registration failed: "+
            (failure->diagnostics.empty()?std::string{"unknown registration error"}:
                failure->diagnostics.front().explanation));
    registry::Requirements requirements;
    requirements.output.representation={"csl.polyhedron.h"};
    requirements.output.relation=SetRelation::equivalent;
    auto prepared=registry::prepare_provider(registry::select_provider(providers,method,requirements));
    if(const auto* rejection=std::get_if<registry::Rejection>(&prepared))
        throw std::logic_error("Built-in hybrid projection provider preparation failed: "+
            (rejection->diagnostics.empty()?std::string{"unknown registration error"}:
                rejection->diagnostics.front().explanation));
    return std::get<registry::PreparedProvider<registry::GeometryPort>>(std::move(prepared));
}

std::string exact_input_identity(const model::HybridPath& path,const sets::HRepresentation& relation,
    const std::vector<std::string>& coordinate_labels) {
    std::ostringstream identity;
    identity.imbue(std::locale::classic());
    identity<<std::setprecision(std::numeric_limits<double>::max_digits10)<<std::hexfloat<<"path:";
    for(const auto& mode_id:path.modes) identity<<mode_id.value.size()<<':'<<mode_id.value<<';';
    identity<<"edges:";
    for(const auto& edge_id:path.edges) identity<<edge_id.value.size()<<':'<<edge_id.value<<';';
    identity<<"labels:";
    for(const auto& label:coordinate_labels) identity<<label.size()<<':'<<label<<';';
    identity<<"width:"<<relation.inequalities.cols()<<";A:";
    for(std::size_t row=0;row<relation.inequalities.rows();++row) {
        for(std::size_t col=0;col<relation.inequalities.cols();++col) identity<<relation.inequalities(row,col)<<',';
        identity<<"<="<<relation.upper_bounds[row]<<';';
    }
    identity<<"E:";
    for(std::size_t row=0;row<relation.equalities.rows();++row) {
        for(std::size_t col=0;col<relation.equalities.cols();++col) identity<<relation.equalities(row,col)<<',';
        identity<<'='<<relation.equality_values[row]<<';';
    }
    return identity.str();
}

class ProjectedReachabilityStage final : public HybridReachabilityStage {
    HybridPathReachability pending_;
    registry::PreparedPipeline<registry::GeometryPort> pipeline_;
    OperationRequest request_;
    registry::Provenance selected_;
    std::size_t input_rows_;
    std::size_t maximum_rows_;
public:
    ProjectedReachabilityStage(HybridPathReachability pending,
        registry::PreparedPipeline<registry::GeometryPort> pipeline,
        OperationRequest request,registry::Provenance selected,
        std::size_t input_rows,std::size_t maximum_rows)
        :pending_(std::move(pending)),pipeline_(std::move(pipeline)),
         request_(std::move(request)),selected_(std::move(selected)),
         input_rows_(input_rows),maximum_rows_(maximum_rows) {}

    HybridPathReachabilityResult execute(const ExecutionContext& context) && override {
        if(const auto stop=interruption(context))
            return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
                "Projected-state reachability stopped before workspace creation"};
        auto workers=pipeline_.create();
        auto outcome=std::get<0>(workers)->run(context);
        if(const auto* stopped=std::get_if<OperationStopped>(&outcome)) return *stopped;
        if(const auto* rejected=std::get_if<Unsupported>(&outcome)) return rejected->diagnostics;
        const auto* result=std::get_if<OperationResult>(&outcome);
        if(!result || result->relation!=SetRelation::equivalent)
            return unsupported("hybrid.projected.provider_result",
                "Projection provider did not return an equivalent set relation");
        const auto evidence_errors=check_geometry_evidence(result->evidence,request_);
        if(!evidence_errors.empty()) return evidence_errors;
        const auto projected_import=sets::from_handle(result->output);
        if(const auto* diagnostic=std::get_if<Diagnostic>(&projected_import)) return Diagnostics{*diagnostic};
        auto projected=std::get<sets::SetData>(projected_import);
        if(projected.metadata()->set.dimension!=1 ||
           !std::holds_alternative<sets::HRepresentation>(projected.representation()))
            return unsupported("hybrid.projected.provider_shape",
                "Projection provider returned a non-scalar or non-H terminal set");
        const auto output_rows=h_rows(projected);
        if(output_rows>maximum_rows_)
            return unsupported("hybrid.projected.row_limit",
                "Projected terminal H set exceeds the adapter's declared output-row limit");
        if(const auto stop=interruption(context))
            return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
                "Projected-state reachability stopped before result publication"};
        pending_.projected_state=HybridPathReachability::ProjectedStateEvidence{
            std::move(projected),selected_,result->evidence,input_rows_,output_rows,maximum_rows_};
        return std::move(pending_);
    }
};
}

ProjectedStateHybridReachabilityAdapter::ProjectedStateHybridReachabilityAdapter(
    std::size_t maximum_projection_rows)
    :projection_(make_projection_provider(maximum_projection_rows)),
     maximum_projection_rows_(maximum_projection_rows) {}

ProjectedStateHybridReachabilityAdapter::ProjectedStateHybridReachabilityAdapter(
    registry::PreparedProvider<registry::GeometryPort> projection,
    std::size_t maximum_projection_rows)
    :projection_(std::move(projection)),maximum_projection_rows_(maximum_projection_rows) {}

HybridReachabilityCapabilities ProjectedStateHybridReachabilityAdapter::capabilities() const noexcept {
    return {true,Assurance::numerical,true,projection_.provenance(),maximum_projection_rows_};
}

HybridReachabilityPreflightResult ProjectedStateHybridReachabilityAdapter::preflight(
    const model::HybridSystem& system,const model::HybridRequest& request,const model::HybridPath& path,
    model::HybridRelationLimits limits,std::stop_token cancellation) const {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Projected-state reachability preflight was cancelled"};
    const auto profile=profile_errors(system,request,path);
    if(!profile.empty()) return profile;
    if(maximum_projection_rows_==0)
        return unsupported("hybrid.projected.row_limit","Projection row limit must be positive");
    auto composed=model::preflight_hybrid_path_relations(system,request,
        std::span<const model::HybridPath>(&path,1),limits,cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&composed)) return *failure;
    if(const auto* diagnostics=std::get_if<Diagnostics>(&composed)) return *diagnostics;
    if(const auto* stopped=std::get_if<OperationStopped>(&composed)) return *stopped;
    const auto* source=mode(system,path.modes[0]);
    const auto* target=mode(system,path.modes[1]);
    const auto* transition=edge(system,path.edges[0]);
    std::size_t required_rows=5; // initial state, flow, scalar control, and deterministic reset
    for(const auto* set:{&source->invariants[0],&source->invariants[1],
                         &transition->guards[0],&target->invariants[1]}) {
        const std::size_t rows=std::holds_alternative<UniversalSet>(*set)?0:2;
        if(required_rows>std::numeric_limits<std::size_t>::max()-rows)
            return unsupported("hybrid.projected.row_limit","Projected input row count overflows size_t");
        required_rows+=rows;
    }
    if(required_rows>maximum_projection_rows_)
        return unsupported("hybrid.projected.row_limit","Projection input relation exceeds the selected provider row limit");
    if(limits.max_variables==0)
        return unsupported("hybrid.projected.provider_envelope",
            "Projection provider envelope requires a positive variable limit");
    if(required_rows>
       std::numeric_limits<std::size_t>::max()/limits.max_variables)
        return unsupported("hybrid.projected.provider_envelope",
            "Projection provider envelope matrix extent overflows size_t");
    const registry::RequestEnvelope envelope{"geometry.h_projection",required_rows,
        limits.max_variables,required_rows*limits.max_variables,"equivalent"};
    const auto declaration=projection_.declare_support(envelope);
    if(declaration.status!=registry::AdmissionStatus::supported||!declaration.envelope_is_sufficient) {
        const std::string status=declaration.status==registry::AdmissionStatus::unsupported?"unsupported":
            declaration.status==registry::AdmissionStatus::conditional?"conditional":"unknown";
        return unsupported("hybrid.projected.provider_admission",
            "Selected geometry provider returned "+status+
            " for the complete H-projection envelope before relation composition");
    }
    return std::monostate{};
}

HybridReachabilityStageResult ProjectedStateHybridReachabilityAdapter::stage_path(
    const model::HybridSystem& system,const model::HybridRequest& request,const model::HybridPath& path,
    model::HybridRelationLimits limits,const ExecutionContext& context) const {
    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
            "Projected-state reachability was cancelled before relation construction"};
    const auto admitted=preflight(system,request,path,limits,context.cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&admitted)) return *failure;
    if(const auto* diagnostics=std::get_if<Diagnostics>(&admitted)) return *diagnostics;
    if(const auto* stopped=std::get_if<OperationStopped>(&admitted)) return *stopped;

    // Coordinate order matches the one-step public relation contract:
    // [x0, u0, x_pre1, x1]. Assemble each factor here so projection evidence
    // does not depend on the model relation composer.
    std::vector<Vector> inequalities,equalities;
    Vector bounds,equality_values;
    constexpr std::size_t width=4;
    auto append=[&](Vector row,double rhs,bool equality) {
        if(interruption(context)) return false;
        const auto count=inequalities.size()+equalities.size();
        if(count>=limits.max_rows || width==0 || count+1>limits.max_matrix_elements/width) return false;
        (equality?equalities:inequalities).push_back(std::move(row));
        (equality?equality_values:bounds).push_back(rhs);
        return true;
    };
    const auto append_failure=[&](std::string field,std::string explanation)->HybridReachabilityStageResult {
        if(const auto stop=interruption(context))
            return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
                "Projected-state relation assembly was cancelled"};
        return unsupported(std::move(field),std::move(explanation));
    };
    std::vector<model::HybridRelationOperationRecord> operations;
    const auto instrumentation=detail::make_hybrid_operation_instrumentation();
    const auto record=[&](model::HybridRelationOperationKind kind,std::size_t stage,
        std::optional<model::HybridModeId> mode_id,std::optional<model::HybridEdgeId> edge_id,
        std::size_t before,std::chrono::steady_clock::time_point started,bool completed,
        model::HybridOperationThreadCpuTimer& thread_cpu_timer) {
        const auto rows=inequalities.size()+equalities.size();
        const auto cumulative_elements=rows*width;
        const auto previous_elements=before*width;
        const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now()-started).count();
        operations.push_back({kind,stage,std::move(mode_id),std::move(edge_id),
            "csl.hybrid.projected-scalar-reachability","1",width,rows-before,
            cumulative_elements-previous_elements,rows,cumulative_elements,
            elapsed>0?static_cast<std::uint64_t>(elapsed):0,completed,thread_cpu_timer.finish()});
    };
    const auto* source=mode(system,path.modes[0]);
    const auto* target=mode(system,path.modes[1]);
    const auto* transition=edge(system,path.edges[0]);
    auto before=inequalities.size()+equalities.size();
    model::HybridOperationThreadCpuTimer initial_cpu_timer{instrumentation.thread_cpu_reader};
    auto operation_started=std::chrono::steady_clock::now();
    Vector initial(width);initial[0]=1.0;
    const bool initial_added=append(std::move(initial),request.initial.state[0],true);
    record(model::HybridRelationOperationKind::initial_state,0,source->id,{},before,
        operation_started,initial_added,initial_cpu_timer);
    if(!initial_added)
        return append_failure("hybrid.projected.rows","Relation row or matrix limit exceeded");

    const auto add_interval=[&](const AdmissibleSet& set,std::size_t coordinate)->bool {
        if(std::holds_alternative<UniversalSet>(set)) return true;
        const auto interval=scalar_interval(set,false);
        if(!interval) return false;
        Vector upper(width);upper[coordinate]=1.0;
        Vector lower(width);lower[coordinate]=-1.0;
        return append(std::move(upper),interval->second,false)&&append(std::move(lower),-interval->first,false);
    };
    before=inequalities.size()+equalities.size();
    model::HybridOperationThreadCpuTimer source_invariant_cpu_timer{instrumentation.thread_cpu_reader};
    operation_started=std::chrono::steady_clock::now();
    const bool source_invariant_added=add_interval(source->invariants[0],0);
    record(model::HybridRelationOperationKind::post_state_invariant,0,source->id,{},before,
        operation_started,source_invariant_added,source_invariant_cpu_timer);
    if(!source_invariant_added) return append_failure("hybrid.projected.invariant","Unsupported source invariant or relation limit exceeded");

    const auto& flow=std::get<LinearStage>(source->flow);
    before=inequalities.size()+equalities.size();
    model::HybridOperationThreadCpuTimer flow_cpu_timer{instrumentation.thread_cpu_reader};
    operation_started=std::chrono::steady_clock::now();
    Vector flow_row(width);flow_row[2]=1.0;flow_row[0]-=flow.A.values[0];flow_row[1]-=flow.B.values[0];
    const bool flow_added=append(std::move(flow_row),flow.offset[0],true);
    record(model::HybridRelationOperationKind::mode_flow,0,source->id,{},before,
        operation_started,flow_added,flow_cpu_timer);
    if(!flow_added)
        return append_failure("hybrid.projected.rows","Relation row or matrix limit exceeded");

    before=inequalities.size()+equalities.size();
    model::HybridOperationThreadCpuTimer control_cpu_timer{instrumentation.thread_cpu_reader};
    operation_started=std::chrono::steady_clock::now();
    const bool control_added=add_interval(source->control_sets[0],1);
    record(model::HybridRelationOperationKind::continuous_control,0,source->id,{},before,
        operation_started,control_added,control_cpu_timer);
    if(!control_added) return append_failure("hybrid.projected.control","Unsupported source control interval or relation limit exceeded");

    before=inequalities.size()+equalities.size();
    model::HybridOperationThreadCpuTimer pre_invariant_cpu_timer{instrumentation.thread_cpu_reader};
    operation_started=std::chrono::steady_clock::now();
    const bool pre_invariant_added=add_interval(source->invariants[1],2);
    record(model::HybridRelationOperationKind::pre_reset_invariant,1,source->id,{},before,
        operation_started,pre_invariant_added,pre_invariant_cpu_timer);
    if(!pre_invariant_added) return append_failure("hybrid.projected.invariant","Unsupported pre-reset invariant or relation limit exceeded");

    before=inequalities.size()+equalities.size();
    model::HybridOperationThreadCpuTimer guard_cpu_timer{instrumentation.thread_cpu_reader};
    operation_started=std::chrono::steady_clock::now();
    const bool guard_added=add_interval(transition->guards[0],2);
    record(model::HybridRelationOperationKind::transition_guard,0,{},transition->id,before,
        operation_started,guard_added,guard_cpu_timer);
    if(!guard_added) return append_failure("hybrid.projected.guard","Unsupported transition guard or relation limit exceeded");

    const auto reset_data=std::get<sets::SetData>(sets::from_handle(transition->reset_relations[0]));
    const auto reset=std::get<sets::HRepresentation>(reset_data.representation());
    before=inequalities.size()+equalities.size();
    model::HybridOperationThreadCpuTimer reset_cpu_timer{instrumentation.thread_cpu_reader};
    operation_started=std::chrono::steady_clock::now();
    Vector reset_row(width);reset_row[2]=reset.equalities(0,0);reset_row[3]=reset.equalities(0,1);
    const bool reset_added=append(std::move(reset_row),reset.equality_values[0],true);
    record(model::HybridRelationOperationKind::reset_relation,0,{},transition->id,before,
        operation_started,reset_added,reset_cpu_timer);
    if(!reset_added)
        return append_failure("hybrid.projected.rows","Relation row or matrix limit exceeded");

    before=inequalities.size()+equalities.size();
    model::HybridOperationThreadCpuTimer target_invariant_cpu_timer{instrumentation.thread_cpu_reader};
    operation_started=std::chrono::steady_clock::now();
    const bool target_invariant_added=add_interval(target->invariants[1],3);
    record(model::HybridRelationOperationKind::post_state_invariant,1,target->id,{},before,
        operation_started,target_invariant_added,target_invariant_cpu_timer);
    if(!target_invariant_added) return append_failure("hybrid.projected.invariant","Unsupported target invariant or relation limit exceeded");
    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
            "Projected-state reachability stopped before relation publication"};

    Matrix a{inequalities.size(),width,{}};Matrix e{equalities.size(),width,{}};
    for(const auto& row:inequalities)a.values.insert(a.values.end(),row.begin(),row.end());
    for(const auto& row:equalities)e.values.insert(e.values.end(),row.begin(),row.end());
    auto av=numeric::snapshot(a),ev=numeric::snapshot(e);
    auto bv=numeric::snapshot_vector(bounds),fv=numeric::snapshot_vector(equality_values);
    if(!std::holds_alternative<numeric::MatrixView>(av)||!std::holds_alternative<numeric::MatrixView>(ev)||
       !std::holds_alternative<numeric::VectorView>(bv)||!std::holds_alternative<numeric::VectorView>(fv))
        return unsupported("hybrid.projected.storage","Relation data failed numeric validation");
    std::vector<std::string> labels{
        "post:0:"+std::to_string(source->id.value.size())+":"+source->id.value+":"+
            std::to_string(source->state_coordinate_labels[0].size())+":"+source->state_coordinate_labels[0],
        "control:0:"+std::to_string(source->id.value.size())+":"+source->id.value+":"+
            std::to_string(source->control_coordinate_labels[0].size())+":"+source->control_coordinate_labels[0],
        "pre:1:"+std::to_string(source->id.value.size())+":"+source->id.value+":"+
            std::to_string(source->state_coordinate_labels[0].size())+":"+source->state_coordinate_labels[0],
        "post:1:"+std::to_string(target->id.value.size())+":"+target->id.value+":"+
            std::to_string(target->state_coordinate_labels[0].size())+":"+target->state_coordinate_labels[0]};
    const sets::HRepresentation relation_data{std::get<numeric::MatrixView>(av),
        std::get<numeric::VectorView>(bv),std::get<numeric::MatrixView>(ev),
        std::get<numeric::VectorView>(fv)};
    const auto request_identity=exact_input_identity(path,relation_data,labels);
    auto relation_result=sets::make_h({SetId{"hybrid-projected:"+request_identity},width,std::move(labels)},
        relation_data);
    if(const auto* diagnostic=std::get_if<Diagnostic>(&relation_result))return Diagnostics{*diagnostic};
    auto relation=std::get<sets::SetData>(std::move(relation_result));
    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
            "Projected-state reachability stopped before provider admission"};

    const auto identity=GeometryRequestIdentity{ProblemId{"hybrid-projected-reachability"},
        RequestId{"terminal-state:"+request_identity},ReferenceId{"terminal-state:"+request_identity}};
    const auto provenance=projection_.provenance();
    const auto implementation=provenance.actual?provenance.actual->id:provenance.requested.id;
    OperationRequest projection_request{identity,implementation,
        Projection{relation.as_handle(),{3}},SetRelation::equivalent,Assurance::numerical};
    auto prepared_result=projection_.prepare(projection_request);
    if(const auto* rejected=std::get_if<registry::Rejection>(&prepared_result))
        return HybridReachabilityStageFailure{HybridReachabilityStageOperation::projection,
            rejected->diagnostics};
    auto pipeline=std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(prepared_result));
    const auto selected=pipeline.provenance()[0];
    if(const auto stop=interruption(context))
        return OperationStopped{*stop==Termination::cancelled?StopReason::cancelled:StopReason::deadline_expired,
            "Projected-state reachability stopped after concrete provider preparation"};
    const auto input_rows=inequalities.size()+equalities.size();
    HybridPathReachability pending{path,std::move(relation),limits,std::move(operations),
        Assurance::numerical,std::nullopt};
    return std::make_unique<ProjectedReachabilityStage>(std::move(pending),std::move(pipeline),
        std::move(projection_request),selected,input_rows,maximum_projection_rows_);
}

HybridPathReachabilityResult ProjectedStateHybridReachabilityAdapter::compose_path(
    const model::HybridSystem& system,const model::HybridRequest& request,const model::HybridPath& path,
    model::HybridRelationLimits limits,std::stop_token cancellation) const {
    ExecutionContext context;
    context.cancellation=cancellation;
    auto staged=stage_path(system,request,path,limits,context);
    if(auto* stage=std::get_if<std::unique_ptr<HybridReachabilityStage>>(&staged))
        return std::move(**stage).execute(context);
    if(auto* diagnostics=std::get_if<Diagnostics>(&staged)) return std::move(*diagnostics);
    if(auto* failure=std::get_if<HybridReachabilityStageFailure>(&staged))
        return std::move(failure->diagnostics);
    if(auto* stopped=std::get_if<OperationStopped>(&staged)) return *stopped;
    return std::get<model::HybridPathCompositionFailureReport>(std::move(staged));
}
}
