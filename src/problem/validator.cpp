#include <csl/problem/validator.hpp>

namespace csl::problem {
namespace detail {
struct PreparedAccess {
    static PreparedResolvedStrategy prepared(ResolvedProblem p,registry::PreparedStrategy value) {
        return PreparedResolvedStrategy{std::move(p),std::move(value)};
    }
};
}
PreparedResolvedStrategy::PreparedResolvedStrategy(ResolvedProblem p,registry::PreparedStrategy prepared):problem_(p),preparation_(std::move(prepared)) {}
ResolvedProblem PreparedResolvedStrategy::problem() const {return problem_;}
registry::PreparedStrategy PreparedResolvedStrategy::preparation() const {return preparation_;}
StrategyAdmission prepare_strategy(const ResolvedProblem& problem,const registry::StrategyRegistry& registry,
    const StrategyConfiguration& configuration,const FamilyRequest& family,
    const registry::Requirements& requirements,std::optional<std::string> version) {
    auto prepared=registry.prepare({problem,configuration,family,{},{}},requirements,std::move(version));
    if(auto* rejection=std::get_if<registry::Rejection>(&prepared)) return *rejection;
    return detail::PreparedAccess::prepared(problem,std::get<registry::PreparedStrategy>(std::move(prepared)));
}
} // namespace csl::problem
