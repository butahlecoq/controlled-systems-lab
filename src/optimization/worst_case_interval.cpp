#include <csl/optimization/worst_case_interval.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <limits>
#include <type_traits>

namespace csl::optimization {
static_assert(std::numeric_limits<double>::is_iec559 &&
    std::numeric_limits<double>::radix==2 &&
    std::numeric_limits<double>::digits==53,
    "worst_case_interval requires IEC 60559 binary64 arithmetic");
struct WorstCaseIntervalBuilder {
    static WorstCaseIntervalBounds make(const WorstCaseIntervalRequest& request,
            double lower, double upper) {
        return {request.problem, request.request, request.domain.metadata()->id,
            lower, upper};
    }
};
namespace {
struct Interval {
    double lower;
    double upper;
};
constexpr double negative_infinity=-std::numeric_limits<double>::infinity();
constexpr double positive_infinity=std::numeric_limits<double>::infinity();
Interval whole() { return {negative_infinity,positive_infinity}; }
double down(double value) { return std::nextafter(value,negative_infinity); }
double up(double value) { return std::nextafter(value,positive_infinity); }
Interval add(Interval a,Interval b) {
    const double lower=a.lower+b.lower,upper=a.upper+b.upper;
    if(std::isnan(lower)||std::isnan(upper)) return whole();
    return {down(lower),up(upper)};
}
Interval multiply(Interval a,Interval b) {
    const std::array<double,4> products{
        a.lower*b.lower,a.lower*b.upper,a.upper*b.lower,a.upper*b.upper};
    if(std::any_of(products.begin(),products.end(),
            [](double value){return std::isnan(value);})) return whole();
    const auto [minimum,maximum]=std::minmax_element(products.begin(),products.end());
    return {down(*minimum),up(*maximum)};
}
Interval square(Interval value) {
    if(value.lower<=0&&value.upper>=0) {
        const double upper=std::max(value.lower*value.lower,value.upper*value.upper);
        if(std::isnan(upper)) return {0,positive_infinity};
        return {0,up(upper)};
    }
    const double first=value.lower*value.lower,second=value.upper*value.upper;
    if(std::isnan(first)||std::isnan(second)) return {0,positive_infinity};
    return {std::max(0.0,down(std::min(first,second))),up(std::max(first,second))};
}
Interval square_root(Interval value) {
    if(value.upper<0) return whole();
    double lower=0;
    if(std::isfinite(value.lower)&&value.lower>0) {
        auto candidate=std::sqrt(value.lower);
        for(int attempt=0;attempt<4&&candidate>0;++attempt) {
            if(square({candidate,candidate}).upper<=value.lower) {lower=candidate;break;}
            candidate=down(candidate);
        }
    }
    double upper=positive_infinity;
    if(std::isfinite(value.upper)) {
        auto candidate=std::sqrt(std::max(0.0,value.upper));
        for(int attempt=0;attempt<4;++attempt) {
            if(square({candidate,candidate}).lower>=value.upper) {upper=candidate;break;}
            candidate=up(candidate);
        }
        if(!std::isfinite(upper))
            upper=std::max(1.0,value.upper); // sqrt(x) <= max(1,x), x >= 0.
    }
    return {lower,upper};
}
Interval evaluate_box(const ObjectiveCoefficients& objective,
        const std::vector<Interval>& point) {
    return std::visit([&](const auto& coefficients)->Interval {
        using T=std::decay_t<decltype(coefficients)>;
        if constexpr(std::is_same_v<T,LinearCoefficients>) {
            Interval result{coefficients.offset,coefficients.offset};
            for(std::size_t i=0;i<point.size();++i)
                result=add(result,multiply({coefficients.coefficients[i],coefficients.coefficients[i]},point[i]));
            return result;
        } else if constexpr(std::is_same_v<T,QuadraticCoefficients>) {
            Interval result{coefficients.offset,coefficients.offset};
            for(std::size_t i=0;i<point.size();++i) {
                Interval row{0,0};
                for(std::size_t j=0;j<point.size();++j)
                    row=add(row,multiply({coefficients.Q(i,j),coefficients.Q(i,j)},point[j]));
                result=add(result,multiply(multiply({0.5,0.5},point[i]),row));
                result=add(result,multiply({coefficients.linear[i],coefficients.linear[i]},point[i]));
            }
            return result;
        } else {
            Interval squared{0,0};
            for(std::size_t r=0;r<coefficients.map.rows();++r) {
                Interval residual{-coefficients.target[r],-coefficients.target[r]};
                for(std::size_t c=0;c<point.size();++c)
                    residual=add(residual,multiply(
                        {coefficients.map(r,c),coefficients.map(r,c)},point[c]));
                squared=add(squared,square(residual));
            }
            return square_root(squared);
        }
    },objective);
}
std::variant<std::vector<Interval>,Unsupported> bounds_of(const sets::SetData& domain,
        std::size_t count) {
    const auto dimension=domain.metadata()->set.dimension;
    const auto representation=domain.representation();
    std::vector<Interval> bounds(dimension,{positive_infinity,negative_infinity});
    if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation)) {
        for(std::size_t i=0;i<dimension;++i)
            bounds[i]={singleton->point[i],singleton->point[i]};
        return bounds;
    }
    const auto* vertices=std::get_if<sets::VRepresentation>(&representation);
    if(!vertices)
        return Unsupported{{{DiagnosticCode::unsupported,"worst_case_interval.representation",
            "A complete bounded native V description or singleton is required."}}};
    if(vertices->rays.rows()!=0)
        return Unsupported{{{DiagnosticCode::unsupported,"worst_case_interval.bounded",
            "V rays make the domain unbounded."}}};
    if(vertices->vertices.rows()!=count)
        return Unsupported{{{DiagnosticCode::invalid_input,"worst_case_interval.vertices",
            "Vertex count changed during immutable interval admission."}}};
    for(std::size_t row=0;row<count;++row) for(std::size_t col=0;col<dimension;++col) {
        const double value=vertices->vertices(row,col);
        if(!std::isfinite(value))
            return Unsupported{{{DiagnosticCode::invalid_input,"worst_case_interval.vertex",
                "Vertex coordinates must be finite."}}};
        bounds[col].lower=std::min(bounds[col].lower,value);
        bounds[col].upper=std::max(bounds[col].upper,value);
    }
    for(auto& bound:bounds) if(bound.lower==positive_infinity) bound={0,0};
    return bounds;
}
}

WorstCaseIntervalOutcome worst_case_interval(const WorstCaseIntervalRequest& request,
        const ExecutionContext& context) {
    if(request.problem.value.empty()||request.request.value.empty())
        return Unsupported{{{DiagnosticCode::invalid_input,"worst_case_interval.identity",
            "Nonempty problem and request identities are required."}}};
    if(request.objective.dimension()!=request.domain.metadata()->set.dimension)
        return Unsupported{{{DiagnosticCode::invalid_input,"worst_case_interval.dimension",
            "Set and objective dimensions differ."}}};
    if(request.objective.policy().assurance!=Assurance::numerical)
        return Unsupported{{{DiagnosticCode::unsupported,"worst_case_interval.assurance",
            "The interval evaluator accepts stored binary64 objective coefficients only."}}};
    const auto representation=request.domain.representation();
    if(std::holds_alternative<sets::EmptyRepresentation>(representation))
        return WorstCaseIntervalEmpty{};
    const auto* vertices=std::get_if<sets::VRepresentation>(&representation);
    const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation);
    if(!vertices&&!singleton)
        return Unsupported{{{DiagnosticCode::unsupported,"worst_case_interval.representation",
            "A complete bounded native V description or singleton is required."}}};
    const auto count=singleton?std::size_t{1}:vertices->vertices.rows();
    if(vertices&&vertices->rays.rows()!=0)
        return Unsupported{{{DiagnosticCode::unsupported,"worst_case_interval.bounded",
            "V rays make the domain unbounded."}}};
    if(count==0) return WorstCaseIntervalEmpty{};
    if(count>request.max_vertices)
        return Unsupported{{{DiagnosticCode::unsupported,"worst_case_interval.capacity",
            "Vertex count exceeds the caller limit."}}};
    if(context.cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Interval worst-case evaluation cancelled."};
    if(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)
        return OperationStopped{StopReason::deadline_expired,"Interval worst-case deadline expired."};
    auto box=bounds_of(request.domain,count);
    if(const auto* failure=std::get_if<Unsupported>(&box)) return *failure;
    const auto objective=request.objective.coefficients();
    const auto upper=evaluate_box(objective,std::get<std::vector<Interval>>(box)).upper;
    double lower=negative_infinity;
    for(std::size_t row=0;row<count;++row) {
        if(context.cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Interval worst-case evaluation cancelled."};
        if(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)
            return OperationStopped{StopReason::deadline_expired,"Interval worst-case deadline expired."};
        std::vector<Interval> point(request.objective.dimension());
        if(singleton) {
            for(std::size_t col=0;col<point.size();++col)
                point[col]={singleton->point[col],singleton->point[col]};
        } else {
            for(std::size_t col=0;col<point.size();++col) {
                const double value=vertices->vertices(row,col);
                if(!std::isfinite(value))
                    return Unsupported{{{DiagnosticCode::invalid_input,"worst_case_interval.vertex",
                        "Vertex coordinates must be finite."}}};
                point[col]={value,value};
            }
        }
        lower=std::max(lower,evaluate_box(objective,point).lower);
    }
    if(std::isnan(lower)||std::isnan(upper)||lower>upper)
        return OperationStopped{StopReason::numerical_failure,
            "Outward interval evaluation failed to enclose a finite-domain maximum."};
    return WorstCaseIntervalBuilder::make(request,lower,upper);
}
} // namespace csl::optimization
