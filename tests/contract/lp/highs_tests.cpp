#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/lp/highs.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <csl/optimization/linear_infeasibility_certificate.hpp>
#include "../../../src/adapters/certificate_verification.hpp"
#include <barrier>
#include <future>
#include <limits>

using namespace csl;
using namespace csl::registry;
using namespace csl::optimization;
using namespace csl::adapters::lp;

namespace {
template<class T, class... Rest> T accepted(std::variant<T, Rest...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
LinearProgram triangle(double offset = 0) {
    return accepted(make_linear_program({{{"native-test"}, {offset == 0 ? "triangle" : "offset"}},
        {-1, -2}, offset, {1, 2, {0, 2}, {0, 1}, {1, 1}}, {{0, {}}, {0, {}}}, {{{}, 1}}}));
}
LinearProgram rhs_lp(std::string id,double rhs,std::optional<double> upper_x2 = {}) {
    return accepted(make_linear_program({{{"native-test"}, {std::move(id)}},
        {-1,-2},0,{1,2,{0,2},{0,1},{1,1}},{{0,{}},{0,upper_x2}},{{{},rhs}}}));
}
Requirements requirements() {
    Requirements request;
    request.output.representation = {"csl.program-result.v1"};
    return request;
}
auto prepare(const LinearProgram& program, HighsLPOptions options = {}) {
    Registry<LPPort> registry;
    REQUIRE_FALSE(registry.add(accepted(make_highs_registration(options))).has_value());
    return accepted(prepare_pipeline(select(registry, {{"csl.lp.highs"}, {}}, program, requirements())));
}
ExecutionContext context() { return {{}, {}, {}, {1e-8, 1e-8}, "native-test"}; }
void cost(const ProgramResult& result, const LinearProgram& program, double expected) {
    REQUIRE(result.primal.has_value());
    CHECK(accepted(evaluate_primal(program, *result.primal, {1e-8, 1e-8}, {{"test.oracle"}, "1"})).objective
          == doctest::Approx(expected));
    CHECK(check_program_result(result, program, Assurance::numerical).empty());
    CHECK(result.outcome.subject == program.identity());
    CHECK(std::holds_alternative<Unestablished>(result.outcome.support));
    CHECK_FALSE(result.objective.lower.has_value());
    CHECK_FALSE(result.objective.upper.has_value());
}
}

TEST_CASE("registered native triangle reports literal optimum and independent residuals") {
    const auto program = triangle();
    auto plan = prepare(program);
    CHECK(plan.provenance()[0].actual->version == "1.1.0+highs.1.11.0");
    auto [worker] = plan.create();
    CHECK(worker->basis() == nullptr);
    const auto result = accepted(worker->run(context()));
    INFO(result.raw_diagnostics);
    CHECK(result.termination == Termination::completed);
    CHECK(result.outcome.value == MathematicalOutcome::optimal);
    cost(result, program, -2);
    CHECK(result.raw_diagnostics.find(std::string("native.downstream.hvectorbase_sha256=")+CSL_HIGHS_PATCHED_SOURCE_SHA256) != std::string::npos);
    REQUIRE(result.primal->size() == 2);
    CHECK((*result.primal)[0] == 0);
    CHECK((*result.primal)[1] == 1);
    REQUIRE(result.residuals.primal.has_value());
    CHECK(result.residuals.primal->rows.violation == 0);
    CHECK(result.residuals.primal->variables.violation == 0);
    REQUIRE(result.residuals.dual.has_value());
    REQUIRE(result.residuals.dual->stationarity.has_value());
    REQUIRE(result.residuals.dual->signs.has_value());
    CHECK(result.residuals.dual->stationarity->violation == 0);
    CHECK(result.residuals.dual->signs->violation == 0);
    CHECK_FALSE(result.residuals.dual->complementarity.has_value());
    CHECK(result.raw_diagnostics.find("Model status") != std::string::npos);
    CHECK(result.raw_diagnostics.find("native.version=1.11.0") != std::string::npos);
    CHECK(result.raw_diagnostics.find("native.model_status=7") != std::string::npos);
}

TEST_CASE("cross-query warm starts are optional, workspace-local, dimension-checked and independently verified") {
    const auto first=rhs_lp("warm-first",1);
    const auto changed_row=rhs_lp("warm-row-change",2);
    const auto changed_bound=rhs_lp("warm-bound-change",2,1);
    const auto changed_columns=accepted(make_linear_program({{{"native-test"},{"warm-column-change"}},
        {-1,-2,-3},0,{1,3,{0,3},{0,1,2},{1,1,1}},{{0,{}},{0,{}},{0,{}}},{{{},2}}}));
    auto registration=accepted(make_highs_registration({.cross_query_warm_start=true}));
    auto warm=registration.factory(first);
    const auto cold=accepted(warm->solve(first,context()));
    CHECK(cold.outcome.value==MathematicalOutcome::optimal);
    cost(cold,first,-2);
    CHECK(cold.raw_diagnostics.find("warm_start.cache_state=empty")!=std::string::npos);
    const auto changed=accepted(warm->solve(changed_row,context()));
    INFO(changed.raw_diagnostics);
    CHECK(changed.outcome.value==MathematicalOutcome::optimal);
    cost(changed,changed_row,-4);
    CHECK(changed.raw_diagnostics.find("warm_start.cache_state=compatible")!=std::string::npos);
    CHECK(changed.raw_diagnostics.find("warm_start.accepted=true")!=std::string::npos);
    const auto bounded=accepted(warm->solve(changed_bound,context()));
    CHECK(bounded.outcome.value==MathematicalOutcome::optimal);
    cost(bounded,changed_bound,-3);
    const auto dimension_change=accepted(warm->solve(changed_columns,context()));
    CHECK(dimension_change.outcome.value==MathematicalOutcome::optimal);
    cost(dimension_change,changed_columns,-6);
    CHECK(dimension_change.raw_diagnostics.find("warm_start.cache_state=invalidated_dimension_change")!=std::string::npos);
    CHECK(dimension_change.raw_diagnostics.find("warm_start.fallback=cold_no_compatible_basis")!=std::string::npos);
    CHECK(dimension_change.raw_diagnostics.find("warm_start.setup_seconds=")!=std::string::npos);
    CHECK(dimension_change.raw_diagnostics.find("native.solve_seconds=")!=std::string::npos);

    auto other_workspace=registration.factory(first);
    const auto isolated=accepted(other_workspace->solve(first,context()));
    CHECK(isolated.raw_diagnostics.find("warm_start.cache_state=empty")!=std::string::npos);
    cost(isolated,first,-2);
}

TEST_CASE("warm starts fall back for a changed row dimension and retain exact infeasibility checks") {
    const auto feasible=rhs_lp("warm-feasible",2);
    const auto infeasible=accepted(make_linear_program({{{"native-test"},{"warm-infeasible"}},
        {0},0,{2,1,{0,1,2},{0,0},{1,1}},{{{},{}}},{{{},0},{1,{}}}}));
    auto registration=accepted(make_highs_registration({.cross_query_warm_start=true}));
    auto worker=registration.factory(feasible);
    cost(accepted(worker->solve(feasible,context())),feasible,-4);
    const auto result=accepted(worker->solve(infeasible,context()));
    CHECK(result.termination==Termination::completed);
    CHECK(result.outcome.value==MathematicalOutcome::infeasible);
    REQUIRE(std::holds_alternative<ExactFarkasEvidence>(result.outcome.support));
    CHECK(verify_linear_infeasibility_certificate(infeasible,std::get<ExactFarkasEvidence>(result.outcome.support).certificate()).index()==0);
    CHECK(result.raw_diagnostics.find("warm_start.cache_state=invalidated_dimension_change")!=std::string::npos);
    CHECK(result.raw_diagnostics.find("warm_start.next_cache=invalidated_after_result")!=std::string::npos);
}

TEST_CASE("warm starts preserve independently checked results across a degenerate basis") {
    const auto degenerate=accepted(make_linear_program({{{"native-test"},{"warm-degenerate"}},
        {-1},0,{2,1,{0,1,2},{0,0},{1,1}},{{0,{}}},{{{},1},{{},1}}}));
    const auto changed_rows=accepted(make_linear_program({{{"native-test"},{"warm-degenerate-rhs-change"}},
        {-1},0,{2,1,{0,1,2},{0,0},{1,1}},{{0,{}}},{{{},1},{{},0.5}}}));
    const auto infeasible=accepted(make_linear_program({{{"native-test"},{"warm-degenerate-infeasible"}},
        {-1},0,{2,1,{0,1,2},{0,0},{1,1}},{{0,{}}},{{{},1},{{},-1}}}));
    auto registration=accepted(make_highs_registration({.cross_query_warm_start=true}));
    auto worker=registration.factory(degenerate);
    const auto first=accepted(worker->solve(degenerate,context()));
    cost(first,degenerate,-1);
    const auto second=accepted(worker->solve(changed_rows,context()));
    INFO(second.raw_diagnostics);
    cost(second,changed_rows,-0.5);
    CHECK(second.raw_diagnostics.find("warm_start.cache_state=compatible")!=std::string::npos);
    CHECK(second.raw_diagnostics.find("warm_start.setup_seconds=")!=std::string::npos);
    CHECK(second.raw_diagnostics.find("native.load_seconds=")!=std::string::npos);
    CHECK(second.raw_diagnostics.find("native.solve_seconds=")!=std::string::npos);
    const auto infeasible_result=accepted(worker->solve(infeasible,context()));
    CHECK(infeasible_result.termination==Termination::completed);
    CHECK(infeasible_result.outcome.value==MathematicalOutcome::infeasible);
    REQUIRE(std::holds_alternative<ExactFarkasEvidence>(infeasible_result.outcome.support));
    CHECK(verify_linear_infeasibility_certificate(infeasible,std::get<ExactFarkasEvidence>(infeasible_result.outcome.support).certificate()).index()==0);
    CHECK(infeasible_result.raw_diagnostics.find("warm_start.cache_state=compatible")!=std::string::npos);
    CHECK(infeasible_result.raw_diagnostics.find("warm_start.accepted=true")!=std::string::npos);
    CHECK(infeasible_result.raw_diagnostics.find("warm_start.next_cache=invalidated_after_result")!=std::string::npos);
    CHECK(infeasible_result.raw_diagnostics.find("warm_start.fallback=cold_after_invalid_result")!=std::string::npos);
    CHECK(infeasible_result.raw_diagnostics.find("warm_start.retry=cold_after_invalid_result")!=std::string::npos);
    CHECK(infeasible_result.raw_diagnostics.find("warm_start.cache_state=empty")!=std::string::npos);
}

TEST_CASE("literal offset equality free fixed infeasible unbounded and zero-dimensional LPs") {
    const auto offset = triangle(7);
    auto [offset_worker] = prepare(offset).create();
    cost(accepted(offset_worker->run(context())), offset, 5);
    const auto equality = accepted(make_linear_program({{{"native-test"}, {"equality"}},
        {0,0}, 0, {2,2,{0,2,3},{0,1,1},{1,1,2}}, {{0,{}},{0,{}}}, {{1,1},{1,1}}}));
    auto [eq_worker] = prepare(equality).create();
    const auto eq = accepted(eq_worker->run(context()));
    cost(eq,equality,0);
    CHECK(*eq.primal == Vector{0.5,0.5});
    const auto fixed = accepted(make_linear_program({{{"native-test"},{"fixed"}},
        {1,-3},10,{2,2,{0,2,3},{0,1,0},{1,1,0}}, {{{},{}},{2,2}}, {{3,3},{{},{}}}}));
    auto [fixed_worker] = prepare(fixed).create();
    const auto fr = accepted(fixed_worker->run(context()));
    cost(fr,fixed,5);
    CHECK(*fr.primal == Vector{1,2});
    const auto infeasible = accepted(make_linear_program({{{"native-test"},{"infeasible"}},
        {0},0,{2,1,{0,1,2},{0,0},{1,1}}, {{{},{}}}, {{{},0},{1,{}}}}));
    auto [bad_worker] = prepare(infeasible).create();
    const auto bad = accepted(bad_worker->run(context()));
    CHECK(bad.termination == Termination::completed);
    CHECK(bad.outcome.value == MathematicalOutcome::infeasible);
    REQUIRE(std::holds_alternative<ExactFarkasEvidence>(bad.outcome.support));
    const auto& proof = std::get<ExactFarkasEvidence>(bad.outcome.support);
    CHECK(proof.subject() == infeasible.identity());
    CHECK(verify_linear_infeasibility_certificate(infeasible,proof.certificate()).index() == 0);
    CHECK_FALSE(bad.objective.lower);
    const auto unbounded = accepted(make_linear_program({{{"native-test"},{"unbounded"}},
        {-1},0,{0,1,{0},{},{}},{{0,{}}},{}}));
    auto [unbounded_worker] = prepare(unbounded).create();
    const auto ur = accepted(unbounded_worker->run(context()));
    CHECK(ur.termination == Termination::completed);
    CHECK(ur.outcome.value == MathematicalOutcome::unbounded);
    CHECK_FALSE(ur.objective.lower);
    for (const bool contradiction : {false,true}) {
        const auto zero = accepted(make_linear_program({{{"native-test"},{contradiction ? "zero-bad" : "zero-eq"}},
            {},7,{1,0,{0,0},{},{}},{},{{contradiction ? 1.0 : 0.0,contradiction ? std::optional<double>{} : 0.0}}}));
        auto [worker] = prepare(zero).create();
        const auto result = accepted(worker->run(context()));
        CHECK(result.outcome.value == (contradiction ? MathematicalOutcome::infeasible : MathematicalOutcome::optimal));
        CHECK(result.raw_diagnostics.find("native_run=false") != std::string::npos);
        if (!contradiction) cost(result,zero,7);
    }
    const auto empty = accepted(make_linear_program({{{"native-test"},{"empty"}}, {},7,{0,0,{0},{},{}},{},{}}));
    auto [empty_worker] = prepare(empty).create();
    cost(accepted(empty_worker->run(context())),empty,7);
    const auto large = accepted(make_linear_program({{{"native-test"},{"large-bound"}}, {0},0,{0,1,{0},{},{}},{{1e21,1e21}},{}}));
    auto [large_worker] = prepare(large).create();
    const auto large_result = accepted(large_worker->run(context()));
    cost(large_result,large,0);
    CHECK((*large_result.primal)[0] == 1e21);
}

TEST_CASE("HiGHS infeasibility ray is accepted only as an exact Farkas certificate") {
    const auto program = accepted(make_linear_program({{{"native-test"},{"farkas-ray"}},
        {0},0,{2,1,{0,1,2},{0,0},{1,1}},{{{},{}}},{{{},0},{1,{}}}}));
    auto [worker] = prepare(program).create();
    const auto result = accepted(worker->run(context()));

    REQUIRE(result.termination == Termination::completed);
    REQUIRE(result.outcome.value == MathematicalOutcome::infeasible);
    REQUIRE(std::holds_alternative<ExactFarkasEvidence>(result.outcome.support));
    const auto& evidence = std::get<ExactFarkasEvidence>(result.outcome.support);
    CHECK(evidence.subject() == program.identity());
    const auto verified = verify_linear_infeasibility_certificate(program,evidence.certificate());
    REQUIRE(std::holds_alternative<ExactFarkasEvidence>(verified));
    CHECK(std::get<ExactFarkasEvidence>(verified).certificate() == evidence.certificate());
}

TEST_CASE("late certificate verification discards evidence when the final poll observes a stop") {
    ExecutionContext deadline_context;
    const auto expired = adapters::highs_detail::verify_then_poll(
        [&] {
            deadline_context.deadline = std::chrono::steady_clock::now();
            return std::optional<int>{42};
        },
        [&]() -> std::optional<Termination> {
            if (deadline_context.deadline && std::chrono::steady_clock::now() >= *deadline_context.deadline)
                return Termination::resource_limit;
            return std::nullopt;
        });
    CHECK_FALSE(expired.evidence);
    REQUIRE(expired.stop);
    CHECK(*expired.stop == Termination::resource_limit);

    ExecutionContext cancellation_context;
    std::stop_source cancellation;
    cancellation_context.cancellation = cancellation.get_token();
    const auto cancelled = adapters::highs_detail::verify_then_poll(
        [&] {
            cancellation_context.deadline = std::chrono::steady_clock::now();
            cancellation.request_stop();
            return std::optional<int>{42};
        },
        [&]() -> std::optional<Termination> {
            if (cancellation_context.cancellation.stop_requested()) return Termination::cancelled;
            if (cancellation_context.deadline && std::chrono::steady_clock::now() >= *cancellation_context.deadline)
                return Termination::resource_limit;
            return std::nullopt;
        });
    CHECK_FALSE(cancelled.evidence);
    REQUIRE(cancelled.stop);
    CHECK(*cancelled.stop == Termination::cancelled);
}

TEST_CASE("native limits and pre-stops never claim optimal or reuse a previous candidate") {
    const auto p = triangle();
    auto [limited] = prepare(p,{0}).create();
    const auto limit = accepted(limited->run(context()));
    CHECK(limit.termination == Termination::resource_limit);
    CHECK(limit.outcome.value == MathematicalOutcome::undetermined);
    CHECK(check_program_result(limit,p,Assurance::numerical).empty());
    CHECK_FALSE(limit.objective.lower);
    CHECK_FALSE(limit.objective.upper);
    CHECK(limit.raw_diagnostics.find("native.model_status=14") != std::string::npos);
    auto [worker] = prepare(p).create();
    const auto history = accepted(worker->run(context()));
    cost(history,p,-2);
    const auto first = *worker->last_attempt();
    std::stop_source source;
    source.request_stop();
    auto stopped_context = context();
    stopped_context.cancellation = source.get_token();
    const auto stopped = accepted(worker->run(stopped_context));
    CHECK(stopped.termination == Termination::cancelled);
    CHECK(stopped.outcome.value == MathematicalOutcome::undetermined);
    CHECK_FALSE(stopped.primal);
    CHECK_FALSE(stopped.residuals.primal);
    CHECK_FALSE(stopped.residuals.dual);
    CHECK(worker->last_attempt()->stamp.attempt() == first.stamp.attempt()+1);
    auto expired = context();
    expired.deadline = std::chrono::steady_clock::now()-std::chrono::seconds(1);
    CHECK(accepted(worker->run(expired)).termination == Termination::resource_limit);
    const auto again = accepted(worker->run(context()));
    cost(again,p,-2);
    cost(history,p,-2);
    CHECK(again.raw_diagnostics.find("model.reused=true") != std::string::npos);
}

TEST_CASE("selection and execution reject unsupported capabilities and numerical resource policies") {
    Registry<LPPort> registry;
    REQUIRE_FALSE(registry.add(accepted(make_highs_registration())).has_value());
    const auto p = triangle();
    for (int feature=0;feature<6;++feature) {
        auto req = requirements();
        if(feature==0) req.scalar = Scalar::exact;
        if(feature==1) req.output.assurance = Assurance::validated;
        if(feature==2) req.basis_diagnostics = true;
        if(feature==3) req.output.completeness = Completeness::established;
        if(feature==4) req.output.representation = {"other"};
        if(feature==5) req.output.family = FamilyTarget::exact_optimal_relation;
        CHECK(std::holds_alternative<Rejection>(prepare_pipeline(select(registry,{{"csl.lp.highs"},{}},p,req))));
    }
    CHECK(std::holds_alternative<Rejection>(prepare_pipeline(select(registry,{{"csl.lp.highs"},"wrong"},p,requirements()))));
    const auto tiny = accepted(make_linear_program({{{"native-test"},{"tiny"}}, {1},0,{1,1,{0,1},{0},{1e-13}},{{0,{}}},{{{},1}}}));
    CHECK(std::holds_alternative<Rejection>(prepare_pipeline(select(registry,{{"csl.lp.highs"},{}},tiny,requirements()))));
    auto [worker] = prepare(p).create();
    auto bad = context();
    bad.numerical.absolute_tolerance = 1e-12;
    CHECK(std::holds_alternative<Unsupported>(worker->run(bad)));
    bad = context(); bad.numerical.relative_tolerance = -1;
    CHECK(std::holds_alternative<Unsupported>(worker->run(bad)));
    bad = context(); bad.numerical.absolute_tolerance = std::numeric_limits<double>::infinity();
    CHECK(std::holds_alternative<Unsupported>(worker->run(bad)));
    bad = context(); bad.resources = std::make_shared<ResourcePolicy>(ResourcePolicy{1,1,1,1024});
    CHECK(std::holds_alternative<Unsupported>(worker->run(bad)));
    bad.resources = std::make_shared<ResourcePolicy>(ResourcePolicy{0,1,1,{}});
    CHECK(std::holds_alternative<Unsupported>(worker->run(bad)));
    CHECK(worker->last_attempt()->state == SolveAttemptState::unsupported);
    CHECK(std::holds_alternative<Diagnostics>(make_highs_registration({std::numeric_limits<std::size_t>::max()})));
}


TEST_CASE("exclusive workspaces retain identity across model changes and own historical results") {
    auto registration = accepted(make_highs_registration());
    const auto p = triangle();
    const auto q = triangle(7);
    const auto bad = accepted(make_linear_program({{{"native-test"},{"reuse-infeasible"}},
        {0},0,{2,1,{0,1,2},{0,0},{1,1}},{{{},{}}},{{{},0},{1,{}}}}));
    auto worker = registration.factory(p);
    const auto identity = worker->workspace_identity();
    const auto first = accepted(worker->solve(p,context()));
    const auto stamp = worker->last_attempt()->stamp;
    cost(first,p,-2);
    CHECK(accepted(worker->solve(bad,context())).outcome.value == MathematicalOutcome::infeasible);
    cost(accepted(worker->solve(q,context())),q,5);
    cost(accepted(worker->solve(p,context())),p,-2);
    CHECK(worker->workspace_identity() == identity);
    CHECK(worker->last_attempt()->stamp.attempt() == 4);
    CHECK(stamp.attempt() == 1);
    CHECK(stamp.program().identity() == p.identity());
    cost(first,p,-2);
}

TEST_CASE("prepared ownership survives producers and independent workspaces solve concurrently") {
    auto plan = prepare(triangle()); // registry and producer have already gone
    auto [left] = plan.create();
    auto [right] = plan.create();
    CHECK_FALSE(left->workspace_identity() == right->workspace_identity());
    std::barrier start(2);
    auto launch = [&](auto& worker) {
        return std::async(std::launch::async,[&worker,&start] {
            start.arrive_and_wait();
            auto first = worker->run(context());
            auto second = worker->run(context());
            return std::pair{std::move(first),std::move(second)};
        });
    };
    auto a = launch(left);
    auto b = [&] {
        try { return launch(right); }
        catch (...) {
            // Release the first worker before its future joins during unwinding.
            start.arrive_and_drop();
            throw;
        }
    }();
    auto ar = a.get(), br = b.get();
    const auto p = triangle();
    cost(accepted(ar.first),p,-2); cost(accepted(ar.second),p,-2);
    cost(accepted(br.first),p,-2); cost(accepted(br.second),p,-2);
    CHECK(left->last_attempt()->stamp.attempt() == 2);
    CHECK(right->last_attempt()->stamp.attempt() == 2);
    CHECK_FALSE(left->last_attempt()->stamp == right->last_attempt()->stamp);
    auto retained = [] { auto local_plan = prepare(triangle(7)); return std::get<0>(local_plan.create()); }();
    cost(accepted(retained->run(context())),triangle(7),5);
}
