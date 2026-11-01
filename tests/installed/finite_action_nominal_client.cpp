#include <csl/optimization/finite_action_nominal.hpp>

#include <type_traits>

using namespace csl::optimization;
using Nominal = FiniteActionNominalOutcome (*)(const FiniteActionNominalRequest &,
    FiniteActionNominalLimits, const csl::ExecutionContext &);
static_assert(std::is_same_v<decltype(&finite_action_nominal), Nominal>);

int main() {
  return &finite_action_nominal == nullptr;
}
