#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/linear_infeasibility_certificate.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <csl/synthesis/contracts.hpp>
#include <algorithm>
#include <limits>
#include <type_traits>
#include <iostream>

using namespace csl;
using namespace csl::optimization;
static_assert(!std::is_default_constructible_v<ExactFarkasEvidence>);
static_assert(!std::is_constructible_v<ExactFarkasEvidence,LinearInfeasibilityCertificate>);

namespace {
LinearProgram accepted(LinearProgramInput input) {
    auto result=make_linear_program(input);
    if(const auto* errors=std::get_if<Diagnostics>(&result))
        for(const auto& error:*errors)std::cerr<<error.field<<": "<<error.explanation<<'\n';
    REQUIRE(std::holds_alternative<LinearProgram>(result));
    return std::get<LinearProgram>(std::move(result));
}
LinearProgram disjoint_row_bounds(std::string id="row-infeasible") {
    return accepted({{{"farkas"},{std::move(id)}},{0},0,
        {2,1,{0,1,2},{0,0},{1,1}},{{{},{}}},{{1,{}},{{},0}}});
}
LinearInfeasibilityCertificate row_certificate(const LinearProgram& program) {
    return {program.identity(),{1,0},{0,1},{0},{0}};
}
ProgramResult infeasible_result(const LinearProgram& program,
    EvidenceSupport support=Unestablished{}) {
    return {Termination::completed,
        {program.identity(),MathematicalOutcome::infeasible,std::move(support),{}},
        {},{},"infeasible backend status",{}};
}
ExactFarkasEvidence verified(const LinearProgram& program,
    const LinearInfeasibilityCertificate& certificate) {
    auto result=verify_linear_infeasibility_certificate(program,certificate);
    REQUIRE(std::holds_alternative<ExactFarkasEvidence>(result));
    return std::get<ExactFarkasEvidence>(std::move(result));
}
}

TEST_CASE("exact Farkas certificate proves contradictory row bounds at the public LP boundary") {
    const auto program=disjoint_row_bounds();
    const auto certificate=row_certificate(program);

    const auto proof=verified(program,certificate);
    CHECK(proof.subject()==program.identity());
    CHECK(proof.certificate().row_lower==Vector{1,0});
    CHECK(check_program_result(infeasible_result(program,proof),program,Assurance::numerical).empty());
    CHECK(check_program_result(infeasible_result(program,proof),program,Assurance::validated).empty());
}

TEST_CASE("exact verifier rejects a certificate whose identity belongs to another LP") {
    const auto program=disjoint_row_bounds();
    auto certificate=row_certificate(program);
    certificate.subject.program.value+="-other";

    const auto wrong=verify_linear_infeasibility_certificate(program,certificate);
    REQUIRE(std::holds_alternative<Diagnostics>(wrong));
    CHECK_FALSE(std::get<Diagnostics>(wrong).empty());
}

TEST_CASE("exact verifier rejects malformed, negative, nonfinite, and absent-endpoint multipliers") {
    const auto program=disjoint_row_bounds();
    const auto valid=row_certificate(program);
    auto invalid=valid;invalid.row_lower.pop_back();
    CHECK(std::holds_alternative<Diagnostics>(verify_linear_infeasibility_certificate(program,invalid)));
    invalid=valid;invalid.row_lower[0]=-1;
    CHECK(std::holds_alternative<Diagnostics>(verify_linear_infeasibility_certificate(program,invalid)));
    invalid=valid;invalid.variable_upper[0]=std::numeric_limits<double>::infinity();
    CHECK(std::holds_alternative<Diagnostics>(verify_linear_infeasibility_certificate(program,invalid)));
    invalid=valid;invalid.row_upper[0]=1; // row zero has no upper endpoint
    CHECK(std::holds_alternative<Diagnostics>(verify_linear_infeasibility_certificate(program,invalid)));
    invalid=valid;invalid.row_lower[1]=1; // row one has no lower endpoint
    CHECK(std::holds_alternative<Diagnostics>(verify_linear_infeasibility_certificate(program,invalid)));
    invalid=valid;invalid.variable_lower[0]=1; // variable is free
    CHECK(std::holds_alternative<Diagnostics>(verify_linear_infeasibility_certificate(program,invalid)));
}

TEST_CASE("exact verifier rejects nonzero stationarity and nonpositive contradiction constants") {
    const auto program=disjoint_row_bounds();
    auto invalid=row_certificate(program);invalid.row_upper[1]=0;
    CHECK(std::holds_alternative<Diagnostics>(verify_linear_infeasibility_certificate(program,invalid)));

    const auto feasible=accepted({{{"farkas"},{"feasible"}},{0},0,
        {1,1,{0,1},{0},{1}},{{{},{}}},{{0,1}}});
    const LinearInfeasibilityCertificate nonpositive{
        feasible.identity(),{1},{1},{0},{0}};
    CHECK(std::holds_alternative<Diagnostics>(verify_linear_infeasibility_certificate(feasible,nonpositive)));
}

TEST_CASE("exact stationarity preserves cancellation lost by rounded summation") {
    const auto program=accepted({{{"farkas"},{"cancellation"}},{0},0,
        {4,1,{0,1,2,3,4},{0,0,0,0},{1e16,1,-1e16,-1}},{{{},{}}},
        {{1,{}},{0,{}},{0,{}},{0,{}}}});
    const LinearInfeasibilityCertificate certificate{
        program.identity(),{1,1,1,1},{0,0,0,0},{0},{0}};

    CHECK(std::holds_alternative<ExactFarkasEvidence>(verify_linear_infeasibility_certificate(program,certificate)));
}

TEST_CASE("strictly positive subnormal contradiction and zero-dimensional proofs remain exact") {
    const double tiny=std::numeric_limits<double>::denorm_min();
    const auto subnormal=accepted({{{"farkas"},{"subnormal"}},{0},0,
        {2,1,{0,1,2},{0,0},{1,1}},{{{},{}}},{{tiny,{}},{{},0}}});
    const auto certificate=row_certificate(subnormal);
    CHECK(std::holds_alternative<ExactFarkasEvidence>(verify_linear_infeasibility_certificate(subnormal,certificate)));

    const auto zero_dimensional=accepted({{{"farkas"},{"zero-dimensional"}},{},0,
        {1,0,{0,0},{},{}},{},{{1,{}}}});
    const LinearInfeasibilityCertificate zero_certificate{
        zero_dimensional.identity(),{1},{0},{},{}};
    CHECK(std::holds_alternative<ExactFarkasEvidence>(verify_linear_infeasibility_certificate(zero_dimensional,zero_certificate)));
}

TEST_CASE("variable endpoint multipliers independently prove incompatible bounds") {
    const auto program=accepted({{{"farkas"},{"variable-bounds"}},{0},0,
        {1,1,{0,1},{0},{1}},{{{},0}},{{1,{}}}});
    const LinearInfeasibilityCertificate certificate{program.identity(),{1},{0},{0},{1}};
    CHECK(std::holds_alternative<ExactFarkasEvidence>(verify_linear_infeasibility_certificate(program,certificate)));
}

TEST_CASE("LP and synthesis outcome validation permit only infeasibility-scoped Farkas evidence") {
    const auto program=disjoint_row_bounds();
    CHECK(check_program_result(infeasible_result(program),program,Assurance::numerical).empty());
    const auto proof=verified(program,row_certificate(program));
    CHECK(check_program_result(infeasible_result(program,proof),program,Assurance::numerical).empty());

    const auto valid_claim=ProgramOutcomeClaim{program.identity(),MathematicalOutcome::infeasible,proof,{}};
    CHECK(check_outcome_evidence(valid_claim,program.identity(),Assurance::validated).empty());
    auto wrong_outcome=valid_claim;wrong_outcome.value=MathematicalOutcome::optimal;
    CHECK_FALSE(check_outcome_evidence(wrong_outcome,program.identity(),Assurance::numerical).empty());
    auto source_claim=SynthesisOutcomeClaim{program.identity().problem,MathematicalOutcome::infeasible,proof,{}};
    CHECK(check_outcome_evidence(source_claim,program.identity().problem,Assurance::validated).empty());
    CHECK_FALSE(check_outcome_evidence(source_claim,ProblemId{"another-source"},Assurance::numerical).empty());
    source_claim.value=MathematicalOutcome::optimal;
    CHECK_FALSE(check_outcome_evidence(source_claim,program.identity().problem,Assurance::numerical).empty());

    source_claim.value=MathematicalOutcome::infeasible;
    FamilyRequest family_request;family_request.objective=program.identity().problem;
    family_request.profile="test";family_request.target=FamilyTarget::exact_optimal_relation;
    family_request.representation={"csl.polyhedron.h"};
    FamilyIdentity identity{program.identity().problem,family_request,{{1,1,0},0},{"test.strategy"},"1",{}};
    const JointRelation relation{identity.coordinates,family_request.representation,{}};
    const CompleteOptimalFamily claimed{relation,{{program.identity().problem,proof},{}},
        {identity,RegisteredCompletenessEvidence{{"test.verifier"},"1","unchecked"}},Assurance::numerical};
    const auto publication=FamilyPublisher::publish(identity,claimed);
    REQUIRE(std::holds_alternative<Diagnostics>(publication));
    CHECK(std::any_of(std::get<Diagnostics>(publication).begin(),std::get<Diagnostics>(publication).end(),
        [](const Diagnostic& diagnostic){return diagnostic.field=="family.optimum";}));
}

TEST_CASE("LP result validation rechecks sealed evidence against the exact current LP data") {
    const auto original=disjoint_row_bounds("stable-identity");
    auto feasible=accepted({original.identity(),{0},0,{2,1,{0,1,2},{0,0},{1,1}},{{{},{}}},{{0,{}},{{},1}}});
    const auto proof=verified(original,row_certificate(original));

    CHECK_FALSE(check_program_result(infeasible_result(feasible,proof),feasible,Assurance::numerical).empty());
}
