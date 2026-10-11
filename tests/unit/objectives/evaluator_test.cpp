#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/objectives.hpp>
#include <array>
#include <limits>

using namespace csl;
using namespace csl::optimization;

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
}

TEST_CASE("literal linear and half-quadratic costs retain their offsets") {
    const auto linear = accepted(snapshot(LinearTerminal{{2, -1}, 3}));
    const auto quadratic = accepted(snapshot(QuadraticTerminal{{2, 2, {2, 0, 0, 0}}, {0, 1}, 3}));
    CHECK(accepted(evaluate(linear, Vector{1, 2})) == 3);
    CHECK(accepted(evaluate(quadratic, Vector{1, 2})) == 6);
    CHECK(accepted(evaluate(linear, Vector{0, 0})) == 3);
    CHECK(accepted(evaluate(quadratic, Vector{0, 0})) == 3);
    CHECK(accepted(evaluate(linear, Vector{2, -1})) == 8);
    CHECK(accepted(evaluate(quadratic, Vector{2, -1})) == 6);
    REQUIRE(quadratic.quadratic_checks().has_value());
    CHECK(quadratic.quadratic_checks()->minimum_eigenvalue == 0);
    CHECK(quadratic.policy().assurance == Assurance::numerical);
}

TEST_CASE("wide rectangular residual reports zero and original five-unit norm") {
    const auto objective = accepted(snapshot(ResidualNormTerminal{{2, 3, {1, 0, 0, 0, 1, 1}}, {1, 4}}));
    CHECK(objective.dimension() == 3);
    const auto residual = std::get<ResidualCoefficients>(objective.coefficients());
    CHECK(residual.map.rows() == 2);
    CHECK(residual.map.cols() == 3);
    CHECK(accepted(evaluate(objective, Vector{1, 1, 3})) == 0);
    CHECK(accepted(evaluate(objective, Vector{4, 1, 7})) == 5);
}

TEST_CASE("rectangular shapes and point dimensions are checked independently") {
    rejected(snapshot(ResidualNormTerminal{{2, 3, {1, 0, 0, 0, 1, 1}}, {1, 4, 0}}),
             DiagnosticCode::invalid_input, "objective.shape");
    rejected(snapshot(ResidualNormTerminal{{2, 3, {1, 0, 0, 0, 1}}, {1, 4}}),
             DiagnosticCode::invalid_input, "numeric.dense.storage");
    rejected(snapshot(QuadraticTerminal{{2, 3, {1, 0, 0, 0, 1, 0}}, {0, 0, 0}, 0}),
             DiagnosticCode::invalid_input, "objective.shape");
    rejected(snapshot(QuadraticTerminal{{2, 2, {1, 0, 0, 1}}, {0}, 0}),
             DiagnosticCode::invalid_input, "objective.shape");
    const auto objective = accepted(snapshot(ResidualNormTerminal{{2, 3, {1, 0, 0, 0, 1, 1}}, {1, 4}}));
    rejected(evaluate(objective, Vector{1, 2}), DiagnosticCode::invalid_input, "objective.point");
    rejected(evaluate(objective, Vector{1, 2, 3, 4}), DiagnosticCode::invalid_input, "objective.point");
}

TEST_CASE("every coefficient role rejects infinity and NaN at publication") {
    const std::array nonfinite{std::numeric_limits<double>::infinity(),
                              -std::numeric_limits<double>::infinity(),
                              std::numeric_limits<double>::quiet_NaN()};
    for (const double value : nonfinite) {
        CAPTURE(value);
        rejected(snapshot(LinearTerminal{{1, value}, 0}), DiagnosticCode::invalid_input, "numeric.values");
        rejected(snapshot(LinearTerminal{{1, 2}, value}), DiagnosticCode::invalid_input, "objective.offset");
        rejected(snapshot(QuadraticTerminal{{2, 2, {1, 0, 0, value}}, {0, 0}, 0}),
                 DiagnosticCode::invalid_input, "numeric.values");
        rejected(snapshot(QuadraticTerminal{{2, 2, {1, 0, 0, 1}}, {0, value}, 0}),
                 DiagnosticCode::invalid_input, "numeric.values");
        rejected(snapshot(QuadraticTerminal{{2, 2, {1, 0, 0, 1}}, {0, 0}, value}),
                 DiagnosticCode::invalid_input, "objective.offset");
        rejected(snapshot(ResidualNormTerminal{{2, 3, {1, 0, 0, 0, 1, value}}, {1, 4}}),
                 DiagnosticCode::invalid_input, "numeric.values");
        rejected(snapshot(ResidualNormTerminal{{2, 3, {1, 0, 0, 0, 1, 1}}, {1, value}}),
                 DiagnosticCode::invalid_input, "numeric.values");
    }
}

TEST_CASE("every objective rejects nonfinite evaluation coordinates") {
    for (const auto& authored : std::vector<TerminalObjective>{
             LinearTerminal{{2, -1}, 3},
             QuadraticTerminal{{2, 2, {2, 0, 0, 0}}, {0, 1}, 3},
             ResidualNormTerminal{{1, 2, {1, 1}}, {1}}}) {
        const auto objective = accepted(snapshot(authored));
        for (const double value : std::array{std::numeric_limits<double>::infinity(),
                                            -std::numeric_limits<double>::infinity(),
                                            std::numeric_limits<double>::quiet_NaN()}) {
            CAPTURE(value);
            rejected(evaluate(objective, Vector{1, value}), DiagnosticCode::invalid_input, "objective.point");
        }
    }
}

TEST_CASE("numerical quadratic policy separates invalid unresolved and supported data") {
    const ObjectivePolicy policy{Assurance::numerical, {0.0625, 0}};
    rejected(snapshot(QuadraticTerminal{{2, 2, {2, 0.25, 0, 2}}, {0, 0}, 0}, policy),
             DiagnosticCode::invalid_input, "objective.symmetry");
    rejected(snapshot(QuadraticTerminal{{2, 2, {1, 2, 2, 1}}, {0, 0}, 0}, policy),
             DiagnosticCode::invalid_input, "objective.psd");
    rejected(snapshot(QuadraticTerminal{{1, 1, {-0.03125}}, {0}, 0}, policy),
             DiagnosticCode::unsupported, "objective.psd");
    rejected(snapshot(QuadraticTerminal{{1, 1, {-0.125}}, {0}, 0}, policy),
             DiagnosticCode::invalid_input, "objective.psd");
    const auto semidefinite = accepted(snapshot(QuadraticTerminal{{2, 2, {2, 0, 0, 0}}, {0, 0}, 0}, policy));
    CHECK(accepted(evaluate(semidefinite, Vector{2, 7})) == 4);
    REQUIRE(semidefinite.quadratic_checks().has_value());
    CHECK(semidefinite.quadratic_checks()->minimum_eigenvalue == 0);
    CHECK(semidefinite.policy().assurance == Assurance::numerical);
    rejected(snapshot(QuadraticTerminal{{2, 2, {2, 0, 0, 0}}, {0, 0}, 0},
                      {Assurance::validated, {0.0625, 0}}),
             DiagnosticCode::unsupported, "objective.assurance");
}
