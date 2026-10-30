#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/synthesis/finite_mixed_branch.hpp>

#include <limits>

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

FiniteMixedBranchProblem branch(const problem::ResolvedProblem& problem,
                                std::vector<std::size_t> indices) {
    auto result = prepare_finite_mixed_branch(problem, FiniteActionHistory{std::move(indices)});
    REQUIRE(std::holds_alternative<FiniteMixedBranchProblem>(result));
    return std::get<FiniteMixedBranchProblem>(std::move(result));
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
