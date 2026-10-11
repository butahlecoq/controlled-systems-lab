#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/sets/data.hpp>

#include <type_traits>

using namespace csl;
using namespace csl::sets;

static_assert(!std::is_default_constructible_v<SetData>);
static_assert(std::is_same_v<decltype(std::declval<SetData>().metadata()), std::shared_ptr<const Metadata>>);

namespace {
template<class T> T accepted(std::variant<T, Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
void rejected(const Result<SetData>& result, const char* field) {
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).code == DiagnosticCode::invalid_input);
    CHECK(std::get<Diagnostic>(result).field == field);
}
numeric::MatrixView matrix(std::size_t rows, std::size_t cols, Vector values) {
    return accepted(numeric::snapshot(Matrix{rows, cols, std::move(values)}));
}
numeric::VectorView vector(Vector values) { return accepted(numeric::snapshot_vector(values)); }
Description plane() { return {{"segment"}, 2, {"x", "y"}}; }
HRepresentation segment_h() {
    return {matrix(2, 2, {-1, 0, 1, 0}), vector({1, 2}), matrix(1, 2, {0, 1}), vector({0})};
}
VRepresentation segment_v() { return {matrix(2, 2, {-1, 0, 2, 0}), matrix(0, 2, {})}; }
AffineDimensionClaim dimension(std::size_t value) { return {DimensionValue{value}, Unestablished{}}; }
}

// Losing an equality, transposing rows, or confusing ambient and affine dimension breaks this.
TEST_CASE("literal H segment retains equalities and supplied affine dimension") {
    auto set = accepted(make_h(plane(), segment_h(), dimension(1)));
    auto info = set.metadata();
    CHECK(info->set.dimension == 2);
    CHECK(info->id.value == "segment");
    CHECK(info->coordinate_labels == std::vector<std::string>{"x", "y"});
    REQUIRE(info->affine_dimension.has_value());
    CHECK(std::get<DimensionValue>(info->affine_dimension->claim.value).value == 1);
    CHECK(info->affine_dimension->origin == DimensionOrigin::supplied);
    CHECK(std::holds_alternative<Unestablished>(info->affine_dimension->claim.support));
    CHECK(info->set.bounded == SetProperty::unknown);
    auto h = std::get<HRepresentation>(set.representation());
    CHECK(h.inequalities(0, 0) == -1);
    CHECK(h.inequalities(1, 0) == 1);
    CHECK(h.upper_bounds[0] == 1);
    CHECK(h.upper_bounds[1] == 2);
    CHECK(h.equalities.rows() == 1);
    CHECK(h.equalities(0, 0) == 0);
    CHECK(h.equalities(0, 1) == 1);
    CHECK(h.equality_values[0] == 0);
}

TEST_CASE("supplied equivalent V segment keeps endpoints and a different representation identity") {
    auto h = accepted(make_h(plane(), segment_h(), dimension(1)));
    auto v = accepted(make_v(plane(), segment_v(), dimension(1)));
    CHECK(v.metadata()->set.representation.value != h.metadata()->set.representation.value);
    CHECK(v.metadata()->set.bounded == SetProperty::yes);
    auto data = std::get<VRepresentation>(v.representation());
    CHECK(data.vertices.rows() == 2);
    CHECK(data.vertices(0, 0) == -1);
    CHECK(data.vertices(0, 1) == 0);
    CHECK(data.vertices(1, 0) == 2);
    CHECK(data.vertices(1, 1) == 0);
    CHECK(data.rays.rows() == 0);
    CHECK(data.rays.cols() == 2);
}

TEST_CASE("rays and opposite rays preserve unbounded and lineality descriptions without rank inference") {
    auto ray = accepted(make_v(plane(), {matrix(1, 2, {0, 0}), matrix(1, 2, {1, 0})}));
    CHECK_FALSE(ray.metadata()->affine_dimension.has_value());
    CHECK(ray.metadata()->set.bounded == SetProperty::unknown);
    auto r = std::get<VRepresentation>(ray.representation());
    CHECK(r.rays(0, 0) == 1);
    CHECK(r.rays(0, 1) == 0);
    auto line = accepted(make_v(plane(), {matrix(1, 2, {0, 0}), matrix(2, 2, {1, 0, -1, 0})}, dimension(1)));
    CHECK(std::get<VRepresentation>(line.representation()).rays(1, 0) == -1);
}

TEST_CASE("elementary cases remain distinct in zero and positive ambient dimensions") {
    for (auto n : {std::size_t{0}, std::size_t{2}}) {
        Description desc{{"elementary"}, n, {}};
        auto empty = accepted(make_empty(desc));
        auto universe = accepted(make_universal(desc));
        auto point = accepted(make_singleton(desc, vector(Vector(n, 0))));
        CHECK(std::holds_alternative<EmptyRepresentation>(empty.representation()));
        CHECK(std::holds_alternative<UniversalRepresentation>(universe.representation()));
        CHECK(std::holds_alternative<SingletonRepresentation>(point.representation()));
        CHECK(std::holds_alternative<EmptyAffineDimension>(empty.metadata()->affine_dimension->claim.value));
        CHECK(std::get<DimensionValue>(universe.metadata()->affine_dimension->claim.value).value == n);
        CHECK(std::get<DimensionValue>(point.metadata()->affine_dimension->claim.value).value == 0);
        CHECK(universe.metadata()->set.bounded == (n == 0 ? SetProperty::yes : SetProperty::no));
        CHECK(point.metadata()->set.bounded == SetProperty::yes);
        CHECK(empty.metadata()->affine_dimension->origin == DimensionOrigin::definition);
        CHECK(std::holds_alternative<SymbolicArgument>(point.metadata()->affine_dimension->claim.support));
    }
}

TEST_CASE("zero row and zero column H V data retain authored dimensions") {
    auto h = accepted(make_h({{"H0"}, 0, {}}, {matrix(1, 0, {}), vector({-1}), matrix(0, 0, {}), vector({})}));
    CHECK(std::get<HRepresentation>(h.representation()).inequalities.rows() == 1);
    CHECK_FALSE(h.metadata()->affine_dimension.has_value()); // 0 <= -1 is infeasible, but no feasibility solver here.
    auto point = accepted(make_v({{"V0"}, 0, {}}, {matrix(1, 0, {}), matrix(0, 0, {})}, dimension(0)));
    CHECK(std::get<VRepresentation>(point.representation()).vertices.rows() == 1);
    auto empty = accepted(make_v(plane(), {matrix(0, 2, {}), matrix(1, 2, {1, 0})},
        AffineDimensionClaim{EmptyAffineDimension{}, Unestablished{}}));
    CHECK(empty.metadata()->set.bounded == SetProperty::yes);
    CHECK(std::get<VRepresentation>(empty.representation()).rays.rows() == 1);
}

TEST_CASE("metadata and typed numeric data survive producer and set destruction") {
    auto retained = [] {
        Matrix source{2, 2, {-1, 0, 2, 0}};
        auto vertices = accepted(numeric::snapshot(source));
        auto desc = plane();
        auto set = accepted(make_v(desc, {vertices, matrix(0, 2, {})}, dimension(1)));
        auto info = set.metadata();
        CHECK(info.get() == set.metadata().get()); // metadata query retains, it does not copy.
        auto data = std::get<VRepresentation>(set.representation());
        CHECK(std::get<numeric::DenseInput>(vertices.descriptor()).storage.data() ==
              std::get<numeric::DenseInput>(data.vertices.descriptor()).storage.data());
        source.values[0] = 99;
        desc.coordinate_labels[0] = "changed";
        return std::pair{info, data};
    }();
    CHECK(retained.first->coordinate_labels[0] == "x");
    CHECK(retained.first->id.value == "segment");
    CHECK(retained.second.vertices(0, 0) == -1);
    CHECK(retained.second.vertices(1, 0) == 2);
}

TEST_CASE("supplied numerical symbolic and unchecked certificate evidence stays supplied") {
    std::vector<EvidenceSupport> supports{NumericalCheck{1e-8, 2e-8, 3e-9, {"rank-check"}},
        SymbolicArgument{"user-proof", "exact input coefficients"}, CertificateReference{"rank.cert", "external"}};
    for (const auto& support : supports) {
        auto set = accepted(make_h(plane(), segment_h(), AffineDimensionClaim{DimensionValue{1}, support}));
        auto info = set.metadata();
        CHECK(info->affine_dimension->origin == DimensionOrigin::supplied);
        CHECK(info->affine_dimension->claim.support.index() == support.index());
        if (auto numerical = std::get_if<NumericalCheck>(&info->affine_dimension->claim.support)) {
            CHECK(numerical->max_residual == 3e-9);
            CHECK(numerical->verifier.value == "rank-check");
        }
        if (auto symbolic = std::get_if<SymbolicArgument>(&info->affine_dimension->claim.support))
            CHECK(symbolic->reference == "user-proof");
        if (auto certificate = std::get_if<CertificateReference>(&info->affine_dimension->claim.support))
            CHECK(certificate->artifact == "rank.cert");
    }
}

TEST_CASE("moved authored metadata cannot retain mutable producer aliases") {
    auto desc = plane();
    char& id_alias = desc.id.value[0];
    char& label_alias = desc.coordinate_labels[0][0];
    std::optional<AffineDimensionClaim> claim{AffineDimensionClaim{DimensionValue{1},
        SymbolicArgument{"a long user proof reference with heap storage", "exact data"}}};
    char& proof_alias = std::get<SymbolicArgument>(claim->support).reference[0];
    auto set = accepted(make_h(std::move(desc), segment_h(), std::move(claim)));
    id_alias = 'X';
    label_alias = 'X';
    proof_alias = 'X';
    CHECK(set.metadata()->id.value == "segment");
    CHECK(set.metadata()->coordinate_labels[0] == "x");
    CHECK(std::get<SymbolicArgument>(set.metadata()->affine_dimension->claim.support).reference ==
        "a long user proof reference with heap storage");
}

TEST_CASE("structural errors are rejected at set creation") {
    auto desc = plane();
    SUBCASE("H columns") { auto h = segment_h(); h.equalities = matrix(1, 1, {1}); rejected(make_h(desc, h), "sets.h.shape"); }
    SUBCASE("H bound rows") { auto h = segment_h(); h.upper_bounds = vector({1}); rejected(make_h(desc, h), "sets.h.shape"); }
    SUBCASE("V columns") { auto v = segment_v(); v.rays = matrix(0, 1, {}); rejected(make_v(desc, v), "sets.v.shape"); }
    SUBCASE("label count") { desc.coordinate_labels = {"x"}; rejected(make_empty(desc), "sets.labels"); }
    SUBCASE("duplicate labels") { desc.coordinate_labels = {"x", "x"}; rejected(make_empty(desc), "sets.labels"); }
    SUBCASE("empty label") { desc.coordinate_labels = {"x", ""}; rejected(make_empty(desc), "sets.labels"); }
    SUBCASE("empty identity") { desc.id.value.clear(); rejected(make_empty(desc), "sets.id"); }
    SUBCASE("affine exceeds ambient") { rejected(make_h(desc, segment_h(), dimension(3)), "sets.affine_dimension"); }
    SUBCASE("nonempty V claimed empty") { rejected(make_v(desc, segment_v(), AffineDimensionClaim{EmptyAffineDimension{}, Unestablished{}}), "sets.affine_dimension"); }
    SUBCASE("empty V claimed nonempty") { rejected(make_v(desc, {matrix(0, 2, {}), matrix(0, 2, {})}, dimension(0)), "sets.affine_dimension"); }
    SUBCASE("singleton dimension") { rejected(make_singleton(desc, vector({1})), "sets.singleton.shape"); }
}

TEST_CASE("SetHandle roundtrip retains data and rejects a changed envelope") {
    auto handle = accepted(make_h(plane(), segment_h(), dimension(1))).as_handle();
    auto imported = accepted(from_handle(handle));
    CHECK(imported.metadata()->id.value == "segment");
    CHECK(std::get<HRepresentation>(imported.representation()).equalities(0, 1) == 1);
    CHECK(imported.as_handle().payload.get() == handle.payload.get());
    SUBCASE("id") { handle.id.value = "other"; }
    SUBCASE("dimension") { handle.metadata.dimension = 3; }
    SUBCASE("representation") { handle.metadata.representation.value = "other"; }
    SUBCASE("bounded") { handle.metadata.bounded = SetProperty::yes; }
    SUBCASE("convex") { handle.metadata.convex = SetProperty::no; }
    SUBCASE("polyhedral") { handle.metadata.polyhedral = SetProperty::unknown; }
    rejected(from_handle(handle), "sets.handle.metadata");
}

TEST_CASE("foreign and null payloads do not import as native set data") {
    struct Foreign final : SetPayload {};
    auto handle = accepted(make_empty(plane())).as_handle();
    SUBCASE("null") { handle.payload.reset(); }
    SUBCASE("foreign") { handle.payload = std::make_shared<const Foreign>(); }
    auto result = from_handle(handle);
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).code == DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostic>(result).field == "sets.handle.payload");
}
