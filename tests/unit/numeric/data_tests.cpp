#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/numeric/data.hpp>

#include <future>
#include <limits>
#include <thread>
#include <type_traits>
#include <utility>

using namespace csl;
using namespace csl::numeric;

static_assert(!std::is_default_constructible_v<MatrixView>);
static_assert(!std::is_default_constructible_v<VectorView>);
static_assert(std::is_same_v<decltype(std::declval<const MatrixView&>()(0, 0)), double>);
static_assert(std::is_same_v<decltype(std::declval<const VectorView&>()[0]), double>);
static_assert(!std::is_constructible_v<MatrixView, std::shared_ptr<const void>>);
template<class T>
concept VectorScalar = requires(std::span<const T> input_values) { snapshot_vector(input_values); };
static_assert(VectorScalar<double>);
static_assert(!VectorScalar<float>);

namespace {
template<class T>
T accepted(Result<T> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
template<class T>
void rejected(const Result<T>& result, DiagnosticCode code, const char* field) {
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    const auto& diagnostic = std::get<Diagnostic>(result);
    CHECK(diagnostic.code == code);
    CHECK(diagnostic.field == field);
    CHECK_FALSE(diagnostic.explanation.empty());
}
const Vector input{7, 11, 13};
}

// Wrong indexing, square-only loops, or ignoring padding must break this oracle.
TEST_CASE("dense layouts multiply the non-square literal oracle") {
    Vector storage;
    DenseInput descriptor{};
    SUBCASE("contiguous row-major") {
        storage = {1, 2, 3, 4, 5, 6};
        descriptor = {storage, 2, 3, 3, 1, DenseLayout::row_major};
    }
    SUBCASE("contiguous column-major") {
        storage = {1, 4, 2, 5, 3, 6};
        descriptor = {storage, 2, 3, 1, 2, DenseLayout::column_major};
    }
    SUBCASE("padded row-major") {
        storage = {1, 2, 3, 99, 99, 4, 5, 6};
        descriptor = {storage, 2, 3, 5, 1, DenseLayout::row_major};
    }
    SUBCASE("padded column-major") {
        storage = {1, 4, 99, 2, 5, 99, 3, 6};
        descriptor = {storage, 2, 3, 1, 3, DenseLayout::column_major};
    }
    SUBCASE("general interleaved positive strides") {
        storage = {1, 99, 2, 4, 3, 5, 99, 6};
        descriptor = {storage, 2, 3, 3, 2, DenseLayout::strided};
    }
    SUBCASE("strided snapshot survives mutable descriptor storage") {
        storage = {1, 99, 2, 4, 3, 5, 99, 6};
        auto retained = accepted(snapshot(DenseInput{storage, 2, 3, 3, 2, DenseLayout::strided}));
        storage.assign(8, 0);
        CHECK(accepted(multiply(retained, accepted(snapshot_vector(input)))) == Vector{68, 161});
        return;
    }
    const auto matrix = accepted(snapshot(descriptor));
    const auto vector = accepted(snapshot_vector(input));
    CHECK(accepted(multiply(matrix, vector)) == Vector{68, 161});
    CHECK(matrix.rows() == 2);
    CHECK(matrix.cols() == 3);
    CHECK(matrix(1, 2) == 6);
    CHECK(vector.size() == 3);
    CHECK(vector[1] == 11);
}

TEST_CASE("authored row-major and CSR snapshots use the same literal oracle") {
    const auto vector = accepted(snapshot_vector(input));
    SUBCASE("authored dense") {
        auto matrix = accepted(snapshot(Matrix{2, 3, {1, 2, 3, 4, 5, 6}}));
        CHECK(accepted(multiply(matrix, vector)) == Vector{68, 161});
    }
    SUBCASE("authored CSR") {
        auto matrix = accepted(snapshot(SparseMatrix{2, 3, {0, 3, 6}, {0, 1, 2, 0, 1, 2}, {1, 2, 3, 4, 5, 6}}));
        CHECK(accepted(multiply(matrix, vector)) == Vector{68, 161});
        CHECK(matrix(1, 2) == 6);
    }
    SUBCASE("implicit zeros and empty rows in CSR") {
        auto matrix = accepted(snapshot(SparseMatrix{3, 3, {0, 1, 1, 2}, {2, 0}, {2, 4}}));
        CHECK(accepted(multiply(matrix, vector)) == Vector{26, 0, 28});
        CHECK(matrix(0, 0) == 0);
    }
}

TEST_CASE("empty shapes preserve dimensions and zero-control multiplication") {
    SUBCASE("zero rows") {
        auto matrix = accepted(snapshot(Matrix{0, 3, {}}));
        CHECK(matrix.rows() == 0);
        CHECK(matrix.cols() == 3);
        CHECK(accepted(multiply(matrix, accepted(snapshot_vector(input)))) == Vector{});
    }
    SUBCASE("zero columns") {
        auto matrix = accepted(snapshot(Matrix{2, 0, {}}));
        CHECK(matrix.rows() == 2);
        CHECK(matrix.cols() == 0);
        CHECK(accepted(multiply(matrix, accepted(snapshot_vector({})))) == Vector{0, 0});
    }
    SUBCASE("zero by zero CSR") {
        auto matrix = accepted(snapshot(SparseMatrix{0, 0, {0}, {}, {}}));
        CHECK(matrix.rows() == 0);
        CHECK(matrix.cols() == 0);
        CHECK(accepted(multiply(matrix, accepted(snapshot_vector({})))) == Vector{});
    }
    SUBCASE("CSR with no columns") {
        auto matrix = accepted(snapshot(SparseMatrix{2, 0, {0, 0, 0}, {}, {}}));
        CHECK(accepted(multiply(matrix, accepted(snapshot_vector({})))) == Vector{0, 0});
    }
    SUBCASE("CSR with no rows") {
        auto matrix = accepted(snapshot(SparseMatrix{0, 3, {0}, {}, {}}));
        CHECK(matrix.cols() == 3);
        CHECK(accepted(multiply(matrix, accepted(snapshot_vector(input)))) == Vector{});
    }
    SUBCASE("empty strided descriptor needs no address") {
        auto matrix = accepted(snapshot(DenseInput{{}, 2, 0, 0, 0, DenseLayout::strided}));
        CHECK(accepted(multiply(matrix, accepted(snapshot_vector({})))) == Vector{0, 0});
    }
    // Empty behavior accompanies nonempty behavior, rather than absence alone.
    CHECK(accepted(multiply(accepted(snapshot(Matrix{1, 1, {3}})),
                            accepted(snapshot_vector(Vector{2})))) == Vector{6});
}

TEST_CASE("dense seams diagnose malformed shape layout stride and extent") {
    const Vector storage{1, 2, 3, 4, 5, 6};
    SUBCASE("authored storage too short") {
        rejected(snapshot(Matrix{2, 3, {1, 2}}), DiagnosticCode::invalid_input, "numeric.dense.storage");
    }
    SUBCASE("authored storage too long") {
        rejected(snapshot(Matrix{1, 1, {1, 2}}), DiagnosticCode::invalid_input, "numeric.dense.storage");
    }
    SUBCASE("shape product overflow") {
        rejected(snapshot(Matrix{std::numeric_limits<std::size_t>::max(), 2, {}}), DiagnosticCode::invalid_input, "numeric.dense.shape");
    }
    SUBCASE("unknown layout") {
        rejected(snapshot(DenseInput{storage, 2, 3, 3, 1, static_cast<DenseLayout>(99)}), DiagnosticCode::unsupported, "numeric.dense.layout");
    }
    SUBCASE("negative stride") {
        rejected(snapshot(DenseInput{storage, 2, 3, -3, 1, DenseLayout::strided}), DiagnosticCode::unsupported, "numeric.dense.stride");
    }
    SUBCASE("zero stride") {
        rejected(snapshot(DenseInput{storage, 2, 3, 3, 0, DenseLayout::strided}), DiagnosticCode::unsupported, "numeric.dense.stride");
    }
    SUBCASE("overlap despite positive strides") {
        rejected(snapshot(DenseInput{storage, 3, 2, 2, 4, DenseLayout::strided}), DiagnosticCode::unsupported, "numeric.dense.stride");
    }
    SUBCASE("row-major label cannot bless overlap") {
        rejected(snapshot(DenseInput{storage, 2, 3, 2, 1, DenseLayout::row_major}), DiagnosticCode::unsupported, "numeric.dense.stride");
    }
    SUBCASE("column-major label cannot bless overlap") {
        rejected(snapshot(DenseInput{storage, 2, 3, 1, 1, DenseLayout::column_major}), DiagnosticCode::unsupported, "numeric.dense.stride");
    }
    SUBCASE("layout label inconsistent with strides") {
        rejected(snapshot(DenseInput{storage, 2, 3, 1, 2, DenseLayout::row_major}), DiagnosticCode::unsupported, "numeric.dense.stride");
    }
    SUBCASE("extent too short") {
        rejected(snapshot(DenseInput{storage, 2, 3, 5, 1, DenseLayout::row_major}), DiagnosticCode::invalid_input, "numeric.dense.storage");
    }
    SUBCASE("extent addition overflow before indexing") {
        const auto stride = std::numeric_limits<std::ptrdiff_t>::max();
        rejected(snapshot(DenseInput{storage, 3, 2, stride, stride - 1, DenseLayout::strided}), DiagnosticCode::invalid_input, "numeric.dense.extent");
    }
    SUBCASE("extent multiplication overflow before indexing") {
        rejected(snapshot(DenseInput{storage, std::numeric_limits<std::size_t>::max(), 1, 3, 1, DenseLayout::strided}), DiagnosticCode::invalid_input, "numeric.dense.extent");
    }
    SUBCASE("extent final plus one overflow before indexing") {
        rejected(snapshot(DenseInput{storage, 3, 2, std::numeric_limits<std::ptrdiff_t>::max(), 1, DenseLayout::row_major}), DiagnosticCode::invalid_input, "numeric.dense.extent");
    }
    SUBCASE("coprime strides collide only beyond adjacent rows") {
        rejected(snapshot(DenseInput{storage, 4, 3, 2, 3, DenseLayout::strided}), DiagnosticCode::unsupported, "numeric.dense.stride");
    }
}

TEST_CASE("coprime strided layout accepts the exact nonoverlap boundary") {
    const Vector storage{1, 99, 3, 2, 5, 4, 99, 6};
    auto matrix = accepted(snapshot(DenseInput{storage, 3, 2, 2, 3, DenseLayout::strided}));
    CHECK(accepted(multiply(matrix, accepted(snapshot_vector(Vector{7, 11})))) == Vector{29, 65, 101});
}

// Adapters map storage once; wrong spans/strides or an extra snapshot copy must fail.
TEST_CASE("coarse const storage descriptors support adapters without another snapshot copy") {
    const auto vector = accepted(snapshot_vector(input));
    CHECK(vector.values()[2] == 13);
    CHECK(vector.values().data() == VectorView(vector).values().data());
    static_assert(std::is_same_v<decltype(vector.values())::element_type, const double>);
    SUBCASE("dense mapped coefficients preserve strides and layout") {
        const auto matrix = [] {
            Vector producer{1, 99, 2, 4, 3, 5, 99, 6, 777};
            auto view = accepted(snapshot(DenseInput{producer, 2, 3, 3, 2, DenseLayout::strided}));
            producer.assign(9, 0);
            return view;
        }();
        const auto descriptor = matrix.descriptor();
        REQUIRE(std::holds_alternative<DenseInput>(descriptor));
        const auto dense = std::get<DenseInput>(descriptor);
        CHECK(dense.rows == 2);
        CHECK(dense.cols == 3);
        CHECK(dense.row_stride == 3);
        CHECK(dense.column_stride == 2);
        CHECK(dense.layout == DenseLayout::strided);
        CHECK(dense.storage.size() == 8); // trailing producer data is not retained.
        CHECK(dense.storage.data() == std::get<DenseInput>(MatrixView(matrix).descriptor()).storage.data());
        auto worker = std::async(std::launch::async, [matrix, vector] {
            const auto retained = std::get<DenseInput>(matrix.descriptor());
            Vector mapped(retained.rows, 0);
            for (std::size_t row = 0; row < retained.rows; ++row)
                for (std::size_t column = 0; column < retained.cols; ++column)
                    mapped[row] += retained.storage[row * static_cast<std::size_t>(retained.row_stride) +
                                                   column * static_cast<std::size_t>(retained.column_stride)] * vector.values()[column];
            return mapped;
        });
        CHECK(worker.get() == Vector{68, 161});
    }
    SUBCASE("CSR adapter sees validated sorted nonzeros") {
        const auto matrix = accepted(snapshot(SparseMatrix{2, 3, {0, 3, 6}, {0, 1, 2, 0, 1, 2}, {1, 2, 3, 4, 5, 6}}));
        const auto descriptor = matrix.descriptor();
        REQUIRE(std::holds_alternative<CsrInput>(descriptor));
        const auto sparse = std::get<CsrInput>(descriptor);
        static_assert(std::is_same_v<decltype(sparse.values)::element_type, const double>);
        static_assert(std::is_same_v<decltype(sparse.row_offsets)::element_type, const std::size_t>);
        CHECK(sparse.rows == 2);
        CHECK(sparse.cols == 3);
        CHECK(sparse.values.data() == std::get<CsrInput>(MatrixView(matrix).descriptor()).values.data());
        Vector mapped(sparse.rows, 0);
        for (std::size_t row = 0; row < sparse.rows; ++row)
            for (auto index = sparse.row_offsets[row]; index < sparse.row_offsets[row + 1]; ++index)
                mapped[row] += sparse.values[index] * vector.values()[sparse.column_indices[index]];
        CHECK(mapped == Vector{68, 161});
    }
}

TEST_CASE("CSR seams diagnose malformed offsets indices and value storage") {
    SparseMatrix source{2, 3, {0, 3, 6}, {0, 1, 2, 0, 1, 2}, {1, 2, 3, 4, 5, 6}};
    const char* field = "numeric.csr.offsets";
    SUBCASE("missing offsets") { source.row_offsets = {}; }
    SUBCASE("nonzero first offset") { source.row_offsets[0] = 1; }
    SUBCASE("descending offsets") { source.row_offsets = {0, 5, 4}; }
    SUBCASE("offset outside values") { source.row_offsets = {0, 7, 6}; }
    SUBCASE("wrong last offset") { source.row_offsets[2] = 5; }
    SUBCASE("rows plus one overflow") { source.rows = std::numeric_limits<std::size_t>::max(); }
    SUBCASE("mismatched values and indices") { source.column_indices.pop_back(); field = "numeric.csr.storage"; }
    SUBCASE("index out of range") { source.column_indices[2] = 3; field = "numeric.csr.indices"; }
    SUBCASE("unsorted columns") { source.column_indices[0] = 1; source.column_indices[1] = 0; field = "numeric.csr.indices"; }
    SUBCASE("duplicate columns") { source.column_indices[1] = 0; field = "numeric.csr.indices"; }
    SUBCASE("zero columns cannot contain nonzeros") { source.cols = 0; field = "numeric.csr.indices"; }
    rejected(snapshot(source), DiagnosticCode::invalid_input, field);
}

TEST_CASE("finite-value policy covers coefficients and vectors but ignores dense padding") {
    const auto infinity = std::numeric_limits<double>::infinity();
    const auto nan = std::numeric_limits<double>::quiet_NaN();
    rejected(snapshot(Matrix{1, 1, {infinity}}), DiagnosticCode::invalid_input, "numeric.values");
    rejected(snapshot(Matrix{1, 1, {nan}}), DiagnosticCode::invalid_input, "numeric.values");
    rejected(snapshot_vector(Vector{nan}), DiagnosticCode::invalid_input, "numeric.values");
    rejected(snapshot_vector(Vector{-infinity}), DiagnosticCode::invalid_input, "numeric.values");
    rejected(snapshot(SparseMatrix{1, 1, {0, 1}, {0}, {nan}}), DiagnosticCode::invalid_input, "numeric.values");
    Vector padded{1, nan, infinity, 2, nan};
    auto matrix = accepted(snapshot(DenseInput{padded, 2, 1, 3, 1, DenseLayout::row_major}));
    CHECK(accepted(multiply(matrix, accepted(snapshot_vector(Vector{7})))) == Vector{7, 14});
}

TEST_CASE("multiply rejects mismatched vector shape and nonfinite arithmetic") {
    auto matrix = accepted(snapshot(Matrix{2, 3, {1, 2, 3, 4, 5, 6}}));
    rejected(multiply(matrix, accepted(snapshot_vector(Vector{7, 11}))), DiagnosticCode::invalid_input, "numeric.multiply.shape");
    auto empty = accepted(snapshot(Matrix{0, 3, {}}));
    rejected(multiply(empty, accepted(snapshot_vector({}))), DiagnosticCode::invalid_input, "numeric.multiply.shape");
    auto large = accepted(snapshot(Matrix{1, 1, {std::numeric_limits<double>::max()}}));
    rejected(multiply(large, accepted(snapshot_vector(Vector{2}))), DiagnosticCode::invalid_input, "numeric.multiply.arithmetic");
}

TEST_CASE("retained snapshots survive producer scope mutable aliases and detached asynchronous use") {
    auto make_dense = [] {
        Matrix producer{2, 3, {1, 2, 3, 4, 5, 6}};
        auto view = accepted(snapshot(producer));
        producer.values.assign(6, 99);
        return view;
    };
    auto make_sparse = [] {
        SparseMatrix producer{2, 3, {0, 3, 6}, {0, 1, 2, 0, 1, 2}, {1, 2, 3, 4, 5, 6}};
        auto view = accepted(snapshot(producer));
        producer.values.assign(6, 99);
        producer.row_offsets.clear();
        return view;
    };
    auto make_vector = [] {
        Vector producer{7, 11, 13};
        auto view = accepted(snapshot_vector(producer));
        producer.assign(3, 99);
        return view;
    };
    const auto dense = make_dense();
    const auto sparse = make_sparse();
    const auto vector = make_vector();
    std::vector<std::future<Result<Vector>>> workers;
    for (int worker = 0; worker < 8; ++worker) {
        workers.push_back(std::async(std::launch::async, [dense, sparse, vector, worker] {
            return multiply(worker % 2 == 0 ? dense : sparse, vector);
        }));
    }
    for (auto& result : workers) CHECK(accepted(result.get()) == Vector{68, 161});
    CHECK(dense(0, 1) == 2);
    CHECK(sparse(1, 2) == 6);
    CHECK(vector[2] == 13);

    // The detached worker is gated until all producer handles have gone away.
    std::promise<void> release;
    auto gate = release.get_future();
    std::promise<Result<Vector>> completion;
    auto result = completion.get_future();
    {
        auto retained_matrix = make_dense();
        auto retained_vector = make_vector();
        std::thread([matrix = retained_matrix, values = retained_vector,
                     gate = std::move(gate), completion = std::move(completion)]() mutable {
            gate.wait();
            completion.set_value(multiply(matrix, values));
        }).detach();
    }
    release.set_value();
    CHECK(accepted(result.get()) == Vector{68, 161});
}
