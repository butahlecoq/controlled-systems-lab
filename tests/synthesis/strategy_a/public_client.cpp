#include <csl/synthesis/strategy_a/strategy.hpp>
#include <type_traits>

static_assert(std::is_base_of_v<csl::JointRelationPayload,csl::synthesis::strategy_a::CandidateHistory>);
using RegistrationFactory=csl::registry::StrategyRegistration(*)(csl::synthesis::strategy_a::Providers);
RegistrationFactory volatile registration_factory=&csl::synthesis::strategy_a::make_registration;

int main() {
    return registration_factory==nullptr?1:0;
}
