#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <csl/geometry/basis_reuse_reducer.hpp>
#include "../../../src/geometry/exact_convex_combination.hpp"
#include <array>
#include <cmath>
#include <csl/registry/provider.hpp>
#include <limits>

using namespace csl;

namespace {
TEST_CASE("exact convex combination verifier uses exact binary64 arithmetic") {
    using geometry::ConvexCombination;
    using geometry::PointCloud;
    using geometry::detail::exact_convex_combination;

    const PointCloud midpoint{{"exact-midpoint"}, {{0.0}, {1.0}, {0.5}}};
    CHECK(exact_convex_combination(midpoint, 2, std::array<ConvexCombination, 2>{{{0, 0.5}, {1, 0.5}}}));

    // The exact average rounds to 0.5 in binary64, but this certificate is
    // wrong by one representable step and must not pass a tolerance check.
    const PointCloud rounded{{"rounded-away-error"}, {{0.0}, {1.0}, {std::nextafter(0.5, 1.0)}}};
    CHECK_FALSE(exact_convex_combination(rounded, 2, std::array<ConvexCombination, 2>{{{0, 0.5}, {1, 0.5}}}));

    const double tiny = std::numeric_limits<double>::denorm_min();
    const PointCloud subnormal{{"subnormal-product"}, {{0.0}, {tiny}, {0.0}}};
    CHECK_FALSE(exact_convex_combination(subnormal, 2, std::array<ConvexCombination, 2>{{{1, 0.5}, {0, 0.5}}}));
    CHECK(exact_convex_combination(subnormal, 2, std::array<ConvexCombination, 2>{{{0, 1.0}}}));
}

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

class RecordingLPWorkspace final : public LPWorkspace {
public:
    RecordingLPWorkspace(std::unique_ptr<LPWorkspace> delegate,
            std::shared_ptr<std::vector<WorkspaceIdentity>> identities,
            std::shared_ptr<std::size_t> solves)
        : delegate_(std::move(delegate)), identities_(std::move(identities)), solves_(std::move(solves)) {}
protected:
    ProgramOutcome do_solve(const LinearProgram& program, const ExecutionContext& context) override {
        ++*solves_;
        identities_->push_back(workspace_identity());
        return delegate_->solve(program, context);
    }
private:
    std::unique_ptr<LPWorkspace> delegate_;
    std::shared_ptr<std::vector<WorkspaceIdentity>> identities_;
    std::shared_ptr<std::size_t> solves_;
};
} // namespace

TEST_CASE("registered hull queries preflight each LP and retain provider identity after registry exit") {
    auto capability_calls = std::make_shared<std::size_t>(0);
    auto factory_calls = std::make_shared<std::size_t>(0);
    auto solve_calls = std::make_shared<std::size_t>(0);
    auto workspace_identities = std::make_shared<std::vector<WorkspaceIdentity>>();
    auto provider = [&] {
        auto highs_result = adapters::lp::make_highs_registration();
        REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(highs_result));
        auto highs = std::get<registry::Registration<registry::LPPort>>(std::move(highs_result));
        registry::Registry<registry::LPPort> lp_registry;
        auto factory = highs.factory;
        REQUIRE_FALSE(lp_registry.add({{{"test.per-query-lp"}, "3.2"},
            [capability_calls](const LinearProgram&, const registry::Requirements&) -> registry::Capability {
                ++*capability_calls;
                return registry::Offer{};
            },
            [factory = std::move(factory), factory_calls, solve_calls, workspace_identities](const LinearProgram& request) {
                ++*factory_calls;
                return std::make_unique<RecordingLPWorkspace>(factory(request), workspace_identities, solve_calls);
            }}));
        auto result = registry::prepare_provider(registry::select_provider(lp_registry,
            registry::Method{{"test.per-query-lp"}, std::nullopt}));
        REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(result));
        return std::get<registry::PreparedProvider<registry::LPPort>>(std::move(result));
    }();

    registry::Registry<registry::HullReducerPort> reducers;
    REQUIRE_FALSE(reducers.add(geometry::make_lp_hull_reducer_registration()));
    const geometry::PointCloud cloud{{"provider-hull"}, {{0.0}, {1.0}, {0.5}}};
    auto prepared_reducer = registry::prepare_pipeline(registry::select(reducers,
        registry::Method{{"csl.hull.lp-membership"}, std::nullopt}, cloud));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<registry::HullReducerPort>>(prepared_reducer));
    auto reducer_workspaces = std::get<registry::PreparedPipeline<registry::HullReducerPort>>(
        std::move(prepared_reducer)).create();
    registry::RegisteredLPQueryRunner runner(std::move(provider));
    const auto result = std::get<0>(reducer_workspaces)->run_with(ExecutionContext{}, runner);

    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    CHECK(reduction.status == geometry::ReductionStatus::complete);
    CHECK(reduction.retained == std::vector<std::size_t>{0, 1});
    CHECK(reduction.lp_calls == 3);
    CHECK(*capability_calls == 3);
    CHECK(*factory_calls == 3);
    CHECK(*solve_calls == 3);
    REQUIRE(runner.records().size() == 3);
    REQUIRE(std::holds_alternative<registry::LPQueryCompleted>(runner.records()[0]));
    CHECK(std::get<registry::LPQueryCompleted>(runner.records()[0]).request.program.value == "hull-membership-0");
    CHECK(std::get<registry::LPQueryCompleted>(runner.records()[0]).returned_subject.program.value == "hull-membership-0");
    CHECK(std::get<registry::LPQueryCompleted>(runner.records()[0]).provider.actual->id.value == "test.per-query-lp");
    CHECK(std::get<registry::LPQueryCompleted>(runner.records()[0]).provider.actual->version == "3.2");
    CHECK(std::get<registry::LPQueryCompleted>(runner.records()[2]).request.program.value == "hull-membership-2");
    REQUIRE(workspace_identities->size() == 3);
    CHECK_FALSE((*workspace_identities)[0] == (*workspace_identities)[1]);
    CHECK_FALSE((*workspace_identities)[1] == (*workspace_identities)[2]);
}

TEST_CASE("provider capacity rejection creates no LP workspace for the incompatible hull query") {
    auto capability_calls = std::make_shared<std::size_t>(0);
    auto factory_calls = std::make_shared<std::size_t>(0);
    auto solve_calls = std::make_shared<std::size_t>(0);
    auto provider = [&] {
        auto highs_result = adapters::lp::make_highs_registration();
        REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(highs_result));
        auto highs = std::get<registry::Registration<registry::LPPort>>(std::move(highs_result));
        registry::Registry<registry::LPPort> lp_registry;
        auto factory = highs.factory;
        REQUIRE_FALSE(lp_registry.add({{{"test.minimum-membership-capacity"}, "1"},
            [capability_calls](const LinearProgram& request, const registry::Requirements&) -> registry::Capability {
                ++*capability_calls;
                if (request.objective().size() < 5)
                    return Diagnostics{{DiagnosticCode::unsupported, "test.membership_capacity",
                        "requires at least five membership weights"}};
                return registry::Offer{};
            },
            [factory = std::move(factory), factory_calls, solve_calls](const LinearProgram& request) {
                ++*factory_calls;
                return std::make_unique<CountingLPWorkspace>(factory(request), solve_calls);
            }}));
        auto result = registry::prepare_provider(registry::select_provider(lp_registry,
            registry::Method{{"test.minimum-membership-capacity"}, std::nullopt}));
        REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(result));
        return std::get<registry::PreparedProvider<registry::LPPort>>(std::move(result));
    }();

    registry::Registry<registry::HullReducerPort> reducers;
    REQUIRE_FALSE(reducers.add(geometry::make_lp_hull_reducer_registration()));
    const geometry::PointCloud cloud{{"rejected-provider-hull"},
        {{0,0}, {1,0}, {1,1}, {0,1}, {0.5,0.5}, {0.5,0.5}, {0.5,0.5}}};
    auto prepared_reducer = registry::prepare_pipeline(registry::select(reducers,
        registry::Method{{"csl.hull.lp-membership"}, std::nullopt}, cloud));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<registry::HullReducerPort>>(prepared_reducer));
    auto reducer_workspaces = std::get<registry::PreparedPipeline<registry::HullReducerPort>>(
        std::move(prepared_reducer)).create();
    registry::RegisteredLPQueryRunner runner(std::move(provider));
    const auto result = std::get<0>(reducer_workspaces)->run_with(ExecutionContext{}, runner);

    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    CHECK(reduction.status == geometry::ReductionStatus::incomplete);
    CHECK(reduction.retained == std::vector<std::size_t>{0, 1, 2, 3, 6});
    CHECK(reduction.lp_calls == 7);
    CHECK(reduction.attempts.size() == 7);
    CHECK(reduction.attempts.back().outcome == geometry::MembershipOutcome::unsupported);
    CHECK(*capability_calls == 7);
    CHECK(*factory_calls == 6);
    CHECK(*solve_calls == 6);
    REQUIRE(runner.records().size() == 7);
    CHECK(std::holds_alternative<registry::LPQueryRejected>(runner.records().back()));
    const auto& rejected = std::get<registry::LPQueryRejected>(runner.records().back());
    CHECK(rejected.request.program.value == "hull-membership-6");
    CHECK(rejected.rejection.provenance.actual->id.value == "test.minimum-membership-capacity");
    CHECK(rejected.rejection.diagnostics[0].field == "test.membership_capacity");
}

TEST_CASE("registered hull queries preserve cancellation deadline and backend resource outcomes") {
    auto capability_calls = std::make_shared<std::size_t>(0);
    auto factory_calls = std::make_shared<std::size_t>(0);
    auto provider = [&] {
        registry::Registry<registry::LPPort> lp_registry;
        REQUIRE_FALSE(lp_registry.add({{{"test.stopped-lp"}, "1"},
            [capability_calls](const LinearProgram&, const registry::Requirements&) -> registry::Capability {
                ++*capability_calls;
                return registry::Offer{};
            },
            [factory_calls](const LinearProgram&) -> std::unique_ptr<LPWorkspace> {
                ++*factory_calls;
                return std::make_unique<LimitedWorkspace>();
            }}));
        auto result = registry::prepare_provider(registry::select_provider(lp_registry,
            registry::Method{{"test.stopped-lp"}, std::nullopt}));
        REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(result));
        return std::get<registry::PreparedProvider<registry::LPPort>>(std::move(result));
    }();

    registry::Registry<registry::HullReducerPort> reducers;
    REQUIRE_FALSE(reducers.add(geometry::make_lp_hull_reducer_registration()));
    const geometry::PointCloud cloud{{"stopped-provider-hull"}, {{0.0}, {1.0}}};
    auto prepared_reducer = registry::prepare_pipeline(registry::select(reducers,
        registry::Method{{"csl.hull.lp-membership"}, std::nullopt}, cloud));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<registry::HullReducerPort>>(prepared_reducer));
    auto reducer_workspaces = std::get<registry::PreparedPipeline<registry::HullReducerPort>>(
        std::move(prepared_reducer)).create();
    auto& reducer = *std::get<0>(reducer_workspaces);

    std::stop_source stop_source;
    stop_source.request_stop();
    ExecutionContext cancelled_context;
    cancelled_context.cancellation = stop_source.get_token();
    registry::RegisteredLPQueryRunner cancelled_runner(provider);
    const auto cancelled = reducer.run_with(cancelled_context, cancelled_runner);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(cancelled));
    CHECK(std::get<geometry::HullReduction>(cancelled).status == geometry::ReductionStatus::incomplete);
    CHECK(std::get<geometry::HullReduction>(cancelled).attempts[0].outcome == geometry::MembershipOutcome::stopped);
    REQUIRE(cancelled_runner.records().size() == 1);
    REQUIRE(std::holds_alternative<registry::LPQueryNotRun>(cancelled_runner.records()[0]));
    CHECK(std::get<registry::LPQueryNotRun>(cancelled_runner.records()[0]).reason ==
        registry::LPQueryNotRunReason::cancelled);

    ExecutionContext deadline_context;
    deadline_context.deadline = std::chrono::steady_clock::now() - std::chrono::milliseconds{1};
    registry::RegisteredLPQueryRunner deadline_runner(provider);
    const auto deadline = reducer.run_with(deadline_context, deadline_runner);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(deadline));
    CHECK(std::get<geometry::HullReduction>(deadline).status == geometry::ReductionStatus::incomplete);
    REQUIRE(deadline_runner.records().size() == 1);
    REQUIRE(std::holds_alternative<registry::LPQueryNotRun>(deadline_runner.records()[0]));
    CHECK(std::get<registry::LPQueryNotRun>(deadline_runner.records()[0]).reason ==
        registry::LPQueryNotRunReason::deadline);
    CHECK(*capability_calls == 0);
    CHECK(*factory_calls == 0);

    registry::RegisteredLPQueryRunner limited_runner(provider);
    const auto limited = reducer.run_with(ExecutionContext{}, limited_runner);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(limited));
    CHECK(std::get<geometry::HullReduction>(limited).status == geometry::ReductionStatus::incomplete);
    CHECK(std::get<geometry::HullReduction>(limited).attempts[0].outcome == geometry::MembershipOutcome::stopped);
    REQUIRE(limited_runner.records().size() == 1);
    REQUIRE(std::holds_alternative<registry::LPQueryStopped>(limited_runner.records()[0]));
    CHECK(std::get<registry::LPQueryStopped>(limited_runner.records()[0]).reason ==
        registry::LPQueryStopReason::resource_limit);
    CHECK(*capability_calls == 1);
    CHECK(*factory_calls == 1);
}

TEST_CASE("hull reducer selects alternative reducers and per-query registered LP providers") {
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

    auto first_lp_provider_result = registry::prepare_provider(registry::select_provider(lp_providers,
        registry::Method{{"test.lp-first"}, std::nullopt}));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(first_lp_provider_result));
    registry::RegisteredLPQueryRunner selected_lp(
        std::get<registry::PreparedProvider<registry::LPPort>>(std::move(first_lp_provider_result)));
    auto outcome = registered_reducer.run_with(ExecutionContext{}, selected_lp);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(outcome));
    CHECK(reducer_calls == 0);
    CHECK(*first_lp_calls == 5);
    REQUIRE(selected_lp.records().size() == 5);
    CHECK(std::get<registry::LPQueryCompleted>(selected_lp.records()[0]).provider.actual->id.value == "test.lp-first");
    const auto& result = std::get<geometry::HullReduction>(outcome);
    CHECK(result.status == geometry::ReductionStatus::complete);
    CHECK(prepared.provenance()[0].actual->id.value == "csl.hull.lp-membership");

    const auto alternative_result = registry::prepare_pipeline(registry::select(reducers,
        registry::Method{{"test.counting-hull"}, std::nullopt}, cloud));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<Port>>(alternative_result));
    auto alternative = std::get<registry::PreparedPipeline<Port>>(alternative_result).create();
    auto& substituted_reducer = *std::get<0>(alternative);

    auto second_lp_provider_result = registry::prepare_provider(registry::select_provider(lp_providers,
        registry::Method{{"test.lp-second"}, std::nullopt}));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(second_lp_provider_result));
    registry::RegisteredLPQueryRunner second_lp(
        std::get<registry::PreparedProvider<registry::LPPort>>(std::move(second_lp_provider_result)));
    auto second = substituted_reducer.run_with(ExecutionContext{}, second_lp);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(second));
    CHECK(reducer_calls == 1);
    CHECK(*second_lp_calls == 5);
    REQUIRE(second_lp.records().size() == 5);
    CHECK(std::get<registry::LPQueryCompleted>(second_lp.records()[0]).provider.actual->id.value == "test.lp-second");
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

TEST_CASE("basis reuse bulk removes only exactly certified nonbasis points and preserves hull") {
    auto lp = highs_workspace();
    REQUIRE(lp != nullptr);
    using Port = registry::HullReducerPort;
    registry::Registry<Port> reducers;
    REQUIRE_FALSE(reducers.add(geometry::make_lp_hull_reducer_registration()));
    REQUIRE_FALSE(reducers.add(geometry::make_basis_reuse_hull_reducer_registration()));
    const geometry::PointCloud cloud{{"basis-bulk-permuted"}, {
        {0,0}, {1,1}, {2,0}, {0,2}, {2,2}, {1,0}, {1,2}, {0,1}, {2,1}, {1,1.5}
    }};
    const auto prepared_result = registry::prepare_pipeline(registry::select(reducers,
        registry::Method{{"csl.hull.phase-one-basis-bulk"}, std::nullopt}, cloud));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<Port>>(prepared_result));
    auto workspaces = std::get<registry::PreparedPipeline<Port>>(prepared_result).create();
    auto& bulk_reducer = *std::get<0>(workspaces);
    const auto result = bulk_reducer.run_with(ExecutionContext{}, *lp);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& bulk = std::get<geometry::HullReduction>(result);
    REQUIRE(bulk.basis_reuse.has_value());
    CHECK(bulk.basis_reuse->basis_solves == 1);
    CHECK(bulk.basis_reuse->bulk_candidates > 0);
    CHECK(bulk.basis_reuse->bulk_removals > 0);
    CHECK_FALSE(bulk.basis_reuse->fell_back_to_lp_baseline);
    CHECK(bulk.basis_reuse->pivots > 0);
    CHECK(bulk.basis_reuse->bulk_removals == bulk.removed.size());
    CHECK(bulk.lp_calls == 0);
    CHECK(bulk.retained.size() < cloud.points.size());
    std::vector<unsigned char> seen(cloud.points.size(), 0);
    for (const auto point : bulk.retained) {
        REQUIRE(point < cloud.points.size());
        CHECK(seen[point] == 0);
        seen[point] = 1;
    }
    for (const auto& certificate : bulk.removed)
    {
        REQUIRE(certificate.removed < cloud.points.size());
        CHECK(seen[certificate.removed] == 0);
        seen[certificate.removed] = 1;
        CHECK(geometry::detail::exact_convex_combination(cloud, certificate.removed, certificate.combination));
        for (const auto& term : certificate.combination) CHECK(term.point < cloud.points.size());
    }
    CHECK(std::all_of(seen.begin(), seen.end(), [](unsigned char present) { return present != 0; }));

    auto baseline_lp = highs_workspace();
    REQUIRE(baseline_lp != nullptr);
    const auto baseline_result = geometry::reduce_hull(cloud, *baseline_lp, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(baseline_result));
    const auto& baseline = std::get<geometry::HullReduction>(baseline_result);
    CHECK(baseline.lp_calls > bulk.lp_calls);
    for (const auto point : bulk.retained)
        CHECK(independent_membership(*baseline_lp, cloud, baseline.retained, point));
    for (const auto point : baseline.retained)
        CHECK(independent_membership(*lp, cloud, bulk.retained, point));

    const geometry::PointCloud degenerate{{"basis-bulk-degenerate"}, {
        {0,0}, {1,0}, {2,0}, {1,0}, {3,0}, {0,0}
    }};
    const auto degenerate_prepared = registry::prepare_pipeline(registry::select(reducers,
        registry::Method{{"csl.hull.phase-one-basis-bulk"}, std::nullopt}, degenerate));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<Port>>(degenerate_prepared));
    auto degenerate_workspaces = std::get<registry::PreparedPipeline<Port>>(degenerate_prepared).create();
    const auto degenerate_result = std::get<0>(degenerate_workspaces)->run_with(ExecutionContext{}, *lp);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(degenerate_result));
    const auto& degenerate_bulk = std::get<geometry::HullReduction>(degenerate_result);
    REQUIRE(degenerate_bulk.basis_reuse.has_value());
    CHECK(degenerate_bulk.basis_reuse->basis_solves == 1);
    for (const auto& certificate : degenerate_bulk.removed)
        CHECK(geometry::detail::exact_convex_combination(
            degenerate, certificate.removed, certificate.combination));
    auto degenerate_baseline_lp = highs_workspace();
    REQUIRE(degenerate_baseline_lp != nullptr);
    const auto degenerate_baseline_result = geometry::reduce_hull(
        degenerate, *degenerate_baseline_lp, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(degenerate_baseline_result));
    const auto& degenerate_baseline = std::get<geometry::HullReduction>(degenerate_baseline_result);
    for (const auto point : degenerate_bulk.retained)
        CHECK(independent_membership(*degenerate_baseline_lp, degenerate,
            degenerate_baseline.retained, point));
    for (const auto point : degenerate_baseline.retained)
        CHECK(independent_membership(*lp, degenerate, degenerate_bulk.retained, point));

    auto generic_provider_result = adapters::lp::make_highs_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(generic_provider_result));
    auto generic_provider = std::get<registry::Registration<registry::LPPort>>(
        std::move(generic_provider_result));
    generic_provider.basis_factory = {}; // simulate a valid solver without optional basis diagnostics
    registry::Registry<Port> fallback_reducers;
    REQUIRE_FALSE(fallback_reducers.add(geometry::make_basis_reuse_hull_reducer_registration(
        std::move(generic_provider))));
    const auto fallback_prepared = registry::prepare_pipeline(registry::select(fallback_reducers,
        registry::Method{{"csl.hull.phase-one-basis-bulk"}, std::nullopt}, cloud));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<Port>>(fallback_prepared));
    auto fallback_workspaces = std::get<registry::PreparedPipeline<Port>>(fallback_prepared).create();
    const auto fallback_result = std::get<0>(fallback_workspaces)->run_with(ExecutionContext{}, *lp);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(fallback_result));
    const auto& fallback_reduction = std::get<geometry::HullReduction>(fallback_result);
    REQUIRE(fallback_reduction.basis_reuse.has_value());
    CHECK(fallback_reduction.basis_reuse->fell_back_to_lp_baseline);
    CHECK(fallback_reduction.lp_calls > 0);
}

TEST_CASE("basis reuse verifies hull when a structural interior point is in the phase-one basis") {
    auto lp = highs_workspace();
    REQUIRE(lp != nullptr);
    using Port = registry::HullReducerPort;
    registry::Registry<Port> reducers;
    REQUIRE_FALSE(reducers.add(geometry::make_basis_reuse_hull_reducer_registration()));
    // The center is deliberately the first structural column. The fixed Bland
    // phase-I provider deterministically returns it as a basic structural point.
    const geometry::PointCloud cloud{{"basis-interior-point"}, {
        {1,1}, {0,0}, {2,0}, {2,2}, {0,2}
    }};
    const auto prepared_result = registry::prepare_pipeline(registry::select(reducers,
        registry::Method{{"csl.hull.phase-one-basis-bulk"}, std::nullopt}, cloud));
    REQUIRE(std::holds_alternative<registry::PreparedPipeline<Port>>(prepared_result));
    auto workspaces = std::get<registry::PreparedPipeline<Port>>(prepared_result).create();
    const auto result = std::get<0>(workspaces)->run_with(ExecutionContext{}, *lp);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& bulk = std::get<geometry::HullReduction>(result);
    REQUIRE(bulk.basis_reuse.has_value());
    CHECK(std::find(bulk.basis_reuse->structural_basis_points.begin(),
        bulk.basis_reuse->structural_basis_points.end(), 0) !=
        bulk.basis_reuse->structural_basis_points.end());
    CHECK(std::find(bulk.retained.begin(), bulk.retained.end(), 0) != bulk.retained.end());

    auto baseline_lp = highs_workspace();
    REQUIRE(baseline_lp != nullptr);
    const auto baseline_result = geometry::reduce_hull(cloud, *baseline_lp, {});
    REQUIRE(std::holds_alternative<geometry::HullReduction>(baseline_result));
    const auto& baseline = std::get<geometry::HullReduction>(baseline_result);
    REQUIRE(baseline.status == geometry::ReductionStatus::complete);
    for (const auto point : bulk.retained)
        CHECK(independent_membership(*baseline_lp, cloud, baseline.retained, point));
    for (const auto point : baseline.retained)
        CHECK(independent_membership(*lp, cloud, bulk.retained, point));
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

TEST_CASE("approximate LP membership cannot authorize a removal within tolerance") {
    ApproximateFirstSupportWorkspace workspace;
    const geometry::PointCloud cloud{{"certificate-chain"}, {{0.0}, {7.5e-9}, {1.5e-8}}};
    ExecutionContext context{};
    context.numerical = {1e-8, 0.0};

    auto result = geometry::reduce_hull(cloud, workspace, context);
    REQUIRE(std::holds_alternative<geometry::HullReduction>(result));
    const auto& reduction = std::get<geometry::HullReduction>(result);
    CHECK(reduction.status == geometry::ReductionStatus::incomplete);
    CHECK(reduction.retained == std::vector<std::size_t>{0, 1, 2});
    CHECK(reduction.removed.empty());
    REQUIRE(!reduction.attempts.empty());
    CHECK(reduction.attempts.front().outcome == geometry::MembershipOutcome::malformed_result);
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
