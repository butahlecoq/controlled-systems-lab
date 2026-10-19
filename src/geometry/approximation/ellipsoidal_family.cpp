#include <csl/geometry/ellipsoidal.hpp>
#include <csl/sets/data.hpp>

namespace csl::geometry::ellipsoidal {
namespace {
registry::Rejection reject(const char* field,const char* message) {
    return {{registry::ApproximationPort::name,{{"csl.ellipsoid.family"},"1"},{}},
        {{DiagnosticCode::unsupported,field,message}}};
}
Unsupported unsupported(const char* field,const char* message) {
    return {{{DiagnosticCode::unsupported,field,message}}};
}
}

EllipsoidFamilyOutcome run_ellipsoid_family(
    const registry::Registry<registry::ApproximationPort>& registry,
    const std::vector<registry::Method>& methods,const ApproximationRequest& request,
    const ExecutionContext& context) {
    if(methods.empty())return reject("ellipsoid.family.methods",
        "At least one ellipsoid method is required.");
    if(request.direction!=SetRelation::outer && request.direction!=SetRelation::inner)
        return reject("ellipsoid.family.relation",
            "A finite family requires an inner or outer relation.");
    if(request.output.value!="csl.ellipsoid.directional2d")
        return reject("ellipsoid.family.output","An ellipsoid output is required.");
    const auto reference=sets::from_handle(request.input);
    const auto* source=std::get_if<sets::SetData>(&reference);
    if(!source || source->metadata()->set.dimension!=2)
        return reject("ellipsoid.family.reference","A native planar reference is required.");
    std::vector<approximation::EnclosedApproximation> members;
    members.reserve(methods.size());
    for(const auto& method:methods) {
        auto result=approximation::run_registered(registry,method,request,context);
        if(const auto* rejected=std::get_if<registry::Rejection>(&result))return *rejected;
        if(const auto* stopped=std::get_if<OperationStopped>(&result))return *stopped;
        if(const auto* refusal=std::get_if<Unsupported>(&result))return *refusal;
        const auto* admitted=std::get_if<approximation::EnclosedApproximation>(&result);
        if(!admitted)return unsupported("ellipsoid.family.admission",
            "A family member has no independently admitted enclosure.");
        const auto imported=from_ellipsoid_handle(admitted->result.output);
        const auto* ellipse=std::get_if<EllipsoidSet>(&imported);
        if(!ellipse || ellipse->coordinate_labels()!=source->metadata()->coordinate_labels ||
           admitted->result.relation!=request.direction ||
           admitted->result.evidence.reference.inputs.size()!=1 ||
           admitted->result.evidence.reference.inputs[0]!=request.input.id)
            return unsupported("ellipsoid.family.member",
                "A member differs from the common ellipsoid reference or relation.");
        members.push_back(*admitted);
    }
    return EllipsoidFamily(request.input.id,request.direction,
        request.direction==SetRelation::outer?FamilyComposition::intersection:
            FamilyComposition::union_of_members,std::move(members));
}
} // namespace csl::geometry::ellipsoidal
