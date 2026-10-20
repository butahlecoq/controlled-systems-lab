#include <csl/synthesis/hybrid_path_program.hpp>

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <numeric>
#include <optional>
#include <sstream>
#include <stdexcept>

namespace csl::synthesis {
namespace {
using Interval = std::pair<double,double>;

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

std::optional<sets::SetData> make_projection_admission_probe(
    std::size_t dimension,std::size_t row_count) {
    if(dimension!=0 && row_count>std::numeric_limits<std::size_t>::max()/dimension)
        return std::nullopt;
    Matrix inequalities{row_count,dimension,
        std::vector<double>(row_count*dimension,0.0)};
    Matrix equalities{0,dimension,{}};
    const auto a=numeric::snapshot(inequalities);
    const auto b=numeric::snapshot_vector(Vector(row_count,0.0));
    const auto e=numeric::snapshot(equalities);
    const auto f=numeric::snapshot_vector({});
    if(!std::holds_alternative<numeric::MatrixView>(a) ||
       !std::holds_alternative<numeric::VectorView>(b) ||
       !std::holds_alternative<numeric::MatrixView>(e) ||
       !std::holds_alternative<numeric::VectorView>(f))
        return std::nullopt;
    auto relation=sets::make_h({SetId{"hybrid-projection-admission-probe"},dimension,{}},
        {std::get<numeric::MatrixView>(a),std::get<numeric::VectorView>(b),
         std::get<numeric::MatrixView>(e),std::get<numeric::VectorView>(f)});
    if(!std::holds_alternative<sets::SetData>(relation)) return std::nullopt;
    return std::get<sets::SetData>(std::move(relation));
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

std::string encoded_path_identity(const model::HybridPath& path) {
    std::string identity;
    for(const auto& id:path.modes)
        identity+=std::to_string(id.value.size())+":"+id.value+";";
    identity+="/";
    for(const auto& id:path.edges)
        identity+=std::to_string(id.value.size())+":"+id.value+";";
    return identity;
}
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
    return {true,Assurance::numerical};
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
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Projected-state reachability preflight was cancelled before provider admission"};
    auto probe=make_projection_admission_probe(4,required_rows);
    if(!probe)
        return unsupported("hybrid.projected.preflight",
            "Could not create projection provider admission probe");
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Projected-state reachability preflight was cancelled after probe construction"};
    const auto selected=projection_.provenance();
    const auto implementation=selected.actual?selected.actual->id:selected.requested.id;
    const auto path_identity=encoded_path_identity(path);
    const GeometryRequestIdentity identity{
        ProblemId{"hybrid-projected-reachability"},
        RequestId{"preflight:"+path_identity+":"+std::to_string(required_rows)},
        ReferenceId{"preflight:"+path_identity+":"+std::to_string(required_rows)}};
    OperationRequest projection_request{identity,implementation,
        Projection{probe->as_handle(),{3}},SetRelation::equivalent,Assurance::numerical};
    const auto provider_admission=projection_.prepare(projection_request);
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Projected-state reachability preflight was cancelled during provider admission"};
    if(const auto* rejection=std::get_if<registry::Rejection>(&provider_admission))
        return rejection->diagnostics;
    return std::monostate{};
}

HybridPathReachabilityResult ProjectedStateHybridReachabilityAdapter::compose_path(
    const model::HybridSystem& system,const model::HybridRequest& request,const model::HybridPath& path,
    model::HybridRelationLimits limits,std::stop_token cancellation) const {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Projected-state reachability was cancelled before relation construction"};
    const auto admitted=preflight(system,request,path,limits,cancellation);
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
        if(cancellation.stop_requested()) return false;
        const auto count=inequalities.size()+equalities.size();
        if(count>=limits.max_rows || width==0 || count+1>limits.max_matrix_elements/width) return false;
        (equality?equalities:inequalities).push_back(std::move(row));
        (equality?equality_values:bounds).push_back(rhs);
        return true;
    };
    const auto append_failure=[&](std::string field,std::string explanation)->HybridPathReachabilityResult {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Projected-state relation assembly was cancelled"};
        return unsupported(std::move(field),std::move(explanation));
    };
    std::vector<model::HybridRelationOperationRecord> operations;
    const auto record=[&](model::HybridRelationOperationKind kind,std::size_t stage,
        std::optional<model::HybridModeId> mode_id,std::optional<model::HybridEdgeId> edge_id,
        std::size_t before) {
        const auto rows=inequalities.size()+equalities.size();
        operations.push_back({kind,stage,std::move(mode_id),std::move(edge_id),
            "csl.hybrid.projected-scalar-reachability","1",width,rows-before,rows,rows*width});
    };
    const auto* source=mode(system,path.modes[0]);
    const auto* target=mode(system,path.modes[1]);
    const auto* transition=edge(system,path.edges[0]);
    auto before=inequalities.size()+equalities.size();
    Vector initial(width);initial[0]=1.0;
    if(!append(std::move(initial),request.initial.state[0],true))
        return append_failure("hybrid.projected.rows","Relation row or matrix limit exceeded");
    record(model::HybridRelationOperationKind::initial_state,0,source->id,{},before);

    const auto add_interval=[&](const AdmissibleSet& set,std::size_t coordinate)->bool {
        if(std::holds_alternative<UniversalSet>(set)) return true;
        const auto interval=scalar_interval(set,false);
        if(!interval) return false;
        Vector upper(width);upper[coordinate]=1.0;
        Vector lower(width);lower[coordinate]=-1.0;
        return append(std::move(upper),interval->second,false)&&append(std::move(lower),-interval->first,false);
    };
    before=inequalities.size()+equalities.size();
    if(!add_interval(source->invariants[0],0)) return append_failure("hybrid.projected.invariant","Unsupported source invariant or relation limit exceeded");
    record(model::HybridRelationOperationKind::post_state_invariant,0,source->id,{},before);

    const auto& flow=std::get<LinearStage>(source->flow);
    before=inequalities.size()+equalities.size();
    Vector flow_row(width);flow_row[2]=1.0;flow_row[0]-=flow.A.values[0];flow_row[1]-=flow.B.values[0];
    if(!append(std::move(flow_row),flow.offset[0],true))
        return append_failure("hybrid.projected.rows","Relation row or matrix limit exceeded");
    record(model::HybridRelationOperationKind::mode_flow,0,source->id,{},before);

    before=inequalities.size()+equalities.size();
    if(!add_interval(source->control_sets[0],1)) return append_failure("hybrid.projected.control","Unsupported source control interval or relation limit exceeded");
    record(model::HybridRelationOperationKind::continuous_control,0,source->id,{},before);

    before=inequalities.size()+equalities.size();
    if(!add_interval(source->invariants[1],2)) return append_failure("hybrid.projected.invariant","Unsupported pre-reset invariant or relation limit exceeded");
    record(model::HybridRelationOperationKind::pre_reset_invariant,1,source->id,{},before);

    before=inequalities.size()+equalities.size();
    if(!add_interval(transition->guards[0],2)) return append_failure("hybrid.projected.guard","Unsupported transition guard or relation limit exceeded");
    record(model::HybridRelationOperationKind::transition_guard,0,{},transition->id,before);

    const auto reset_data=std::get<sets::SetData>(sets::from_handle(transition->reset_relations[0]));
    const auto reset=std::get<sets::HRepresentation>(reset_data.representation());
    before=inequalities.size()+equalities.size();
    Vector reset_row(width);reset_row[2]=reset.equalities(0,0);reset_row[3]=reset.equalities(0,1);
    if(!append(std::move(reset_row),reset.equality_values[0],true))
        return append_failure("hybrid.projected.rows","Relation row or matrix limit exceeded");
    record(model::HybridRelationOperationKind::reset_relation,0,{},transition->id,before);

    before=inequalities.size()+equalities.size();
    if(!add_interval(target->invariants[1],3)) return append_failure("hybrid.projected.invariant","Unsupported target invariant or relation limit exceeded");
    record(model::HybridRelationOperationKind::post_state_invariant,1,target->id,{},before);
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Projected-state reachability stopped before relation publication"};

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
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Projected-state reachability stopped before provider admission"};

    const auto identity=GeometryRequestIdentity{ProblemId{"hybrid-projected-reachability"},
        RequestId{"terminal-state:"+request_identity},ReferenceId{"terminal-state:"+request_identity}};
    const auto provenance=projection_.provenance();
    const auto implementation=provenance.actual?provenance.actual->id:provenance.requested.id;
    OperationRequest projection_request{identity,implementation,
        Projection{relation.as_handle(),{3}},SetRelation::equivalent,Assurance::numerical};
    auto prepared_result=projection_.prepare(projection_request);
    if(const auto* rejected=std::get_if<registry::Rejection>(&prepared_result))
        return rejected->diagnostics;
    const auto pipeline=std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(prepared_result));
    const auto selected=pipeline.provenance()[0];
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Projected-state reachability stopped before projection workspace creation"};
    auto workers=pipeline.create();
    ExecutionContext context;context.cancellation=cancellation;
    auto outcome=std::get<0>(workers)->run(context);
    if(const auto* stopped=std::get_if<OperationStopped>(&outcome))return *stopped;
    if(const auto* rejected=std::get_if<Unsupported>(&outcome))return rejected->diagnostics;
    const auto* result=std::get_if<OperationResult>(&outcome);
    if(!result || result->relation!=SetRelation::equivalent)
        return unsupported("hybrid.projected.provider_result","Projection provider did not return an equivalent set relation");
    const auto projected_import=sets::from_handle(result->output);
    if(const auto* diagnostic=std::get_if<Diagnostic>(&projected_import))return Diagnostics{*diagnostic};
    auto projected=std::get<sets::SetData>(projected_import);
    if(projected.metadata()->set.dimension!=1 || !std::holds_alternative<sets::HRepresentation>(projected.representation()))
        return unsupported("hybrid.projected.provider_shape","Projection provider returned a non-scalar or non-H terminal set");
    const auto output_rows=h_rows(projected);
    if(output_rows>maximum_projection_rows_)
        return unsupported("hybrid.projected.row_limit","Projected terminal H set exceeds the adapter's declared output-row limit");
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Projected-state reachability stopped before result publication"};
    const auto input_rows=inequalities.size()+equalities.size();
    return HybridPathReachability{path,std::move(relation),limits,std::move(operations),Assurance::numerical,
        HybridPathReachability::ProjectedStateEvidence{std::move(projected),selected,input_rows,
            output_rows,maximum_projection_rows_}};
}

GeneralProjectedStateHybridReachabilityAdapter::GeneralProjectedStateHybridReachabilityAdapter(
    std::size_t maximum_projection_rows)
    :projection_(make_projection_provider(maximum_projection_rows)),
     maximum_projection_rows_(maximum_projection_rows) {}

GeneralProjectedStateHybridReachabilityAdapter::GeneralProjectedStateHybridReachabilityAdapter(
    registry::PreparedProvider<registry::GeometryPort> projection,
    std::size_t maximum_projection_rows)
    :projection_(std::move(projection)),maximum_projection_rows_(maximum_projection_rows) {}

HybridReachabilityCapabilities GeneralProjectedStateHybridReachabilityAdapter::capabilities() const noexcept {
    return {true,Assurance::numerical};
}

HybridReachabilityPreflightResult GeneralProjectedStateHybridReachabilityAdapter::preflight(
    const model::HybridSystem& system,const model::HybridRequest& request,const model::HybridPath& path,
    model::HybridRelationLimits limits,std::stop_token cancellation) const {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"General projected reachability preflight was cancelled"};
    if(maximum_projection_rows_==0)
        return Diagnostics{{DiagnosticCode::invalid_input,"hybrid.projected.row_limit",
            "Projection row limit must be positive"}};

    const auto composed=model::preflight_hybrid_path_relations(system,request,
        std::span<const model::HybridPath>(&path,1),limits,cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&composed)) return *failure;
    if(const auto* diagnostics=std::get_if<Diagnostics>(&composed)) return *diagnostics;
    if(const auto* stopped=std::get_if<OperationStopped>(&composed)) return *stopped;

    // Count the exact H rows the joint composer will submit to projection.
    // This is a preflight-only inventory; no relation or provider workspace is
    // created until the configured projection budget admits the complete path.
    const auto rows_in=[&](const AdmissibleSet& set)->std::optional<std::size_t> {
        if(std::holds_alternative<UniversalSet>(set)) return 0;
        if(std::holds_alternative<EmptySet>(set)) return 1;
        if(const auto* point=std::get_if<Singleton>(&set)) return point->point.size();
        const auto imported=sets::from_handle(std::get<SetHandle>(set));
        const auto* data=std::get_if<sets::SetData>(&imported);
        if(!data) return std::nullopt;
        const auto representation=data->representation();
        if(const auto* h=std::get_if<sets::HRepresentation>(&representation))
            return h->inequalities.rows()+h->equalities.rows();
        if(std::holds_alternative<sets::EmptyRepresentation>(representation)) return 1;
        if(std::holds_alternative<sets::UniversalRepresentation>(representation)) return 0;
        if(const auto* point=std::get_if<sets::SingletonRepresentation>(&representation))
            return point->point.size();
        return std::nullopt;
    };
    const auto add=[&](std::size_t& total,std::size_t amount) {
        if(total>std::numeric_limits<std::size_t>::max()-amount) return false;
        total+=amount;
        return total<=maximum_projection_rows_;
    };
    std::size_t required=0;
    if(!add(required,request.initial.state.size()))
        return unsupported("hybrid.projected.row_limit","Projected relation exceeds the selected provider row limit");
    for(std::size_t stage=0;stage<system.horizon;++stage) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"General projected reachability preflight was cancelled"};
        const auto* source=mode(system,path.modes[stage]);
        const auto* transition=edge(system,path.edges[stage]);
        if(!source||!transition)
            return unsupported("hybrid.projected.path","Path references an unknown mode or transition");
        const auto add_set=[&](const AdmissibleSet& set) {
            const auto rows=rows_in(set);
            return rows&&add(required,*rows);
        };
        const auto reset=sets::from_handle(transition->reset_relations[stage]);
        const auto* reset_data=std::get_if<sets::SetData>(&reset);
        if(!reset_data)
            return unsupported("hybrid.projected.preflight","Could not inspect the complete projected relation inventory");
        const auto reset_representation=reset_data->representation();
        std::optional<std::size_t> reset_rows;
        if(const auto* h=std::get_if<sets::HRepresentation>(&reset_representation))
            reset_rows=h->inequalities.rows()+h->equalities.rows();
        else if(std::holds_alternative<sets::EmptyRepresentation>(reset_representation)) reset_rows=1;
        else if(std::holds_alternative<sets::UniversalRepresentation>(reset_representation)) reset_rows=0;
        else if(const auto* point=std::get_if<sets::SingletonRepresentation>(&reset_representation))
            reset_rows=point->point.size();
        if(!add_set(source->invariants[stage]) || !add(required,source->state_dimension) ||
           !add_set(source->control_sets[stage]) || !add_set(source->invariants[stage+1]) ||
           !add_set(transition->guards[stage]) || !reset_rows || !add(required,*reset_rows))
            return unsupported("hybrid.projected.row_limit","Projected relation exceeds the selected provider row limit");
    }
    const auto* terminal=mode(system,path.modes.back());
    if(!terminal) return unsupported("hybrid.projected.path","Terminal mode is absent from the admitted system");
    const auto terminal_rows=rows_in(terminal->invariants[system.horizon]);
    if(!terminal_rows || !add(required,*terminal_rows))
        return unsupported("hybrid.projected.row_limit","Projected relation exceeds the selected provider row limit");

    // Compose the exact relation and ask the selected provider to admit the
    // operation it will execute. Preparation creates no workspace; synthetic
    // probes cannot establish support for the relation's coefficients,
    // equality partition, labels, metadata, or coordinate selection.
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "General projected reachability preflight was cancelled before relation composition"};
    auto relation_composition=model::compose_hybrid_path_relation_with_report(
        system,request,path,limits,cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&relation_composition))
        return *failure;
    auto composed_relation=std::get<model::HybridComposedPathRelation>(std::move(relation_composition));
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "General projected reachability preflight was cancelled after relation composition"};
    const auto representation=composed_relation.relation.representation();
    const auto* relation=std::get_if<sets::HRepresentation>(&representation);
    if(!relation)
        return unsupported("hybrid.projected.relation","Joint composer did not return an H relation");
    if(terminal->state_dimension>composed_relation.relation.metadata()->set.dimension)
        return unsupported("hybrid.projected.path","Terminal state coordinates are missing from the joint relation");
    const auto width=composed_relation.relation.metadata()->set.dimension;
    std::vector<std::size_t> coordinates(terminal->state_dimension);
    for(std::size_t i=0;i<coordinates.size();++i)
        coordinates[i]=width-terminal->state_dimension+i;
    const auto request_identity=exact_input_identity(path,*relation,
        composed_relation.relation.metadata()->coordinate_labels);
    const GeometryRequestIdentity identity{
        ProblemId{"hybrid-general-projected-reachability"},
        RequestId{"terminal-state:"+request_identity},ReferenceId{"terminal-state:"+request_identity}};
    const auto selected=projection_.provenance();
    const auto implementation=selected.actual?selected.actual->id:selected.requested.id;
    OperationRequest projection_request{identity,implementation,
        Projection{composed_relation.relation.as_handle(),std::move(coordinates)},
        SetRelation::equivalent,Assurance::numerical};
    const auto provider_admission=projection_.prepare(projection_request);
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"General projected reachability preflight was cancelled during provider admission"};
    if(const auto* rejection=std::get_if<registry::Rejection>(&provider_admission))
        return rejection->diagnostics;
    return std::monostate{};
}

HybridPathReachabilityResult GeneralProjectedStateHybridReachabilityAdapter::compose_path(
    const model::HybridSystem& system,const model::HybridRequest& request,const model::HybridPath& path,
    model::HybridRelationLimits limits,std::stop_token cancellation) const {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"General projected reachability was cancelled before relation construction"};
    const auto admitted=preflight(system,request,path,limits,cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&admitted)) return *failure;
    if(const auto* diagnostics=std::get_if<Diagnostics>(&admitted)) return *diagnostics;
    if(const auto* stopped=std::get_if<OperationStopped>(&admitted)) return *stopped;

    auto composition=model::compose_hybrid_path_relation_with_report(system,request,path,limits,cancellation);
    if(const auto* failure=std::get_if<model::HybridPathCompositionFailureReport>(&composition)) return *failure;
    auto composed=std::get<model::HybridComposedPathRelation>(std::move(composition));
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"General projected reachability stopped before provider admission"};
    const auto relation_representation=composed.relation.representation();
    const auto* h=std::get_if<sets::HRepresentation>(&relation_representation);
    if(!h) return unsupported("hybrid.projected.relation","Joint composer did not return an H relation");
    const auto* terminal=mode(system,path.modes.back());
    if(!terminal || terminal->state_dimension>composed.relation.metadata()->set.dimension)
        return unsupported("hybrid.projected.path","Terminal state coordinates are missing from the joint relation");
    const auto width=composed.relation.metadata()->set.dimension;
    std::vector<std::size_t> coordinates(terminal->state_dimension);
    for(std::size_t i=0;i<coordinates.size();++i)
        coordinates[i]=width-terminal->state_dimension+i;
    const auto input_rows=h->inequalities.rows()+h->equalities.rows();
    const auto request_identity=exact_input_identity(path,*h,composed.relation.metadata()->coordinate_labels);
    const GeometryRequestIdentity identity{ProblemId{"hybrid-general-projected-reachability"},
        RequestId{"terminal-state:"+request_identity},ReferenceId{"terminal-state:"+request_identity}};
    const auto provenance=projection_.provenance();
    const auto implementation=provenance.actual?provenance.actual->id:provenance.requested.id;
    OperationRequest projection_request{identity,implementation,
        Projection{composed.relation.as_handle(),coordinates},SetRelation::equivalent,Assurance::numerical};
    auto prepared_result=projection_.prepare(projection_request);
    if(const auto* rejected=std::get_if<registry::Rejection>(&prepared_result)) return rejected->diagnostics;
    const auto pipeline=std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(prepared_result));
    const auto selected=pipeline.provenance()[0];
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"General projected reachability stopped before projection workspace creation"};
    auto workers=pipeline.create();
    ExecutionContext context;context.cancellation=cancellation;
    const auto outcome=std::get<0>(workers)->run(context);
    if(const auto* stopped=std::get_if<OperationStopped>(&outcome)) return *stopped;
    if(const auto* rejected=std::get_if<Unsupported>(&outcome)) return rejected->diagnostics;
    const auto* projected_result=std::get_if<OperationResult>(&outcome);
    if(!projected_result || projected_result->relation!=SetRelation::equivalent)
        return unsupported("hybrid.projected.provider_result","Projection provider did not return an equivalent terminal set");
    const auto imported=sets::from_handle(projected_result->output);
    if(const auto* diagnostic=std::get_if<Diagnostic>(&imported)) return Diagnostics{*diagnostic};
    auto projected=std::get<sets::SetData>(imported);
    const auto output_rows=std::visit([](const auto& rep)->std::size_t {
        using T=std::decay_t<decltype(rep)>;
        if constexpr(std::is_same_v<T,sets::HRepresentation>)
            return rep.inequalities.rows()+rep.equalities.rows();
        else return 0;
    },projected.representation());
    if(projected.metadata()->set.dimension!=terminal->state_dimension ||
       !std::holds_alternative<sets::HRepresentation>(projected.representation()) ||
       output_rows>maximum_projection_rows_)
        return unsupported("hybrid.projected.provider_shape","Projection provider returned an unsupported terminal-set representation or dimension");
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"General projected reachability stopped before result publication"};
    return HybridPathReachability{path,std::move(composed.relation),limits,std::move(composed.operations),
        Assurance::numerical,HybridPathReachability::ProjectedStateEvidence{std::move(projected),selected,
            input_rows,output_rows,maximum_projection_rows_}};
}
}
