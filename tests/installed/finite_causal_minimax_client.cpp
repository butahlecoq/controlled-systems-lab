#include <csl/optimization/finite_causal_minimax.hpp>

#include <iostream>
#include <variant>

int main() {
    using namespace csl::optimization::finite_causal_minimax;

    const Game game{
        {Stage{1, 2, 1, {true}, {{{StateId{0}}, {StateId{1}}}}}},
        Terminal{2, {true, true}, {2.0, 1.0}},
        StateId{0}};
    const auto outcome = solve(game, Options{1e-12, 1e-12});
    const auto* result = std::get_if<Result>(&outcome);
    if(!result || !result->initial().feasible || result->initial().value != 1.0 ||
       result->initial().optimal_actions != std::vector<ActionId>{ActionId{1}})
        return 1;

    std::cout << "Installed causal minimax client: terminal choice and action passed\n";
}
