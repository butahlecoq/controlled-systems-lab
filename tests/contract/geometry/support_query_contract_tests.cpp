#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/geometry/operation_admission.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/numeric/data.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/data.hpp>

#include <memory>
#include <utility>

using namespace csl;

namespace {
template<class T,class... Alternatives> T take(std::variant<T,Alternatives...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
}

TEST_CASE("admission rejects an unsupported ray SupportQuery") {
    // V={0}+cone{1}=[0,+infinity), so its support in direction +1 is +infinity.
    const auto ray=take(sets::make_v({{"positive-ray"},1,{"x"}},
        {take(numeric::snapshot(Matrix{1,1,{0}})),
         take(numeric::snapshot(Matrix{1,1,{1}}))})).as_handle();
    const OperationRequest request{{{"test08"},{"unbounded-support"},{"positive-infinity"}},
        {"csl.geometry.polyhedral-projection"},SupportQuery{ray,{1}},
        SetRelation::equivalent,Assurance::numerical};
    CHECK(check_operation_shape(request).empty());

    auto entry=geometry::polyhedral::make_projection_registration();
    auto workspace_creations=std::make_shared<std::size_t>(0);
    auto factory=entry.factory;
    entry.factory=[workspace_creations,factory=std::move(factory)](
            const OperationRequest& operation) mutable {
        ++*workspace_creations;
        return factory(operation);
    };
    registry::Registry<registry::GeometryPort> registry;
    const registry::Method method{entry.identity.id,entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    registry::Requirements requirements;
    requirements.output.representation={"csl.polyhedron.h"};
    requirements.output.relation=SetRelation::equivalent;
    auto selected=take(registry::prepare_provider(
        registry::select_provider(registry,method,requirements)));

    const auto admission=geometry::prepare_geometry_operation(request,selected);
    const auto* rejection=std::get_if<geometry::GeometryAdmissionRejection>(&admission);
    REQUIRE(rejection);
    CHECK(rejection->reference.identity==request.identity);
    CHECK(rejection->reference.inputs==std::vector<SetId>{ray.id});
    REQUIRE(rejection->provider.diagnostics.size()==1);
    CHECK(rejection->provider.diagnostics.front().code==DiagnosticCode::unsupported);
    CHECK(rejection->provider.diagnostics.front().field=="projection.operation");
    CHECK(rejection->provider.provenance.requested.id==ModuleId{"csl.geometry.polyhedral-projection"});
    REQUIRE(rejection->provider.provenance.actual);
    CHECK(rejection->provider.provenance.actual->id==ModuleId{"csl.geometry.polyhedral-projection"});
    CHECK(*workspace_creations==0);
}
