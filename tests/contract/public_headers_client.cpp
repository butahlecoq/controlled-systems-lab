#include <csl/contracts.hpp>
#include <csl/numeric/data.hpp>
#ifdef CSL_PUBLIC_HEADERS_LP_FIRST
#include <csl/optimization/linear_program.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <csl/optimization/phase_one.hpp>
#include <csl/optimization/objectives.hpp>
#else
#include <csl/optimization/objectives.hpp>
#include <csl/optimization/linear_program.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <csl/optimization/phase_one.hpp>
#endif
#include <csl/model/linear_system.hpp>
#include <csl/registry/registry.hpp>
#include <csl/sets/data.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/problem/domains.hpp>
#include <csl/problem/constraints.hpp>
#include <csl/problem/initial_information.hpp>
#include <csl/problem/temporal_lifts.hpp>
#include <csl/problem/validator.hpp>
#include <csl/execution/executor.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <csl/adapters/convex/highs.hpp>
#include <csl/artifacts/run_statistics.hpp>
#include <csl/execution/observability.hpp>
#include <csl/input/scenario_loader.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/reachability/nominal_predecessor.hpp>
#include <csl/reachability/finite_plan_box.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>
#include <csl/reachability/finite_plan_parallelotope.hpp>

#include <iostream>
#include <stdexcept>
#include <type_traits>
#include <utility>

using namespace csl;
using namespace csl::numeric;

static_assert(std::is_same_v<csl::optimization::LPDataResult<LinearProgram>,
    std::variant<LinearProgram, Diagnostics>>);
static_assert(std::is_same_v<csl::optimization::Result<csl::optimization::Objective>,
    std::variant<csl::optimization::Objective, Diagnostic, OperationStopped>>);

namespace {
template<class T> T accepted(Result<T> result) {
    if (const auto* error = std::get_if<Diagnostic>(&result))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(result));
}
void check(const MatrixView& matrix, const VectorView& vector, const Vector& expected) {
    if (accepted(multiply(matrix, vector)) != expected)
        throw std::runtime_error("Public header client literal result differs.");
}
}

int main() {
    try {
        const auto retained = [] {
            Vector producer{1, 99, 2, 4, 3, 5, 99, 6};
            Vector input{7, 11, 13};
            auto matrix = accepted(snapshot(DenseInput{producer, 2, 3, 3, 2, DenseLayout::strided}));
            auto vector = accepted(snapshot_vector(input));
            auto moved = std::move(matrix);
            auto moved_vector = std::move(vector);
            check(matrix, vector, {68, 161});
            producer.assign(1024, -99);
            input.clear();
            return std::pair{moved, moved_vector};
        }();
        check(retained.first, retained.second, {68, 161});
        auto assigned = accepted(snapshot(Matrix{1, 1, {-1}}));
        assigned = retained.first;
        check(assigned, retained.second, {68, 161});
        check(accepted(snapshot(Matrix{3, 4, {1, 2, -1, 3, -4, 0, 2, -1, 5, -3, 0, 2}})),
              accepted(snapshot_vector(Vector{2, -3, 5, -7})), {-30, 9, 5});
        check(accepted(snapshot(Matrix{3, 0, {}})), accepted(snapshot_vector({})), {0, 0, 0});
#ifdef _MSC_VER
        std::cout << "MSVC=" << _MSC_VER << " iterator=" << _ITERATOR_DEBUG_LEVEL << '\n';
#endif
        std::cout << "Public headers client: retained layout, signed oracle and zero ports passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
