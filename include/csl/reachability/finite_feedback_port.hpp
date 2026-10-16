#pragma once

#include <csl/reachability/finite_feedback.hpp>
#include <csl/registry/registry.hpp>

namespace csl::reachability::finite_feedback {

struct Request {
    ProblemId problem;
    RequestId request;
    Game game;
};

using PortResult = std::variant<Policy,Diagnostic,OperationStopped>;
class Workspace : public ExclusiveWorkspace {
public:
    virtual PortResult compute(const Request&,const ExecutionContext&) = 0;
};

struct RegisteredPolicy {
    ProblemId problem;
    RequestId request;
    registry::Provenance provider;
    Policy policy;
};
struct RegisteredFailure {
    ProblemId problem;
    RequestId request;
    registry::Provenance provider;
    Diagnostics diagnostics;
};
struct RegisteredStopped {
    ProblemId problem;
    RequestId request;
    registry::Provenance provider;
    OperationStopped stop;
};
using RegisteredOutcome = std::variant<RegisteredPolicy,RegisteredFailure,RegisteredStopped>;

} // namespace csl::reachability::finite_feedback

namespace csl::registry {
struct FiniteFeedbackPort {
    using Request = reachability::finite_feedback::Request;
    using Workspace = reachability::finite_feedback::Workspace;
    static constexpr const char* name = "finite-feedback";
    static Request snapshot(const Request& request) { return request; }
    static reachability::finite_feedback::PortResult run(Workspace&,const Request&,
        const ExecutionContext&);
};
} // namespace csl::registry

namespace csl::reachability::finite_feedback {

// Current registry revision requires binary64 admission metadata even though
// this table algorithm performs no floating-point arithmetic.
registry::Requirements finite_table_requirements();
registry::Registration<registry::FiniteFeedbackPort> make_registration();
RegisteredOutcome run_registered(const registry::Registry<registry::FiniteFeedbackPort>&,
    registry::Method,const Request&,const registry::Requirements&,
    const ExecutionContext&);

} // namespace csl::reachability::finite_feedback
