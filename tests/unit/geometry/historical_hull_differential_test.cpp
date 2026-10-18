#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/basis_reuse_reducer.hpp>
#include <csl/geometry/quickhull_2d.hpp>

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <map>
#include <memory>
#include <numeric>

using namespace csl;

namespace {
template<class T, class... Rest> T accepted(std::variant<T, Rest...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}

// Independent Andrew monotone chain. All fixture coordinates are integers in
// [-16,16], so these orientation products and differences are exact binary64.
double turn(const Vector& a, const Vector& b, const Vector& c) {
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0]);
}
std::vector<Vector> monotone_chain(std::vector<Vector> points) {
    std::sort(points.begin(), points.end());
    points.erase(std::unique(points.begin(), points.end()), points.end());
    if (points.size() < 2) return points;
    std::vector<Vector> lower, upper;
    for (const auto& point : points) {
        while (lower.size() >= 2 && turn(lower[lower.size()-2], lower.back(), point) <= 0)
            lower.pop_back();
        lower.push_back(point);
    }
    for (auto it = points.rbegin(); it != points.rend(); ++it) {
        while (upper.size() >= 2 && turn(upper[upper.size()-2], upper.back(), *it) <= 0)
            upper.pop_back();
        upper.push_back(*it);
    }
    lower.pop_back(); upper.pop_back();
    lower.insert(lower.end(), upper.begin(), upper.end());
    return lower;
}

// Exact dyadic sum for these bounded integer-coordinate fixtures, without the
// production certificate verifier. Each frexp significand is an integer with
// at most 53 bits. At most 64 terms times coordinates <=16 fit signed int64.
bool exact_sum(const std::vector<std::pair<double, int>>& terms, int expected) {
    REQUIRE(terms.size() <= 64);
    std::map<int, std::int64_t> columns;
    for (const auto& [weight, coefficient] : terms) {
        REQUIRE(std::isfinite(weight));
        REQUIRE(weight >= 0); REQUIRE(weight <= 1);
        REQUIRE(std::abs(coefficient) <= 16);
        int exponent = 0;
        const auto mantissa = std::frexp(weight, &exponent);
        columns[exponent-53] += static_cast<std::int64_t>(std::ldexp(mantissa, 53)) * coefficient;
    }
    columns[0] -= expected;
    while (!columns.empty()) {
        const auto [exponent, coefficient] = *columns.begin();
        columns.erase(columns.begin());
        if (coefficient == 0) continue;
        if (coefficient % 2 != 0) return false;
        columns[exponent+1] += coefficient / 2;
    }
    return true;
}

void check_certificates(const geometry::PointCloud& cloud, const geometry::HullReduction& result) {
    std::vector<bool> accounted(cloud.points.size(), false);
    for (const auto id : result.retained) {
        REQUIRE(id < cloud.points.size());
        CHECK_FALSE(accounted[id]); accounted[id] = true;
    }
    for (const auto& certificate : result.removed) {
        REQUIRE(certificate.removed < cloud.points.size());
        CHECK_FALSE(accounted[certificate.removed]); accounted[certificate.removed] = true;
        CHECK(certificate.program.problem == cloud.problem);
        std::vector<std::pair<double, int>> sum, x, y;
        for (const auto& term : certificate.combination) {
            REQUIRE(term.point < cloud.points.size());
            CHECK(term.point != certificate.removed);
            sum.emplace_back(term.weight, 1);
            x.emplace_back(term.weight, static_cast<int>(cloud.points[term.point][0]));
            y.emplace_back(term.weight, static_cast<int>(cloud.points[term.point][1]));
        }
        CHECK(exact_sum(sum, 1));
        CHECK(exact_sum(x, static_cast<int>(cloud.points[certificate.removed][0])));
        CHECK(exact_sum(y, static_cast<int>(cloud.points[certificate.removed][1])));
    }
    CHECK(std::all_of(accounted.begin(), accounted.end(), [](bool present) { return present; }));
}

std::vector<Vector> coordinates(const geometry::PointCloud& cloud, const std::vector<std::size_t>& ids) {
    std::vector<Vector> result;
    for (const auto id : ids) { REQUIRE(id < cloud.points.size()); result.push_back(cloud.points[id]); }
    std::sort(result.begin(), result.end());
    result.erase(std::unique(result.begin(), result.end()), result.end());
    return result;
}

double support(const std::vector<Vector>& points, const Vector& direction) {
    REQUIRE_FALSE(points.empty());
    double answer = -INFINITY;
    for (const auto& point : points)
        answer = std::max(answer, point[0]*direction[0] + point[1]*direction[1]);
    return answer;
}

class CountingWorkspace final : public LPWorkspace {
public:
    CountingWorkspace(std::unique_ptr<LPWorkspace> inner, std::shared_ptr<std::atomic<std::size_t>> calls)
        : inner_(std::move(inner)), calls_(std::move(calls)) { REQUIRE(inner_); }
protected:
    ProgramOutcome do_solve(const LinearProgram& p, const ExecutionContext& context) override {
        ++*calls_;
        return inner_->solve(p, context);
    }
private:
    std::unique_ptr<LPWorkspace> inner_;
    std::shared_ptr<std::atomic<std::size_t>> calls_;
};

auto highs(bool warm = false) {
    return accepted(adapters::lp::make_highs_registration({.cross_query_warm_start=warm}));
}
LinearProgram seed() {
    return accepted(optimization::make_linear_program({{{"historical-differential"},{"seed"}},
        {}, 0, {0,0,{0},{},{}}, {}, {}}));
}

std::vector<std::vector<Vector>> fixtures() {
    std::vector<Vector> square{{-4,-4}, {4,-4}, {4,4}, {-4,4}};
    for (int x : {-2,0,2}) for (int y : {-2,0,2})
        for (int duplicate=0; duplicate<3; ++duplicate) square.push_back({double(x),double(y)});
    std::vector<Vector> rotated;
    for (const auto& p : square) rotated.push_back({p[0]-p[1], p[0]+p[1]});
    std::vector<Vector> flat;
    for (int x=-8; x<=8; ++x) { flat.push_back({double(x),-2}); flat.push_back({double(x),-2}); }
    return {square, rotated, flat, {{0,0},{8,0},{0,8},{2,2},{4,0},{0,4},{2,2}},
        {{3,-8},{3,8},{3,0},{3,-8}}, {{1,1},{1,1}}, {}};
}
}

TEST_CASE("independent dyadic oracle detects sums hidden by rounded arithmetic") {
    CHECK(exact_sum({{0.5,1},{0.25,1},{0.25,1}}, 1));
    CHECK(exact_sum({{0.5,-4},{0.5,4}}, 0));
    CHECK_FALSE(exact_sum({{0.1,1},{0.2,1},{0.7,1}}, 1));
    CHECK_FALSE(exact_sum({{0.5,1},{std::nextafter(0.5,1.0),1}}, 1));
}

TEST_CASE("QuickHull matches an independent monotone chain across degeneracies and permutations") {
    for (auto points : fixtures()) for (int permutation=0; permutation<3; ++permutation) {
        if (permutation==1) std::reverse(points.begin(),points.end());
        if (permutation==2 && !points.empty()) std::rotate(points.begin(),points.begin()+points.size()/2,points.end());
        const geometry::PointCloud cloud{{"quickhull-independent"},points};
        auto expected=monotone_chain(points); std::sort(expected.begin(),expected.end());
        const auto actual=accepted(geometry::quickhull_2d(points));
        CHECK(coordinates(cloud,actual.vertex_indices)==expected);
    }
}

TEST_CASE("historical hull variants preserve literal support and exact certificates under tied input orders") {
    const auto provider=highs(true);
    // One warm workspace deliberately spans unrelated problems and dimensions.
    auto shared=provider.factory(seed()); REQUIRE(shared);
    bool exercised_grouping=false;
    std::size_t fixture_id=0;
    for (const auto& points : fixtures()) {
        ++fixture_id;
        if (points.empty()) continue;
        for (int permutation=0; permutation<3; ++permutation) {
            geometry::PointCloud cloud{{"historical-"+std::to_string(fixture_id)+"-"+std::to_string(permutation)},points};
            if (permutation==1) std::reverse(cloud.points.begin(),cloud.points.end());
            if (permutation==2) std::rotate(cloud.points.begin(),cloud.points.begin()+cloud.points.size()/2,cloud.points.end());
            const auto expected=monotone_chain(cloud.points);
            const auto baseline=accepted(geometry::reduce_hull(cloud,*shared,{}));
            CAPTURE(cloud.problem.value);
            REQUIRE_FALSE(baseline.removed.empty());
            check_certificates(cloud,baseline);
            const auto baseline_points=coordinates(cloud,baseline.retained);
            auto fallback=highs(); fallback.basis_factory={};
            const std::array registrations{
                geometry::make_ordered_hull_reducer_registration(),
                geometry::make_grouped_hull_reducer_registration(),
                geometry::make_basis_reuse_hull_reducer_registration(),
                geometry::make_basis_reuse_hull_reducer_registration(std::move(fallback)),
                geometry::make_recursive_hull_reducer_registration(highs())};
            for (std::size_t method=0; method<registrations.size(); ++method) {
                CAPTURE(cloud.problem.value,method);
                registry::Registry<registry::HullReducerPort> registry;
                REQUIRE_FALSE(registry.add(registrations[method]));
                auto plan=accepted(registry::prepare_pipeline(registry::select(registry,
                    registry::Method{registrations[method].identity.id,std::nullopt},cloud)));
                auto [worker]=plan.create();
                ExecutionContext context;
                context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
                const auto result=accepted(worker->run_with(context,*shared));
                REQUIRE_FALSE(result.removed.empty());
                // Numerical LP candidates need not be exact dyadic witnesses.
                // Uncertain attempts retain their incomplete status; independent
                // hull equality below must not promote the algorithm's status.
                for (const auto& attempt : result.attempts)
                    if (attempt.outcome!=geometry::MembershipOutcome::feasible &&
                            attempt.outcome!=geometry::MembershipOutcome::infeasible)
                        CHECK(result.status==geometry::ReductionStatus::incomplete);
                check_certificates(cloud,result);
                const auto actual=coordinates(cloud,result.retained);
                // Every independently found extreme must survive. Extra retained
                // interior/basic points are permitted and are never called vertices.
                for (const auto& vertex : expected)
                    CHECK(std::find(actual.begin(),actual.end(),vertex)!=actual.end());
                for (const Vector direction : {Vector{1,0},Vector{-1,0},Vector{0,1},Vector{0,-1},
                        Vector{1,1},Vector{-1,1},Vector{1,-1},Vector{-1,-1}}) {
                    CHECK(support(actual,direction)==support(expected,direction));
                    CHECK(support(actual,direction)==support(baseline_points,direction));
                }
                if (method==3) { REQUIRE(result.basis_reuse); CHECK(result.basis_reuse->fell_back_to_lp_baseline); }
                if (result.grouped) exercised_grouping |= result.grouped->grouping_triggered;
            }
        }
    }
    CHECK(exercised_grouping);
}

TEST_CASE("recursive LP totals include every observed child solve") {
    auto provider=highs();
    const auto calls=std::make_shared<std::atomic<std::size_t>>(0);
    const auto factory=provider.factory;
    provider.factory=[factory,calls](const LinearProgram& p) {
        return std::make_unique<CountingWorkspace>(factory(p),calls);
    };
    auto injected=highs().factory(seed()); REQUIRE(injected);
    geometry::PointCloud cloud{{"recursive-total"},fixtures().front()};
    auto registration=geometry::make_recursive_hull_reducer_registration(std::move(provider));
    registry::Registry<registry::HullReducerPort> registry;
    REQUIRE_FALSE(registry.add(registration));
    auto plan=accepted(registry::prepare_pipeline(registry::select(registry,
        registry::Method{registration.identity.id,std::nullopt},cloud)));
    for (std::size_t workers : {1U,2U}) {
        auto [worker]=plan.create();
        ExecutionContext context;
        context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{workers,workers,1,{}});
        const auto before=calls->load();
        const auto result=accepted(worker->run_with(context,*injected));
        CAPTURE(workers);
        REQUIRE_FALSE(result.removed.empty());
        REQUIRE(result.recursive);
        CHECK(result.recursive->leaf_nodes>1);
        CHECK(result.recursive->merge_nodes>0);
        CHECK(result.lp_calls==calls->load()-before);
        CHECK(result.lp_calls==result.recursive->leaf_lp_calls+result.recursive->merge_lp_calls);
        check_certificates(cloud,result);
        for (const auto& vertex : monotone_chain(cloud.points)) {
            const auto actual=coordinates(cloud,result.retained);
            CHECK(std::find(actual.begin(),actual.end(),vertex)!=actual.end());
        }
    }
}
