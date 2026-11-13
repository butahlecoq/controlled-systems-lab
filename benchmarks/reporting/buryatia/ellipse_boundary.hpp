#pragma once

#include <csl/geometry/ellipsoidal.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

namespace csl::benchmarks::buryatia {

inline std::vector<std::array<double,2>> factor_ellipsoid_boundary_2d(
        const geometry::ellipsoidal::FactorEllipsoid& ellipsoid,
        std::size_t count=96) {
    if(ellipsoid.center.size()!=2 || ellipsoid.factor.rows!=2 || count<4 ||
       (ellipsoid.factor.cols!=0 && ellipsoid.factor.rows>
            std::numeric_limits<std::size_t>::max()/ellipsoid.factor.cols) ||
       ellipsoid.factor.values.size()!=ellipsoid.factor.rows*ellipsoid.factor.cols)
        throw std::invalid_argument("A two-dimensional factor ellipsoid and at least four samples are required.");

    double q00=0.0,q01=0.0,q11=0.0;
    for(std::size_t column=0;column<ellipsoid.factor.cols;++column) {
        const double x=ellipsoid.factor.values[column];
        const double y=ellipsoid.factor.values[ellipsoid.factor.cols+column];
        q00+=x*x;
        q01+=x*y;
        q11+=y*y;
    }
    const double spread=std::hypot(q00-q11,2.0*q01);
    const double major=std::sqrt(std::max(0.0,(q00+q11+spread)/2.0));
    const double minor=std::sqrt(std::max(0.0,(q00+q11-spread)/2.0));
    const double angle=0.5*std::atan2(2.0*q01,q00-q11);
    const double cosine=std::cos(angle),sine=std::sin(angle);
    const std::array<double,2> major_axis{cosine,sine};
    const std::array<double,2> minor_axis{-sine,cosine};

    std::vector<std::array<double,2>> points;
    points.reserve(count);
    const double pi=std::acos(-1.0);
    for(std::size_t i=0;i<count;++i) {
        const double parameter=2.0*pi*static_cast<double>(i)/static_cast<double>(count);
        const double along_major=major*std::cos(parameter);
        const double along_minor=minor*std::sin(parameter);
        points.push_back({ellipsoid.center[0]+along_major*major_axis[0]+along_minor*minor_axis[0],
                          ellipsoid.center[1]+along_major*major_axis[1]+along_minor*minor_axis[1]});
    }
    return points;
}

} // namespace csl::benchmarks::buryatia
