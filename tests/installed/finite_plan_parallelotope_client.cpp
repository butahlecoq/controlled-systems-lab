#include <csl/reachability/finite_plan_parallelotope.hpp>

#include <iostream>
#include <stdexcept>
#include <type_traits>

using namespace csl;

using ParallelotopePropagation = reachability::FinitePlanParallelotopeOutcome (*)(
    const reachability::FixedPlanRequest &, const ExecutionContext &);
static_assert(
    std::is_same_v<decltype(&reachability::finite_plan_parallelotope), ParallelotopePropagation>);

namespace {
template <class T> T take(std::variant<T, Diagnostic> result) {
    if (auto *value = std::get_if<T>(&result))
        return std::move(*value);
    throw std::runtime_error("Public model or set construction failed");
}

sets::SetData domain(bool bounded, double bound = 2) {
    Matrix rows{bounded ? 8u : 0u, 4, {}};
    if (bounded) {
        rows.values.assign(32, 0);
        for (std::size_t j = 0; j < 4; ++j) {
            rows.values[2 * j * 4 + j] = 1;
            rows.values[(2 * j + 1) * 4 + j] = -1;
        }
    }
    return take(sets::make_h({{"installed-four-state-H"}, 4, {}},
                             {take(numeric::snapshot(std::move(rows))),
                              take(numeric::snapshot_vector(Vector(bounded ? 8 : 0, bound))),
                              take(numeric::snapshot(Matrix{0, 4, {}})),
                              take(numeric::snapshot_vector(Vector{}))}));
}

reachability::FixedPlanRequest request(const sets::SetData &safe) {
    const SystemModel source_model{
        {{4, 1, 0},
         TimeDomain::discrete,
         LinearStage{{4, 4, {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1}},
                     {4, 1, {1, 0, 0, 0}},
                     {4, 0, {}},
                     Vector(4, 0)}},
        {}};
    return {take(model::snapshot(source_model, Vector{0, 1})),
            take(sets::make_singleton({{"installed-initial"}, 4, {}},
                                      take(numeric::snapshot_vector(Vector(4, 0))))),
            {{0.25}},
            {take(sets::make_singleton({{"installed-disturbance"}, 0, {}},
                                       take(numeric::snapshot_vector(Vector{}))))},
            {safe, safe},
            {"installed-four-state-H"}};
}
} // namespace

int main() try {
    for (const bool bounded : {false, true}) {
        const auto result = reachability::finite_plan_parallelotope(request(domain(bounded)));
        const auto *trace = std::get_if<reachability::FinitePlanParallelotopeTrace>(&result);
        if (!trace || trace->stages.size() != 2 || trace->relation != SetRelation::outer)
            throw std::runtime_error("Containing four-state H domain was rejected");
    }
    const auto rejected = reachability::finite_plan_parallelotope(request(domain(true, 0.125)));
    if (!std::holds_alternative<Unsupported>(rejected))
        throw std::runtime_error("A violated four-state H bound was accepted");
    std::cout << "Installed parallelotope client: four-state H admission and refusal passed\n";
} catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
}
