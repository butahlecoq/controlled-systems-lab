#pragma once

#include <csl/numeric/data.hpp>

namespace csl::optimization {

template<class T> using Result = std::variant<T, Diagnostic, OperationStopped>;
struct ObjectivePolicy {
    Assurance assurance{Assurance::numerical};
    NumericalPolicy numerical{1e-8, 1e-8};
};
struct LinearCoefficients { numeric::VectorView coefficients; double offset; };
struct QuadraticCoefficients { numeric::MatrixView Q; numeric::VectorView linear; double offset; };
struct ResidualCoefficients { numeric::MatrixView map; numeric::VectorView target; };
using ObjectiveCoefficients = std::variant<LinearCoefficients, QuadraticCoefficients, ResidualCoefficients>;
struct QuadraticChecks {
    NumericalCheck symmetry;
    NumericalCheck positive_semidefiniteness;
    double minimum_eigenvalue;
    double eigenvalue_scale;
    // The eigensolver checks (Q+Q')/2; the original Q is retained unchanged.
};
namespace detail { struct ObjectiveStorage; }
class Objective {
public:
    Objective(const Objective&) = default;
    Objective& operator=(const Objective&) = default;
    std::size_t dimension() const noexcept;
    ObjectiveCoefficients coefficients() const;
    ObjectivePolicy policy() const noexcept;
    std::optional<QuadraticChecks> quadratic_checks() const;
private:
    explicit Objective(std::shared_ptr<const detail::ObjectiveStorage>);
    std::shared_ptr<const detail::ObjectiveStorage> storage_;
    friend Result<Objective> snapshot(const TerminalObjective&, ObjectivePolicy);
};

Result<Objective> snapshot(const TerminalObjective&, ObjectivePolicy = {});
Result<double> evaluate(const Objective&, std::span<const double> point);

enum class ObjectiveTransformation { residual_norm_squared };
class NormSquareReformulation {
public:
    NormSquareReformulation(const NormSquareReformulation&) = default;
    NormSquareReformulation& operator=(const NormSquareReformulation&) = default;
    Objective original() const;
    Objective squared() const;
    ObjectiveTransformation transformation() const noexcept;
private:
    NormSquareReformulation(Objective original, Objective squared);
    Objective original_, squared_;
    friend Result<NormSquareReformulation> square_residual_norm(const Objective&);
};
Result<NormSquareReformulation> square_residual_norm(const Objective&);

} // namespace csl::optimization
