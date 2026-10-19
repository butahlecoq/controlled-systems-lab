#include <csl/geometry/zonotope_reduction.hpp>
#include <csl/sets/generator_sets.hpp>
#include "../exact_dyadic.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <numeric>
#include <unordered_set>

namespace csl::geometry::approximation {
namespace {
Diagnostics unsupported(std::string field,const char* reason) {
    return {{DiagnosticCode::unsupported,std::move(field),reason}};
}
bool stopped(const ExecutionContext& context) {
    return context.cancellation.stop_requested() ||
        (context.deadline && std::chrono::steady_clock::now()>=*context.deadline);
}
OperationStopped stop(const ExecutionContext& context) {
    return {context.cancellation.stop_requested()?StopReason::cancelled:StopReason::deadline_expired,
        "Zonotope reduction stopped before publishing a set."};
}
bool capacity(std::size_t rows,std::size_t cols) {
    return rows==0 || (cols<=std::numeric_limits<std::size_t>::max()/rows &&
        rows*cols<=Vector{}.max_size());
}
std::variant<sets::GeneratorSet,Diagnostics> input_set(const SetHandle& handle) {
    return sets::from_generator_handle(handle);
}
GeometryEvidence evidence(const GeometryRequestIdentity& identity,const SetId& input,
                          std::string title,std::string argument,
                          std::vector<std::string> assumptions) {
    return {{identity,{input}},GeometryClaimScope::set_relation,
        SymbolicArgument{std::move(title),std::move(argument)},
        std::move(assumptions),{}};
}
registry::Capability common_capability(Assurance assurance,const registry::Requirements& requirements,
                                       const SetHandle& input,const SetId& output_id,
                                       const RepresentationId& output) {
    if(assurance!=Assurance::numerical || requirements.output.assurance!=Assurance::numerical ||
       requirements.scalar!=registry::Scalar::binary64)
        return unsupported("zonotope.assurance","Only binary64 numerical assurance is available.");
    if(output.value!="csl.zonotope" || requirements.output.representation!=output)
        return unsupported("zonotope.output","A native unconstrained zonotope output is required.");
    if(output_id.value.empty())
        return unsupported("zonotope.id","The output set ID must be nonempty.");
    auto native=input_set(input);
    if(const auto* errors=std::get_if<Diagnostics>(&native))return *errors;
    return registry::Offer{};
}
registry::Capability zero_capability(const ConversionRequest& request,
                                     const registry::Requirements& requirements,
                                     const SetId& output_id) {
    auto common=common_capability(request.assurance,requirements,request.input,output_id,request.output);
    if(!std::holds_alternative<registry::Offer>(common))return common;
    if(requirements.output.relation && *requirements.output.relation!=SetRelation::equivalent)
        return unsupported("zonotope.zero.relation","Exact zero removal is a conversion.");
    const auto native=input_set(request.input);
    const auto& source=std::get<sets::GeneratorSet>(native);
    if(source.equalities().rows!=0)
        return unsupported("zonotope.zero.equalities","Constrained factors need a separate exact elimination proof.");
    registry::Output output;
    output.representation=request.output;
    output.assurance=Assurance::numerical;
    output.relation=SetRelation::equivalent;
    return registry::Offer{output};
}
class ZeroWorkspace final : public RepresentationConverterWorkspace {
    SetId output_id_;
public:
    explicit ZeroWorkspace(SetId output_id):output_id_(std::move(output_id)){}
    SetTransformOutcome convert(const ConversionRequest& request,const ExecutionContext& context) override {
        if(stopped(context))return stop(context);
        auto imported=input_set(request.input);
        if(const auto* errors=std::get_if<Diagnostics>(&imported))return Unsupported{*errors};
        const auto& source=std::get<sets::GeneratorSet>(imported);
        if(source.equalities().rows!=0)
            return Unsupported{unsupported("zonotope.zero.equalities",
                "Constrained factors need a separate exact elimination proof.")};
        const auto dimension=source.center().size(),count=source.factor_ids().size();
        std::vector<std::size_t> retained;
        for(std::size_t factor=0;factor<count;++factor) {
            if(stopped(context))return stop(context);
            bool nonzero=false;
            for(std::size_t row=0;row<dimension;++row)
                nonzero|=source.generators().values[row*count+factor]!=0;
            if(nonzero)retained.push_back(factor);
        }
        if(!capacity(dimension,retained.size()))
            return Unsupported{unsupported("zonotope.zero.capacity","Output matrix exceeds capacity.")};
        sets::GeneratorInput output{output_id_,source.center(),
            {dimension,retained.size(),Vector(dimension*retained.size(),0)},
            {},{0,retained.size(),{}},{},source.coordinate_labels()};
        for(std::size_t column=0;column<retained.size();++column) {
            output.factor_ids.push_back(source.factor_ids()[retained[column]]);
            for(std::size_t row=0;row<dimension;++row)
                output.generators.values[row*retained.size()+column]=
                    source.generators().values[row*count+retained[column]];
        }
        auto built=sets::make_generator_set(std::move(output));
        if(const auto* errors=std::get_if<Diagnostics>(&built))return Unsupported{*errors};
        if(stopped(context))return stop(context);
        auto proof=evidence(request.identity,request.input.id,"zero-generator removal",
            "An unconstrained zero column contributes nothing to any physical point; all retained factor IDs and coefficients are unchanged.",
            {"Physical-set equivalence is for the exact mathematical set defined by stored binary64 coefficients.",
             "No validated rounding or optimizer-family claim is supplied.",
             "input_generators="+std::to_string(count)+"; output_generators="+
                 std::to_string(retained.size())});
        if(auto errors=check_geometry_evidence(proof,request);!errors.empty())
            return Unsupported{std::move(errors)};
        return OperationResult{std::get<sets::GeneratorSet>(std::move(built)).as_handle(),
            SetRelation::equivalent,std::move(proof)};
    }
};
registry::Capability cover_capability(const ApproximationRequest& request,
                                      const registry::Requirements& requirements,
                                      const SetId& output_id) {
    auto common=common_capability(request.assurance,requirements,request.input,output_id,request.output);
    if(!std::holds_alternative<registry::Offer>(common))return common;
    if(request.direction!=SetRelation::outer ||
       requirements.output.relation!=SetRelation::outer)
        return unsupported("zonotope.cover.direction","Only an outer enclosure is offered.");
    registry::Output output;
    output.representation=request.output;
    output.assurance=Assurance::numerical;
    output.relation=SetRelation::outer;
    return registry::Offer{output};
}
std::optional<double> radius(const sets::GeneratorSet& source,
                             const std::vector<bool>& retained,std::size_t row) {
    using namespace detail::exact_detail;
    Integer sum;
    const auto count=source.factor_ids().size();
    for(std::size_t factor=0;factor<count;++factor)
        if(!retained[factor] && !add_dyadic(sum,
            decode(std::abs(source.generators().values[row*count+factor]))))return std::nullopt;
    return outward_binary64(sum);
}
class CoverWorkspace final : public SetApproximatorWorkspace {
    SetId output_id_;
public:
    explicit CoverWorkspace(SetId output_id):output_id_(std::move(output_id)){}
    SetTransformOutcome approximate(const ApproximationRequest& request,
                                     const ExecutionContext& context) override {
        if(stopped(context))return stop(context);
        auto imported=input_set(request.input);
        if(const auto* errors=std::get_if<Diagnostics>(&imported))return Unsupported{*errors};
        const auto& source=std::get<sets::GeneratorSet>(imported);
        const auto dimension=source.center().size(),count=source.factor_ids().size();
        std::vector<std::size_t> order(count);
        std::iota(order.begin(),order.end(),0);
        const auto magnitude=[&](std::size_t factor) {
            double largest=0;
            for(std::size_t row=0;row<dimension;++row)
                largest=std::max(largest,std::abs(source.generators().values[row*count+factor]));
            return largest;
        };
        std::stable_sort(order.begin(),order.end(),[&](std::size_t a,std::size_t b) {
            return magnitude(a)>magnitude(b);
        });
        std::vector<bool> keep(count,false);
        std::vector<double> radii(dimension);
        std::size_t retained_count=0,axis_count=0;
        bool found=false;
        for(std::size_t candidate=std::min(count,request.size_budget);;) {
            if(stopped(context))return stop(context);
            std::fill(keep.begin(),keep.end(),false);
            for(std::size_t factor=0;factor<candidate;++factor)keep[order[factor]]=true;
            axis_count=0;
            bool finite=true;
            for(std::size_t row=0;row<dimension;++row) {
                if(stopped(context))return stop(context);
                const auto bound=radius(source,keep,row);
                if(!bound) { finite=false; break; }
                radii[row]=*bound;
                axis_count+=*bound!=0;
            }
            if(finite && axis_count<=request.size_budget-candidate) {
                retained_count=candidate;
                found=true;
                break;
            }
            if(candidate==0)break;
            --candidate;
        }
        if(!found)
            return Unsupported{unsupported("zonotope.cover.budget",
                "No finite axis enclosure fits the requested generator budget.")};
        const auto output_count=retained_count+axis_count;
        if(!capacity(dimension,output_count))
            return Unsupported{unsupported("zonotope.cover.capacity","Output matrix exceeds capacity.")};
        sets::GeneratorInput output{output_id_,source.center(),
            {dimension,output_count,Vector(dimension*output_count,0)},
            {},{0,output_count,{}},{},source.coordinate_labels()};
        for(std::size_t column=0;column<retained_count;++column) {
            const auto source_column=order[column];
            output.factor_ids.push_back(source.factor_ids()[source_column]);
            for(std::size_t row=0;row<dimension;++row)
                output.generators.values[row*output_count+column]=
                    source.generators().values[row*count+source_column];
        }
        std::unordered_set<std::string> names;
        for(const auto& factor:source.factor_ids())names.insert(factor.value);
        std::size_t axis_column=retained_count;
        for(std::size_t row=0;row<dimension;++row) {
            if(radii[row]==0)continue;
            std::string name="app03-axis/"+output_id_.value+"/"+std::to_string(row);
            while(names.contains(name))name.push_back('_');
            names.insert(name);
            output.factor_ids.push_back({std::move(name)});
            output.generators.values[row*output_count+axis_column]=radii[row];
            ++axis_column;
        }
        auto built=sets::make_generator_set(std::move(output));
        if(const auto* errors=std::get_if<Diagnostics>(&built))return Unsupported{*errors};
        if(stopped(context))return stop(context);
        auto proof=evidence(request.identity,request.input.id,"generator-axis outer cover",
            "Retained factor IDs and columns are unchanged; independent coordinate-axis factors cover the exact sum of absolute omitted stored-binary64 coefficients.",
            {"requested_budget="+std::to_string(request.size_budget)+
                 "; input_generators="+std::to_string(count)+
                 "; retained_generators="+std::to_string(retained_count)+
                 "; output_generators="+std::to_string(output_count),
             source.equalities().rows!=0?"Input factor equalities were relaxed.":
                 "The input had no factor equalities.",
             "Omitted FactorId dependencies were relaxed to independent axis factors; retained IDs are unchanged.",
             "No realizable control witness, complete optimal family, validated rounding bound, or global error bound is supplied."});
        if(auto errors=check_geometry_evidence(proof,request);!errors.empty())
            return Unsupported{std::move(errors)};
        return OperationResult{std::get<sets::GeneratorSet>(std::move(built)).as_handle(),
            SetRelation::outer,std::move(proof)};
    }
};
} // namespace

registry::Registration<registry::ConversionPort> make_zero_generator_removal_registration(SetId output_id) {
    return {{{"csl.geometry.zonotope.zero-removal"},"1.0.0"},
        [output_id](const ConversionRequest& request,const registry::Requirements& requirements) {
            return zero_capability(request,requirements,output_id);
        },
        [output_id](const ConversionRequest&) {
            return std::make_unique<ZeroWorkspace>(output_id);
        }};
}
registry::Registration<registry::ApproximationPort> make_axis_cover_registration(SetId output_id) {
    return {{{"csl.geometry.zonotope.axis-cover"},"1.0.0"},
        [output_id](const ApproximationRequest& request,const registry::Requirements& requirements) {
            return cover_capability(request,requirements,output_id);
        },
        [output_id](const ApproximationRequest&) {
            return std::make_unique<CoverWorkspace>(output_id);
        }};
}
} // namespace csl::geometry::approximation
