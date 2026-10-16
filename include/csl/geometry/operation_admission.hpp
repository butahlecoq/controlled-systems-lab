#pragma once

#include <csl/registry/provider.hpp>

namespace csl::geometry {

// A concrete geometry admission failure retains the immutable request identity
// and ordered input IDs without changing the registry's method-level result.
struct GeometryAdmissionRejection {
    GeometryReference reference;
    registry::Rejection provider;
};
using GeometryAdmission = std::variant<registry::PreparedPipeline<registry::GeometryPort>,
    GeometryAdmissionRejection>;

inline GeometryAdmission prepare_geometry_operation(const OperationRequest& request,
        const registry::PreparedProvider<registry::GeometryPort>& provider) {
    auto result=provider.prepare(request);
    if(auto* rejected=std::get_if<registry::Rejection>(&result))
        return GeometryAdmissionRejection{geometry_reference(request),std::move(*rejected)};
    return std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(result));
}

inline GeometryAdmission prepare_geometry_operation(const registry::Selection<registry::GeometryPort>& selection) {
    auto result=registry::prepare_pipeline(selection);
    if(auto* rejected=std::get_if<registry::Rejection>(&result))
        return GeometryAdmissionRejection{geometry_reference(selection.request),std::move(*rejected)};
    return std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(result));
}

} // namespace csl::geometry
