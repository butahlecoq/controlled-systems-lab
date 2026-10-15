#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include "lp_report.hpp"
#include <limits>
#include <sstream>

using namespace csl::reporting;

TEST_CASE("literal catalogue uses the actual registered LP and owns the returned evidence") {
    const auto fixtures = catalogue();
    REQUIRE(fixtures.size() == 5);
    const double expected[] = {5, -1, -6};
    for (std::size_t i = 0; i < fixtures.size(); ++i) {
        const auto trial = run_trial(fixtures[i], {});
        INFO(trial.error);
        for (const auto& error : trial.errors) INFO(error);
        REQUIRE(trial.passed());
        REQUIRE(trial.result.has_value());
        CHECK(trial.actual_version == "1.0.0+highs.1.11.0");
        REQUIRE(trial.attempt.has_value());
        CHECK(trial.attempt->stamp.attempt() == 1);
        CHECK(trial.attempt->state == csl::SolveAttemptState::returned_result);
        CHECK(trial.attempt->stamp.program().identity() == fixtures[i].input.identity);
        CHECK(trial.result->raw_diagnostics.find("native_run=true") != std::string::npos);
        CHECK(trial.result->raw_diagnostics.find(std::string("native.downstream.hvectorbase_sha256=")+CSL_HIGHS_PATCHED_SOURCE_SHA256) != std::string::npos);
        CHECK(trial.result->raw_diagnostics.find("model.reused=false") != std::string::npos);
        if (i < 3) {
            REQUIRE(trial.objective.has_value());
            CHECK(*trial.objective == doctest::Approx(expected[i]));
            CHECK(trial.result->outcome.value == csl::MathematicalOutcome::optimal);
        } else {
            CHECK(trial.result->outcome.value == (i == 3 ? csl::MathematicalOutcome::infeasible : csl::MathematicalOutcome::unbounded));
        }
        CHECK(trial.timings[5].available);
        CHECK(trial.timings[5].start <= trial.timings[3].start);
        CHECK(trial.timings[5].end >= trial.timings[4].end);
        CHECK_FALSE(trial.result->objective.lower.has_value());
        CHECK_FALSE(trial.result->objective.upper.has_value());
    }
}

TEST_CASE("infeasible LP report names independently verified Farkas support") {
    const auto fixture=catalogue()[3];
    const auto trial=run_trial(fixture,{});
    INFO(trial.error);
    for(const auto& error:trial.errors) INFO(error);
    REQUIRE(trial.passed());
    REQUIRE(trial.result);
    const auto json=trial_json(fixture,trial,1,1,"test");
    CHECK(json.find("\"support\":{\"kind\":\"exact_farkas_verified\"}")!=std::string::npos);
    CHECK(json.find("\"assumptions\":[\"binary64 numerical output; exact_farkas_verified\"]")!=std::string::npos);
    CHECK(catalogue_json().find("binary64 numerical output; exact_farkas_verified support required")!=std::string::npos);
}

TEST_CASE("pre-cancelled functional trial retains current result without passing oracle") {
    const auto fixtures = catalogue();
    REQUIRE(fixtures.size() == 5);
    std::stop_source source;
    source.request_stop();
    const auto trial = run_trial(fixtures[0], source.get_token());
    REQUIRE(trial.result.has_value());
    CHECK(trial.result->termination == csl::Termination::cancelled);
    CHECK_FALSE(trial.passed());
    CHECK_FALSE(trial.errors.empty());
    const auto next = run_trial(fixtures[0], {});
    REQUIRE(next.passed());
    REQUIRE(next.attempt.has_value());
    CHECK_FALSE(next.attempt->stamp.workspace() == trial.attempt->stamp.workspace());
    CHECK(trial.result->termination == csl::Termination::cancelled);
}

TEST_CASE("JSON writer preserves escaping binary64 signed zero and rejects nonfinite") {
    CHECK(json_string("a\n\"\\\t<&") == "\"a\\n\\\"\\\\\\t<&\"");
    CHECK(json_number(-0.0) == "-0.0");
    CHECK(json_number(5.0) == "5.0");
    CHECK_THROWS_AS(json_number(std::numeric_limits<double>::infinity()), std::invalid_argument);
    CHECK_THROWS_AS(json_number(std::numeric_limits<double>::quiet_NaN()), std::invalid_argument);
}

TEST_CASE("preparation rejection retains diagnostic and never claims a solve") {
    auto fixture=catalogue()[0];
    fixture.input.identity.program={"test-unsupported-tiny"};
    fixture.input.constraints.values[0]=1e-13;
    const auto trial=run_trial(fixture,{});
    CHECK(trial.harness_status=="unsupported");
    CHECK_FALSE(trial.passed());
    CHECK_FALSE(trial.result.has_value());
    CHECK_FALSE(trial.timings[3].available);
    CHECK(trial.error.find("highs.matrix")!=std::string::npos);
    CHECK(trial.error.find("1e-12")!=std::string::npos);
}

TEST_CASE("exceptional total explicitly records owner unwind while preserving the exception") {
    Interval total;
    total.available=true;
    total.start=Clock::now().time_since_epoch().count();
    bool destroyed=false;
    struct Owner { bool& destroyed; ~Owner() { destroyed=true; } };
    try {
        record_failure_unwind(total,[&] {
            Owner owner{destroyed};
            throw std::runtime_error("controlled failure");
        });
        FAIL("failure must propagate");
    } catch (const std::runtime_error& error) {
        CHECK(std::string(error.what())=="controlled failure");
    }
    CHECK(destroyed);
    CHECK(total.includes_unwind);
    CHECK(total.end>=total.start);
    const auto successful=run_trial(catalogue()[0],{});
    CHECK_FALSE(successful.timings[5].includes_unwind);
    auto bad=catalogue()[0];bad.input.identity.program={"unwind-preparation"};bad.input.constraints.values[0]=1e-13;
    const auto failed=run_trial(bad,{});
    CHECK(failed.timings[5].includes_unwind);
    CHECK(trial_json(bad,failed,1,1,"test").find("end_to_end_including_unwind")!=std::string::npos);
}
