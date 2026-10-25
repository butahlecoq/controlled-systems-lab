#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/application/comparison.hpp>
#include <csl/artifacts/run_statistics.hpp>
#include <csl/artifacts/comparison_manifest.hpp>
#include <csl/execution/observability.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/problem/validator.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/synthesis/witness_selector.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
#include <type_traits>
#include <utility>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using namespace csl;

namespace {
template<class T, class... Rest> T take(std::variant<T, Rest...> value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}

template<class T> T take_artifact(artifacts::ArtifactResult<T> value, const char* operation) {
    if (const auto* error = std::get_if<artifacts::ArtifactError>(&value))
        throw std::runtime_error(std::string(operation) + " failed at " + error->path + ": " + error->message);
    if (!std::holds_alternative<T>(value))
        throw std::runtime_error(std::string(operation) + " returned an unexpected artifact result");
    return std::get<T>(std::move(value));
}

nlohmann::json sample_obs04_environment() {
    const auto digest=std::string(64,'a');
    return {
        {"schema","csl.obs04-environment/1"},
        {"build",{{"schema","csl.obs04-build/1"},{"source_revision",std::string(40,'b')},
            {"source_tree_sha256",digest},{"source_snapshot_method","git-head-tracked-diff-untracked-content-sha256/1"},
            {"source_dirty",false},{"compiler_id","GNU"},
            {"compiler_version","13.3.0"},{"generator","Unix Makefiles"},{"architecture","x86_64"},
            {"build_type","Release"},{"cxx_standard","20"},{"c_flags_sha256",digest},
            {"cxx_flags_sha256",digest},{"executable_link_flags_sha256",digest},{"target_flags_sha256",digest},
            {"backends",{{"highs",{{"version","1.11.0"},{"archive_sha256",digest}}},
                {"qhull",{{"version","8.0.2"},{"archive_sha256",digest}}}}}}},
        {"runtime",{{"schema","csl.obs04-runtime/1"},
            {"binary_sha256",{{"status","available"},{"value",digest}}},{"os_family","Linux"},
            {"os_version",{{"status","available"},{"value","Ubuntu 24.04"}}},
            {"kernel",{{"status","available"},{"value","6.8.0"}}},{"architecture","x86_64"},
            {"cpu_model",{{"status","unavailable"},{"reason","not exposed by the platform adapter"}}},
            {"logical_cpus",{{"status","available"},{"value",8}}}}},
        {"execution",{{"requested_workers",1},{"observed_driver_workers",1},
            {"requested_backend_threads",1},
            {"observed_backend_threads",{{"status","unavailable"},{"reason","backend thread count is not observable"}}},
            {"workspace_policy","fresh-workspace-per-attempt"},
            {"cache_policy","one warm-up per arm; caches are not flushed"},{"warmup_repetitions",1},
            {"seed_policy",{{"kind","not_applicable"},{"reason","fixed analytic fixture uses no random generator"}}},
            {"tolerances",{{"absolute",1e-8},{"relative",1e-8}}}}}
    };
}

SetHandle interval(std::string id) {
    const sets::Description description{SetId{std::move(id)}, 1, {"u"}};
    const sets::HRepresentation representation{
        take(numeric::snapshot(Matrix{2, 1, {1, -1}})),
        take(numeric::snapshot_vector(Vector{1, 0})),
        take(numeric::snapshot(Matrix{0, 1, {}})),
        take(numeric::snapshot_vector(Vector{}))};
    return take(sets::make_h(description, representation)).as_handle();
}

problem::ResolvedProblem source(std::string profile) {
    Matrix a{1, 1, {1}}, b{1, 1, {1}}, e{1, 0, {}};
    if (profile == "ts03_singular_integrator") a.values = {0};
    const LinearStage transition{std::move(a), std::move(b), std::move(e), {0}};
    const auto model = std::make_shared<const SystemModel>(SystemModel{
        Dynamics{{1, 1, 0}, TimeDomain::discrete, transition}, {}});
    Problem authored;
    authored.id = {"application-paired-" + profile};
    authored.model = model;
    authored.times = {0, 1, 2};
    authored.initial = KnownInitial{{0}};
    authored.controls = ContinuousDomain{{interval("u0"), interval("u1")}};
    authored.states = {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}};
    authored.information = InformationPattern::nominal_open_loop;
    if (profile == "ts01_exact_integrator" || profile == "ts03_singular_integrator") {
        QuadraticTerminal objective;
        objective.Q = Matrix{1, 1, {2}};
        objective.linear = {-2};
        objective.offset = 1;
        authored.objective = objective;
    } else {
        authored.objective = LinearTerminal{{0}, 3};
    }
    return take(problem::resolve(authored,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
}

void check_full_dynamics(const problem::ResolvedProblem& problem, const Witness& witness) {
    REQUIRE(witness.states.size() == witness.controls.size() + 1);
    const auto model = problem.model();
    REQUIRE(witness.states.front() == std::get<KnownInitial>(*problem.initial().description()).point);
    for (std::size_t k = 0; k < witness.controls.size(); ++k) {
        const auto stages = take(model.stage({k}));
        const auto& state = witness.states[k];
        const auto& control = witness.controls[k];
        Vector next(stages.offset.values().begin(), stages.offset.values().end());
        REQUIRE(next.size() == state.size());
        for (std::size_t row = 0; row < next.size(); ++row) {
            for (std::size_t col = 0; col < state.size(); ++col)
                next[row] += stages.A(row, col) * state[col];
            for (std::size_t col = 0; col < control.size(); ++col)
                next[row] += stages.B(row, col) * control[col];
        }
        REQUIRE(next.size() == witness.states[k + 1].size());
        for (std::size_t row = 0; row < next.size(); ++row)
            CHECK(next[row] == doctest::Approx(witness.states[k + 1][row]));
    }
}

bool family_contains_history(const OptimalFamily& family, const Vector& history, double tolerance = 1e-9) {
    const auto* complete = std::get_if<CompleteOptimalFamily>(&family.outcome());
    if (!complete || !complete->relation.payload) return false;
    const auto* relation = complete->relation.payload->h_relation_for_recording();
    if (!relation) return false;
    const auto representation = relation->representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h || history.size() != h->inequalities.cols() || history.size() != h->equalities.cols()) return false;
    for (std::size_t row = 0; row < h->inequalities.rows(); ++row) {
        double value = 0.0;
        for (std::size_t col = 0; col < history.size(); ++col) value += h->inequalities(row, col) * history[col];
        if (value > h->upper_bounds[row] + tolerance) return false;
    }
    for (std::size_t row = 0; row < h->equalities.rows(); ++row) {
        double value = 0.0;
        for (std::size_t col = 0; col < history.size(); ++col) value += h->equalities(row, col) * history[col];
        if (std::abs(value - h->equality_values[row]) > tolerance) return false;
    }
    return true;
}

template<class Port> registry::PreparedProvider<Port> selected(
    registry::Registration<Port> entry, std::string representation) {
    registry::Registry<Port> providers;
    const registry::Method method{entry.identity.id, entry.identity.version};
    REQUIRE_FALSE(providers.add(std::move(entry)));
    registry::Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, registry::GeometryPort> ||
        std::is_same_v<Port, registry::ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(registry::prepare_provider(
        registry::select_provider(providers, method, requirements)));
}

struct Modules {
    std::shared_ptr<registry::Registry<registry::GeometryPort>> projections;
    std::shared_ptr<registry::Registry<registry::GeometryPort>> affines;
    std::shared_ptr<registry::Registry<registry::ConversionPort>> conversions;
    std::shared_ptr<registry::Registry<registry::LPPort>> lps;
    std::shared_ptr<registry::Registry<registry::ConvexPort>> convexes;
    registry::StrategyRegistry strategies;
    registry::Registry<registry::SelectorPort> selectors;
    registry::PreparedProvider<registry::LPPort> membership;

    Modules(std::shared_ptr<registry::Registry<registry::GeometryPort>> projection_registry,
        std::shared_ptr<registry::Registry<registry::GeometryPort>> affine_registry,
        std::shared_ptr<registry::Registry<registry::ConversionPort>> conversion_registry,
        std::shared_ptr<registry::Registry<registry::LPPort>> lp_registry,
        std::shared_ptr<registry::Registry<registry::ConvexPort>> convex_registry,
        registry::PreparedProvider<registry::LPPort> prepared_membership)
        : projections(std::move(projection_registry)), affines(std::move(affine_registry)),
          conversions(std::move(conversion_registry)), lps(std::move(lp_registry)),
          convexes(std::move(convex_registry)), membership(std::move(prepared_membership)) {}
};

Modules modules() {
    auto lp = take(adapters::lp::make_highs_registration());
    auto convex = take(adapters::convex::make_highs_registration());
    auto converter = take(adapters::polyhedral::make_qhull_registration(lp));
    auto projection = geometry::polyhedral::make_projection_registration();
    auto affine = geometry::make_affine_sum_registration({
        selected(geometry::make_lp_hull_reducer_registration(), ""),
        selected(lp, "csl.program-result.v1"), selected(converter, "csl.polyhedron.v")});
    auto projections = std::make_shared<registry::Registry<registry::GeometryPort>>();
    auto affines = std::make_shared<registry::Registry<registry::GeometryPort>>();
    auto conversions = std::make_shared<registry::Registry<registry::ConversionPort>>();
    auto lps = std::make_shared<registry::Registry<registry::LPPort>>();
    auto convexes = std::make_shared<registry::Registry<registry::ConvexPort>>();
    const registry::Method pm{projection.identity.id, {}}, am{affine.identity.id, {}},
        cm{converter.identity.id, {}}, lm{lp.identity.id, {}}, qm{convex.identity.id, {}};
    REQUIRE_FALSE(projections->add(projection));
    REQUIRE_FALSE(affines->add(affine));
    REQUIRE_FALSE(conversions->add(converter));
    REQUIRE_FALSE(lps->add(lp));
    REQUIRE_FALSE(convexes->add(convex));
    registry::Requirements h, v, program;
    h.output.representation = {"csl.polyhedron.h"};
    h.output.relation = SetRelation::equivalent;
    v.output.representation = {"csl.polyhedron.v"};
    v.output.relation = SetRelation::equivalent;
    program.output.representation = {"csl.program-result.v1"};
    auto providers = take(registry::check_providers(
        registry::select_provider(*projections, pm, h), registry::select_provider(*affines, am, v),
        registry::select_provider(*conversions, cm, h), registry::select_provider(*lps, lm, program),
        registry::select_provider(*convexes, qm, program)));
    auto membership = take(registry::prepare_provider(registry::select_provider(*lps, lm, program)));
    Modules result{std::move(projections), std::move(affines), std::move(conversions),
        std::move(lps), std::move(convexes), std::move(membership)};
    REQUIRE_FALSE(result.strategies.add(synthesis::strategy_a::make_registration(std::move(providers))));
    REQUIRE_FALSE(result.strategies.add(synthesis::strategy_b::make_registration(*result.lps, *result.convexes)));
    auto selector = synthesis::witness_selector::make_registration(result.membership);
    REQUIRE_FALSE(result.selectors.add(std::move(selector)));
    return result;
}

application::ComparisonRequest request_for(const problem::ResolvedProblem& problem,
    std::string profile) {
    FamilyRequest family;
    family.profile = std::move(profile);
    family.objective = problem.identity();
    family.target = FamilyTarget::exact_optimal_relation;
    family.assurance = Assurance::numerical;
    family.representation = {"csl.polyhedron.h"};
    StrategyConfiguration reach_back;
    reach_back.strategy = {"csl.synthesis.reach-back"};
    reach_back.lp = {"csl.lp.highs"};
    reach_back.convex = {"csl.convex.highs"};
    reach_back.representation = family.representation;
    StrategyConfiguration direct_joint = reach_back;
    direct_joint.strategy = {"csl.synthesis.strategy-b"};
    return {problem, family, {reach_back, direct_joint}};
}

csl::artifacts::RecordedRunArtifact check_complete_family_encoder_boundary(const problem::ResolvedProblem& problem,
    const application::PreparedComparison& prepared, const application::StrategyExecution& strategy_execution,
    std::size_t strategy_index, const WitnessRequest& witnesses, bool instrumentation_enabled=false) {
    namespace ar = artifacts;
    namespace ob = csl::execution::observability;
    const auto& synthesis_result = std::get<SynthesisResult>(strategy_execution.outcome);
    REQUIRE(synthesis_result.family);
    const auto expected = prepared.expected_synthesis_identity(strategy_index);
    const ar::Unavailable uninstrumented{ar::MissingReason::not_instrumented, {}};
    const ar::PinAvailability pin = uninstrumented;
    ar::ConfigurationInput input;
    input.collection = {instrumentation_enabled, ar::CollectionMode::detail, 5, 10000, 0, 0};
    input.modules = {
        {"strategy", {expected.strategy, expected.strategy_version, pin}, {}},
        {"lp", {prepared.strategies()[strategy_index].lp, "1", pin}, {}},
        {"convex", {prepared.strategies()[strategy_index].convex, "1", pin}, {}}};
    input.numerical = prepared.family().numerical;
    input.resources = {1, 1, 1, {}};
    input.output = {ar::OutputKind::synthesis, prepared.family().assurance,
        prepared.family().target, prepared.family().representation, witnesses};
    input.selector = {{csl::synthesis::witness_selector::selector_id}, "1", {}};
    input.strategy = prepared.strategies()[strategy_index];
    input.strategy.selector = input.selector.id;
    const auto configuration = take_artifact(ar::resolve_configuration(std::move(input)),
        "resolve_configuration");
    CHECK(configuration.description().strategy.selector == configuration.description().selector.id);
    const ar::RunId run{"application-comparison-encoder-"+std::to_string(strategy_index)+
        (instrumentation_enabled?"-instrumented":"-uninstrumented")};
    const auto plan = take_artifact(ob::make_collection_plan({problem, configuration, run, {}, {}, 0}),
        "make_collection_plan");
    const auto statistics = take_artifact(ob::merge_observations(plan, {}), "merge_observations");
    const auto encoded = application::encode_strategy_run(problem, strategy_execution,
        configuration, run, statistics,
        {uninstrumented, uninstrumented, uninstrumented, uninstrumented, true,
            ar::MemoryAccounting::unlimited});
    REQUIRE(std::holds_alternative<std::string>(encoded));
    const auto& wire=std::get<std::string>(encoded);
    CHECK(wire.find("csl.run-statistics/6")!=std::string::npos);
    CHECK(wire.find("unverified_recorded_data")!=std::string::npos);
    CHECK(wire.find("csl.h-relation-attachment/1")!=std::string::npos);
    const auto outer = nlohmann::json::parse(wire);
    const auto attachment = std::find_if(outer.at("attachments").begin(), outer.at("attachments").end(),
        [](const auto& value) { return value.at("schema") == "csl.trajectory-verification-reports/1"; });
    REQUIRE(attachment != outer.at("attachments").end());
    const auto& hex = attachment->at("content").get_ref<const std::string&>();
    REQUIRE(hex.size() % 2 == 0);
    std::string report_text;
    report_text.reserve(hex.size() / 2);
    const auto digit = [](char value) -> unsigned {
        if (value >= '0' && value <= '9') return static_cast<unsigned>(value - '0');
        return static_cast<unsigned>(value - 'a' + 10);
    };
    for (std::size_t i = 0; i < hex.size(); i += 2)
        report_text.push_back(static_cast<char>((digit(hex[i]) << 4) | digit(hex[i + 1])));
    const auto report_document = nlohmann::json::parse(report_text);
    CHECK(report_document.at("schema") == "csl.trajectory-verification-reports/1");
    REQUIRE(report_document.at("reports").size() == strategy_execution.verification.size());
    CHECK(report_document.at("reports").at(0).at("bindings") == "numerical_pass");
    CHECK(report_document.at("reports").at(0).at("feasibility") == "numerical_pass");
    CHECK(report_document.at("reports").at(0).at("objective") == "numerical_pass");
    CHECK(report_document.at("reports").at(0).at("optimality") == "unsupported");
    CHECK(report_document.at("reports").at(0).at("witness_index") == 0);
    const auto& saved_request = report_document.at("reports").at(0).at("request");
    CHECK(saved_request.at("outcome").at("value") == "optimal");
    CHECK(saved_request.at("family_identity").at("strategy") ==
        strategy_execution.verification.at(0).input.expected_synthesis->strategy.value);
    CHECK(saved_request.at("expected_synthesis").at("lineage").size() > 0);
    CHECK(saved_request.at("bounds").contains("lower"));
    CHECK(saved_request.at("bounds").contains("upper"));
    auto mismatched_execution = strategy_execution;
    REQUIRE(mismatched_execution.verification.at(0).input.expected_synthesis);
    mismatched_execution.verification.at(0).input.expected_synthesis->request.profile = "wrong-family-profile";
    const auto mismatched_artifact = application::encode_strategy_run(problem, mismatched_execution,
        configuration, run, statistics,
        {uninstrumented, uninstrumented, uninstrumented, uninstrumented, true,
            ar::MemoryAccounting::unlimited});
    REQUIRE(std::holds_alternative<ar::ArtifactError>(mismatched_artifact));
    CHECK(std::get<ar::ArtifactError>(mismatched_artifact).path == "run.verification[0].context");
    auto partial_execution=strategy_execution;
    auto partial_selection=std::get<WitnessSelection>(partial_execution.selection);
    partial_selection.batch.witnesses.resize(1);
    partial_selection.termination=Termination::operation_rejected;
    partial_selection.diagnostics="The second direction query failed; this is a partial batch.";
    partial_execution.selection=std::move(partial_selection);
    partial_execution.verification.clear();
    const auto partial_encoded=application::encode_strategy_run(problem,partial_execution,
        configuration,run,statistics,
        {uninstrumented,uninstrumented,uninstrumented,uninstrumented,true,
            ar::MemoryAccounting::unlimited});
    REQUIRE(std::holds_alternative<std::string>(partial_encoded));
    CHECK(wire.find("registered_verifier")!=std::string::npos);
    static_assert(!std::is_convertible_v<ar::RecordedRunArtifact,ar::RunStatistics>);
    const auto imported=take_artifact(ar::decode_recorded_run(wire,problem),"decode_recorded_run");
    CHECK(imported.content().bytes().size()==wire.size());
    CHECK(std::equal(imported.content().bytes().begin(), imported.content().bytes().end(),
        reinterpret_cast<const std::byte*>(wire.data())));
    const auto other_profile=prepared.family().profile=="ts01_exact_integrator"
        ?"ts02_constant_integrator":"ts01_exact_integrator";
    const auto problem_mismatch=ar::decode_recorded_run(wire,source(other_profile));
    REQUIRE(std::holds_alternative<ar::ArtifactError>(problem_mismatch));
    CHECK(std::get<ar::ArtifactError>(problem_mismatch).path=="run.problem");
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(wire)));
    auto trailing=wire+" ";
    const auto trailing_result=ar::decode_recorded_run(trailing);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(trailing_result));
    CHECK(std::get<ar::ArtifactError>(trailing_result).path=="recorded.canonical");
    auto self_asserted=wire;
    const auto state=self_asserted.find("unverified_recorded_data");
    REQUIRE(state!=std::string::npos);
    self_asserted.replace(state,std::string_view("unverified_recorded_data").size(),"registry_verified");
    const auto state_result=ar::decode_recorded_run(self_asserted);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(state_result));
    CHECK(std::get<ar::ArtifactError>(state_result).path=="recorded_state");
    return imported;
}

void compare_profile(const std::string& profile) {
    namespace ar=artifacts;
    const auto problem = source(profile);
    const auto request = request_for(problem, profile);
    auto registered = modules();
    auto admission = application::prepare_comparison(request, registered.strategies);
    REQUIRE(std::holds_alternative<application::PreparedComparison>(admission));
    const auto& prepared = std::get<application::PreparedComparison>(admission);
    registry::Requirements selection_requirements;
    selection_requirements.output.representation = {"csl.witness-batch.v1"};
    const WitnessRequest witness_request{2, 0, {{1, -1}, {-1, 1}}, 31};
    ExecutionContext context;
    context.numerical = request.family.numerical;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    const auto execution = application::run_comparison(prepared, registered.selectors,
        {synthesis::witness_selector::selector_id, {}}, witness_request, selection_requirements,
        context, registered.membership);

    for (std::size_t i = 0; i < execution.strategies.size(); ++i) {
        const auto& strategy = execution.strategies[i];
        REQUIRE(std::holds_alternative<SynthesisResult>(strategy.outcome));
        const auto& result = std::get<SynthesisResult>(strategy.outcome);
        REQUIRE(result.family);
        CHECK(result.family->registry_verified());
        REQUIRE(std::holds_alternative<CompleteOptimalFamily>(result.family->outcome()));
        REQUIRE(std::holds_alternative<WitnessSelection>(strategy.selection));
        const auto& selected = std::get<WitnessSelection>(strategy.selection);
        REQUIRE(selected.batch.returned_count() == 2);
        REQUIRE(selected.batch.source_family == result.family->identity());
        const double expected_objective = profile == "ts02_constant_integrator" ? 3.0 : 0.0;
        for (const auto& witness : selected.batch.witnesses) {
            check_full_dynamics(problem, witness);
            REQUIRE(witness.controls.size() == 2);
            REQUIRE(witness.states.size() == 3);
            const auto u0 = witness.controls[0][0];
            const auto u1 = witness.controls[1][0];
            CHECK(u0 >= -1e-9); CHECK(u0 <= 1.0 + 1e-9);
            CHECK(u1 >= -1e-9); CHECK(u1 <= 1.0 + 1e-9);
            if (profile == "ts01_exact_integrator") CHECK(u0 + u1 == doctest::Approx(1.0));
            if (profile == "ts03_singular_integrator") CHECK(u1 == doctest::Approx(1.0));
            if (profile != "ts02_constant_integrator")
                CHECK(witness.states[2][0] == doctest::Approx(1.0));
            CHECK(witness.original_objective == doctest::Approx(expected_objective));
        }
        REQUIRE(strategy.verification.size() == selected.batch.witnesses.size());
        const auto expected = prepared.expected_synthesis_identity(i);
        REQUIRE(expected.lineage);
        for (std::size_t j = 0; j < strategy.verification.size(); ++j) {
            const auto& report = strategy.verification[j];
            CHECK(report.input.expected_synthesis);
            CHECK(report.input.expected_synthesis->request == expected.request);
            CHECK(report.input.expected_synthesis->strategy == expected.strategy);
            CHECK(report.input.expected_synthesis->strategy_version == expected.strategy_version);
            CHECK(report.input.expected_synthesis->lineage == *expected.lineage);
            CHECK(report.bindings == verification::CheckStatus::numerical_pass);
            CHECK(report.feasibility == verification::CheckStatus::numerical_pass);
            CHECK(report.objective == verification::CheckStatus::numerical_pass);
            CHECK(report.optimality == verification::CheckStatus::unsupported);
            CHECK(report.completeness == verification::CheckStatus::unsupported);
            CHECK(report.validated == verification::CheckStatus::unsupported);
        }
    }
    if (profile == "ts01_exact_integrator") {
        // This history is stagewise feasible: u0=u1=0.75 obeys both control
        // boxes and x1=u0, x2=x1+u1. It is outside the global optimum relation,
        // which requires x2=1 and u0+u1=1. Both paired strategies must retain
        // the coupled history set rather than a Cartesian product of stages.
        const Vector cross_stage_cartesian_history{0, 0.75, 1.5, 0.75, 0.75};
        for (const auto& strategy : execution.strategies) {
            const auto& synthesis = std::get<SynthesisResult>(strategy.outcome);
            REQUIRE(synthesis.family);
            CHECK(family_contains_history(*synthesis.family, {0, 0, 1, 0, 1}));
            CHECK(family_contains_history(*synthesis.family, {0, 1, 1, 1, 0}));
            CHECK_FALSE(family_contains_history(*synthesis.family, cross_stage_cartesian_history));
        }
    }
    auto run_a=check_complete_family_encoder_boundary(problem, prepared, execution.strategies[0],
        0, witness_request);
    auto run_b=check_complete_family_encoder_boundary(problem, prepared, execution.strategies[1],
        1, witness_request);
    const auto request_a=take_artifact(ar::comparison_request_digest(run_a),"comparison_request_digest A");
    const auto request_b=take_artifact(ar::comparison_request_digest(run_b),"comparison_request_digest B");
    REQUIRE(request_a==request_b);
    const auto config_a=take_artifact(ar::comparison_configuration_id(run_a),"comparison_configuration_id A");
    const auto config_b=take_artifact(ar::comparison_configuration_id(run_b),"comparison_configuration_id B");
    const auto request_digest=csl::problem::hex(request_a);
    std::string spec_text="{\"problem_id\":\"";
    spec_text+=problem.identity().value;
    spec_text+="\",\"repetitions\":1,\"request_digest\":\"";
    spec_text+=request_digest;
    spec_text+="\",\"schema\":\"csl.comparison-spec/1\",\"strategies\":[\"";
    spec_text+=config_a.value;
    spec_text+="\",\"";
    spec_text+=config_b.value;
    spec_text+="\"]}";
    const auto spec_result=csl::problem::snapshot_content(
        std::span<const std::byte>{reinterpret_cast<const std::byte*>(spec_text.data()),spec_text.size()});
    REQUIRE_MESSAGE(std::holds_alternative<csl::problem::ResolvedContent>(spec_result),
        std::get<csl::Diagnostic>(spec_result).explanation);
    const auto spec=std::get<csl::problem::ResolvedContent>(spec_result);
    const std::vector<ar::ComparisonAttempt> attempts{
        {0,0,ar::AttemptStatus::completed,{ar::RunId{"application-comparison-encoder-0-uninstrumented"},run_a.content().digest()},run_a},
        {1,0,ar::AttemptStatus::completed,{ar::RunId{"application-comparison-encoder-1-uninstrumented"},run_b.content().digest()},run_b}};
    const auto bundle=take_artifact(ar::encode_recorded_comparison(spec,attempts),"encode_recorded_comparison");
    auto mislabeled=attempts;
    mislabeled.front().reported_status=ar::AttemptStatus::failed;
    const auto status_mismatch=ar::encode_recorded_comparison(spec,mislabeled);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(status_mismatch));
    CHECK(std::get<ar::ArtifactError>(status_mismatch).code==ar::ArtifactErrorCode::identity);
    mislabeled.front().reported_status=ar::AttemptStatus::unsupported;
    const auto unsupported_mismatch=ar::encode_recorded_comparison(spec,mislabeled);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(unsupported_mismatch));
    CHECK(std::get<ar::ArtifactError>(unsupported_mismatch).code==ar::ArtifactErrorCode::identity);
    const auto bundle_wire=std::string(reinterpret_cast<const char*>(bundle.content().bytes().data()),bundle.content().bytes().size());
    const auto restored_bundle=take_artifact(ar::decode_recorded_comparison(bundle_wire),"decode_recorded_comparison");
    CHECK(restored_bundle.content().digest()==bundle.content().digest());
    CHECK(restored_bundle.spec_id().digest==spec.digest());
    CHECK(restored_bundle.identity().digest==bundle.content().digest());
    CHECK(bundle_wire.find("csl.comparison/1")!=std::string::npos);
    CHECK(bundle_wire.find("csl.run-statistics/6")!=std::string::npos);

    auto run_a_enabled=check_complete_family_encoder_boundary(problem,prepared,execution.strategies[0],
        0,witness_request,true);
    const auto config_a_enabled=take_artifact(ar::comparison_configuration_id(run_a_enabled),
        "comparison_configuration_id enabled A");
    const auto request_a_enabled=take_artifact(ar::comparison_request_digest(run_a_enabled),
        "comparison_request_digest enabled A");
    REQUIRE(request_a_enabled==request_a);
    const auto canonical_problem=problem.canonical_bytes();
    const auto manifest_bytes=std::span<const std::byte>{canonical_problem};
    const auto input_manifest_hash=csl::problem::hex(take(csl::problem::snapshot_content(manifest_bytes)).digest());
    const std::string record_spec_text="{\"arms\":[{\"configuration_id\":\""+config_a.value+
        "\",\"instrumentation\":\"disabled\",\"strategy\":\"csl.synthesis.reach-back\"},{\"configuration_id\":\""+
        config_a_enabled.value+"\",\"instrumentation\":\"enabled\",\"strategy\":\"csl.synthesis.reach-back\"}],\"input_manifest_hash\":\""+input_manifest_hash+
        "\",\"input_manifest_source\":\"resolved-problem-canonical-bytes\""+
        ",\"problem_id\":\""+problem.identity().value+"\",\"repetitions\":1,\"request_digest\":\""+request_digest+
        "\",\"schema\":\"csl.comparison-spec/2\"}";
    const auto record_spec_result=csl::problem::snapshot_content(
        std::span<const std::byte>{reinterpret_cast<const std::byte*>(record_spec_text.data()),record_spec_text.size()});
    REQUIRE(std::holds_alternative<csl::problem::ResolvedContent>(record_spec_result));
    const auto record_spec=std::get<csl::problem::ResolvedContent>(record_spec_result);
    const std::vector<ar::ComparisonAttempt> measured_attempts{
        {0,0,ar::AttemptStatus::completed,{ar::RunId{"application-comparison-encoder-0-uninstrumented"},run_a.content().digest()},run_a,
            "{\"schema\":\"csl.obs04-instrumentation-comparison-event/2\",\"repetition\":0,\"warmup\":true,\"status\":\"passed\",\"strategy\":\"csl.synthesis.reach-back\",\"instrumentation\":\"disabled\"}"},
        {1,0,ar::AttemptStatus::completed,{ar::RunId{"application-comparison-encoder-0-instrumented"},run_a_enabled.content().digest()},run_a_enabled,
            "{\"schema\":\"csl.obs04-instrumentation-comparison-event/2\",\"repetition\":0,\"warmup\":true,\"status\":\"passed\",\"strategy\":\"csl.synthesis.reach-back\",\"instrumentation\":\"enabled\"}"}};
    const auto recorded=take_artifact(ar::encode_recorded_comparison(record_spec,measured_attempts),
        "encode_recorded_comparison comparison-record/1");
    const auto record_wire=std::string(reinterpret_cast<const char*>(recorded.content().bytes().data()),
        recorded.content().bytes().size());
    CHECK(record_wire.find("csl.comparison-record/1")!=std::string::npos);
    const auto restored_record=take_artifact(ar::decode_recorded_comparison(record_wire),
        "decode_recorded_comparison comparison-record/1");
    CHECK(restored_record.content().digest()==recorded.content().digest());
    CHECK(restored_record.identity().digest==recorded.identity().digest);
    CHECK(record_wire.find(csl::problem::hex(recorded.identity().digest))!=std::string::npos);
    std::string escaped_measurement;
    for(const char character:measured_attempts.front().measurement_payload) {
        if(character=='"'||character=='\\')escaped_measurement.push_back('\\');
        escaped_measurement.push_back(character);
    }
    CHECK(record_wire.find(escaped_measurement)!=std::string::npos);
    auto version_three_spec_json=nlohmann::json::parse(record_spec_text);
    version_three_spec_json["environment"]=sample_obs04_environment();
    version_three_spec_json["schema"]="csl.comparison-spec/3";
    const auto version_three_spec_text=version_three_spec_json.dump();
    const auto version_three_spec_owner=csl::problem::snapshot_content(
        std::span<const std::byte>{reinterpret_cast<const std::byte*>(version_three_spec_text.data()),
            version_three_spec_text.size()});
    REQUIRE(std::holds_alternative<csl::problem::ResolvedContent>(version_three_spec_owner));
    const auto version_three_spec=std::get<csl::problem::ResolvedContent>(version_three_spec_owner);
    const auto version_three=take_artifact(ar::encode_recorded_comparison(version_three_spec,measured_attempts),
        "encode_recorded_comparison comparison-spec/3");
    const auto version_three_wire=std::string(reinterpret_cast<const char*>(version_three.content().bytes().data()),
        version_three.content().bytes().size());
    const auto version_three_replay=take_artifact(ar::decode_recorded_comparison(version_three_wire),
        "decode_recorded_comparison comparison-spec/3");
    CHECK(version_three_replay.content().digest()==version_three.content().digest());
    CHECK(version_three_replay.spec_id().digest==version_three_spec.digest());
    CHECK(version_three_replay.identity().digest==version_three.identity().digest);
    const auto& witness_batch=std::get<WitnessSelection>(execution.strategies[0].selection).batch;
    CHECK(witness_batch.distinct_count()==2);
    const auto v3_measurement=[&](std::string instrumentation) {
        return nlohmann::json{{"schema","csl.obs04-instrumentation-comparison-event/3"},
            {"repetition",0},{"warmup",true},{"status","passed"},
            {"strategy","csl.synthesis.reach-back"},{"instrumentation",std::move(instrumentation)},
            {"selection_setup_ns",1},{"selection_run_ns",2},{"verification_ns",3},
            {"requested_witness_count",witness_batch.requested},
            {"returned_witness_count",witness_batch.returned_count()},
            {"distinct_witness_count",witness_batch.distinct_count()}}.dump();
    };
    std::vector<ar::ComparisonAttempt> measured_attempts_v3{
        {0,0,ar::AttemptStatus::completed,
            {ar::RunId{"application-comparison-encoder-0-uninstrumented"},run_a.content().digest()},
            run_a,v3_measurement("disabled")},
        {1,0,ar::AttemptStatus::completed,
            {ar::RunId{"application-comparison-encoder-0-instrumented"},run_a_enabled.content().digest()},
            run_a_enabled,v3_measurement("enabled")}};
    const auto recorded_v3=take_artifact(ar::encode_recorded_comparison(
        version_three_spec,measured_attempts_v3),"encode_recorded_comparison event/3");
    const auto recorded_v3_wire=std::string(
        reinterpret_cast<const char*>(recorded_v3.content().bytes().data()),
        recorded_v3.content().bytes().size());
    const auto restored_v3=take_artifact(ar::decode_recorded_comparison(recorded_v3_wire),
        "decode_recorded_comparison event/3");
    CHECK(restored_v3.content().digest()==recorded_v3.content().digest());
    auto bad_witness_counts=measured_attempts_v3;
    auto bad_measurement=nlohmann::json::parse(bad_witness_counts.front().measurement_payload);
    bad_measurement["returned_witness_count"]=1;
    bad_witness_counts.front().measurement_payload=bad_measurement.dump();
    const auto count_mismatch=ar::encode_recorded_comparison(version_three_spec,bad_witness_counts);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(count_mismatch));
    CHECK(std::get<ar::ArtifactError>(count_mismatch).path=="attempts[0].measurement_payload.status");
    auto measured_attempts_v4=measured_attempts_v3;
    for(auto& attempt:measured_attempts_v4) {
        auto measurement=nlohmann::json::parse(attempt.measurement_payload);
        measurement["schema"]="csl.obs04-instrumentation-comparison-event/4";
        measurement["strategy_run_ns"]=2;
        measurement["family_construction_ns"]=2;
        measurement["end_to_end_ns"]=30;
        measurement["selection_run_ns"]=20;
        measurement["first_witness_query_ns"]=3;
        measurement["additional_witness_query_ns"]=4;
        attempt.measurement_payload=measurement.dump();
    }
    const auto recorded_v4=take_artifact(ar::encode_recorded_comparison(
        version_three_spec,measured_attempts_v4),"encode_recorded_comparison event/4");
    const auto recorded_v4_wire=std::string(
        reinterpret_cast<const char*>(recorded_v4.content().bytes().data()),
        recorded_v4.content().bytes().size());
    const auto restored_v4=take_artifact(ar::decode_recorded_comparison(recorded_v4_wire),
        "decode_recorded_comparison event/4");
    CHECK(restored_v4.content().digest()==recorded_v4.content().digest());
    auto measured_attempts_v5=measured_attempts_v3;
    for(auto& attempt:measured_attempts_v5) {
        auto measurement=nlohmann::json::parse(attempt.measurement_payload);
        measurement["schema"]="csl.obs04-instrumentation-comparison-event/5";
        measurement["setup_ns"]=1;
        measurement["strategy_run_ns"]=2;
        measurement["family_construction_ns"]=nullptr;
        measurement["end_to_end_ns"]=30;
        measurement["selection_setup_ns"]=1;
        measurement["selection_run_ns"]=20;
        measurement["verification_ns"]=3;
        measurement["first_witness_query_ns"]=3;
        measurement["additional_witness_query_ns"]=4;
        attempt.measurement_payload=measurement.dump();
    }
    const auto recorded_v5=take_artifact(ar::encode_recorded_comparison(
        version_three_spec,measured_attempts_v5),"encode_recorded_comparison event/5");
    const auto recorded_v5_wire=std::string(
        reinterpret_cast<const char*>(recorded_v5.content().bytes().data()),
        recorded_v5.content().bytes().size());
    const auto restored_v5=take_artifact(ar::decode_recorded_comparison(recorded_v5_wire),
        "decode_recorded_comparison event/5");
    CHECK(restored_v5.content().digest()==recorded_v5.content().digest());
    auto measured_attempts_v6=measured_attempts_v5;
    for(auto& attempt:measured_attempts_v6) {
        auto measurement=nlohmann::json::parse(attempt.measurement_payload);
        measurement["schema"]="csl.obs04-instrumentation-comparison-event/6";
        measurement["phase_status"]="failed";
        attempt.measurement_payload=measurement.dump();
    }
    const auto recorded_v6=take_artifact(ar::encode_recorded_comparison(
        version_three_spec,measured_attempts_v6),"encode_recorded_comparison event/6");
    const auto recorded_v6_wire=std::string(
        reinterpret_cast<const char*>(recorded_v6.content().bytes().data()),
        recorded_v6.content().bytes().size());
    const auto restored_v6=take_artifact(ar::decode_recorded_comparison(recorded_v6_wire),
        "decode_recorded_comparison event/6");
    CHECK(restored_v6.content().digest()==recorded_v6.content().digest());
    auto measured_attempts_v7=measured_attempts_v6;
    for(auto& attempt:measured_attempts_v7) {
        auto measurement=nlohmann::json::parse(attempt.measurement_payload);
        measurement["schema"]="csl.obs04-instrumentation-comparison-event/7";
        if(measurement["instrumentation"]=="enabled")measurement["family_construction_ns"]=5;
        else measurement["family_construction_ns"]=nullptr;
        attempt.measurement_payload=measurement.dump();
    }
    const auto recorded_v7=take_artifact(ar::encode_recorded_comparison(
        version_three_spec,measured_attempts_v7),"encode_recorded_comparison event/7");
    const auto recorded_v7_wire=std::string(
        reinterpret_cast<const char*>(recorded_v7.content().bytes().data()),
        recorded_v7.content().bytes().size());
    const auto restored_v7=take_artifact(ar::decode_recorded_comparison(recorded_v7_wire),
        "decode_recorded_comparison event/7");
    CHECK(restored_v7.content().digest()==recorded_v7.content().digest());
    auto measured_attempts_v8=measured_attempts_v7;
    for(auto& attempt:measured_attempts_v8) {
        auto measurement=nlohmann::json::parse(attempt.measurement_payload);
        measurement["schema"]="csl.obs04-instrumentation-comparison-event/8";
        measurement["strategy_run_cpu_ns"]=1;
        measurement["observed_backend_scheduler_width"]=1;
        attempt.measurement_payload=measurement.dump();
    }
    const auto recorded_v8=take_artifact(ar::encode_recorded_comparison(
        version_three_spec,measured_attempts_v8),"encode_recorded_comparison event/8");
    const auto recorded_v8_wire=std::string(
        reinterpret_cast<const char*>(recorded_v8.content().bytes().data()),
        recorded_v8.content().bytes().size());
    const auto restored_v8=take_artifact(ar::decode_recorded_comparison(recorded_v8_wire),
        "decode_recorded_comparison event/8");
    CHECK(restored_v8.content().digest()==recorded_v8.content().digest());
    auto zero_scheduler_width=measured_attempts_v8;
    auto zero_width_measurement=nlohmann::json::parse(
        zero_scheduler_width.front().measurement_payload);
    zero_width_measurement["observed_backend_scheduler_width"]=0;
    zero_scheduler_width.front().measurement_payload=zero_width_measurement.dump();
    const auto zero_width=ar::encode_recorded_comparison(version_three_spec,zero_scheduler_width);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(zero_width));
    auto negative_family_timing=measured_attempts_v7;
    auto negative_family_measurement=nlohmann::json::parse(
        negative_family_timing.front().measurement_payload);
    negative_family_measurement["family_construction_ns"]=-1;
    negative_family_timing.front().measurement_payload=negative_family_measurement.dump();
    const auto negative_family=ar::encode_recorded_comparison(version_three_spec,negative_family_timing);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(negative_family));
    auto missing_family_timing=measured_attempts_v7;
    auto missing_family_measurement=nlohmann::json::parse(
        missing_family_timing.at(1).measurement_payload);
    missing_family_measurement["family_construction_ns"]=nullptr;
    missing_family_timing.at(1).measurement_payload=missing_family_measurement.dump();
    const auto missing_family=ar::encode_recorded_comparison(version_three_spec,missing_family_timing);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(missing_family));
    auto missing_query_timing=measured_attempts_v4;
    auto missing_query_measurement=nlohmann::json::parse(missing_query_timing.front().measurement_payload);
    missing_query_measurement["additional_witness_query_ns"]=nullptr;
    missing_query_timing.front().measurement_payload=missing_query_measurement.dump();
    const auto missing_query=ar::encode_recorded_comparison(version_three_spec,missing_query_timing);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(missing_query));
    CHECK(std::get<ar::ArtifactError>(missing_query).path=="attempts[0].measurement_payload.status");
    auto missing_v5_query_timing=measured_attempts_v6;
    auto missing_v5_query_measurement=nlohmann::json::parse(
        missing_v5_query_timing.front().measurement_payload);
    missing_v5_query_measurement["first_witness_query_ns"]=nullptr;
    missing_v5_query_timing.front().measurement_payload=missing_v5_query_measurement.dump();
    const auto missing_v5_query=ar::encode_recorded_comparison(
        version_three_spec,missing_v5_query_timing);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(missing_v5_query));
    CHECK(std::get<ar::ArtifactError>(missing_v5_query).path==
        "attempts[0].measurement_payload.status");
    auto impossible_query_timing=measured_attempts_v6;
    auto impossible_query=nlohmann::json::parse(impossible_query_timing.front().measurement_payload);
    impossible_query["selection_run_ns"]=6;
    impossible_query_timing.front().measurement_payload=impossible_query.dump();
    const auto impossible_query_result=ar::encode_recorded_comparison(
        version_three_spec,impossible_query_timing);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(impossible_query_result));
    CHECK(std::get<ar::ArtifactError>(impossible_query_result).path==
        "attempts[0].measurement_payload.status");
    auto impossible_end_to_end=measured_attempts_v6;
    auto impossible_end_to_end_measurement=nlohmann::json::parse(
        impossible_end_to_end.front().measurement_payload);
    impossible_end_to_end_measurement["end_to_end_ns"]=26;
    impossible_end_to_end.front().measurement_payload=impossible_end_to_end_measurement.dump();
    const auto impossible_end_to_end_result=ar::encode_recorded_comparison(
        version_three_spec,impossible_end_to_end);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(impossible_end_to_end_result));
    CHECK(std::get<ar::ArtifactError>(impossible_end_to_end_result).path==
        "attempts[0].measurement_payload.status");
    auto bad_distinct_count=measured_attempts_v3;
    auto bad_distinct_measurement=nlohmann::json::parse(bad_distinct_count.front().measurement_payload);
    bad_distinct_measurement["distinct_witness_count"]=1;
    bad_distinct_count.front().measurement_payload=bad_distinct_measurement.dump();
    const auto distinct_mismatch=ar::encode_recorded_comparison(version_three_spec,bad_distinct_count);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(distinct_mismatch));
    CHECK(std::get<ar::ArtifactError>(distinct_mismatch).path=="attempts[0].measurement_payload.status");
    auto missing_selection_timing=measured_attempts_v3;
    auto missing_timing_measurement=nlohmann::json::parse(missing_selection_timing.front().measurement_payload);
    missing_timing_measurement["verification_ns"]=nullptr;
    missing_selection_timing.front().measurement_payload=missing_timing_measurement.dump();
    const auto timing_mismatch=ar::encode_recorded_comparison(version_three_spec,missing_selection_timing);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(timing_mismatch));
    CHECK(std::get<ar::ArtifactError>(timing_mismatch).path=="attempts[0].measurement_payload.status");
    auto changed_environment_spec_json=version_three_spec_json;
    changed_environment_spec_json["environment"]["build"]["compiler_version"]="13.3.1";
    const auto changed_environment_text=changed_environment_spec_json.dump();
    const auto changed_environment_owner=csl::problem::snapshot_content(
        std::span<const std::byte>{reinterpret_cast<const std::byte*>(changed_environment_text.data()),
            changed_environment_text.size()});
    REQUIRE(std::holds_alternative<csl::problem::ResolvedContent>(changed_environment_owner));
    const auto changed_environment=take_artifact(ar::encode_recorded_comparison(
        std::get<csl::problem::ResolvedContent>(changed_environment_owner),measured_attempts),
        "encode changed comparison environment");
    CHECK(changed_environment.spec_id().digest!=version_three.spec_id().digest);
    CHECK(changed_environment.identity().digest!=version_three.identity().digest);
    auto tampered_version_three=nlohmann::json::parse(version_three_wire);
    auto tampered_version_three_spec=nlohmann::json::parse(tampered_version_three.at("spec").get<std::string>());
    tampered_version_three_spec["environment"]["build"]["compiler_version"]="tampered";
    tampered_version_three["spec"]=tampered_version_three_spec.dump();
    const auto tampered_version_three_result=ar::decode_recorded_comparison(tampered_version_three.dump());
    REQUIRE(std::holds_alternative<ar::ArtifactError>(tampered_version_three_result));
    auto malformed_environment_spec_json=version_three_spec_json;
    malformed_environment_spec_json["environment"]["runtime"]["cpu_model"]=
        {{"status","unavailable"}};
    const auto malformed_environment_text=malformed_environment_spec_json.dump();
    const auto malformed_environment_owner=csl::problem::snapshot_content(
        std::span<const std::byte>{reinterpret_cast<const std::byte*>(malformed_environment_text.data()),
            malformed_environment_text.size()});
    REQUIRE(std::holds_alternative<csl::problem::ResolvedContent>(malformed_environment_owner));
    const auto malformed_environment_result=ar::encode_recorded_comparison(
        std::get<csl::problem::ResolvedContent>(malformed_environment_owner),measured_attempts);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(malformed_environment_result));
    auto wrong_measurement=measured_attempts;
    wrong_measurement.front().measurement_payload="{\"status\":\"failed\"}";
    const auto wrong_measurement_result=ar::encode_recorded_comparison(record_spec,wrong_measurement);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(wrong_measurement_result));
    CHECK(std::get<ar::ArtifactError>(wrong_measurement_result).code==ar::ArtifactErrorCode::identity);
    auto wrong_arm_text=record_spec_text;
    const auto disabled_label=wrong_arm_text.find("disabled");
    REQUIRE(disabled_label!=std::string::npos);
    wrong_arm_text.replace(disabled_label,std::string_view("disabled").size(),"enabled");
    const auto wrong_arm_owner=csl::problem::snapshot_content(std::span<const std::byte>{
        reinterpret_cast<const std::byte*>(wrong_arm_text.data()),wrong_arm_text.size()});
    REQUIRE(std::holds_alternative<csl::problem::ResolvedContent>(wrong_arm_owner));
    const auto wrong_arm_result=ar::encode_recorded_comparison(
        std::get<csl::problem::ResolvedContent>(wrong_arm_owner),measured_attempts);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(wrong_arm_result));
    CHECK(std::get<ar::ArtifactError>(wrong_arm_result).code==ar::ArtifactErrorCode::identity);
}
}

TEST_CASE("application preparation retains provider registries after module assembly returns") {
    const auto problem = source("ts01_exact_integrator");
    auto request = request_for(problem, "ts01_exact_integrator");
    auto registered = modules();
    auto admission = application::prepare_comparison(request, registered.strategies);
    REQUIRE(std::holds_alternative<application::PreparedComparison>(admission));
    const auto& prepared = std::get<application::PreparedComparison>(admission);
    CHECK(prepared.problem().identity() == problem.identity());
    CHECK(prepared.strategies().size() == 2);
    const auto workspaces = prepared.create();
    CHECK(workspaces[0] != nullptr);
    CHECK(workspaces[1] != nullptr);
}
TEST_CASE("application composes and verifies paired T-S01 complete families") {
    compare_profile("ts01_exact_integrator");
}

TEST_CASE("application composes and verifies paired T-S02 complete families") {
    compare_profile("ts02_constant_integrator");
}

TEST_CASE("application compares T-S03 families by the analytic relation and verifies each full history") {
    compare_profile("ts03_singular_integrator");
}
