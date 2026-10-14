#include <csl/problem/contracts.hpp>
#include "detail.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
#include <utility>

namespace csl {
namespace {
using contracts_detail::Overloaded;
using contracts_detail::matrix_matches;
}
Diagnostics check_nominal_profile(const Problem& p, bool requires_inverse, Assurance assurance) {
    Diagnostics result;
    auto unsupported = [&](std::string field, std::string explanation) {
        result.push_back({DiagnosticCode::unsupported,std::move(field),std::move(explanation)});
    };
    if (!p.model) return {{DiagnosticCode::invalid_input,"model","Model snapshot is required"}};
    if (p.model->dynamics.time_domain != TimeDomain::discrete)
        unsupported("time_domain","Only supplied discrete transitions are supported");
    if (requires_inverse)
        unsupported("dynamics.inverse","Revision 1 supplies no invertibility proof; choose a pipeline not requiring inverse dynamics");
    if (!std::holds_alternative<KnownInitial>(p.initial))
        unsupported("initial","Known initial point required");
    if (p.information != InformationPattern::nominal_open_loop)
        unsupported("information","Nominal open-loop profile required");
    if (p.external || p.model->dynamics.dimensions.external != 0)
        unsupported("external","External-input semantics require another capability profile");
    if (p.temporal && p.temporal->joint_map.rows != 0)
        unsupported("temporal","Nonempty temporal constraints require a compatible lift");
    auto polyhedral = [](const AdmissibleSet& set) {
        auto handle = std::get_if<SetHandle>(&set);
        return !handle || (handle->metadata.convex == SetProperty::yes && handle->metadata.polyhedral == SetProperty::yes);
    };
    if (auto continuous = std::get_if<ContinuousDomain>(&p.controls)) {
        for (const auto& set : continuous->stages)
            if (!polyhedral(set)) unsupported("controls","Convex polyhedral stage sets required");
    } else unsupported("controls","Continuous controls required; finite/mixed domains are not silently convexified");
    for (const auto& set : p.states)
        if (!polyhedral(set)) unsupported("states","Convex polyhedral stage sets required");
    if (assurance == Assurance::validated)
        unsupported("assurance","No validated verifier is implemented in revision 1");
    return result;
}
} // namespace csl
