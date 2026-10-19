#include <csl/geometry/approximation.hpp>
#include <csl/geometry/zonotope_reduction.hpp>
#include <csl/sets/generator_sets.hpp>
#include <iostream>

int main() {
    using namespace csl;
    using namespace csl::geometry::approximation;
    const auto source=sets::make_generator_set({{"installed-source"},{0,0},
        {2,3,{1,0,0.5,0,1,0.5}},{{"x"},{"y"},{"diagonal"}},
        {0,3,{}},{},{"x","y"}});
    if(!std::holds_alternative<sets::GeneratorSet>(source))return 1;
    const ApproximationRequest request{{{"installed-problem"},{"installed-request"},{"source-set"}},
        std::get<sets::GeneratorSet>(source).as_handle(),{"csl.zonotope"},
        SetRelation::outer,2,Assurance::numerical};
    registry::Registry<registry::ApproximationPort> methods;
    if(methods.add(make_axis_cover_registration({"installed-cover"})))return 2;
    const auto outcome=run_registered(methods,
        {{"csl.geometry.zonotope.axis-cover"},std::nullopt},request,ExecutionContext{});
    if(!std::holds_alternative<EnclosedApproximation>(outcome))return 3;
    const auto& enclosed=std::get<EnclosedApproximation>(outcome);
    if(enclosed.basis!=StructuralBasis::generator_axis_cover)return 4;
    const auto output=sets::from_generator_handle(enclosed.result.output);
    if(!std::holds_alternative<sets::GeneratorSet>(output))return 5;
    const auto& cover=std::get<sets::GeneratorSet>(output);
    if(cover.factor_ids().size()!=2 ||
       cover.generators().values!=Vector{1.5,0,0,1.5})return 6;
    std::cout << "Installed zonotope client: independently admitted axis cover passed\n";
}
