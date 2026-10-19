#include <csl/geometry/approximation.hpp>
#include <csl/geometry/ellipsoidal.hpp>
#include <csl/sets/data.hpp>
#include "../exact_dyadic.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>

namespace csl::geometry::approximation {
namespace {
using namespace detail::exact_detail;

Diagnostics unsupported(const char* field,const char* message) {
    return {{DiagnosticCode::unsupported,field,message}};
}
bool stopped(const ExecutionContext& context) {
    return context.cancellation.stop_requested() ||
        (context.deadline && std::chrono::steady_clock::now()>=*context.deadline);
}
OperationStopped stop(const ExecutionContext& context) {
    return {context.cancellation.stop_requested()?StopReason::cancelled:StopReason::deadline_expired,
        "Ellipsoidal approximation stopped before publishing an enclosure."};
}
bool orientation_valid(const Matrix& b) {
    if(b.rows!=2 || b.cols!=2 || b.values.size()!=4)return false;
    for(double value:b.values)if(!std::isfinite(value))return false;
    Integer determinant;
    if(!add_product(determinant,decode(b.values[0]),decode(b.values[3])))return false;
    auto negative=decode(b.values[1]);negative.negative=!negative.negative;
    return add_product(determinant,negative,decode(b.values[2])) && !is_zero(determinant);
}
bool radius_sufficient(double bound,double radius) {
    Integer difference;
    if(!add_product(difference,decode(radius),decode(radius)))return false;
    auto negative=decode(bound);negative.negative=true;
    return add_product(difference,negative,decode(bound)) &&
        add_product(difference,negative,decode(bound)) && !difference.negative;
}
std::optional<double> radius_for(double bound) {
    if(bound==0)return 0.0;
    double radius=std::sqrt(2.0)*bound;
    if(!std::isfinite(radius))return std::nullopt;
    while(!radius_sufficient(bound,radius)) {
        radius=std::nextafter(radius,std::numeric_limits<double>::infinity());
        if(!std::isfinite(radius))return std::nullopt;
    }
    return radius;
}
registry::Capability capability(const ApproximationRequest& request,
                                const registry::Requirements& requirements,
                                const SetId& output_id,const Matrix& orientation) {
    if(output_id.value.empty() || !orientation_valid(orientation))
        return unsupported("ellipsoid.configuration","A nonempty output ID and independent finite orientation rows are required.");
    if(request.direction!=SetRelation::outer ||
       requirements.output.relation!=SetRelation::outer)
        return unsupported("ellipsoid.direction","Only an outer enclosure is offered.");
    if(request.assurance!=Assurance::numerical ||
       requirements.output.assurance!=Assurance::numerical ||
       requirements.scalar!=registry::Scalar::binary64)
        return unsupported("ellipsoid.assurance","Only binary64 numerical assurance is offered.");
    if(request.output.value!="csl.ellipsoid.directional2d" ||
       requirements.output.representation!=request.output ||
       request.input.metadata.dimension!=2 || request.size_budget<1)
        return unsupported("ellipsoid.output","A planar ellipsoid and one output primitive are required.");
    const auto imported=sets::from_handle(request.input);
    const auto* data=std::get_if<sets::SetData>(&imported);
    if(!data)return unsupported("ellipsoid.input","A native V input is required.");
    const auto representation=data->representation();
    const auto* v=std::get_if<sets::VRepresentation>(&representation);
    if(!v || v->vertices.rows()==0 || v->rays.rows()!=0)
        return unsupported("ellipsoid.input","A nonempty bounded native V input is required.");
    registry::Output output;
    output.representation=request.output;
    output.assurance=Assurance::numerical;
    output.relation=SetRelation::outer;
    return registry::Offer{output};
}
class EllipsoidWorkspace final : public SetApproximatorWorkspace {
    SetId output_id_;
    Matrix orientation_;
public:
    EllipsoidWorkspace(SetId id,Matrix orientation)
        :output_id_(std::move(id)),orientation_(std::move(orientation)){}
    SetTransformOutcome approximate(const ApproximationRequest& request,
                                     const ExecutionContext& context) override {
        if(stopped(context))return stop(context);
        const auto imported=sets::from_handle(request.input);
        const auto* data=std::get_if<sets::SetData>(&imported);
        if(!data)return Unsupported{unsupported("ellipsoid.input","Native V input is unavailable.")};
        const auto representation=data->representation();
        const auto* v=std::get_if<sets::VRepresentation>(&representation);
        if(!v || v->vertices.rows()==0 || v->rays.rows()!=0)
            return Unsupported{unsupported("ellipsoid.input","A nonempty bounded V input is required.")};
        Vector center(2),bounds(2,0),radii(2);
        for(std::size_t coordinate=0;coordinate<2;++coordinate) {
            double low=v->vertices(0,coordinate),high=low;
            for(std::size_t vertex=1;vertex<v->vertices.rows();++vertex) {
                if(stopped(context))return stop(context);
                low=std::min(low,v->vertices(vertex,coordinate));
                high=std::max(high,v->vertices(vertex,coordinate));
            }
            center[coordinate]=low/2+high/2;
            if(!std::isfinite(center[coordinate]))
                return Unsupported{unsupported("ellipsoid.center","Finite center could not be stored.")};
        }
        for(std::size_t row=0;row<2;++row) {
            Integer maximum;
            for(std::size_t vertex=0;vertex<v->vertices.rows();++vertex) {
                if(stopped(context))return stop(context);
                Integer projection;
                for(std::size_t coordinate=0;coordinate<2;++coordinate) {
                    const auto coefficient=decode(orientation_.values[row*2+coordinate]);
                    if(!add_product(projection,coefficient,decode(v->vertices(vertex,coordinate))))
                        return Unsupported{unsupported("ellipsoid.projection","Exact projection overflowed.")};
                    auto negative_center=decode(center[coordinate]);
                    negative_center.negative=!negative_center.negative;
                    if(!add_product(projection,coefficient,negative_center))
                        return Unsupported{unsupported("ellipsoid.projection","Exact projection overflowed.")};
                }
                projection.negative=false;
                if(compare_magnitude(projection,maximum)>0)maximum=projection;
            }
            const auto bound=outward_binary64(maximum);
            if(!bound)return Unsupported{unsupported("ellipsoid.projection","Finite projected bound could not be stored.")};
            bounds[row]=*bound;
            const auto radius=radius_for(*bound);
            if(!radius)return Unsupported{unsupported("ellipsoid.radius","Finite enclosing radius could not be stored.")};
            radii[row]=*radius;
        }
        const auto made=ellipsoidal::make_ellipsoid({output_id_,std::move(center),orientation_,
            std::move(bounds),std::move(radii),data->metadata()->coordinate_labels});
        if(!std::holds_alternative<ellipsoidal::EllipsoidSet>(made))
            return Unsupported{std::get<Diagnostics>(made)};
        if(stopped(context))return stop(context);
        GeometryEvidence evidence{{request.identity,{request.input.id}},GeometryClaimScope::set_relation,
            SymbolicArgument{"directional native ellipsoid candidate",
                "Every stored V vertex requires independent policy admission."},
            {"input_class=bounded_native_planar_v", "radius_rule=r_i^2 >= 2 m_i^2",
             "rounding=outward_projected_bounds; error_bound=unavailable"}, {}};
        return OperationResult{std::get<ellipsoidal::EllipsoidSet>(made).as_handle(),
            SetRelation::outer,std::move(evidence)};
    }
};
}

registry::Registration<registry::ApproximationPort> make_directional_ellipsoid_registration(
    registry::Method method,SetId output_id,Matrix orientation_rows) {
    return {{method.id,method.version.value_or("")},
        [output_id,orientation_rows](const ApproximationRequest& request,
            const registry::Requirements& requirements) -> registry::Capability {
            return capability(request,requirements,output_id,orientation_rows);
        },
        [output_id=std::move(output_id),orientation_rows=std::move(orientation_rows)](
            const ApproximationRequest&) {
            return std::make_unique<EllipsoidWorkspace>(output_id,orientation_rows);
        }};
}
} // namespace csl::geometry::approximation
