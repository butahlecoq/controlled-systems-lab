#include <csl/sets/data.hpp>

#include <iostream>
#include <stdexcept>

namespace {
template<class T> T take(std::variant<T, csl::Diagnostic> result) {
    if (const auto* error = std::get_if<csl::Diagnostic>(&result))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(result));
}
void require(bool condition) {
    if (!condition) throw std::runtime_error("Installed set data fixture failed.");
}
}

int main() {
    using namespace csl;
    using namespace csl::sets;
    auto exported = [] {
        Description description{{"installed-segment"}, 2, {"x", "y"}};
        HRepresentation h{
            take(numeric::snapshot(Matrix{2, 2, {-1, 0, 1, 0}})),
            take(numeric::snapshot_vector(Vector{1, 2})),
            take(numeric::snapshot(Matrix{1, 2, {0, 1}})),
            take(numeric::snapshot_vector(Vector{0}))};
        return take(make_h(description, h, AffineDimensionClaim{DimensionValue{1},
            SymbolicArgument{"literal segment", "y=0 and -1<=x<=2"}})).as_handle();
    }();
    auto set = take(from_handle(exported));
    auto info = set.metadata();
    auto h = std::get<HRepresentation>(set.representation());
    require(info->set.dimension == 2 && info->coordinate_labels[1] == "y");
    require(std::get<DimensionValue>(info->affine_dimension->claim.value).value == 1);
    require(info->affine_dimension->origin == DimensionOrigin::supplied);
    require(h.inequalities(0, 0) == -1 && h.upper_bounds[1] == 2 && h.equalities(0, 1) == 1);

    auto point = take(make_singleton({{"point"}, 2, {}}, take(numeric::snapshot_vector(Vector{3, -4}))));
    require(std::get<SingletonRepresentation>(point.representation()).point[1] == -4);
    auto empty = take(make_empty({{"empty"}, 0, {}}));
    auto universal = take(make_universal({{"universal"}, 0, {}}));
    require(std::holds_alternative<EmptyRepresentation>(empty.representation()));
    require(std::holds_alternative<UniversalRepresentation>(universal.representation()));
    require(std::get<DimensionValue>(universal.metadata()->affine_dimension->claim.value).value == 0);
    require(empty.metadata()->set.representation.value != universal.metadata()->set.representation.value);
    std::cout << "Installed sets client: retained H segment and elementary zero-dimensional cases passed\n";
}
