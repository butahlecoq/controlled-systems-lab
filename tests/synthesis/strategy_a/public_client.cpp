#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/b04_c_exact_family.hpp>
#include <type_traits>

static_assert(std::is_base_of_v<csl::JointRelationPayload,csl::synthesis::strategy_a::CandidateHistory>);
using RegistrationFactory=csl::registry::StrategyRegistration(*)(csl::synthesis::strategy_a::Providers);
RegistrationFactory volatile registration_factory=&csl::synthesis::strategy_a::make_registration;

int main() {
    const csl::JointRelation unsupported{};
    const auto query=csl::synthesis::b04_c::contains_exact_history(
        unsupported,std::span<const csl::synthesis::b04_c::RationalCoordinate>{});
    return registration_factory!=nullptr &&
        query==csl::synthesis::b04_c::HistoryMembership::unsupported_relation?0:1;
}
