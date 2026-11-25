#pragma once

#include "../synthesis/exact_rational.hpp"

#include <csl/optimization/objectives.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>

#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstdint>
#include <limits>
#include <optional>
#include <span>
#include <stdexcept>
#include <string_view>
#include <vector>

namespace csl::optimization::detail {

namespace exact = synthesis::detail::exact_rational;
using Pair = std::array<exact::Rational, 2>;
struct ArithmeticLimit {};

class Arithmetic {
    exact::Budget budget_;

  public:
    exact::Rational decode(double value) {
        exact::Rational result;
        if (!exact::from_binary64(value, result, budget_))
            throw ArithmeticLimit{};
        return result;
    }
    exact::Rational add(const exact::Rational &a, const exact::Rational &b) {
        exact::Rational result;
        if (!exact::add(a, b, result, budget_))
            throw ArithmeticLimit{};
        return result;
    }
    exact::Rational subtract(const exact::Rational &a, const exact::Rational &b) {
        exact::Rational result;
        if (!exact::subtract(a, b, result, budget_))
            throw ArithmeticLimit{};
        return result;
    }
    exact::Rational multiply(const exact::Rational &a, const exact::Rational &b) {
        exact::Rational result;
        if (!exact::multiply(a, b, result, budget_))
            throw ArithmeticLimit{};
        return result;
    }
    int compare(const exact::Rational &a, const exact::Rational &b) {
        int order;
        if (!exact::compare(a, b, order, budget_))
            throw ArithmeticLimit{};
        return order;
    }
};

template <class CheckStop>
exact::Rational maximum_planar_quadratic(Pair center, std::span<const Pair> factors,
                                         const Pair &quadratic, const Pair &linear,
                                         Arithmetic &arithmetic, CheckStop check_stop) {
    const exact::Rational zero;
    if (arithmetic.compare(quadratic[0], zero) < 0 || arithmetic.compare(quadratic[1], zero) < 0)
        throw std::invalid_argument("Convex planar score needs nonnegative quadratic weights.");

    // With all factor directions in the closed upper half-plane the zonotope
    // boundary is c - sum(g) followed by the doubled generators in angular
    // order. Walking that sequence forwards and then backwards visits every
    // boundary vertex, including tied and opposite directions.
    std::vector<Pair> edges;
    edges.reserve(factors.size());
    for (auto g : factors) {
        check_stop();
        const int y = arithmetic.compare(g[1], zero);
        const int x = arithmetic.compare(g[0], zero);
        if (x == 0 && y == 0)
            continue;
        if (y < 0 || (y == 0 && x < 0))
            for (auto &v : g)
                v = arithmetic.subtract(zero, v);
        for (std::size_t axis = 0; axis < g.size(); ++axis)
            center[axis] = arithmetic.subtract(center[axis], g[axis]);
        for (auto &v : g)
            v = arithmetic.add(v, v);
        edges.push_back(std::move(g));
    }
    std::ranges::sort(edges, [&](const Pair &a, const Pair &b) {
        check_stop();
        const auto left = arithmetic.multiply(a[0], b[1]);
        const auto right = arithmetic.multiply(a[1], b[0]);
        return arithmetic.compare(left, right) > 0;
    });
    const auto evaluate = [&] {
        exact::Rational value;
        for (std::size_t axis = 0; axis < center.size(); ++axis) {
            const auto gradient =
                arithmetic.add(arithmetic.multiply(quadratic[axis], center[axis]), linear[axis]);
            value = arithmetic.add(value, arithmetic.multiply(center[axis], gradient));
        }
        return value;
    };
    auto best = evaluate();
    for (const bool reverse : {false, true})
        for (const auto &edge : edges) {
            check_stop();
            for (std::size_t axis = 0; axis < edge.size(); ++axis)
                center[axis] = reverse ? arithmetic.subtract(center[axis], edge[axis])
                                       : arithmetic.add(center[axis], edge[axis]);
            auto value = evaluate();
            if (arithmetic.compare(value, best) > 0)
                best = std::move(value);
        }
    return best;
}

// Least finite binary64 at least the exact value. Norm reporting squares into
// the same exact comparison, so the returned double is never below the score.
inline double outward_planar_score(const exact::Rational &value, bool square_root,
                                   Arithmetic &arithmetic) {
    if (!square_root) {
        const auto bounds = exact::exact_h::bracket_binary64(
            {value.numerator, value.denominator, value.binary_exponent},
            exact::default_max_integer_bits);
        if (bounds.status != exact::exact_h::Binary64BracketStatus::finite)
            throw ArithmeticLimit{};
        return bounds.upper;
    }
    constexpr std::uint64_t largest = 0x7fefffffffffffffULL;
    const auto large = arithmetic.decode(std::bit_cast<double>(largest));
    if (arithmetic.compare(arithmetic.multiply(large, large), value) < 0)
        throw ArithmeticLimit{};
    std::uint64_t first = 0, last = largest;
    while (first < last) {
        const auto mid = first + (last - first) / 2;
        const auto candidate = arithmetic.decode(std::bit_cast<double>(mid));
        if (arithmetic.compare(arithmetic.multiply(candidate, candidate), value) < 0)
            first = mid + 1;
        else
            last = mid;
    }
    return std::bit_cast<double>(first);
}

struct PlanarTerminalScore {
    double value{};
    std::size_t visits{};
    std::string_view method{};
};

using PlanarTerminalOutcome = std::variant<PlanarTerminalScore, OperationStopped>;

// Scores one terminal zonotope without enumerating factor corners. Returns an
// empty optional when the stored objective and factor structure do not admit
// an independent planar reduction, so the caller preserves its refusal.
template <class CheckStop>
std::optional<PlanarTerminalOutcome>
try_planar_zonotope_score(const reachability::FinitePlanZonotopeTrace::Stage &terminal,
                          const Objective &objective, std::size_t visit_limit,
                          CheckStop check_stop) {
    const auto n = terminal.center.size();
    const auto m = terminal.generators.cols;
    if (n == 0 || n > 64 || m == 0 || n != objective.dimension() || terminal.generators.rows != n ||
        terminal.generators.values.size() != n * m ||
        objective.policy().assurance != Assurance::numerical)
        return std::nullopt;
    const auto coefficients = objective.coefficients();
    Arithmetic arithmetic;
    std::size_t visits = 0;
    const auto maximum = [&](Pair center, const std::vector<Pair> &factors, const Pair &weights,
                             const Pair &linear) {
        const auto needed = 2 * factors.size() + 1;
        if (visits > visit_limit || needed > visit_limit - visits)
            throw OperationStopped{StopReason::resource_limit,
                                   "Planar zonotope score exceeds the terminal vertex budget."};
        visits += needed;
        return maximum_planar_quadratic(std::move(center), factors, weights, linear, arithmetic,
                                        check_stop);
    };
    const auto entry = [&](std::size_t row, std::size_t col) {
        return terminal.generators.values[row * m + col];
    };
    const auto finite = [&] {
        for (const auto value : terminal.center)
            if (!std::isfinite(value))
                return false;
        return std::ranges::all_of(terminal.generators.values,
                                   [](double value) { return std::isfinite(value); });
    };
    try {
        check_stop();
        if (!finite())
            return OperationStopped{StopReason::numerical_failure,
                                    "Nonfinite planar zonotope data."};
        if (const auto *residual = std::get_if<ResidualCoefficients>(&coefficients)) {
            if (residual->map.rows() != 2 || residual->map.cols() != n ||
                residual->target.size() != 2 ||
                (residual->weights && residual->weights->size() != 2))
                return std::nullopt;
            Pair center, weights;
            std::vector<Pair> factors(m);
            for (std::size_t row = 0; row < 2; ++row) {
                const auto weight = residual->weights ? (*residual->weights)[row] : 1.0;
                if (!std::isfinite(residual->target[row]) || !std::isfinite(weight) || weight < 0)
                    return OperationStopped{StopReason::numerical_failure,
                                            "Nonfinite planar residual coefficients."};
                center[row] = arithmetic.decode(-residual->target[row]);
                weights[row] = arithmetic.decode(weight);
                for (std::size_t i = 0; i < n; ++i) {
                    check_stop();
                    if (residual->map(row, i) == 0)
                        continue;
                    if (!std::isfinite(residual->map(row, i)))
                        return OperationStopped{StopReason::numerical_failure,
                                                "Nonfinite planar residual map."};
                    const auto scale = arithmetic.decode(residual->map(row, i));
                    center[row] = arithmetic.add(
                        center[row],
                        arithmetic.multiply(scale, arithmetic.decode(terminal.center[i])));
                    for (std::size_t j = 0; j < m; ++j)
                        factors[j][row] = arithmetic.add(
                            factors[j][row],
                            arithmetic.multiply(scale, arithmetic.decode(entry(i, j))));
                }
            }
            const auto score = maximum(std::move(center), factors, weights, {});
            return PlanarTerminalScore{outward_planar_score(score, true, arithmetic), visits,
                                       "exact-planar-residual-sweep/1"};
        }

        const auto *quadratic = std::get_if<QuadraticCoefficients>(&coefficients);
        if (!quadratic)
            return std::nullopt;
        for (std::size_t i = 0; i < n; ++i) {
            if (!std::isfinite(quadratic->Q(i, i)) || quadratic->Q(i, i) < 0 ||
                !std::isfinite(quadratic->linear[i]))
                return std::nullopt;
            for (std::size_t j = 0; j < n; ++j)
                if (i != j && quadratic->Q(i, j) != 0)
                    return std::nullopt;
        }
        if (!std::isfinite(quadratic->offset))
            return std::nullopt;

        // The stored factor columns must split into disjoint blocks of one or
        // two coordinates; the diagonal objective is then additive over them.
        std::vector<std::size_t> partner(n, n);
        for (std::size_t j = 0; j < m; ++j) {
            check_stop();
            std::size_t a = n, b = n;
            for (std::size_t i = 0; i < n; ++i) {
                if (entry(i, j) == 0)
                    continue;
                if (a == n)
                    a = i;
                else if (b == n)
                    b = i;
                else
                    return std::nullopt;
            }
            if (b == n)
                continue;
            if ((partner[a] != n && partner[a] != b) || (partner[b] != n && partner[b] != a))
                return std::nullopt;
            partner[a] = b;
            partner[b] = a;
        }

        auto score = arithmetic.decode(quadratic->offset);
        for (std::size_t a = 0; a < n; ++a) {
            check_stop();
            const auto b = partner[a];
            if (b < a)
                continue;
            Pair center, weights, linear;
            const auto half = arithmetic.decode(0.5);
            const auto prepare_coordinate = [&](std::size_t slot, std::size_t index) {
                center[slot] = arithmetic.decode(terminal.center[index]);
                weights[slot] =
                    arithmetic.multiply(half, arithmetic.decode(quadratic->Q(index, index)));
                linear[slot] = arithmetic.decode(quadratic->linear[index]);
            };
            prepare_coordinate(0, a);
            if (b != n)
                prepare_coordinate(1, b);
            std::vector<Pair> factors;
            for (std::size_t j = 0; j < m; ++j) {
                const auto x = entry(a, j);
                const auto y = b == n ? 0 : entry(b, j);
                if (x != 0 || y != 0)
                    factors.push_back({arithmetic.decode(x), arithmetic.decode(y)});
            }
            score = arithmetic.add(score, maximum(std::move(center), factors, weights, linear));
        }
        return PlanarTerminalScore{outward_planar_score(score, false, arithmetic), visits,
                                   "exact-separable-quadratic-sweep/1"};
    } catch (const OperationStopped &reason) {
        return reason;
    } catch (const detail::ArithmeticLimit &) {
        return OperationStopped{StopReason::resource_limit,
                                "Exact planar zonotope scoring exceeded its arithmetic budget."};
    }
}

} // namespace csl::optimization::detail
