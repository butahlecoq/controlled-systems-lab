#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/synthesis/finite_action_histories.hpp>

#include <limits>
#include <utility>

using namespace csl;
using namespace csl::synthesis;

namespace {
FiniteActionHistoryCursor cursor(const FiniteDomain& domain,std::size_t horizon) {
    auto result=FiniteActionHistoryCursor::prepare(domain,horizon);
    REQUIRE(std::holds_alternative<FiniteActionHistoryCursor>(result));
    return std::get<FiniteActionHistoryCursor>(std::move(result));
}
}

TEST_CASE("finite action history cursor streams distinct catalogue indices in order") {
    const FiniteDomain domain{1,{{-1},{-1}}}; // Equal values remain separate choices.
    auto search=cursor(domain,2);

    const auto first=search.take_prefix(1);
    REQUIRE(first.histories==std::vector<FiniteActionHistory>{{{0,0}}});
    CHECK_FALSE(first.complete);
    CHECK_FALSE(search.complete());

    const auto no_progress=search.take_prefix(0);
    CHECK(no_progress.histories.empty());
    CHECK_FALSE(no_progress.complete);

    const auto middle=search.take_prefix(2);
    REQUIRE(middle.histories==std::vector<FiniteActionHistory>{{{0,1}},{{1,0}}});
    CHECK_FALSE(middle.complete);

    const auto last=search.take_prefix(4);
    REQUIRE(last.histories==std::vector<FiniteActionHistory>{{{1,1}}});
    CHECK(last.complete);
    CHECK(search.complete());
    CHECK(search.take_prefix(1).histories.empty());
}

TEST_CASE("zero horizon has one empty history even with an empty catalogue") {
    auto search=cursor(FiniteDomain{1,{}},0);
    CHECK_FALSE(search.complete());
    const auto page=search.take_prefix(1);
    REQUIRE(page.histories.size()==1);
    CHECK(page.histories.front().catalogue_indices.empty());
    CHECK(page.complete);
}

TEST_CASE("positive horizon with no actions has an empty complete inventory") {
    auto search=cursor(FiniteDomain{1,{}},3);
    CHECK(search.complete());
    const auto page=search.take_prefix(8);
    CHECK(page.histories.empty());
    CHECK(page.complete);
}

TEST_CASE("finite action history preparation rejects malformed catalogue rows") {
    const auto wrong_dimension=FiniteActionHistoryCursor::prepare(FiniteDomain{2,{{1}}},1);
    REQUIRE(std::holds_alternative<Diagnostics>(wrong_dimension));
    CHECK(std::get<Diagnostics>(wrong_dimension).front().field=="finite_history.action_dimension");

    const auto nonfinite=FiniteActionHistoryCursor::prepare(
        FiniteDomain{1,{{std::numeric_limits<double>::infinity()}}},1);
    REQUIRE(std::holds_alternative<Diagnostics>(nonfinite));
    CHECK(std::get<Diagnostics>(nonfinite).front().field=="finite_history.action_value");
}
