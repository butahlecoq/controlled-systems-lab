#include <csl/geometry/approximation.hpp>
#include <csl/execution/instrumented_operation.hpp>
#include <csl/geometry/ellipsoidal.hpp>
#include <csl/sets/data.hpp>
#include <csl/sets/generator_sets.hpp>
#include "../exact_dyadic.hpp"

#include <cmath>
#include <chrono>
#include <unordered_map>

namespace csl::geometry::approximation {
namespace {
namespace ar=artifacts;
namespace ob=execution::observability;
template<class Outcome> Termination approximation_termination(const Outcome& outcome) noexcept {
    if(std::holds_alternative<Unsupported>(outcome))return Termination::operation_rejected;
    if(const auto* stopped=std::get_if<OperationStopped>(&outcome)) {
        switch(stopped->reason) {
        case StopReason::cancelled:case StopReason::deadline_expired:return Termination::cancelled;
        case StopReason::resource_limit:return Termination::resource_limit;
        case StopReason::numerical_failure:return Termination::numerical_failure;
        }
        return Termination::numerical_failure;
    }
    return Termination::completed;
}
ar::ModuleIdentity provider_identity(const registry::Identity& identity) {
    return {identity.id,identity.version,ar::Unavailable{ar::MissingReason::not_instrumented,{}}};
}
ob::OperationSpanIdentity approximation_identity(const ApproximationRequest& request,
        const registry::Provenance& provenance) {
    return {request.identity.request.value,"geometry.approximation.provider-call",
        provenance.actual?provider_identity(*provenance.actual):provider_identity(
            registry::Identity{provenance.requested.id,"unknown"}),
        {},{},{},{}};
}
ob::OperationSpanIdentity requested_approximation_identity(const ApproximationRequest& request,
        const registry::Method& method) {
    return {request.identity.request.value,"geometry.approximation.provider-call",
        provider_identity({method.id,method.version.value_or(std::string{})}),{},{},{},{}};
}
Diagnostics error(DiagnosticCode code, const char* field, const char* message) {
    return {{code,field,message}};
}
bool same_metadata(const SetMetadata& left,const SetMetadata& right) {
    return left.dimension==right.dimension && left.representation==right.representation &&
        left.convex==right.convex && left.polyhedral==right.polyhedral && left.bounded==right.bounded;
}
bool has_constraint_rows(const numeric::MatrixView& required_rows,
                         const numeric::VectorView& required_values,
                         const numeric::MatrixView& available_rows,
                         const numeric::VectorView& available_values) {
    for(std::size_t required=0;required<required_rows.rows();++required) {
        bool found=false;
        for(std::size_t available=0;available<available_rows.rows()&&!found;++available) {
            if(required_values[required]!=available_values[available])continue;
            bool same=true;
            for(std::size_t column=0;column<required_rows.cols();++column)
                if(required_rows(required,column)!=available_rows(available,column)) {
                    same=false;
                    break;
                }
            found=same;
        }
        if(!found)return false;
    }
    return true;
}
bool h_constraints_contained(const sets::HRepresentation& required,
                             const sets::HRepresentation& available) {
    // Every additional authored constraint can only shrink the defined set.
    // Compare stored finite coefficients; do not infer algebraic equivalence.
    return has_constraint_rows(required.inequalities,required.upper_bounds,
               available.inequalities,available.upper_bounds) &&
           has_constraint_rows(required.equalities,required.equality_values,
               available.equalities,available.equality_values);
}
bool h_rows_contain_point(const numeric::MatrixView& rows,
                          const numeric::VectorView& values,
                          const numeric::VectorView& point,bool equality) {
    using namespace detail::exact_detail;
    for(std::size_t row=0;row<rows.rows();++row) {
        Integer difference;
        for(std::size_t column=0;column<rows.cols();++column) {
            const double coefficient=rows(row,column),coordinate=point[column];
            if(!std::isfinite(coefficient)||!std::isfinite(coordinate)||
               !add_product(difference,decode(coefficient),decode(coordinate)))return false;
        }
        if(!std::isfinite(values[row]))return false;
        auto bound=decode(values[row]);bound.negative=!bound.negative;
        if(!add_dyadic(difference,bound))return false;
        if(equality?!is_zero(difference):(!difference.negative&&!is_zero(difference)))return false;
    }
    return true;
}
bool h_contains_point(const sets::HRepresentation& h,const sets::SingletonRepresentation& point) {
    return h_rows_contain_point(h.inequalities,h.upper_bounds,point.point,false) &&
           h_rows_contain_point(h.equalities,h.equality_values,point.point,true);
}
bool h_rows_contain_v(const numeric::MatrixView& rows,const numeric::VectorView& values,
                      const sets::VRepresentation& v,bool equality,
                      const ExecutionContext& context,bool& interrupted) {
    using namespace detail::exact_detail;
    for(std::size_t row=0;row<rows.rows();++row) {
        for(std::size_t member=0;member<v.vertices.rows()+v.rays.rows();++member) {
            if(context.cancellation.stop_requested() ||
               (context.deadline && std::chrono::steady_clock::now()>=*context.deadline)) {
                interrupted=true;
                return false;
            }
            const bool ray=member>=v.vertices.rows();
            const auto& points=ray?v.rays:v.vertices;
            const auto index=ray?member-v.vertices.rows():member;
            Integer difference;
            for(std::size_t column=0;column<rows.cols();++column) {
                if(context.cancellation.stop_requested() ||
                   (context.deadline && std::chrono::steady_clock::now()>=*context.deadline)) {
                    interrupted=true;
                    return false;
                }
                const double coefficient=rows(row,column),coordinate=points(index,column);
                if(!std::isfinite(coefficient)||!std::isfinite(coordinate)||
                   !add_product(difference,decode(coefficient),decode(coordinate)))return false;
            }
            if(!ray) {
                if(!std::isfinite(values[row]))return false;
                auto bound=decode(values[row]);bound.negative=!bound.negative;
                if(!add_dyadic(difference,bound))return false;
            }
            if(equality?!is_zero(difference):(!difference.negative&&!is_zero(difference)))return false;
        }
    }
    return true;
}
bool h_contains_v(const sets::HRepresentation& h,const sets::VRepresentation& v,
                  const ExecutionContext& context,bool& interrupted) {
    return h_rows_contain_v(h.inequalities,h.upper_bounds,v,false,context,interrupted) &&
           h_rows_contain_v(h.equalities,h.equality_values,v,true,context,interrupted);
}
bool generator_axis_cover(const sets::GeneratorSet& source,const sets::GeneratorSet& output,
                          const ExecutionContext& context,bool& interrupted) {
    using namespace detail::exact_detail;
    if(source.center()!=output.center() ||
       source.coordinate_labels()!=output.coordinate_labels() ||
       output.equalities().rows!=0)return false;
    const auto dimension=source.center().size();
    const auto source_count=source.factor_ids().size();
    const auto output_count=output.factor_ids().size();
    std::unordered_map<std::string,std::size_t> source_positions;
    for(std::size_t factor=0;factor<source_count;++factor)
        source_positions.emplace(source.factor_ids()[factor].value,factor);
    std::vector<bool> retained(source_count,false);
    std::vector<bool> new_axis(output_count,false);
    for(std::size_t factor=0;factor<output_count;++factor) {
        if(context.cancellation.stop_requested() ||
           (context.deadline && std::chrono::steady_clock::now()>=*context.deadline)) {
            interrupted=true;
            return false;
        }
        const auto found=source_positions.find(output.factor_ids()[factor].value);
        if(found!=source_positions.end()) {
            retained[found->second]=true;
            for(std::size_t row=0;row<dimension;++row) {
                if(context.cancellation.stop_requested() ||
                   (context.deadline && std::chrono::steady_clock::now()>=*context.deadline)) {
                    interrupted=true;
                    return false;
                }
                if(output.generators().values[row*output_count+factor]!=
                   source.generators().values[row*source_count+found->second])return false;
            }
        } else {
            std::size_t nonzero=0;
            for(std::size_t row=0;row<dimension;++row) {
                if(context.cancellation.stop_requested() ||
                   (context.deadline && std::chrono::steady_clock::now()>=*context.deadline)) {
                    interrupted=true;
                    return false;
                }
                nonzero+=output.generators().values[row*output_count+factor]!=0;
            }
            if(nonzero>1)return false;
            new_axis[factor]=true;
        }
    }
    for(std::size_t row=0;row<dimension;++row) {
        if(context.cancellation.stop_requested() ||
           (context.deadline && std::chrono::steady_clock::now()>=*context.deadline)) {
            interrupted=true;
            return false;
        }
        Integer required,available;
        for(std::size_t factor=0;factor<source_count;++factor) {
            if(context.cancellation.stop_requested() ||
               (context.deadline && std::chrono::steady_clock::now()>=*context.deadline)) {
                interrupted=true;
                return false;
            }
            if(!retained[factor] && !add_dyadic(required,
                decode(std::abs(source.generators().values[row*source_count+factor]))))return false;
        }
        for(std::size_t factor=0;factor<output_count;++factor) {
            if(context.cancellation.stop_requested() ||
               (context.deadline && std::chrono::steady_clock::now()>=*context.deadline)) {
                interrupted=true;
                return false;
            }
            if(new_axis[factor] && !add_dyadic(available,
                decode(std::abs(output.generators().values[row*output_count+factor]))))return false;
        }
        if(compare_magnitude(required,available)>0)return false;
    }
    return true;
}
bool v_ellipsoid_cover(const sets::VRepresentation& source,
                       const ellipsoidal::EllipsoidSet& output,
                       const ExecutionContext& context,bool& interrupted) {
    using namespace detail::exact_detail;
    if(source.vertices.rows()==0 || source.rays.rows()!=0)return false;
    for(std::size_t vertex=0;vertex<source.vertices.rows();++vertex) {
        for(std::size_t row=0;row<2;++row) {
            if(context.cancellation.stop_requested() ||
               (context.deadline && std::chrono::steady_clock::now()>=*context.deadline)) {
                interrupted=true;
                return false;
            }
            Integer projection,limit;
            for(std::size_t coordinate=0;coordinate<2;++coordinate) {
                const auto coefficient=decode(output.orientation().values[row*2+coordinate]);
                if(!add_product(projection,coefficient,
                     decode(source.vertices(vertex,coordinate))))return false;
                auto negative_center=decode(output.center()[coordinate]);
                negative_center.negative=!negative_center.negative;
                if(!add_product(projection,coefficient,negative_center))return false;
            }
            projection.negative=false;
            if(!add_dyadic(limit,decode(output.projected_bounds()[row])) ||
               compare_magnitude(projection,limit)>0)return false;
        }
    }
    return true;
}
std::optional<StructuralBasis> structural_basis(const ApproximationRequest& request,
                                                 const OperationResult& result,
                                                 const ExecutionContext& context,bool& interrupted) {
    if(request.input.id==result.output.id && request.input.payload==result.output.payload &&
       same_metadata(request.input.metadata,result.output.metadata))
        return StructuralBasis::identical_set;
    const auto reference=sets::from_handle(request.input);
    const auto native=sets::from_handle(result.output);
    if(request.direction==SetRelation::outer) {
        const auto imported=ellipsoidal::from_ellipsoid_handle(result.output);
        if(const auto* source=std::get_if<sets::SetData>(&reference))
            if(const auto* ellipse=std::get_if<ellipsoidal::EllipsoidSet>(&imported))
                if(source->metadata()->coordinate_labels==ellipse->coordinate_labels()) {
                    const auto representation=source->representation();
                    if(const auto* v=std::get_if<sets::VRepresentation>(&representation))
                        if(v_ellipsoid_cover(*v,*ellipse,context,interrupted))
                            return StructuralBasis::v_ellipsoid_containment;
                }
    }
    if(request.direction==SetRelation::outer) {
        const auto source=sets::from_generator_handle(request.input);
        const auto output=sets::from_generator_handle(result.output);
        if(const auto* source_set=std::get_if<sets::GeneratorSet>(&source))
            if(const auto* output_set=std::get_if<sets::GeneratorSet>(&output))
                if(generator_axis_cover(*source_set,*output_set,context,interrupted))
                    return StructuralBasis::generator_axis_cover;
    }
    if(const auto* source=std::get_if<sets::SetData>(&reference);
       source && std::holds_alternative<sets::SetData>(native) &&
       source->metadata()->coordinate_labels==
           std::get<sets::SetData>(native).metadata()->coordinate_labels) {
        const auto* data=std::get_if<sets::SetData>(&native);
        const auto representation=data->representation();
        const auto reference_representation=source->representation();
        if(request.direction==SetRelation::inner)
            if(const auto* reference_h=std::get_if<sets::HRepresentation>(&reference_representation))
                if(const auto* output_point=std::get_if<sets::SingletonRepresentation>(&representation))
                    if(h_contains_point(*reference_h,*output_point))
                        return StructuralBasis::h_point_containment;
        if(request.direction==SetRelation::outer)
            if(const auto* reference_point=std::get_if<sets::SingletonRepresentation>(&reference_representation))
                if(const auto* output_h=std::get_if<sets::HRepresentation>(&representation))
                    if(h_contains_point(*output_h,*reference_point))
                        return StructuralBasis::h_point_containment;
        if(const auto* reference_h=std::get_if<sets::HRepresentation>(&reference_representation))
            if(const auto* output_h=std::get_if<sets::HRepresentation>(&representation)) {
                const auto& required=request.direction==SetRelation::inner?*reference_h:*output_h;
                const auto& available=request.direction==SetRelation::inner?*output_h:*reference_h;
                if(h_constraints_contained(required,available))
                    return StructuralBasis::h_constraint_containment;
            }
        if(request.direction==SetRelation::outer)
            if(const auto* reference_v=std::get_if<sets::VRepresentation>(&reference_representation))
                if(const auto* output_h=std::get_if<sets::HRepresentation>(&representation))
                    if(h_contains_v(*output_h,*reference_v,context,interrupted))
                        return StructuralBasis::v_h_containment;
        if(request.direction==SetRelation::inner)
            if(const auto* reference_h=std::get_if<sets::HRepresentation>(&reference_representation))
                if(const auto* output_v=std::get_if<sets::VRepresentation>(&representation))
                    if(h_contains_v(*reference_h,*output_v,context,interrupted))
                        return StructuralBasis::h_v_containment;
        if(request.direction==SetRelation::inner &&
            (std::holds_alternative<sets::EmptyRepresentation>(representation) ||
             (std::holds_alternative<sets::VRepresentation>(representation) &&
              std::get<sets::VRepresentation>(representation).vertices.rows()==0)))
            return StructuralBasis::empty_subset;
        if(request.direction==SetRelation::outer &&
            std::holds_alternative<sets::UniversalRepresentation>(representation))
            return StructuralBasis::universal_superset;
    }
    return std::nullopt;
}
bool within_budget(const SetHandle& output,std::size_t budget) {
    if(std::holds_alternative<ellipsoidal::EllipsoidSet>(
        ellipsoidal::from_ellipsoid_handle(output)))return budget>=1;
    const auto generator=sets::from_generator_handle(output);
    if(const auto* set=std::get_if<sets::GeneratorSet>(&generator))
        return set->factor_ids().size()<=budget;
    const auto native=sets::from_handle(output);
    const auto* data=std::get_if<sets::SetData>(&native);
    if(!data)return false;
    const auto representation=data->representation();
    if(const auto* h=std::get_if<sets::HRepresentation>(&representation))
        return h->inequalities.rows()<=budget &&
            h->equalities.rows()<=budget-h->inequalities.rows();
    if(const auto* v=std::get_if<sets::VRepresentation>(&representation))
        return v->vertices.rows()<=budget && v->rays.rows()<=budget-v->vertices.rows();
    if(std::holds_alternative<sets::SingletonRepresentation>(representation))return budget>=1;
    return true; // Empty and universal have no stored primitives.
}
registry::Rejection reject(const registry::Method& method,const char* field,const char* message) {
    return {{registry::ApproximationPort::name,method,{}},error(DiagnosticCode::unsupported,field,message)};
}
}

RunOutcome run_registered(const registry::Registry<registry::ApproximationPort>& registry,
                          registry::Method method,const ApproximationRequest& request,
                          const ExecutionContext& context) {
    if(request.direction==SetRelation::equivalent)
    {
        ob::InstrumentedOperation observation{context,requested_approximation_identity(request,method)};
        observation.not_called(ar::NotCalledReason::capability_rejected);
        return reject(method,"approximation.direction","Equivalent conversion belongs to ConversionPort.");
    }
    if(request.identity.problem.value.empty() || request.identity.request.value.empty() ||
       request.identity.ideal_output.value.empty() || request.input.id.value.empty() ||
       !request.input.payload || request.output.value.empty())
        return reject(method,"approximation.request","A complete reference, input and output representation are required.");
    registry::Requirements requirements;
    requirements.output.representation=request.output;
    requirements.output.assurance=request.assurance;
    requirements.output.relation=request.direction;
    auto prepared=registry::prepare_pipeline(registry::select(registry,method,request,requirements));
    if(const auto* rejected=std::get_if<registry::Rejection>(&prepared)) {
        ob::InstrumentedOperation observation{context,
            requested_approximation_identity(request,rejected->provenance.requested)};
        observation.not_called(ar::NotCalledReason::capability_rejected);
        return *rejected;
    }
    auto pipeline=std::get<registry::PreparedPipeline<registry::ApproximationPort>>(std::move(prepared));
    const auto provenance=pipeline.provenance().front();
    auto workspace=pipeline.create();
    auto outcome=ob::run_instrumented_operation(context,approximation_identity(request,provenance),
        [&]() {return std::get<0>(workspace)->run(context);},approximation_termination<SetTransformOutcome>);
    if(const auto* stopped=std::get_if<OperationStopped>(&outcome))return *stopped;
    if(const auto* unsupported=std::get_if<Unsupported>(&outcome))return *unsupported;
    auto result=std::get<OperationResult>(std::move(outcome));
    if(result.relation!=request.direction)
        return Unsupported{error(DiagnosticCode::evidence_mismatch,"approximation.relation",
            "Provider result differs from the requested relation.")};
    if(auto diagnostics=check_geometry_evidence(result.evidence,request);!diagnostics.empty())
        return Unsupported{std::move(diagnostics)};
    if(result.evidence.error_bound)
        return Unsupported{error(DiagnosticCode::unsupported,"approximation.error_bound",
            "No independent approximation error-bound verifier is available.")};
    if(result.output.id.value.empty() || !result.output.payload ||
       result.output.metadata.dimension!=request.input.metadata.dimension ||
       result.output.metadata.representation!=request.output)
        return Unsupported{error(DiagnosticCode::evidence_mismatch,"approximation.output",
            "Output identity, payload, dimension or representation differs from the request.")};
    if(!within_budget(result.output,request.size_budget))
        return Unsupported{error(DiagnosticCode::unsupported,"approximation.budget",
            "Native output exceeds the requested primitive budget, or output size is unavailable.")};
    if(request.direction==SetRelation::heuristic)return HeuristicApproximation{std::move(result)};
    bool interrupted=false;
    const auto basis=structural_basis(request,result,context,interrupted);
    if(interrupted || context.cancellation.stop_requested() ||
       (context.deadline && std::chrono::steady_clock::now()>=*context.deadline))
        return OperationStopped{context.cancellation.stop_requested()?StopReason::cancelled:
            StopReason::deadline_expired,"Approximation policy stopped before publishing an enclosure."};
    if(basis) {
        result.evidence.support=SymbolicArgument{"CSL native structural set-inclusion check",
            "Same immutable set, empty subset, universal superset, exact H constraint retention, exact binary64 H containment of native points and recession rays, exact stored-binary64 generator axis cover, or exact V vertex bounds within a directional ellipsoid over the same ambient coordinates."};
        return EnclosedApproximation{std::move(result),*basis};
    }
    return Unsupported{error(DiagnosticCode::unsupported,"approximation.inclusion",
        "Requested enclosure has no independently checkable inclusion evidence.")};
}

BoundSide objective_bound_side(SetRelation relation,ObjectiveSense sense) noexcept {
    switch(relation) {
    case SetRelation::equivalent: return BoundSide::both;
    case SetRelation::heuristic: return BoundSide::none;
    case SetRelation::inner: return sense==ObjectiveSense::minimize?BoundSide::upper:BoundSide::lower;
    case SetRelation::outer: return sense==ObjectiveSense::minimize?BoundSide::lower:BoundSide::upper;
    }
    return BoundSide::none;
}
} // namespace csl::geometry::approximation
