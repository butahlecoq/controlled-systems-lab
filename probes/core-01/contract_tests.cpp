#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/contracts.hpp>
#include <type_traits>
#include <limits>

using namespace csl;
static_assert(!std::is_copy_constructible_v<LPWorkspace>);
static_assert(!std::is_copy_constructible_v<SynthesisWorkspace>);
static_assert(!std::is_convertible_v<WitnessBatch, OptimalFamily>);
static_assert(!std::is_same_v<ProblemId, ModuleId>);

namespace {
Problem problem() {
    LinearStage singular{{1,1,{0}}, {1,1,{1}}, {1,0,{}}, {0}};
    return {{"test/singular"}, std::make_shared<const SystemModel>(SystemModel{
        {{1,1,0}, TimeDomain::discrete, singular}, {}}),
        {0,1}, KnownInitial{{0}}, ContinuousDomain{{UniversalSet{1}}},
        {UniversalSet{1}, UniversalSet{1}}, {}, {}, InformationPattern::nominal_open_loop,
        LinearTerminal{{1},0}};
}
struct RelationFixture : JointRelationPayload {};
OptimalFamily family() {
    ClaimEvidence unknown{{"test/singular"}, Unestablished{}};
    return {{"test/singular"}, {{ {1,1,0}, 1}, {"fixture/joint"}, std::make_shared<const RelationFixture>()},
        FamilyTarget::exact_optimal_relation, {unknown, unknown, unknown}};
}
}

TEST_CASE("T-M03: singular dynamics remain representable; inverse-only pipeline is unsupported") {
    auto p = problem();
    CHECK(check_model_shape(p.model->dynamics, 1).empty());
    CHECK(check_nominal_profile(p, false, Assurance::numerical).empty());
    auto rejected = check_nominal_profile(p, true, Assurance::numerical);
    REQUIRE(rejected.size() == 1);
    CHECK(rejected[0].code == DiagnosticCode::unsupported);
    CHECK(rejected[0].field == "dynamics.inverse");
}
TEST_CASE("T-M03: future profiles do not masquerade as infeasibility") {
    auto p = problem();
    SUBCASE("temporal") { p.temporal = TemporalConstraints{{1,3,{0,1},{0},{1}},{{0,1}}}; }
    SUBCASE("finite") { p.controls = FiniteDomain{{{0},{1}}}; }
    SUBCASE("mixed") { p.controls = MixedDomain{{{UniversalSet{1}}}, {{{0},{1}}}}; }
    SUBCASE("initial uncertainty") { p.initial = InitialSet{UniversalSet{1}}; }
    SUBCASE("feedback") { p.information = InformationPattern::feedback; }
    SUBCASE("external") { p.external = UniversalSet{1}; }
    SUBCASE("continuous") { auto model = *p.model; model.dynamics.time_domain = TimeDomain::continuous; p.model = std::make_shared<const SystemModel>(model); }
    auto rejected = check_nominal_profile(p, false, Assurance::numerical);
    REQUIRE(rejected.size() == 1);
    CHECK(rejected[0].code == DiagnosticCode::unsupported);
}
TEST_CASE("empty temporal collection is the uncoupled profile") {
    auto p = problem();
    p.temporal = TemporalConstraints{{0,3,{0},{},{}},{}};
    CHECK(check_nominal_profile(p, false, Assurance::numerical).empty());
}
TEST_CASE("model shape checks reject malformed input but allow absent ports and constant coefficients") {
    auto d = problem().model->dynamics;
    CHECK(check_model_shape(d, 3).empty());
    SUBCASE("coefficient count") { d.stages = std::vector<LinearStage>{}; }
    SUBCASE("storage") { std::get<LinearStage>(d.stages).A.values = {}; }
    SUBCASE("shape") { std::get<LinearStage>(d.stages).B.cols = 2; }
    auto rejected = check_model_shape(d, 3);
    REQUIRE_FALSE(rejected.empty());
    CHECK(rejected[0].code == DiagnosticCode::invalid_input);
}
TEST_CASE("T-V02: numerical success and certificate references cannot satisfy validated request") {
    auto f = family();
    f.evidence.feasibility.support = NumericalCheck{1e-8,1e-8,0,{"fixture/verifier"}};
    CHECK(check_family_evidence(f, {"test/singular"}, Assurance::numerical).empty());
    SUBCASE("numerical") {}
    SUBCASE("unverified certificate") { f.evidence.completeness.support = CertificateReference{"cert.json","future/verifier"}; }
    auto rejected = check_family_evidence(f, {"test/singular"}, Assurance::validated);
    REQUIRE_FALSE(rejected.empty());
    CHECK(rejected[0].code == DiagnosticCode::unsupported);
}
TEST_CASE("T-V02: evidence is bound to the expected problem for every claim") {
    auto f = family();
    SUBCASE("family") { f.problem = {"other"}; }
    SUBCASE("feasibility") { f.evidence.feasibility.problem = {"other"}; }
    SUBCASE("optimality") { f.evidence.optimality.problem = {"other"}; }
    SUBCASE("completeness") { f.evidence.completeness.problem = {"other"}; }
    auto rejected = check_family_evidence(f, {"test/singular"}, Assurance::numerical);
    REQUIRE_FALSE(rejected.empty());
    CHECK(rejected[0].code == DiagnosticCode::evidence_mismatch);
}
TEST_CASE("T-V02: partial or relaxed relations cannot claim full optimal-family coverage") {
    auto f = family();
    SUBCASE("partial") { f.target = FamilyTarget::partial_relation; }
    SUBCASE("relaxed") { f.target = FamilyTarget::candidate_relaxation; }
    CHECK(check_family_evidence(f, {"test/singular"}, Assurance::numerical).empty());
    f.evidence.completeness.support = SymbolicArgument{"argument","assumptions"};
    auto rejected = check_family_evidence(f, {"test/singular"}, Assurance::numerical);
    REQUIRE(rejected.size() == 1);
    CHECK(rejected[0].code == DiagnosticCode::invalid_claim);
}
TEST_CASE("T-V02: a numerical check alone cannot establish completeness") {
    auto f = family();
    f.evidence.completeness.support = NumericalCheck{1e-8,1e-8,0,{"backend/success"}};
    auto rejected = check_family_evidence(f, {"test/singular"}, Assurance::numerical);
    REQUIRE(rejected.size() == 1);
    CHECK(rejected[0].code == DiagnosticCode::invalid_claim);
}
TEST_CASE("T-M03: nonpolyhedral stage domains need another pipeline") {
    auto p = problem();
    SetHandle curved{{1,{"curved"},SetProperty::yes,SetProperty::no,SetProperty::yes}, {}};
    SUBCASE("control") { p.controls = ContinuousDomain{{curved}}; }
    SUBCASE("state") { p.states[1] = curved; }
    auto rejected = check_nominal_profile(p, false, Assurance::numerical);
    REQUIRE(rejected.size() == 1);
    CHECK(rejected[0].code == DiagnosticCode::unsupported);
}
TEST_CASE("one resource policy refuses oversubscription including overflow and zero") {
    CHECK(check_resources({4,2,2,{}}).empty());
    for (auto r : {ResourcePolicy{4,3,2,{}}, {0,1,1,{}}, {4,0,1,{}}, {4,1,0,{}}, {4,std::numeric_limits<std::size_t>::max(),2,{}}}) {
        auto rejected = check_resources(r);
        REQUIRE(rejected.size() == 1);
        CHECK(rejected[0].code == DiagnosticCode::invalid_input);
    }
}
