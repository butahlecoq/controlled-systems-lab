#include <csl/reachability/fixed_plan_disturbance.hpp>
#include <algorithm>
#include <cmath>
#include <limits>

namespace csl::reachability {
namespace {
Unsupported unsupported(std::string field, std::string explanation,
                        DiagnosticCode code=DiagnosticCode::unsupported) {
    return {{{code,std::move(field),std::move(explanation)}}};
}
std::optional<OperationStopped> stopped(const ExecutionContext& context) {
    if(context.cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Fixed-plan propagation cancelled."};
    if(context.deadline && std::chrono::steady_clock::now()>=*context.deadline)
        return OperationStopped{StopReason::deadline_expired,"Fixed-plan propagation deadline expired."};
    return {};
}
using Points = std::vector<Vector>;
std::variant<Points,Unsupported> points(const sets::SetData& set,std::size_t limit) {
    const auto rep=set.representation();
    const auto dimension=set.metadata()->set.dimension;
    if(std::holds_alternative<sets::EmptyRepresentation>(rep))return Points{};
    if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&rep)) {
        if(limit==0)return unsupported("fixed_plan.capacity","Initial or disturbance point exceeds caller limit.");
        const auto values=singleton->point.values();
        return Points{Vector(values.begin(),values.end())};
    }
    const auto* v=std::get_if<sets::VRepresentation>(&rep);
    if(!v)return unsupported("fixed_plan.representation","Initial and disturbance sets require complete bounded V descriptions or singletons.");
    if(v->rays.rows()!=0)return unsupported("fixed_plan.bounded","Unbounded V sets are unsupported.");
    if(v->vertices.rows()>limit)return unsupported("fixed_plan.capacity","Point count exceeds caller limit.");
    Points result;
    result.reserve(v->vertices.rows());
    for(std::size_t row=0;row<v->vertices.rows();++row) {
        Vector point(dimension);
        for(std::size_t col=0;col<dimension;++col)point[col]=v->vertices(row,col);
        result.push_back(std::move(point));
    }
    return result;
}
enum class Membership { inside,outside,numerical_failure,unsupported };
Membership contains(const sets::SetData& set,const Vector& point,NumericalPolicy policy) {
    const auto rep=set.representation();
    if(std::holds_alternative<sets::UniversalRepresentation>(rep))return Membership::inside;
    if(std::holds_alternative<sets::EmptyRepresentation>(rep))return Membership::outside;
    const auto within=[&](long double activity,long double bound,bool equality) {
        const auto scale=std::max({1.0L,std::abs(activity),std::abs(bound)});
        const auto tolerance=static_cast<long double>(policy.absolute_tolerance)+
            static_cast<long double>(policy.relative_tolerance)*scale;
        if(!std::isfinite(activity)||!std::isfinite(tolerance))return Membership::numerical_failure;
        const auto residual=equality?std::abs(activity-bound):activity-bound;
        return residual<=tolerance?Membership::inside:Membership::outside;
    };
    if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&rep)) {
        for(std::size_t col=0;col<point.size();++col)
            if(const auto check=within(point[col],singleton->point[col],true);check!=Membership::inside)return check;
        return Membership::inside;
    }
    const auto* h=std::get_if<sets::HRepresentation>(&rep);
    if(!h)return Membership::unsupported;
    const auto rows=[&](const numeric::MatrixView& matrix,const numeric::VectorView& bounds,bool equality) {
        for(std::size_t row=0;row<matrix.rows();++row) {
            long double activity=0;
            for(std::size_t col=0;col<point.size();++col)
                activity+=static_cast<long double>(matrix(row,col))*static_cast<long double>(point[col]);
            if(const auto check=within(activity,bounds[row],equality);check!=Membership::inside)return check;
        }
        return Membership::inside;
    };
    if(const auto check=rows(h->inequalities,h->upper_bounds,false);check!=Membership::inside)return check;
    return rows(h->equalities,h->equality_values,true);
}
std::variant<sets::SetData,Unsupported> stage_set(const FixedPlanRequest& request,
    std::size_t stage,const Points& points) {
    const auto n=request.system.dimensions().state;
    if(points.size() && n>std::numeric_limits<std::size_t>::max()/points.size())
        return unsupported("fixed_plan.storage","Candidate matrix exceeds size_t.");
    Vector values;
    values.reserve(points.size()*n);
    for(const auto& point:points)values.insert(values.end(),point.begin(),point.end());
    const auto matrix=numeric::snapshot(Matrix{points.size(),n,std::move(values)});
    const auto rays=numeric::snapshot(Matrix{0,n,{}});
    if(const auto* error=std::get_if<Diagnostic>(&matrix))return unsupported(error->field,error->explanation,error->code);
    if(const auto* error=std::get_if<Diagnostic>(&rays))return unsupported(error->field,error->explanation,error->code);
    const auto field=[](const std::string& value) {return std::to_string(value.size())+":"+value;};
    const auto id=SetId{"fixed-plan/"+field(request.initial.metadata()->id.value)+
        field(request.request.value)+std::to_string(stage)};
    auto result=sets::make_v({id,n,request.initial.metadata()->coordinate_labels},
        {std::get<numeric::MatrixView>(matrix),std::get<numeric::MatrixView>(rays)});
    if(const auto* error=std::get_if<Diagnostic>(&result))return unsupported(error->field,error->explanation,error->code);
    return std::get<sets::SetData>(std::move(result));
}
}

FixedPlanOutcome fixed_plan_disturbance(const FixedPlanRequest& request,
    std::size_t max_points,const ExecutionContext& context) {
    const auto dims=request.system.dimensions();
    const auto horizon=request.system.horizon();
    if(request.request.value.empty())
        return unsupported("fixed_plan.request","A nonempty caller-unique request ID is required.",DiagnosticCode::invalid_input);
    if(request.controls.size()!=horizon||request.disturbances.size()!=horizon||
       request.admissible_states.size()!=horizon+1)
        return unsupported("fixed_plan.horizon","Controls, disturbances and safe sets must match the system horizon.",DiagnosticCode::invalid_input);
    if(!std::isfinite(context.numerical.absolute_tolerance)||context.numerical.absolute_tolerance<0||
       !std::isfinite(context.numerical.relative_tolerance)||context.numerical.relative_tolerance<0)
        return unsupported("fixed_plan.numerical","Numerical tolerances must be finite and nonnegative.",DiagnosticCode::invalid_input);
    if(request.initial.metadata()->set.dimension!=dims.state)
        return unsupported("fixed_plan.initial.dimension","Initial state dimension differs from model.",DiagnosticCode::invalid_input);
    for(std::size_t stage=0;stage<horizon;++stage) {
        if(request.controls[stage].size()!=dims.control||request.disturbances[stage].metadata()->set.dimension!=dims.external)
            return unsupported("fixed_plan.stage.dimension","Control or disturbance dimension differs from model.",DiagnosticCode::invalid_input);
        for(double value:request.controls[stage])if(!std::isfinite(value))
            return unsupported("fixed_plan.control","Controls must be finite.",DiagnosticCode::invalid_input);
    }
    for(const auto& safe:request.admissible_states) {
        if(safe.metadata()->set.dimension!=dims.state||
           (!safe.metadata()->coordinate_labels.empty() && !request.initial.metadata()->coordinate_labels.empty() &&
            safe.metadata()->coordinate_labels!=request.initial.metadata()->coordinate_labels))
            return unsupported("fixed_plan.safe.dimension","Safe set dimensions or named coordinates differ from initial state.",DiagnosticCode::invalid_input);
        const auto representation=safe.representation();
        if(!std::holds_alternative<sets::HRepresentation>(representation) &&
           !std::holds_alternative<sets::SingletonRepresentation>(representation) &&
           !std::holds_alternative<sets::UniversalRepresentation>(representation) &&
           !std::holds_alternative<sets::EmptyRepresentation>(representation))
            return unsupported("fixed_plan.safe.representation","Safe set requires H, singleton, universal or empty representation.");
    }
    // Admit the complete request before a robust violation can be reported.
    auto current_result=points(request.initial,max_points);
    if(const auto* error=std::get_if<Unsupported>(&current_result))return *error;
    auto current=std::get<Points>(std::move(current_result));
    std::vector<Points> all_disturbances;
    all_disturbances.reserve(horizon);
    for(const auto& set:request.disturbances) {
        auto result=points(set,max_points);
        if(const auto* error=std::get_if<Unsupported>(&result))return *error;
        all_disturbances.push_back(std::get<Points>(std::move(result)));
    }
    auto candidate_count=current.size();
    for(const auto& disturbance:all_disturbances) {
        if(disturbance.empty()) {candidate_count=0;continue;}
        if(candidate_count>max_points/disturbance.size())
            return unsupported("fixed_plan.capacity","Generated successor count exceeds caller limit.");
        candidate_count*=disturbance.size();
    }
    if(const auto stop=stopped(context))return *stop;
    if(current.empty())return FixedPlanEmpty{0};
    for(const auto& point:current) {
        const auto membership=contains(request.admissible_states[0],point,context.numerical);
        if(membership==Membership::outside)return FixedPlanViolation{0,point};
        if(membership==Membership::unsupported)return unsupported("fixed_plan.safe.representation","Safe set requires H, singleton, universal or empty representation.");
        if(membership==Membership::numerical_failure)return OperationStopped{StopReason::numerical_failure,"Nonfinite safe-set arithmetic."};
    }
    FixedPlanReachable tube{{request.initial},Assurance::numerical};
    for(std::size_t stage=0;stage<horizon;++stage) {
        if(const auto stop=stopped(context))return *stop;
        const auto& disturbances=all_disturbances[stage];
        if(disturbances.empty())return FixedPlanEmpty{stage+1};
        Points next;
        next.reserve(current.size()*disturbances.size());
        for(const auto& state:current)for(const auto& disturbance:disturbances) {
            if(const auto stop=stopped(context))return *stop;
            auto stepped=request.system.step({stage},state,request.controls[stage],disturbance);
            if(const auto* error=std::get_if<Diagnostic>(&stepped))
                return unsupported(error->field,error->explanation,error->code);
            if(const auto* stop=std::get_if<OperationStopped>(&stepped))return *stop;
            auto successor=std::get<Vector>(std::move(stepped));
            const auto membership=contains(request.admissible_states[stage+1],successor,context.numerical);
            if(membership==Membership::outside)return FixedPlanViolation{stage+1,std::move(successor)};
            if(membership==Membership::unsupported)return unsupported("fixed_plan.safe.representation","Safe set requires H, singleton, universal or empty representation.");
            if(membership==Membership::numerical_failure)return OperationStopped{StopReason::numerical_failure,"Nonfinite safe-set arithmetic."};
            next.push_back(std::move(successor));
        }
        auto materialized=stage_set(request,stage+1,next);
        if(const auto* error=std::get_if<Unsupported>(&materialized))return *error;
        tube.stages.push_back(std::get<sets::SetData>(std::move(materialized)));
        current=std::move(next);
    }
    return tube;
}
} // namespace csl::reachability
