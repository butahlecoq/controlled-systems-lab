#include <csl/synthesis/b04_c_exact_family.hpp>

#include "b04_c_exact_family.hpp"

#include <algorithm>
#include <new>
#include <stdexcept>
#include <string>
#include <vector>

namespace csl::synthesis::b04_c {
namespace {

bool decimal_syntax(std::string_view value) {
    if (value.empty())
        return false;
    if (value.front() == '-')
        value.remove_prefix(1);
    if (value.empty())
        return false;
    return std::all_of(value.begin(), value.end(), [](char digit) {
        return digit >= '0' && digit <= '9';
    });
}

bool exceeds_decimal_bit_cap(std::string_view value) {
    if (!decimal_syntax(value))
        return false;
    if (value.front() == '-')
        value.remove_prefix(1);
    const auto first_nonzero = value.find_first_not_of('0');
    if (first_nonzero == std::string_view::npos)
        return false;
    value.remove_prefix(first_nonzero);
    // Conservatively refuse the boundary length: some 2467-digit values fit
    // 8192 bits, while others exceed it. A refusal is preferable to mislabeling
    // an arithmetic cap as malformed caller input.
    return value.size() >= 2467;
}

} // namespace

HistoryMembership contains_exact_history(
    const JointRelation& relation, std::span<const RationalCoordinate> history) {
    if (relation.representation.value != exact_family_representation)
        return HistoryMembership::unsupported_relation;
    if (relation.coordinates != JointCoordinates{{4, 1, 0}, 16})
        return HistoryMembership::invalid_input;
    const auto* exact = dynamic_cast<const detail::b04_c::ExactFamilyPayload*>(
        relation.payload.get());
    if (!exact)
        return HistoryMembership::unsupported_relation;
    if (history.size() != detail::b04_c::history_dimension)
        return HistoryMembership::invalid_input;

    detail::exact_rational::Budget budget;
    budget.max_operations = 2'000'000;
    std::vector<detail::exact_rational::Rational> point;
    try {
        point.reserve(history.size());
        constexpr std::size_t max_decimal_digits = 2500;
        for (const auto& coordinate : history) {
            if (coordinate.numerator.empty() || coordinate.denominator.empty() ||
                coordinate.numerator.size() > max_decimal_digits ||
                coordinate.denominator.size() > max_decimal_digits)
                return HistoryMembership::resource_limit;
            if (exceeds_decimal_bit_cap(coordinate.numerator) ||
                exceeds_decimal_bit_cap(coordinate.denominator))
                return HistoryMembership::resource_limit;
            std::string fraction;
            fraction.reserve(coordinate.numerator.size() + coordinate.denominator.size() + 1);
            fraction.append(coordinate.numerator);
            fraction.push_back('/');
            fraction.append(coordinate.denominator);
            detail::exact_rational::Rational value;
            if (!detail::exact_rational::parse(fraction, value, budget)) {
                if (budget.operations >= budget.max_operations ||
                    budget.maximum_integer_bits > budget.max_integer_bits)
                    return HistoryMembership::resource_limit;
                return HistoryMembership::invalid_input;
            }
            value.binary_exponent = coordinate.binary_exponent;
            if (!detail::exact_rational::normalize(value, budget))
                return HistoryMembership::resource_limit;
            point.push_back(std::move(value));
        }
    } catch (const std::bad_alloc&) {
        return HistoryMembership::resource_limit;
    } catch (const std::length_error&) {
        return HistoryMembership::resource_limit;
    }

    detail::b04_c::Membership membership;
    try {
        membership = exact->contains(point, budget);
    } catch (const std::bad_alloc&) {
        return HistoryMembership::resource_limit;
    } catch (const std::length_error&) {
        return HistoryMembership::resource_limit;
    }
    switch (membership) {
    case detail::b04_c::Membership::member:
        return HistoryMembership::member;
    case detail::b04_c::Membership::not_member:
        return HistoryMembership::not_member;
    case detail::b04_c::Membership::resource_limit:
        return HistoryMembership::resource_limit;
    case detail::b04_c::Membership::invalid_relation:
        return HistoryMembership::unsupported_relation;
    }
    return HistoryMembership::unsupported_relation;
}

} // namespace csl::synthesis::b04_c
