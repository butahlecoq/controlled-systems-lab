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

Vector history(double u0, double u1) {
    return {0, u0, u0 + u1, u0, u1}; // canonical [x0,x1,x2,u0,u1]
}

const sets::SetData& recovered(const synthesis::ControlRecoveryOutcome& outcome) {
    REQUIRE(std::holds_alternative<synthesis::JointHistoryRelation>(outcome));
    return std::get<synthesis::JointHistoryRelation>(outcome).relation;
}
}

TEST_CASE("backward recovery retains the two-step terminal fiber and rejects infeasible control histories") {
    const auto result = synthesis::recover_joint_history(integrator(), interval_data("terminal-one", 1, 1));
    const auto& relation = recovered(result);

    // Every returned point is checked against the public meaning of a history:
    // x0=0, x1=u0, x2=u0+u1, 0<=u0,u1<=1, and x2=1.
    for (const Vector point : {history(0, 1), history(0.25, 0.75), history(0.5, 0.5),
                               history(1, 0)})
        CHECK(contains(relation, point));
    CHECK_FALSE(contains(relation, history(1, 1)));
    CHECK_FALSE(contains(relation, {0, 0.5, 1, 0.75, 0.25})); // inconsistent x1
    CHECK_FALSE(contains(relation, {0, 0.5, 1.25, 0.5, 0.5})); // inconsistent x2
    CHECK_FALSE(contains(relation, history(0.25, 0.5))); // misses terminal slice
}

TEST_CASE("recovery handles singular transitions without inverting A") {
    const auto result = synthesis::recover_joint_history(
        singular_integrator(), interval_data("singular-terminal-one", 1, 1));
    const auto& relation = recovered(result);

    // x1=u0 and x2=u1 when A=0. The terminal slice fixes u1=1 while
    // leaving every admissible first-stage control free.
    for (double u0 : {0.0, 0.2, 0.5, 0.8, 1.0})
        CHECK(contains(relation, {0, u0, 1, u0, 1}));
    CHECK_FALSE(contains(relation, {0, 0.5, 0.9, 0.5, 0.9}));
    CHECK_FALSE(contains(relation, {0, 0.5, 1, 0.5, 0.99}));
}

TEST_CASE("recovery preserves the full feasible history when the supplied terminal slice is the full minimizer relation") {
    // The helper receives no objective. This interval is already the entire
    // terminal minimizer relation for a constant terminal criterion.
    const auto result = synthesis::recover_joint_history(integrator(), interval_data("terminal-full", 0, 2));
    const auto& relation = recovered(result);

    for (double u0 : {0.0, 0.2, 0.5, 1.0})
        for (double u1 : {0.0, 0.3, 0.7, 1.0})
            CHECK(contains(relation, history(u0, u1)));
    CHECK_FALSE(contains(relation, {0, 0.5, 1, -0.1, 1.1}));
}

TEST_CASE("recovered histories respect intermediate state constraints") {
    const auto result = synthesis::recover_joint_history(
        integrator(0.5), interval_data("terminal-full-with-stage-bound", 0, 2));
    const auto& relation = recovered(result);

    CHECK(contains(relation, history(0.5, 0)));
    CHECK(contains(relation, history(0.5, 1)));
    CHECK_FALSE(contains(relation, history(0.5001, 0)));
    CHECK_FALSE(contains(relation, {0, 0.75, 0.75, 0.5, 0.25})); // x1 violates bound
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
