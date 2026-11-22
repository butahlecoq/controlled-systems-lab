#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/synthesis/control_recovery.hpp>
#include <cmath>

using namespace csl;

namespace {
template<class T, class... E>
T take(std::variant<T, E...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

numeric::MatrixView matrix(Matrix value) {
    return take(numeric::snapshot(value));
}

numeric::VectorView vector(Vector value) {
    return take(numeric::snapshot_vector(value));
}

SetHandle interval(std::string id, double lower, double upper, std::string label) {
    return take(sets::make_h({{std::move(id)}, 1, {std::move(label)}},
        {matrix({2, 1, {1, -1}}), vector({upper, -lower}),
         matrix({0, 1, {}}), vector({})})).as_handle();
}

sets::SetData interval_data(std::string id, double lower, double upper) {
    return take(sets::from_handle(interval(std::move(id), lower, upper, "x")));
}

problem::ResolvedProblem integrator(std::optional<double> stage_one_upper = std::nullopt,
                                    bool finite_controls = false) {
    const auto model = std::make_shared<const SystemModel>(SystemModel{
        {{1, 1, 0}, TimeDomain::discrete,
         LinearStage{{1, 1, {1}}, {1, 1, {1}}, {1, 0, {}}, {0}}}, {}});
    ControlDomain controls = ContinuousDomain{{
        interval("u0", 0, 1, "u0"), interval("u1", 0, 1, "u1")}};
    if (finite_controls) controls = FiniteDomain{1, {{0}, {1}}};
    std::vector<AdmissibleSet> states{
        Singleton{{0}}, UniversalSet{1}, UniversalSet{1}};
    if (stage_one_upper) states[1] = interval("x1", 0, *stage_one_upper, "x1");
    Problem source{{"control-recovery-integrator"}, model, {0, 1, 2},
        KnownInitial{{0}}, std::move(controls), std::move(states), {}, {},
        InformationPattern::nominal_open_loop, LinearTerminal{{0}, 0}};
    return take(problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
}

problem::ResolvedProblem singular_integrator() {
    const auto model = std::make_shared<const SystemModel>(SystemModel{
        {{1, 1, 0}, TimeDomain::discrete,
         std::vector<LinearStage>{
             {{1, 1, {0}}, {1, 1, {1}}, {1, 0, {}}, {0}},
             {{1, 1, {0}}, {1, 1, {1}}, {1, 0, {}}, {0}}}}, {}});
    Problem source{{"control-recovery-singular-integrator"}, model, {0, 1, 2},
        KnownInitial{{0}}, ContinuousDomain{{
            interval("singular-u0", 0, 1, "u0"), interval("singular-u1", 0, 1, "u1")}},
        {Singleton{{0}}, UniversalSet{1}, UniversalSet{1}}, {}, {},
        InformationPattern::nominal_open_loop, LinearTerminal{{0}, 0}};
    return take(problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
}

problem::ResolvedProblem zero_state_integrator() {
    const auto model = std::make_shared<const SystemModel>(SystemModel{
        {{0, 1, 0}, TimeDomain::discrete,
         LinearStage{{0, 0, {}}, {0, 1, {}}, {0, 0, {}}, {}}}, {}});
    Problem source{{"control-recovery-zero-state"}, model, {0, 1, 2},
        KnownInitial{{}}, ContinuousDomain{{
            interval("zero-state-u0", -1, 0, "u0"),
            interval("zero-state-u1", 1, 2, "u1")}},
        {UniversalSet{0}, UniversalSet{0}, UniversalSet{0}}, {}, {},
        InformationPattern::nominal_open_loop, LinearTerminal{{}, 0}};
    return take(problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
}

problem::ResolvedProblem two_state_two_stage_system() {
    const auto model = std::make_shared<const SystemModel>(SystemModel{
        {{2, 1, 0}, TimeDomain::discrete,
         std::vector<LinearStage>{
             {{2, 2, {1, 0, 0, 1}}, {2, 1, {1, 0}}, {2, 0, {}}, {0, 0}},
             {{2, 2, {1, 0, 0, 1}}, {2, 1, {0, 1}}, {2, 0, {}}, {0, 0}}}}, {}});
    Problem source{{"control-recovery-stage-map"}, model, {0, 1, 2},
        KnownInitial{{1, -1}}, ContinuousDomain{{
            interval("stage-map-u0", -1, 1, "u0"),
            interval("stage-map-u1", -1, 1, "u1")}},
        {UniversalSet{2}, UniversalSet{2}, UniversalSet{2}}, {}, {},
        InformationPattern::nominal_open_loop, LinearTerminal{{0, 0}, 0}};
    return take(problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
}

bool contains(const sets::SetData& set, const Vector& point) {
    const auto representation = set.representation();
    if (const auto* h = std::get_if<sets::HRepresentation>(&representation)) {
        if (point.size() != h->inequalities.cols()) return false;
        for (std::size_t row = 0; row < h->inequalities.rows(); ++row) {
            double lhs = 0;
            for (std::size_t col = 0; col < point.size(); ++col)
                lhs += h->inequalities(row, col) * point[col];
            if (lhs > h->upper_bounds[row] + 1e-8) return false;
        }
        for (std::size_t row = 0; row < h->equalities.rows(); ++row) {
            double lhs = 0;
            for (std::size_t col = 0; col < point.size(); ++col)
                lhs += h->equalities(row, col) * point[col];
            if (std::abs(lhs - h->equality_values[row]) > 1e-8) return false;
        }
        return true;
    }
    if (const auto* singleton = std::get_if<sets::SingletonRepresentation>(&representation)) {
        if (point.size() != singleton->point.size()) return false;
        for (std::size_t i = 0; i < point.size(); ++i)
            if (std::abs(point[i] - singleton->point[i]) > 1e-8) return false;
        return true;
    }
    if (std::holds_alternative<sets::UniversalRepresentation>(representation)) return true;
    return std::holds_alternative<sets::EmptyRepresentation>(representation) && false;
}

bool sparse_h(const sets::SetData& set) {
    const auto representation = set.representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    return h && std::holds_alternative<numeric::CsrInput>(h->inequalities.descriptor()) &&
        std::holds_alternative<numeric::CsrInput>(h->equalities.descriptor());
}

Vector two_step_integrator_history(double u0, double u1) {
    return {0, u0, u0 + u1, u0, u1};
}

const sets::SetData& recovered(const synthesis::ControlRecoveryOutcome& outcome) {
    REQUIRE(std::holds_alternative<synthesis::JointHistoryRelation>(outcome));
    return std::get<synthesis::JointHistoryRelation>(outcome).relation;
}
}

TEST_CASE("recovery accepts sampled two-step terminal histories and rejects inconsistent samples") {
    const auto result = synthesis::recover_joint_history(integrator(), interval_data("terminal-one", 1, 1));
    const auto& relation = recovered(result);
    CHECK(sparse_h(relation));

    for (const Vector point : {two_step_integrator_history(0, 1),
                               two_step_integrator_history(0.25, 0.75),
                               two_step_integrator_history(0.5, 0.5),
                               two_step_integrator_history(1, 0)})
        CHECK(contains(relation, point));
    CHECK_FALSE(contains(relation, two_step_integrator_history(1, 1)));
    const Vector inconsistent_first_stage{0, 0.5, 1, 0.75, 0.25};
    const Vector inconsistent_second_stage{0, 0.5, 1, 0.5, 0.6};
    CHECK_FALSE(contains(relation, inconsistent_first_stage));
    CHECK_FALSE(contains(relation, inconsistent_second_stage));
    CHECK_FALSE(contains(relation, two_step_integrator_history(0.25, 0.5)));
}

TEST_CASE("recovery stores empty terminal contradictions as sparse zero rows") {
    const auto empty_terminal = take(sets::make_empty({{"empty-terminal"}, 1, {"x"}}));
    const auto relation = recovered(synthesis::recover_joint_history(integrator(), empty_terminal));
    CHECK(sparse_h(relation));
    CHECK_FALSE(contains(relation, two_step_integrator_history(0.5, 0.5)));

    const auto representation = std::get<sets::HRepresentation>(relation.representation());
    const auto rows = std::get<numeric::CsrInput>(representation.inequalities.descriptor());
    bool has_empty_contradiction = false;
    for (std::size_t row = 0; row < rows.rows; ++row)
        if (rows.row_offsets[row] == rows.row_offsets[row + 1] &&
            representation.upper_bounds[row] == -1.0)
            has_empty_contradiction = true;
    CHECK(has_empty_contradiction);
}

TEST_CASE("recovery embeds CSR terminal rows at the terminal-state coordinates") {
    const auto terminal = take(sets::make_h({{"csr-terminal-one"}, 1, {"x"}},
        {take(numeric::snapshot(SparseMatrix{2, 1, {0, 1, 2}, {0, 0}, {1, -1}})),
         vector({1, -1}), take(numeric::snapshot(SparseMatrix{0, 1, {0}, {}, {}})), vector({})}));
    const auto relation = recovered(synthesis::recover_joint_history(integrator(), terminal));

    CHECK(sparse_h(relation));
    CHECK(contains(relation, two_step_integrator_history(0.25, 0.75)));
    CHECK_FALSE(contains(relation, two_step_integrator_history(0.25, 0.5)));
}

TEST_CASE("recovery handles singular transitions without inverting A") {
    const auto result = synthesis::recover_joint_history(
        singular_integrator(), interval_data("singular-terminal-one", 1, 1));
    const auto& relation = recovered(result);
    CHECK(sparse_h(relation));

    for (double u0 : {0.0, 0.2, 0.5, 0.8, 1.0})
        CHECK(contains(relation, {0, u0, 1, u0, 1}));
    CHECK_FALSE(contains(relation, {0, 0.5, 0.9, 0.5, 0.9}));
    CHECK_FALSE(contains(relation, {0, 0.5, 1, 0.5, 0.99}));
}

TEST_CASE("recovery admits sampled histories across a caller-supplied terminal interval") {
    const auto result = synthesis::recover_joint_history(integrator(), interval_data("terminal-full", 0, 2));
    const auto& relation = recovered(result);
    CHECK(sparse_h(relation));

    for (double u0 : {0.0, 0.2, 0.5, 1.0})
        for (double u1 : {0.0, 0.3, 0.7, 1.0})
            CHECK(contains(relation, two_step_integrator_history(u0, u1)));
    CHECK_FALSE(contains(relation, {0, 0.5, 1, -0.1, 1.1}));
}

TEST_CASE("recovered histories respect intermediate state constraints") {
    const auto result = synthesis::recover_joint_history(
        integrator(0.5), interval_data("terminal-full-with-stage-bound", 0, 2));
    const auto& relation = recovered(result);

    CHECK(contains(relation, two_step_integrator_history(0.5, 0)));
    CHECK(contains(relation, two_step_integrator_history(0.5, 1)));
    CHECK_FALSE(contains(relation, two_step_integrator_history(0.5001, 0)));
    CHECK_FALSE(contains(relation, two_step_integrator_history(0.75, 0)));
}

TEST_CASE("recovery rejects finite control catalogues when only continuous controls are supported") {
    const auto result = synthesis::recover_joint_history(
        integrator(std::nullopt, true), interval_data("terminal-finite-controls", 1, 1));
    CHECK(std::holds_alternative<Diagnostics>(result));
    REQUIRE_FALSE(std::get<Diagnostics>(result).empty());
}

TEST_CASE("joint history identity binds the supplied terminal relation identity") {
    const auto problem = integrator();
    const auto first = synthesis::recover_joint_history(problem,
        interval_data("terminal-first", 1, 1));
    const auto second = synthesis::recover_joint_history(problem,
        interval_data("terminal-second", 1, 1));
    REQUIRE(std::holds_alternative<synthesis::JointHistoryRelation>(first));
    REQUIRE(std::holds_alternative<synthesis::JointHistoryRelation>(second));
    CHECK(std::get<synthesis::JointHistoryRelation>(first).relation.metadata()->id !=
        std::get<synthesis::JointHistoryRelation>(second).relation.metadata()->id);
}

TEST_CASE("zero-dimensional states preserve every staged control coordinate in canonical history order") {
    const auto source = zero_state_integrator();
    const auto terminal = take(sets::make_universal({{"zero-state-terminal"}, 0, {}}));
    const auto outcome = synthesis::recover_joint_history(source, terminal);
    const auto& relation = recovered(outcome);

    CHECK(std::get<synthesis::JointHistoryRelation>(outcome).coordinates ==
        (JointCoordinates{{0, 1, 0}, 2}));
    CHECK(relation.metadata()->set.dimension == 2);
    CHECK(contains(relation, {-0.25, 1.75}));
    CHECK(contains(relation, {-1, 2}));
    CHECK_FALSE(contains(relation, {1.75, -0.25}));
    CHECK_FALSE(contains(relation, {0.01, 1.5}));
    CHECK_FALSE(contains(relation, {0.25}));
}

TEST_CASE("stage-labelled recovery preserves the coordinate map and complete multivariable history") {
    const auto source = two_state_two_stage_system();
    const auto terminal = take(sets::make_singleton({{"stage-map-terminal"}, 2, {}},
        vector({1.5, -1.25})));
    const auto outcome = synthesis::recover_joint_history(source, terminal);
    const auto& joint = std::get<synthesis::JointHistoryRelation>(outcome);

    CHECK(joint.coordinates == (JointCoordinates{{2, 1, 0}, 2}));
    CHECK(joint.coordinates == source.constraints().coordinates());
    const Vector expected_history{1, -1, 1.5, -1, 1.5, -1.25, 0.5, -0.25};
    const Vector swapped_control_order{1, -1, 1.5, -1, 1.5, -1.25, -0.25, 0.5};
    CHECK(contains(joint.relation, expected_history));
    CHECK_FALSE(contains(joint.relation, swapped_control_order));
    CHECK_FALSE(contains(joint.relation, {1, -1, 1.5, -1, 1.5, -1.0, 0.5, -0.25}));
}

TEST_CASE("lifted projections exclude future rows and retain the full terminal contradiction") {
    const auto terminal = take(sets::make_empty({{"empty-terminal-lift"}, 1, {"x"}}));
    const auto model = integrator(0.5);
    const auto lifted = take<synthesis::LiftedHistoryProjections>(
        synthesis::recover_lifted_history_projections(model, terminal));
    REQUIRE(lifted.prefixes.size() == 3);
    const auto h = std::get<sets::HRepresentation>(lifted.history.relation.representation());
    CHECK_FALSE(contains(lifted.history.relation, two_step_integrator_history(0.25, 0.25)));

    const auto prefix_contains = [&](std::size_t stage, const Vector& values) {
        const auto& prefix = lifted.prefixes.at(stage);
        const auto check_rows = [&](const numeric::MatrixView& rows, const numeric::VectorView& b,
                                    const auto& ranges, bool equality) {
            for (const auto& range : ranges)
                for (std::size_t row = range.begin; row < range.end; ++row) {
                    double lhs = 0;
                    for (std::size_t column = 0; column < values.size(); ++column)
                        lhs += rows(row, column) * values[column];
                    if (equality ? lhs != b[row] : lhs > b[row])
                        return false;
                }
            return true;
        };
        return check_rows(h.inequalities, h.upper_bounds, prefix.inequality_rows, false) &&
               check_rows(h.equalities, h.equality_values, prefix.equality_rows, true);
    };
    using synthesis::HistoryIndexRange;
    CHECK(lifted.prefixes[0].state_columns == HistoryIndexRange{0, 1});
    CHECK(lifted.prefixes[1].state_columns == HistoryIndexRange{1, 2});
    CHECK(lifted.prefixes[2].state_columns == HistoryIndexRange{2, 3});
    CHECK(prefix_contains(0, {0, 7, 9, 7, -5}));
    CHECK_FALSE(prefix_contains(0, {1, 7, 9, 7, -5}));
    CHECK(prefix_contains(1, {0, 0.25, 9, 0.25, -5}));
    CHECK_FALSE(prefix_contains(1, {0, 0.75, 9, 0.75, -5}));
    CHECK_FALSE(prefix_contains(1, {0, 0.25, 9, 0.5, -5}));
    CHECK(prefix_contains(2, two_step_integrator_history(0.25, 0.25)));
    CHECK_FALSE(prefix_contains(2, two_step_integrator_history(0.25, 2)));
    CHECK_FALSE(prefix_contains(2, {0, 0.25, 0.75, 0.25, 0.25}));
}
