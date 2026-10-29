#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/controllers/continuous_policy.hpp>
#include <csl/optimization/phase_one.hpp>

#include <limits>

using namespace csl;
using namespace csl::model;
using namespace csl::controllers;

namespace {
ObservationPoint before(std::size_t stage) {
    return {{stage}, ObservationTiming::before_decision};
}

ObservationPoint after(std::size_t stage) {
    return {{stage}, ObservationTiming::after_decision};
}

LinearSystem noisy_delayed_system() {
    SystemModel authored{{{1, 1, 1}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{1}}, {1,1,{1}}, {0}}},
        {{ObservationStage{{1,1,{1}}, {1,1,{0}}, {1,1,{0}}, {1,1,{1}}, {0}},
            {{{0}, before(0), before(0), std::nullopt},
             {{1}, after(0), after(0), StageIndex{0}}}}}};
    const auto result = snapshot(authored, Vector{0, 1, 2});
    REQUIRE(std::holds_alternative<LinearSystem>(result));
    return std::get<LinearSystem>(result);
}

LinearSystem partial_sensor_system() {
    SystemModel authored{{{2, 1, 0}, TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}}, {2,1,{0,0}}, {2,0,{}}, {0,0}}},
        {{ObservationStage{{1,2,{1,0}}, {1,1,{0}}, {1,0,{}}, {1,1,{1}}, {0}},
            {{{0}, before(0), before(0), std::nullopt}}}}};
    const auto result = snapshot(authored, Vector{0, 1});
    REQUIRE(std::holds_alternative<LinearSystem>(result));
    return std::get<LinearSystem>(result);
}

LinearSystem multi_output_sensor_system() {
    SystemModel authored{{{2, 1, 0}, TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}}, {2,1,{0,0}}, {2,0,{}}, {0,0}}},
        {{ObservationStage{{2,2,{1,0,0,1}}, {2,1,{0,0}}, {2,0,{}}, {2,0,{}}, {0,0}},
            {{{0}, before(0), before(0), std::nullopt}}}}};
    const auto result = snapshot(authored, Vector{0, 1});
    REQUIRE(std::holds_alternative<LinearSystem>(result));
    return std::get<LinearSystem>(result);
}

LinearSystem one_stage_noisy_integrator() {
    SystemModel authored{{{1, 1, 0}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{1}}, {1,0,{}}, {0}}},
        {{ObservationStage{{1,1,{1}}, {1,1,{0}}, {1,0,{}}, {1,1,{1}}, {0}},
            {{{0}, before(0), before(0), std::nullopt}}}}};
    const auto result = snapshot(authored, Vector{0, 1});
    REQUIRE(std::holds_alternative<LinearSystem>(result));
    return std::get<LinearSystem>(result);
}

LinearSystem one_stage_no_sensor_integrator() {
    SystemModel authored{{{1, 1, 0}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{1}}, {1,0,{}}, {0}}}, {}};
    const auto result = snapshot(authored, Vector{0, 1});
    REQUIRE(std::holds_alternative<LinearSystem>(result));
    return std::get<LinearSystem>(result);
}

AffineStagePolicy rule(std::size_t stage, std::vector<ObservationComponentRef> inputs,
        Matrix estimate, Vector estimate_offset, Matrix action_history,
        Matrix action_estimate, Vector action_offset) {
    return {{stage}, std::move(inputs), std::move(estimate), std::move(estimate_offset),
        std::move(action_history), std::move(action_estimate), std::move(action_offset)};
}

std::vector<AffineStagePolicy> policy_rules() {
    return {
        rule(0, {{{0}, {0}, 0}}, {1,1,{1}}, {0}, {1,1,{0}}, {1,1,{1}}, {0}),
        rule(1, {{{0}, {1}, 0}}, {1,1,{1}}, {0}, {1,1,{1}}, {1,1,{0}}, {0})
    };
}

JointVUncertainty make_domain(const LinearSystem& system) {
    auto result = make_joint_v_uncertainty(system, {
        {1, 0, 0, -1, 0},
        {1, 0, 0, 1, 0}
    });
    REQUIRE(std::holds_alternative<JointVUncertainty>(result));
    return std::get<JointVUncertainty>(std::move(result));
}

JointVUncertainty one_stage_noisy_domain(const LinearSystem& system) {
    auto result = make_joint_v_uncertainty(system, {
        {-1.0, -0.1}, {-1.0, 0.1}, {1.0, -0.1}, {1.0, 0.1}
    });
    REQUIRE(std::holds_alternative<JointVUncertainty>(result));
    return std::get<JointVUncertainty>(std::move(result));
}

OneStageAffineSynthesisRequest one_stage_request(const LinearSystem& system) {
    const auto domain = system.horizon() == 1
        ? one_stage_noisy_domain(system) : make_domain(system);
    return {{{"ext04-one-stage"}, {"noisy-integrator-feasibility"}},
        domain, {{{0}, {0}, 0}},
        {{{2,1,{1,-1}}, {1.1,1.1}}, {{2,1,{1,-1}}, {0.11,0.11}}},
        {{{2,1,{1,-1}}, {1.2,1.2}}}, 1e-8};
}

std::unique_ptr<LPWorkspace> phase_one_workspace() {
    auto registered = optimization::phase_one::make_registration();
    REQUIRE(std::holds_alternative<registry::Registration<registry::LPPort>>(registered));
    const auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registered));
    auto seed = optimization::make_linear_program({{{"ext04-one-stage"}, {"workspace-seed"}},
        {0.0}, 0.0, {1,1,{0,1},{0},{1}}, {Interval{0.0, std::nullopt}}, {Interval{0.0, 0.0}}});
    REQUIRE(std::holds_alternative<LinearProgram>(seed));
    return adapter.factory(std::get<LinearProgram>(seed));
}

class ReportInfeasibleWorkspace final : public LPWorkspace {
protected:
    ProgramOutcome do_solve(const LinearProgram& program, const ExecutionContext&) override {
        return ProgramResult{Termination::completed,
            {program.identity(), MathematicalOutcome::infeasible, Unestablished{}, {}},
            {}, {}, "numerical infeasibility without an exact certificate", {}};
    }
};
}

TEST_CASE("joint V uncertainty keeps correlated coordinates and evaluates released history") {
    const auto system = noisy_delayed_system();
    const auto domain = make_domain(system);
    REQUIRE(domain.layout().total_dimension == 5);
    CHECK(domain.layout().initial_state.offset == 0);
    CHECK(domain.layout().external_by_stage[0].offset == 1);
    CHECK(domain.layout().external_by_stage[1].offset == 2);
    CHECK(domain.layout().errors_by_channel_sample[0][0].offset == 3);
    CHECK(domain.layout().errors_by_channel_sample[0][1].offset == 4);

    const auto policy = make_affine_observation_policy(system, policy_rules());
    REQUIRE(std::holds_alternative<AffineObservationPolicy>(policy));
    const ContinuousPolicyRequest request{PolicyCoverage::all_joint_uncertainty, domain,
        std::get<AffineObservationPolicy>(policy), {}, {}, std::nullopt, 1e-9};
    const auto result = evaluate_continuous_policy(system, request);
    REQUIRE(std::holds_alternative<ContinuousPolicyEvidence>(result));
    const auto& evidence = std::get<ContinuousPolicyEvidence>(result);
    CHECK(evidence.assurance == Assurance::numerical);
    CHECK(evidence.feasibility == NumericalFeasibility::within_tolerance);
    REQUIRE(evidence.trajectories.size() == 2);

    const auto& low = evidence.trajectories[0].trajectory;
    const auto& high = evidence.trajectories[1].trajectory;
    CHECK(low.inputs.initial_state == Vector{1});
    CHECK(low.inputs.measurement_errors[0][0] == Vector{-1});
    CHECK(high.inputs.measurement_errors[0][0] == Vector{1});
    CHECK(low.released[0].value.values == Vector{0});
    CHECK(high.released[0].value.values == Vector{2});
    CHECK(low.decisions[0].action == Vector{0});
    CHECK(high.decisions[0].action == Vector{2});
    CHECK(low.decisions[0].available.size() == 1);
    CHECK(low.decisions[1].available.size() == 2);
    CHECK(low.decisions[1].available[1].released_at.timing == ObservationTiming::after_decision);
    CHECK(low.decisions[1].action == Vector{1});
    CHECK(high.decisions[1].action == Vector{3});
}

TEST_CASE("affine policy builder rejects a post-decision observation at the same decision") {
    const auto system = noisy_delayed_system();
    auto rules = policy_rules();
    rules[0] = rule(0, {{{0}, {1}, 0}}, {1,1,{1}}, {0}, {1,1,{0}}, {1,1,{1}}, {0});
    const auto result = make_affine_observation_policy(system, std::move(rules));
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field == "controllers.policy.nonanticipativity");
}

TEST_CASE("all-joint evidence checks safety at every generator and keeps a violating counterexample") {
    const auto system = noisy_delayed_system();
    const auto domain = make_domain(system);
    const auto policy = make_affine_observation_policy(system, policy_rules());
    REQUIRE(std::holds_alternative<AffineObservationPolicy>(policy));
    LinearSafetyConstraints action_bound{{1,1,{1}}, {1.5}};
    const ContinuousPolicyRequest request{PolicyCoverage::all_joint_uncertainty, domain,
        std::get<AffineObservationPolicy>(policy), {}, {action_bound, action_bound}, std::nullopt, 1e-9};
    const auto result = evaluate_continuous_policy(system, request);
    REQUIRE(std::holds_alternative<ContinuousPolicyEvidence>(result));
    const auto& evidence = std::get<ContinuousPolicyEvidence>(result);
    CHECK(evidence.feasibility == NumericalFeasibility::violation_found);
    REQUIRE(evidence.trajectories.size() == 2);
    CHECK(evidence.trajectories[1].action_slacks[0][0] < 0.0);
    CHECK(evidence.trajectories[1].trajectory.decisions[0].action == Vector{2});
}

TEST_CASE("selected joint witness is one convex combination and requires valid weights") {
    const auto system = noisy_delayed_system();
    const auto domain = make_domain(system);
    const auto policy = make_affine_observation_policy(system, policy_rules());
    REQUIRE(std::holds_alternative<AffineObservationPolicy>(policy));
    const ContinuousPolicyRequest request{PolicyCoverage::selected_joint_witness, domain,
        std::get<AffineObservationPolicy>(policy), {}, {}, JointWitness{{0.5, 0.5}}, 1e-9};
    const auto result = evaluate_continuous_policy(system, request);
    REQUIRE(std::holds_alternative<ContinuousPolicyEvidence>(result));
    const auto& evidence = std::get<ContinuousPolicyEvidence>(result);
    REQUIRE(evidence.trajectories.size() == 1);
    CHECK_FALSE(evidence.trajectories[0].generator_index.has_value());
    REQUIRE(evidence.trajectories[0].witness_weights.has_value());
    CHECK(*evidence.trajectories[0].witness_weights == Vector{0.5, 0.5});
    CHECK(evidence.trajectories[0].joint_coordinates == Vector{1, 0, 0, 0, 0});
    CHECK(evidence.trajectories[0].trajectory.decisions[0].action == Vector{1});

    auto bad = request;
    bad.witness = JointWitness{{1.0, 1.0}};
    const auto rejected = evaluate_continuous_policy(system, bad);
    REQUIRE(std::holds_alternative<Diagnostic>(rejected));
    CHECK(std::get<Diagnostic>(rejected).field == "controllers.policy.witness");
}

TEST_CASE("partial observations leave hidden initial coordinates out of the policy input") {
    const auto system = partial_sensor_system();
    const auto domain_result = make_joint_v_uncertainty(system, {
        {1, 7, 0},
        {1, 9, 0}
    });
    REQUIRE(std::holds_alternative<JointVUncertainty>(domain_result));
    auto built_policy = make_affine_observation_policy(system, {
        rule(0, {{{0}, {0}, 0}}, {2,1,{1,0}}, {0,0}, {1,1,{1}}, {1,2,{0,0}}, {0})
    });
    REQUIRE(std::holds_alternative<AffineObservationPolicy>(built_policy));
    const ContinuousPolicyRequest request{PolicyCoverage::all_joint_uncertainty,
        std::get<JointVUncertainty>(domain_result),
        std::get<AffineObservationPolicy>(built_policy), {}, {}, std::nullopt, 1e-9};
    const auto result = evaluate_continuous_policy(system, request);
    REQUIRE(std::holds_alternative<ContinuousPolicyEvidence>(result));
    const auto& evidence = std::get<ContinuousPolicyEvidence>(result);
    REQUIRE(evidence.trajectories.size() == 2);
    CHECK(evidence.trajectories[0].trajectory.decisions[0].available[0].value.values == Vector{1});
    CHECK(evidence.trajectories[1].trajectory.decisions[0].available[0].value.values == Vector{1});
    CHECK(evidence.trajectories[0].trajectory.decisions[0].action == Vector{1});
    CHECK(evidence.trajectories[1].trajectory.decisions[0].action == Vector{1});
    CHECK(evidence.trajectories[0].trajectory.inputs.initial_state[1] == 7);
    CHECK(evidence.trajectories[1].trajectory.inputs.initial_state[1] == 9);
}

TEST_CASE("affine policies can read two components from one released observation sample") {
    const auto system = multi_output_sensor_system();
    const auto built = make_affine_observation_policy(system, {
        rule(0, {{{0}, {0}, 0}, {{0}, {0}, 1}},
            {2,2,{1,0,0,1}}, {0,0}, {1,2,{0,0}}, {1,2,{0,1}}, {0})
    });
    REQUIRE(std::holds_alternative<AffineObservationPolicy>(built));
    const auto domain_result = make_joint_v_uncertainty(system, {{1,2}, {3,4}});
    REQUIRE(std::holds_alternative<JointVUncertainty>(domain_result));
    const ContinuousPolicyRequest request{PolicyCoverage::all_joint_uncertainty,
        std::get<JointVUncertainty>(domain_result),
        std::get<AffineObservationPolicy>(built), {}, {}, std::nullopt, 1e-9};
    const auto result = evaluate_continuous_policy(system, request);
    REQUIRE(std::holds_alternative<ContinuousPolicyEvidence>(result));
    const auto& trajectories = std::get<ContinuousPolicyEvidence>(result).trajectories;
    REQUIRE(trajectories.size() == 2);
    CHECK(trajectories[0].trajectory.decisions[0].available[0].value.values == Vector{1,2});
    CHECK(trajectories[1].trajectory.decisions[0].available[0].value.values == Vector{3,4});
    CHECK(trajectories[0].trajectory.decisions[0].action == Vector{2});
    CHECK(trajectories[1].trajectory.decisions[0].action == Vector{4});

    auto duplicate_component = make_affine_observation_policy(system, {
        rule(0, {{{0}, {0}, 0}, {{0}, {0}, 0}},
            {2,2,{1,0,0,1}}, {0,0}, {1,2,{0,0}}, {1,2,{0,1}}, {0})
    });
    REQUIRE(std::holds_alternative<Diagnostic>(duplicate_component));
}

TEST_CASE("constraint margins near the requested tolerance remain inconclusive") {
    const auto system = noisy_delayed_system();
    const auto domain = make_domain(system);
    const auto policy = make_affine_observation_policy(system, policy_rules());
    REQUIRE(std::holds_alternative<AffineObservationPolicy>(policy));
    LinearSafetyConstraints action_bound{{1,1,{1}}, {3.0}};
    const ContinuousPolicyRequest request{PolicyCoverage::all_joint_uncertainty, domain,
        std::get<AffineObservationPolicy>(policy), {}, {action_bound, action_bound}, std::nullopt, 1e-9};
    const auto result = evaluate_continuous_policy(system, request);
    REQUIRE(std::holds_alternative<ContinuousPolicyEvidence>(result));
    CHECK(std::get<ContinuousPolicyEvidence>(result).feasibility == NumericalFeasibility::inconclusive);
}

TEST_CASE("joint V uncertainty rejects incomplete and nonfinite generator rows") {
    const auto system = noisy_delayed_system();
    auto wrong_dimension = make_joint_v_uncertainty(system, {{1, 0, 0}});
    REQUIRE(std::holds_alternative<Diagnostic>(wrong_dimension));
    auto nonfinite = make_joint_v_uncertainty(system, {{1, 0, 0,
        std::numeric_limits<double>::infinity(), 0}});
    REQUIRE(std::holds_alternative<Diagnostic>(nonfinite));
}

TEST_CASE("joint generators retain initial and cross-stage external correlation") {
    const auto system = noisy_delayed_system();
    const auto domain_result = make_joint_v_uncertainty(system, {
        {0, 1, 0, 0, 0},
        {1, 0, 1, 0, 0}
    });
    REQUIRE(std::holds_alternative<JointVUncertainty>(domain_result));
    const auto built_policy = make_affine_observation_policy(system, policy_rules());
    REQUIRE(std::holds_alternative<AffineObservationPolicy>(built_policy));
    const ContinuousPolicyRequest request{PolicyCoverage::all_joint_uncertainty,
        std::get<JointVUncertainty>(domain_result),
        std::get<AffineObservationPolicy>(built_policy), {}, {}, std::nullopt, 1e-9};
    const auto result = evaluate_continuous_policy(system, request);
    REQUIRE(std::holds_alternative<ContinuousPolicyEvidence>(result));
    const auto& trajectories = std::get<ContinuousPolicyEvidence>(result).trajectories;
    REQUIRE(trajectories.size() == 2);
    CHECK(trajectories[0].trajectory.inputs.initial_state == Vector{0});
    CHECK(trajectories[0].trajectory.inputs.external == std::vector<Vector>{{1}, {0}});
    CHECK(trajectories[1].trajectory.inputs.initial_state == Vector{1});
    CHECK(trajectories[1].trajectory.inputs.external == std::vector<Vector>{{0}, {1}});
}

TEST_CASE("one-stage affine synthesis finds an observation policy over the whole joint V-hull") {
    const auto system = one_stage_noisy_integrator();
    auto request = one_stage_request(system);
    auto lp = phase_one_workspace();
    REQUIRE(lp != nullptr);

    const auto result = synthesize_one_stage_affine_policy(system, request, *lp, {});
    REQUIRE(std::holds_alternative<SynthesizedAffinePolicy>(result));
    const auto& found = std::get<SynthesizedAffinePolicy>(result);
    CHECK(found.feasibility_solve.termination == Termination::completed);
    CHECK(found.feasibility_solve.outcome.value == MathematicalOutcome::optimal);
    CHECK(found.evaluation.scope == PolicyCoverage::all_joint_uncertainty);
    CHECK(found.evaluation.assurance == Assurance::numerical);
    CHECK(found.evaluation.feasibility == NumericalFeasibility::within_tolerance);
    REQUIRE(found.evaluation.trajectories.size() == 4);
    for (const auto& generator : found.evaluation.trajectories) {
        REQUIRE(generator.trajectory.states.size() == 2);
        CHECK(std::abs(generator.trajectory.states.back()[0]) < 0.11);
        CHECK(std::abs(generator.trajectory.decisions.front().action[0]) < 1.2);
    }
}

TEST_CASE("one-stage synthesis rejects observations unavailable before the action") {
    auto system = one_stage_noisy_integrator();
    auto authored = SystemModel{{{1, 1, 0}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{1}}, {1,0,{}}, {0}}},
        {{ObservationStage{{1,1,{1}}, {1,1,{0}}, {1,0,{}}, {1,1,{1}}, {0}},
            {{{0}, after(0), after(0), std::nullopt}}}}};
    const auto later = snapshot(authored, Vector{0, 1});
    REQUIRE(std::holds_alternative<LinearSystem>(later));
    system = std::get<LinearSystem>(later);
    auto request = one_stage_request(system);
    auto lp = phase_one_workspace();
    REQUIRE(lp != nullptr);

    const auto result = synthesize_one_stage_affine_policy(system, request, *lp, {});
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field == "controllers.policy.nonanticipativity");
}

TEST_CASE("numerical solver infeasibility is reported as inconclusive without a certificate") {
    const auto system = one_stage_noisy_integrator();
    auto request = one_stage_request(system);
    ReportInfeasibleWorkspace lp;

    const auto result = synthesize_one_stage_affine_policy(system, request, lp, {});
    REQUIRE(std::holds_alternative<AffineSynthesisInconclusive>(result));
    CHECK(std::get<AffineSynthesisInconclusive>(result).reason ==
        AffineSynthesisInconclusiveReason::solver_reported_infeasible_without_certificate);
}

TEST_CASE("one-stage synthesis stops before allocating an LP over its memory budget") {
    const auto system = one_stage_noisy_integrator();
    auto request = one_stage_request(system);
    auto lp = phase_one_workspace();
    REQUIRE(lp != nullptr);
    constexpr std::size_t generated_rows = 4 * (2 + 2 + 2);
    constexpr std::size_t parameters = 2;
    constexpr std::size_t columns = 2 * parameters + generated_rows;
    constexpr std::size_t maximum_nonzeros = generated_rows * (2 * parameters + 1);
    const auto previously_estimated_bytes = generated_rows * parameters * sizeof(double) +
        generated_rows * (sizeof(Vector) + sizeof(double)) +
        maximum_nonzeros * (sizeof(std::size_t) + sizeof(double)) +
        (generated_rows + 1) * sizeof(std::size_t) +
        columns * (sizeof(double) + sizeof(Interval)) +
        generated_rows * sizeof(Interval);
    ExecutionContext context;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{
        1, 1, 1, previously_estimated_bytes});

    const auto result = synthesize_one_stage_affine_policy(system, request, *lp, context);
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason == StopReason::resource_limit);
}

TEST_CASE("one-stage affine synthesis rejects longer horizons before building a policy") {
    const auto system = noisy_delayed_system();
    auto request = one_stage_request(system);
    auto lp = phase_one_workspace();
    REQUIRE(lp != nullptr);

    const auto result = synthesize_one_stage_affine_policy(system, request, *lp, {});
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).code == DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostic>(result).field == "controllers.synthesis.horizon");
}

TEST_CASE("one-stage synthesis rejects a joint domain from a different system layout") {
    const auto sensed_system = one_stage_noisy_integrator();
    const auto system = one_stage_no_sensor_integrator();
    auto request = one_stage_request(sensed_system);
    auto lp = phase_one_workspace();
    REQUIRE(lp != nullptr);

    const auto result = synthesize_one_stage_affine_policy(system, request, *lp, {});
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field == "controllers.synthesis.domain");

    auto policy = make_affine_observation_policy(system, {AffineStagePolicy{{0}, {},
        {1,0,{}}, {0}, {1,0,{}}, {1,1,{0}}, {0}}});
    REQUIRE(std::holds_alternative<AffineObservationPolicy>(policy));
    ContinuousPolicyRequest evaluation_request{PolicyCoverage::all_joint_uncertainty,
        request.domain, std::get<AffineObservationPolicy>(std::move(policy)), {}, {}, std::nullopt, 1e-9};
    const auto evaluation = evaluate_continuous_policy(system, evaluation_request);
    REQUIRE(std::holds_alternative<Diagnostic>(evaluation));
    CHECK(std::get<Diagnostic>(evaluation).field == "controllers.policy.domain");
}
