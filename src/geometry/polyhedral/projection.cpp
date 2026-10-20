#include <csl/geometry/polyhedral_projection.hpp>
#include <algorithm>
#include <cmath>
#include <limits>

namespace csl::geometry::polyhedral {
namespace {
constexpr const char* module="csl.geometry.polyhedral-projection";
constexpr const char* lazy_representation="csl.polyhedron.projection";
struct LazyPayload final : SetPayload {
    SetMetadata metadata;
    SetId id;
    LazyProjectionDescription description;
    LazyPayload(SetMetadata info,SetId identity,LazyProjectionDescription data)
        :metadata(std::move(info)),id(std::move(identity)),description(std::move(data)) {}
};
Diagnostics error(std::string field,std::string explanation,
        DiagnosticCode code=DiagnosticCode::unsupported) {
    return {{code,std::move(field),std::move(explanation)}};
}
bool stopped(const ExecutionContext& c) {
    return c.cancellation.stop_requested() ||
        (c.deadline && std::chrono::steady_clock::now()>=*c.deadline);
}
OperationStopped stop(const ExecutionContext& c) {
    return {c.cancellation.stop_requested()?StopReason::cancelled:StopReason::deadline_expired,
        "Projection interrupted before publishing materialization."};
}
std::string representation(ProjectionOutput output) {
    return output==ProjectionOutput::lazy?lazy_representation:
        output==ProjectionOutput::h?"csl.polyhedron.h":"csl.polyhedron.v";
}
std::variant<LazyProjectionDescription,Diagnostics> native_projection(const Projection& op) {
    if(std::dynamic_pointer_cast<const LazyPayload>(op.input.payload)) {
        auto previous=inspect_lazy_projection(op.input);
        if(auto* failure=std::get_if<Diagnostics>(&previous)) return *failure;
        auto result=std::get<LazyProjectionDescription>(std::move(previous));
        result.lineage.push_back(result.creation_evidence);
        std::vector<std::size_t> coordinates;
        std::vector<std::string> labels;
        for(auto index:op.coordinates) {
            if(index>=result.coordinates.size()) return error("projection.coordinates","Coordinate out of range.",DiagnosticCode::invalid_input);
            coordinates.push_back(result.coordinates[index]);
            if(!result.coordinate_labels.empty()) labels.push_back(result.coordinate_labels[index]);
        }
        result.coordinates=std::move(coordinates);result.coordinate_labels=std::move(labels);
        return result;
    }
    auto imported=sets::from_handle(op.input);
    if(auto* failure=std::get_if<Diagnostic>(&imported)) return Diagnostics{*failure};
    const auto data=std::get<sets::SetData>(std::move(imported));
    std::vector<std::string> labels;
    for(auto index:op.coordinates) {
        if(index>=data.metadata()->set.dimension) return error("projection.coordinates","Coordinate out of range.",DiagnosticCode::invalid_input);
        if(!data.metadata()->coordinate_labels.empty()) labels.push_back(data.metadata()->coordinate_labels[index]);
    }
    return LazyProjectionDescription{op.input,op.coordinates,std::move(labels),
        {{{},{op.input.id}},GeometryClaimScope::set_relation,Unestablished{}, {}, {}}, {}};
}
Diagnostics shape(const OperationRequest& request) {
    if(request.identity.problem.value.empty() || request.identity.request.value.empty() || request.identity.ideal_output.value.empty())
        return error("projection.identity","Complete operation identity is required.",DiagnosticCode::invalid_input);
    if(request.implementation.value!=module)
        return error("projection.implementation","Request must identify the selected projection module.",DiagnosticCode::invalid_input);
    if(!std::holds_alternative<Projection>(request.operation)) return error("projection.operation","Only coordinate projections are implemented.");
    auto errors=check_operation_shape(request);
    if(!errors.empty()) return errors;
    auto sorted=std::get<Projection>(request.operation).coordinates;
    std::sort(sorted.begin(),sorted.end());
    if(std::adjacent_find(sorted.begin(),sorted.end())!=sorted.end())
        return error("projection.coordinates","Coordinate selection must not repeat an index.",DiagnosticCode::invalid_input);
    return {};
}
bool supports(const LazyProjectionDescription& data,ProjectionOutput output) {
    if(output==ProjectionOutput::lazy) return true;
    auto native=sets::from_handle(data.source);
    if(!std::holds_alternative<sets::SetData>(native)) return false;
    auto rep=std::get<sets::SetData>(native).representation();
    if(output==ProjectionOutput::h) return !std::holds_alternative<sets::VRepresentation>(rep);
    return !std::holds_alternative<sets::HRepresentation>(rep) && !std::holds_alternative<sets::UniversalRepresentation>(rep);
}
template<class T> T take(std::variant<T,Diagnostic> value) {
    if(auto* failure=std::get_if<Diagnostic>(&value)) throw std::logic_error(failure->explanation);
    return std::get<T>(std::move(value));
}
SetHandle make_h(const sets::Description& description,const std::vector<Vector>& rows,
        const Vector& bounds,const std::vector<Vector>& equalities,const Vector& values) {
    Matrix a{rows.size(),description.ambient_dimension,{}};
    Matrix e{equalities.size(),description.ambient_dimension,{}};
    for(const auto& row:rows) a.values.insert(a.values.end(),row.begin(),row.end());
    for(const auto& row:equalities) e.values.insert(e.values.end(),row.begin(),row.end());
    return take(sets::make_h(description,{take(numeric::snapshot(a)),take(numeric::snapshot_vector(bounds)),
        take(numeric::snapshot(e)),take(numeric::snapshot_vector(values))})).as_handle();
}
struct Rows { std::vector<Vector> a,e; Vector b,f; };
bool finite(const Vector& row) {
    return std::all_of(row.begin(),row.end(),[](double value){return std::isfinite(value);});
}
bool contradiction(Rows& rows) {
    const auto clean=[](std::vector<Vector>& matrix,Vector& bounds,bool equality) {
        std::size_t kept=0;
        for(std::size_t row=0;row<matrix.size();++row) {
            const bool zero=std::all_of(matrix[row].begin(),matrix[row].end(),[](double value){return value==0.0;});
            if(zero) {if(equality?bounds[row]!=0.0:bounds[row]<0.0) return true;continue;}
            if(kept!=row) matrix[kept]=std::move(matrix[row]);
            bounds[kept++]=bounds[row];
        }
        matrix.resize(kept);bounds.resize(kept);return false;
    };
    return clean(rows.a,rows.b,false)||clean(rows.e,rows.f,true);
}
bool capacity(std::size_t a,std::size_t e,std::size_t dimension,std::optional<std::size_t> limit) {
    const auto maximum=std::numeric_limits<std::size_t>::max();
    return a<=maximum-e && (!limit || a+e<=*limit) && (dimension==0 || a+e<=maximum/dimension);
}
using Materialized=std::variant<SetHandle,Unsupported,OperationStopped>;
Materialized materialize_h(const LazyProjectionDescription& data,SetId id,
        std::optional<std::size_t> limit,const ExecutionContext& context,
        GeometryResourceObservation& observation) {
    const auto source=std::get<sets::SetData>(sets::from_handle(data.source));
    const std::size_t n=source.metadata()->set.dimension;
    const auto rep=source.representation();
    const sets::Description output{std::move(id),data.coordinates.size(),data.coordinate_labels};
    const auto empty=[&]() -> Materialized {
        if(!capacity(1,0,output.ambient_dimension,limit))
            return Unsupported{error("projection.capacity","Empty H encoding exceeds capacity or caller row limit.")};
        observation.peak_rows=std::max<std::size_t>(observation.peak_rows,1);
        observation.peak_matrix_elements=std::max(observation.peak_matrix_elements,
            output.ambient_dimension);
        return make_h(output,{Vector(output.ambient_dimension,0.0)},{-1.0},{},{});
    };
    if(std::holds_alternative<sets::EmptyRepresentation>(rep)) return empty();
    Rows rows;
    if(const auto* h=std::get_if<sets::HRepresentation>(&rep)) {
        if(!capacity(h->inequalities.rows(),h->equalities.rows(),n,limit))
            return Unsupported{error("projection.capacity","Input H rows exceed capacity or caller admission limit.")};
        const auto copy=[&](const numeric::MatrixView& matrix,const numeric::VectorView& bounds,
                std::vector<Vector>& destination,Vector& values) {
            for(std::size_t r=0;r<matrix.rows();++r) {
                Vector row(n);
                for(std::size_t c=0;c<n;++c) row[c]=matrix(r,c);
                destination.push_back(std::move(row));values.push_back(bounds[r]);
            }
        };
        copy(h->inequalities,h->upper_bounds,rows.a,rows.b);copy(h->equalities,h->equality_values,rows.e,rows.f);
    } else if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&rep)) {
        if(!capacity(0,n,n,limit)) return Unsupported{error("projection.capacity","Singleton equality storage exceeds capacity or caller limit.")};
        for(std::size_t c=0;c<n;++c) {Vector row(n,0.0);row[c]=1;rows.e.push_back(std::move(row));rows.f.push_back(singleton->point[c]);}
    }
    const auto observe_rows=[&](std::size_t additional_rows) {
        const auto maximum=std::numeric_limits<std::size_t>::max();
        if(rows.a.size()>maximum-rows.e.size()) return false;
        const auto live_rows=rows.a.size()+rows.e.size();
        if(live_rows>maximum-additional_rows) return false;
        const auto peak_rows=live_rows+additional_rows;
        if(n!=0&&peak_rows>maximum/n) return false;
        observation.peak_rows=std::max(observation.peak_rows,peak_rows);
        observation.peak_matrix_elements=std::max(observation.peak_matrix_elements,peak_rows*n);
        return true;
    };
    if(!observe_rows(0))
        return Unsupported{error("projection.capacity","Projection resource observation overflows size_t.")};
    if(contradiction(rows)) return empty();
    std::vector<bool> keep(n,false);
    for(auto index:data.coordinates) keep[index]=true;
    for(std::size_t k=0;k<n;++k) {
        if(keep[k]) continue;
        if(stopped(context)) return stop(context);
        std::optional<std::size_t> pivot;
        for(std::size_t r=0;r<rows.e.size();++r)
            if(rows.e[r][k]!=0.0 && (!pivot || std::abs(rows.e[r][k])>std::abs(rows.e[*pivot][k]))) pivot=r;
        if(pivot) {
            if(!observe_rows(1))
                return Unsupported{error("projection.capacity","Projection resource observation overflows size_t.")};
            const auto equation=rows.e[*pivot];const double value=rows.f[*pivot];
            rows.e.erase(rows.e.begin()+static_cast<std::ptrdiff_t>(*pivot));rows.f.erase(rows.f.begin()+static_cast<std::ptrdiff_t>(*pivot));
            const auto substitute=[&](std::vector<Vector>& matrix,Vector& bounds) {
                for(std::size_t r=0;r<matrix.size();++r) {
                    if(matrix[r][k]==0.0) continue;
                    const double ratio=matrix[r][k]/equation[k];
                    if(!std::isfinite(ratio)) return false;
                    for(std::size_t c=0;c<n;++c) if(c!=k) matrix[r][c]-=ratio*equation[c];
                    matrix[r][k]=0.0;bounds[r]-=ratio*value;
                    if(!finite(matrix[r]) || !std::isfinite(bounds[r])) return false;
                }
                return true;
            };
            if(!substitute(rows.a,rows.b)||!substitute(rows.e,rows.f))
                return Unsupported{error("projection.arithmetic","Nonfinite equality substitution; no set published.")};
        } else {
            std::vector<std::size_t> positive,negative,zero;
            for(std::size_t r=0;r<rows.a.size();++r) (rows.a[r][k]>0.0?positive:rows.a[r][k]<0.0?negative:zero).push_back(r);
            const auto maximum=std::numeric_limits<std::size_t>::max();
            if(!negative.empty() && positive.size()>(maximum-zero.size())/negative.size())
                return Unsupported{error("projection.capacity","Fourier--Motzkin row count overflows size_t.")};
            const auto count=zero.size()+positive.size()*negative.size();
            if(!capacity(count,rows.e.size(),n,limit))
                return Unsupported{error("projection.capacity","Fourier--Motzkin intermediate rows exceed capacity or caller limit.")};
            if(observation.generated_rows>maximum-count||
               (!negative.empty()&&positive.size()>maximum/negative.size())||
               observation.charged_elimination_operations>maximum-positive.size()*negative.size()||
               !observe_rows(count))
                return Unsupported{error("projection.capacity","Projection resource observation overflows size_t.")};
            observation.generated_rows+=count;
            observation.charged_elimination_operations+=positive.size()*negative.size();
            std::vector<Vector> combined;Vector bounds;combined.reserve(count);bounds.reserve(count);
            for(auto r:zero) {combined.push_back(rows.a[r]);bounds.push_back(rows.b[r]);}
            for(auto p:positive) for(auto m:negative) {
                if(stopped(context)) return stop(context);
                const double positive_scale=rows.a[p][k],negative_scale=-rows.a[m][k];
                Vector row(n,0.0);
                for(std::size_t c=0;c<n;++c) if(c!=k) row[c]=rows.a[p][c]/positive_scale+rows.a[m][c]/negative_scale;
                const double bound=rows.b[p]/positive_scale+rows.b[m]/negative_scale;
                if(!finite(row)||!std::isfinite(bound)) return Unsupported{error("projection.arithmetic","Nonfinite Fourier--Motzkin arithmetic; no set published.")};
                combined.push_back(std::move(row));bounds.push_back(bound);
            }
            rows.a=std::move(combined);rows.b=std::move(bounds);
            if(!observe_rows(0))
                return Unsupported{error("projection.capacity","Projection resource observation overflows size_t.")};
        }
        if(contradiction(rows)) return empty();
    }
    const auto select=[&](std::vector<Vector>& matrix) {
        for(auto& row:matrix) {Vector selected;for(auto index:data.coordinates) selected.push_back(row[index]);row=std::move(selected);}
    };
    select(rows.a);select(rows.e);return make_h(output,rows.a,rows.b,rows.e,rows.f);
}
Materialized materialize_v(const LazyProjectionDescription& data,SetId id,const ExecutionContext& context) {
    const auto source=std::get<sets::SetData>(sets::from_handle(data.source));const auto rep=source.representation();
    const auto n=data.coordinates.size();Matrix vertices{0,n,{}},rays{0,n,{}};
    if(const auto* v=std::get_if<sets::VRepresentation>(&rep)) {
        vertices.rows=v->vertices.rows();rays.rows=v->rays.rows();
        if(!capacity(vertices.rows,rays.rows,n,{})) return Unsupported{error("projection.capacity","Projected V storage overflows size_t.")};
        const auto select=[&](const numeric::MatrixView& input,Matrix& output) {
            for(std::size_t r=0;r<input.rows();++r) {if(stopped(context)) return false;for(auto index:data.coordinates) output.values.push_back(input(r,index));}
            return true;
        };
        if(!select(v->vertices,vertices)||!select(v->rays,rays)) return stop(context);
    } else if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&rep)) {
        vertices.rows=1;for(auto index:data.coordinates) vertices.values.push_back(singleton->point[index]);
    }
    return take(sets::make_v({std::move(id),n,data.coordinate_labels},{take(numeric::snapshot(vertices)),take(numeric::snapshot(rays))})).as_handle();
}
GeometryEvidence evidence(GeometryReference reference,const ExecutionContext& context,bool numerical) {
    EvidenceSupport support=SymbolicArgument{"Coordinate projection of conv(V)+cone(R), or retained existential projection",
        "Coordinate selection copies generators; lazy projection retains its immutable source without elimination."};
    (void)context;
    if(numerical) support=Unestablished{};
    return {std::move(reference),GeometryClaimScope::set_relation,std::move(support),
        {"ordered selected coordinates retained; affine dimension is not inferred",
         numerical?"binary64 equality substitution and Fourier--Motzkin elimination; set-relation support remains unestablished; no exact arithmetic, inclusion, coverage or error-bound certificate":
            "generator copying or lazy retention introduces no arithmetic conversion",
         "H materialization preserves equalities; V materialization preserves every ray including zero images"}, {}};
}
OperationOutcome execute(LazyProjectionDescription data,GeometryReference reference,SetId id,
        ProjectionOptions options,const ExecutionContext& context) {
    if(stopped(context)) return stop(context);
    if(!std::isfinite(context.numerical.absolute_tolerance)||context.numerical.absolute_tolerance<0 ||
            !std::isfinite(context.numerical.relative_tolerance)||context.numerical.relative_tolerance<0)
        return Unsupported{error("projection.numerical","Finite nonnegative caller tolerances required.",DiagnosticCode::invalid_input)};
    auto claim=evidence(std::move(reference),context,options.output==ProjectionOutput::h);
    if(!supports(data,options.output)) return Unsupported{error("projection.representation","Unsupported native input/output pair.")};
    for(const auto& prior:data.lineage)
        claim.assumptions.push_back("prior projection request="+prior.reference.identity.request.value);
    if(!data.creation_evidence.reference.identity.request.value.empty())
        claim.assumptions.push_back("retained lazy projection request="+data.creation_evidence.reference.identity.request.value);
    if(options.output==ProjectionOutput::lazy) {
        SetMetadata info{data.coordinates.size(),{lazy_representation},SetProperty::yes,SetProperty::yes,
            data.source.metadata.bounded==SetProperty::yes || data.coordinates.empty()?SetProperty::yes:SetProperty::unknown};
        data.creation_evidence=claim;auto payload=std::make_shared<const LazyPayload>(info,id,std::move(data));
        return OperationResult{{info,payload,std::move(id)},SetRelation::equivalent,std::move(claim)};
    }
    std::optional<GeometryResourceObservation> resource_observation;
    Materialized materialized;
    if(options.output==ProjectionOutput::h) {
        resource_observation.emplace();
        materialized=materialize_h(data,std::move(id),options.max_rows,context,
            *resource_observation);
    } else {
        materialized=materialize_v(data,std::move(id),context);
    }
    if(auto* failure=std::get_if<Unsupported>(&materialized)) return *failure;
    if(auto* failure=std::get_if<OperationStopped>(&materialized)) return *failure;
    if(stopped(context)) return stop(context);
    return OperationResult{std::get<SetHandle>(std::move(materialized)),SetRelation::equivalent,
        std::move(claim),std::move(resource_observation)};
}
class ProjectionWorkspace final : public SetOperatorWorkspace {
    ProjectionOptions options_;
public:
    explicit ProjectionWorkspace(ProjectionOptions options):options_(options) {}
    OperationOutcome apply(const OperationRequest& request,const ExecutionContext& context) override {
        if(auto failures=shape(request);!failures.empty()) return Unsupported{std::move(failures)};
        const auto& projection=std::get<Projection>(request.operation);auto description=native_projection(projection);
        if(auto* failure=std::get_if<Diagnostics>(&description)) return Unsupported{*failure};
        return execute(std::get<LazyProjectionDescription>(std::move(description)),{request.identity,{projection.input.id}},
            {request.identity.ideal_output.value},options_,context);
    }
};
class MaterializerWorkspace final : public RepresentationConverterWorkspace {
    std::optional<std::size_t> limit_;
public:
    explicit MaterializerWorkspace(std::optional<std::size_t> limit):limit_(limit) {}
    SetTransformOutcome convert(const ConversionRequest& request,const ExecutionContext& context) override {
        if(request.identity.problem.value.empty() || request.identity.request.value.empty() || request.identity.ideal_output.value.empty())
            return Unsupported{error("projection.identity","Complete immutable materialization identity required.",DiagnosticCode::invalid_input)};
        if(request.output.value!="csl.polyhedron.h" && request.output.value!="csl.polyhedron.v")
            return Unsupported{error("projection.representation","Only H or V materialization is implemented.")};
        auto data=inspect_lazy_projection(request.input);
        if(auto* failure=std::get_if<Diagnostics>(&data)) return Unsupported{*failure};
        const auto output=request.output.value=="csl.polyhedron.h"?ProjectionOutput::h:ProjectionOutput::v;
        auto result=execute(std::get<LazyProjectionDescription>(std::move(data)),{request.identity,{request.input.id}},
            {request.identity.ideal_output.value},{output,limit_},context);
        if(auto* success=std::get_if<OperationResult>(&result)) return *success;
        if(auto* failure=std::get_if<Unsupported>(&result)) return *failure;
        return std::get<OperationStopped>(std::move(result));
    }
};
} // namespace

std::variant<LazyProjectionDescription,Diagnostics> inspect_lazy_projection(const SetHandle& handle) {
    const auto payload=std::dynamic_pointer_cast<const LazyPayload>(handle.payload);
    if(!payload) return error("projection.payload","Input is not this module's lazy projection.");
    const auto& actual=handle.metadata;const auto& expected=payload->metadata;
    if(handle.id!=payload->id || actual.dimension!=expected.dimension || actual.representation.value!=expected.representation.value ||
            actual.convex!=expected.convex || actual.polyhedral!=expected.polyhedral || actual.bounded!=expected.bounded)
        return error("projection.metadata","Lazy envelope does not match immutable payload.",DiagnosticCode::invalid_input);
    return payload->description;
}
registry::Registration<registry::GeometryPort> make_projection_registration(ProjectionOptions options) {
    return {{{module},"1.0.0"},
        [options](const OperationRequest& request,const registry::Requirements& requirements) -> registry::Capability {
            if(auto failures=shape(request);!failures.empty()) return failures;
            if(request.assurance!=Assurance::numerical || requirements.output.assurance!=Assurance::numerical)
                return error("projection.assurance","Validated projection assurance is not implemented.");
            if(request.required_relation!=SetRelation::equivalent || (requirements.output.relation && *requirements.output.relation!=SetRelation::equivalent))
                return error("projection.relation","This adapter offers equivalent numerical relations only.");
            auto data=native_projection(std::get<Projection>(request.operation));
            if(auto* failure=std::get_if<Diagnostics>(&data)) return *failure;
            if(!supports(std::get<LazyProjectionDescription>(data),options.output))
                return error("projection.representation","Selected output requires native H or V input; cross H/V conversion is separate.");
            registry::Output output;output.representation={representation(options.output)};output.relation=SetRelation::equivalent;
            return registry::Offer{output};
        },[options](const OperationRequest&) {return std::make_unique<ProjectionWorkspace>(options);}};
}
registry::Registration<registry::ConversionPort> make_projection_materializer(std::optional<std::size_t> limit) {
    return {{{"csl.geometry.projection-materializer"},"1.0.0"},
        [](const ConversionRequest& request,const registry::Requirements& requirements) -> registry::Capability {
            if(request.identity.problem.value.empty() || request.identity.request.value.empty() || request.identity.ideal_output.value.empty())
                return error("projection.identity","Complete immutable materialization identity required.",DiagnosticCode::invalid_input);
            if(request.assurance!=Assurance::numerical || requirements.output.assurance!=Assurance::numerical)
                return error("projection.assurance","Validated materialization assurance is not implemented.");
            if(request.output.value!="csl.polyhedron.h" && request.output.value!="csl.polyhedron.v")
                return error("projection.representation","Only native H or V materialization is supported.");
            auto data=inspect_lazy_projection(request.input);
            if(auto* failure=std::get_if<Diagnostics>(&data)) return *failure;
            if(!supports(std::get<LazyProjectionDescription>(data),request.output.value=="csl.polyhedron.h"?ProjectionOutput::h:ProjectionOutput::v))
                return error("projection.representation","Cross H/V materialization requires a separate converter.");
            registry::Output output;output.representation=request.output;output.relation=SetRelation::equivalent;
            return registry::Offer{output};
        },[limit](const ConversionRequest&) {return std::make_unique<MaterializerWorkspace>(limit);}};
}
ProjectionMaterializationOutcome materialize_lazy_projection(const ConversionRequest& request,
        const registry::PreparedProvider<registry::ConversionPort>& provider,const ExecutionContext& context) {
    const auto& selected=provider.provenance();
    const RequestProvenance provenance{request.identity.request,selected.port,selected.requested.id,
        selected.requested.version,selected.actual?std::optional<ModuleId>{selected.actual->id}:std::nullopt,
        selected.actual?std::optional<std::string>{selected.actual->version}:std::nullopt};
    std::vector<GeometryEvidence> lineage;
    std::vector<std::size_t> coordinates;
    const auto failure=[&](auto cause) -> ProjectionMaterializationOutcome {
        return ProjectionMaterializationFailure{{request.identity,{request.input.id}},provenance,
            lineage,coordinates,std::move(cause)};
    };
    auto description=inspect_lazy_projection(request.input);
    if(auto* errors=std::get_if<Diagnostics>(&description)) return failure(Unsupported{*errors});
    const auto& data=std::get<LazyProjectionDescription>(description);
    lineage=data.lineage;lineage.push_back(data.creation_evidence);coordinates=data.coordinates;
    auto admission=provider.prepare(request);
    if(auto* rejected=std::get_if<registry::Rejection>(&admission)) return failure(Unsupported{rejected->diagnostics});
    auto prepared=std::get<registry::PreparedPipeline<registry::ConversionPort>>(std::move(admission));
    auto outcome=std::get<0>(prepared.create())->run(context);
    if(auto* stopped_result=std::get_if<OperationStopped>(&outcome)) return failure(*stopped_result);
    if(auto* rejected=std::get_if<Unsupported>(&outcome)) return failure(*rejected);
    auto result=std::get<OperationResult>(std::move(outcome));
    if(result.relation!=SetRelation::equivalent)
        return failure(Unsupported{error("projection.materialization.relation","Materializer returned a different relation.",DiagnosticCode::evidence_mismatch)});
    if(auto errors=check_geometry_evidence(result.evidence,request);!errors.empty()) return failure(Unsupported{std::move(errors)});
    if(result.output.metadata.dimension!=coordinates.size() || result.output.metadata.representation.value!=request.output.value)
        return failure(Unsupported{error("projection.materialization.coordinates","Materializer changed requested output schema.",DiagnosticCode::evidence_mismatch)});
    auto native=sets::from_handle(result.output);
    if(auto* rejected=std::get_if<Diagnostic>(&native)) return failure(Unsupported{{*rejected}});
    if(std::get<sets::SetData>(native).metadata()->coordinate_labels!=data.coordinate_labels)
        return failure(Unsupported{error("projection.materialization.coordinates","Materializer changed ordered output labels.",DiagnosticCode::evidence_mismatch)});
    return ProjectionMaterializationResult{std::move(result),provenance,std::move(lineage),std::move(coordinates)};
}
} // namespace csl::geometry::polyhedral
