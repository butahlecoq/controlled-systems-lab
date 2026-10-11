#include <csl/sets/data.hpp>

#include <unordered_set>
#include <utility>

namespace csl::sets::detail {
struct Storage final : SetPayload {
    Storage(Metadata info, Representation data)
        : metadata(std::move(info)), representation(std::move(data)) {}
    Metadata metadata;
    Representation representation;
};
} // namespace csl::sets::detail

namespace csl::sets {
namespace {
Diagnostic invalid(const char* field, const char* explanation) {
    return {DiagnosticCode::invalid_input, field, explanation};
}
std::optional<Diagnostic> check_description(const Description& description) {
    if (description.id.value.empty()) return invalid("sets.id", "Set identity must be nonempty.");
    const auto& labels = description.coordinate_labels;
    if (!labels.empty() && labels.size() != description.ambient_dimension)
        return invalid("sets.labels", "Supply no labels or one label per ambient coordinate.");
    std::unordered_set<std::string> unique;
    for (const auto& label : labels) {
        if (label.empty() || !unique.insert(label).second)
            return invalid("sets.labels", "Coordinate labels must be nonempty and unique.");
    }
    return std::nullopt;
}
std::optional<Diagnostic> check_dimension(const std::optional<AffineDimensionClaim>& claim,
                                         std::size_t ambient) {
    if (claim) {
        if (auto dimension = std::get_if<DimensionValue>(&claim->value); dimension && dimension->value > ambient)
            return invalid("sets.affine_dimension", "Affine dimension cannot exceed ambient dimension.");
    }
    return std::nullopt;
}
std::optional<AffineDimensionInfo> supplied(const std::optional<AffineDimensionClaim>& claim) {
    if (!claim) return std::nullopt;
    return AffineDimensionInfo{*claim, DimensionOrigin::supplied};
}
AffineDimensionInfo defined(AffineDimension value, const char* reference) {
    return {{std::move(value), SymbolicArgument{reference, "Exact elementary set definition over real coordinates."}},
        DimensionOrigin::definition};
}
std::shared_ptr<const detail::Storage> store(Description description, const char* representation,
                                           SetProperty bounded, std::optional<AffineDimensionInfo> affine,
                                           Representation data) {
    Metadata metadata{std::move(description.id),
        {description.ambient_dimension, {representation}, SetProperty::yes, SetProperty::yes, bounded},
        std::move(description.coordinate_labels), std::move(affine)};
    return std::make_shared<const detail::Storage>(std::move(metadata), std::move(data));
}
}
SetData::SetData(std::shared_ptr<const detail::Storage> storage) : storage_(std::move(storage)) {}
std::shared_ptr<const Metadata> SetData::metadata() const noexcept {
    return {storage_, &storage_->metadata};
}
Representation SetData::representation() const { return storage_->representation; }
SetHandle SetData::as_handle() const { return {storage_->metadata.set, storage_, storage_->metadata.id}; }

Result<SetData> make_h(const Description& description, HRepresentation h, const std::optional<AffineDimensionClaim>& affine) {
    if (auto error = check_description(description)) return *error;
    if (h.inequalities.cols() != description.ambient_dimension ||
        h.equalities.cols() != description.ambient_dimension ||
        h.inequalities.rows() != h.upper_bounds.size() || h.equalities.rows() != h.equality_values.size())
        return invalid("sets.h.shape", "H matrices require ambient columns and one scalar per constraint row.");
    if (auto error = check_dimension(affine, description.ambient_dimension)) return *error;
    return SetData(store(description, "csl.polyhedron.h", SetProperty::unknown,
        supplied(affine), std::move(h)));
}
Result<SetData> make_v(const Description& description, VRepresentation v, const std::optional<AffineDimensionClaim>& affine) {
    if (auto error = check_description(description)) return *error;
    if (v.vertices.cols() != description.ambient_dimension || v.rays.cols() != description.ambient_dimension)
        return invalid("sets.v.shape", "V vertices and rays require ambient columns.");
    if (auto error = check_dimension(affine, description.ambient_dimension)) return *error;
    if (affine && (std::holds_alternative<EmptyAffineDimension>(affine->value) != (v.vertices.rows() == 0)))
        return invalid("sets.affine_dimension", "Under conv(V)+cone(R), the set is empty exactly when V has no rows.");
    const auto bounded = v.vertices.rows() == 0 || v.rays.rows() == 0 ? SetProperty::yes : SetProperty::unknown;
    return SetData(store(description, "csl.polyhedron.v", bounded,
        supplied(affine), std::move(v)));
}
Result<SetData> make_empty(const Description& description) {
    if (auto error = check_description(description)) return *error;
    return SetData(store(description, "csl.empty", SetProperty::yes,
        defined(EmptyAffineDimension{}, "aff(empty) has dimension -1 by convention"), EmptyRepresentation{}));
}
Result<SetData> make_universal(const Description& description) {
    if (auto error = check_description(description)) return *error;
    const auto dimension = description.ambient_dimension;
    return SetData(store(description, "csl.universal", dimension == 0 ? SetProperty::yes : SetProperty::no,
        defined(DimensionValue{dimension}, "aff(R^n) has dimension n"), UniversalRepresentation{}));
}
Result<SetData> make_singleton(const Description& description, numeric::VectorView point) {
    if (auto error = check_description(description)) return *error;
    if (point.size() != description.ambient_dimension)
        return invalid("sets.singleton.shape", "Singleton point length must equal ambient dimension.");
    return SetData(store(description, "csl.singleton", SetProperty::yes,
        defined(DimensionValue{0}, "aff({p}) has dimension zero"), SingletonRepresentation{std::move(point)}));
}
Result<SetData> from_handle(const SetHandle& handle) {
    auto storage = std::dynamic_pointer_cast<const detail::Storage>(handle.payload);
    if (!storage) return Diagnostic{DiagnosticCode::unsupported, "sets.handle.payload", "Payload is not native CSL set data."};
    const auto& expected = storage->metadata;
    const auto& actual = handle.metadata;
    if (handle.id != expected.id || actual.dimension != expected.set.dimension ||
        actual.representation.value != expected.set.representation.value || actual.convex != expected.set.convex ||
        actual.polyhedral != expected.set.polyhedral || actual.bounded != expected.set.bounded)
        return invalid("sets.handle.metadata", "SetHandle envelope does not match its immutable native payload.");
    return SetData(std::move(storage));
}
} // namespace csl::sets
