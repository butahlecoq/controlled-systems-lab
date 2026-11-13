#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/model/flexible_pitch.hpp>
#include <csl/model/linear_system.hpp>
#include <csl/problem/temporal_lifts.hpp>
#include <csl/sets/data.hpp>
#include <csl/numeric/data.hpp>

#include <cmath>
#include <numbers>

namespace {
using namespace csl;
template<class T, class... Errors> T take(std::variant<T, Errors...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
SetHandle interval(std::string id, double radius) {
    return take(sets::make_h({{std::move(id)}, 1, {"delta"}}, {
        take(numeric::snapshot(Matrix{2, 1, {-1, 1}})),
        take(numeric::snapshot_vector(Vector{radius, radius})),
        take(numeric::snapshot(Matrix{0, 1, {}})),
        take(numeric::snapshot_vector(Vector{}))})).as_handle();
}
bool contains(const AdmissibleSet& admissible, const Vector& point) {
    const auto data = take(sets::from_handle(std::get<SetHandle>(admissible)));
    const auto h = std::get<sets::HRepresentation>(data.representation());
    for (std::size_t row = 0; row < h.inequalities.rows(); ++row) {
        double value = 0;
        for (std::size_t j = 0; j < point.size(); ++j) value += h.inequalities(row, j) * point[j];
        if (value > h.upper_bounds[row] + 1e-12) return false;
    }
    return true;
}
}

TEST_CASE("physical pitch cases have a separate exact slew-memory capability probe") {
    using namespace csl;
    constexpr double radians = std::numbers::pi / 180;
    for (const auto& info : model::catalogue::flexible_pitch_cases()) {
        const auto data = take(model::catalogue::make_flexible_pitch_case(info.id));
        const auto n = info.states.size();
        const auto physical = take(model::snapshot(data.reachability.model, data.reachability.time_grid));
        const auto amplitude = interval("pitch-amplitude", 4 * radians);
        const auto increment = interval("pitch-increment", 35 * radians * 0.1);
        // Zero terminal data is only an API-required structural fixture. No
        // optimization runs or substituted source objective are represented.
        Problem original{{std::string(info.id) + "/slew-memory-structural-probe"},
            std::make_shared<const SystemModel>(data.reachability.model), data.reachability.time_grid,
            KnownInitial{Vector(n, 0)}, ContinuousDomain{std::vector<AdmissibleSet>(40, amplitude)},
            std::vector<AdmissibleSet>(41, UniversalSet{n}), {}, {}, InformationPattern::nominal_open_loop,
            QuadraticTerminal{{n, n, Vector(n * n, 0)}, Vector(n, 0), 0}};
        problem::SlewMemoryRequest request{problem::RateLimitedFirstAction{{0}, increment},
            std::vector<AdmissibleSet>(39, increment)};
        const auto lift = take(problem::lift_one_step_slew(original, request));
        CHECK(lift.problem.id != original.id);
        CHECK(lift.problem.id.value != info.id);
        CHECK(lift.problem.model->dynamics.dimensions.state == n + 1);
        const auto augmented = take(model::snapshot(*lift.problem.model, lift.problem.times));
        const auto& controls = std::get<ContinuousDomain>(lift.problem.controls).stages;
        Vector x(n, 0), z(n + 1, 0);
        double previous = 0;
        for (std::size_t k = 0; k < physical.horizon(); ++k) {
            const double input = (k % 2 ? 2 : 3) * radians;
            const Vector v{input - previous};
            CHECK(contains(controls[k], v));
            x = take(physical.step({k}, x, Vector{input}, {}));
            z = take(augmented.step({k}, z, v, {}));
            REQUIRE(z.size() == n + 1);
            for (std::size_t j = 0; j < n; ++j) CHECK(z[j] == doctest::Approx(x[j]).epsilon(1e-10));
            CHECK(z[n] == doctest::Approx(input));
            CHECK(contains(lift.problem.states[k + 1], z));
            previous = input;
        }
        // Both absolute commands are legal; their six-degree jump is illegal.
        CHECK(contains(std::get<ContinuousDomain>(original.controls).stages[0], {3 * radians}));
        CHECK(contains(std::get<ContinuousDomain>(original.controls).stages[1], {-3 * radians}));
        CHECK_FALSE(contains(controls[1], {-6 * radians}));
    }
}
