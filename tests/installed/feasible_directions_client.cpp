#include <csl/optimization/feasible_directions/smooth_convex.hpp>

#include <iostream>
#include <type_traits>

using namespace csl::optimization::feasible_directions;
using namespace csl;
using namespace csl::optimization;

static_assert(std::is_same_v<std::variant_alternative_t<0, SmoothOutcome>, SmoothStationary>);
static_assert(std::is_same_v<std::variant_alternative_t<1, SmoothOutcome>, SmoothStopped>);

class UnusedWorkspace final : public LPWorkspace {
protected:
    ProgramOutcome do_solve(const LinearProgram&, const ExecutionContext&) override {
        return Unsupported{{{DiagnosticCode::unsupported, "unused", "No solve expected."}}};
    }
};

int main() {
    const auto created = make_linear_program({{{"installed"}, {"feasible-directions"}},
        {0}, 0, {0, 1, {0}, {}, {}}, {{0, 1}}, {}});
    if (!std::holds_alternative<LinearProgram>(created)) return 1;
    const auto& feasible = std::get<LinearProgram>(created);
    SmoothObjective wrong_shape{"wrong-shape", 2, ObjectiveClaim::declared_convex,
        [](std::span<const double>) { return 0.0; },
        [](std::span<const double>) { return Vector{0}; }};
    UnusedWorkspace workspace;
    ExecutionContext context{{}, {}, {}, {1e-9, 1e-9}, "installed"};
    const auto result = minimize(feasible, wrong_shape, Vector{0.5}, workspace, context);
    if (!std::holds_alternative<Diagnostics>(result) ||
        std::get<Diagnostics>(result).front().field != "feasible_directions.shape") return 2;
    std::cout << "Installed feasible-directions client: public adapter linked and outcome types checked\n";
}
