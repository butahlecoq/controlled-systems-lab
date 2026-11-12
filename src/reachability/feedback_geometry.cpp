#include <csl/reachability/feedback_geometry.hpp>
#include <csl/sets/data.hpp>

#include <algorithm>
#include <cmath>
#include <limits>

namespace csl::reachability {
namespace {
Diagnostics bad(const char* message) {
    return {{DiagnosticCode::invalid_input,"feedback.axis_enclosure",message}};
}
}
std::variant<FeedbackMembership, Diagnostics> axis_enclosure(FeedbackFamily family,
        SetId id, const Vector& lower, const Vector& upper,
        const std::vector<std::string>& labels) {
    const auto n=lower.size();
    if (id.value.empty() || upper.size()!=n || (!labels.empty() && labels.size()!=n) ||
        (n && n>std::numeric_limits<std::size_t>::max()/n/2) || n>std::numeric_limits<std::size_t>::max()/2)
        return bad("Nonempty ID and consistent bounded dimensions are required.");
    Vector center(n), radius(n);
    const double infinity=std::numeric_limits<double>::infinity();
    for (std::size_t i=0;i<n;++i) {
        if (!std::isfinite(lower[i]) || !std::isfinite(upper[i]) || lower[i]>upper[i])
            return bad("Axis bounds must be finite and ordered; no emptiness claim is made.");
        if (lower[i]==upper[i]) { center[i]=lower[i]; radius[i]=0; continue; }
        center[i]=lower[i]/2+upper[i]/2;
        radius[i]=std::nextafter(std::max(center[i]-lower[i],upper[i]-center[i]),infinity);
        if (!std::isfinite(center[i]) || !std::isfinite(radius[i])) return bad("Axis enclosure overflowed.");
    }
    Matrix diagonal{n,n,Vector(n*n,0)};
    if (family==FeedbackFamily::zonotope || family==FeedbackFamily::ellipsoid) {
        const double scale=family==FeedbackFamily::ellipsoid && n>0
            ? std::nextafter(std::sqrt(static_cast<double>(n)),infinity) : 1.0;
        for (std::size_t i=0;i<n;++i) {
            const double value=radius[i]*scale;
            diagonal.values[i*n+i]=value==0 ? 0 : std::nextafter(value,infinity);
            if (!std::isfinite(diagonal.values[i*n+i])) return bad("Axis factor overflowed.");
        }
        if (family==FeedbackFamily::ellipsoid)
            return FeedbackMembership{FeedbackEllipsoidMembership{std::move(center),std::move(diagonal)}};
        std::vector<sets::FactorId> factors;
        for (std::size_t i=0;i<n;++i) factors.push_back({id.value+"/axis/"+std::to_string(i)});
        return FeedbackMembership{FeedbackZonotopeMembership{std::move(center),std::move(diagonal),std::move(factors)}};
    }
    if (family==FeedbackFamily::polytope) return bad("Polytope membership must retain the original H operand.");
    Matrix rows{2*n,n,Vector(2*n*n,0)}, equalities{0,n,{}};
    Vector bounds(2*n);
    for (std::size_t i=0;i<n;++i) {
        rows.values[(2*i)*n+i]=1; rows.values[(2*i+1)*n+i]=-1;
        bounds[2*i]=upper[i]; bounds[2*i+1]=-lower[i];
        diagonal.values[i*n+i]=1;
    }
    auto a=numeric::snapshot(rows); auto b=numeric::snapshot_vector(bounds);
    auto e=numeric::snapshot(equalities); auto f=numeric::snapshot_vector({});
    if (auto* error=std::get_if<Diagnostic>(&a)) return Diagnostics{*error};
    if (auto* error=std::get_if<Diagnostic>(&b)) return Diagnostics{*error};
    if (auto* error=std::get_if<Diagnostic>(&e)) return Diagnostics{*error};
    if (auto* error=std::get_if<Diagnostic>(&f)) return Diagnostics{*error};
    auto h=sets::make_h({std::move(id),n,labels},
        {std::get<numeric::MatrixView>(a),std::get<numeric::VectorView>(b),
         std::get<numeric::MatrixView>(e),std::get<numeric::VectorView>(f)});
    if (auto* error=std::get_if<Diagnostic>(&h)) return Diagnostics{*error};
    return FeedbackMembership{FeedbackHMembership{std::get<sets::SetData>(h).as_handle(),
        family==FeedbackFamily::parallelotope ? std::optional<Matrix>{std::move(diagonal)} : std::nullopt}};
}
} // namespace csl::reachability
