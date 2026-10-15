#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/verification/trajectory.hpp>
#include <csl/optimization/phase_one.hpp>

using namespace csl;
using namespace csl::verification;
namespace {
template<class T,class... Rest> T accepted(std::variant<T,Rest...> result) {
    REQUIRE(std::holds_alternative<T>(result));return std::get<T>(std::move(result));
}
numeric::MatrixView matrix(Matrix value) {return accepted(numeric::snapshot(std::move(value)));}
numeric::VectorView vector(Vector value) {return accepted(numeric::snapshot_vector(std::move(value)));}
SetHandle segment_v() {
    return accepted(sets::make_v({{"segment"},1,{}},
        {matrix({2,1,{0,4}}),matrix({0,1,{}})})).as_handle();
}
Problem source_problem() {
    return {{"authored"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{0}},{1,1,{1}},{1,0,{}},{0}}},{}}),{0,1},KnownInitial{{2}},
        ContinuousDomain{{Singleton{{3}}}},{UniversalSet{1},UniversalSet{1}},{},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{1},0}};
}
problem::ResolvedProblem resolve(Problem p) {
    return accepted(problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
}
TrajectoryRequest request(const problem::ResolvedProblem& p) {
    TrajectoryRequest result;
    result.witness={p.identity(),{{2},{3}},{{3}},3};
    return result;
}
class UnexpectedMembershipWorkspace final:public LPWorkspace {
public:
    ProgramOutcome do_solve(const LinearProgram&,const ExecutionContext&) override {
        return Unsupported{Diagnostics{{DiagnosticCode::unsupported,"unexpected","rejected provider factory must not run"}}};
    }
};
registry::PreparedProvider<registry::LPPort> rejecting_provider(int& factory_calls) {
    registry::Registry<registry::LPPort> registry;
    REQUIRE(!registry.add({{{"membership-rejector"},"1"},
        [](const LinearProgram&,const registry::Requirements&)->registry::Capability {
            return Diagnostics{{DiagnosticCode::unsupported,"membership","literal operation rejection"}};
        },
        [&factory_calls](const LinearProgram&) {
            ++factory_calls;return std::make_unique<UnexpectedMembershipWorkspace>();
        }}));
    return accepted(registry::prepare_provider(
        registry::select_provider(registry,{{"membership-rejector"},"1"})));
}
}
TEST_CASE("provider rejection retains backend bound provenance without promoting candidate claims") {
    auto input=source_problem();
    input.states[1]=segment_v();
    const auto p=resolve(input);
    auto q=request(p);

    ClaimEvidence claim{p.identity(),NumericalCheck{0,0,0,{"literal-candidate-check"}}};
    q.outcome=SynthesisOutcomeClaim{p.identity(),MathematicalOutcome::optimal,
        claim.support,{"backend-reported-optimum"}};
    const auto coordinates=p.constraints().coordinates();
    const FamilyRequest effective{"nominal",p.identity(),FamilyTarget::candidate_relaxation,
        {1e-8,1e-8},Assurance::numerical,{"candidate-representation"},{}};
    const FamilyIdentity family_identity{p.identity(),effective,coordinates,{"candidate-strategy"},"1",{}};
    const JointRelation relation{coordinates,effective.representation,{}};
    q.expected_synthesis=ExpectedSynthesisBinding{effective,{"candidate-strategy"},"1",{}};
    q.family=accepted(FamilyPublisher::publish(family_identity,CandidateFamily{relation,
        HeuristicRelationEvidence{"sampled candidate"},WitnessFeasibilityEvidence{q.witness,claim}}));

    const ProgramIdentity backend_program{p.identity(),{"backend/source-objective-program"}};
    const CertificateReference backend_support{"backend-bound-artifact","source-solver-v1"};
    const std::vector<std::string> assumptions{"backend bound refers to generated source-objective LP"};
    q.backend_bounds.push_back({ProgramObjectiveBound{3,{backend_program,backend_support,assumptions}},std::nullopt});

    int factory_calls=0;
    const auto report=verify_trajectory(p,q,{},rejecting_provider(factory_calls));

    CHECK(report.termination==Termination::completed);
    CHECK(report.bindings==CheckStatus::numerical_pass);
    CHECK(report.feasibility==CheckStatus::unsupported);
    CHECK(report.objective==CheckStatus::numerical_pass);
    CHECK(report.optimality==CheckStatus::unsupported);
    CHECK(report.completeness==CheckStatus::unsupported);
    CHECK(report.validated==CheckStatus::unsupported);
    CHECK(factory_calls==0);

    REQUIRE(report.input.outcome);
    CHECK(report.input.outcome->value==MathematicalOutcome::optimal);
    REQUIRE(report.input.family);
    CHECK(report.input.family->target()==FamilyTarget::candidate_relaxation);
    REQUIRE(report.input.backend_bounds.size()==1);
    REQUIRE(report.input.backend_bounds[0].lower);
    CHECK_FALSE(report.input.backend_bounds[0].upper);
    const auto& retained=*report.input.backend_bounds[0].lower;
    CHECK(retained.value==3);
    CHECK(retained.evidence.subject==backend_program);
    CHECK(retained.evidence.subject.problem==p.identity());
    CHECK(retained.evidence.subject.program.value=="backend/source-objective-program");
    REQUIRE(std::holds_alternative<CertificateReference>(retained.evidence.support));
    const auto& support=std::get<CertificateReference>(retained.evidence.support);
    CHECK(support.artifact=="backend-bound-artifact");
    CHECK(support.verifier=="source-solver-v1");
    CHECK(retained.evidence.assumptions==assumptions);

    REQUIRE(report.membership_queries.size()==1);
    REQUIRE(std::holds_alternative<registry::LPQueryRejected>(report.membership_queries[0]));
    const auto& rejected=std::get<registry::LPQueryRejected>(report.membership_queries[0]);
    CHECK(rejected.request.problem==p.identity());
    CHECK(rejected.rejection.provenance.requested.id.value=="membership-rejector");
    REQUIRE(rejected.rejection.provenance.actual);
    CHECK(rejected.rejection.provenance.actual->id.value=="membership-rejector");
    REQUIRE(rejected.rejection.diagnostics.size()==1);
    CHECK(rejected.rejection.diagnostics.front().code==DiagnosticCode::unsupported);
    CHECK(rejected.rejection.diagnostics.front().field=="membership");
    CHECK(rejected.rejection.diagnostics.front().explanation=="literal operation rejection");
}
