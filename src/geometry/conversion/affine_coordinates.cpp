#include "affine_coordinates.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <string>

namespace csl::geometry::conversion::detail {

bool affine_coordinates(const Eigen::MatrixXd& points, AffineCoordinates& output,
                        std::string& reason) {
    if (points.rows() == 0) {
        reason = "An empty point matrix has no affine hull.";
        return false;
    }
    if (!points.allFinite()) {
        reason = "Point coordinates must be finite.";
        return false;
    }
    const Eigen::Index ambient = points.cols();
    output.origin = points.row(0).transpose();
    const Eigen::MatrixXd differences = points.bottomRows(points.rows() - 1).rowwise() - output.origin.transpose();
    if (differences.rows() == 0 || ambient == 0) {
        output.basis.resize(ambient, 0);
        output.left_inverse.resize(0, ambient);
        output.orthogonal_equalities = Eigen::MatrixXd::Identity(ambient, ambient);
        output.dimension = 0;
        output.rank_threshold = 0;
        output.maximum_residual = 0;
        return true;
    }
    Eigen::JacobiSVD<Eigen::MatrixXd> svd(differences.transpose(), Eigen::ComputeFullU | Eigen::ComputeThinV);
    if (svd.info() != Eigen::Success || !svd.singularValues().allFinite()) {
        reason = "Affine rank decomposition failed.";
        return false;
    }
    const double scale = std::max(1.0, differences.cwiseAbs().maxCoeff());
    const double threshold = 128.0 * std::numeric_limits<double>::epsilon() *
        static_cast<double>(std::max(points.rows(), points.cols())) * scale;
    std::size_t rank = 0;
    for (Eigen::Index i = 0; i < svd.singularValues().size(); ++i) {
        const double value = svd.singularValues()[i];
        if (value > threshold) ++rank;
        else if (value > 0) {
            reason = "Affine rank is numerically ambiguous at binary64 precision.";
            return false;
        }
    }
    output.dimension = rank;
    output.rank_threshold = threshold;
    output.basis = svd.matrixU().leftCols(static_cast<Eigen::Index>(rank));
    output.left_inverse = output.basis.transpose();
    output.orthogonal_equalities = svd.matrixU().rightCols(ambient-static_cast<Eigen::Index>(rank)).transpose();
    output.maximum_residual = (differences.transpose() - output.basis * (output.basis.transpose() * differences.transpose())).norm();
    if (!std::isfinite(output.maximum_residual) || output.maximum_residual > threshold * std::sqrt(static_cast<double>(points.size()))) {
        reason = "Affine basis reconstruction exceeds its rank threshold.";
        return false;
    }
    return true;
}

} // namespace csl::geometry::conversion::detail
