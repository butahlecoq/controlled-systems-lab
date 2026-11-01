#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <Highs.h>
#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/optimization/finite_action_nominal.hpp>
#include <csl/synthesis/finite_mixed_branch.hpp>
#include <csl/synthesis/strategy_a/nominal_linear_exact_profile.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <stop_token>
#include <string>
#include <thread>

using namespace csl;
using namespace csl::synthesis;

namespace {
numeric::MatrixView matrix(Matrix value) {
    auto result = numeric::snapshot(value);
    REQUIRE(std::holds_alternative<numeric::MatrixView>(result));
    return std::get<numeric::MatrixView>(std::move(result));
}

numeric::VectorView vector(Vector value) {
    auto result = numeric::snapshot_vector(value);
    REQUIRE(std::holds_alternative<numeric::VectorView>(result));
    return std::get<numeric::VectorView>(std::move(result));
}

template<class T, class... Errors>
T take(std::variant<T, Errors...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

SetHandle interval(std::string id, double lo, double hi, std::string label = "x") {
    auto result = sets::make_h({{std::move(id)}, 1, {std::move(label)}},
        {matrix({2, 1, {1, -1}}), vector({hi, -lo}),
         matrix({0, 1, {}}), vector({})});
    REQUIRE(std::holds_alternative<sets::SetData>(result));
    return std::get<sets::SetData>(std::move(result)).as_handle();
}

template<class Port>
registry::PreparedProvider<Port> selected(registry::Registration<Port> registration,
                                           std::string representation) {
    registry::Registry<Port> provider_registry;
    const registry::Method method{registration.identity.id, registration.identity.version};
    REQUIRE_FALSE(provider_registry.add(std::move(registration)).has_value());
    registry::Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, registry::GeometryPort> ||
                  std::is_same_v<Port, registry::ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(registry::prepare_provider(registry::select_provider(
        provider_registry, method, requirements)));
}

struct ExactLinearStrategyFixture {
    registry::Registry<registry::GeometryPort> projections, affines;
    registry::Registry<registry::ConversionPort> conversions;
    registry::Registry<registry::LPPort> lps;
    registry::Registry<registry::ConvexPort> convexes;
    registry::StrategyRegistry strategies;

    ExactLinearStrategyFixture() {
        auto lp = take(adapters::lp::make_highs_registration());
        auto convex = take(adapters::convex::make_highs_registration());
        auto converter = take(adapters::polyhedral::make_qhull_registration(lp));
        auto projection = geometry::polyhedral::make_projection_registration();
        auto affine = geometry::make_affine_sum_registration({
            selected(geometry::make_lp_hull_reducer_registration(), ""),
            selected(lp, "csl.program-result.v1"), selected(converter, "csl.polyhedron.v")});
        const registry::Method pm{projection.identity.id, projection.identity.version};
        const registry::Method am{affine.identity.id, affine.identity.version};
        const registry::Method cm{converter.identity.id, converter.identity.version};
        const registry::Method lm{lp.identity.id, lp.identity.version};
        const registry::Method qm{convex.identity.id, convex.identity.version};
        REQUIRE_FALSE(projections.add(projection).has_value());
        REQUIRE_FALSE(affines.add(affine).has_value());
        REQUIRE_FALSE(conversions.add(converter).has_value());
        REQUIRE_FALSE(lps.add(lp).has_value());
        REQUIRE_FALSE(convexes.add(convex).has_value());
        registry::Requirements h, v, program;
        h.output.representation = {"csl.polyhedron.h"}; h.output.relation = SetRelation::equivalent;
        v.output.representation = {"csl.polyhedron.v"}; v.output.relation = SetRelation::equivalent;
        program.output.representation = {"csl.program-result.v1"};
        auto providers = take(registry::check_providers(
            registry::select_provider(projections, pm, h), registry::select_provider(affines, am, v),
            registry::select_provider(conversions, cm, h), registry::select_provider(lps, lm, program),
            registry::select_provider(convexes, qm, program)));
        REQUIRE_FALSE(strategies.add(synthesis::strategy_a::make_registration(std::move(providers))).has_value());
    }
};

class StopInsideStrategyWorkspace final : public SynthesisWorkspace {
    std::shared_ptr<std::stop_source> cancellation_;
    Termination termination_;
public:
    StopInsideStrategyWorkspace(std::shared_ptr<std::stop_source> cancellation,
        Termination termination)
        : cancellation_(std::move(cancellation)), termination_(termination) {}

    SynthesisResult solve(const problem::ResolvedProblem& problem, const FamilyRequest&,
        const ExecutionContext& context) override {
        StopReason reason = termination_ == Termination::deadline_expired
            ? StopReason::deadline_expired : StopReason::cancelled;
        if (reason == StopReason::cancelled) {
            cancellation_->request_stop();
        } else if (context.deadline) {
            std::this_thread::sleep_until(*context.deadline);
        }
        SynthesisResult result;
        result.termination = termination_;
        result.outcome = {problem.identity(), MathematicalOutcome::undetermined,
            Unestablished{}, {}};
        RequestProvenance provenance{{"finite-mixed-branch-stop-test"}, "strategy",
            {"csl.synthesis.reach-back"}, std::string{"1"},
            ModuleId{"csl.synthesis.reach-back"}, std::string{"1"}};
        result.stop = ScopedOperationStopped{
            OperationStopped{reason, "Synthetic strategy stopped during its branch solve."},
            std::move(provenance), {}};
        return result;
    }
};

registry::StrategyRegistration stopping_strategy(std::shared_ptr<std::stop_source> cancellation,
    Termination termination) {
    registry::StrategyRegistration registration;
    registration.identity = {{"csl.synthesis.reach-back"}, "1"};
    registration.capabilities = [](const registry::StrategyRequest&,
        const registry::Requirements& requirements) -> registry::Capability {
        return registry::Offer{requirements.output};
    };
    registration.complete_family_verifier = {
        {"csl.verifier.strategy-a.nominal-linear-exact"}, "1"};
    registration.planner = [cancellation = std::move(cancellation), termination](
        const registry::StrategyRequest&, const registry::Requirements&)
        -> std::variant<registry::StrategyPlan, registry::Rejection> {
        auto checked = registry::check_pipeline();
        return registry::compose_strategy(std::get<registry::CheckedPipeline<>>(
            std::move(checked)), [cancellation, termination](auto,
            const registry::StrategyRequest&, const registry::Requirements&) {
                return std::make_unique<StopInsideStrategyWorkspace>(cancellation, termination);
            });
    };
    return registration;
}

problem::ResolvedProblem mixed_linear_tie_problem() {
    const auto controls = take(sets::make_h({{"mixed-continuous-interval"}, 1, {"u"}},
        {matrix({2, 1, {1, -1}}), vector({1, 1}), matrix({0, 1, {}}), vector({})}));
    const auto terminal = take(sets::make_h({{"mixed-terminal-halfline"}, 1, {"x1"}},
        {matrix({1, 1, {-1}}), vector({0}), matrix({0, 1, {}}), vector({})}));
    Problem source{{"mixed-linear-tie"},
        std::make_shared<const SystemModel>(SystemModel{{{1, 2, 0}, TimeDomain::discrete,
            LinearStage{{1, 1, {0}}, {1, 2, {1, 1}}, {1, 0, {}}, {0}}}, {}}),
        {0, 1}, KnownInitial{{0}},
        MixedDomain{ContinuousDomain{{controls.as_handle()}}, FiniteDomain{1, {{-1}, {1}, {-1}}}},
        {interval("mixed-initial-state", 0.0, 0.0, "x1"), terminal.as_handle()}, {}, {},
        InformationPattern::nominal_open_loop, LinearTerminal{{1}, 0}};
    auto resolved = problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved));
    return std::get<problem::ResolvedProblem>(std::move(resolved));
}
}

TEST_CASE("mixed branch solve runs registered continuous solvers and retains verified source families") {
    const auto source = mixed_linear_tie_problem();
    ExactLinearStrategyFixture strategy_fixture;
    FiniteMixedBranchSolveRequest request;
    request.strategy.strategy = {"csl.synthesis.reach-back"};
    request.strategy.representation = {"csl.polyhedron.h"};
    request.family.profile = synthesis::strategy_a::nominal_linear_exact_profile;
    request.family.objective = source.identity();
    request.family.target = FamilyTarget::exact_optimal_relation;
    request.family.assurance = Assurance::numerical;
    request.family.representation = {"csl.polyhedron.h"};
    request.resolution = {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}};
    request.branches_per_page = 2;
    request.limits.max_branch_evaluations = 3;
    ExecutionContext context;
    context.numerical = request.family.numerical;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});

    const auto outcome = solve_finite_mixed_branch_portfolio(
        source, strategy_fixture.strategies, request, context);
    REQUIRE(std::holds_alternative<FiniteMixedBranchSolveResult>(outcome));
    const auto& solved = std::get<FiniteMixedBranchSolveResult>(outcome);
    for (const auto& evaluation : solved.portfolio.evaluations)
        if (const auto* failed = std::get_if<FailedFiniteMixedBranch>(&evaluation.branch))
            for (const auto& diagnostic : failed->diagnostics)
                CHECK_MESSAGE(false, diagnostic.field << ": " << diagnostic.explanation);
    CHECK(solved.history_enumeration_complete);
    CHECK(solved.every_branch_solved);
    CHECK(solved.portfolio.complete);
    REQUIRE(solved.portfolio.optimum.has_value());
    CHECK(*solved.portfolio.optimum == doctest::Approx(0.0));
    REQUIRE(solved.portfolio.optimal_evaluation_indices == std::vector<std::size_t>{0, 1, 2});
    CHECK(solved.portfolio.all_selected_relations_present);
    CHECK(solved.retained_relation_rows > 0);
    CHECK(solved.retained_relation_scalars > 0);
    for (std::size_t index = 0; index < solved.portfolio.evaluations.size(); ++index) {
        const auto& evaluation = solved.portfolio.evaluations[index];
        REQUIRE(std::holds_alternative<FiniteMixedBranchProblem>(evaluation.branch));
        CHECK(std::get<FiniteMixedBranchProblem>(evaluation.branch).history ==
            FiniteActionHistory{{index}});
        REQUIRE(evaluation.verified_continuous_family.has_value());
        CHECK(evaluation.verified_continuous_family->registry_verified());
        REQUIRE(evaluation.source_relation.has_value());
        CHECK(evaluation.source_relation->metadata()->set.dimension == 4);
        const auto h = std::get<sets::HRepresentation>(evaluation.source_relation->representation());
        REQUIRE(h.equalities.rows() >= 1);
        const auto discrete_row = h.equalities.rows() - 1;
        CHECK(h.equalities(discrete_row, 3) == 1.0);
        const std::array<double, 3> expected_discrete{-1.0, 1.0, -1.0};
        CHECK(h.equality_values[discrete_row] == expected_discrete[index]);
    }

    auto bounded_request = request;
    bounded_request.branches_per_page = 3;
    bounded_request.limits.max_retained_relation_rows = solved.retained_relation_rows - 1;
    const auto bounded_outcome = solve_finite_mixed_branch_portfolio(
        source, strategy_fixture.strategies, bounded_request, context);
    REQUIRE(std::holds_alternative<FiniteMixedBranchSolveResult>(bounded_outcome));
    const auto& bounded = std::get<FiniteMixedBranchSolveResult>(bounded_outcome);
    REQUIRE(bounded.stop.has_value());
    CHECK(bounded.stop->reason == StopReason::resource_limit);
    CHECK(bounded.portfolio.evaluations.size() == 3);
    CHECK(bounded.history_enumeration_complete);
    CHECK_FALSE(bounded.portfolio.enumeration_complete);
    CHECK_FALSE(bounded.portfolio.complete);
    CHECK_FALSE(bounded.every_branch_solved);
    CHECK(bounded.portfolio.all_selected_relations_present);
    CHECK(bounded.retained_relation_rows <= bounded_request.limits.max_retained_relation_rows);
    CHECK(bounded.retained_relation_scalars <= bounded_request.limits.max_retained_relation_scalars);
    CHECK(std::holds_alternative<FailedFiniteMixedBranch>(bounded.portfolio.evaluations.back().branch));
    const auto& refusal = std::get<FailedFiniteMixedBranch>(bounded.portfolio.evaluations.back().branch);
    REQUIRE_FALSE(refusal.diagnostics.empty());
    CHECK(refusal.diagnostics.front().field == "finite_mixed_branch.resource_limit");

    auto scalar_bounded_request = request;
    scalar_bounded_request.limits.max_retained_relation_scalars = solved.retained_relation_scalars - 1;
    const auto scalar_bounded_outcome = solve_finite_mixed_branch_portfolio(
        source, strategy_fixture.strategies, scalar_bounded_request, context);
    REQUIRE(std::holds_alternative<FiniteMixedBranchSolveResult>(scalar_bounded_outcome));
    const auto& scalar_bounded = std::get<FiniteMixedBranchSolveResult>(scalar_bounded_outcome);
    REQUIRE(scalar_bounded.stop.has_value());
    CHECK(scalar_bounded.stop->reason == StopReason::resource_limit);
    CHECK(scalar_bounded.retained_relation_scalars <=
        scalar_bounded_request.limits.max_retained_relation_scalars);
    CHECK_FALSE(scalar_bounded.portfolio.complete);
}

TEST_CASE("finite mixed branch enumeration agrees with an independent MILP on a tied affine fixture") {
    const auto source = mixed_linear_tie_problem();
    ExactLinearStrategyFixture strategy_fixture;
    FiniteMixedBranchSolveRequest request;
    request.strategy.strategy = {"csl.synthesis.reach-back"};
    request.strategy.representation = {"csl.polyhedron.h"};
    request.family.profile = synthesis::strategy_a::nominal_linear_exact_profile;
    request.family.objective = source.identity();
    request.family.target = FamilyTarget::exact_optimal_relation;
    request.family.assurance = Assurance::numerical;
    request.family.representation = {"csl.polyhedron.h"};
    request.resolution = {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}};
    request.branches_per_page = 3;
    request.limits.max_branch_evaluations = 3;
    ExecutionContext context;
    context.numerical = request.family.numerical;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});

    const auto enumerated = solve_finite_mixed_branch_portfolio(
        source, strategy_fixture.strategies, request, context);
    REQUIRE(std::holds_alternative<FiniteMixedBranchSolveResult>(enumerated));
    const auto& portfolio = std::get<FiniteMixedBranchSolveResult>(enumerated).portfolio;
    REQUIRE(portfolio.complete);
    REQUIRE(portfolio.optimum.has_value());
    CHECK(*portfolio.optimum == doctest::Approx(0.0));
    REQUIRE(portfolio.optimal_evaluation_indices == std::vector<std::size_t>{0, 1, 2});

    // Independent one-step MIP: choose one catalogue entry, one bounded
    // continuous input, enforce the affine transition and terminal halfspace.
    // The action values {-1, +1, -1} are represented by distinct binaries so
    // both equal-valued catalogue branches remain identifiable.
    HighsLp lp;
    lp.num_col_ = 5; // u, z[0..2], terminal state
    lp.num_row_ = 2;
    lp.sense_ = ObjSense::kMinimize;
    lp.col_cost_ = {0.0, 0.0, 0.0, 0.0, 1.0};
    lp.col_lower_ = {-1.0, 0.0, 0.0, 0.0, 0.0};
    lp.col_upper_ = {1.0, 1.0, 1.0, 1.0, kHighsInf};
    lp.row_lower_ = {1.0, 0.0};
    lp.row_upper_ = {1.0, 0.0};
    lp.a_matrix_.format_ = MatrixFormat::kRowwise;
    lp.a_matrix_.start_ = {0, 3, 8};
    lp.a_matrix_.index_ = {1, 2, 3, 0, 1, 2, 3, 4};
    lp.a_matrix_.value_ = {1.0, 1.0, 1.0, -1.0, 1.0, -1.0, 1.0, 1.0};
    lp.a_matrix_.num_row_ = lp.num_row_;
    lp.a_matrix_.num_col_ = lp.num_col_;
    lp.integrality_.assign(5, HighsVarType::kContinuous);
    lp.integrality_[1] = HighsVarType::kInteger;
    lp.integrality_[2] = HighsVarType::kInteger;
    lp.integrality_[3] = HighsVarType::kInteger;

    Highs mip;
    REQUIRE(mip.setOptionValue("output_flag", false) == HighsStatus::kOk);
    REQUIRE(mip.setOptionValue("threads", 1) == HighsStatus::kOk);
    REQUIRE(mip.setOptionValue("mip_rel_gap", 0.0) == HighsStatus::kOk);
    REQUIRE(mip.passModel(lp) == HighsStatus::kOk);
    REQUIRE(mip.run() == HighsStatus::kOk);
    REQUIRE(mip.getModelStatus() == HighsModelStatus::kOptimal);
    const auto& mip_solution = mip.getSolution().col_value;
    REQUIRE(mip_solution.size() == 5);
    const auto& mip_info = mip.getInfo();
    CHECK(mip_info.objective_function_value == doctest::Approx(*portfolio.optimum));
    CHECK(mip_info.mip_dual_bound == doctest::Approx(*portfolio.optimum));
    CHECK(mip_info.mip_gap == doctest::Approx(0.0));
    CHECK(mip_solution[1] + mip_solution[2] + mip_solution[3] == doctest::Approx(1.0));
    for (std::size_t action = 1; action < 4; ++action)
        CHECK(std::min(std::abs(mip_solution[action]),
            std::abs(mip_solution[action] - 1.0)) == doctest::Approx(0.0));

    std::size_t selected_catalogue_index = 0;
    for (std::size_t action = 1; action < 3; ++action)
        if (mip_solution[action + 1] > mip_solution[selected_catalogue_index + 1])
            selected_catalogue_index = action;
    CHECK(mip_solution[selected_catalogue_index + 1] == doctest::Approx(1.0));
    CHECK(std::find(portfolio.optimal_evaluation_indices.begin(),
        portfolio.optimal_evaluation_indices.end(), selected_catalogue_index) !=
        portfolio.optimal_evaluation_indices.end());
    const std::array<double, 3> action_values{-1.0, 1.0, -1.0};
    const double replayed_terminal = mip_solution[0] + action_values[selected_catalogue_index];
    CHECK(replayed_terminal == doctest::Approx(mip_solution[4]));
    CHECK(mip_solution[4] >= -1e-9);
}

TEST_CASE("finite-only affine enumeration agrees with a one-hot MILP and preserves duplicate branches") {
    LinearStage finite_stage;
    finite_stage.A = {1, 1, {0}};
    finite_stage.B = {1, 1, {1}};
    finite_stage.E = {1, 1, {0}};
    finite_stage.offset = {0};
    SystemModel authored;
    authored.dynamics.dimensions = {1, 1, 1};
    authored.dynamics.time_domain = TimeDomain::discrete;
    authored.dynamics.stages = std::move(finite_stage);
    const auto system = take(model::snapshot(authored, Vector{0, 1}));
    const auto safe = interval("finite-only-safe", -2, 2, "x");
    const auto safe_data = take(sets::from_handle(safe));
    csl::optimization::FiniteActionNominalRequest request{{"finite-only-affine"},
        {"finite-only-milp"}, system, {0}, {1, {{-1}, {1}, {-1}}}, {{0}},
        {safe_data, safe_data},
        std::get<csl::optimization::Objective>(
            csl::optimization::snapshot(LinearTerminal{{1}, 0}))};

    const auto enumerated = csl::optimization::finite_action_nominal(request, {3, 3, 100, 10, 0.0});
    REQUIRE(std::holds_alternative<csl::optimization::FiniteActionNominalResult>(enumerated));
    const auto& result = std::get<csl::optimization::FiniteActionNominalResult>(enumerated);
    REQUIRE(result.tracks.size() == 5);
    const auto& exact_track = result.tracks.front();
    REQUIRE(exact_track.representation == csl::optimization::NominalRepresentation::exact_polytope);
    REQUIRE(std::holds_alternative<csl::optimization::NominalTrackSelected>(exact_track.outcome));
    const auto& reference = std::get<csl::optimization::NominalTrackSelected>(exact_track.outcome);
    REQUIRE(reference.coverage == csl::optimization::NominalSearchCoverage::complete);
    CHECK(reference.candidate_score == doctest::Approx(-1.0));
    CHECK(reference.replay.terminal_objective == doctest::Approx(-1.0));
    REQUIRE(reference.attempts.size() == 3);
    std::vector<std::size_t> minimizing_catalogue_indices;
    for(std::size_t index = 0; index < reference.attempts.size(); ++index) {
        const auto* scored = std::get_if<csl::optimization::NominalPlanScored>(
            &reference.attempts[index]);
        REQUIRE(scored != nullptr);
        CHECK(scored->score_kind == csl::optimization::NominalScoreKind::exact_deterministic_objective);
        if(scored->candidate_score == doctest::Approx(-1.0))
            minimizing_catalogue_indices.push_back(scored->action_indices.front());
    }
    CHECK(minimizing_catalogue_indices == std::vector<std::size_t>{0, 2});

    // Independent MILP for x[1] = -z[0] + z[1] - z[2], sum(z) = 1.
    // The identical -1 catalogue entries retain different binary identities.
    HighsLp lp;
    lp.num_col_ = 4; // z[0..2], terminal state
    lp.num_row_ = 2;
    lp.sense_ = ObjSense::kMinimize;
    lp.col_cost_ = {0.0, 0.0, 0.0, 1.0};
    lp.col_lower_ = {0.0, 0.0, 0.0, -2.0};
    lp.col_upper_ = {1.0, 1.0, 1.0, 2.0};
    lp.row_lower_ = {1.0, 0.0};
    lp.row_upper_ = {1.0, 0.0};
    lp.a_matrix_.format_ = MatrixFormat::kRowwise;
    lp.a_matrix_.start_ = {0, 3, 7};
    lp.a_matrix_.index_ = {0, 1, 2, 0, 1, 2, 3};
    lp.a_matrix_.value_ = {1.0, 1.0, 1.0, 1.0, -1.0, 1.0, 1.0};
    lp.a_matrix_.num_row_ = lp.num_row_;
    lp.a_matrix_.num_col_ = lp.num_col_;
    lp.integrality_.assign(4, HighsVarType::kContinuous);
    lp.integrality_[0] = HighsVarType::kInteger;
    lp.integrality_[1] = HighsVarType::kInteger;
    lp.integrality_[2] = HighsVarType::kInteger;

    Highs mip;
    REQUIRE(mip.setOptionValue("output_flag", false) == HighsStatus::kOk);
    REQUIRE(mip.setOptionValue("threads", 1) == HighsStatus::kOk);
    REQUIRE(mip.setOptionValue("mip_rel_gap", 0.0) == HighsStatus::kOk);
    REQUIRE(mip.passModel(lp) == HighsStatus::kOk);
    REQUIRE(mip.run() == HighsStatus::kOk);
    REQUIRE(mip.getModelStatus() == HighsModelStatus::kOptimal);
    const auto& solution = mip.getSolution().col_value;
    REQUIRE(solution.size() == 4);
    const auto& info = mip.getInfo();
    CHECK(info.objective_function_value == doctest::Approx(reference.candidate_score));
    CHECK(info.mip_dual_bound == doctest::Approx(reference.candidate_score));
    CHECK(info.mip_gap == doctest::Approx(0.0));
    CHECK(solution[0] + solution[1] + solution[2] == doctest::Approx(1.0));
    for(std::size_t action = 0; action < 3; ++action)
        CHECK(std::min(std::abs(solution[action]),
            std::abs(solution[action] - 1.0)) == doctest::Approx(0.0));
    std::size_t selected = 0;
    for(std::size_t action = 1; action < 3; ++action)
        if(solution[action] > solution[selected]) selected = action;
    CHECK(std::find(minimizing_catalogue_indices.begin(),
        minimizing_catalogue_indices.end(), selected) != minimizing_catalogue_indices.end());
    const std::array<double, 3> actions{-1.0, 1.0, -1.0};
    CHECK(actions[selected] == doctest::Approx(solution[3]));
}

TEST_CASE("mixed branch solve propagates cancellation and deadline after starting branch work") {
    const auto source = mixed_linear_tie_problem();
    FiniteMixedBranchSolveRequest request;
    request.strategy.strategy = {"csl.synthesis.reach-back"};
    request.strategy.representation = {"csl.polyhedron.h"};
    request.family.profile = synthesis::strategy_a::nominal_linear_exact_profile;
    request.family.objective = source.identity();
    request.family.target = FamilyTarget::exact_optimal_relation;
    request.family.assurance = Assurance::numerical;
    request.family.representation = {"csl.polyhedron.h"};
    request.resolution = {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}};
    request.branches_per_page = 3;
    ExecutionContext context;
    context.numerical = request.family.numerical;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});

    auto cancellation = std::make_shared<std::stop_source>();
    registry::StrategyRegistry cancellation_strategy;
    REQUIRE_FALSE(cancellation_strategy.add(stopping_strategy(
        cancellation, Termination::cancelled)).has_value());
    context.cancellation = cancellation->get_token();
    const auto cancelled_outcome = solve_finite_mixed_branch_portfolio(
        source, cancellation_strategy, request, context);
    REQUIRE(std::holds_alternative<FiniteMixedBranchSolveResult>(cancelled_outcome));
    const auto& cancelled = std::get<FiniteMixedBranchSolveResult>(cancelled_outcome);
    REQUIRE(cancelled.stop.has_value());
    CHECK(cancelled.stop->reason == StopReason::cancelled);
    CHECK(cancelled.history_enumeration_complete);
    CHECK_FALSE(cancelled.portfolio.enumeration_complete);
    CHECK_FALSE(cancelled.portfolio.complete);
    CHECK_FALSE(cancelled.portfolio.evaluations.empty());

    registry::StrategyRegistry deadline_strategy;
    REQUIRE_FALSE(deadline_strategy.add(stopping_strategy(
        std::make_shared<std::stop_source>(), Termination::deadline_expired)).has_value());
    context.cancellation = {};
    context.deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(250);
    const auto deadline_outcome = solve_finite_mixed_branch_portfolio(
        source, deadline_strategy, request, context);
    REQUIRE(std::holds_alternative<FiniteMixedBranchSolveResult>(deadline_outcome));
    const auto& deadline = std::get<FiniteMixedBranchSolveResult>(deadline_outcome);
    REQUIRE(deadline.stop.has_value());
    CHECK(deadline.stop->reason == StopReason::deadline_expired);
    CHECK(deadline.history_enumeration_complete);
    CHECK_FALSE(deadline.portfolio.enumeration_complete);
    CHECK_FALSE(deadline.portfolio.complete);
    CHECK_FALSE(deadline.portfolio.evaluations.empty());
}

TEST_CASE("mixed branch solve stops at the aggregate branch evaluation limit") {
    const auto source = mixed_linear_tie_problem();
    ExactLinearStrategyFixture strategy_fixture;
    FiniteMixedBranchSolveRequest request;
    request.strategy.strategy = {"csl.synthesis.reach-back"};
    request.strategy.representation = {"csl.polyhedron.h"};
    request.family.profile = synthesis::strategy_a::nominal_linear_exact_profile;
    request.family.objective = source.identity();
    request.family.target = FamilyTarget::exact_optimal_relation;
    request.family.assurance = Assurance::numerical;
    request.family.representation = {"csl.polyhedron.h"};
    request.resolution = {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}};
    request.branches_per_page = 3;
    request.limits.max_branch_evaluations = 2;
    ExecutionContext context;
    context.numerical = request.family.numerical;

    const auto outcome = solve_finite_mixed_branch_portfolio(
        source, strategy_fixture.strategies, request, context);
    REQUIRE(std::holds_alternative<FiniteMixedBranchSolveResult>(outcome));
    const auto& result = std::get<FiniteMixedBranchSolveResult>(outcome);
    REQUIRE(result.stop.has_value());
    CHECK(result.stop->reason == StopReason::resource_limit);
    CHECK(result.portfolio.evaluations.size() == 2);
    CHECK_FALSE(result.history_enumeration_complete);
    CHECK_FALSE(result.portfolio.complete);
    CHECK_FALSE(result.every_branch_solved);
    REQUIRE(result.portfolio.optimal_evaluation_indices == std::vector<std::size_t>{0, 1});
    CHECK(result.portfolio.all_selected_relations_present);
}
