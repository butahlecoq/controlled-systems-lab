#include <csl/geometry/approximation.hpp>
#include <csl/geometry/ellipsoidal.hpp>
#include <csl/sets/data.hpp>
#include <iostream>

int main() {
    using namespace csl;
    using namespace csl::geometry::approximation;
    using namespace csl::geometry::ellipsoidal;
    const auto vertices=numeric::snapshot(Matrix{4,2,{-1,-1,1,-1,1,1,-1,1}});
    const auto rays=numeric::snapshot(Matrix{0,2,{}});
    if(!std::holds_alternative<numeric::MatrixView>(vertices) ||
       !std::holds_alternative<numeric::MatrixView>(rays))return 1;
    const auto source=sets::make_v({{"installed-square"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(rays)});
    if(!std::holds_alternative<sets::SetData>(source))return 2;
    const ApproximationRequest request{{{"installed-app04"},{"square"},{"source"}},
        std::get<sets::SetData>(source).as_handle(),{"csl.ellipsoid.directional2d"},
        SetRelation::outer,1,Assurance::numerical};
    registry::Registry<registry::ApproximationPort> registry;
    const registry::Method axis{{"installed.ellipse.axis"},"1"};
    const registry::Method rotated{{"installed.ellipse.rotated"},"1"};
    if(registry.add(make_directional_ellipsoid_registration(axis,{"axis"},
        Matrix{2,2,{1,0,0,1}})))return 3;
    if(registry.add(make_directional_ellipsoid_registration(rotated,{"rotated"},
        Matrix{2,2,{1,1,1,-1}})))return 4;
    const auto outcome=run_ellipsoid_family(registry,{axis,rotated},request,ExecutionContext{});
    if(!std::holds_alternative<EllipsoidFamily>(outcome))return 5;
    const auto& family=std::get<EllipsoidFamily>(outcome);
    if(family.composition()!=FamilyComposition::intersection ||
       family.members().size()!=2 || family.reference_id()!=request.input.id)return 6;
    for(const auto& member:family.members())
        if(member.basis!=StructuralBasis::v_ellipsoid_containment ||
           !std::holds_alternative<EllipsoidSet>(from_ellipsoid_handle(member.result.output)))
            return 7;
    std::cout<<"Installed ellipsoidal client: two reviewed outer members passed\n";
}
