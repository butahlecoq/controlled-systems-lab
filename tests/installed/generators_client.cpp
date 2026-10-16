#include <csl/geometry/generators.hpp>

int main() {
    using namespace csl;
    auto input=sets::make_generator_set({{"segment"},{1},{1,1,{2}},
        {{"shared"}},{0,1,{}},{},{}});
    if (!std::holds_alternative<sets::GeneratorSet>(input)) return 1;
    const auto& segment=std::get<sets::GeneratorSet>(input);
    const auto image=geometry::generators::affine_image(segment,{1,1,{-1}},{4},{"image"});
    if (!std::holds_alternative<sets::GeneratorSet>(image)) return 2;
    const auto& transformed=std::get<sets::GeneratorSet>(image);
    return transformed.center()==Vector{3} && transformed.generators().values==Vector{-2} &&
        transformed.factor_ids()==std::vector<sets::FactorId>{{"shared"}} ? 0 : 3;
}
