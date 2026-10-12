#include <csl/geometry/polyhedral_intersection.hpp>

#include <iostream>
#include <stdexcept>

namespace {
template<class T> T take(std::variant<T, csl::Diagnostic> result) {
    if (const auto* error = std::get_if<csl::Diagnostic>(&result))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(result));
}
void require(bool condition) {
    if (!condition) throw std::runtime_error("Installed polyhedral intersection fixture failed.");
}
}

int main() {
    using namespace csl;
    auto left = take(sets::make_h({{"installed-left"},1,{}},
        {take(numeric::snapshot(Matrix{1,1,{1}})), take(numeric::snapshot_vector(Vector{1})),
         take(numeric::snapshot(Matrix{0,1,{}})), take(numeric::snapshot_vector(Vector{}))}));
    auto right = take(sets::make_h({{"installed-right"},1,{}},
        {take(numeric::snapshot(Matrix{1,1,{-1}})), take(numeric::snapshot_vector(Vector{0})),
         take(numeric::snapshot(Matrix{0,1,{}})), take(numeric::snapshot_vector(Vector{}))}));
    const auto intersection = geometry::polyhedral::intersect_h(left, right, {"installed-intersection"});
    require(std::holds_alternative<sets::SetData>(intersection));
    const auto representation = std::get<sets::SetData>(intersection).representation();
    require(std::holds_alternative<sets::HRepresentation>(representation));
    require(std::get<sets::HRepresentation>(representation).inequalities.rows() == 2);
    std::cout << "Installed polyhedral client: public H intersection passed\n";
}
