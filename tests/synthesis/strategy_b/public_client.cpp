#include <csl/synthesis/strategy_b/direct_joint.hpp>

using RegistrationFactory = csl::registry::StrategyRegistration (*)(
    const csl::registry::Registry<csl::registry::LPPort> &,
    const csl::registry::Registry<csl::registry::ConvexPort> &);

RegistrationFactory volatile registration_factory = &csl::synthesis::strategy_b::make_registration;

int main() { return registration_factory != nullptr ? 0 : 1; }
