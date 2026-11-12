#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/polyhedral_intersection.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/reachability/nominal_tube.hpp>
#include <csl/registry/provider.hpp>

#include <algorithm>
#include <cmath>
#include <memory>
#include <stop_token>
#include <string>
#include <type_traits>
#include <vector>

using namespace csl;
using namespace csl::registry;
using namespace csl::reachability;
using numeric::MatrixView;
using numeric::VectorView;

namespace {
template<class T, class... E> T take(std::variant<T, E...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

template<class Port> PreparedProvider<Port> selected(Registration<Port> entry,
        std::string representation, std::optional<SetRelation> relation = {}) {
    Registry<Port> registry;
    const Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if (relation) requirements.output.relation = relation;
    else if constexpr (std::is_same_v<Port, GeometryPort> || std::is_same_v<Port, ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry, method, requirements)));
}

MatrixView matrix(std::size_t rows, std::size_t columns, Vector values) {
    return take(numeric::snapshot(Matrix{rows, columns, std::move(values)}));
}
VectorView vector(Vector values) { return take(numeric::snapshot_vector(std::move(values))); }

SetHandle box(std::string id, std::vector<std::string> labels, Vector lower, Vector upper) {
    REQUIRE(lower.size() == upper.size());
    const auto dimension = lower.size();
    Matrix a{2 * dimension, dimension, Vector(2 * dimension * dimension, 0.0)};
    Vector b(2 * dimension, 0.0);
    for (std::size_t coordinate = 0; coordinate < dimension; ++coordinate) {
        a.values[(2 * coordinate) * dimension + coordinate] = 1.0;
        b[2 * coordinate] = upper[coordinate];
        a.values[(2 * coordinate + 1) * dimension + coordinate] = -1.0;
        b[2 * coordinate + 1] = -lower[coordinate];
    }
    return take(sets::make_h({{std::move(id)}, dimension, std::move(labels)},
        {matrix(a.rows, a.cols, std::move(a.values)), vector(std::move(b)),
         matrix(0, dimension, {}), vector({})})).as_handle();
}

struct Providers {
    ForwardDependencies forward;
    PreparedProvider<GeometryPort> intersection;
    std::optional<PreparedProvider<ConversionPort>> compact_h_to_v;
};

Providers providers(std::optional<std::size_t> projection_rows = {}, bool compact_h = false) {
    auto lp = take(adapters::lp::make_highs_registration());
    auto qhull = take(adapters::polyhedral::make_qhull_registration(lp));
    auto projection = geometry::polyhedral::make_projection_registration(
        {geometry::polyhedral::ProjectionOutput::h, projection_rows});
    auto affine = geometry::make_affine_sum_registration({
        selected(geometry::make_lp_hull_reducer_registration(), ""),
        selected(lp, "csl.program-result.v1"),
        selected(qhull, "csl.polyhedron.v")}, {{}, {}});
    auto intersection = geometry::polyhedral::make_intersection_registration();
    return {{selected(std::move(projection), "csl.polyhedron.h", SetRelation::equivalent),
        selected(std::move(affine), "csl.polyhedron.v"),
        selected(qhull, "csl.polyhedron.h")},
        selected(std::move(intersection), "csl.polyhedron.h", SetRelation::equivalent),
        compact_h ? std::optional{selected(qhull, "csl.polyhedron.v")} : std::nullopt};
}

Matrix identity2() { return {2, 2, {1, 0, 0, 1}}; }
LinearStage stage2(Matrix a, Matrix b, Vector offset) {
    return {std::move(a), std::move(b), {2, 0, {}}, std::move(offset)};
}
Problem two_step_problem() {
    const auto dynamics = std::vector<LinearStage>{
        stage2(identity2(), identity2(), {0.2, -0.2}),
        stage2(identity2(), identity2(), {-0.1, 0.4})};
    auto model = std::make_shared<const SystemModel>(SystemModel{
        {{2, 2, 0}, TimeDomain::discrete, dynamics}, {}});
    const auto x = std::vector<std::string>{"x", "y"};
    const auto u = std::vector<std::string>{"u_x", "u_y"};
    return {{"two-step-analytic"}, std::move(model), {0, 1, 2}, KnownInitial{{0.5, 1.5}},
        ContinuousDomain{{box("u0", u, {-0.25, -0.4}, {0.5, 0.2}),
                          box("u1", u, {-0.3, -0.2}, {0.4, 0.3})}},
        {box("X0", x, {-2, 0}, {2, 4}),
         box("X1", x, {0.6, 0.8}, {1, 1.4}),
         box("X2", x, {0.4, 1.2}, {1.1, 1.9})}, {}, {},
        InformationPattern::nominal_open_loop,
        QuadraticTerminal{{2, 2, {2, 0, 0, 2}}, {0, 0}, 0}};
}

Problem rank_deficient_problem() {
    const auto dynamics = std::vector<LinearStage>{
        stage2({2, 2, {1, 0, 0, 0}}, identity2(), {0, 0})};
    auto model = std::make_shared<const SystemModel>(SystemModel{
        {{2, 2, 0}, TimeDomain::discrete, dynamics}, {}});
    const auto labels = std::vector<std::string>{"x", "y"};
    const auto controls = std::vector<std::string>{"u_x", "u_y"};
    return {{"rank-deficient"}, std::move(model), {0, 1}, KnownInitial{{0, 2}},
        ContinuousDomain{{box("u0", controls, {-1, -1}, {1, 1})}},
        {box("X0", labels, {-2, -2}, {2, 3}), box("X1", labels, {-1, 0}, {1, 1})}, {}, {},
        InformationPattern::nominal_open_loop,
        QuadraticTerminal{{2, 2, {2, 0, 0, 2}}, {0, 0}, 0}};
}

Problem zero_step_3d_problem() {
    auto model = std::make_shared<const SystemModel>(SystemModel{
        {{3, 0, 0}, TimeDomain::discrete, std::vector<LinearStage>{}}, {}});
    const auto labels = std::vector<std::string>{"x", "y", "z"};
    return {{"full-state-disjoint-3d"}, std::move(model), {0}, KnownInitial{{0, 0, 0}},
        ContinuousDomain{{}}, {box("X0", labels, {-2, -2, -2}, {2, 2, 3})}, {}, {},
        InformationPattern::nominal_open_loop,
        QuadraticTerminal{{3, 3, {2,0,0,0,2,0,0,0,2}}, {0,0,0}, 0}};
}

problem::ResolvedProblem resolve(Problem source) {
    auto result = problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    return take(std::move(result));
}

std::pair<double, double> axis_bounds(const SetHandle& handle, std::size_t coordinate) {
    const auto data = take(sets::from_handle(handle));
    const auto representation = data.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h = std::get<sets::HRepresentation>(representation);
    double lower = -std::numeric_limits<double>::infinity();
    double upper = std::numeric_limits<double>::infinity();
    for (std::size_t row = 0; row < h.inequalities.rows(); ++row) {
        std::size_t nonzero = 0;
        for (std::size_t column = 0; column < h.inequalities.cols(); ++column)
            nonzero += h.inequalities(row, column) != 0.0;
        REQUIRE(nonzero <= 1);
        const auto coefficient = h.inequalities(row, coordinate);
        if (coefficient > 0.0) upper = std::min(upper, h.upper_bounds[row] / coefficient);
        else if (coefficient < 0.0) lower = std::max(lower, h.upper_bounds[row] / coefficient);
        else continue;
    }
    for (std::size_t row = 0; row < h.equalities.rows(); ++row) {
        std::size_t nonzero = 0;
        for (std::size_t column = 0; column < h.equalities.cols(); ++column)
            nonzero += h.equalities(row, column) != 0.0;
        REQUIRE(nonzero <= 1);
        const auto coefficient = h.equalities(row, coordinate);
        if (coefficient != 0.0) {
            const auto value = h.equality_values[row] / coefficient;
            lower = std::max(lower, value);
            upper = std::min(upper, value);
        }
    }
    return {lower, upper};
}

NominalTubeOutcome run(Problem source, SetHandle terminal, Providers selected_providers,
        ExecutionContext context = {}) {
    return nominal_tube(resolve(std::move(source)), {"analytic-tube"}, terminal,
        {std::move(selected_providers.forward), std::move(selected_providers.intersection),
         std::move(selected_providers.compact_h_to_v)}, context);
}

void check_range(const SetHandle& set, std::size_t coordinate, double lower, double upper) {
    const auto range = axis_bounds(set, coordinate);
    CHECK(range.first == doctest::Approx(lower));
    CHECK(range.second == doctest::Approx(upper));
}

std::string describe(const NominalTubeOutcome& outcome) {
    if (const auto* failure = std::get_if<NominalTubeFailure>(&outcome)) {
        if (const auto* unsupported = std::get_if<Unsupported>(&failure->cause)) {
            std::string result = "unsupported at stage " + std::to_string(failure->stage.value) + ":";
            for (const auto& diagnostic : unsupported->diagnostics)
                result += " " + diagnostic.field + "=" + diagnostic.explanation;
            return result;
        }
        const auto& stopped = std::get<OperationStopped>(failure->cause);
        return "stopped at stage " + std::to_string(failure->stage.value) + ": " + stopped.diagnostics;
    }
    return std::holds_alternative<NominalTubeEmptyForward>(outcome) ? "empty forward" : "complete";
}
}

TEST_CASE("two-stage full-state H tube matches independent box arithmetic at every stage") {
    const auto terminal = box("physical-terminal", {"x", "y"}, {0.7, 1.4}, {0.9, 1.6});
    const auto result = run(two_step_problem(), terminal, providers());
    INFO(describe(result));
    REQUIRE(std::holds_alternative<NominalTube>(result));
    const auto& tube = std::get<NominalTube>(result);
    REQUIRE(tube.stages.size() == 3);
    for (std::size_t stage = 0; stage < tube.stages.size(); ++stage) {
        CHECK(tube.stages[stage].stage.value == stage);
        REQUIRE(tube.stages[stage].forward);
        REQUIRE(tube.stages[stage].backward);
        REQUIRE(tube.stages[stage].intersection);
        CHECK(tube.stages[stage].coordinates == std::vector<std::size_t>{0, 1});
        CHECK_FALSE(tube.stages[stage].requests.empty());
        CHECK_FALSE(tube.stages[stage].providers.empty());
        CHECK_FALSE(tube.stages[stage].lineage.empty());
    }
    CHECK(std::any_of(tube.stages[0].requests.begin(), tube.stages[0].requests.end(),
        [](const auto& request) { return request.identity.request.value.find("predecessor") != std::string::npos; }));
    const auto& stages = tube.stages;
    check_range(stages[0].forward->output, 0, 0.5, 0.5);
    check_range(stages[0].forward->output, 1, 1.5, 1.5);
    check_range(stages[0].backward->output, 0, -0.1, 1.05);
    check_range(stages[0].backward->output, 1, 0.8, 2.0);
    check_range(stages[0].intersection->output, 0, 0.5, 0.5);
    check_range(stages[0].intersection->output, 1, 1.5, 1.5);

    check_range(stages[1].forward->output, 0, 0.6, 1.0);
    check_range(stages[1].forward->output, 1, 0.9, 1.4);
    check_range(stages[1].backward->output, 0, 0.6, 1.0);
    check_range(stages[1].backward->output, 1, 0.8, 1.4);
    check_range(stages[1].intersection->output, 0, 0.6, 1.0);
    check_range(stages[1].intersection->output, 1, 0.9, 1.4);

    check_range(stages[2].forward->output, 0, 0.4, 1.1);
    check_range(stages[2].forward->output, 1, 1.2, 1.9);
    check_range(stages[2].backward->output, 0, 0.7, 0.9);
    check_range(stages[2].backward->output, 1, 1.4, 1.6);
    check_range(stages[2].intersection->output, 0, 0.7, 0.9);
    check_range(stages[2].intersection->output, 1, 1.4, 1.6);
    CHECK(stages[2].forward->evidence.support.index() == 0);
    CHECK(stages[2].intersection->evidence.reference.inputs.size() == 2);
}

TEST_CASE("existential predecessor projection handles noninvertible state dynamics") {
    const auto terminal = box("terminal", {"x", "y"}, {0.2, 0.7}, {0.5, 0.9});
    const auto result = run(rank_deficient_problem(), terminal, providers());
    INFO(describe(result));
    REQUIRE(std::holds_alternative<NominalTube>(result));
    const auto& tube = std::get<NominalTube>(result);
    REQUIRE(tube.stages.size() == 2);
    CHECK(tube.stages[0].backward.has_value());
    CHECK(tube.stages[1].backward.has_value());
    check_range(tube.stages[0].intersection->output, 0, 0, 0);
    check_range(tube.stages[0].intersection->output, 1, 2, 2);
    check_range(tube.stages[1].backward->output, 0, 0.2, 0.5);
    check_range(tube.stages[1].backward->output, 1, 0.7, 0.9);
}

TEST_CASE("3D full-state intersection is empty even while its xy projections overlap") {
    const auto terminal = box("z-slab", {"x", "y", "z"}, {-1, -1, 2}, {1, 1, 3});
    const auto result = run(zero_step_3d_problem(), terminal, providers());
    INFO(describe(result));
    REQUIRE(std::holds_alternative<NominalTube>(result));
    const auto& intersection = *std::get<NominalTube>(result).stages[0].intersection;
    const auto full_state = take(sets::from_handle(intersection.output));
    CHECK(full_state.metadata()->set.dimension == 3);
    const auto x = axis_bounds(intersection.output, 0);
    const auto y = axis_bounds(intersection.output, 1);
    const auto z = axis_bounds(intersection.output, 2);
    CHECK(x.first <= 0.0); CHECK(x.second >= 0.0);
    CHECK(y.first <= 0.0); CHECK(y.second >= 0.0);
    CHECK(z.first > z.second);
}

TEST_CASE("empty terminal feasibility remains an empty full-state intersection") {
    const auto unreachable = box("unreachable-terminal", {"x", "y"}, {2, 3}, {3, 4});
    const auto result = run(two_step_problem(), unreachable, providers());
    INFO(describe(result));
    REQUIRE(std::holds_alternative<NominalTube>(result));
    const auto& final = *std::get<NominalTube>(result).stages.back().intersection;
    CHECK(axis_bounds(final.output, 0).first > axis_bounds(final.output, 0).second);
}

TEST_CASE("optional bounded H compaction records H-to-V-to-H and preserves membership") {
    const auto terminal = take(sets::make_h({{"z-slab-with-small-redundant-row"}, 3, {"x", "y", "z"}},
        {matrix(7, 3, {1,0,0,-1,0,0,0,1,0,0,-1,0,0,0,1,0,0,-1,
                1.0e-17,-2.0e-17,0}),
         vector({1,1,1,1,3,-2,20}), matrix(0, 3, {}), vector({})})).as_handle();
    const auto result = run(zero_step_3d_problem(), terminal, providers({}, true));
    INFO(describe(result));
    REQUIRE(std::holds_alternative<NominalTube>(result));
    const auto& stage = std::get<NominalTube>(result).stages[0];
    REQUIRE(stage.backward);
    const auto backward = take(sets::from_handle(stage.backward->output));
    const auto representation = backward.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h = std::get<sets::HRepresentation>(representation);
    CHECK(h.inequalities.rows() == 6);
    CHECK(stage.backward->relation == SetRelation::equivalent);
    CHECK(std::any_of(stage.requests.begin(), stage.requests.end(), [](const auto& request) {
        return request.identity.request.value.find("compact-h/to-v") != std::string::npos;
    }));
    CHECK(std::any_of(stage.requests.begin(), stage.requests.end(), [](const auto& request) {
        return request.identity.request.value.find("compact-h/to-h") != std::string::npos;
    }));
    CHECK(std::any_of(stage.requests.begin(), stage.requests.end(), [](const auto& request) {
        return request.identity.request.value.find("compact-h/box-reduction") != std::string::npos;
    }));
    CHECK(std::any_of(stage.lineage.begin(), stage.lineage.end(), [](const auto& evidence) {
        return std::holds_alternative<SymbolicArgument>(evidence.support) &&
            std::get<SymbolicArgument>(evidence.support).reference.find("coordinate-box") != std::string::npos;
    }));
    CHECK(std::count_if(stage.providers.begin(), stage.providers.end(), [](const auto& provider) {
        return provider.port == "conversion" && provider.actual_module &&
            provider.actual_module->value == "csl.conversion.qhull";
    }) >= 2);
    CHECK(stage.backward->evidence.reference.inputs.size() == 2);
    CHECK(stage.backward->evidence.support.index() == 0);
    CHECK(axis_bounds(stage.backward->output, 0).first == doctest::Approx(-1));
    CHECK(axis_bounds(stage.backward->output, 0).second == doctest::Approx(1));
    CHECK(axis_bounds(stage.backward->output, 2).first == doctest::Approx(2));
    CHECK(axis_bounds(stage.backward->output, 2).second == doctest::Approx(3));
}

TEST_CASE("tube preserves cancellation and projection row-capacity failures with phase and stage") {
    const auto terminal = box("physical-terminal", {"x", "y"}, {0.7, 1.4}, {0.9, 1.6});
    std::stop_source cancellation;
    cancellation.request_stop();
    ExecutionContext context;
    context.cancellation = cancellation.get_token();
    const auto cancelled = run(two_step_problem(), terminal, providers(), context);
    INFO(describe(cancelled));
    REQUIRE(std::holds_alternative<NominalTubeFailure>(cancelled));
    const auto& cancelled_failure = std::get<NominalTubeFailure>(cancelled);
    CHECK(cancelled_failure.phase == NominalTubePhase::forward);
    CHECK(cancelled_failure.stage.value == 0);
    REQUIRE(std::holds_alternative<OperationStopped>(cancelled_failure.cause));
    CHECK(std::get<OperationStopped>(cancelled_failure.cause).reason == StopReason::cancelled);

    const auto limited = run(two_step_problem(), terminal, providers(1));
    INFO(describe(limited));
    REQUIRE(std::holds_alternative<NominalTubeFailure>(limited));
    const auto& capacity_failure = std::get<NominalTubeFailure>(limited);
    CHECK(capacity_failure.phase == NominalTubePhase::forward);
    CHECK(capacity_failure.stage.value == 0);
    REQUIRE(std::holds_alternative<Unsupported>(capacity_failure.cause));
    CHECK_FALSE(capacity_failure.forward_providers.empty());
    REQUIRE(capacity_failure.active_request);
}
