#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <limits>

using namespace csl;

namespace {
std::unique_ptr<LPWorkspace> highs_workspace() {
    auto registration = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(registration));
    auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto seed = optimization::make_linear_program({{{"hull"},{"seed"}}, {}, 0,
        {0,0,{0},{},{ }}, {}, {}});
    REQUIRE(std::holds_alternative<LinearProgram>(seed));
    return adapter.factory(std::get<LinearProgram>(seed));
}

bool independent_membership(LPWorkspace& workspace, const geometry::PointCloud& source,
        const std::vector<std::size_t>& hull, std::size_t candidate) {
    const auto dimension = source.points[candidate].size();
    const auto variables = hull.size();
    SparseMatrix a{dimension + 1, variables, {0}, {}, {}};
    Vector rhs = source.points[candidate];
    rhs.push_back(1.0);
    for (std::size_t row = 0; row <= dimension; ++row) {
        for (std::size_t col = 0; col < variables; ++col) {
            a.column_indices.push_back(col);
            a.values.push_back(row == dimension ? 1.0 : source.points[hull[col]][row]);
        }
        a.row_offsets.push_back(a.values.size());
    }
    std::vector<Interval> equalities;
    for (const double value : rhs) equalities.push_back({value, value});
    auto program = optimization::make_linear_program({
        {source.problem,{"independent-membership-" + std::to_string(candidate)}},
        Vector(variables, 0.0), 0.0, std::move(a),
        std::vector<Interval>(variables, {0.0, std::nullopt}), std::move(equalities)});
    if (!std::holds_alternative<LinearProgram>(program)) return false;
    auto outcome = workspace.solve(std::get<LinearProgram>(program), {});
    if (!std::holds_alternative<ProgramResult>(outcome)) return false;
    const auto& result = std::get<ProgramResult>(outcome);
    if (result.termination != Termination::completed || result.outcome.value != MathematicalOutcome::optimal ||
        !result.primal || result.primal->size() != variables) return false;
    double total = 0.0;
    Vector point(dimension, 0.0);
    for (std::size_t col = 0; col < variables; ++col) {
        if ((*result.primal)[col] < 0.0) return false;
        total += (*result.primal)[col];
        for (std::size_t row = 0; row < dimension; ++row)
            point[row] += (*result.primal)[col] * source.points[hull[col]][row];
    }
    if (std::abs(total - 1.0) > 1e-9) return false;
    for (std::size_t row = 0; row < dimension; ++row)
        if (std::abs(point[row] - source.points[candidate][row]) > 1e-9) return false;
    return true;
}

class LimitedWorkspace final : public LPWorkspace {
protected:
    ProgramOutcome do_solve(const LinearProgram& program, const ExecutionContext&) override {
        return ProgramResult{Termination::resource_limit,
            {program.identity(), MathematicalOutcome::undetermined, Unestablished{}, {}},
            {}, {}, "test resource limit", {}};
    }
};

class ApproximateFirstSupportWorkspace final : public LPWorkspace {
protected:
    ProgramOutcome do_solve(const LinearProgram& program, const ExecutionContext&) override {
        Vector weights(program.objective().size(), 0.0);
        weights.front() = 1.0;
        return ProgramResult{Termination::completed,
            {program.identity(), MathematicalOutcome::optimal, Unestablished{}, {}},
            std::move(weights), {}, "scripted locally acceptable approximate membership", {}};
    }
};

class MisboundInfeasibleWorkspace final : public LPWorkspace {
protected:
    ProgramOutcome do_solve(const LinearProgram&, const ExecutionContext&) override {
        return ProgramResult{Termination::completed,
            {ProgramIdentity{{"different-problem"}, {"stale-program"}},
                MathematicalOutcome::infeasible, Unestablished{}, {}},
            {}, {}, "stale infeasibility", {}};
    }
};

class CountingHullWorkspace final : public geometry::HullReducerWorkspace {
public:
    explicit CountingHullWorkspace(std::size_t& calls) : calls_(calls) {}
    geometry::HullReductionResult reduce(const geometry::PointCloud& cloud, LPWorkspace& lp,
            const ExecutionContext& context) override {
        ++calls_;
        return geometry::reduce_hull(cloud, lp, context);
    }
private:
    std::size_t& calls_;
};

class CountingLPWorkspace final : public LPWorkspace {
public:
    CountingLPWorkspace(std::unique_ptr<LPWorkspace> delegate, std::shared_ptr<std::size_t> calls)
        : delegate_(std::move(delegate)), calls_(std::move(calls)) {}
protected:
    ProgramOutcome do_solve(const LinearProgram& program, const ExecutionContext& context) override {
        ++*calls_;
        return delegate_->solve(program, context);
    }
private:
    std::unique_ptr<LPWorkspace> delegate_;
    std::shared_ptr<std::size_t> calls_;
};
} // namespace

TEST_CASE("hull reducer registry selection composes with an independently supplied LP workspace") {
    using Port = registry::HullReducerPort;
    std::size_t reducer_calls = 0;
    registry::Registry<Port> reducers;
    auto baseline_hull = geometry::make_lp_hull_reducer_registration();
    CHECK(baseline_hull.identity.id.value == "csl.hull.lp-membership");
    REQUIRE_FALSE(reducers.add(std::move(baseline_hull)));
    REQUIRE_FALSE(reducers.add({{{"test.counting-hull"}, "1"},
        [](const geometry::PointCloud&, const registry::Requirements&) -> registry::Capability {
            return registry::Offer{};
        },
        [&reducer_calls](const geometry::PointCloud&) {
            return std::make_unique<CountingHullWorkspace>(reducer_calls);
        }}));

    auto highs_result = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(highs_result));
    auto highs = std::get<registry::Registration<registry::LPPort>>(std::move(highs_result));
    auto seed_result = optimization::make_linear_program({{{"registered-lp"},{"seed"}}, {}, 0,
        {0,0,{0},{},{ }}, {}, {}});
    REQUIRE(std::holds_alternative<LinearProgram>(seed_result));
    const auto seed = std::get<LinearProgram>(std::move(seed_result));
    registry::Registry<registry::LPPort> lp_providers;
    auto add_counting_provider = [&](const char* method, const std::shared_ptr<std::size_t>& calls) {
        auto factory = highs.factory;
        return lp_providers.add({{{method}, "1"},
            [](const LinearProgram&, const registry::Requirements&) -> registry::Capability {
                return registry::Offer{};
            },
            [factory = std::move(factory), calls](const LinearProgram& request) {
                return std::make_unique<CountingLPWorkspace>(factory(request), calls);
            }});
    };
    const auto first_lp_calls = std::make_shared<std::size_t>(0);
    const auto second_lp_calls = std::make_shared<std::size_t>(0);
    REQUIRE_FALSE(add_counting_provider("test.lp-first", first_lp_calls));
    REQUIRE_FALSE(add_counting_provider("test.lp-second", second_lp_calls));

    const geometry::PointCloud cloud{{"registered-square"}, {{0,0}, {1,0}, {1,1}, {0,1}, {0.5,0.5}}};
    const auto prepared_result = registry::prepare_pipeline(
        registry::select(reducers, registry::Method{{"csl.hull.lp-membership"}, std::nullopt}, cloud));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<Port>>(prepared_result));
    auto prepared = std::get<registry::PreparedPipeline<Port>>(prepared_result);
    auto workspaces = prepared.create();
    auto& registered_reducer = *std::get<0>(workspaces);

    const auto first_lp_prepared_result = registry::prepare_pipeline(registry::select(lp_providers,
        registry::Method{{"test.lp-first"}, std::nullopt}, seed));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<registry::LPPort>>(first_lp_prepared_result));
    auto first_lp_prepared = std::get<registry::PreparedPipeline<registry::LPPort>>(first_lp_prepared_result);
    auto first_lp_workspaces = first_lp_prepared.create();
    registry::LPWorkspaceView selected_lp(*std::get<0>(first_lp_workspaces));
    auto outcome = registered_reducer.run_with(ExecutionContext{}, selected_lp);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(outcome));
    CHECK(reducer_calls == 0);
    CHECK(*first_lp_calls == 5);
    const auto& result = std::get<geometry::HullReduction>(outcome);
    CHECK(result.status == geometry::ReductionStatus::complete);
    CHECK(prepared.provenance()[0].actual->id.value == "csl.hull.lp-membership");

    const auto alternative_result = registry::prepare_pipeline(registry::select(reducers,
        registry::Method{{"test.counting-hull"}, std::nullopt}, cloud));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<Port>>(alternative_result));
    auto alternative = std::get<registry::PreparedPipeline<Port>>(alternative_result).create();
    auto& substituted_reducer = *std::get<0>(alternative);

    const auto second_lp_prepared_result = registry::prepare_pipeline(registry::select(lp_providers,
        registry::Method{{"test.lp-second"}, std::nullopt}, seed));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<registry::LPPort>>(second_lp_prepared_result));
    auto second_lp_prepared = std::get<registry::PreparedPipeline<registry::LPPort>>(second_lp_prepared_result);
    auto second_lp_workspaces = second_lp_prepared.create();
    registry::LPWorkspaceView second_lp(*std::get<0>(second_lp_workspaces));
    auto second = substituted_reducer.run_with(ExecutionContext{}, second_lp);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(second));
    CHECK(reducer_calls == 1);
    CHECK(*second_lp_calls == 5);
    auto independent_lp = highs_workspace();
    for (std::size_t point = 0; point < cloud.points.size(); ++point)
        CHECK(independent_membership(*independent_lp, cloud,
            std::get<geometry::HullReduction>(second).retained, point));
}

TEST_CASE("LP hull reduction removes a point only with a barycentric certificate") {
    auto workspace = highs_workspace();
    REQUIRE(workspace != nullptr);

    const geometry::PointCloud cloud{{"square"}, {
        {0,0}, {1,0}, {1,1}, {0,1}, {0.5,0.5}, {0.5,0}
    }};
    auto result = geometry::reduce_hull(cloud, *workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    CHECK(reduction.status == geometry::ReductionStatus::complete);
    CHECK(reduction.retained.size() == 4);
    CHECK(reduction.attempts.size() == 6);
    CHECK(reduction.lp_calls == 6);
    CHECK(reduction.removed.size() == 2);
    for (const auto& certificate : reduction.removed) {
        CHECK(certificate.program.problem == cloud.problem);
        CHECK(certificate.program.program.value == "hull-membership-" + std::to_string(certificate.removed));
        double total = 0;
        Vector reconstructed(2, 0);
        for (const auto& term : certificate.combination) {
            CHECK(term.point != certificate.removed);
            REQUIRE(term.weight >= 0);
            total += term.weight;
            reconstructed[0] += term.weight * cloud.points[term.point][0];
            reconstructed[1] += term.weight * cloud.points[term.point][1];
        }
        CHECK(total == doctest::Approx(1).epsilon(1e-10));
        CHECK(reconstructed[0] == doctest::Approx(cloud.points[certificate.removed][0]).epsilon(1e-10));
        CHECK(reconstructed[1] == doctest::Approx(cloud.points[certificate.removed][1]).epsilon(1e-10));
    }

    // Independent LP construction/membership queries establish conv(original)
    // is contained in conv(retained); the reverse inclusion follows because
    // every retained point is an original point.
    auto oracle = highs_workspace();
    for (std::size_t point = 0; point < cloud.points.size(); ++point)
        CHECK(independent_membership(*oracle, cloud, reduction.retained, point));
}

TEST_CASE("LP hull reduction handles empty, singleton, duplicate and flat clouds") {
    auto workspace = highs_workspace();
    const geometry::PointCloud empty{{"empty"}, {}};
    auto empty_result = geometry::reduce_hull(empty, *workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(empty_result));
    CHECK(std::get<geometry::HullReduction>(empty_result).retained.empty());
    CHECK(std::get<geometry::HullReduction>(empty_result).lp_calls == 0);

    const geometry::PointCloud singleton{{"singleton"}, {{3.0, -2.0}}};
    auto singleton_result = geometry::reduce_hull(singleton, *workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(singleton_result));
    CHECK(std::get<geometry::HullReduction>(singleton_result).retained == std::vector<std::size_t>{0});
    CHECK(std::get<geometry::HullReduction>(singleton_result).lp_calls == 0);

    const geometry::PointCloud duplicates{{"duplicates"}, {{2.0}, {2.0}, {2.0}}};
    auto duplicate_result = geometry::reduce_hull(duplicates, *workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(duplicate_result));
    CHECK(std::get<geometry::HullReduction>(duplicate_result).retained.size() == 1);
    CHECK(std::get<geometry::HullReduction>(duplicate_result).removed.size() == 2);

    const geometry::PointCloud segment{{"flat"}, {{-2.0, 1.0, 4.0}, {0.0, 1.0, 4.0},
        {2.0, 1.0, 4.0}, {1.0, 1.0, 4.0}}};
    auto segment_result = geometry::reduce_hull(segment, *workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(segment_result));
    const auto& reduced = std::get<geometry::HullReduction>(segment_result);
    CHECK(reduced.retained.size() == 2);
    CHECK(reduced.removed.size() == 2);

    const geometry::PointCloud zero_dimensional{{"zero-dimensional"}, {{}, {}, {}}};
    auto zero_result = geometry::reduce_hull(zero_dimensional, *workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(zero_result));
    CHECK(std::get<geometry::HullReduction>(zero_result).retained.size() == 1);
}

TEST_CASE("uncertain membership never removes a point and reports an incomplete reduction") {
    LimitedWorkspace workspace;
    const geometry::PointCloud cloud{{"stopped"}, {{0.0}, {1.0}, {0.5}}};
    auto result = geometry::reduce_hull(cloud, workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    CHECK(reduction.status == geometry::ReductionStatus::incomplete);
    CHECK(reduction.retained == std::vector<std::size_t>{0,1,2});
    CHECK(reduction.removed.empty());
    CHECK(reduction.lp_calls == 1);
    REQUIRE(!reduction.attempts.empty());
    CHECK(reduction.attempts.front().outcome == geometry::MembershipOutcome::stopped);
}

TEST_CASE("accepted local certificates cannot exceed tolerance after later support removals") {
    ApproximateFirstSupportWorkspace workspace;
    const geometry::PointCloud cloud{{"certificate-chain"}, {{0.0}, {7.5e-9}, {1.5e-8}}};
    ExecutionContext context{};
    context.numerical = {1e-8, 0.0};

    auto result = geometry::reduce_hull(cloud, workspace, context);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    REQUIRE(reduction.status == geometry::ReductionStatus::complete);
    REQUIRE(!reduction.retained.empty());

    double lower = cloud.points[reduction.retained.front()][0];
    double upper = lower;
    for (const auto index : reduction.retained) {
        lower = std::min(lower, cloud.points[index][0]);
        upper = std::max(upper, cloud.points[index][0]);
    }
    for (const auto& point : cloud.points) {
        const double distance = point[0] < lower ? lower - point[0] :
            (point[0] > upper ? point[0] - upper : 0.0);
        CHECK(distance <= context.numerical.absolute_tolerance);
    }
}

TEST_CASE("a mismatched completed infeasibility result is malformed, not a valid exclusion") {
    MisboundInfeasibleWorkspace workspace;
    const geometry::PointCloud cloud{{"identity-check"}, {{0.0}, {1.0}}};

    auto result = geometry::reduce_hull(cloud, workspace, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    CHECK(reduction.status == geometry::ReductionStatus::incomplete);
    CHECK(reduction.retained == std::vector<std::size_t>{0, 1});
    REQUIRE(!reduction.attempts.empty());
    CHECK(reduction.attempts.front().outcome == geometry::MembershipOutcome::malformed_result);
    CHECK(reduction.removed.empty());
}

TEST_CASE("hull reducer rejects inconsistent and non-finite point clouds") {
    auto workspace = highs_workspace();
    const geometry::PointCloud inconsistent{{"bad-dimension"}, {{0.0}, {0.0, 1.0}}};
    CHECK(std::holds_alternative<Diagnostics>(geometry::reduce_hull(inconsistent, *workspace, {})));
    const geometry::PointCloud non_finite{{"non-finite"}, {{std::numeric_limits<double>::infinity()}}};
    CHECK(std::holds_alternative<Diagnostics>(geometry::reduce_hull(non_finite, *workspace, {})));
}
