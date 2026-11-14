#pragma once
#include <csl/optimization/convex_backend.hpp>
#include <bit>

namespace row_diagnostic {
using namespace csl;
using namespace csl::optimization;
inline double scale_exact(double value, int exponent) {
    if (!std::isfinite(value)) throw std::runtime_error("Nonfinite finite-bound/coefficient input");
    const double scaled = std::scalbn(value, exponent);
    if (!std::isfinite(scaled) || (value != 0.0 && scaled == 0.0) ||
        std::bit_cast<std::uint64_t>(std::scalbn(scaled, -exponent)) != std::bit_cast<std::uint64_t>(value))
        throw std::runtime_error("Power-of-two transform overflow/underflow/exact-roundtrip refusal");
    return scaled;
}
inline std::optional<double> scale_bound(std::optional<double> value, int exponent) {
    if (!value) return std::nullopt; // Explicit absent bound remains infinite.
    return scale_exact(*value, exponent);
}
inline ConvexProgram export_and_scale(const ConvexProgram& original, const std::filesystem::path& folder,
                                     std::size_t nx, std::size_t nu, std::size_t horizon, bool apply) {
    std::filesystem::create_directory(folder);
    const auto& qp = original.quadratic_program();
    const auto csr = std::get<numeric::CsrInput>(qp.constraints().descriptor());
    SparseMatrix changed{csr.rows, csr.cols,
        {csr.row_offsets.begin(), csr.row_offsets.end()},
        {csr.column_indices.begin(), csr.column_indices.end()},
        {csr.values.begin(), csr.values.end()}};
    std::vector<Interval> rows(qp.rows().begin(), qp.rows().end());
    std::ofstream coefficients(folder / "csr.csv"), bounds(folder / "rows.csv"), objective(folder / "objective.csv"), identity(folder / "identity.txt");
    for (auto* stream : {&coefficients, &bounds, &objective}) *stream << std::setprecision(17);
    coefficients << "row,column,original,scaled,offends_original_threshold,exact_roundtrip\n";
    bounds << "row,role,stage,coordinate,min_abs_nonzero,max_abs_nonzero,power2_exponent,original_lower,original_upper,scaled_lower,scaled_upper\n";
    objective << "kind,row,column,value\n";
    identity << "original_problem=" << original.identity().problem.value << "\noriginal_program=" << original.identity().program.value
             << "\nconfiguration=" << (apply ? "positive-power2-row-min-normalization-v1" : "original-export-only-v1")
             << "\ndual_relation=y_original=D*y_scaled; mathematical relation only, ProgramResult has no public dual vectors\n";
    auto bound_text = [](std::ostream& stream, std::optional<double> value) { if (value) stream << *value; else stream << "unbounded"; };
    for (std::size_t row = 0; row < csr.rows; ++row) {
        double minimum = std::numeric_limits<double>::infinity(), maximum = 0.0;
        for (std::size_t k = csr.row_offsets[row]; k < csr.row_offsets[row + 1]; ++k) if (csr.values[k] != 0.0) {
            minimum = std::min(minimum, std::abs(csr.values[k])); maximum = std::max(maximum, std::abs(csr.values[k]));
        }
        // Scale only rows containing an actually offending nonzero. Power2 makes their minimum in [1,2).
        const int exponent = apply && minimum <= 1e-12 ? std::max(0, -std::ilogb(minimum)) : 0;
        rows[row] = {scale_bound(qp.rows()[row].lower, exponent), scale_bound(qp.rows()[row].upper, exponent)};
        std::string role; std::size_t stage{}, coordinate{};
        if (nx == 0) { role = "analytic_equalities"; coordinate = row; }
        else if (row < nx) { role = "initial"; coordinate = row; }
        else if (row < (horizon + 1) * nx) { role = "dynamics"; stage = (row - nx) / nx; coordinate = (row - nx) % nx; }
        else { role = "control_bound"; stage = (row - (horizon + 1) * nx) / nu; coordinate = (row - (horizon + 1) * nx) % nu; }
        bounds << row << ',' << role << ',' << stage << ',' << coordinate << ',' << minimum << ',' << maximum << ',' << exponent << ',';
        bound_text(bounds, qp.rows()[row].lower); bounds << ','; bound_text(bounds, qp.rows()[row].upper); bounds << ',';
        bound_text(bounds, rows[row].lower); bounds << ','; bound_text(bounds, rows[row].upper); bounds << '\n';
        for (std::size_t k = csr.row_offsets[row]; k < csr.row_offsets[row + 1]; ++k) {
            changed.values[k] = scale_exact(csr.values[k], exponent);
            coefficients << row << ',' << csr.column_indices[k] << ',' << csr.values[k] << ',' << changed.values[k] << ','
                         << (csr.values[k] != 0.0 && std::abs(csr.values[k]) <= 1e-12) << ",true\n";
        }
    }
    const auto cost = std::get<QuadraticCoefficients>(original.original_objective().coefficients());
    Matrix q{cost.Q.rows(), cost.Q.cols(), Vector(cost.Q.rows() * cost.Q.cols())};
    for (std::size_t i = 0; i < q.rows; ++i) for (std::size_t j = 0; j < q.cols; ++j) {
        q.values[i * q.cols + j] = cost.Q(i, j); objective << "Q," << i << ',' << j << ',' << cost.Q(i, j) << '\n';
    }
    Vector linear(cost.linear.values().begin(), cost.linear.values().end());
    for (std::size_t i = 0; i < linear.size(); ++i) objective << "linear," << i << ",0," << linear[i] << '\n';
    objective << "offset,0,0," << cost.offset << '\n';
    coefficients.flush(); bounds.flush(); objective.flush();
    if (!coefficients || !bounds || !objective || !identity) throw std::runtime_error("Diagnostic export write failed");
    if (!apply) return original;
    auto derived = original.identity(); derived.program.value += "/diagnostic-row-min-power2-v1";
    identity << "derived_problem=" << derived.problem.value << "\nderived_program=" << derived.program.value << '\n';
    auto built = make_convex_program({derived, QuadraticTerminal{std::move(q), std::move(linear), cost.offset},
        std::move(changed), {qp.variables().begin(), qp.variables().end()}, std::move(rows), std::nullopt});
    if (auto* result = std::get_if<ConvexProgram>(&built)) return *result;
    throw std::runtime_error("Derived power2 program construction refused");
}
}
