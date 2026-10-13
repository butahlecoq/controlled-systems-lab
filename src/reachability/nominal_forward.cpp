#include <csl/reachability/nominal_forward.hpp>
#include <algorithm>
#include <limits>
#include <numeric>

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
}

NominalForwardOutcome nominal_forward(const problem::ResolvedProblem& resolved,RequestId request,
        const registry::PreparedProvider<registry::GeometryPort>& provider,const ExecutionContext& context) {
    ForwardTube tube{resolved.identity(),std::move(request),{}};
    StageIndex stage{0};std::optional<GeometryReference> active;
    std::vector<GeometryEvidence> lineage;std::vector<RequestProvenance> providers;
    const auto failure=[&](auto cause) -> NominalForwardOutcome {
        return ForwardFailure{tube,stage,active,lineage,providers,std::move(cause)};
    };
    try {
    if(tube.request.value.empty())return failure(Unsupported{error("forward.request","Nonempty immutable request ID required.",DiagnosticCode::invalid_input)});
    const auto p=resolved.description();const auto system=resolved.model();const auto dims=system.dimensions();
    if(p->temporal)return failure(Unsupported{error("forward.temporal","Declared temporal constraints require a coupled-history algorithm.")});
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
        stage={t};active.reset();lineage.clear();providers.clear();
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
        auto projected=run_projection(joint,next,"/project");
        if(auto* rejected=std::get_if<Unsupported>(&projected))return failure(*rejected);
        if(auto* stop=std::get_if<OperationStopped>(&projected))return failure(*stop);
        auto marginal=std::get<OperationResult>(std::move(projected));
        // Eliminate all coordinates to decide emptiness rather than interpreting
        // an H payload or absence of sampled points as a feasibility proof.
        auto feasibility=run_projection(joint,{},"/feasibility");
        if(auto* rejected=std::get_if<Unsupported>(&feasibility))return failure(*rejected);
        if(auto* stop=std::get_if<OperationStopped>(&feasibility))return failure(*stop);
        const auto probe=std::get<OperationResult>(std::move(feasibility));
        const bool empty=empty_zero_projection(take(sets::from_handle(probe.output)));
        marginal.evidence.reference={{tube.problem,{child(tube.problem,tube.request,t,"/stage")},
            {child(tube.problem,tube.request,t,"/reachable")}},factors};
        marginal.evidence.support=Unestablished{};marginal.evidence.error_bound.reset();
        marginal.evidence.assumptions.push_back("authored recurrence compiled into [x,u,y] affine equality factors; binary64 operation lineage retained separately");
        marginal.evidence.assumptions.push_back("stage marginal only; no optimality or joint-history completeness claim");
        tube.stages.push_back({stage,std::move(marginal),joint,std::move(factors),std::move(current),std::move(control),
            std::move(next),lineage,providers});
        if(empty) {
            auto evidence=tube.stages.back().marginal.evidence;
            evidence.assumptions.push_back("zero-coordinate projection of the joint factor is empty; authored emptiness support remains unestablished");
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
