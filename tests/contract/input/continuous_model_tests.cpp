#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/input/continuous_model.hpp>

#include <cmath>
#include <algorithm>
#include <string_view>

using namespace csl;
using namespace csl::input;

namespace {
constexpr std::string_view document=R"({"schema":"csl.continuous-model/1","dimensions":{"state":2,"control":1,"external":0},"times":[0,1,3],"hold":"zero_order_hold","coefficients":{"kind":"continuous_lti","A":[[0,1],[0,0]],"B":[[0],[1]],"E":{"rows":2,"cols":0,"values":[]},"offset":[0,0]},"integration":{"absolute_tolerance":1e-10,"relative_tolerance":1e-10,"max_attempts_per_stage":100000}})";
ContinuousModelLoadResult load(std::string_view value,const LoadOptions& options={}) {
    return load_continuous_model(std::as_bytes(std::span(value.data(),value.size())),options);
}
template<class T,class Variant> T take(Variant result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
std::string replace(std::string value,std::string_view old,std::string_view next) {
    const auto position=value.find(old);REQUIRE(position!=std::string::npos);
    value.replace(position,old.size(),next);return value;
}
}

TEST_CASE("distinct continuous document binds source and yields literal 2D transition") {
    auto loaded=take<ContinuousModelInput>(load(document));
    CHECK(loaded.schema=="csl.continuous-model/1");
    const auto original=std::as_bytes(std::span(document.data(),document.size()));
    CHECK(std::ranges::equal(loaded.source.bytes(),original));
    CHECK(loaded.model.times==Vector{0,1,3});
    CHECK(loaded.model.hold==model::HoldConvention::zero_order_hold);
    CHECK(loaded.integration.absolute_tolerance==1e-10);
    auto converted=take<model::DiscretizedModel>(model::discretize(loaded.model,loaded.integration));
    const auto& stages=std::get<std::vector<LinearStage>>(converted.model.dynamics.stages);
    REQUIRE(stages.size()==2);
    CHECK(std::abs(stages[0].B.values[0]-0.5)<1e-11);
    CHECK(std::abs(stages[1].B.values[0]-2)<1e-11);
    CHECK(converted.receipt.source_domain==TimeDomain::continuous);
}

TEST_CASE("LTV document requires every physical interval and retains endpoints") {
    const auto base=replace(std::string(document),
        R"({"kind":"continuous_lti","A":[[0,1],[0,0]],"B":[[0],[1]],"E":{"rows":2,"cols":0,"values":[]},"offset":[0,0]})",
        R"({"kind":"continuous_piecewise_linear_ltv","stages":[{"start":{"A":[[0,1],[0,0]],"B":[[0],[1]],"E":{"rows":2,"cols":0,"values":[]},"offset":[0,0]},"end":{"A":[[0,1],[0,0]],"B":[[0],[2]],"E":{"rows":2,"cols":0,"values":[]},"offset":[0,0]}},{"start":{"A":[[0,1],[0,0]],"B":[[0],[2]],"E":{"rows":2,"cols":0,"values":[]},"offset":[0,0]},"end":{"A":[[0,1],[0,0]],"B":[[0],[3]],"E":{"rows":2,"cols":0,"values":[]},"offset":[0,0]}}]})");
    auto loaded=take<ContinuousModelInput>(load(base));
    const auto& stages=std::get<std::vector<model::CoefficientEndpoints>>(loaded.model.coefficients);
    REQUIRE(stages.size()==2);
    CHECK(stages[0].end.B.values==Vector{0,2});
    CHECK(stages[1].end.B.values==Vector{0,3});
    const auto missing=replace(base,R"(,"end":{"A":[[0,1],[0,0]],"B":[[0],[3]],"E":{"rows":2,"cols":0,"values":[]},"offset":[0,0]}})","}");
    const auto error=take<InputFailure>(load(missing));
    CHECK(error.category==InputCategory::field);
    CHECK(error.path=="/coefficients/stages/1/end");
}

TEST_CASE("schema, discrete, descriptor, nonlinear and unknown forms never reinterpret") {
    auto wrong=take<InputFailure>(load(replace(std::string(document),"csl.continuous-model/1","csl.scenario/1")));
    CHECK(wrong.path=="/schema");
    wrong=take<InputFailure>(load(replace(std::string(document),"continuous_lti","linear_discrete")));
    CHECK(wrong.path=="/coefficients/kind");
    auto unsupported=take<UnsupportedInput>(load(replace(std::string(document),"continuous_lti","continuous_descriptor")));
    CHECK(unsupported.path=="/coefficients/kind");
    unsupported=take<UnsupportedInput>(load(replace(std::string(document),"continuous_lti","continuous_nonlinear")));
    CHECK(unsupported.path=="/coefficients/kind");
    wrong=take<InputFailure>(load(replace(std::string(document),R"("hold":"zero_order_hold")",R"("hold":"unknown")")));
    CHECK(wrong.path=="/hold");
    wrong=take<InputFailure>(load(replace(std::string(document),R"("times":[0,1,3])",R"("times":[0,1,1])")));
    CHECK(wrong.path=="/times/2");
    wrong=take<InputFailure>(load(replace(std::string(document),R"("B":[[0],[1]])",R"("B":[[0],[1],[2]])")));
    CHECK(wrong.path=="/coefficients/B");
    wrong=take<InputFailure>(load(replace(std::string(document),R"("offset":[0,0])",R"("offset":[0,0],"extra":1)")));
    CHECK(wrong.path=="/coefficients/extra");
    wrong=take<InputFailure>(load(replace(std::string(document),R"("state":2)",R"("state":2,"state":2)")));
    CHECK(wrong.category==InputCategory::syntax);
}

TEST_CASE("numeric, quota and cancellation boundaries refuse before a model") {
    auto error=take<InputFailure>(load(replace(std::string(document),"1e-10","1e-9999")));
    CHECK((error.category==InputCategory::field || error.category==InputCategory::syntax));
    error=take<InputFailure>(load(replace(std::string(document),R"("state":2)",R"("state":257)")));
    CHECK(error.category==InputCategory::limit);
    LoadOptions limited;limited.limits.input_bytes=8;
    error=take<InputFailure>(load(document,limited));
    CHECK(error.category==InputCategory::limit);
    limited=LoadOptions{};limited.limits.expanded_scalars=2;
    error=take<InputFailure>(load(document,limited));
    CHECK(error.category==InputCategory::limit);
    CHECK(error.path=="/times");
    std::stop_source cancellation;cancellation.request_stop();
    LoadOptions stopped;stopped.cancellation=cancellation.get_token();
    CHECK(std::holds_alternative<OperationStopped>(load(document,stopped)));
}
