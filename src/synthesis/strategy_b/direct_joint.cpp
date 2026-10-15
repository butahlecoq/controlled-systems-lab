#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>
#include <csl/synthesis/ts02_constant_integrator.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <csl/verification/trajectory.hpp>
#include "../../registry/compiled_verifiers.hpp"
#include "../../registry/runtime_lineage.hpp"
#include "../../registry/strategy_b_lineage.hpp"
#include <algorithm>
#include <limits>
#include <numeric>
#include <type_traits>
#include <utility>

namespace csl::synthesis::strategy_b {
namespace {
const RepresentationId h_polyhedron{"csl.polyhedron.h"};
Diagnostic unsupported(std::string field, std::string text) {
    return {DiagnosticCode::unsupported,std::move(field),std::move(text)};
}
Diagnostics capabilities(const problem::ResolvedProblem& p,const FamilyRequest& request) {
    auto d=check_family_request(request,p.identity());
    const auto source=p.description();
    const bool reviewed_ts01=registry::detail::ts01_case_valid(p,request,h_polyhedron);
    const bool reviewed_ts02=registry::detail::ts02_case_valid(p,request,h_polyhedron);
    if(request.profile!="nominal_open_loop"&&!reviewed_ts01)
        if(!reviewed_ts02)d.push_back(unsupported("joint.profile","Supported profiles are nominal_open_loop and the exact reviewed T-S01/T-S02 cases."));
    if(request.representation.value!="csl.polyhedron.h") d.push_back(unsupported("joint.representation","Native joint H relation is required."));
    if(request.assurance!=Assurance::numerical) d.push_back(unsupported("joint.assurance","Validated construction is unavailable."));
    if(request.target!=FamilyTarget::candidate_relaxation&&!reviewed_ts01&&!reviewed_ts02)
        d.push_back(unsupported("joint.coverage","Only the exact reviewed T-S01/T-S02 profiles have registered complete-family verifiers; other requests remain candidates."));
    if(source->information!=InformationPattern::nominal_open_loop || source->model->dynamics.time_domain!=TimeDomain::discrete)
        d.push_back(unsupported("joint.dynamics","Discrete nominal open-loop dynamics are required."));
    if(source->external || p.model().dimensions().external!=0) d.push_back(unsupported("joint.external","External inputs require a different profile."));
    if(!std::holds_alternative<KnownInitial>(source->initial)) d.push_back(unsupported("joint.initial","A known initial point is required."));
    if(!std::holds_alternative<ContinuousDomain>(source->controls)) d.push_back(unsupported("joint.controls","Continuous controls are required."));
    const auto native=[&](const AdmissibleSet& set) {
        if(const auto* h=std::get_if<SetHandle>(&set)) {
            const auto data=sets::from_handle(*h);
            if(const auto* error=std::get_if<Diagnostic>(&data)) d.push_back(*error);
            else if(std::holds_alternative<sets::VRepresentation>(std::get<sets::SetData>(data).representation()))
                d.push_back(unsupported("joint.set","Native H, singleton, empty or universal constraints are required; no implicit conversion."));
        }
    };
    for(const auto& set:source->states) native(set);
    if(const auto* c=std::get_if<ContinuousDomain>(&source->controls)) for(const auto& set:c->stages) native(set);
    return d;
}
struct Assembly {
    SparseMatrix matrix;
    std::vector<Interval> bounds;
    std::vector<RowLineage> lineage;
    explicit Assembly(std::size_t n):matrix{0,n,{0},{},{}}{}
    void append(const Vector& row,Interval bound,RowSource source,std::size_t stage,std::size_t source_row) {
        for(std::size_t j=0;j<row.size();++j) if(row[j]!=0) {
            matrix.column_indices.push_back(j); matrix.values.push_back(row[j]);
        }
        lineage.push_back({source,stage,source_row,matrix.rows++});
        matrix.row_offsets.push_back(matrix.values.size()); bounds.push_back(bound);
    }
    void append_set(const AdmissibleSet& set,std::size_t offset,std::size_t dimension,RowSource source,std::size_t stage) {
        auto singleton=[&](std::span<const double> x) {
            for(std::size_t j=0;j<dimension;++j) {Vector row(matrix.cols);row[offset+j]=1;append(row,{x[j],x[j]},source,stage,j);}
        };
        auto empty=[&] {append(Vector(matrix.cols),{std::nullopt,-1},source,stage,0);};
        std::visit([&](const auto& s) {
            using T=std::decay_t<decltype(s)>;
            if constexpr(std::is_same_v<T,Singleton>) singleton(s.point);
            else if constexpr(std::is_same_v<T,EmptySet>) empty();
            else if constexpr(std::is_same_v<T,SetHandle>) {
                const auto data=std::get<sets::SetData>(sets::from_handle(s));
                const auto r=data.representation();
                if(const auto* h=std::get_if<sets::HRepresentation>(&r)) {
                    auto add=[&](numeric::MatrixView map,numeric::VectorView rhs,bool eq,std::size_t first) {
                        for(std::size_t i=0;i<map.rows();++i) {Vector row(matrix.cols);
                            for(std::size_t j=0;j<dimension;++j) row[offset+j]=map(i,j);
                            append(row,{eq?std::optional<double>{rhs[i]}:std::nullopt,rhs[i]},source,stage,first+i);
                        }
                    };
                    add(h->inequalities,h->upper_bounds,false,0); add(h->equalities,h->equality_values,true,h->inequalities.rows());
                } else if(const auto* x=std::get_if<sets::SingletonRepresentation>(&r)) singleton(x->point.values());
                else if(std::holds_alternative<sets::EmptyRepresentation>(r)) empty();
            }
        },set);
    }
};
TerminalObjective lift(const TerminalObjective& objective,std::size_t width,std::size_t offset,std::size_t n) {
    return std::visit([&](const auto& c)->TerminalObjective {
        using T=std::decay_t<decltype(c)>;
        if constexpr(std::is_same_v<T,LinearTerminal>) {
            Vector q(width); std::copy(c.coefficients.begin(),c.coefficients.end(),q.begin()+offset);
            return LinearTerminal{std::move(q),c.offset};
        } else if constexpr(std::is_same_v<T,QuadraticTerminal>) {
            Matrix Q{width,width,Vector(width*width)};Vector q(width);
            for(std::size_t i=0;i<n;++i)for(std::size_t j=0;j<n;++j)Q.values[(offset+i)*width+offset+j]=c.Q.values[i*n+j];
            std::copy(c.linear.begin(),c.linear.end(),q.begin()+offset);
            return QuadraticTerminal{std::move(Q),std::move(q),c.offset};
        } else {
            Matrix L{c.map.rows,width,Vector(c.map.rows*width)};
            for(std::size_t i=0;i<c.map.rows;++i)for(std::size_t j=0;j<n;++j)L.values[i*width+offset+j]=c.map.values[i*n+j];
            return ResidualNormTerminal{std::move(L),c.target};
        }
    },objective);
}
} // namespace
JointProgramOutcome build_joint_program(const problem::ResolvedProblem& p, const FamilyRequest& request) {
    auto diagnostics=capabilities(p,request); if(!diagnostics.empty()) return diagnostics;
    const auto source=p.description();const auto coords=p.constraints().coordinates();
    const auto width=p.constraints().joint_dimension();const auto n=coords.dimensions.state;
    const auto m=coords.dimensions.control;const auto T=coords.horizon;
    const auto max=std::numeric_limits<std::size_t>::max();
    if(width!=0 && width>max/width) return Diagnostics{unsupported("joint.capacity","Objective storage width overflows size_t.")};
    if(const auto* residual=std::get_if<ResidualNormTerminal>(&source->objective); residual && width!=0 && residual->map.rows>max/width)
        return Diagnostics{unsupported("joint.capacity","Residual map storage overflows size_t.")};
    Assembly a(width);
    a.append_set(Singleton{std::get<KnownInitial>(source->initial).point},0,n,RowSource::initial,0);
    for(std::size_t t=0;t<=T;++t) a.append_set(source->states[t],t*n,n,RowSource::state,t);
    const auto& controls=std::get<ContinuousDomain>(source->controls);
    for(std::size_t t=0;t<T;++t) a.append_set(controls.stages[t],(T+1)*n+t*m,m,RowSource::control,t);
    for(std::size_t t=0;t<T;++t) {
        const auto step=std::get<model::DynamicsStage>(p.model().stage({t}));
        for(std::size_t i=0;i<n;++i) {
            Vector row(width); row[(t+1)*n+i]=1;
            for(std::size_t j=0;j<n;++j) row[t*n+j]=-step.A(i,j);
            for(std::size_t j=0;j<m;++j) row[(T+1)*n+t*m+j]=-step.B(i,j);
            a.append(row,{step.offset[i],step.offset[i]},RowSource::transition,t,i);
        }
    }
    if(const auto temporal=p.constraints().temporal())for(std::size_t i=0;i<temporal->joint_map.rows();++i) {
        Vector row(width);for(std::size_t j=0;j<width;++j)row[j]=temporal->joint_map(i,j);
        a.append(row,(*temporal->bounds)[i],RowSource::temporal,0,i);
    }
    auto objective=lift(source->objective,width,T*n,n);
    const ProgramIdentity id{p.identity(),{"syn04-joint:"+p.identity().value}};
    std::optional<std::variant<LinearProgram,ConvexProgram>> program;
    if(const auto* c=std::get_if<LinearTerminal>(&objective)) {
        auto built=optimization::make_linear_program({id,c->coefficients,c->offset,a.matrix,std::vector<Interval>(width),a.bounds});
        if(const auto* d=std::get_if<Diagnostics>(&built)) return *d;
        program=std::get<LinearProgram>(std::move(built));
    } else {
        auto built=optimization::make_convex_program({id,objective,a.matrix,std::vector<Interval>(width),a.bounds,
            std::holds_alternative<ResidualNormTerminal>(objective)?std::optional<ProgramId>{{id.program.value+":squared"}}:std::nullopt},{request.assurance,request.numerical});
        if(const auto* d=std::get_if<Diagnostics>(&built)) return *d;
        if(const auto* stop=std::get_if<OperationStopped>(&built)) return *stop;
        program=std::get<ConvexProgram>(std::move(built));
    }
    std::vector<std::size_t> map(width);std::iota(map.begin(),map.end(),0);
    return JointProgram{coords,std::move(map),std::move(a.lineage),std::move(a.matrix),std::move(a.bounds),std::move(objective),std::move(*program)};
}
DirectJointPayload::DirectJointPayload(JointProgram p,sets::SetData r):construction(std::move(p)),relation(std::move(r)){}
DirectJointWorkspace::DirectJointWorkspace(registry::PreparedProvider<registry::LPPort> lp,registry::PreparedProvider<registry::ConvexPort> qp)
    :lp_(std::move(lp)),convex_(std::move(qp)){}
namespace {
constexpr const char* strategy_id="csl.synthesis.strategy-b";
constexpr const char* strategy_version="1";
constexpr const char* complete_verifier_id="csl.verifier.ts01-analytic";
constexpr const char* complete_verifier_version="1";
Termination stopped_termination(StopReason reason) {
    switch(reason) {
    case StopReason::cancelled:case StopReason::deadline_expired:return Termination::cancelled;
    case StopReason::resource_limit:return Termination::resource_limit;
    case StopReason::numerical_failure:return Termination::numerical_failure;
    }
    return Termination::numerical_failure;
}
struct RelationRows {
    Matrix inequalities, equalities;
    Vector upper, values;
    explicit RelationRows(std::size_t width):inequalities{0,width,{}},equalities{0,width,{}}{}
    void equality(const Vector& row,double rhs) {
        equalities.values.insert(equalities.values.end(),row.begin(),row.end());++equalities.rows;values.push_back(rhs);
    }
    void inequality(const Vector& row,double rhs) {
        inequalities.values.insert(inequalities.values.end(),row.begin(),row.end());++inequalities.rows;upper.push_back(rhs);
    }
    std::variant<sets::SetData,Diagnostics> finish(SetId id,std::vector<std::string> labels={}) const {
        const auto A=numeric::snapshot(inequalities),E=numeric::snapshot(equalities);
        const auto b=numeric::snapshot_vector(upper),e=numeric::snapshot_vector(values);
        for(const auto* matrix:{&A,&E})if(const auto* d=std::get_if<Diagnostic>(matrix))return Diagnostics{*d};
        for(const auto* vector:{&b,&e})if(const auto* d=std::get_if<Diagnostic>(vector))return Diagnostics{*d};
        auto r=sets::make_h({std::move(id),inequalities.cols,std::move(labels)},{std::get<numeric::MatrixView>(A),std::get<numeric::VectorView>(b),std::get<numeric::MatrixView>(E),std::get<numeric::VectorView>(e)});
        if(const auto* d=std::get_if<Diagnostic>(&r))return Diagnostics{*d};
        return std::get<sets::SetData>(std::move(r));
    }
};
RelationRows feasible_rows(const JointProgram& p) {
    RelationRows r(p.constraints.cols);
    for(std::size_t i=0;i<p.constraints.rows;++i) {
        Vector row(p.constraints.cols);for(auto j=p.constraints.row_offsets[i];j<p.constraints.row_offsets[i+1];++j)row[p.constraints.column_indices[j]]=p.constraints.values[j];
        const auto& bound=p.bounds[i];
        if(bound.lower && bound.upper && *bound.lower==*bound.upper)r.equality(row,*bound.upper);
        else {
            if(bound.upper)r.inequality(row,*bound.upper);
            if(bound.lower) {for(auto& v:row)v=-v;r.inequality(row,-*bound.lower);}
        }
    }
    return r;
}
RelationRows relation_rows(const sets::SetData& relation) {
    const auto representation=relation.representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h) throw std::logic_error("Strategy B extraction requires its retained H-relation artifact");
    RelationRows rows{h->inequalities.cols()};
    for(std::size_t i=0;i<h->inequalities.rows();++i) {
        Vector row(h->inequalities.cols());
        for(std::size_t j=0;j<row.size();++j)row[j]=h->inequalities(i,j);
        rows.inequality(row,h->upper_bounds[i]);
    }
    for(std::size_t i=0;i<h->equalities.rows();++i) {
        Vector row(h->equalities.cols());
        for(std::size_t j=0;j<row.size();++j)row[j]=h->equalities(i,j);
        rows.equality(row,h->equality_values[i]);
    }
    return rows;
}
void optimal_level(RelationRows& rows,const JointProgram& p,const Vector& anchor) {
    const auto width=p.constraints.cols;
    auto add=[&](const Vector& row) {double rhs=0;for(std::size_t j=0;j<width;++j)rhs+=row[j]*anchor[j];rows.equality(row,rhs);};
    // For a true optimizer a on convex C: quadratic argmin is
    // C intersect {Hz=Ha,q'z=q'a}; residual-norm argmin fixes Lz=La.
    // Neither formula asserts that a numerical anchor is a true optimizer.
    std::visit([&](const auto& c) {
        using T=std::decay_t<decltype(c)>;
        if constexpr(std::is_same_v<T,LinearTerminal>) add(c.coefficients);
        else if constexpr(std::is_same_v<T,QuadraticTerminal>) {
            for(std::size_t i=0;i<width;++i) {Vector row(width);for(std::size_t j=0;j<width;++j)row[j]=c.Q.values[i*width+j]/2+c.Q.values[j*width+i]/2;add(row);}
            add(c.linear);
        } else {
            for(std::size_t i=0;i<c.map.rows;++i) {Vector row(width);for(std::size_t j=0;j<width;++j)row[j]=c.map.values[i*width+j];add(row);}
        }
    },p.lifted_objective);
}
RequestProvenance scope(const ProgramIdentity& id,const registry::Provenance& provenance) {
    RequestProvenance r{{id.program.value},provenance.port,provenance.requested.id,provenance.requested.version,{},{}};
    if(provenance.actual){r.actual_module=provenance.actual->id;r.actual_version=provenance.actual->version;}return r;
}
RetainedEvidenceScope retained(const SynthesisResult& r) {
    return {r.objective.lower.has_value(),r.objective.upper.has_value(),r.incumbents.size(),r.family.has_value()};
}
}
namespace detail {
class DirectJointExecutionRunner final : public SynthesisWorkspace, public registry::detail::RuntimeReceiptSource {
    registry::PreparedProvider<registry::LPPort> lp_;
    registry::PreparedProvider<registry::ConvexPort> convex_;
    std::optional<registry::StrategyRequest> prepared_request_;
    std::optional<registry::StrategyRegistration::CompleteFamilyVerifierKey> verifier_binding_;
    std::optional<registry::detail::StrategyBRuntimeLineageReceipt> receipt_;
public:
    DirectJointExecutionRunner(registry::PreparedProvider<registry::LPPort> lp,
        registry::PreparedProvider<registry::ConvexPort> convex,
        std::optional<registry::StrategyRequest> prepared_request={},
        std::optional<registry::StrategyRegistration::CompleteFamilyVerifierKey> verifier_binding={})
        :lp_(std::move(lp)),convex_(std::move(convex)),prepared_request_(std::move(prepared_request)),
         verifier_binding_(std::move(verifier_binding)){}
    SynthesisResult solve(const problem::ResolvedProblem&,const FamilyRequest&,const ExecutionContext&) override;
    std::optional<registry::detail::StrategyBRuntimeLineageReceipt> take_runtime_receipt() noexcept override {
        return std::exchange(receipt_,std::nullopt);
    }
};
}
SynthesisResult DirectJointWorkspace::solve(const problem::ResolvedProblem& p,const FamilyRequest& request,const ExecutionContext& context) {
    detail::DirectJointExecutionRunner runner{lp_,convex_};
    return runner.solve(p,request,context);
}
SynthesisResult detail::DirectJointExecutionRunner::solve(const problem::ResolvedProblem& p,const FamilyRequest& request,const ExecutionContext& context) {
    receipt_.reset();
    SynthesisResult result{Termination::completed,{p.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},{},{},{},{},{}};
    auto reject=[&](Diagnostics diagnostics,Termination termination) {
        result.termination=termination;
        if(termination==Termination::contract_rejected) {
            result.stop=ContractValidationFailure{std::move(diagnostics),retained(result),std::monostate{}};
            return;
        }
        result.stop=ScopedRequestRejection{
            {{"syn04-admission:"+p.identity().value},"strategy",{strategy_id},{},ModuleId{strategy_id},strategy_version},std::move(diagnostics),{},retained(result)};
    };
    auto d=capabilities(p,request);
    if(!d.empty()) {const bool unsupported_request=std::all_of(d.begin(),d.end(),[](const Diagnostic& error){return error.code==DiagnosticCode::unsupported;});
        reject(std::move(d),unsupported_request?Termination::operation_rejected:Termination::contract_rejected);return result;}
    const bool reviewed_ts01=registry::detail::ts01_case_valid(p,request,h_polyhedron);
    if(context.numerical!=request.numerical) {reject({{DiagnosticCode::evidence_mismatch,"joint.numerical","Execution numerical policy must equal the effective family request."}},Termination::contract_rejected);return result;}
    if(context.cancellation.stop_requested() || (context.deadline && std::chrono::steady_clock::now()>=*context.deadline)) {
        const auto reason=context.cancellation.stop_requested()?StopReason::cancelled:StopReason::deadline_expired;
        result.termination=stopped_termination(reason);
        result.stop=ScopedOperationStopped{{reason,"Stopped before joint program construction."},
            {{"syn04-build:"+p.identity().value},"strategy",{strategy_id},{},ModuleId{strategy_id},strategy_version},retained(result)};return result;
    }
    auto built=build_joint_program(p,request);
    if(const auto* failure=std::get_if<Diagnostics>(&built)) {reject(*failure,Termination::contract_rejected);return result;}
    if(const auto* stop=std::get_if<OperationStopped>(&built)) {
        result.termination=stopped_termination(stop->reason);
        result.stop=ScopedOperationStopped{*stop,{{"syn04-build:"+p.identity().value},"strategy",{strategy_id},{},ModuleId{strategy_id},strategy_version},retained(result)};return result;
    }
    auto construction=std::get<JointProgram>(std::move(built));
    auto build_artifact=std::make_shared<const JointProgram>(std::move(construction));
    auto rows=feasible_rows(*build_artifact);
    if(request.materialization_limit && rows.inequalities.rows+rows.equalities.rows>*request.materialization_limit) {
        result.termination=Termination::resource_limit;
        result.stop=ScopedOperationStopped{{StopReason::resource_limit,"Feasible relation exceeds the caller's row materialization limit."},
            {{"syn04-materialization:"+p.identity().value},"strategy",{strategy_id},{},ModuleId{strategy_id},strategy_version},retained(result)};
        return result;
    }
    const SetId feasible_id{"syn04-feasible:"+p.identity().value};
    auto initial=rows.finish(feasible_id);
    if(const auto* errors=std::get_if<Diagnostics>(&initial)){reject(*errors,Termination::contract_rejected);return result;}
    auto feasible_artifact=std::make_shared<const sets::SetData>(std::get<sets::SetData>(std::move(initial)));
    auto data=std::make_shared<DirectJointPayload>(*build_artifact,*feasible_artifact);
    std::vector<TransformStepIdentity> lineage{{{"syn04-build:"+p.identity().value},{p.identity().value},feasible_id,{strategy_id},strategy_version}};
    const bool reviewed_ts02=registry::detail::ts02_case_valid(p,request,h_polyhedron);
    if(reviewed_ts02&&request.target==FamilyTarget::exact_optimal_relation) {
        auto canonical=rows.finish({"ts02-optimal-histories"},{"x0","x1","x2","u0","u1"});
        if(const auto* errors=std::get_if<Diagnostics>(&canonical)) {reject(*errors,Termination::contract_rejected);return result;}
        auto relation=std::make_shared<const synthesis::Ts02ConstantIntegratorRelation>(
            std::get<sets::SetData>(std::move(canonical)));
        const FamilyIdentity identity{p.identity(),request,build_artifact->coordinates,{strategy_id},strategy_version,lineage};
        const SymbolicArgument derivation{"T-S02 exact constant-objective derivation",
            "For x0=0, x1=x0+u0, x2=x1+u1 and u0,u1 in [0,1], every feasible history has terminal objective 3. Therefore the argmin relation is exactly the full feasible joint-history polyhedron."};
        const ClaimEvidence claim{p.identity(),derivation};const ObjectiveBound bound{3,claim};
        CompleteOptimalFamily complete{{build_artifact->coordinates,request.representation,relation},
            {claim,{bound,bound}},
            {identity,RegisteredCompletenessEvidence{{synthesis::ts02_constant_integrator_verifier},"1",
                synthesis::ts02_constant_integrator_proof}},Assurance::numerical};
        result.outcome={p.identity(),MathematicalOutcome::optimal,derivation,{}};
        result.objective={bound,bound};result.complete_proposal=CompleteFamilyProposal{identity,std::move(complete)};
        if(prepared_request_&&verifier_binding_&&prepared_request_->problem.identity()==p.identity()&&
            prepared_request_->family==request&&prepared_request_->configuration.strategy.value==strategy_id&&
            prepared_request_->strategy_version==strategy_version&&
            registry::detail::strategy_b_ts02_profile_valid(p,*prepared_request_)) {
            receipt_=registry::detail::StrategyBRuntimeLineageReceipt{*prepared_request_,build_artifact,
                feasible_artifact,feasible_artifact,feasible_artifact,*verifier_binding_};
        }
        return result;
    }
    auto publish=[&] {
        // An unbounded generated program has no optimal-history family to
        // publish. The mapped outcome is retained separately with an explicit
        // unvalidated transformation caveat below.
        if(result.outcome.value==MathematicalOutcome::unbounded) {
            result.family.reset();
            result.complete_proposal.reset();
            result.partial_proposal.reset();
            return;
        }
        FamilyIdentity identity{p.identity(),request,build_artifact->coordinates,{strategy_id},strategy_version,lineage};
        CandidateFeasibility feasibility=Unestablished{};
        if(!result.incumbents.empty()) feasibility=WitnessFeasibilityEvidence{result.incumbents.front().witness,result.incumbents.front().feasibility};
        CandidateFamily candidate{{build_artifact->coordinates,request.representation,data},
            HeuristicRelationEvidence{"binary64 full joint feasible/optimal-level relation; program/problem equivalence and optimal coverage unestablished"},std::move(feasibility)};
        auto family=FamilyPublisher::publish(std::move(identity),std::move(candidate));
        if(const auto* errors=std::get_if<Diagnostics>(&family)) {
            data->diagnostics=*errors;result.termination=Termination::contract_rejected;
            result.stop=ContractValidationFailure{*errors,retained(result),std::monostate{}};return;
        }
        result.family=std::get<OptimalFamily>(std::move(family));
    };
    publish();
    std::shared_ptr<const sets::SetData> extracted_artifact;
    auto run_program=[&]<class Program,class Port>(const Program& program,const registry::PreparedProvider<Port>& provider) {
        data->provider=provider.provenance();const auto provenance=scope(program.identity(),provider.provenance());
        auto preparation=provider.prepare(program);
        if(const auto* rejection=std::get_if<registry::Rejection>(&preparation)) {
            result.termination=Termination::operation_rejected;data->diagnostics=rejection->diagnostics;
            result.stop=ScopedRequestRejection{scope(program.identity(),rejection->provenance),rejection->diagnostics,lineage,retained(result)};return;
        }
        if(context.cancellation.stop_requested() || (context.deadline && std::chrono::steady_clock::now()>=*context.deadline)) {
            const auto reason=context.cancellation.stop_requested()?StopReason::cancelled:StopReason::deadline_expired;
            result.termination=stopped_termination(reason);result.stop=ScopedOperationStopped{{reason,"Stopped before admitted generated program execution."},provenance,retained(result)};return;
        }
        auto workers=std::get<registry::PreparedPipeline<Port>>(std::move(preparation)).create();
        auto outcome=std::get<0>(workers)->run(context);
        if(const auto* unsupported_result=std::get_if<Unsupported>(&outcome)) {
            result.termination=Termination::operation_rejected;data->diagnostics=unsupported_result->diagnostics;
            result.stop=ScopedRequestRejection{provenance,data->diagnostics,lineage,retained(result)};return;
        }
        auto solved=std::get<ProgramResult>(std::move(outcome));auto errors=optimization::check_program_result(solved,program,request.assurance);
        if(!errors.empty()) {
            data->diagnostics=errors;result.termination=Termination::contract_rejected;
            result.stop=ContractValidationFailure{errors,retained(result),ScopedRequestRejection{provenance,errors,lineage,retained(result)}};return;
        }
        result.termination=solved.termination;data->optimization=std::move(solved);
        const auto& evidence=*data->optimization;
        if(evidence.termination==Termination::completed&&evidence.outcome.value==MathematicalOutcome::unbounded) {
            result.outcome={p.identity(),MathematicalOutcome::unbounded,Unestablished{}, {
                "Source generated program: "+evidence.outcome.subject.program.value+".",
                "Transfer from generated-program unboundedness to the resolved problem is not independently validated."
            }};
            // A finite lower bound contradicts unboundedness. Any feasible
            // incumbent found below may still provide a valid upper bound.
            result.objective.lower.reset();
        }
        if(evidence.termination==Termination::completed&&evidence.outcome.value==MathematicalOutcome::infeasible) {
            result.outcome={p.identity(),MathematicalOutcome::infeasible,Unestablished{}, {
                "Source generated program: "+evidence.outcome.subject.program.value+".",
                "Transfer from generated-program infeasibility to the resolved problem is not independently validated."
            }};
            result.objective={};
        }
        if(evidence.termination==Termination::completed&&evidence.outcome.value==MathematicalOutcome::infimum_not_attained) {
            result.outcome={p.identity(),MathematicalOutcome::infimum_not_attained,Unestablished{}, {
                "Source generated program: "+evidence.outcome.subject.program.value+".",
                "Transfer from generated-program nonattainment to the resolved problem is not independently validated."
            }};
            // A finite lower bound combined with a feasible candidate at that
            // value would contradict nonattainment; retain only witness-scoped
            // upper bounds established independently for the source problem.
            result.objective.lower.reset();
        }
        if(evidence.primal) {
            const auto& anchor=*evidence.primal;const auto coordinates=build_artifact->coordinates;
            Witness witness{p.identity(),{},{},0};const auto n=coordinates.dimensions.state,m=coordinates.dimensions.control,T=coordinates.horizon;
            for(std::size_t t=0;t<=T;++t)witness.states.emplace_back(anchor.begin()+t*n,anchor.begin()+(t+1)*n);
            for(std::size_t t=0;t<T;++t)witness.controls.emplace_back(anchor.begin()+(T+1)*n+t*m,anchor.begin()+(T+1)*n+(t+1)*m);
            const auto cost=optimization::evaluate(p.objective(),witness.states.back());
            if(const auto* value=std::get_if<double>(&cost)) {
                witness.original_objective=*value;verification::TrajectoryRequest q;q.witness=witness;
                const auto checked=verification::verify_trajectory(p,q,context);
                if(checked.termination!=Termination::completed) {
                    data->diagnostics=checked.diagnostics;
                    StopReason reason=StopReason::numerical_failure;
                    if(context.cancellation.stop_requested())reason=StopReason::cancelled;
                    else if(context.deadline && std::chrono::steady_clock::now()>=*context.deadline)reason=StopReason::deadline_expired;
                    else if(checked.termination==Termination::resource_limit)reason=StopReason::resource_limit;
                    result.termination=stopped_termination(reason);
                    result.stop=ScopedOperationStopped{{reason,"Original-problem anchor verification stopped; program evidence and feasible candidate retained."},provenance,retained(result)};
                }
                if(checked.bindings==verification::CheckStatus::numerical_pass && checked.feasibility==verification::CheckStatus::numerical_pass && checked.objective==verification::CheckStatus::numerical_pass) {
                    double residual=0;for(const auto& r:checked.residuals)residual=std::max(residual,r.measure.violation);
                    const ClaimEvidence feasibility{p.identity(),NumericalCheck{request.numerical.absolute_tolerance,request.numerical.relative_tolerance,residual,checked.verifier.id}};
                    result.incumbents.push_back({witness,feasibility});
                    // Numerical witness-scoped upper bound only; backend lower
                    // bounds stay in the program-scoped retained payload.
                    result.objective.upper=ObjectiveBound{*value,feasibility};
                    if(evidence.outcome.value==MathematicalOutcome::optimal) {
                        auto optimal=relation_rows(*feasible_artifact);optimal_level(optimal,*build_artifact,anchor);
                        if(request.materialization_limit && optimal.inequalities.rows+optimal.equalities.rows>*request.materialization_limit) {
                            result.termination=Termination::resource_limit;data->diagnostics={unsupported("joint.materialization","Optimal-level relation exceeds caller row limit; feasible candidate and evidence retained.")};
                            result.stop=ScopedOperationStopped{{StopReason::resource_limit,data->diagnostics.front().explanation},provenance,retained(result)};
                        } else {
                            const SetId id{"syn04-optimal-level:"+p.identity().value};auto refined=optimal.finish(id);
                            if(const auto* failures=std::get_if<Diagnostics>(&refined)) {
                                result.termination=Termination::numerical_failure;data->diagnostics=*failures;
                                result.stop=ScopedOperationStopped{{StopReason::numerical_failure,"Optimal-level arithmetic failed; feasible candidate retained."},provenance,retained(result)};
                            } else {
                                auto extracted=std::get<sets::SetData>(std::move(refined));
                                data->relation=extracted;
                                extracted_artifact=std::make_shared<const sets::SetData>(std::move(extracted));
                                lineage.push_back({{"syn04-extract:"+p.identity().value},feasible_id,id,{strategy_id},strategy_version});
                            }
                        }
                    }
                } else data->diagnostics=checked.diagnostics;
            }
        }
        publish();
        if(evidence.termination!=Termination::completed && std::holds_alternative<std::monostate>(result.stop)) {
            StopReason reason=StopReason::numerical_failure;
            if(evidence.termination==Termination::cancelled)reason=StopReason::cancelled;
            if(evidence.termination==Termination::resource_limit)reason=StopReason::resource_limit;
            result.stop=ScopedOperationStopped{{reason,evidence.raw_diagnostics},provenance,retained(result)};
        }
    };
    std::visit([&]<class Program>(const Program& program) {
        if constexpr(std::is_same_v<Program,LinearProgram>) run_program(program,lp_);
        else run_program(program,convex_);
    },build_artifact->program);
    if(reviewed_ts01) {
        const bool completed_extraction=lineage==::csl::synthesis::strategy_b::detail::expected_ts01_lineage(p.identity());
        const bool supported_optimum=data->optimization&&data->optimization->termination==Termination::completed&&
            data->optimization->outcome.value==MathematicalOutcome::optimal&&result.incumbents.size()==1&&
            result.incumbents.front().witness.original_objective==0&&result.objective.upper&&result.objective.upper->value==0;
        if(completed_extraction&&supported_optimum&&result.termination==Termination::completed) {
            auto relation=synthesis::strategy_ts01::ExactJointRelation::canonical();
            if(const auto* errors=std::get_if<Diagnostics>(&relation)) {
                result.termination=Termination::contract_rejected;
                result.stop=ContractValidationFailure{*errors,retained(result),std::monostate{}};
                return result;
            }
            auto payload=std::get<std::shared_ptr<const synthesis::strategy_ts01::ExactJointRelation>>(std::move(relation));
            const FamilyIdentity identity{p.identity(),request,build_artifact->coordinates,{strategy_id},strategy_version,lineage};
            const SymbolicArgument derivation{"T-S01 exact analytic derivation",
                "x2=u0+u1 and (x2-1)^2>=0; zero is attained exactly when u0+u1=1. With u0,u1 in [0,1], the full canonical optimal history relation is the segment (0,s,1,s,1-s), s in [0,1]."};
            const ClaimEvidence optimum{p.identity(),derivation};
            const ObjectiveBound bound{0,{p.identity(),derivation}};
            const OptimumEvidence optimum_evidence{optimum,{bound,bound}};
            CompleteOptimalFamily complete{{build_artifact->coordinates,request.representation,payload},optimum_evidence,
                {identity,RegisteredCompletenessEvidence{{"csl.verifier.ts01-analytic"},"1","TS01-analytic-v1"}},Assurance::numerical};
            if(prepared_request_&&verifier_binding_&&extracted_artifact&&prepared_request_->problem.identity()==p.identity()&&
                prepared_request_->family==request&&prepared_request_->configuration.strategy.value==strategy_id&&
                prepared_request_->strategy_version==strategy_version&&
                registry::detail::strategy_b_ts01_profile_valid(p,*prepared_request_)) {
                receipt_=registry::detail::StrategyBRuntimeLineageReceipt{*prepared_request_,build_artifact,
                    feasible_artifact,feasible_artifact,std::move(extracted_artifact),*verifier_binding_};
            }
            result.outcome={p.identity(),MathematicalOutcome::optimal,derivation,{}};
            result.objective=optimum_evidence.bounds;
            result.complete_proposal=CompleteFamilyProposal{identity,std::move(complete)};
        } else if(result.termination==Termination::completed) {
            result.termination=Termination::operation_rejected;
            result.stop=ScopedRequestRejection{{{"syn04-ts01-coverage:"+p.identity().value},"strategy",{strategy_id},
                std::string(strategy_version),ModuleId{strategy_id},strategy_version},
                {unsupported("joint.ts01","T-S01 requires a completed direct program, optimal-level extraction and independently feasible zero-cost anchor.")},
                lineage,retained(result)};
        }
    }
    return result;
}
registry::StrategyRegistration make_registration(const registry::Registry<registry::LPPort>& lp,const registry::Registry<registry::ConvexPort>& convex) {
    const registry::StrategyRegistration::CompleteFamilyVerifierKey verifier_binding{{complete_verifier_id},complete_verifier_version};
    registry::StrategyRegistration registration{{{strategy_id},strategy_version},[](const registry::StrategyRequest& request,const registry::Requirements& requirements)->registry::Capability {
        auto d=capabilities(request.problem,request.family);
        if(request.configuration.representation!=request.family.representation)
            d.push_back({DiagnosticCode::evidence_mismatch,"joint.configuration.representation","Strategy representation must equal the effective family representation."});
        if(requirements.scalar!=registry::Scalar::binary64)d.push_back(unsupported("joint.scalar","Only binary64 construction is available."));
        if(!d.empty())return d;
        const bool complete=request.family.target==FamilyTarget::exact_optimal_relation;
        return registry::Offer{{request.family.representation,Assurance::numerical,
            complete?SetRelation::equivalent:SetRelation::heuristic,request.family.target,
            complete?registry::Completeness::established:registry::Completeness::unestablished}};
    },[&lp,&convex,verifier_binding](const registry::StrategyRequest& request,const registry::Requirements&)->std::variant<registry::StrategyPlan,registry::Rejection> {
        auto selected_verifier=verifier_binding;
        if(request.family.profile==synthesis::ts02_constant_integrator_profile&&
            request.family.target==FamilyTarget::exact_optimal_relation)
            selected_verifier={{synthesis::ts02_constant_integrator_verifier},"1"};
        registry::Requirements program_requirements;program_requirements.output.representation={"csl.program-result.v1"};
        program_requirements.output.assurance=request.family.assurance;
        auto generated=registry::check_providers(registry::select_provider(lp,registry::Method{request.configuration.lp,{}},program_requirements),
            registry::select_provider(convex,registry::Method{request.configuration.convex,{}},program_requirements));
        if(const auto* failure=std::get_if<registry::Rejection>(&generated))return *failure;
        auto fixed=registry::check_pipeline();
        return registry::compose_strategy(std::get<registry::CheckedPipeline<>>(std::move(fixed)),
            std::get<registry::CheckedProviders<registry::LPPort,registry::ConvexPort>>(std::move(generated)),
            [selected_verifier](auto,auto providers,const registry::StrategyRequest& prepared,const registry::Requirements&)->std::unique_ptr<SynthesisWorkspace> {
                return std::make_unique<detail::DirectJointExecutionRunner>(std::get<0>(std::move(providers)),
                    std::get<1>(std::move(providers)),prepared,selected_verifier);
            });
    },verifier_binding};
    registration.complete_family_verifier_selector=[](const registry::StrategyRequest& request)
        ->std::optional<registry::StrategyRegistration::CompleteFamilyVerifierKey> {
        if(request.family.target!=FamilyTarget::exact_optimal_relation)return std::nullopt;
        if(request.family.profile==synthesis::strategy_ts01::profile_id)
            return registry::StrategyRegistration::CompleteFamilyVerifierKey{{"csl.verifier.ts01-analytic"},"1"};
        if(request.family.profile==synthesis::ts02_constant_integrator_profile)
            return registry::StrategyRegistration::CompleteFamilyVerifierKey{{synthesis::ts02_constant_integrator_verifier},"1"};
        return std::nullopt;
    };
    registration.expected_lineage=[](const registry::StrategyRequest& request) {
        if(request.configuration.strategy.value==strategy_id&&
            registry::detail::ts01_case_valid(request.problem,request.family,request.configuration.representation))
            return detail::expected_ts01_lineage(request.problem.identity());
        if(request.configuration.strategy.value==strategy_id&&
            registry::detail::ts02_case_valid(request.problem,request.family,request.configuration.representation))
            return detail::expected_ts02_lineage(request.problem.identity());
        return std::vector<TransformStepIdentity>{};
    };
    return registration;
}
} // namespace csl::synthesis::strategy_b
