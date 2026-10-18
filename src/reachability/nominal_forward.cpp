#include <csl/reachability/nominal_forward.hpp>
#include <algorithm>
#include <limits>
#include <numeric>
#include <type_traits>
#include <utility>

namespace csl::reachability {
namespace {
Diagnostics error(std::string field,std::string explanation,
        DiagnosticCode code=DiagnosticCode::unsupported) {
    return {{code,std::move(field),std::move(explanation)}};
}
struct ConstructionRejected { Diagnostic diagnostic; };
template<class T> T take(std::variant<T,Diagnostic> value) {
    if(const auto* failure=std::get_if<Diagnostic>(&value))throw ConstructionRejected{*failure};
    return std::get<T>(std::move(value));
}
std::string child(const ProblemId& p,const RequestId& request,std::size_t stage,const std::string& suffix) {
    const auto field=[](const std::string& s){return std::to_string(s.size())+":"+s;};
    return "nominal-forward/"+field(p.value)+field(request.value)+std::to_string(stage)+suffix;
}
std::optional<OperationStopped> stopped(const ExecutionContext& context) {
    if(context.cancellation.stop_requested())return OperationStopped{StopReason::cancelled,"Forward propagation cancelled at a stage/operation boundary."};
    if(context.deadline && std::chrono::steady_clock::now()>=*context.deadline)
        return OperationStopped{StopReason::deadline_expired,"Forward propagation deadline expired at a stage/operation boundary."};
    return {};
}
std::variant<sets::SetData,Diagnostic> native(const AdmissibleSet& set,SetId id,
        const std::vector<std::string>& labels) {
    return std::visit([&](const auto& value) -> std::variant<sets::SetData,Diagnostic> {
        using T=std::decay_t<decltype(value)>;
        if constexpr(std::is_same_v<T,SetHandle>)return sets::from_handle(value);
        else if constexpr(std::is_same_v<T,EmptySet>)return sets::make_empty({id,value.dimension,labels});
        else if constexpr(std::is_same_v<T,UniversalSet>)return sets::make_universal({id,value.dimension,labels});
        else return sets::make_singleton({id,value.point.size(),labels},take(numeric::snapshot_vector(value.point)));
    },set);
}
bool supported(const sets::SetData& data) {
    return !std::holds_alternative<sets::VRepresentation>(data.representation());
}
struct Rows {
    Matrix a,e;
    Vector b,f;
    explicit Rows(std::size_t dimension):a{0,dimension,{}},e{0,dimension,{}} {}
    bool append(Vector values,double bound,bool equality) {
        auto& matrix=equality?e:a;auto& bounds=equality?f:b;
        const auto maximum=std::numeric_limits<std::size_t>::max();
        if(matrix.rows==maximum || (matrix.cols && matrix.rows+1>maximum/matrix.cols))return false;
        ++matrix.rows;matrix.values.insert(matrix.values.end(),values.begin(),values.end());bounds.push_back(bound);return true;
    }
    bool add(const sets::SetData& data,std::size_t offset) {
        const auto rep=data.representation();const auto n=data.metadata()->set.dimension;
        if(const auto* h=std::get_if<sets::HRepresentation>(&rep)) {
            const auto copy=[&](numeric::MatrixView matrix,numeric::VectorView bounds,bool equality) {
                for(std::size_t r=0;r<matrix.rows();++r) {
                    Vector values(a.cols,0);for(std::size_t c=0;c<n;++c)values[offset+c]=matrix(r,c);
                    if(!append(std::move(values),bounds[r],equality))return false;
                }return true;
            };
            return copy(h->inequalities,h->upper_bounds,false) && copy(h->equalities,h->equality_values,true);
        }
        if(const auto* point=std::get_if<sets::SingletonRepresentation>(&rep)) {
            for(std::size_t c=0;c<n;++c) {Vector row(a.cols,0);row[offset+c]=1;if(!append(std::move(row),point->point[c],true))return false;}
        } else if(std::holds_alternative<sets::EmptyRepresentation>(rep))return append(Vector(a.cols,0),-1,false);
        return true;
    }
    sets::SetData finish(SetId id,std::vector<std::string> labels) {
        return take(sets::make_h({std::move(id),a.cols,std::move(labels)},
            {take(numeric::snapshot(a)),take(numeric::snapshot_vector(b)),take(numeric::snapshot(e)),take(numeric::snapshot_vector(f))}));
    }
};
bool empty_zero_projection(const sets::SetData& data) {
    const auto rep=data.representation();
    if(std::holds_alternative<sets::EmptyRepresentation>(rep))return true;
    if(const auto* h=std::get_if<sets::HRepresentation>(&rep)) {
        for(std::size_t r=0;r<h->inequalities.rows();++r)if(h->upper_bounds[r]<0)return true;
        for(std::size_t r=0;r<h->equalities.rows();++r)if(h->equality_values[r]!=0)return true;
    }
    return false;
}
std::vector<std::size_t> coordinates(std::size_t offset,std::size_t count) {
    std::vector<std::size_t> result(count);std::iota(result.begin(),result.end(),offset);return result;
}
sets::SetData relabel(const sets::SetData& data,SetId id,std::vector<std::string> labels) {
    const sets::Description description{std::move(id),data.metadata()->set.dimension,std::move(labels)};
    return std::visit([&](const auto& representation) -> sets::SetData {
        using T=std::decay_t<decltype(representation)>;
        if constexpr(std::is_same_v<T,sets::HRepresentation>)return take(sets::make_h(description,representation));
        else if constexpr(std::is_same_v<T,sets::VRepresentation>)return take(sets::make_v(description,representation));
        else if constexpr(std::is_same_v<T,sets::SingletonRepresentation>)return take(sets::make_singleton(description,representation.point));
        else if constexpr(std::is_same_v<T,sets::EmptyRepresentation>)return take(sets::make_empty(description));
        else return take(sets::make_universal(description));
    },data.representation());
}
}

NominalForwardOutcome nominal_forward(const problem::ResolvedProblem& resolved,RequestId request,
        const ForwardDependencies& dependencies,const ExecutionContext& context) {
    const auto& provider=dependencies.projection;
    ForwardTube tube{resolved.identity(),std::move(request),{}};
    StageIndex stage{0};std::optional<GeometryReference> active;
    std::optional<ForwardPartialRelation> partial_relation;
    std::vector<GeometryEvidence> lineage;std::vector<RequestProvenance> providers;
    std::vector<CoordinateRelabeling> coordinate_lineage;
    const auto failure=[&](auto cause) -> NominalForwardOutcome {
        using Cause = std::remove_cvref_t<decltype(cause)>;
        return NominalForwardOutcome{std::in_place_type<ForwardFailure>,tube,stage,partial_relation,
            active,lineage,providers,coordinate_lineage,
            std::variant<Unsupported,OperationStopped>{std::in_place_type<Cause>,std::move(cause)}};
    };
    try {
    if(tube.request.value.empty())return failure(Unsupported{error("forward.request","Nonempty immutable request ID required.",DiagnosticCode::invalid_input)});
    const auto p=resolved.description();const auto system=resolved.model();const auto dims=system.dimensions();
    if(p->temporal && p->temporal->joint_map.rows!=0)
        return failure(Unsupported{error("forward.temporal","Declared temporal constraints require a coupled-history algorithm.")});
    if(p->model->dynamics.time_domain!=TimeDomain::discrete || p->information!=InformationPattern::nominal_open_loop)
        return failure(Unsupported{error("forward.profile","Discrete nominal open-loop dynamics required.")});
    if(dims.external || p->external)return failure(Unsupported{error("forward.external","External inputs are outside this nominal profile.")});
    if(!std::holds_alternative<KnownInitial>(p->initial))return failure(Unsupported{error("forward.initial","This nominal profile requires a known initial point.")});
    const auto* continuous=std::get_if<ContinuousDomain>(&p->controls);
    if(!continuous)return failure(Unsupported{error("forward.controls","Continuous controls required; finite/mixed choices are not convexified.")});
    const auto& policy=provider.requirements().output;
    if(!provider.provenance().actual || policy.representation.value!="csl.polyhedron.h" ||
            policy.relation!=SetRelation::equivalent || policy.assurance!=Assurance::numerical)
        return failure(Unsupported{error("forward.provider","Select an equivalent numerical native H projection provider; validated authored recurrence is unavailable.")});
    const auto admitted=[](const auto& selected,const char* representation) {
        const auto& output=selected.requirements().output;
        return selected.provenance().actual && output.representation.value==representation &&
            output.relation==SetRelation::equivalent && output.assurance==Assurance::numerical;
    };
    if(!admitted(dependencies.affine_sum,"csl.polyhedron.v") || !admitted(dependencies.to_h,"csl.polyhedron.h"))
        return failure(Unsupported{error("forward.provider","Equivalent numerical V affine/sum and H conversion providers required.")});
    const auto n=dims.state,m=dims.control,maximum=std::numeric_limits<std::size_t>::max();
    if(n>maximum-m || n>maximum-(n+m))return failure(Unsupported{error("forward.capacity","Joint [x,u,y] dimension overflows size_t.")});

    // Admit every authored operand before any operation/workspace. These are
    // resolved snapshots; shape/time/dynamics validation belongs to resolve.
    std::vector<sets::SetData> states,controls;std::vector<std::string> labels;
    for(std::size_t t=0;t<=system.horizon();++t) {
        auto imported=native(p->states[t],{child(tube.problem,tube.request,t,"/state-constraint")},labels);
        if(const auto* rejected=std::get_if<Diagnostic>(&imported))return failure(Unsupported{{*rejected}});
        auto data=std::get<sets::SetData>(std::move(imported));
        if(!supported(data))return failure(Unsupported{error("forward.representation","Native H, singleton, empty or universal factors required; explicit conversion is separate.")});
        if(t==0)labels=data.metadata()->coordinate_labels;
        if(data.metadata()->coordinate_labels!=labels)return failure(Unsupported{error("forward.coordinates","All state factors must use the same ordered coordinates.",DiagnosticCode::invalid_input)});
        states.push_back(std::move(data));
    }
    for(std::size_t t=0;t<system.horizon();++t) {
        auto imported=native(continuous->stages[t],{child(tube.problem,tube.request,t,"/control-constraint")},{});
        if(const auto* rejected=std::get_if<Diagnostic>(&imported))return failure(Unsupported{{*rejected}});
        auto data=std::get<sets::SetData>(std::move(imported));
        if(!supported(data))return failure(Unsupported{error("forward.representation","Native H controls required; explicit conversion is separate.")});
        controls.push_back(std::move(data));
    }
    const auto remember=[&](const auto& selected,const GeometryRequestIdentity& identity,std::vector<SetId> inputs) {
        active=GeometryReference{identity,std::move(inputs)};
        const auto& provenance=selected.provenance();
        providers.push_back({identity.request,provenance.port,provenance.requested.id,provenance.requested.version,
            provenance.actual->id,provenance.actual->version});
    };
    const auto native_result=[&](const OperationResult& result,const char* representation) -> Diagnostics {
        auto imported=sets::from_handle(result.output);
        if(auto* rejected=std::get_if<Diagnostic>(&imported))return {*rejected};
        if(result.relation!=SetRelation::equivalent || result.output.metadata.representation.value!=representation ||
                result.output.metadata.dimension!=n || !std::get<sets::SetData>(imported).metadata()->coordinate_labels.empty())
            return error("forward.result","Provider changed the selected relation, representation or ordered state coordinates.",DiagnosticCode::evidence_mismatch);
        return {};
    };
    const auto run_affine=[&](GeometryOperation operation,const char* suffix)
            -> std::variant<OperationResult,Unsupported,OperationStopped> {
        const auto& selected=dependencies.affine_sum;
        OperationRequest request_{{tube.problem,{child(tube.problem,tube.request,stage.value,suffix)},
            {child(tube.problem,tube.request,stage.value,std::string(suffix)+"/output")}},
            selected.provenance().actual->id,std::move(operation),SetRelation::equivalent,Assurance::numerical};
        std::vector<SetId> inputs;
        if(const auto* image=std::get_if<AffineImage>(&request_.operation))inputs={image->input.id};
        else {const auto& sum=std::get<MinkowskiSum>(request_.operation);inputs={sum.left.id,sum.right.id};}
        remember(selected,request_.identity,std::move(inputs));
        if(auto stop=stopped(context))return *stop;
        auto prepared=selected.prepare(request_);
        if(auto* rejected=std::get_if<registry::Rejection>(&prepared))return Unsupported{rejected->diagnostics};
        auto workspace=std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(prepared)).create();
        auto outcome=std::get<0>(workspace)->run(context);
        if(auto* rejected=std::get_if<Unsupported>(&outcome))return *rejected;
        if(auto* stop=std::get_if<OperationStopped>(&outcome))return *stop;
        const auto* result=std::get_if<OperationResult>(&outcome);
        if(!result)return Unsupported{error("forward.result","Affine/sum provider returned a query result.",DiagnosticCode::evidence_mismatch)};
        if(auto errors=check_geometry_evidence(result->evidence,request_);!errors.empty())return Unsupported{std::move(errors)};
        if(auto errors=native_result(*result,"csl.polyhedron.v");!errors.empty())return Unsupported{std::move(errors)};
        lineage.push_back(result->evidence);
        if(auto stop=stopped(context))return *stop;
        return *result;
    };
    const auto convert=[&](SetHandle input) -> std::variant<OperationResult,Unsupported,OperationStopped> {
        const auto& selected=dependencies.to_h;
        ConversionRequest request_{{tube.problem,{child(tube.problem,tube.request,stage.value,"/to-h")},
            {child(tube.problem,tube.request,stage.value,"/to-h/output")}},input,{"csl.polyhedron.h"},Assurance::numerical};
        remember(selected,request_.identity,{input.id});
        if(auto stop=stopped(context))return *stop;
        auto prepared=selected.prepare(request_);
        if(auto* rejected=std::get_if<registry::Rejection>(&prepared))return Unsupported{rejected->diagnostics};
        auto workspace=std::get<registry::PreparedPipeline<registry::ConversionPort>>(std::move(prepared)).create();
        auto outcome=std::get<0>(workspace)->run(context);
        if(auto* rejected=std::get_if<Unsupported>(&outcome))return *rejected;
        if(auto* stop=std::get_if<OperationStopped>(&outcome))return *stop;
        const auto result=std::get<OperationResult>(std::move(outcome));
        if(auto errors=check_geometry_evidence(result.evidence,request_);!errors.empty())return Unsupported{std::move(errors)};
        if(auto errors=native_result(result,"csl.polyhedron.h");!errors.empty())return Unsupported{std::move(errors)};
        lineage.push_back(result.evidence);
        if(auto stop=stopped(context))return *stop;
        return result;
    };
    const auto run_projection=[&](SetHandle input,std::vector<std::size_t> selected,const char* suffix)
            -> std::variant<OperationResult,Unsupported,OperationStopped> {
        OperationRequest operation{{tube.problem,{child(tube.problem,tube.request,stage.value,suffix)},
            {child(tube.problem,tube.request,stage.value,std::string(suffix)+"/output")}},
            provider.provenance().actual->id,Projection{input,std::move(selected)},SetRelation::equivalent,Assurance::numerical};
        active=GeometryReference{operation.identity,{input.id}};
        const auto& provenance=provider.provenance();
        providers.push_back({operation.identity.request,provenance.port,provenance.requested.id,provenance.requested.version,
            provenance.actual->id,provenance.actual->version});
        if(auto stop=stopped(context))return *stop;
        auto prepared=provider.prepare(operation);
        if(auto* rejected=std::get_if<registry::Rejection>(&prepared))return Unsupported{rejected->diagnostics};
        auto workspaces=std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(prepared)).create();
        auto outcome=std::get<0>(workspaces)->run(context);
        if(auto* rejected=std::get_if<Unsupported>(&outcome))return *rejected;
        if(auto* stop=std::get_if<OperationStopped>(&outcome))return *stop;
        auto* result=std::get_if<OperationResult>(&outcome);
        if(!result)return Unsupported{error("forward.result","Projection returned a query result.",DiagnosticCode::evidence_mismatch)};
        if(auto errors=check_geometry_evidence(result->evidence,operation);!errors.empty())return Unsupported{std::move(errors)};
        auto output=sets::from_handle(result->output);
        if(auto* rejected=std::get_if<Diagnostic>(&output))return Unsupported{{*rejected}};
        const auto& data=std::get<sets::SetData>(output);
        const auto& selection=std::get<Projection>(operation.operation).coordinates;
        const auto source=take(sets::from_handle(input));std::vector<std::string> expected;
        if(!source.metadata()->coordinate_labels.empty())for(auto c:selection)expected.push_back(source.metadata()->coordinate_labels[c]);
        if(result->relation!=SetRelation::equivalent || result->output.metadata.representation.value!="csl.polyhedron.h" ||
                result->output.metadata.dimension!=selection.size() || data.metadata()->coordinate_labels!=expected)
            return Unsupported{error("forward.result","Projection changed the selected relation, native H representation or coordinates.",DiagnosticCode::evidence_mismatch)};
        lineage.push_back(result->evidence);
        if(auto stop=stopped(context))return *stop;
        return std::move(*result);
    };
    for(std::size_t t=0;t<=system.horizon();++t) {
        stage={t};partial_relation.reset();active.reset();lineage.clear();providers.clear();coordinate_lineage.clear();
        if(auto stop=stopped(context))return failure(*stop);
        Rows rows(t?2*n+m:n);std::vector<SetId> factors;std::vector<std::string> joint_labels;
        std::vector<std::size_t> current,control,next;
        bool assembled=true;
        if(t==0) {
            const auto initial=take(sets::make_singleton({{child(tube.problem,tube.request,0,"/initial")},n,labels},
                take(numeric::snapshot_vector(std::get<KnownInitial>(p->initial).point))));
            assembled=rows.add(initial,0) && rows.add(states[0],0);
            factors={initial.metadata()->id,states[0].metadata()->id};next=coordinates(0,n);joint_labels=labels;
        } else {
            const auto previous=take(sets::from_handle(tube.stages.back().marginal.output));
            assembled=rows.add(previous,0) && rows.add(controls[t-1],n) && rows.add(states[t],n+m);
            const auto dynamics=take(system.stage({t-1}));
            for(std::size_t r=0;r<n && assembled;++r) {
                Vector values(2*n+m,0);
                for(std::size_t c=0;c<n;++c)values[c]=-dynamics.A(r,c);
                for(std::size_t c=0;c<m;++c)values[n+c]=-dynamics.B(r,c);
                values[n+m+r]=1;assembled=rows.append(std::move(values),dynamics.offset[r],true);
            }
            factors={previous.metadata()->id,controls[t-1].metadata()->id,states[t].metadata()->id};
            current=coordinates(0,n);control=coordinates(n,m);next=coordinates(n+m,n);
            if(!labels.empty()) {
                // Prefixes are made disjoint from authored next-state labels.
                std::string prefix="$forward/";
                while(std::any_of(labels.begin(),labels.end(),[&](const auto& label){return label.starts_with(prefix);}))prefix="$"+prefix;
                for(const auto& label:labels)joint_labels.push_back(prefix+"state/"+label);
                const auto control_labels=controls[t-1].metadata()->coordinate_labels;
                for(std::size_t c=0;c<m;++c)joint_labels.push_back(prefix+"control/"+(control_labels.empty()?std::to_string(c):control_labels[c]));
                joint_labels.insert(joint_labels.end(),labels.begin(),labels.end());
            }
        }
        if(!assembled)return failure(Unsupported{error("forward.capacity","Joint row storage overflows size_t.")});
        const auto joint=rows.finish({child(tube.problem,tube.request,t,"/joint")},std::move(joint_labels)).as_handle();
        auto propagation=joint;auto marginal_coordinates=next;
        if(t) {
            const auto bridge=[&](SetHandle source,std::vector<std::string> target_labels,const char* suffix) {
                const auto data=take(sets::from_handle(source));
                if(data.metadata()->coordinate_labels==target_labels)return source;
                auto target=relabel(data,{child(tube.problem,tube.request,t,suffix)},std::move(target_labels)).as_handle();
                coordinate_lineage.push_back({source,target,coordinates(0,source.metadata.dimension)});
                return target;
            };
            const auto dynamics=take(system.stage({t-1}));
            const auto matrix=[](numeric::MatrixView view) {
                Matrix result{view.rows(),view.cols(),{}};
                for(std::size_t r=0;r<view.rows();++r)for(std::size_t c=0;c<view.cols();++c)result.values.push_back(view(r,c));
                return result;
            };
            Vector offset;for(std::size_t r=0;r<n;++r)offset.push_back(dynamics.offset[r]);
            auto state_operand=bridge(tube.stages.back().marginal.output,{},"/unnamed-state");
            auto control_operand=bridge(controls[t-1].as_handle(),{},"/unnamed-control");
            auto state_image=run_affine(AffineImage{state_operand,matrix(dynamics.A),std::move(offset)},"/affine-state");
            if(auto* rejected=std::get_if<Unsupported>(&state_image))return failure(*rejected);
            if(auto* stop=std::get_if<OperationStopped>(&state_image))return failure(*stop);
            auto control_image=run_affine(AffineImage{control_operand,matrix(dynamics.B),Vector(n,0)},"/affine-control");
            if(auto* rejected=std::get_if<Unsupported>(&control_image))return failure(*rejected);
            if(auto* stop=std::get_if<OperationStopped>(&control_image))return failure(*stop);
            auto sum=run_affine(MinkowskiSum{std::get<OperationResult>(state_image).output,std::get<OperationResult>(control_image).output},"/sum");
            if(auto* rejected=std::get_if<Unsupported>(&sum))return failure(*rejected);
            if(auto* stop=std::get_if<OperationStopped>(&sum))return failure(*stop);
            auto converted=convert(std::get<OperationResult>(sum).output);
            if(auto* rejected=std::get_if<Unsupported>(&converted))return failure(*rejected);
            if(auto* stop=std::get_if<OperationStopped>(&converted))return failure(*stop);
            const auto labelled_sum=bridge(std::get<OperationResult>(converted).output,labels,"/labelled-sum");
            Rows intersection(n);
            if(!intersection.add(take(sets::from_handle(labelled_sum)),0) || !intersection.add(states[t],0))
                return failure(Unsupported{error("forward.capacity","Intersection row storage overflows size_t.")});
            propagation=intersection.finish({child(tube.problem,tube.request,t,"/intersection")},labels).as_handle();
            marginal_coordinates=coordinates(0,n);
        }
        const auto scoped_coordinates=marginal_coordinates;
        auto projected=run_projection(propagation,std::move(marginal_coordinates),"/project");
        if(auto* rejected=std::get_if<Unsupported>(&projected))return failure(*rejected);
        if(auto* stop=std::get_if<OperationStopped>(&projected))return failure(*stop);
        auto marginal=std::get<OperationResult>(std::move(projected));
        marginal.evidence.reference={{tube.problem,{child(tube.problem,tube.request,t,"/stage")},
            {child(tube.problem,tube.request,t,"/reachable")}},factors};
        marginal.evidence.scope=GeometryClaimScope::set_relation;
        marginal.evidence.support=Unestablished{};marginal.evidence.error_bound.reset();
        marginal.evidence.assumptions.push_back("selected affine-image, sum, conversion and projection evidence retained separately; authored aggregate recurrence and compiled recovery-factor support remain unestablished");
        marginal.evidence.assumptions.push_back("stage marginal only; no optimality or joint-history completeness claim");
        partial_relation=ForwardPartialRelation{stage,marginal,propagation,scoped_coordinates};
        // Eliminate all coordinates to decide emptiness rather than interpreting
        // an H payload or absence of sampled points as a feasibility proof.
        auto feasibility=run_projection(propagation,{},"/feasibility");
        if(auto* rejected=std::get_if<Unsupported>(&feasibility))return failure(*rejected);
        if(auto* stop=std::get_if<OperationStopped>(&feasibility))return failure(*stop);
        const auto probe=std::get<OperationResult>(std::move(feasibility));
        const bool empty=empty_zero_projection(take(sets::from_handle(probe.output)));
        auto recovery=marginal.evidence;
        recovery.reference.identity.request={child(tube.problem,tube.request,t,"/recovery")};
        recovery.reference.identity.ideal_output={joint.id.value};
        recovery.assumptions.push_back("compiled [x,u,y] authored transition rows retained for future recovery; no provider or validated recovery theorem asserted");
        tube.stages.push_back({stage,std::move(marginal),joint,std::move(recovery),propagation,std::move(factors),std::move(current),std::move(control),
            std::move(next),lineage,providers,coordinate_lineage});
        partial_relation.reset();
        if(empty) {
            auto evidence=tube.stages.back().marginal.evidence;
            evidence.assumptions.push_back("zero-coordinate projection of the propagation factor is empty; authored emptiness support remains unestablished");
            return EmptyForwardStage{std::move(tube),stage,std::move(evidence)};
        }
    }
    return tube;
    } catch(const ConstructionRejected& rejected) {
        return failure(Unsupported{{rejected.diagnostic}});
    } catch(const std::bad_alloc&) {
        return failure(OperationStopped{StopReason::resource_limit,"Allocation failed while constructing a forward stage."});
    } catch(const std::length_error&) {
        return failure(OperationStopped{StopReason::resource_limit,"Forward stage storage exceeds container capacity."});
    }
}
} // namespace csl::reachability
