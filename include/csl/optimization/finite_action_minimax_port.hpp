#pragma once

#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/registry/registry.hpp>

namespace csl::optimization {

// One immutable registry query: the complete finite catalogue and caller limits.
struct FiniteActionMinimaxQuery {
    FiniteActionMinimaxRequest request;
    FiniteActionMinimaxLimits limits;
};

class FiniteActionMinimaxWorkspace : public ExclusiveWorkspace {
public:
    virtual FiniteActionMinimaxOutcome solve(const FiniteActionMinimaxQuery&,
        const ExecutionContext&) = 0;
};

} // namespace csl::optimization

namespace csl::registry {

struct FiniteActionMinimaxPort {
    using Request = optimization::FiniteActionMinimaxQuery;
    using Workspace = optimization::FiniteActionMinimaxWorkspace;
    static constexpr const char* name = "finite-action-minimax";
    static Request snapshot(const Request& request) { return request; }
    static optimization::FiniteActionMinimaxOutcome run(Workspace&,
        const Request&,const ExecutionContext&);
};

} // namespace csl::registry

namespace csl::optimization {

// Scalar numerical outcome; no set relation or optimal-family publication.
registry::Requirements finite_action_minimax_requirements();
registry::Registration<registry::FiniteActionMinimaxPort>
    make_finite_action_minimax_registration();

} // namespace csl::optimization
