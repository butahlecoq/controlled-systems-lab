#pragma once
#include <csl/contracts.hpp>
#include <optional>
#include <utility>

namespace csl::adapters::highs_detail {
template<class Evidence> struct CertificateVerificationResult {
    std::optional<Evidence> evidence;
    std::optional<Termination> stop;
};

// A final stop poll runs after expensive verification but before its evidence
// can become caller-visible. The callback owns cancellation/deadline priority.
template<class Verify,class Poll> auto verify_then_poll(Verify&& verify,Poll&& poll) {
    auto evidence=verify();
    auto stop=poll();
    using Evidence=typename decltype(evidence)::value_type;
    if(stop)return CertificateVerificationResult<Evidence>{std::nullopt,std::move(stop)};
    return CertificateVerificationResult<Evidence>{std::move(evidence),std::nullopt};
}
} // namespace csl::adapters::highs_detail
