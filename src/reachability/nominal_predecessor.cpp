#include <csl/reachability/nominal_predecessor.hpp>
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <set>

namespace csl::reachability {
namespace {
Diagnostics error(std::string field,std::string explanation,
        DiagnosticCode code=DiagnosticCode::invalid_input) {
    return {{code,std::move(field),std::move(explanation)}};
}
template<class T> T take(std::variant<T,Diagnostic> value) {
    if(auto* failure=std::get_if<Diagnostic>(&value)) throw std::logic_error(failure->explanation);
    return std::get<T>(std::move(value));
}
bool finite(const Vector& values) {
    return std::all_of(values.begin(),values.end(),[](double value){return std::isfinite(value);});
}
bool matrix(const Matrix& value,std::size_t rows,std::size_t columns) {
    return value.rows==rows && value.cols==columns &&
        (!columns || rows<=std::numeric_limits<std::size_t>::max()/columns) &&
        value.values.size()==rows*columns && finite(value.values);
}
struct Row { Vector coefficients;double bound;bool equality; };
std::variant<std::vector<Row>,Diagnostics> rows(const sets::SetData& set) {
    const auto representation=set.representation();const auto n=set.metadata()->set.dimension;
    std::vector<Row> result;
    if(const auto* h=std::get_if<sets::HRepresentation>(&representation)) {
        const auto copy=[&](const numeric::MatrixView& values,const numeric::VectorView& bounds,bool equality) {
            for(std::size_t r=0;r<values.rows();++r) {
                Vector row(n);for(std::size_t c=0;c<n;++c) row[c]=values(r,c);
                result.push_back({std::move(row),bounds[r],equality});
            }
        };
        copy(h->inequalities,h->upper_bounds,false);copy(h->equalities,h->equality_values,true);
    } else if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation)) {
        if(n && n>std::numeric_limits<std::size_t>::max()/n)
            return error("predecessor.capacity","Singleton equality storage overflows size_t.");
        for(std::size_t c=0;c<n;++c) {Vector row(n,0);row[c]=1;result.push_back({std::move(row),singleton->point[c],true});}
    } else if(std::holds_alternative<sets::EmptyRepresentation>(representation)) {
        result.push_back({Vector(n,0),-1,false});
    } else if(!std::holds_alternative<sets::UniversalRepresentation>(representation)) {
        return error("predecessor.representation","Predecessor requires native H, singleton, empty or universal operands; V conversion is separate.",DiagnosticCode::unsupported);
    }
    return result;
}
std::string child_id(const GeometryRequestIdentity& identity,const char* suffix) {
    const auto field=[](const std::string& value){return std::to_string(value.size())+":"+value;};
    return "nominal-predecessor/"+field(identity.problem.value)+field(identity.request.value)+
        field(identity.ideal_output.value)+suffix;
}
}

PreparedNominalPredecessor::PreparedNominalPredecessor(NominalPredecessorRequest request,
        OperationRequest projection,registry::PreparedPipeline<registry::GeometryPort> prepared)
    :request_(std::move(request)),projection_(std::move(projection)),prepared_(std::move(prepared)) {}

NominalPredecessorOutcome PreparedNominalPredecessor::run(const ExecutionContext& context) const {
    const auto selected=prepared_.provenance()[0];
    const RequestProvenance provenance{projection_.identity.request,selected.port,
        selected.requested.id,selected.requested.version,
        selected.actual?std::optional<ModuleId>{selected.actual->id}:std::nullopt,
        selected.actual?std::optional<std::string>{selected.actual->version}:std::nullopt};
    const GeometryReference original{request_.identity,{request_.states.id,request_.controls.id,request_.target.id}};
    const GeometryReference child{projection_.identity,{std::get<Projection>(projection_.operation).input.id}};
    const auto failure=[&](auto cause) -> NominalPredecessorOutcome {
        return NominalPredecessorFailure{original,child,provenance,{},std::move(cause)};
    };
    auto workspace=prepared_.create();
    auto outcome=std::get<0>(workspace)->run(context);
    if(auto* rejected=std::get_if<Unsupported>(&outcome)) return failure(*rejected);
    if(auto* stopped=std::get_if<OperationStopped>(&outcome)) return failure(*stopped);
    auto* operation=std::get_if<OperationResult>(&outcome);
    if(!operation) return failure(Unsupported{error("predecessor.result",
        "Selected projection returned a query result instead of an OperationResult.",DiagnosticCode::evidence_mismatch)});
    auto result=std::move(*operation);
    if(result.relation!=SetRelation::equivalent)
        return failure(Unsupported{error("predecessor.relation","Selected projection did not return the requested equivalent relation.",DiagnosticCode::evidence_mismatch)});
    if(auto errors=check_geometry_evidence(result.evidence,projection_);!errors.empty()) return failure(Unsupported{std::move(errors)});
    if(result.output.metadata.dimension!=request_.states.metadata.dimension)
        return failure(Unsupported{error("predecessor.coordinates","Selected projection changed the state output dimension.",DiagnosticCode::evidence_mismatch)});
    auto source=take(sets::from_handle(request_.states));
    std::vector<std::string> labels;
    if(result.output.metadata.representation.value=="csl.polyhedron.projection") {
        auto data=geometry::polyhedral::inspect_lazy_projection(result.output);
        if(auto* rejected=std::get_if<Diagnostics>(&data)) return failure(Unsupported{*rejected});
        labels=std::get<geometry::polyhedral::LazyProjectionDescription>(data).coordinate_labels;
    } else {
        auto data=sets::from_handle(result.output);
        if(auto* rejected=std::get_if<Diagnostic>(&data)) return failure(Unsupported{{*rejected}});
        labels=std::get<sets::SetData>(data).metadata()->coordinate_labels;
    }
    if(labels!=source.metadata()->coordinate_labels)
        return failure(Unsupported{error("predecessor.coordinates","Selected projection changed the ordered state labels.",DiagnosticCode::evidence_mismatch)});
    result.evidence.reference={request_.identity,{request_.states.id,request_.controls.id,request_.target.id}};
    // The provider's projection theorem/evidence concerns the compiled binary64
    // joint rows. It cannot certify that those rows equal the authored dynamics
    // pullback over reals. Never upgrade the original predecessor claim.
    result.evidence.support=Unestablished{};result.evidence.error_bound.reset();
    result.evidence.assumptions.push_back("existential controls: project joint [x,u] constrained by X, U and A*x+B*u+a in S; no inverse A");
    result.evidence.assumptions.push_back("joint target-row pullback uses binary64 arithmetic; original predecessor support remains unestablished");
    if(provenance.actual_module) result.evidence.assumptions.push_back("projection provider="+provenance.actual_module->value+"@"+*provenance.actual_version);
    std::vector<std::size_t> coordinates(request_.states.metadata.dimension);
    std::iota(coordinates.begin(),coordinates.end(),std::size_t{0});
    return NominalPredecessorResult{std::move(result),provenance,projection_.identity,std::move(coordinates)};
}

NominalPredecessorPreparation prepare_nominal_predecessor(const NominalPredecessorRequest& request,
        const registry::PreparedProvider<registry::GeometryPort>& provider) {
    if(request.identity.problem.value.empty() || request.identity.request.value.empty() || request.identity.ideal_output.value.empty())
        return error("predecessor.identity","Complete immutable predecessor identity required.");
    if(request.required_relation!=SetRelation::equivalent || request.assurance!=Assurance::numerical)
        return error("predecessor.guarantee","Only equivalent operations with unestablished numerical support are implemented.",DiagnosticCode::unsupported);
    auto x=sets::from_handle(request.states),u=sets::from_handle(request.controls),s=sets::from_handle(request.target);
    for(const auto* imported:{&x,&u,&s})
        if(const auto* failure=std::get_if<Diagnostic>(imported)) return Diagnostics{*failure};
    const auto states=std::get<sets::SetData>(std::move(x));
    const auto controls=std::get<sets::SetData>(std::move(u));
    const auto target=std::get<sets::SetData>(std::move(s));
    const auto n=states.metadata()->set.dimension,m=controls.metadata()->set.dimension;
    if(target.metadata()->set.dimension!=n || !matrix(request.A,n,n) || !matrix(request.B,n,m) ||
            request.offset.size()!=n || !finite(request.offset))
        return error("predecessor.dynamics","Finite A[n,n], B[n,m], offset[n] and n-dimensional target required.");
    if(states.metadata()->coordinate_labels!=target.metadata()->coordinate_labels)
        return error("predecessor.coordinates","X and S must name the same ordered state coordinates (or both be unnamed).");
    if(n>std::numeric_limits<std::size_t>::max()-m) return error("predecessor.capacity","Joint dimension overflows size_t.");
    const auto dimension=n+m;
    auto xr=rows(states),ur=rows(controls),sr=rows(target);
    for(const auto* parsed:{&xr,&ur,&sr})
        if(const auto* failure=std::get_if<Diagnostics>(parsed)) return *failure;
    auto state_rows=std::get<std::vector<Row>>(std::move(xr));
    auto control_rows=std::get<std::vector<Row>>(std::move(ur));
    auto target_rows=std::get<std::vector<Row>>(std::move(sr));
    const auto maximum=std::numeric_limits<std::size_t>::max();
    if(state_rows.size()>maximum-control_rows.size() || state_rows.size()+control_rows.size()>maximum-target_rows.size())
        return error("predecessor.capacity","Joint row count overflows size_t.");
    const auto count=state_rows.size()+control_rows.size()+target_rows.size();
    if(dimension && count>maximum/dimension) return error("predecessor.capacity","Joint row storage overflows size_t.");
    Matrix a{0,dimension,{}},e{0,dimension,{}};Vector b,f;
    const auto append=[&](Vector coefficients,double bound,bool equality) {
        auto& destination=equality?e:a;auto& values=equality?f:b;
        ++destination.rows;destination.values.insert(destination.values.end(),coefficients.begin(),coefficients.end());values.push_back(bound);
    };
    for(const auto& row:state_rows) {Vector values(dimension,0);std::copy(row.coefficients.begin(),row.coefficients.end(),values.begin());append(std::move(values),row.bound,row.equality);}
    for(const auto& row:control_rows) {Vector values(dimension,0);std::copy(row.coefficients.begin(),row.coefficients.end(),values.begin()+static_cast<std::ptrdiff_t>(n));append(std::move(values),row.bound,row.equality);}
    for(const auto& row:target_rows) {
        Vector values(dimension,0.0);double bound=row.bound;
        for(std::size_t r=0;r<n;++r) {
            for(std::size_t c=0;c<n;++c) values[c]+=row.coefficients[r]*request.A.values[r*n+c];
            for(std::size_t c=0;c<m;++c) values[n+c]+=row.coefficients[r]*request.B.values[r*m+c];
            bound-=row.coefficients[r]*request.offset[r];
        }
        if(!finite(values)||!std::isfinite(bound)) return error("predecessor.arithmetic","Nonfinite target pullback; no projection workspace created.",DiagnosticCode::unsupported);
        append(std::move(values),bound,row.equality);
    }
    auto labels=states.metadata()->coordinate_labels;
    if(!labels.empty()) {
        std::set<std::string> used(labels.begin(),labels.end());
        for(std::size_t c=0;c<m;++c) {
            std::string label="$control/"+std::to_string(c);
            while(used.contains(label)) label="$"+label;
            used.insert(label);labels.push_back(std::move(label));
        }
    }
    const auto joint=take(sets::make_h({{child_id(request.identity,"/joint")},dimension,std::move(labels)},
        {take(numeric::snapshot(a)),take(numeric::snapshot_vector(b)),take(numeric::snapshot(e)),take(numeric::snapshot_vector(f))}));
    std::vector<std::size_t> coordinates(n);std::iota(coordinates.begin(),coordinates.end(),std::size_t{0});
    if(!provider.provenance().actual) return error("predecessor.provider","Projection provider identity is unresolved.",DiagnosticCode::unsupported);
    OperationRequest projection{{request.identity.problem,{child_id(request.identity,"/project")},
        {child_id(request.identity,"/projected-joint")}},provider.provenance().actual->id,
        Projection{joint.as_handle(),std::move(coordinates)},request.required_relation,request.assurance};
    auto prepared=provider.prepare(projection);
    if(auto* failure=std::get_if<registry::Rejection>(&prepared)) return *failure;
    return PreparedNominalPredecessor{request,projection,
        std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(prepared))};
}
} // namespace csl::reachability
