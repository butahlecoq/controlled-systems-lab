#include <csl/geometry/generator_adapter.hpp>

#include <csl/geometry/generators.hpp>
#include <csl/numeric/data.hpp>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <unordered_set>

namespace csl::geometry::generators {
namespace {
Diagnostics unsupported(std::string field,std::string reason,
        DiagnosticCode code=DiagnosticCode::unsupported) {
    return {{code,std::move(field),std::move(reason)}};
}
bool stopped(const ExecutionContext& context) {
    return context.cancellation.stop_requested() ||
        (context.deadline && std::chrono::steady_clock::now()>=*context.deadline);
}
OperationStopped stop(const ExecutionContext& context) {
    return {context.cancellation.stop_requested() ? StopReason::cancelled : StopReason::resource_limit,
        "Generator operation stopped before or during binary64 materialization."};
}
std::variant<sets::GeneratorSet,Diagnostics> imported(const SetHandle& handle) {
    return sets::from_generator_handle(handle);
}
bool independent(const sets::GeneratorSet& left,const sets::GeneratorSet& right) {
    std::unordered_set<std::string> ids;
    for(const auto& id:left.factor_ids()) ids.insert(id.value);
    return std::none_of(right.factor_ids().begin(),right.factor_ids().end(),
        [&](const auto& id) {return ids.contains(id.value);});
}
Diagnostics common_admission(Assurance assurance,const registry::Requirements& requirements) {
    if(assurance!=Assurance::numerical || requirements.output.assurance!=Assurance::numerical)
        return unsupported("generators.assurance","Only binary64 numerical assurance is available.");
    if(requirements.scalar!=registry::Scalar::binary64)
        return unsupported("generators.scalar","Only binary64 scalar data are implemented.");
    if(requirements.output.relation && *requirements.output.relation!=SetRelation::equivalent)
        return unsupported("generators.relation","Only a numerical equivalent relation is offered.");
    return {};
}
GeometryEvidence evidence(const GeometryRequestIdentity& identity,std::vector<SetId> inputs,
        std::string argument) {
    return {{identity,std::move(inputs)},GeometryClaimScope::set_relation,
        SymbolicArgument{"generator representation identity",std::move(argument)},
        {"Real-set generator algebra defines the relation; binary64 coefficient evaluation may round.",
         "No validated rounding enclosure, physical-set equality certificate or global error bound is supplied."},
        {}};
}

registry::Capability operation_capability(const OperationRequest& request,
        const registry::Requirements& requirements) {
    if(auto errors=common_admission(request.assurance,requirements);!errors.empty()) return errors;
    if(request.required_relation!=SetRelation::equivalent)
        return unsupported("generators.relation","Only equivalent generator algebra is offered.");
    if(request.identity.ideal_output.value.empty())
        return unsupported("generators.output","Output set identity must be nonempty.",DiagnosticCode::invalid_input);
    if(auto errors=check_operation_shape(request);!errors.empty()) return errors;
    bool constrained=false;
    if(const auto* image=std::get_if<AffineImage>(&request.operation)) {
        const auto input=imported(image->input);
        if(const auto* errors=std::get_if<Diagnostics>(&input)) return *errors;
        constrained=std::get<sets::GeneratorSet>(input).equalities().rows!=0;
        if(!std::all_of(image->map.values.begin(),image->map.values.end(),
                [](double value){return std::isfinite(value);}) ||
           !std::all_of(image->offset.begin(),image->offset.end(),
                [](double value){return std::isfinite(value);}))
            return unsupported("generators.image","Affine map and offset must be finite.",DiagnosticCode::invalid_input);
    } else if(const auto* sum=std::get_if<MinkowskiSum>(&request.operation)) {
        const auto left=imported(sum->left),right=imported(sum->right);
        if(const auto* errors=std::get_if<Diagnostics>(&left)) return *errors;
        if(const auto* errors=std::get_if<Diagnostics>(&right)) return *errors;
        const auto& a=std::get<sets::GeneratorSet>(left);
        const auto& b=std::get<sets::GeneratorSet>(right);
        if(!independent(a,b))
            return unsupported("generators.minkowski.factor_ids",
                "Shared factor IDs denote dependence; independent Minkowski sum is unsupported.");
        if(a.coordinate_labels()!=b.coordinate_labels())
            return unsupported("generators.minkowski.labels",
                "Minkowski inputs require the same ordered coordinate labels.",DiagnosticCode::invalid_input);
        constrained=a.equalities().rows!=0 || b.equalities().rows!=0;
    } else {
        return unsupported("generators.operation",
            "Only affine images and independent Minkowski sums are registered.");
    }
    registry::Output output;
    output.representation={constrained ? "csl.constrained-zonotope" : "csl.zonotope"};
    output.assurance=Assurance::numerical;
    output.relation=SetRelation::equivalent;
    return registry::Offer{output};
}

class OperationWorkspace final : public SetOperatorWorkspace {
    OperationRequest request_;
public:
    explicit OperationWorkspace(OperationRequest request):request_(std::move(request)) {}
    OperationOutcome apply(const OperationRequest&,const ExecutionContext& context) override {
        if(stopped(context)) return stop(context);
        sets::GeneratorResult result=Diagnostics{};
        std::vector<SetId> inputs;
        if(const auto* image=std::get_if<AffineImage>(&request_.operation)) {
            auto input=imported(image->input);
            if(const auto* errors=std::get_if<Diagnostics>(&input)) return Unsupported{*errors};
            result=affine_image(std::get<sets::GeneratorSet>(input),image->map,image->offset,
                {request_.identity.ideal_output.value});
            inputs={image->input.id};
        } else if(const auto* sum=std::get_if<MinkowskiSum>(&request_.operation)) {
            auto left=imported(sum->left),right=imported(sum->right);
            if(const auto* errors=std::get_if<Diagnostics>(&left)) return Unsupported{*errors};
            if(const auto* errors=std::get_if<Diagnostics>(&right)) return Unsupported{*errors};
            result=minkowski_sum(std::get<sets::GeneratorSet>(left),std::get<sets::GeneratorSet>(right),
                {request_.identity.ideal_output.value});
            inputs={sum->left.id,sum->right.id};
        } else return Unsupported{unsupported("generators.operation","Unsupported generator operation.")};
        if(const auto* errors=std::get_if<Diagnostics>(&result)) return Unsupported{*errors};
        if(stopped(context)) return stop(context);
        auto proof=evidence(request_.identity,std::move(inputs),
            "Affine images retain each factor and equality; disjoint-ID Minkowski sums concatenate independent factors and equalities.");
        if(auto errors=check_geometry_evidence(proof,request_);!errors.empty()) return Unsupported{std::move(errors)};
        return OperationResult{std::get<sets::GeneratorSet>(std::move(result)).as_handle(),
            SetRelation::equivalent,std::move(proof)};
    }
};

std::variant<std::size_t,Diagnostics> corner_count(const sets::GeneratorSet& input,
        std::size_t max_vertices) {
    std::size_t count=1;
    if(max_vertices==0) return unsupported("generators.convert.cap","A positive vertex cap is required.");
    for(std::size_t factor=0;factor<input.factor_ids().size();++factor) {
        if(count>max_vertices/2)
            return unsupported("generators.convert.cap","Full cube-corner output exceeds the caller's vertex cap.");
        count*=2;
    }
    const auto dimension=input.center().size();
    if(dimension!=0 && count>std::vector<double>{}.max_size()/dimension)
        return unsupported("generators.convert.capacity","V coordinate storage exceeds container capacity.");
    return count;
}

registry::Capability conversion_capability(const ConversionRequest& request,
        const registry::Requirements& requirements,std::size_t max_vertices) {
    if(auto errors=common_admission(request.assurance,requirements);!errors.empty()) return errors;
    if(request.output.value!="csl.polyhedron.v")
        return unsupported("generators.convert.output","Only explicit finite V output is supported.");
    if(request.identity.ideal_output.value.empty())
        return unsupported("generators.convert.id","Output set identity must be nonempty.",DiagnosticCode::invalid_input);
    auto input=imported(request.input);
    if(const auto* errors=std::get_if<Diagnostics>(&input)) return *errors;
    const auto& set=std::get<sets::GeneratorSet>(input);
    if(set.equalities().rows!=0)
        return unsupported("generators.convert.equalities",
            "Constrained generators require a separate factor-feasibility and projection conversion.");
    if(auto count=corner_count(set,max_vertices);std::holds_alternative<Diagnostics>(count))
        return std::get<Diagnostics>(std::move(count));
    registry::Output output;
    output.representation={"csl.polyhedron.v"};
    output.assurance=Assurance::numerical;
    output.relation=SetRelation::equivalent;
    return registry::Offer{output};
}

class ConversionWorkspace final : public RepresentationConverterWorkspace {
    ConversionRequest request_;
    std::size_t max_vertices_;
public:
    ConversionWorkspace(ConversionRequest request,std::size_t max_vertices)
        :request_(std::move(request)),max_vertices_(max_vertices) {}
    SetTransformOutcome convert(const ConversionRequest&,const ExecutionContext& context) override {
        if(stopped(context)) return stop(context);
        auto input=imported(request_.input);
        if(const auto* errors=std::get_if<Diagnostics>(&input)) return Unsupported{*errors};
        const auto& set=std::get<sets::GeneratorSet>(input);
        auto admitted=corner_count(set,max_vertices_);
        if(const auto* errors=std::get_if<Diagnostics>(&admitted)) return Unsupported{*errors};
        const auto count=std::get<std::size_t>(admitted);
        const auto dimension=set.center().size(),factors=set.factor_ids().size();
        Vector vertices;
        vertices.reserve(count*dimension);
        for(std::size_t vertex=0;vertex<count;++vertex) {
            if(stopped(context)) return stop(context);
            for(std::size_t row=0;row<dimension;++row) {
                double value=set.center()[row];
                for(std::size_t factor=0;factor<factors;++factor)
                    value+=set.generators().values[row*factors+factor]*
                        ((vertex>>factor)&1 ? 1.0 : -1.0);
                if(!std::isfinite(value))
                    return Unsupported{unsupported("generators.convert.arithmetic",
                        "Binary64 cube-corner calculation produced a nonfinite coordinate.")};
                vertices.push_back(value);
            }
        }
        auto points=numeric::snapshot(Matrix{count,dimension,std::move(vertices)});
        auto rays=numeric::snapshot(Matrix{0,dimension,{}});
        if(const auto* error=std::get_if<Diagnostic>(&points)) return Unsupported{{*error}};
        if(const auto* error=std::get_if<Diagnostic>(&rays)) return Unsupported{{*error}};
        auto output=sets::make_v({{request_.identity.ideal_output.value},dimension,set.coordinate_labels()},
            {std::get<numeric::MatrixView>(points),std::get<numeric::MatrixView>(rays)});
        if(const auto* error=std::get_if<Diagnostic>(&output)) return Unsupported{{*error}};
        auto proof=evidence(request_.identity,{request_.input.id},
            "The convex hull of all mapped cube corners equals the unconstrained generator set in real arithmetic; redundant corners remain.");
        proof.assumptions.emplace_back("V materialization loses FactorId dependence metadata; it must not be used to infer independence in later sums.");
        if(auto errors=check_geometry_evidence(proof,request_);!errors.empty()) return Unsupported{std::move(errors)};
        return OperationResult{std::get<sets::SetData>(std::move(output)).as_handle(),
            SetRelation::equivalent,std::move(proof)};
    }
};
} // namespace

registry::Registration<registry::GeometryPort> make_operation_registration() {
    return {{{"csl.geometry.generators.operations"},"1.0.0"},operation_capability,
        [](const OperationRequest& request) {return std::make_unique<OperationWorkspace>(request);}};
}
registry::Registration<registry::ConversionPort> make_v_conversion_registration(
        std::size_t max_vertices) {
    return {{{"csl.geometry.generators.v-conversion"},"1.0.0"},
        [max_vertices](const ConversionRequest& request,const registry::Requirements& requirements) {
            return conversion_capability(request,requirements,max_vertices);
        },
        [max_vertices](const ConversionRequest& request) {
            return std::make_unique<ConversionWorkspace>(request,max_vertices);
        }};
}
} // namespace csl::geometry::generators
