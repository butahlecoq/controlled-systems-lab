#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <csl/geometry/ellipsoidal.hpp>

#include <doctest/doctest.h>

#include <cmath>
#include <variant>

namespace {
using namespace csl;
using namespace csl::geometry::ellipsoidal;

double support(const FactorEllipsoid& ellipsoid,const Vector& direction) {
    double center=0.0;
    for(std::size_t i=0;i<direction.size();++i)
        center+=direction[i]*ellipsoid.center[i];
    double square=0.0;
    for(std::size_t column=0;column<ellipsoid.factor.cols;++column) {
        double projection=0.0;
        for(std::size_t row=0;row<ellipsoid.factor.rows;++row)
            projection+=direction[row]*ellipsoid.factor.values[
                row*ellipsoid.factor.cols+column];
        square+=projection*projection;
    }
    return center+std::sqrt(square);
}

template<class T> T take(std::variant<T,Diagnostics> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
}

TEST_CASE("factor ellipsoid outer Minkowski sum encloses both supports") {
    const auto left=take(make_factor_ellipsoid({1.0,-2.0},Matrix{2,2,{2.0,0.5,0.0,1.0}}));
    const auto right=take(make_factor_ellipsoid({-0.5,3.0},Matrix{2,1,{0.25,-1.5}}));
    const auto sum=take(outer_minkowski_sum(left,right,0.75));
    for(const Vector direction: {Vector{1.0,0.0},Vector{0.0,1.0},
                                  Vector{1.0,1.0},Vector{-2.0,0.5}})
        CHECK(support(sum,direction)+1e-12>=support(left,direction)+support(right,direction));
}

TEST_CASE("factor ellipsoid outer box allows rectangular controls and arbitrary state dimension") {
    const auto box=take(outer_box({0.0,0.0,0.0},Matrix{3,2,{1.0,0.0,0.0,2.0,1.0,-1.0}}));
    CHECK(box.factor.rows==3);
    CHECK(box.factor.cols==2);
    const auto diagonal=Vector{1.0,-2.0,0.5};
    const double maximum_box=std::abs(diagonal[0]+diagonal[2])+
        std::abs(2.0*diagonal[1]-diagonal[2]);
    CHECK(support(box,diagonal)+1e-12>=maximum_box);
}

TEST_CASE("factor ellipsoid Minkowski kernel supports a four-state model") {
    const auto left=take(make_factor_ellipsoid({0,1,-1,2},
        Matrix{4,2,{1,0,0,2,1,-1,0.5,0.25}}));
    const auto right=take(make_factor_ellipsoid({0,0.5,0,0},
        Matrix{4,2,{0.2,0,0,0.4,-0.3,0.1,0,0.2}}));
    const auto beta=std::sqrt(0.34/7.3125);
    const auto sum=take(outer_minkowski_sum(left,right,beta));
    for(const Vector direction: {Vector{1,0,0,0},Vector{0,1,-1,2},
                                  Vector{0.5,-1,2,0.25}})
        CHECK(support(sum,direction)+1e-12>=support(left,direction)+support(right,direction));
}

TEST_CASE("factor ellipsoid affine image supports rank deficient factors") {
    const auto point=take(make_factor_ellipsoid({2.0,3.0},Matrix{2,0,{}}));
    const auto image=take(affine_image(point,Matrix{3,2,{1.0,0.0,0.0,1.0,1.0,-1.0}},
        Vector{1.0,-1.0,0.5}));
    CHECK(image.center==Vector{3.0,2.0,-0.5});
    CHECK(image.factor.rows==3);
    CHECK(image.factor.cols==0);
}

TEST_CASE("zero-factor Minkowski operands preserve the other factor exactly") {
    const auto point=take(make_factor_ellipsoid({1.0,-1.0},Matrix{2,0,{}}));
    const auto segment=take(make_factor_ellipsoid({0.5,2.0},Matrix{2,1,{3.0,-4.0}}));
    const auto sum=take(outer_minkowski_sum(point,segment,1.0));
    CHECK(sum.center==Vector{1.5,1.0});
    CHECK(sum.factor.rows==2);
    CHECK(sum.factor.cols==1);
    CHECK(sum.factor.values==segment.factor.values);
}
