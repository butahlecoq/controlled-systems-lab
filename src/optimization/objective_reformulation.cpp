#include <csl/optimization/objectives.hpp>
#include <cmath>
#include <algorithm>
#include <limits>
#include <numeric>
#include <Eigen/Eigenvalues>

namespace csl::optimization {
namespace {
OperationStopped arithmetic_failure() {
    return {StopReason::numerical_failure, "Nonrepresentable objective arithmetic or eigensolver failure."};
}
bool accumulate_product(double& total, double left, double right) {
    const double product = left * right;
    if (product == 0 && left != 0 && right != 0) return false;
    total += product;
    return true;
}
OperationStopped erased_product(const char* group) {
    return {StopReason::numerical_failure,
            std::string("objective.reformulation.") + group + ": nonzero coefficient product rounded to zero."};
}
Result<QuadraticChecks> check_quadratic(const numeric::MatrixView& Q, NumericalPolicy policy) {
    const auto n = Q.rows();
    if (n != 0 && n > static_cast<std::size_t>(std::numeric_limits<Eigen::Index>::max()) / n)
        return Diagnostic{DiagnosticCode::unsupported, "objective.shape", "Quadratic exceeds native index range."};
    double scale = 0, asymmetry = 0;
    for (std::size_t i = 0; i < n; ++i)
        for (std::size_t j = 0; j < n; ++j) {
            scale = std::max(scale, std::abs(Q(i, j)));
            asymmetry = std::max(asymmetry, std::abs(Q(i, j) - Q(j, i)));
        }
    const double symmetry_tolerance = policy.absolute_tolerance + policy.relative_tolerance * scale;
    if (!std::isfinite(symmetry_tolerance) || !std::isfinite(asymmetry)) return arithmetic_failure();
    if (asymmetry > symmetry_tolerance)
        return Diagnostic{DiagnosticCode::invalid_input, "objective.symmetry", "Quadratic exceeds the symmetry tolerance."};
    double minimum = 0, eigenvalue_scale = 0;
    if (n != 0 && scale != 0) {
        const auto size = static_cast<Eigen::Index>(n);
        Eigen::MatrixXd symmetric(size, size);
        for (Eigen::Index i = 0; i < size; ++i)
            for (Eigen::Index j = 0; j < size; ++j) {
                const double value = std::midpoint(Q(static_cast<std::size_t>(i), static_cast<std::size_t>(j)),
                                                   Q(static_cast<std::size_t>(j), static_cast<std::size_t>(i)));
                symmetric(i, j) = value / scale;
                if (value != 0 && symmetric(i, j) == 0) return arithmetic_failure();
            }
        Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> solver(symmetric, Eigen::EigenvaluesOnly);
        if (solver.info() != Eigen::Success || !solver.eigenvalues().allFinite()) return arithmetic_failure();
        minimum = solver.eigenvalues().minCoeff() * scale;
        if (solver.eigenvalues().minCoeff() != 0 && minimum == 0) return arithmetic_failure();
        eigenvalue_scale = solver.eigenvalues().cwiseAbs().maxCoeff() * scale;
    }
    const double threshold = policy.absolute_tolerance + policy.relative_tolerance * eigenvalue_scale;
    if (!std::isfinite(minimum) || !std::isfinite(eigenvalue_scale) || !std::isfinite(threshold)) return arithmetic_failure();
    if (minimum < -threshold)
        return Diagnostic{DiagnosticCode::invalid_input, "objective.psd", "Negative eigenvalue exceeds the PSD tolerance; indefinite quadratic unsupported."};
    if (minimum < 0)
        return Diagnostic{DiagnosticCode::unsupported, "objective.psd", "Negative eigenvalue within tolerance leaves PSD numerically unresolved; coefficients were not repaired."};
    return QuadraticChecks{
        {policy.absolute_tolerance, policy.relative_tolerance, asymmetry, {"csl.objectives.symmetry.v1"}},
        {policy.absolute_tolerance, policy.relative_tolerance, 0, {"csl.objectives.eigen-3.4.0.symmetric-part.v1"}},
        minimum, eigenvalue_scale};
}
}
namespace detail {
struct ObjectiveStorage {
    ObjectiveCoefficients coefficients;
    ObjectivePolicy policy;
    std::optional<QuadraticChecks> checks;
};
}
Objective::Objective(std::shared_ptr<const detail::ObjectiveStorage> storage) : storage_(std::move(storage)) {}
ObjectiveCoefficients Objective::coefficients() const { return storage_->coefficients; }
ObjectivePolicy Objective::policy() const noexcept { return storage_->policy; }
std::optional<QuadraticChecks> Objective::quadratic_checks() const { return storage_->checks; }
std::size_t Objective::dimension() const noexcept {
    return std::visit([](const auto& data) {
        using T = std::decay_t<decltype(data)>;
        if constexpr (std::is_same_v<T, LinearCoefficients>) return data.coefficients.size();
        else if constexpr (std::is_same_v<T, QuadraticCoefficients>) return data.linear.size();
        else return data.map.cols();
    }, storage_->coefficients);
}
Result<Objective> snapshot(const TerminalObjective& authored, ObjectivePolicy policy) {
    if (policy.assurance != Assurance::numerical && policy.assurance != Assurance::validated)
        return Diagnostic{DiagnosticCode::invalid_input, "objective.assurance", "Unknown requested assurance."};
    if (!std::isfinite(policy.numerical.absolute_tolerance) || !std::isfinite(policy.numerical.relative_tolerance) ||
        policy.numerical.absolute_tolerance < 0 || policy.numerical.relative_tolerance < 0)
        return Diagnostic{DiagnosticCode::invalid_input, "objective.policy", "Tolerances must be finite and nonnegative."};
    if (policy.assurance == Assurance::validated)
        return Diagnostic{DiagnosticCode::unsupported, "objective.assurance", "This module supplies numerical arithmetic only; validated evidence is unavailable."};
    if (const auto* linear = std::get_if<LinearTerminal>(&authored)) {
        auto vector = numeric::snapshot_vector(linear->coefficients);
        if (const auto* error = std::get_if<Diagnostic>(&vector)) return *error;
        if (!std::isfinite(linear->offset))
            return Diagnostic{DiagnosticCode::invalid_input, "objective.offset", "Offset must be finite."};
        return Objective{std::make_shared<const detail::ObjectiveStorage>(detail::ObjectiveStorage{
            LinearCoefficients{std::get<numeric::VectorView>(vector), linear->offset}, policy, std::nullopt})};
    }
    if (const auto* quadratic = std::get_if<QuadraticTerminal>(&authored)) {
        auto matrix = numeric::snapshot(quadratic->Q);
        if (const auto* error = std::get_if<Diagnostic>(&matrix)) return *error;
        auto linear = numeric::snapshot_vector(quadratic->linear);
        if (const auto* error = std::get_if<Diagnostic>(&linear)) return *error;
        if (quadratic->Q.rows != quadratic->Q.cols || quadratic->Q.cols != quadratic->linear.size())
            return Diagnostic{DiagnosticCode::invalid_input, "objective.shape", "Quadratic matrix must be square and match the linear term."};
        if (!std::isfinite(quadratic->offset))
            return Diagnostic{DiagnosticCode::invalid_input, "objective.offset", "Offset must be finite."};
        auto checks = check_quadratic(std::get<numeric::MatrixView>(matrix), policy.numerical);
        if (const auto* error = std::get_if<Diagnostic>(&checks)) return *error;
        if (const auto* stopped = std::get_if<OperationStopped>(&checks)) return *stopped;
        return Objective{std::make_shared<const detail::ObjectiveStorage>(detail::ObjectiveStorage{
            QuadraticCoefficients{std::get<numeric::MatrixView>(matrix), std::get<numeric::VectorView>(linear), quadratic->offset},
            policy, std::get<QuadraticChecks>(checks)})};
    }
    if (const auto* residual = std::get_if<ResidualNormTerminal>(&authored)) {
        auto map = numeric::snapshot(residual->map);
        if (const auto* error = std::get_if<Diagnostic>(&map)) return *error;
        auto target = numeric::snapshot_vector(residual->target);
        if (const auto* error = std::get_if<Diagnostic>(&target)) return *error;
        if (residual->map.rows != residual->target.size())
            return Diagnostic{DiagnosticCode::invalid_input, "objective.shape", "Residual target must match map rows."};
        return Objective{std::make_shared<const detail::ObjectiveStorage>(detail::ObjectiveStorage{
            ResidualCoefficients{std::get<numeric::MatrixView>(map), std::get<numeric::VectorView>(target)}, policy, std::nullopt})};
    }
    return Diagnostic{DiagnosticCode::unsupported, "objective", "Objective kind is not implemented."};
}
Result<double> evaluate(const Objective& objective, std::span<const double> point) {
    if (point.size() != objective.dimension())
        return Diagnostic{DiagnosticCode::invalid_input, "objective.point", "Point dimension does not match objective."};
    for (const double value : point)
        if (!std::isfinite(value))
            return Diagnostic{DiagnosticCode::invalid_input, "objective.point", "Point must be finite."};
    const auto data = objective.coefficients();
    if (const auto* quadratic = std::get_if<QuadraticCoefficients>(&data)) {
        double result = quadratic->offset;
        for (std::size_t i = 0; i < point.size(); ++i) {
            double row = 0;
            for (std::size_t j = 0; j < point.size(); ++j) row += quadratic->Q(i, j) * point[j];
            if (!std::isfinite(row)) return arithmetic_failure();
            result += (0.5 * point[i]) * row;
            result += quadratic->linear[i] * point[i];
        }
        if (!std::isfinite(result)) return arithmetic_failure();
        return result;
    }
    if (const auto* linear = std::get_if<LinearCoefficients>(&data)) {
        double result = linear->offset;
        for (std::size_t i = 0; i < point.size(); ++i) result += linear->coefficients[i] * point[i];
        if (!std::isfinite(result))
            return OperationStopped{StopReason::numerical_failure, "Nonfinite objective arithmetic."};
        return result;
    }
    if (const auto* residual = std::get_if<ResidualCoefficients>(&data)) {
        double norm = 0;
        for (std::size_t row = 0; row < residual->map.rows(); ++row) {
            double value = -residual->target[row];
            for (std::size_t col = 0; col < point.size(); ++col) value += residual->map(row, col) * point[col];
            norm = std::hypot(norm, value);
        }
        if (!std::isfinite(norm))
            return OperationStopped{StopReason::numerical_failure, "Nonfinite residual arithmetic."};
        return norm;
    }
    return Diagnostic{DiagnosticCode::unsupported, "objective", "Objective kind is not implemented."};
}
NormSquareReformulation::NormSquareReformulation(Objective original, Objective squared)
    : original_(original), squared_(squared) {}
Objective NormSquareReformulation::original() const { return original_; }
Objective NormSquareReformulation::squared() const { return squared_; }
ObjectiveTransformation NormSquareReformulation::transformation() const noexcept {
    return ObjectiveTransformation::residual_norm_squared;
}
Result<NormSquareReformulation> square_residual_norm(const Objective& original) {
    const auto coefficients = original.coefficients();
    const auto* residual = std::get_if<ResidualCoefficients>(&coefficients);
    if (!residual)
        return Diagnostic{DiagnosticCode::unsupported, "objective.reformulation", "Only a residual norm can be squared by this transformation."};
    const auto n = residual->map.cols();
    if (n != 0 && n > std::numeric_limits<std::size_t>::max() / n)
        return Diagnostic{DiagnosticCode::unsupported, "objective.reformulation.shape", "Squared coefficient storage exceeds size_t."};
    QuadraticTerminal authored{{n, n, Vector(n * n)}, Vector(n), 0};
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = i; j < n; ++j) {
            double value = 0;
            for (std::size_t row = 0; row < residual->map.rows(); ++row)
                if (!accumulate_product(value, residual->map(row, i), residual->map(row, j)))
                    return erased_product("Q");
            value *= 2;
            if (!std::isfinite(value)) return arithmetic_failure();
            authored.Q.values[i * n + j] = value;
            authored.Q.values[j * n + i] = value;
        }
        double value = 0;
        for (std::size_t row = 0; row < residual->map.rows(); ++row)
            if (!accumulate_product(value, residual->map(row, i), residual->target[row]))
                return erased_product("q");
        authored.linear[i] = -2 * value;
        if (!std::isfinite(authored.linear[i])) return arithmetic_failure();
    }
    for (const double value : residual->target.values())
        if (!accumulate_product(authored.offset, value, value)) return erased_product("c");
    if (!std::isfinite(authored.offset)) return arithmetic_failure();
    auto squared = snapshot(authored, original.policy());
    if (const auto* error = std::get_if<Diagnostic>(&squared)) return *error;
    if (const auto* stopped = std::get_if<OperationStopped>(&squared)) return *stopped;
    return NormSquareReformulation{original, std::get<Objective>(squared)};
}
} // namespace csl::optimization
