#include <csl/optimization/validated_finite_action_minimax.hpp>

int main() {
    using namespace csl::optimization;
    static_assert(std::variant_size_v<ValidatedFiniteActionMinimaxOutcome> == 7);
    static_assert(std::variant_size_v<ValidatedPlanEvidence> == 3);
    auto* entry = &validated_finite_action_minimax;
    return entry ? 0 : 1;
}
