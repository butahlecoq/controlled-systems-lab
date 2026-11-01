#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/synthesis/finite_mixed_branch.hpp>
#include <csl/synthesis/strategy_a/nominal_linear_exact_profile.hpp>

#include <chrono>
#include <limits>
#include <string>

using namespace csl;
using namespace csl::synthesis;

namespace {
Problem mixed_problem() {
    return {{"mixed-source"},
        std::make_shared<const SystemModel>(SystemModel{{{1, 3, 0}, TimeDomain::discrete,
            std::vector<LinearStage>{
                {{1, 1, {1}}, {1, 3, {1, 10, 100}}, {1, 0, {}}, {2}},
                {{1, 1, {2}}, {1, 3, {4, 10, 100}}, {1, 0, {}}, {3}}}}, {}}),
        {0, 1, 2}, KnownInitial{{0}},
        MixedDomain{ContinuousDomain{{UniversalSet{1}, UniversalSet{1}}},
                    FiniteDomain{2, {{3, 4}, {3, 4}, {0, -1}}}},
        {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}}, {}, {},
        InformationPattern::nominal_open_loop, LinearTerminal{{1}, 0}};
}

problem::ResolvedProblem resolved_mixed_problem() {
    auto result = problem::resolve(mixed_problem(),
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(result));
    return std::get<problem::ResolvedProblem>(std::move(result));
}

template<class T, class... Errors>
T take(std::variant<T, Errors...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

numeric::MatrixView matrix(Matrix value);
numeric::VectorView vector(Vector value);
SetHandle interval(std::string id, double lo, double hi, std::string label = "x") {
    auto result = sets::make_h({{std::move(id)}, 1, {std::move(label)}},
        {matrix({2, 1, {1, -1}}), vector({hi, -lo}),
         matrix({0, 1, {}}), vector({})});
    REQUIRE(std::holds_alternative<sets::SetData>(result));
    return std::get<sets::SetData>(std::move(result)).as_handle();
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
        InformationPattern::nominal_open_loop,
        LinearTerminal{{1}, 0}};
    auto resolved = problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved));
    return std::get<problem::ResolvedProblem>(std::move(resolved));
}

FiniteMixedBranchProblem branch(const problem::ResolvedProblem& problem,
                                std::vector<std::size_t> indices) {
    auto result = prepare_finite_mixed_branch(problem, FiniteActionHistory{std::move(indices)});
    REQUIRE(std::holds_alternative<FiniteMixedBranchProblem>(result));
    return std::get<FiniteMixedBranchProblem>(std::move(result));
}

FiniteMixedBranchCursor cursor(const problem::ResolvedProblem& problem) {
    auto result = FiniteMixedBranchCursor::prepare(problem);
    REQUIRE(std::holds_alternative<FiniteMixedBranchCursor>(result));
    return std::get<FiniteMixedBranchCursor>(std::move(result));
}

sets::SetData relation(std::string id, std::size_t dimension) {
    auto result = sets::make_universal({SetId{std::move(id)}, dimension, {}});
    REQUIRE(std::holds_alternative<sets::SetData>(result));
    return std::get<sets::SetData>(std::move(result));
}

FiniteActionHistory history_of(const FiniteMixedBranchEntry& entry) {
    if (const auto* prepared = std::get_if<FiniteMixedBranchProblem>(&entry))
        return prepared->history;
    return std::get<FailedFiniteMixedBranch>(entry).history;
}

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

Problem one_step_tied_mixed_problem() {
    return {{"mixed-tied-families"},
        std::make_shared<const SystemModel>(SystemModel{{{1, 2, 0}, TimeDomain::discrete,
            std::vector<LinearStage>{
                {{1, 1, {0}}, {1, 2, {0, 1}}, {1, 0, {}}, {0}}}}, {}}),
        {0, 1}, KnownInitial{{0}},
        MixedDomain{ContinuousDomain{{UniversalSet{1}}},
                    FiniteDomain{1, {{-1}, {0}, {1}, {0}}}},
        {UniversalSet{1}, UniversalSet{1}}, {}, {},
        InformationPattern::nominal_open_loop,
        QuadraticTerminal{{1, 1, {2}}, {0}, 0}};
}

sets::SetData analytic_branch_family(std::string id, double terminal_state) {
    auto result = sets::make_h({SetId{std::move(id)}, 3, {}},
        {matrix({0, 3, {}}), vector({}),
         matrix({2, 3, {1, 0, 0, 0, 1, 0}}), vector({0, terminal_state})});
    REQUIRE(std::holds_alternative<sets::SetData>(result));
    return std::get<sets::SetData>(std::move(result));
}
}

TEST_CASE("mixed branch substitutes discrete values and retains the source coordinate map") {
    const auto source = resolved_mixed_problem();
    const auto result = branch(source, {0, 2});

    CHECK(result.history == FiniteActionHistory{{0, 2}});
    CHECK(result.coordinates.source == JointCoordinates{{1, 3, 0}, 2});
    CHECK(result.coordinates.continuous_subproblem == JointCoordinates{{1, 1, 0}, 2});
    CHECK(result.coordinates.discrete_controls == std::vector<Vector>{{3, 4}, {0, -1}});
    CHECK(result.problem.id.value.ends_with("/finite-branch/0/2"));
    CHECK(std::holds_alternative<ContinuousDomain>(result.problem.controls));
    const auto branch_resolved = problem::resolve(result.problem,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    CHECK(std::holds_alternative<problem::ResolvedProblem>(branch_resolved));

    const auto& stages = std::get<std::vector<LinearStage>>(result.problem.model->dynamics.stages);
    REQUIRE(stages.size() == 2);
    CHECK(stages[0].B.rows == 1);
    CHECK(stages[0].B.cols == 1);
    CHECK(stages[0].B.values == Vector{1});
    CHECK(stages[0].offset == Vector{432});
    CHECK(stages[1].B.values == Vector{4});
    CHECK(stages[1].offset == Vector{-97});
    CHECK(result.problem.model->dynamics.dimensions.control == 1);

    const auto source_description = source.description();
    CHECK(source_description->model->dynamics.dimensions.control == 3);
    REQUIRE(std::holds_alternative<MixedDomain>(source_description->controls));
    const auto& source_mixed = std::get<MixedDomain>(source_description->controls);
    CHECK(source_mixed.discrete.catalogue == std::vector<Vector>{{3, 4}, {3, 4}, {0, -1}});
}

TEST_CASE("mixed branch keeps catalogue indices distinct for duplicate action values") {
    const auto source = resolved_mixed_problem();
    const auto left = branch(source, {0, 0});
    const auto right = branch(source, {1, 0});

    CHECK(left.history != right.history);
    CHECK(left.coordinates.discrete_controls == right.coordinates.discrete_controls);
    CHECK(left.problem.id != right.problem.id);
}

TEST_CASE("branch relation lift restores source control coordinates and fixes discrete values") {
    const auto source = resolved_mixed_problem();
    const auto mixed_branch = branch(source, {0, 2});
    const auto relation = sets::make_h({"continuous-branch", 5, {}},
        {matrix({1, 5, {0, 0, 1, 0, 0}}), vector({1}),
         matrix({0, 5, {}}), vector({})});
    REQUIRE(std::holds_alternative<sets::SetData>(relation));

    const auto lifted = lift_finite_mixed_branch_relation(
        mixed_branch, std::get<sets::SetData>(relation));
    REQUIRE(std::holds_alternative<sets::SetData>(lifted));
    const auto& data = std::get<sets::SetData>(lifted);
    CHECK(data.metadata()->set.dimension == 9);
    const auto h = std::get<sets::HRepresentation>(data.representation());
    CHECK(h.inequalities.rows() == 1);
    CHECK(h.inequalities(0, 2) == 1);
    CHECK(h.upper_bounds[0] == 1);
    REQUIRE(h.equalities.rows() == 4);
    CHECK(h.equalities(0, 4) == 1);
    CHECK(h.equalities(1, 5) == 1);
    CHECK(h.equalities(2, 7) == 1);
    CHECK(h.equalities(3, 8) == 1);
    CHECK(h.equality_values[0] == 3);
    CHECK(h.equality_values[1] == 4);
    CHECK(h.equality_values[2] == 0);
    CHECK(h.equality_values[3] == -1);
}

TEST_CASE("mixed branch rejects malformed histories and unsupported information profiles") {
    const auto source = resolved_mixed_problem();
    auto short_history = prepare_finite_mixed_branch(source, FiniteActionHistory{{0}});
    REQUIRE(std::holds_alternative<Diagnostics>(short_history));
    CHECK(std::get<Diagnostics>(short_history).front().code == DiagnosticCode::invalid_input);

    auto bad_index = prepare_finite_mixed_branch(source, FiniteActionHistory{{0, 3}});
    REQUIRE(std::holds_alternative<Diagnostics>(bad_index));
    CHECK(std::get<Diagnostics>(bad_index).front().code == DiagnosticCode::invalid_input);

    auto authored = *source.description();
    authored.information = InformationPattern::feedback;
    const auto feedback_result = problem::resolve(authored,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(feedback_result));
    const auto& feedback = std::get<problem::ResolvedProblem>(feedback_result);
    auto unsupported = prepare_finite_mixed_branch(feedback, FiniteActionHistory{{0, 2}});
    REQUIRE(std::holds_alternative<Diagnostics>(unsupported));
    CHECK(std::get<Diagnostics>(unsupported).front().code == DiagnosticCode::unsupported);
    auto unsupported_cursor = FiniteMixedBranchCursor::prepare(feedback);
    REQUIRE(std::holds_alternative<Diagnostics>(unsupported_cursor));
    CHECK(std::get<Diagnostics>(unsupported_cursor).front().field ==
        "finite_mixed_branch.profile");
}

TEST_CASE("mixed branch rejects non-finite offsets created by finite inputs") {
    auto authored = mixed_problem();
    auto model = *authored.model;
    auto& stages = std::get<std::vector<LinearStage>>(model.dynamics.stages);
    stages[0].B.values[1] = std::numeric_limits<double>::max();
    authored.model = std::make_shared<const SystemModel>(std::move(model));
    const auto resolved = problem::resolve(authored,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved));

    const auto result = prepare_finite_mixed_branch(
        std::get<problem::ResolvedProblem>(resolved), FiniteActionHistory{{0, 0}});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().code == DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(result).front().field == "finite_mixed_branch.affine_offset");
}

TEST_CASE("mixed branch cursor streams bounded index histories and preserves duplicate identity") {
    auto branches = cursor(resolved_mixed_problem());

    const auto empty = branches.take_prefix(0);
    CHECK(empty.entries.empty());
    CHECK_FALSE(empty.complete);

    const auto first = branches.take_prefix(4);
    REQUIRE(first.entries.size() == 4);
    CHECK(first.entries[0].index() == 0);
    CHECK(history_of(first.entries[0]) == FiniteActionHistory{{0, 0}});
    CHECK(history_of(first.entries[1]) == FiniteActionHistory{{0, 1}});
    CHECK(history_of(first.entries[2]) == FiniteActionHistory{{0, 2}});
    CHECK(history_of(first.entries[3]) == FiniteActionHistory{{1, 0}});
    CHECK_FALSE(first.complete);
    const auto& duplicate_zero = std::get<FiniteMixedBranchProblem>(first.entries[0]);
    const auto& duplicate_one = std::get<FiniteMixedBranchProblem>(first.entries[3]);
    CHECK(duplicate_zero.coordinates.discrete_controls[0] == Vector{3, 4});
    CHECK(duplicate_one.coordinates.discrete_controls[0] == Vector{3, 4});
    CHECK(duplicate_zero.problem.id != duplicate_one.problem.id);

    const auto second = branches.take_prefix(4);
    REQUIRE(second.entries.size() == 4);
    CHECK(history_of(second.entries.front()) == FiniteActionHistory{{1, 1}});
    CHECK(history_of(second.entries.back()) == FiniteActionHistory{{2, 1}});
    CHECK_FALSE(second.complete);

    const auto last = branches.take_prefix(4);
    REQUIRE(last.entries.size() == 1);
    CHECK(history_of(last.entries.front()) == FiniteActionHistory{{2, 2}});
    CHECK(last.complete);

    const auto terminal = branches.take_prefix(1);
    CHECK(terminal.entries.empty());
    CHECK(terminal.complete);
}

TEST_CASE("mixed branch cursor retains refusals and continues preparing later histories") {
    auto authored = mixed_problem();
    auto controls = std::get<MixedDomain>(authored.controls);
    controls.discrete.catalogue = {{0, -1}, {3, 4}, {0, -1}};
    authored.controls = std::move(controls);
    auto model = *authored.model;
    auto& stages = std::get<std::vector<LinearStage>>(model.dynamics.stages);
    stages[1].B.values[1] = std::numeric_limits<double>::max();
    authored.model = std::make_shared<const SystemModel>(std::move(model));
    const auto resolved = problem::resolve(authored,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved));

    auto branches = cursor(std::get<problem::ResolvedProblem>(resolved));
    const auto page = branches.take_prefix(3);
    REQUIRE(page.entries.size() == 3);
    CHECK(std::holds_alternative<FiniteMixedBranchProblem>(page.entries[0]));
    REQUIRE(std::holds_alternative<FailedFiniteMixedBranch>(page.entries[1]));
    const auto& refusal = std::get<FailedFiniteMixedBranch>(page.entries[1]);
    CHECK(refusal.history == FiniteActionHistory{{0, 1}});
    REQUIRE(refusal.diagnostics.size() == 1);
    CHECK(refusal.diagnostics.front().field == "finite_mixed_branch.affine_offset");
    CHECK(std::holds_alternative<FiniteMixedBranchProblem>(page.entries[2]));
    CHECK(history_of(page.entries[2]) == FiniteActionHistory{{0, 2}});
    CHECK_FALSE(page.complete);
}

TEST_CASE("zero-horizon mixed branch cursor emits one empty history") {
    auto authored = mixed_problem();
    authored.times = {0};
    auto model = *authored.model;
    auto& dynamics = model.dynamics;
    dynamics.stages = std::vector<LinearStage>{};
    authored.model = std::make_shared<const SystemModel>(std::move(model));
    auto controls = std::get<MixedDomain>(authored.controls);
    controls.continuous.stages.clear();
    authored.controls = std::move(controls);
    authored.states.resize(1);
    const auto resolved = problem::resolve(authored,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved));

    auto branches = cursor(std::get<problem::ResolvedProblem>(resolved));
    const auto page = branches.take_prefix(1);
    REQUIRE(page.entries.size() == 1);
    REQUIRE(std::holds_alternative<FiniteMixedBranchProblem>(page.entries.front()));
    CHECK(history_of(page.entries.front()) == FiniteActionHistory{{}});
    CHECK(page.complete);
    CHECK(branches.take_prefix(1).entries.empty());
}

TEST_CASE("mixed branch portfolio preserves every globally minimal history tie") {
    const auto source = resolved_mixed_problem();
    std::vector<FiniteMixedBranchEvaluation> evaluations{
        {branch(source, {0, 0}), 2.0},
        {branch(source, {0, 1}), 1.0},
        {branch(source, {1, 0}), 1.0 + 5e-13},
        {branch(source, {2, 2}), 3.0}};

    const auto selected = select_finite_mixed_branch_portfolio(
        std::move(evaluations), true, 1e-12);
    REQUIRE(std::holds_alternative<FiniteMixedBranchPortfolio>(selected));
    const auto& portfolio = std::get<FiniteMixedBranchPortfolio>(selected);
    CHECK(portfolio.complete);
    REQUIRE(portfolio.optimum.has_value());
    CHECK(*portfolio.optimum == doctest::Approx(1.0));
    REQUIRE(portfolio.optimal_evaluation_indices == std::vector<std::size_t>{1, 2});
    CHECK(std::get<FiniteMixedBranchProblem>(portfolio.evaluations[1].branch).history ==
        FiniteActionHistory{{0, 1}});
    CHECK(std::get<FiniteMixedBranchProblem>(portfolio.evaluations[2].branch).history ==
        FiniteActionHistory{{1, 0}});
}

TEST_CASE("mixed branch portfolio keeps each tied continuous relation attached to its history") {
    const auto source = resolved_mixed_problem();
    std::vector<FiniteMixedBranchEvaluation> evaluations{
        {branch(source, {0, 1}), 1.0, relation("continuous-family-a", 5)},
        {branch(source, {1, 0}), 1.0, relation("continuous-family-b", 5)}};

    const auto selected = select_finite_mixed_branch_portfolio(std::move(evaluations), true, 0.0);
    REQUIRE(std::holds_alternative<FiniteMixedBranchPortfolio>(selected));
    const auto& portfolio = std::get<FiniteMixedBranchPortfolio>(selected);
    CHECK(portfolio.complete);
    CHECK(portfolio.all_selected_relations_present);
    REQUIRE(portfolio.optimal_evaluation_indices == std::vector<std::size_t>{0, 1});
    REQUIRE(portfolio.evaluations[0].continuous_relation.has_value());
    REQUIRE(portfolio.evaluations[1].continuous_relation.has_value());
    CHECK(portfolio.evaluations[0].continuous_relation->metadata()->id.value == "continuous-family-a");
    CHECK(portfolio.evaluations[1].continuous_relation->metadata()->id.value == "continuous-family-b");
    CHECK(std::get<FiniteMixedBranchProblem>(portfolio.evaluations[0].branch).history ==
        FiniteActionHistory{{0, 1}});
    CHECK(std::get<FiniteMixedBranchProblem>(portfolio.evaluations[1].branch).history ==
        FiniteActionHistory{{1, 0}});
}

TEST_CASE("mixed branch portfolio reports missing continuous relations without dropping ties") {
    const auto source = resolved_mixed_problem();
    std::vector<FiniteMixedBranchEvaluation> evaluations{
        {branch(source, {0, 1}), 1.0, relation("continuous-family-a", 5)},
        {branch(source, {1, 0}), 1.0, std::nullopt}};

    const auto selected = select_finite_mixed_branch_portfolio(std::move(evaluations), true, 0.0);
    REQUIRE(std::holds_alternative<FiniteMixedBranchPortfolio>(selected));
    const auto& portfolio = std::get<FiniteMixedBranchPortfolio>(selected);
    CHECK_FALSE(portfolio.all_selected_relations_present);
    CHECK(portfolio.optimal_evaluation_indices == std::vector<std::size_t>{0, 1});
}

TEST_CASE("mixed branch portfolio rejects a relation in the wrong branch coordinates") {
    const auto source = resolved_mixed_problem();
    auto result = select_finite_mixed_branch_portfolio(
        std::vector<FiniteMixedBranchEvaluation>{
            {branch(source, {0, 1}), 1.0, relation("wrong-dimension", 4)}}, true, 0.0);
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field == "finite_mixed_branch.relation");
}

TEST_CASE("independent one-step oracle retains every tied catalogue branch and its continuous family") {
    const auto resolved = problem::resolve(one_step_tied_mixed_problem(),
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved));
    const auto& source = std::get<problem::ResolvedProblem>(resolved);
    const auto description = source.description();
    const auto& source_mixed = std::get<MixedDomain>(description->controls);

    auto branches = cursor(source);
    const auto page = branches.take_prefix(8);
    REQUIRE(page.entries.size() == 4);
    CHECK(page.complete);

    std::vector<FiniteMixedBranchEvaluation> evaluations;
    std::vector<std::size_t> oracle_minimizers;
    double oracle_minimum = std::numeric_limits<double>::infinity();
    for (std::size_t row = 0; row < page.entries.size(); ++row) {
        REQUIRE(std::holds_alternative<FiniteMixedBranchProblem>(page.entries[row]));
        const auto& prepared = std::get<FiniteMixedBranchProblem>(page.entries[row]);
        const FiniteActionHistory expected_history{{row}};
        CHECK(prepared.history == expected_history);

        // Independent scalar oracle: x1 = d because A = B_cont = 0, B_disc = 1;
        // the terminal cost is x1^2, and every continuous control is therefore optimal.
        const double discrete = source_mixed.discrete.catalogue[row][0];
        const double terminal_state = discrete;
        const double objective = terminal_state * terminal_state;
        if (objective < oracle_minimum) {
            oracle_minimum = objective;
            oracle_minimizers.clear();
        }
        if (objective == oracle_minimum) oracle_minimizers.push_back(row);

        evaluations.push_back({prepared, objective,
            analytic_branch_family("oracle-history-" + std::to_string(row), terminal_state)});
    }

    const auto selected = select_finite_mixed_branch_portfolio(
        std::move(evaluations), page.complete, 0.0);
    REQUIRE(std::holds_alternative<FiniteMixedBranchPortfolio>(selected));
    const auto& portfolio = std::get<FiniteMixedBranchPortfolio>(selected);
    CHECK(portfolio.complete);
    REQUIRE(portfolio.optimum.has_value());
    CHECK(*portfolio.optimum == oracle_minimum);
    CHECK(portfolio.optimal_evaluation_indices == oracle_minimizers);
    CHECK(portfolio.optimal_evaluation_indices == std::vector<std::size_t>{1, 3});
    CHECK(portfolio.all_selected_relations_present);

    for (const auto index : oracle_minimizers) {
        const auto& evaluation = portfolio.evaluations[index];
        const auto& selected_branch = std::get<FiniteMixedBranchProblem>(evaluation.branch);
        CHECK(selected_branch.history == FiniteActionHistory{{index}});
        REQUIRE(evaluation.continuous_relation.has_value());
        CHECK(evaluation.continuous_relation->metadata()->set.dimension == 3);

        const auto lifted = lift_finite_mixed_branch_relation(
            selected_branch, *evaluation.continuous_relation);
        REQUIRE(std::holds_alternative<sets::SetData>(lifted));
        const auto& source_relation = std::get<sets::SetData>(lifted);
        CHECK(source_relation.metadata()->set.dimension == 4);
        const auto h = std::get<sets::HRepresentation>(source_relation.representation());
        REQUIRE(h.inequalities.rows() == 0);
        REQUIRE(h.equalities.rows() == 3);
        CHECK(h.equalities(0, 0) == 1);
        CHECK(h.equalities(1, 1) == 1);
        CHECK(h.equalities(2, 3) == 1);
        CHECK(h.equalities(0, 2) == 0);
        CHECK(h.equalities(1, 2) == 0);
        CHECK(h.equalities(2, 2) == 0);
        CHECK(h.equality_values[0] == 0);
        CHECK(h.equality_values[1] == 0);
        CHECK(h.equality_values[2] == 0);
    }
}

TEST_CASE("mixed branch solve retains strategy refusals and does not claim a global optimum") {
    const auto source = mixed_linear_tie_problem();
    registry::StrategyRegistry no_strategies;
    FiniteMixedBranchSolveRequest request;
    request.strategy.strategy = {"missing.strategy"};
    request.strategy.representation = {"csl.polyhedron.h"};
    request.family.profile = strategy_a::nominal_linear_exact_profile;
    request.family.objective = source.identity();
    request.family.target = FamilyTarget::exact_optimal_relation;
    request.family.assurance = Assurance::numerical;
    request.family.representation = {"csl.polyhedron.h"};
    request.resolution = {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}};
    ExecutionContext context;
    context.numerical = request.family.numerical;

    const auto outcome = solve_finite_mixed_branch_portfolio(source, no_strategies, request, context);
    REQUIRE(std::holds_alternative<FiniteMixedBranchSolveResult>(outcome));
    const auto& result = std::get<FiniteMixedBranchSolveResult>(outcome);
    CHECK(result.history_enumeration_complete);
    CHECK_FALSE(result.every_branch_solved);
    CHECK(result.portfolio.enumeration_complete);
    CHECK_FALSE(result.portfolio.complete);
    CHECK_FALSE(result.portfolio.optimum.has_value());
    REQUIRE(result.portfolio.evaluations.size() == 3);
    for (const auto& evaluation : result.portfolio.evaluations)
        CHECK(std::holds_alternative<FailedFiniteMixedBranch>(evaluation.branch));
}

TEST_CASE("mixed branch solve reports pre-cancellation without claiming completeness") {
    const auto source = mixed_linear_tie_problem();
    registry::StrategyRegistry no_strategies;
    FiniteMixedBranchSolveRequest request;
    request.strategy.representation = {"csl.polyhedron.h"};
    request.family.profile = strategy_a::nominal_linear_exact_profile;
    request.family.objective = source.identity();
    request.family.target = FamilyTarget::exact_optimal_relation;
    request.family.assurance = Assurance::numerical;
    request.family.representation = {"csl.polyhedron.h"};
    request.resolution = {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}};
    request.branches_per_page = 2;
    std::stop_source cancellation;
    cancellation.request_stop();
    ExecutionContext context;
    context.numerical = request.family.numerical;
    context.cancellation = cancellation.get_token();

    const auto outcome = solve_finite_mixed_branch_portfolio(source, no_strategies, request, context);
    REQUIRE(std::holds_alternative<FiniteMixedBranchSolveResult>(outcome));
    const auto& result = std::get<FiniteMixedBranchSolveResult>(outcome);
    REQUIRE(result.stop.has_value());
    CHECK(result.stop->reason == StopReason::cancelled);
    CHECK_FALSE(result.history_enumeration_complete);
    CHECK_FALSE(result.portfolio.complete);
    CHECK(result.portfolio.evaluations.empty());
    CHECK_FALSE(result.portfolio.optimum.has_value());
}

TEST_CASE("mixed branch solve reports an expired deadline without claiming completeness") {
    const auto source = mixed_linear_tie_problem();
    registry::StrategyRegistry no_strategies;
    FiniteMixedBranchSolveRequest request;
    request.strategy.representation = {"csl.polyhedron.h"};
    request.family.profile = strategy_a::nominal_linear_exact_profile;
    request.family.objective = source.identity();
    request.family.target = FamilyTarget::exact_optimal_relation;
    request.family.assurance = Assurance::numerical;
    request.family.representation = {"csl.polyhedron.h"};
    request.resolution = {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}};
    request.branches_per_page = 2;
    ExecutionContext context;
    context.numerical = request.family.numerical;
    context.deadline = std::chrono::steady_clock::time_point::min();

    const auto outcome = solve_finite_mixed_branch_portfolio(source, no_strategies, request, context);
    REQUIRE(std::holds_alternative<FiniteMixedBranchSolveResult>(outcome));
    const auto& result = std::get<FiniteMixedBranchSolveResult>(outcome);
    REQUIRE(result.stop.has_value());
    CHECK(result.stop->reason == StopReason::deadline_expired);
    CHECK_FALSE(result.history_enumeration_complete);
    CHECK_FALSE(result.portfolio.complete);
    CHECK(result.portfolio.evaluations.empty());
}

TEST_CASE("mixed branch portfolio keeps preparation refusals and incomplete enumeration explicit") {
    const auto source = resolved_mixed_problem();
    auto refused = FailedFiniteMixedBranch{
        FiniteActionHistory{{2, 1}},
        Diagnostics{{DiagnosticCode::unsupported, "finite_mixed_branch.profile", "test refusal"}}};
    std::vector<FiniteMixedBranchEvaluation> evaluations{
        {branch(source, {0, 0}), 4.0}, {std::move(refused), std::nullopt},
        {branch(source, {0, 2}), 2.0}};

    const auto selected = select_finite_mixed_branch_portfolio(
        std::move(evaluations), false, 0.0);
    REQUIRE(std::holds_alternative<FiniteMixedBranchPortfolio>(selected));
    const auto& portfolio = std::get<FiniteMixedBranchPortfolio>(selected);
    CHECK_FALSE(portfolio.complete);
    REQUIRE(portfolio.optimum.has_value());
    CHECK(*portfolio.optimum == doctest::Approx(2.0));
    CHECK(portfolio.optimal_evaluation_indices == std::vector<std::size_t>{2});
    REQUIRE(std::holds_alternative<FailedFiniteMixedBranch>(portfolio.evaluations[1].branch));
    CHECK_FALSE(portfolio.evaluations[1].objective.has_value());
}

TEST_CASE("complete history enumeration with a refused branch is not a complete optimum") {
    const auto source = resolved_mixed_problem();
    auto refused = FailedFiniteMixedBranch{FiniteActionHistory{{2, 1}},
        Diagnostics{{DiagnosticCode::unsupported, "branch", "solver unavailable"}}};
    const auto outcome = select_finite_mixed_branch_portfolio({
        {branch(source, {0, 0}), 4.0}, {std::move(refused), std::nullopt},
        {branch(source, {0, 2}), 2.0}}, true, 0.0);
    REQUIRE(std::holds_alternative<FiniteMixedBranchPortfolio>(outcome));
    const auto& portfolio = std::get<FiniteMixedBranchPortfolio>(outcome);
    CHECK(portfolio.enumeration_complete);
    CHECK_FALSE(portfolio.complete);
    CHECK(portfolio.optimum == 2.0);
}

TEST_CASE("mixed branch portfolio rejects missing, non-finite and invalid objective inputs") {
    const auto source = resolved_mixed_problem();
    const auto prepared = branch(source, {0, 0});

    auto missing = select_finite_mixed_branch_portfolio(
        std::vector<FiniteMixedBranchEvaluation>{{prepared, std::nullopt}}, true, 0.0);
    REQUIRE(std::holds_alternative<Diagnostics>(missing));
    CHECK(std::get<Diagnostics>(missing).front().code == DiagnosticCode::invalid_input);

    auto nonfinite = select_finite_mixed_branch_portfolio(
        std::vector<FiniteMixedBranchEvaluation>{{prepared, std::numeric_limits<double>::quiet_NaN()}},
        true, 0.0);
    REQUIRE(std::holds_alternative<Diagnostics>(nonfinite));
    CHECK(std::get<Diagnostics>(nonfinite).front().code == DiagnosticCode::invalid_input);

    auto tolerance = select_finite_mixed_branch_portfolio({}, true, -1.0);
    REQUIRE(std::holds_alternative<Diagnostics>(tolerance));
    CHECK(std::get<Diagnostics>(tolerance).front().code == DiagnosticCode::invalid_input);
}
