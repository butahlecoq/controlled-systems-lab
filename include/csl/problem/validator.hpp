#pragma once

#include <csl/problem/contracts.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <csl/registry/registry.hpp>

namespace csl::problem {
namespace detail { struct PreparedAccess; }
class PreparedResolvedStrategy {
public:
    PreparedResolvedStrategy(const PreparedResolvedStrategy&) = default;
    PreparedResolvedStrategy& operator=(const PreparedResolvedStrategy&) = default;
    ResolvedProblem problem() const;
    registry::PreparedStrategy preparation() const;
private:
    PreparedResolvedStrategy(ResolvedProblem,registry::PreparedStrategy);
    ResolvedProblem problem_;
    registry::PreparedStrategy preparation_;
    friend struct detail::PreparedAccess;
};
using StrategyAdmission = std::variant<PreparedResolvedStrategy,registry::Rejection>;
// Delegates admission to the actual registry; retains resolved content in the wrapper.
StrategyAdmission prepare_strategy(const ResolvedProblem&,const registry::StrategyRegistry&,
    const StrategyConfiguration&,const FamilyRequest&,const registry::Requirements& = {},
    std::optional<std::string> strategy_version = {});
} // namespace csl::problem
