#include <csl/synthesis/finite_mixed_branch.hpp>

#include <iostream>

int main() {
    using namespace csl;
    using namespace csl::synthesis;
    using Solve = FiniteMixedBranchSolveOutcome (*)(const problem::ResolvedProblem&,
        const registry::StrategyRegistry&, const FiniteMixedBranchSolveRequest&,
        const ExecutionContext&);
    const Solve solve = &solve_finite_mixed_branch_portfolio;
    (void)solve;
    std::cout << "Installed mixed branch client: registered branch solve API linked\n";
}
