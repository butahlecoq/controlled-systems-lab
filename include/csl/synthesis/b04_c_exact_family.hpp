#pragma once

#include <csl/synthesis/contracts.hpp>

#include <span>
#include <string_view>

namespace csl::synthesis::b04_c {

inline constexpr char exact_family_profile[] = "strategy-a.b04-c-exact-dyadic-v1";
inline constexpr char exact_family_representation[] = "csl.joint-history.b04-c-exact-rational-v1";
inline constexpr std::size_t exact_family_horizon = 16;

// Decimal integer strings keep non-dyadic history coordinates exact without
// exposing the verifier's private bigint implementation.
struct RationalCoordinate {
    std::string_view numerator;
    std::string_view denominator;
    int binary_exponent{};
};

enum class HistoryMembership {
    member,
    not_member,
    unsupported_relation,
    invalid_input,
    resource_limit
};

// Checks one full canonical history (x0,...,x16,u0,...,u15). It accepts only
// the compiled B04-C exact-rational payload and applies bounded exact arithmetic.
HistoryMembership contains_exact_history(const JointRelation &,
                                         std::span<const RationalCoordinate> history);

} // namespace csl::synthesis::b04_c
