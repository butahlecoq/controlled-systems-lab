#include <csl/registry/registry.hpp>

int main() {
    csl::registry::StrategyRegistration registration;
    registration.complete_family_verifier = [](const csl::registry::StrategyRequest&,
        const csl::CompleteFamilyProposal&) { return csl::Diagnostics{}; };
    return 0;
}