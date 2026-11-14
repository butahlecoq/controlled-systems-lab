#pragma once

#include <cmath>
#include <optional>
#include <span>
#include <utility>

#include <csl/optimization/running_control_cost.hpp>

namespace csl::optimization::detail {

// Positive binary-scaled arithmetic keeps intermediate products in range.
// It is deliberately independent of extended precision, whose width varies
// by compiler and platform.
struct ScaledPositive {
    double fraction{};
    int exponent{};
};

inline ScaledPositive scaled(double value) {
    int exponent = 0;
    const double fraction = std::frexp(value, &exponent);
    return {fraction, exponent};
}

inline ScaledPositive multiply(ScaledPositive left, ScaledPositive right) {
    int adjustment = 0;
    const double fraction = std::frexp(left.fraction * right.fraction, &adjustment);
    return {fraction, left.exponent + right.exponent + adjustment};
}

inline ScaledPositive divide(ScaledPositive numerator, ScaledPositive denominator) {
    int adjustment = 0;
    const double fraction = std::frexp(numerator.fraction / denominator.fraction, &adjustment);
    return {fraction, numerator.exponent - denominator.exponent + adjustment};
}

inline ScaledPositive add(ScaledPositive left, ScaledPositive right) {
    if (left.fraction == 0.0)
        return right;
    if (right.fraction == 0.0)
        return left;
    if (left.exponent < right.exponent)
        std::swap(left, right);
    const int gap = right.exponent - left.exponent;
    const double aligned = gap < -1075 ? 0.0 : std::scalbn(right.fraction, gap);
    int adjustment = 0;
    const double fraction = std::frexp(left.fraction + aligned, &adjustment);
    return {fraction, left.exponent + adjustment};
}

inline ScaledPositive positive_difference(double left, double right) {
    const double a = std::abs(left), b = std::abs(right);
    if (std::signbit(left) != std::signbit(right))
        return add(scaled(a), scaled(b));
    return scaled(std::abs(left - right));
}

inline std::optional<double> materialize(ScaledPositive value) {
    if (value.fraction == 0.0)
        return 0.0;
    const double result = std::scalbn(value.fraction, value.exponent);
    if (!std::isfinite(result) || result == 0.0)
        return std::nullopt;
    return result;
}

inline std::optional<double> quadratic_stage_cost(const QuadraticControlPenalty &penalty,
                                                  std::span<const double> control) {
    if (penalty.coefficient == 0.0)
        return 0.0;
    ScaledPositive sum{};
    for (std::size_t i = 0; i < control.size(); ++i) {
        if (penalty.weights[i] == 0.0)
            continue;
        auto residual = divide(positive_difference(control[i], penalty.reference[i]),
                               scaled(std::abs(penalty.scales[i])));
        auto term = multiply(scaled(penalty.weights[i]), multiply(residual, residual));
        sum = add(sum, term);
    }
    if (sum.fraction == 0.0)
        return 0.0;
    auto value = divide(multiply(scaled(penalty.coefficient), sum),
                        scaled(static_cast<double>(penalty.normalization_horizon)));
    return materialize(value);
}

} // namespace csl::optimization::detail
