#pragma once

#include <csl/core/values.hpp>
#include <csl/core/diagnostics.hpp>
#include <memory>
#include <variant>
#include <span>

namespace csl::numeric {

enum class DenseLayout { row_major, column_major, strided };

// Borrowed synchronously by snapshot(). Strides are in double elements.
struct DenseInput {
    std::span<const double> storage;
    std::size_t rows{}, cols{};
    std::ptrdiff_t row_stride{}, column_stride{};
    DenseLayout layout{DenseLayout::row_major};
};

// Borrowed CSR descriptor for adapters; immutable spans never retain an owner.
struct CsrInput {
    std::size_t rows{}, cols{};
    std::span<const std::size_t> row_offsets, column_indices;
    std::span<const double> values;
};
using MatrixDescriptor = std::variant<DenseInput, CsrInput>;

template<class T> using Result = std::variant<T, Diagnostic>;

namespace detail { struct MatrixStorage; struct VectorStorage; }
class VectorView;

// Immutable, retaining handle. Creation validates and copies borrowed data.
class MatrixView {
public:
    MatrixView(const MatrixView&) = default;
    MatrixView& operator=(const MatrixView&) = default;
    std::size_t rows() const noexcept;
    std::size_t cols() const noexcept;
    // O(1) read-only borrow. Retain this view or a copy for the entire borrow lifetime.
    MatrixDescriptor descriptor() const noexcept;
    // Preconditions: row < rows(), column < cols(). Returns zero for absent CSR entries.
    double operator()(std::size_t row, std::size_t column) const noexcept;
private:
    explicit MatrixView(std::shared_ptr<const detail::MatrixStorage> storage);
    std::shared_ptr<const detail::MatrixStorage> storage_;
    friend Result<MatrixView> snapshot(DenseInput);
    friend Result<MatrixView> snapshot(const Matrix&);
    friend Result<MatrixView> snapshot(const SparseMatrix&);
    friend Result<Vector> multiply(const MatrixView&, const VectorView&);
};

class VectorView {
public:
    VectorView(const VectorView&) = default;
    VectorView& operator=(const VectorView&) = default;
    std::size_t size() const noexcept;
    // O(1) read-only borrow. Retain this view or a copy for the entire borrow lifetime.
    std::span<const double> values() const noexcept;
    // Precondition: index < size().
    double operator[](std::size_t index) const noexcept;
private:
    explicit VectorView(std::shared_ptr<const detail::VectorStorage> storage);
    std::shared_ptr<const detail::VectorStorage> storage_;
    friend Result<VectorView> snapshot_vector(std::span<const double>);
    friend Result<Vector> multiply(const MatrixView&, const VectorView&);
};

Result<MatrixView> snapshot(DenseInput);
Result<MatrixView> snapshot(const Matrix&);
Result<MatrixView> snapshot(const SparseMatrix&);
Result<VectorView> snapshot_vector(std::span<const double>);
Result<Vector> multiply(const MatrixView&, const VectorView&);

} // namespace csl::numeric
