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
class ExternalSetPayload final : public SetPayload {};
class ExternalGeometryWorkspace final : public SetOperatorWorkspace {
public:
    OperationOutcome apply(const OperationRequest& request,const ExecutionContext&) override {
        return OperationStopped{StopReason::resource_limit,request.identity.request.value};
    }
};
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

TEST_CASE("external geometry registrations resolve typed operands and report conflicts") {
    const SetHandle ellipsoid{{2,{"test.future.ellipsoid"},SetProperty::yes,
        SetProperty::no,SetProperty::yes},std::make_shared<const ExternalSetPayload>(),{"ellipsoid/input"}};
    const OperationRequest request{{{"test.geometry"},{"external-support"},{"support-reference"}},
        {"test.external-support"},SupportQuery{ellipsoid,{1.0,0.0}},SetRelation::equivalent,
        Assurance::numerical};
    auto workspace_creations=std::make_shared<std::size_t>(0);
    registry::Registry<registry::GeometryPort> registry;
    registry::Registration<registry::GeometryPort> entry{
        {{"test.external-support"},"1"},
        [](const OperationRequest& query,const registry::Requirements&) -> registry::Capability {
            const auto* support=std::get_if<SupportQuery>(&query.operation);
            if(!support || support->input.metadata.representation.value!="test.future.ellipsoid")
                return Diagnostics{{DiagnosticCode::unsupported,"input.representation",
                    "external adapter requires test.future.ellipsoid support input"}};
            if(query.required_relation!=SetRelation::equivalent)
                return Diagnostics{{DiagnosticCode::unsupported,"output.relation",
                    "external support query only accepts equivalent output"}};
            registry::Output output;output.representation={"test.support-value"};
            output.relation=SetRelation::equivalent;return registry::Offer{output};
        },
        [workspace_creations](const OperationRequest&) {
            ++*workspace_creations;return std::make_unique<ExternalGeometryWorkspace>();
        }};
    REQUIRE_FALSE(registry.add(entry).has_value());
    auto duplicate=registry.add(entry);
    REQUIRE(duplicate);
    CHECK(duplicate->diagnostics.front().field=="registration");

    registry::Requirements requirements;
    requirements.output.representation={"test.support-value"};
    requirements.output.relation=SetRelation::equivalent;
    const registry::Method method{{"test.external-support"},std::string{"1"}};
    auto provider=take(registry::prepare_provider(
        registry::select_provider(registry,method,requirements)));
    auto admission=geometry::prepare_geometry_operation(request,provider);
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<registry::GeometryPort>>(admission));
    auto workspaces=std::get<registry::PreparedPipeline<registry::GeometryPort>>(admission).create();
    auto stopped=std::get<0>(workspaces)->run(ExecutionContext{});
    REQUIRE(std::holds_alternative<OperationStopped>(stopped));
    CHECK(std::get<OperationStopped>(stopped).diagnostics=="external-support");
    CHECK(*workspace_creations==1);

    auto incompatible=request;
    auto wrong_input=ellipsoid;wrong_input.metadata.representation={"test.future.zonotope"};
    std::get<SupportQuery>(incompatible.operation).input=wrong_input;
    admission=geometry::prepare_geometry_operation(incompatible,provider);
    REQUIRE(std::holds_alternative<geometry::GeometryAdmissionRejection>(admission));
    const auto& rejection=std::get<geometry::GeometryAdmissionRejection>(admission);
    CHECK(rejection.reference.identity==incompatible.identity);
    CHECK(rejection.reference.inputs==std::vector<SetId>{wrong_input.id});
    REQUIRE(rejection.provider.diagnostics.size()==1);
    CHECK(rejection.provider.diagnostics.front().field=="input.representation");
    CHECK(*workspace_creations==1);

    const OperationRequest sum_request{{{"test.geometry"},{"future-set-sum"},{"sum-reference"}},
        {"test.automatic-set-sum"},MinkowskiSum{ellipsoid,wrong_input},SetRelation::equivalent,
        Assurance::numerical};
    const auto missing=registry::check_pipeline(registry::select(registry,
        registry::Method{{"test.automatic-set-sum"},std::nullopt},sum_request,requirements));
    REQUIRE(std::holds_alternative<registry::Rejection>(missing));
    CHECK(std::get<registry::Rejection>(missing).diagnostics.front().field=="method");

    CHECK(*workspace_creations==1);
}
