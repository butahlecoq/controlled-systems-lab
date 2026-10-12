#pragma once

#include <Eigen/Core>
#include <Eigen/SVD>
#include <cstddef>
#include <string>
#include <vector>

namespace csl::geometry::conversion::detail {

struct AffineCoordinates {
    Eigen::VectorXd origin;
    Eigen::MatrixXd basis;
    Eigen::MatrixXd left_inverse;
    Eigen::MatrixXd orthogonal_equalities;
    std::size_t dimension{};
    double rank_threshold{};
    double maximum_residual{};
};

// Builds a numerically resolved affine coordinate map for points stored by row.
// Ambiguous rank is reported to the caller and must never be rounded down.
bool affine_coordinates(const Eigen::MatrixXd& points, AffineCoordinates& output,
                        std::string& reason);

} // namespace csl::geometry::conversion::detail
