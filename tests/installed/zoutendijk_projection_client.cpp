#include <csl/optimization/zoutendijk/projection.hpp>

#include <iostream>
#include <type_traits>
#include <variant>

using namespace csl::optimization::zoutendijk;

static_assert(std::is_same_v<std::variant_alternative_t<0, ProjectionOutcome>, ProjectionSuccess>);
static_assert(std::is_same_v<std::variant_alternative_t<1, ProjectionOutcome>, ProjectionStopped>);

int main() {
    const ProjectionPolicy policy{};
    if (policy.max_iterations == 0) return 1;
    std::cout << "Installed Zoutendijk client: success and stopped result types are distinct\n";
}
