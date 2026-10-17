#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/optimization/zoutendijk/projection.hpp>

#include <memory>
#include <sstream>
#include <stop_token>

using namespace csl;
using namespace csl::optimization;
using namespace csl::optimization::zoutendijk;

namespace {
template<class T, class... Alternatives> T accepted(std::variant<T, Alternatives...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
SparseMatrix matrix_copy(const LinearProgram& program) {
    const auto csr = std::get<numeric::CsrInput>(program.constraints().descriptor());
    return {csr.rows, csr.cols, {csr.row_offsets.begin(), csr.row_offsets.end()},
        {csr.column_indices.begin(), csr.column_indices.end()}, {csr.values.begin(), csr.values.end()}};
}
LinearProgram polyhedron(std::string name, SparseMatrix matrix, std::vector<Interval> variables,
    std::vector<Interval> rows) {
    return accepted(make_linear_program({{{"zoutendijk"}, {std::move(name)}},
        Vector(variables.size(), 0), 0, std::move(matrix), std::move(variables), std::move(rows)}));
}
ExecutionContext context() {
    return {std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}),
        {}, {}, {1e-8, 1e-8}, "zoutendijk-test"};
}

struct Fixture {
    std::string name;
    LinearProgram feasible_set;
    Vector target;
    Vector start;
    Vector expected;
};
class LimitedWorkspace final : public LPWorkspace {
protected:
    ProgramOutcome do_solve(const LinearProgram& program, const ExecutionContext&) override {
        return ProgramResult{Termination::resource_limit,
            {program.identity(), MathematicalOutcome::undetermined, Unestablished{}, {}},
            {}, {}, "deliberate direction limit", {}};
    }
};
std::vector<Fixture> fixtures() {
    return {
        {"interval", polyhedron("interval", {0, 1, {0}, {}, {}}, {{0, 1}}, {}), {-2}, {0.5}, {0}},
        {"box", polyhedron("box", {0, 2, {0}, {}, {}}, {{0, 1}, {0, 1}}, {}), {2, 0.25}, {0.5, 0.5}, {1, 0.25}},
        {"face", polyhedron("face", {1, 2, {0, 2}, {0, 1}, {1, 1}}, {{0, {}}, {0, {}}}, {{1, 1}}),
            {2, 2}, {0.5, 0.5}, {0.5, 0.5}},
        {"singleton", polyhedron("singleton", {0, 1, {0}, {}, {}}, {{1, 1}}, {}), {4}, {1}, {1}}
    };
}
Vector reference_qp(const Fixture& fixture) {
    Vector linear(fixture.target.size());
    double offset = 0;
    Matrix q{fixture.target.size(), fixture.target.size(), Vector(fixture.target.size() * fixture.target.size(), 0)};
    for (std::size_t j = 0; j < fixture.target.size(); ++j) {
        q.values[j * q.cols + j] = 1;
        linear[j] = -fixture.target[j];
        offset = std::fma(0.5 * fixture.target[j], fixture.target[j], offset);
    }
    auto program = accepted(make_convex_program({
        {fixture.feasible_set.identity().problem, {fixture.name + "/reference-qp"}},
        QuadraticTerminal{std::move(q), std::move(linear), offset},
        matrix_copy(fixture.feasible_set),
        {fixture.feasible_set.variables().begin(), fixture.feasible_set.variables().end()},
        {fixture.feasible_set.rows().begin(), fixture.feasible_set.rows().end()}, {}}));
    auto registration = adapters::convex::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::ConvexPort>>(registration));
    auto backend = std::get<registry::Registration<registry::ConvexPort>>(std::move(registration));
    auto workspace = backend.factory(program);
    REQUIRE(workspace);
    auto solved = workspace->solve(program, context());
    if (const auto* unsupported = std::get_if<Unsupported>(&solved)) {
        std::ostringstream message;
        message << "Reference QP unsupported";
        for (const auto& diagnostic : unsupported->diagnostics)
            message << "; " << diagnostic.field << ": " << diagnostic.explanation;
        FAIL(message.str());
    }
    REQUIRE(std::holds_alternative<ProgramResult>(solved));
    const auto& answer = std::get<ProgramResult>(solved);
    REQUIRE(answer.termination == Termination::completed);
    REQUIRE(answer.outcome.value == MathematicalOutcome::optimal);
    REQUIRE(answer.primal);
    return *answer.primal;
}
}

TEST_CASE("feasible-direction projection agrees with analytic and independent QP fixtures") {
    auto registration = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(registration));
    auto backend = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    for (const auto& fixture : fixtures()) {
        auto workspace = backend.factory(fixture.feasible_set);
        REQUIRE(workspace);
        const auto outcome = project(fixture.feasible_set, fixture.target, fixture.start, *workspace, context());
        if (const auto* diagnostics = std::get_if<Diagnostics>(&outcome)) {
            std::ostringstream message;
            message << fixture.name << " diagnostics";
            for (const auto& diagnostic : *diagnostics)
                message << "; " << diagnostic.field << ": " << diagnostic.explanation;
            FAIL(message.str());
        }
        if (const auto* unsupported = std::get_if<Unsupported>(&outcome)) {
            std::ostringstream message;
            message << fixture.name << " unsupported";
            for (const auto& diagnostic : unsupported->diagnostics)
                message << "; " << diagnostic.field << ": " << diagnostic.explanation;
            FAIL(message.str());
        }
        REQUIRE(std::holds_alternative<ProjectionSuccess>(outcome));
        const auto& result = std::get<ProjectionSuccess>(outcome);
        REQUIRE(result.point.size() == fixture.expected.size());
        CHECK(result.stationarity_residual <= 1e-7);
        const auto reference = reference_qp(fixture);
        REQUIRE(reference.size() == fixture.expected.size());
        for (std::size_t j = 0; j < fixture.expected.size(); ++j) {
            CHECK(result.point[j] == doctest::Approx(fixture.expected[j]).epsilon(1e-7));
            CHECK(result.point[j] == doctest::Approx(reference[j]).epsilon(1e-7));
        }
        CHECK(result.distance == doctest::Approx(std::sqrt([&] {
            double sum = 0;
            for (std::size_t j = 0; j < fixture.expected.size(); ++j)
                sum = std::fma(fixture.expected[j] - fixture.target[j], fixture.expected[j] - fixture.target[j], sum);
            return sum;
        }())).epsilon(1e-7));
        CHECK(result.quadratic_objective == doctest::Approx(0.5 * result.distance * result.distance).epsilon(1e-7));
    }
}

TEST_CASE("direction step skips a zero-derivative inactive row before a finite bound") {
    auto feasible = polyhedron("zero-derivative-row", {2, 2, {0, 1, 2}, {1, 0}, {1, 1}},
        {{0, {}}, {0, {}}}, {{{}, 1}, {{}, 0.5}});
    auto registration = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(registration));
    auto backend = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto workspace = backend.factory(feasible);
    const auto outcome = project(feasible, Vector{2, 0}, Vector{0, 0}, *workspace, context());
    REQUIRE(std::holds_alternative<ProjectionSuccess>(outcome));
    const auto& result = std::get<ProjectionSuccess>(outcome);
    CHECK(result.point[0] == doctest::Approx(0.5).epsilon(1e-7));
    CHECK(result.point[1] == doctest::Approx(0).epsilon(1e-7));
}

TEST_CASE("target already feasible returns zero distance and infeasible supplied starts are rejected") {
    const auto feasible = polyhedron("start-policy", {0, 1, {0}, {}, {}}, {{0, 1}}, {});
    auto registration = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(registration));
    auto backend = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto workspace = backend.factory(feasible);
    const auto exact = project(feasible, Vector{0.25}, Vector{0.25}, *workspace, context());
    REQUIRE(std::holds_alternative<ProjectionSuccess>(exact));
    CHECK(std::get<ProjectionSuccess>(exact).distance == 0);
    CHECK(std::get<ProjectionSuccess>(exact).quadratic_objective == 0);
    const auto invalid = project(feasible, Vector{2}, Vector{2}, *workspace, context());
    REQUIRE(std::holds_alternative<Diagnostics>(invalid));
    CHECK(std::get<Diagnostics>(invalid)[0].field == "zoutendijk.start");
}

TEST_CASE("interrupted direction solves preserve the last iterate without an optimality claim") {
    const auto feasible = polyhedron("partial-result", {0, 1, {0}, {}, {}}, {{0, 1}}, {});
    LimitedWorkspace limited;
    const auto resource_stop = project(feasible, Vector{2}, Vector{0.25}, limited, context());
    REQUIRE(std::holds_alternative<ProjectionStopped>(resource_stop));
    const auto& partial = std::get<ProjectionStopped>(resource_stop);
    CHECK(partial.reason == ProjectionStopReason::resource_limit);
    CHECK(partial.last_feasible_iterate == Vector{0.25});

    auto lp_registration = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(lp_registration));
    auto backend = std::get<registry::Registration<registry::LPPort>>(std::move(lp_registration));
    auto workspace = backend.factory(feasible);
    std::stop_source cancelled;
    cancelled.request_stop();
    auto stopped_context = context();
    stopped_context.cancellation = cancelled.get_token();
    const auto cancellation = project(feasible, Vector{2}, Vector{0.25}, *workspace, stopped_context);
    REQUIRE(std::holds_alternative<ProjectionStopped>(cancellation));
    CHECK(std::get<ProjectionStopped>(cancellation).reason == ProjectionStopReason::cancelled);
}
