#include <csl/geometry/approximation.hpp>
#include <csl/geometry/box_parallelotope.hpp>
#include <csl/sets/data.hpp>
#include <iostream>

int main() {
    using namespace csl;
    using namespace csl::geometry::approximation;
    const auto vertices=numeric::snapshot(Matrix{4,2,{0,2,2,0,0,-2,-2,0}});
    const auto rays=numeric::snapshot(Matrix{0,2,{}});
    if(!std::holds_alternative<numeric::MatrixView>(vertices) ||
       !std::holds_alternative<numeric::MatrixView>(rays))return 1;
    const auto source=sets::make_v({{"installed-diamond"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(rays)});
    if(!std::holds_alternative<sets::SetData>(source))return 2;
    const ApproximationRequest request{{{"installed-problem"},{"installed-request"},{"installed-reference"}},
        std::get<sets::SetData>(source).as_handle(),{"csl.polyhedron.h"},
        SetRelation::outer,4,Assurance::numerical};
    registry::Registry<registry::ApproximationPort> methods;
    if(methods.add(make_parallelotope_registration({"installed-output"},
        Matrix{2,2,{1,1,1,-1}})))return 3;
    const auto result=run_registered(methods,{{"csl.approximation.parallelotope"},std::nullopt},
        request,ExecutionContext{});
    if(!std::holds_alternative<EnclosedApproximation>(result))return 4;
    const auto& enclosed=std::get<EnclosedApproximation>(result);
    if(enclosed.basis!=StructuralBasis::v_h_containment)return 5;
    const auto native=sets::from_handle(enclosed.result.output);
    if(!std::holds_alternative<sets::SetData>(native))return 6;
    const auto representation=std::get<sets::SetData>(native).representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h || h->inequalities.rows()!=4 || h->upper_bounds[0]!=2.0 ||
       h->upper_bounds[1]!=2.0 || h->upper_bounds[2]!=2.0 ||
       h->upper_bounds[3]!=2.0)return 7;
    std::cout << "Installed box/parallelotope client: rotated diamond bounds passed\n";
}
