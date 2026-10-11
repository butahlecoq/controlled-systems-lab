#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/numeric/data.hpp>

#include <future>
#include <limits>
#include <stdexcept>
#include <type_traits>
#include <utility>

using namespace csl;
using namespace csl::numeric;

namespace {
template<class T> T accepted(Result<T> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
template<class T> void rejected(const Result<T>& result, DiagnosticCode code, const char* field) {
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    const auto& error = std::get<Diagnostic>(result);
    CHECK(error.code == code);
    CHECK(error.field == field);
    CHECK_FALSE(error.explanation.empty());
}
// Declare after futures: unwinding releases workers before their futures join.
class WorkerGate {
public:
    WorkerGate() : future_(promise_.get_future().share()) {}
    ~WorkerGate() { if (!opened_) { try { promise_.set_value(); } catch (...) {} } }
    std::shared_future<void> future() const { return future_; }
    void open() { promise_.set_value(); opened_ = true; }
private:
    std::promise<void> promise_;
    std::shared_future<void> future_;
    bool opened_{};
};
struct LayoutFixture {
    const char* name;
    Vector storage;
    std::ptrdiff_t row_stride, column_stride;
    DenseLayout layout;
};
}

// Catches destructive moves, stale assignment storage and layout-dependent retention.
TEST_CASE("all literal layouts retain values through copy and move assignment") {
    const double p = std::numeric_limits<double>::quiet_NaN();
    const std::vector<LayoutFixture> fixtures{
        {"row", {1, 2, 3, 4, 5, 6}, 3, 1, DenseLayout::row_major},
        {"column", {1, 4, 2, 5, 3, 6}, 1, 2, DenseLayout::column_major},
        {"padded row", {1, 2, 3, p, 4, 5, 6, p}, 4, 1, DenseLayout::row_major},
        {"padded column", {1, 4, p, 2, 5, p, 3, 6, p}, 1, 3, DenseLayout::column_major},
        {"interleaved", {1, p, 2, 4, 3, 5, p, 6, p}, 3, 2, DenseLayout::strided},
        {"noncoprime", {1, p, 2, p, 3, p, p, p, 4, p, 5, p, 6}, 8, 2, DenseLayout::strided}
    };
    for (const auto& fixture : fixtures) {
        CAPTURE(fixture.name);
        auto matrix = accepted(snapshot(DenseInput{fixture.storage, 2, 3,
            fixture.row_stride, fixture.column_stride, fixture.layout}));
        auto vector = accepted(snapshot_vector(Vector{7, 11, 13}));
        auto matrix_copy = matrix;
        auto vector_copy = vector;
        auto matrix_move = std::move(matrix);
        auto vector_move = std::move(vector);
        CHECK(accepted(multiply(matrix, vector)) == Vector{68, 161});
        CHECK(accepted(multiply(matrix_move, vector_move)) == Vector{68, 161});
        auto assigned_matrix = accepted(snapshot(Matrix{1, 1, {-99}}));
        auto assigned_vector = accepted(snapshot_vector(Vector{-99}));
        assigned_matrix = matrix_copy;
        assigned_vector = vector_copy;
        CHECK(accepted(multiply(assigned_matrix, assigned_vector)) == Vector{68, 161});
        assigned_matrix = std::move(matrix_copy);
        assigned_vector = std::move(vector_copy);
        CHECK(accepted(multiply(matrix_copy, vector_copy)) == Vector{68, 161});
        matrix = accepted(snapshot(Matrix{1, 1, {3}}));
        vector = accepted(snapshot_vector(Vector{-2}));
        CHECK(accepted(multiply(matrix, vector)) == Vector{-6});
        CHECK(accepted(multiply(assigned_matrix, assigned_vector)) == Vector{68, 161});
    }
}

// New signed/rectangular oracle catches swapped axes, discarded signs and omitted columns.
TEST_CASE("signed three by four oracle is independent of dense representation") {
    const double p = std::numeric_limits<double>::infinity();
    const std::vector<LayoutFixture> fixtures{
        {"row", {1, 2, -1, 3, -4, 0, 2, -1, 5, -3, 0, 2}, 4, 1, DenseLayout::row_major},
        {"column", {1, -4, 5, 2, 0, -3, -1, 2, 0, 3, -1, 2}, 1, 3, DenseLayout::column_major},
        {"interleaved", {1, p, p, -4, 2, p, 5, 0, -1, p, -3, 2, 3, p, 0, -1, p, p, 2}, 3, 4, DenseLayout::strided}
    };
    const auto vector = accepted(snapshot_vector(Vector{2, -3, 5, -7}));
    for (const auto& fixture : fixtures) {
        CAPTURE(fixture.name);
        const auto matrix = accepted(snapshot(DenseInput{fixture.storage, 3, 4,
            fixture.row_stride, fixture.column_stride, fixture.layout}));
        CHECK(accepted(multiply(matrix, vector)) == Vector{-30, 9, 5});
    }
    const auto sparse = accepted(snapshot(SparseMatrix{3, 4, {0, 4, 7, 10},
        {0, 1, 2, 3, 0, 2, 3, 0, 1, 3}, {1, 2, -1, 3, -4, 2, -1, 5, -3, 2}}));
    CHECK(accepted(multiply(sparse, vector)) == Vector{-30, 9, 5});
}

// A borrow outlives its original handle because an independent owning copy remains alive.
TEST_CASE("dense descriptors and vector spans survive original handle replacement") {
    auto matrix = accepted(snapshot(DenseInput{Vector{1, 99, 2, 4, 3, 5, 99, 6},
        2, 3, 3, 2, DenseLayout::strided}));
    auto vector = accepted(snapshot_vector(Vector{7, 11, 13}));
    const auto retaining_matrix = matrix;
    const auto retaining_vector = vector;
    const auto borrowed = std::get<DenseInput>(matrix.descriptor());
    const auto values = vector.values();
    matrix = accepted(snapshot(Matrix{1, 1, {-1}}));
    vector = accepted(snapshot_vector(Vector{2}));
    CHECK(accepted(multiply(matrix, vector)) == Vector{-2});
    CHECK(borrowed.storage[0] == 1);
    CHECK(borrowed.storage[3] == 4);
    CHECK(borrowed.storage[7] == 6);
    CHECK(Vector(values.begin(), values.end()) == Vector{7, 11, 13});
    CHECK(accepted(multiply(retaining_matrix, retaining_vector)) == Vector{68, 161});
}

TEST_CASE("CSR retained borrows preserve empty rows and explicit zero after move and replacement") {
    auto source = accepted(snapshot(SparseMatrix{4, 4, {0, 2, 2, 3, 5},
        {0, 3, 1, 0, 2}, {0, -2, 3, -1, 4}}));
    const auto moved = std::move(source);
    const auto descriptor = std::get<CsrInput>(source.descriptor());
    const auto vector = accepted(snapshot_vector(Vector{2, -3, 5, -7}));
    CHECK(accepted(multiply(source, vector)) == Vector{14, 0, -9, 18});
    source = accepted(snapshot(Matrix{1, 1, {9}}));
    CHECK(source(0, 0) == 9);
    CHECK(std::vector<std::size_t>(descriptor.row_offsets.begin(), descriptor.row_offsets.end()) ==
          std::vector<std::size_t>{0, 2, 2, 3, 5});
    CHECK(std::vector<std::size_t>(descriptor.column_indices.begin(), descriptor.column_indices.end()) ==
          std::vector<std::size_t>{0, 3, 1, 0, 2});
    CHECK(Vector(descriptor.values.begin(), descriptor.values.end()) == Vector{0, -2, 3, -1, 4});
    CHECK(moved(1, 3) == 0);
    CHECK(accepted(multiply(moved, vector)) == Vector{14, 0, -9, 18});
}

// All producer arrays and main-thread handles die before workers obtain their borrows.
TEST_CASE("gated joined workers retain dense and CSR views after source owners die") {
    std::vector<std::future<Vector>> workers;
    // Allocate before launch: a throwing push_back must not destroy a gated async temporary.
    workers.reserve(4);
    WorkerGate gate;
    {
        Vector producer{1, 99, 2, 4, 3, 5, 99, 6};
        Vector input{7, 11, 13};
        SparseMatrix csr{2, 3, {0, 3, 6}, {0, 1, 2, 0, 1, 2}, {1, 2, 3, 4, 5, 6}};
        const auto dense = accepted(snapshot(DenseInput{producer, 2, 3, 3, 2, DenseLayout::strided}));
        auto sparse = accepted(snapshot(csr));
        auto vector = accepted(snapshot_vector(input));
        for (int index = 0; index < 4; ++index) {
            auto matrix = index % 2 == 0 ? dense : std::move(sparse);
            workers.push_back(std::async(std::launch::async,
                [matrix = std::move(matrix), vector = std::move(vector), release = gate.future()] {
                    release.wait();
                    const auto descriptor = matrix.descriptor();
                    const double first = std::visit([](const auto& data) {
                        if constexpr (std::is_same_v<std::decay_t<decltype(data)>, DenseInput>)
                            return data.storage[0];
                        else return data.values[0];
                    }, descriptor);
                    if (first != 1 || vector.values()[2] != 13)
                        throw std::runtime_error("Retained buffer contents changed.");
                    auto result = multiply(matrix, vector);
                    if (const auto* error = std::get_if<Diagnostic>(&result))
                        throw std::runtime_error(error->field);
                    return std::get<Vector>(std::move(result));
                }));
        }
        producer.assign(1024, -99);
        input.assign(1024, -99);
        csr.values.assign(1024, -99);
        csr.column_indices.clear();
        csr.row_offsets.clear();
    }
    gate.open();
    std::vector<Vector> outputs;
    for (auto& worker : workers) outputs.push_back(worker.get());
    for (const auto& output : outputs) CHECK(output == Vector{68, 161});
    outputs[0][0] = -500;
    CHECK(outputs[0] == Vector{-500, 161});
    for (std::size_t index = 1; index < outputs.size(); ++index)
        CHECK(outputs[index] == Vector{68, 161});
}

TEST_CASE("noncoprime strides distinguish exact nonoverlap boundary from collision") {
    const Vector storage{2, 99, -1, 99, 3, 99, 4, 99, 9};
    const auto matrix = accepted(snapshot(DenseInput{storage, 2, 2, 4, 2, DenseLayout::strided}));
    CHECK(accepted(multiply(matrix, accepted(snapshot_vector(Vector{5, -2})))) == Vector{12, 7});
    rejected(snapshot(DenseInput{storage, 2, 3, 4, 2, DenseLayout::strided}),
        DiagnosticCode::unsupported, "numeric.dense.stride");
    rejected(snapshot(DenseInput{std::span<const double>(storage).first(6), 2, 2, 4, 2, DenseLayout::strided}),
        DiagnosticCode::invalid_input, "numeric.dense.storage");
    rejected(snapshot(DenseInput{storage, 2, 2, 4, 2, DenseLayout::row_major}),
        DiagnosticCode::unsupported, "numeric.dense.stride");
    rejected(snapshot(Matrix{2, 2, {2, -1, 3}}), DiagnosticCode::invalid_input, "numeric.dense.storage");
    rejected(multiply(matrix, accepted(snapshot_vector(Vector{5, -2, 0}))),
        DiagnosticCode::invalid_input, "numeric.multiply.shape");
}

TEST_CASE("zero ports drop poisonous storage and huge strides but still validate vector shape") {
    const Vector poison{std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::infinity()};
    const auto huge = std::numeric_limits<std::ptrdiff_t>::max();
    for (auto layout : {DenseLayout::row_major, DenseLayout::column_major, DenseLayout::strided}) {
        const auto no_control = accepted(snapshot(DenseInput{poison, 3, 0, huge, huge, layout}));
        const auto no_rows = accepted(snapshot(DenseInput{poison, 0, 4, huge, huge, layout}));
        const auto no_dimensions = accepted(snapshot(DenseInput{poison, 0, 0, 0, 0, layout}));
        for (const auto& view : {no_control, no_rows, no_dimensions}) {
            const auto descriptor = std::get<DenseInput>(view.descriptor());
            CHECK(descriptor.storage.size() == 0);
            CHECK(descriptor.row_stride == 0);
            CHECK(descriptor.column_stride == 0);
            CHECK(descriptor.layout == layout);
        }
        CHECK(no_control.rows() == 3);
        CHECK(no_rows.cols() == 4);
        CHECK(accepted(multiply(no_control, accepted(snapshot_vector({})))) == Vector{0, 0, 0});
        CHECK(accepted(multiply(no_rows, accepted(snapshot_vector(Vector{2, -3, 5, -7})))) == Vector{});
        CHECK(accepted(multiply(no_dimensions, accepted(snapshot_vector({})))) == Vector{});
        rejected(multiply(no_rows, accepted(snapshot_vector({}))), DiagnosticCode::invalid_input, "numeric.multiply.shape");
        rejected(multiply(no_control, accepted(snapshot_vector(Vector{1}))), DiagnosticCode::invalid_input, "numeric.multiply.shape");
        rejected(snapshot(DenseInput{poison, 3, 0, -1, 0, layout}), DiagnosticCode::unsupported, "numeric.dense.stride");
    }
    rejected(snapshot(DenseInput{poison, 0, 0, 0, 0, static_cast<DenseLayout>(77)}),
        DiagnosticCode::unsupported, "numeric.dense.layout");
    CHECK(accepted(multiply(accepted(snapshot(Matrix{1, 1, {-3}})),
        accepted(snapshot_vector(Vector{2})))) == Vector{-6});
}

TEST_CASE("MSVC iterator configuration matches active build mode") {
#ifdef _MSC_VER
#ifdef NDEBUG
    CHECK(_ITERATOR_DEBUG_LEVEL == 0);
#else
    CHECK(_ITERATOR_DEBUG_LEVEL == 2);
#endif
    MESSAGE("_MSC_VER=", _MSC_VER, ", _ITERATOR_DEBUG_LEVEL=", _ITERATOR_DEBUG_LEVEL);
#endif
    CHECK(accepted(multiply(accepted(snapshot(Matrix{1, 1, {2}})),
        accepted(snapshot_vector(Vector{-3})))) == Vector{-6});
}
