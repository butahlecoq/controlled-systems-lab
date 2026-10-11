#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/objectives.hpp>
#include <limits>
#include <type_traits>

using namespace csl;
using namespace csl::optimization;
static_assert(!std::is_default_constructible_v<Objective>);
static_assert(!std::is_default_constructible_v<NormSquareReformulation>);
static_assert(std::is_same_v<decltype(std::declval<const Objective&>().coefficients()), ObjectiveCoefficients>);
namespace {
template<class T> T accepted(Result<T> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
template<class T> void rejected(const Result<T>& result, DiagnosticCode code, const char* field) {
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).code == code);
    CHECK(std::get<Diagnostic>(result).field == field);
}
template<class T> void stopped(const Result<T>& result) {
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason == StopReason::numerical_failure);
    CHECK_FALSE(std::get<OperationStopped>(result).diagnostics.empty());
}

// Square-only maps or reporting a squared cost would fail this rectangular fixture.
TEST_CASE("rectangular residual objective reports original norm including zero") {
    auto objective = accepted(snapshot(ResidualNormTerminal{{3, 2, {1, 0, 0, 2, 1, -1}}, {1, 2, 0}}));
    CHECK(accepted(evaluate(objective, Vector{3, 1})) == doctest::Approx(2.8284271247461903));
    CHECK(accepted(evaluate(objective, Vector{1, 1})) == 0);
}
}

// Dropping the offset, swapping coefficients, or retaining the producer breaks this oracle.
TEST_CASE("linear objective retains coefficients and evaluates the original cost") {
    TerminalObjective authored = LinearTerminal{{2, -1}, 3};
    auto objective = accepted(snapshot(authored));
    std::get<LinearTerminal>(authored).coefficients.assign(2, 0);
    std::get<LinearTerminal>(authored).offset = 99;
    CHECK(accepted(evaluate(objective, Vector{4, 5})) == 6);
}

// A missing half factor, treating PSD as PD, or silently clipping eigenvalues breaks these cases.
TEST_CASE("quadratic convention supports singular objectives with numerical checks") {
    auto objective = accepted(snapshot(QuadraticTerminal{{2, 2, {2, 0, 0, 0}}, {-2, 0}, 1}));
    CHECK(accepted(evaluate(objective, Vector{3, 8})) == 4);
    CHECK(accepted(evaluate(objective, Vector{1, 0})) == 0);
    CHECK(accepted(evaluate(objective, Vector{1, 7})) == 0);
    REQUIRE(objective.quadratic_checks().has_value());
    CHECK(objective.quadratic_checks()->minimum_eigenvalue == 0);
    CHECK(objective.quadratic_checks()->positive_semidefiniteness.max_residual == 0);
}

TEST_CASE("quadratic symmetry and PSD policy diagnoses negative and unresolved eigenvalues") {
    const ObjectivePolicy policy{Assurance::numerical, {0.125, 0}};
    rejected(snapshot(QuadraticTerminal{{2, 2, {1, 1, 0, 1}}, {0, 0}, 0}, policy),
             DiagnosticCode::invalid_input, "objective.symmetry");
    rejected(snapshot(QuadraticTerminal{{1, 1, {-0.25}}, {0}, 0}, policy),
             DiagnosticCode::invalid_input, "objective.psd");
    rejected(snapshot(QuadraticTerminal{{2, 2, {1, 2, 2, 1}}, {0, 0}, 0}, policy),
             DiagnosticCode::invalid_input, "objective.psd");
    rejected(snapshot(QuadraticTerminal{{1, 1, {-0.125}}, {0}, 0}, policy),
             DiagnosticCode::unsupported, "objective.psd");
    rejected(snapshot(QuadraticTerminal{{1, 1, {-0.0625}}, {0}, 0}, policy),
             DiagnosticCode::unsupported, "objective.psd");
    auto retained = accepted(snapshot(QuadraticTerminal{{2, 2, {2, 0.125, 0, 2}}, {0, 0}, 0}, policy));
    CHECK(std::get<QuadraticCoefficients>(retained.coefficients()).Q(0, 1) == 0.125);
    CHECK(std::get<QuadraticCoefficients>(retained.coefficients()).Q(1, 0) == 0);
    CHECK(retained.quadratic_checks()->symmetry.max_residual == 0.125);
    CHECK(accepted(evaluate(retained, Vector{2, 4})) == 20.5);
    rejected(snapshot(QuadraticTerminal{{2, 2, {2, 0.25, 0, 2}}, {0, 0}, 0}, policy),
             DiagnosticCode::invalid_input, "objective.symmetry");
}

TEST_CASE("relative tolerances use coefficient and eigenvalue scales independently") {
    const ObjectivePolicy policy{Assurance::numerical, {0, 0.0625}};
    auto boundary = accepted(snapshot(QuadraticTerminal{{2, 2, {2, 0.125, 0, 2}}, {0, 0}, 0}, policy));
    CHECK(accepted(evaluate(boundary, Vector{2, 4})) == 20.5);
    rejected(snapshot(QuadraticTerminal{{2, 2, {2, 0.25, 0, 2}}, {0, 0}, 0}, policy),
             DiagnosticCode::invalid_input, "objective.symmetry");
    rejected(snapshot(QuadraticTerminal{{2, 2, {-0.125, 0, 0, 2}}, {0, 0}, 0}, policy),
             DiagnosticCode::unsupported, "objective.psd");
    rejected(snapshot(QuadraticTerminal{{2, 2, {-0.25, 0, 0, 2}}, {0, 0}, 0}, policy),
             DiagnosticCode::invalid_input, "objective.psd");
}

// Wrong Gram factor/sign/offset or reporting the solver cost as the original norm must fail.
TEST_CASE("recorded norm square preserves original and literal rectangular coefficients") {
    auto reformulation = accepted(square_residual_norm(accepted(snapshot(
        ResidualNormTerminal{{3, 2, {1, 0, 0, 2, 1, -1}}, {1, 2, 0}}))));
    const auto quadratic = std::get<QuadraticCoefficients>(reformulation.squared().coefficients());
    CHECK(quadratic.Q(0, 0) == 4);
    CHECK(quadratic.Q(0, 1) == -2);
    CHECK(quadratic.Q(1, 0) == -2);
    CHECK(quadratic.Q(1, 1) == 10);
    CHECK(quadratic.linear[0] == -2);
    CHECK(quadratic.linear[1] == -8);
    CHECK(quadratic.offset == 5);
    CHECK(reformulation.transformation() == ObjectiveTransformation::residual_norm_squared);
    CHECK(accepted(evaluate(reformulation.original(), Vector{3, 1})) == doctest::Approx(2.8284271247461903));
    CHECK(accepted(evaluate(reformulation.squared(), Vector{3, 1})) == 8);
    CHECK(accepted(evaluate(reformulation.original(), Vector{1, 1})) == 0);
    CHECK(accepted(evaluate(reformulation.squared(), Vector{1, 1})) == 0);
}

TEST_CASE("rank deficient residual retains distinct minimizing points") {
    auto reformulation = accepted(square_residual_norm(accepted(snapshot(ResidualNormTerminal{{1, 2, {1, 0}}, {1}}))));
    CHECK(accepted(evaluate(reformulation.original(), Vector{1, 0})) == 0);
    CHECK(accepted(evaluate(reformulation.original(), Vector{1, 7})) == 0);
    CHECK(accepted(evaluate(reformulation.squared(), Vector{1, 0})) == 0);
    CHECK(accepted(evaluate(reformulation.squared(), Vector{1, 7})) == 0);
}

// Unsupported requested evidence and malformed tolerance policy must never be silently accepted.
TEST_CASE("assurance and policy validation applies to every objective form") {
    for (const auto& authored : std::vector<TerminalObjective>{
             LinearTerminal{{1}, 0}, QuadraticTerminal{{1, 1, {1}}, {0}, 0}, ResidualNormTerminal{{1, 1, {1}}, {0}}}) {
        rejected(snapshot(authored, {Assurance::validated, {0, 0}}), DiagnosticCode::unsupported, "objective.assurance");
        rejected(snapshot(authored, {static_cast<Assurance>(27), {0, 0}}), DiagnosticCode::invalid_input, "objective.assurance");
        rejected(snapshot(authored, {Assurance::numerical, {-1, 0}}), DiagnosticCode::invalid_input, "objective.policy");
        rejected(snapshot(authored, {Assurance::numerical, {0, -1}}), DiagnosticCode::invalid_input, "objective.policy");
        rejected(snapshot(authored, {Assurance::numerical, {std::numeric_limits<double>::infinity(), 0}}),
                 DiagnosticCode::invalid_input, "objective.policy");
        rejected(snapshot(authored, {Assurance::numerical, {0, std::numeric_limits<double>::quiet_NaN()}}),
                 DiagnosticCode::invalid_input, "objective.policy");
    }
}

TEST_CASE("coefficient shapes offsets and finite values are validated at publication") {
    const double inf = std::numeric_limits<double>::infinity();
    rejected(snapshot(LinearTerminal{{inf}, 0}), DiagnosticCode::invalid_input, "numeric.values");
    rejected(snapshot(LinearTerminal{{1}, inf}), DiagnosticCode::invalid_input, "objective.offset");
    rejected(snapshot(QuadraticTerminal{{1, 2, {1, 0}}, {0, 0}, 0}), DiagnosticCode::invalid_input, "objective.shape");
    rejected(snapshot(QuadraticTerminal{{1, 1, {1}}, {}, 0}), DiagnosticCode::invalid_input, "objective.shape");
    rejected(snapshot(QuadraticTerminal{{1, 1, {1}}, {0}, inf}), DiagnosticCode::invalid_input, "objective.offset");
    rejected(snapshot(QuadraticTerminal{{1, 1, {inf}}, {0}, 0}), DiagnosticCode::invalid_input, "numeric.values");
    rejected(snapshot(QuadraticTerminal{{1, 1, {1}}, {inf}, 0}), DiagnosticCode::invalid_input, "numeric.values");
    rejected(snapshot(ResidualNormTerminal{{2, 1, {1, 2}}, {0}}), DiagnosticCode::invalid_input, "objective.shape");
    rejected(snapshot(ResidualNormTerminal{{2, 1, {1}}, {0, 0}}), DiagnosticCode::invalid_input, "numeric.dense.storage");
    rejected(snapshot(ResidualNormTerminal{{1, 1, {inf}}, {0}}), DiagnosticCode::invalid_input, "numeric.values");
    rejected(snapshot(ResidualNormTerminal{{1, 1, {1}}, {inf}}), DiagnosticCode::invalid_input, "numeric.values");
}

// This catches treating empty maps as invalid or collapsing a constant objective to one point.
TEST_CASE("constant and zero dimensional objectives retain their actual costs") {
    auto linear = accepted(snapshot(LinearTerminal{{0, 0}, 3}));
    CHECK(accepted(evaluate(linear, Vector{2, -4})) == 3);
    CHECK(accepted(evaluate(linear, Vector{9, 7})) == 3);
    auto quadratic = accepted(snapshot(QuadraticTerminal{{2, 2, {0, 0, 0, 0}}, {0, 0}, -2}));
    CHECK(accepted(evaluate(quadratic, Vector{2, -4})) == -2);
    CHECK(accepted(evaluate(quadratic, Vector{9, 7})) == -2);
    auto norm = accepted(square_residual_norm(accepted(snapshot(ResidualNormTerminal{{2, 2, {0, 0, 0, 0}}, {3, 4}}))));
    CHECK(accepted(evaluate(norm.original(), Vector{2, -4})) == 5);
    CHECK(accepted(evaluate(norm.original(), Vector{9, 7})) == 5);
    CHECK(accepted(evaluate(norm.squared(), Vector{9, 7})) == 25);
    CHECK(accepted(evaluate(accepted(snapshot(LinearTerminal{{}, 3})), {})) == 3);
    CHECK(accepted(evaluate(accepted(snapshot(QuadraticTerminal{{0, 0, {}}, {}, 7})), {})) == 7);
    auto no_coordinates = accepted(square_residual_norm(accepted(snapshot(ResidualNormTerminal{{2, 0, {}}, {3, 4}}))));
    CHECK(accepted(evaluate(no_coordinates.original(), {})) == 5);
    CHECK(accepted(evaluate(no_coordinates.squared(), {})) == 25);
    auto no_rows = accepted(square_residual_norm(accepted(snapshot(ResidualNormTerminal{{0, 2, {}}, {}}))));
    CHECK(no_rows.original().dimension() == 2);
    CHECK(accepted(evaluate(no_rows.original(), Vector{1, 7})) == 0);
    CHECK(accepted(evaluate(no_rows.squared(), Vector{1, 7})) == 0);
    CHECK(accepted(evaluate(accepted(snapshot(ResidualNormTerminal{{0, 0, {}}, {}})), {})) == 0);
}

// An overflow result must not be exposed as a usable objective value or cause loss of the original norm.
TEST_CASE("finite arithmetic failures are separate from malformed requests") {
    const double max = std::numeric_limits<double>::max();
    auto linear = accepted(snapshot(LinearTerminal{{max}, 0}));
    stopped(evaluate(linear, Vector{2}));
    rejected(evaluate(linear, {}), DiagnosticCode::invalid_input, "objective.point");
    rejected(evaluate(linear, Vector{std::numeric_limits<double>::quiet_NaN()}), DiagnosticCode::invalid_input, "objective.point");
    rejected(square_residual_norm(linear), DiagnosticCode::unsupported, "objective.reformulation");
    auto quadratic = accepted(snapshot(QuadraticTerminal{{1, 1, {2}}, {0}, 0}));
    stopped(evaluate(quadratic, Vector{max}));
    auto large_norm = accepted(snapshot(ResidualNormTerminal{{1, 1, {0}}, {1e200}}));
    CHECK(accepted(evaluate(large_norm, Vector{3})) == 1e200);
    stopped(square_residual_norm(large_norm));
    CHECK(accepted(evaluate(large_norm, Vector{7})) == 1e200);
    auto large_map = accepted(snapshot(ResidualNormTerminal{{1, 1, {max}}, {0}}));
    stopped(evaluate(large_map, Vector{2}));
    stopped(square_residual_norm(large_map));
    auto hypot = accepted(snapshot(ResidualNormTerminal{{2, 0, {}}, {3e200, 4e200}}));
    CHECK(accepted(evaluate(hypot, {})) == doctest::Approx(5e200));
    auto overflow_tolerance = snapshot(QuadraticTerminal{{1, 1, {max}}, {0}, 0}, {Assurance::numerical, {max, 1}});
    stopped(overflow_tolerance);
}

// Scaling must not erase the tiny negative entry and admit an indefinite diagonal matrix.
TEST_CASE("PSD scaling cannot silently erase nonzero coefficients") {
    stopped(snapshot(QuadraticTerminal{{2, 2, {-std::numeric_limits<double>::denorm_min(), 0,
                                               0, std::numeric_limits<double>::max()}}, {0, 0}, 0}));
}

TEST_CASE("retained objectives and metadata survive producer destruction and move aliases") {
    auto quadratic = [] {
        TerminalObjective authored = QuadraticTerminal{{2, 2, {4, -2, -2, 10}}, {-2, -8}, 5};
        double* alias = std::get<QuadraticTerminal>(authored).Q.values.data();
        auto result = accepted(snapshot(std::move(authored)));
        alias[0] = 100;
        return result;
    }();
    CHECK(accepted(evaluate(quadratic, Vector{3, 1})) == 8);
    auto moved = std::move(quadratic);
    CHECK(accepted(evaluate(quadratic, Vector{3, 1})) == 8);
    CHECK(accepted(evaluate(moved, Vector{3, 1})) == 8);
    auto metadata = moved.quadratic_checks();
    metadata->symmetry.max_residual = 100;
    metadata->symmetry.verifier.value = "changed";
    CHECK(moved.quadratic_checks()->symmetry.max_residual == 0);
    CHECK(moved.quadratic_checks()->symmetry.verifier.value == "csl.objectives.symmetry.v1");
    auto residual = [] {
        ResidualNormTerminal authored{{1, 2, {1, 0}}, {1}};
        auto result = accepted(snapshot(authored));
        authored.map.values[0] = 7;
        authored.target[0] = 10;
        return accepted(square_residual_norm(result));
    }();
    CHECK(accepted(evaluate(residual.original(), Vector{1, 7})) == 0);
    CHECK(accepted(evaluate(residual.squared(), Vector{1, 7})) == 0);
}
