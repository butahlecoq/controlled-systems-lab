#pragma once

#include "exact_rational.hpp"

#include <csl/synthesis/contracts.hpp>

#include <array>
#include <span>
#include <utility>
#include <vector>

namespace csl::synthesis::detail::b04_c {

using exact_rational::Budget;
using exact_rational::Rational;

inline constexpr std::size_t control_dimension = 16;
inline constexpr std::size_t state_dimension = 4;
inline constexpr std::size_t horizon = 16;
inline constexpr std::size_t history_dimension =
    state_dimension * (horizon + 1) + control_dimension;

struct LinearRow {
    std::vector<Rational> coefficients;
    Rational bound;
    friend bool operator==(const LinearRow&, const LinearRow&) = default;
};

struct AffineEquality {
    std::vector<Rational> coefficients;
    Rational offset;
    friend bool operator==(const AffineEquality&, const AffineEquality&) = default;
};

struct AffineState {
    std::array<Rational, state_dimension> offset;
    std::array<std::array<Rational, control_dimension>, state_dimension> controls;
    friend bool operator==(const AffineState&, const AffineState&) = default;
};

enum class Membership { member, not_member, resource_limit, invalid_relation };

class ExactFamilyPayload final : public JointRelationPayload {
public:
    std::vector<LinearRow> feasible_controls;
    std::vector<AffineEquality> terminal_fiber;
    std::array<AffineState, horizon + 1> history_lift;
    std::array<Rational, state_dimension> unique_terminal;
    std::vector<Rational> optimal_controls;

    Membership contains(std::span<const Rational> history, Budget& budget) const {
        if (history.size() != history_dimension || feasible_controls.size() != 100 ||
            terminal_fiber.size() != state_dimension)
            return Membership::invalid_relation;
        const auto controls = history.subspan(state_dimension * (horizon + 1),
            control_dimension);
        for (const auto& row : feasible_controls) {
            if (row.coefficients.size() != control_dimension)
                return Membership::invalid_relation;
            Rational value;
            if (!dot(row.coefficients, controls, value, budget))
                return Membership::resource_limit;
            int order{};
            if (!exact_rational::compare(value, row.bound, order, budget))
                return Membership::resource_limit;
            if (order > 0)
                return Membership::not_member;
        }
        for (std::size_t coordinate = 0; coordinate < terminal_fiber.size(); ++coordinate) {
            const auto& row = terminal_fiber[coordinate];
            if (row.coefficients.size() != control_dimension)
                return Membership::invalid_relation;
            Rational value;
            if (!dot(row.coefficients, controls, value, budget))
                return Membership::resource_limit;
            Rational adjusted;
            if (!exact_rational::add(value, row.offset, adjusted, budget))
                return Membership::resource_limit;
            bool equal{};
            if (!exact_rational::equal(adjusted, unique_terminal[coordinate], equal, budget))
                return Membership::resource_limit;
            if (!equal)
                return Membership::not_member;
        }

        for (std::size_t stage = 0; stage <= horizon; ++stage) {
            const auto& map = history_lift[stage];
            for (std::size_t coordinate = 0; coordinate < state_dimension; ++coordinate) {
                Rational expected = map.offset[coordinate];
                for (std::size_t control = 0; control < control_dimension; ++control) {
                    Rational product;
                    Rational sum;
                    if (!exact_rational::multiply(map.controls[coordinate][control],
                            controls[control], product, budget) ||
                        !exact_rational::add(expected, product, sum, budget))
                        return Membership::resource_limit;
                    expected = std::move(sum);
                }
                bool equal{};
                const auto index = stage * state_dimension + coordinate;
                if (!exact_rational::equal(expected, history[index], equal, budget))
                    return Membership::resource_limit;
                if (!equal)
                    return Membership::not_member;
            }
        }
        return Membership::member;
    }

private:
    static bool dot(std::span<const Rational> lhs, std::span<const Rational> rhs,
                    Rational& result, Budget& budget) {
        if (lhs.size() != rhs.size())
            return false;
        result = {};
        for (std::size_t index = 0; index < lhs.size(); ++index) {
            Rational product;
            Rational sum;
            if (!exact_rational::multiply(lhs[index], rhs[index], product, budget) ||
                !exact_rational::add(result, product, sum, budget))
                return false;
            result = std::move(sum);
        }
        return true;
    }
};

} // namespace csl::synthesis::detail::b04_c
