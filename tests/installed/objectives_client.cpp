#include <csl/optimization/objectives.hpp>
#include <cmath>
#include <iostream>

int main() {
    using namespace csl;
    using namespace csl::optimization;
    auto published = snapshot(ResidualNormTerminal{{3, 2, {1, 0, 0, 2, 1, -1}}, {1, 2, 0}});
    const auto* original = std::get_if<Objective>(&published);
    if (!original) return 1;
    auto transformed = square_residual_norm(*original);
    const auto* record = std::get_if<NormSquareReformulation>(&transformed);
    if (!record) return 2;
    const auto data = record->squared().coefficients();
    const auto* quadratic = std::get_if<QuadraticCoefficients>(&data);
    if (!quadratic || quadratic->Q(0, 0) != 4 || quadratic->Q(0, 1) != -2 ||
        quadratic->Q(1, 0) != -2 || quadratic->Q(1, 1) != 10 ||
        quadratic->linear[0] != -2 || quadratic->linear[1] != -8 || quadratic->offset != 5) return 3;
    auto norm = evaluate(record->original(), Vector{3, 1});
    auto square = evaluate(record->squared(), Vector{3, 1});
    const auto* norm_value = std::get_if<double>(&norm);
    const auto* square_value = std::get_if<double>(&square);
    if (!norm_value || !square_value || std::abs(*norm_value - 2.8284271247461903) > 1e-14 || *square_value != 8) return 4;
    auto zero = evaluate(record->original(), Vector{1, 1});
    if (!std::holds_alternative<double>(zero) || std::get<double>(zero) != 0) return 5;
    std::cout << "Objective client: rectangular reformulation and independent original cost passed\n";
}
