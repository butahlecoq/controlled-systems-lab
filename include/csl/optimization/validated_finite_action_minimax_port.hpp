#pragma once

#include <csl/optimization/validated_finite_action_minimax.hpp>
#include <csl/registry/registry.hpp>

namespace csl::optimization {

struct ValidatedFiniteActionMinimaxQuery {
    ValidatedFiniteActionMinimaxRequest request;
    ValidatedFiniteActionMinimaxLimits limits;
};

class ValidatedFiniteActionMinimaxWorkspace : public ExclusiveWorkspace {
public:
    virtual ValidatedFiniteActionMinimaxOutcome solve(
        const ValidatedFiniteActionMinimaxQuery&, const ExecutionContext&) = 0;
};

} // namespace csl::optimization

namespace csl::registry {

struct ValidatedFiniteActionMinimaxPort {
    using Request = optimization::ValidatedFiniteActionMinimaxQuery;
    using Workspace = optimization::ValidatedFiniteActionMinimaxWorkspace;
    static constexpr const char* name = "validated-finite-action-minimax";
    static constexpr bool accepts_validated_assurance = true;
    static Request snapshot(const Request& request) { return request; }
    static optimization::ValidatedFiniteActionMinimaxOutcome run(
        Workspace&, const Request&, const ExecutionContext&);
};

} // namespace csl::registry

namespace csl::optimization {

registry::Requirements validated_finite_action_minimax_requirements();
registry::Registration<registry::ValidatedFiniteActionMinimaxPort>
    make_validated_finite_action_minimax_registration();

} // namespace csl::optimization
