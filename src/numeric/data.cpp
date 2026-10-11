#include <csl/numeric/data.hpp>

#include <algorithm>
#include <cassert>
#include <cmath>
#include <limits>
#include <numeric>
#include <type_traits>
#include <utility>

namespace csl::numeric::detail {
struct DenseStorage {
    std::size_t rows, cols, row_stride, column_stride;
    DenseLayout layout;
    Vector values;
};
struct MatrixStorage { std::variant<DenseStorage, SparseMatrix> data; };
struct VectorStorage { Vector values; };
} // namespace csl::numeric::detail

namespace csl::numeric {
namespace {
Diagnostic invalid(const char* field, const char* explanation) {
    return {DiagnosticCode::invalid_input, field, explanation};
}
Diagnostic unsupported(const char* field, const char* explanation) {
    return {DiagnosticCode::unsupported, field, explanation};
}
bool product(std::size_t a, std::size_t b, std::size_t& result) {
    if (b != 0 && a > std::numeric_limits<std::size_t>::max() / b) return false;
    result = a * b;
    return true;
}
bool sum(std::size_t a, std::size_t b, std::size_t& result) {
    if (a > std::numeric_limits<std::size_t>::max() - b) return false;
    result = a + b;
    return true;
}
bool finite(std::span<const double> values) {
    return std::all_of(values.begin(), values.end(), [](double value) { return std::isfinite(value); });
}
Result<detail::DenseStorage> parse_dense(DenseInput input) {
    switch (input.layout) {
    case DenseLayout::row_major:
    case DenseLayout::column_major:
    case DenseLayout::strided: break;
    default: return unsupported("numeric.dense.layout", "Unknown dense layout.");
    }
    if (input.row_stride < 0 || input.column_stride < 0)
        return unsupported("numeric.dense.stride", "Negative strides are unsupported.");
    // An empty shape has no addressed coefficients, regardless of its strides.
    if (input.rows == 0 || input.cols == 0)
        return detail::DenseStorage{input.rows, input.cols, 0, 0, input.layout, {}};
    if (input.row_stride == 0 || input.column_stride == 0)
        return unsupported("numeric.dense.stride", "Nonempty shapes require positive strides.");
    const auto rs = static_cast<std::size_t>(input.row_stride);
    const auto cs = static_cast<std::size_t>(input.column_stride);
    if ((input.layout == DenseLayout::row_major && (cs != 1 || rs < input.cols)) ||
        (input.layout == DenseLayout::column_major && (rs != 1 || cs < input.rows)))
        return unsupported("numeric.dense.stride", "Strides are inconsistent with the declared layout.");
    // A collision requires dr*rs == dc*cs. The smallest positive differences
    // are dr=cs/gcd(rs,cs), dc=rs/gcd(rs,cs); both must fit inside the shape.
    const auto divisor = std::gcd(rs, cs);
    if (input.rows > cs / divisor && input.cols > rs / divisor)
        return unsupported("numeric.dense.stride", "Overlapping coefficient addresses are unsupported.");
    std::size_t row_extent{}, column_extent{}, last{}, extent{};
    if (!product(input.rows - 1, rs, row_extent) ||
        !product(input.cols - 1, cs, column_extent) ||
        !sum(row_extent, column_extent, last) || !sum(last, 1, extent))
        return invalid("numeric.dense.extent", "Dense addressed extent overflows size_t.");
    if (input.storage.size() < extent)
        return invalid("numeric.dense.storage", "Dense storage does not cover the addressed extent.");
    for (std::size_t row = 0; row < input.rows; ++row)
        for (std::size_t column = 0; column < input.cols; ++column)
            if (!std::isfinite(input.storage[row * rs + column * cs]))
                return invalid("numeric.values", "Numeric coefficients must be finite doubles.");
    const auto addressed = input.storage.first(extent);
    return detail::DenseStorage{input.rows, input.cols, rs, cs, input.layout,
                               Vector(addressed.begin(), addressed.end())};
}
} // namespace

MatrixView::MatrixView(std::shared_ptr<const detail::MatrixStorage> storage) : storage_(std::move(storage)) {}
VectorView::VectorView(std::shared_ptr<const detail::VectorStorage> storage) : storage_(std::move(storage)) {}
std::size_t MatrixView::rows() const noexcept {
    return std::visit([](const auto& data) { return data.rows; }, storage_->data);
}
std::size_t MatrixView::cols() const noexcept {
    return std::visit([](const auto& data) { return data.cols; }, storage_->data);
}
MatrixDescriptor MatrixView::descriptor() const noexcept {
    return std::visit([](const auto& data) -> MatrixDescriptor {
        if constexpr (std::is_same_v<std::decay_t<decltype(data)>, detail::DenseStorage>) {
            // Dense strides were parsed from ptrdiff_t and never widened afterward.
            return DenseInput{data.values, data.rows, data.cols,
                              static_cast<std::ptrdiff_t>(data.row_stride),
                              static_cast<std::ptrdiff_t>(data.column_stride), data.layout};
        } else {
            return CsrInput{data.rows, data.cols, data.row_offsets, data.column_indices, data.values};
        }
    }, storage_->data);
}
double MatrixView::operator()(std::size_t row, std::size_t column) const noexcept {
    assert(row < rows() && column < cols());
    return std::visit([row, column](const auto& data) -> double {
        if constexpr (std::is_same_v<std::decay_t<decltype(data)>, detail::DenseStorage>) {
            return data.values[row * data.row_stride + column * data.column_stride];
        } else {
            const auto first = data.column_indices.begin() + static_cast<std::ptrdiff_t>(data.row_offsets[row]);
            const auto last = data.column_indices.begin() + static_cast<std::ptrdiff_t>(data.row_offsets[row + 1]);
            const auto found = std::lower_bound(first, last, column);
            if (found == last || *found != column) return 0;
            return data.values[static_cast<std::size_t>(found - data.column_indices.begin())];
        }
    }, storage_->data);
}
std::size_t VectorView::size() const noexcept { return storage_->values.size(); }
std::span<const double> VectorView::values() const noexcept { return storage_->values; }
double VectorView::operator[](std::size_t index) const noexcept {
    assert(index < size());
    return storage_->values[index];
}
Result<MatrixView> snapshot(DenseInput input) {
    auto parsed = parse_dense(input);
    if (const auto* failure = std::get_if<Diagnostic>(&parsed)) return *failure;
    return MatrixView(std::make_shared<const detail::MatrixStorage>(
        detail::MatrixStorage{std::get<detail::DenseStorage>(std::move(parsed))}));
}
Result<MatrixView> snapshot(const Matrix& input) {
    std::size_t count{};
    if (!product(input.rows, input.cols, count))
        return invalid("numeric.dense.shape", "Dense shape product overflows size_t.");
    if (count != input.values.size())
        return invalid("numeric.dense.storage", "Authored dense storage must equal rows times columns.");
    if (count == 0) return snapshot(DenseInput{{}, input.rows, input.cols, 0, 0, DenseLayout::row_major});
    if (input.cols > static_cast<std::size_t>(std::numeric_limits<std::ptrdiff_t>::max()))
        return invalid("numeric.dense.extent", "Row-major stride cannot be represented by ptrdiff_t.");
    return snapshot(DenseInput{input.values, input.rows, input.cols,
                              static_cast<std::ptrdiff_t>(input.cols), 1, DenseLayout::row_major});
}
Result<MatrixView> snapshot(const SparseMatrix& input) {
    if (input.values.size() != input.column_indices.size())
        return invalid("numeric.csr.storage", "CSR values and column indices must have equal sizes.");
    std::size_t offset_count{};
    if (!sum(input.rows, 1, offset_count) || input.row_offsets.size() != offset_count)
        return invalid("numeric.csr.offsets", "CSR requires rows plus one offsets without overflow.");
    if (input.row_offsets.front() != 0 || input.row_offsets.back() != input.values.size())
        return invalid("numeric.csr.offsets", "CSR offsets must start at zero and end at nnz.");
    for (std::size_t row = 0; row < input.rows; ++row) {
        const auto first = input.row_offsets[row];
        const auto last = input.row_offsets[row + 1];
        if (first > last || last > input.values.size())
            return invalid("numeric.csr.offsets", "CSR offsets must be nondecreasing and within nnz.");
        for (auto index = first; index < last; ++index) {
            if (input.column_indices[index] >= input.cols ||
                (index > first && input.column_indices[index - 1] >= input.column_indices[index]))
                return invalid("numeric.csr.indices", "CSR columns must be in range, sorted and unique within each row.");
        }
    }
    if (!finite(input.values)) return invalid("numeric.values", "CSR values must be finite doubles.");
    return MatrixView(std::make_shared<const detail::MatrixStorage>(detail::MatrixStorage{input}));
}
Result<VectorView> snapshot_vector(std::span<const double> input) {
    if (!finite(input)) return invalid("numeric.values", "Vector values must be finite doubles.");
    return VectorView(std::make_shared<const detail::VectorStorage>(
        detail::VectorStorage{Vector(input.begin(), input.end())}));
}
Result<Vector> multiply(const MatrixView& matrix, const VectorView& vector) {
    if (matrix.cols() != vector.size())
        return invalid("numeric.multiply.shape", "Matrix columns must equal vector length, including empty shapes.");
    const auto& values = vector.storage_->values;
    Vector result(matrix.rows(), 0);
    std::visit([&](const auto& data) {
        for (std::size_t row = 0; row < data.rows; ++row) {
            double value = 0;
            if constexpr (std::is_same_v<std::decay_t<decltype(data)>, detail::DenseStorage>) {
                for (std::size_t column = 0; column < data.cols; ++column)
                    value += data.values[row * data.row_stride + column * data.column_stride] * values[column];
            } else {
                for (auto index = data.row_offsets[row]; index < data.row_offsets[row + 1]; ++index)
                    value += data.values[index] * values[data.column_indices[index]];
            }
            result[row] = value;
        }
    }, matrix.storage_->data);
    if (!finite(result)) return invalid("numeric.multiply.arithmetic", "Multiplication produced a nonfinite result.");
    return result;
}
} // namespace csl::numeric
