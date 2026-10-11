#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/contracts.hpp>
#include <type_traits>
#include <limits>
#include <utility>

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
    SUBCASE("finite") { p.controls = FiniteDomain{1,{{0},{1}}}; }
    SUBCASE("mixed") { p.controls = MixedDomain{{{UniversalSet{0}}}, {1,{{0},{1}}}}; }
    SUBCASE("initial uncertainty") { p.initial = InitialSet{UniversalSet{1},SetQuantifier::universal}; }
    SUBCASE("feedback") { p.information = InformationPattern::feedback; }
    SUBCASE("external") { p.external = ExogenousExternalInput{{UniversalSet{0}},SetQuantifier::universal}; }
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
    SetHandle curved{{1,{"curved"},SetProperty::yes,SetProperty::no,SetProperty::yes}, {}, {"curved/set"}};
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
TEST_CASE("outcome evidence binds infeasibility to a program without objective bounds") {
    const ProgramIdentity expected{{"problem/a"},{"lp/feasibility"}};
    ProgramResult result{Termination::completed,
        {expected,MathematicalOutcome::infeasible,Unestablished{},{}}, {},{},"native status: infeasible"};
    CHECK(check_outcome_evidence(result.outcome,expected,Assurance::numerical).empty());
    CHECK_FALSE(result.objective.lower.has_value());
    CHECK_FALSE(result.objective.upper.has_value());
    SUBCASE("different problem") { result.outcome.subject.problem = {"problem/b"}; }
    SUBCASE("different program of same problem") { result.outcome.subject.program = {"lp/other"}; }
    auto rejected = check_outcome_evidence(result.outcome,expected,Assurance::numerical);
    REQUIRE(rejected.size() == 1);
    CHECK(rejected[0].code == DiagnosticCode::evidence_mismatch);
}
TEST_CASE("unsupported, numerical infeasibility and symbolic infeasibility have distinct support") {
    const ProgramIdentity expected{{"problem/a"},{"lp/feasibility"}};
    const ProgramOutcome unsupported = Unsupported{{{DiagnosticCode::unsupported,"program","unsupported profile"}}};
    CHECK(std::holds_alternative<Unsupported>(unsupported));
    ProgramResult numerical{Termination::completed,
        {expected,MathematicalOutcome::infeasible,NumericalCheck{1e-8,1e-8,0,{"farkas/residual"}},
            {"linear constraints as authored; double arithmetic"}}, {},{},"native infeasible"};
    CHECK(check_outcome_evidence(numerical.outcome,expected,Assurance::numerical).empty());
    ProgramResult symbolic{Termination::completed,
        {expected,MathematicalOutcome::infeasible,SymbolicArgument{"contradiction: x<=0 and x>=1","exact supplied inequalities"},
            {"exact supplied inequalities"}}, {},{},""};
    CHECK(check_outcome_evidence(symbolic.outcome,expected,Assurance::numerical).empty());
    for (const auto* claim : {&numerical.outcome,&symbolic.outcome}) {
        auto rejected = check_outcome_evidence(*claim,expected,Assurance::validated);
        REQUIRE(rejected.size() == 1);
        CHECK(rejected[0].code == DiagnosticCode::unsupported);
    }
}
TEST_CASE("synthesis unboundedness carries scoped support even without a family") {
    SynthesisResult result{Termination::completed,
        {{"problem/a"},MathematicalOutcome::unbounded,CertificateReference{"ray.json","future/ray-verifier"},
            {"nominal open-loop; original objective"}}, {},{}, {},{}};
    CHECK(check_outcome_evidence(result.outcome,ProblemId{"problem/a"},Assurance::numerical).empty());
    CHECK_FALSE(result.family.has_value());
    CHECK_FALSE(result.objective.lower.has_value());
    auto mismatch = check_outcome_evidence(result.outcome,ProblemId{"problem/b"},Assurance::numerical);
    REQUIRE(mismatch.size() == 1);
    CHECK(mismatch[0].code == DiagnosticCode::evidence_mismatch);
    auto unverified = check_outcome_evidence(result.outcome,ProblemId{"problem/a"},Assurance::validated);
    REQUIRE(unverified.size() == 1);
    CHECK(unverified[0].code == DiagnosticCode::unsupported);
}
namespace {
struct SetFixture : SetPayload {};
SetHandle input_set(std::string id = "set/a", std::size_t dimension = 2) {
    return {{dimension,{"fixture/set"},SetProperty::yes,SetProperty::yes,SetProperty::yes},
        std::make_shared<const SetFixture>(),{std::move(id)}};
}
OperationRequest affine_request() {
    return {{{"problem/a"},{"image/first"},{"ideal/image-first"}},{"geometry/affine"},
        AffineImage{input_set(),{1,2,{1,0}},{2}}, SetRelation::equivalent,Assurance::numerical};
}
GeometryEvidence image_evidence() {
    return {{{{"problem/a"},{"image/first"},{"ideal/image-first"}},{{"set/a"}}},
        GeometryClaimScope::set_relation,SymbolicArgument{"affine image formula","exact operands"},
        {"exact operands"},{}};
}
}
TEST_CASE("geometry: two neutral affine maps retain separate mathematical requests") {
    auto first = affine_request();
    auto second = affine_request();
    second.identity = {{"problem/a"},{"image/second"},{"ideal/image-second"}};
    second.operation = AffineImage{input_set(),{2,2,{0,1,1,0}},{3,4}};
    CHECK(check_operation_shape(first).empty());
    CHECK(check_operation_shape(second).empty());
    auto wrong = check_geometry_evidence(image_evidence(),second);
    REQUIRE(wrong.size() == 1);
    CHECK(wrong[0].code == DiagnosticCode::evidence_mismatch);
    std::get<AffineImage>(second.operation).offset = {3};
    auto malformed = check_operation_shape(second);
    REQUIRE(malformed.size() == 1);
    CHECK(malformed[0].code == DiagnosticCode::invalid_input);
}
TEST_CASE("geometry: projection coordinates travel through the port and are range checked") {
    auto request = affine_request();
    request.operation = Projection{input_set(),{1,0}};
    CHECK(check_operation_shape(request).empty());
    request.operation = Projection{input_set(),{0}};
    CHECK(check_operation_shape(request).empty());
    request.operation = Projection{input_set(),{2}};
    auto rejected = check_operation_shape(request);
    REQUIRE(rejected.size() == 1);
    CHECK(rejected[0].code == DiagnosticCode::invalid_input);
}
TEST_CASE("geometry: evidence rejects a different request, ideal output, input or claim scope") {
    const auto request = affine_request();
    auto evidence = image_evidence();
    CHECK(check_geometry_evidence(evidence,request).empty());
    SUBCASE("problem") { evidence.reference.identity.problem = {"problem/b"}; }
    SUBCASE("request") { evidence.reference.identity.request = {"another/request"}; }
    SUBCASE("ideal output") { evidence.reference.identity.ideal_output = {"another/ideal-set"}; }
    SUBCASE("input") { evidence.reference.inputs = {{"set/b"}}; }
    SUBCASE("scope") { evidence.scope = GeometryClaimScope::support_value; }
    auto rejected = check_geometry_evidence(evidence,request);
    REQUIRE(rejected.size() == 1);
    CHECK(rejected[0].code == DiagnosticCode::evidence_mismatch);
}
TEST_CASE("geometry: conversion and approximation claims bind to their ideal input set") {
    const auto id = affine_request().identity;
    ConversionRequest conversion{id,input_set(),{"new/representation"},Assurance::numerical};
    ApproximationRequest approximation{id,input_set(),{"small/representation"},SetRelation::outer,8,Assurance::numerical};
    auto evidence = image_evidence();
    evidence.error_bound = GeometryErrorBound{{"euclidean/hausdorff"},0.1,"state units"};
    CHECK(check_geometry_evidence(evidence,conversion).empty());
    CHECK(check_geometry_evidence(evidence,approximation).empty());
    conversion.input = input_set("set/b");
    approximation.input = input_set("set/b");
    REQUIRE(check_geometry_evidence(evidence,conversion).size() == 1);
    REQUIRE(check_geometry_evidence(evidence,approximation).size() == 1);
    conversion.input = input_set();
    approximation.input = input_set();
    conversion.assurance = Assurance::validated;
    approximation.assurance = Assurance::validated;
    const auto conversion_rejection = check_geometry_evidence(evidence,conversion);
    const auto approximation_rejection = check_geometry_evidence(evidence,approximation);
    REQUIRE(conversion_rejection.size() == 1);
    REQUIRE(approximation_rejection.size() == 1);
    CHECK(conversion_rejection[0].code == DiagnosticCode::unsupported);
    CHECK(approximation_rejection[0].code == DiagnosticCode::unsupported);
}
TEST_CASE("geometry: support and containment have query-specific results and claim scopes") {
    auto request = affine_request();
    request.operation = SupportQuery{input_set(),{1,0}};
    SupportResult support{3.0,{},image_evidence()};
    support.evidence.scope = GeometryClaimScope::support_value;
    CHECK(check_operation_shape(request).empty());
    CHECK(check_geometry_evidence(support.evidence,request).empty());
    request.operation = SupportQuery{input_set(),{1}};
    REQUIRE(check_operation_shape(request).size() == 1);
    request.operation = ContainmentQuery{input_set(),input_set("set/b")};
    ContainmentResult containment{ContainmentDecision::undetermined,{},image_evidence()};
    containment.evidence.scope = GeometryClaimScope::containment;
    containment.evidence.reference.inputs = {{"set/a"},{"set/b"}};
    CHECK(check_operation_shape(request).empty());
    CHECK(check_geometry_evidence(containment.evidence,request).empty());
    auto wrong_scope = check_geometry_evidence(support.evidence,request);
    REQUIRE(wrong_scope.size() == 1);
    CHECK(wrong_scope[0].code == DiagnosticCode::evidence_mismatch);
}
TEST_CASE("geometry: sum, intersection and affine preimage enforce operand dimensions") {
    auto request = affine_request();
    SUBCASE("sum") {
        request.operation = MinkowskiSum{input_set(),input_set("set/b")};
        CHECK(check_operation_shape(request).empty());
        request.operation = MinkowskiSum{input_set(),input_set("set/b",3)};
    }
    SUBCASE("intersection") {
        request.operation = Intersection{input_set(),input_set("set/b")};
        CHECK(check_operation_shape(request).empty());
        request.operation = Intersection{input_set(),input_set("set/b",3)};
    }
    SUBCASE("containment") {
        request.operation = ContainmentQuery{input_set(),input_set("set/b")};
        CHECK(check_operation_shape(request).empty());
        request.operation = ContainmentQuery{input_set(),input_set("set/b",3)};
    }
    SUBCASE("preimage") {
        request.operation = AffinePreimage{input_set(),{2,1,{1,0}},{0,0}};
        CHECK(check_operation_shape(request).empty());
        request.operation = AffinePreimage{input_set(),{1,2,{1,0}},{0}};
    }
    auto rejected = check_operation_shape(request);
    REQUIRE(rejected.size() == 1);
    CHECK(rejected[0].code == DiagnosticCode::invalid_input);
}
TEST_CASE("geometry: optional error bounds need nonnegative finite magnitude and support") {
    auto evidence = image_evidence();
    evidence.error_bound = GeometryErrorBound{{"euclidean/hausdorff"},0.1,"state units"};
    CHECK(check_geometry_evidence(evidence,affine_request()).empty());
    SUBCASE("negative") { evidence.error_bound->bound = -1; }
    SUBCASE("infinite") { evidence.error_bound->bound = std::numeric_limits<double>::infinity(); }
    SUBCASE("unsupported bound") { evidence.support = Unestablished{}; }
    auto rejected = check_geometry_evidence(evidence,affine_request());
    REQUIRE(rejected.size() == 1);
    CHECK(rejected[0].code == DiagnosticCode::invalid_claim);
}
