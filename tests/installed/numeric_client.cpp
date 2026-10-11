#include <csl/numeric/data.hpp>

#include <iostream>
#include <stdexcept>
#include <utility>

using namespace csl;
using namespace csl::numeric;

template<class T> T accepted(Result<T> result) {
    if (const auto* error = std::get_if<Diagnostic>(&result))
        throw std::runtime_error(error->field + ": " + error->explanation);
    return std::get<T>(std::move(result));
}

int main() {
    try {
        const auto vector = accepted(snapshot_vector(Vector{7, 11, 13}));
        const auto check = [&](const MatrixView& matrix) {
            if (accepted(multiply(matrix, vector)) != Vector{68, 161})
                throw std::runtime_error("Literal matrix-vector oracle failed.");
        };
        check(accepted(snapshot(Matrix{2, 3, {1, 2, 3, 4, 5, 6}})));
        const Vector columns{1, 4, 2, 5, 3, 6};
        check(accepted(snapshot(DenseInput{columns, 2, 3, 1, 2, DenseLayout::column_major})));
        const Vector strided{1, 99, 2, 4, 3, 5, 99, 6};
        check(accepted(snapshot(DenseInput{strided, 2, 3, 3, 2, DenseLayout::strided})));
        const auto retained = [] {
            SparseMatrix producer{2, 3, {0, 3, 6}, {0, 1, 2, 0, 1, 2}, {1, 2, 3, 4, 5, 6}};
            auto view = accepted(snapshot(producer));
            producer.values.assign(6, 0);
            return view;
        }();
        check(retained);
        const auto csr = std::get<CsrInput>(retained.descriptor());
        if (csr.values[5] != 6 || csr.column_indices[5] != 2 || vector.values()[2] != 13)
            throw std::runtime_error("Borrowed const storage descriptor failed.");
        const auto zero = accepted(snapshot(Matrix{2, 0, {}}));
        if (accepted(multiply(zero, accepted(snapshot_vector({})))) != Vector{0, 0})
            throw std::runtime_error("Zero-control shape failed.");
        const auto invalid = snapshot(Matrix{2, 3, {1}});
        const auto* error = std::get_if<Diagnostic>(&invalid);
        if (!error || error->code != DiagnosticCode::invalid_input || error->field != "numeric.dense.storage")
            throw std::runtime_error("Malformed storage diagnostic failed.");
        std::cout << "Installed numeric client: dense/CSR snapshots and retained literal fixture passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
