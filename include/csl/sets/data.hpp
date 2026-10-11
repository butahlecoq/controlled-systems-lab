#pragma once

#include <csl/numeric/data.hpp>

namespace csl::sets {

struct EmptyAffineDimension {};
struct DimensionValue { std::size_t value; };
using AffineDimension = std::variant<EmptyAffineDimension, DimensionValue>;
struct AffineDimensionClaim { AffineDimension value; EvidenceSupport support; };
enum class DimensionOrigin { supplied, definition };
struct AffineDimensionInfo { AffineDimensionClaim claim; DimensionOrigin origin; };

// Empty labels mean unnamed coordinates; otherwise one unique nonempty label per coordinate.
struct Description {
    SetId id;
    std::size_t ambient_dimension;
    std::vector<std::string> coordinate_labels;
};
struct Metadata {
    SetId id;
    SetMetadata set;
    std::vector<std::string> coordinate_labels;
    // Missing means unknown, not full-dimensional. Empty has affine dimension -1.
    std::optional<AffineDimensionInfo> affine_dimension;
};

struct HRepresentation {
    numeric::MatrixView inequalities;
    numeric::VectorView upper_bounds;
    numeric::MatrixView equalities;
    numeric::VectorView equality_values;
};
struct VRepresentation { numeric::MatrixView vertices, rays; };
struct EmptyRepresentation {};
struct UniversalRepresentation {};
struct SingletonRepresentation { numeric::VectorView point; };
using Representation = std::variant<HRepresentation, VRepresentation,
    EmptyRepresentation, UniversalRepresentation, SingletonRepresentation>;

namespace detail { struct Storage; }
template<class T> using Result = std::variant<T, Diagnostic>;

class SetData {
public:
    SetData(const SetData&) = default;
    SetData& operator=(const SetData&) = default;
    // Both results retain immutable storage independently of this handle.
    std::shared_ptr<const Metadata> metadata() const noexcept;
    Representation representation() const;
    // Envelope strings are copied; numeric payload storage remains shared.
    SetHandle as_handle() const;
private:
    explicit SetData(std::shared_ptr<const detail::Storage> storage);
    std::shared_ptr<const detail::Storage> storage_;
    friend Result<SetData> make_h(const Description&, HRepresentation, const std::optional<AffineDimensionClaim>&);
    friend Result<SetData> make_v(const Description&, VRepresentation, const std::optional<AffineDimensionClaim>&);
    friend Result<SetData> make_empty(const Description&);
    friend Result<SetData> make_universal(const Description&);
    friend Result<SetData> make_singleton(const Description&, numeric::VectorView);
    friend Result<SetData> from_handle(const SetHandle&);
};

Result<SetData> make_h(const Description&, HRepresentation, const std::optional<AffineDimensionClaim>& = std::nullopt);
Result<SetData> make_v(const Description&, VRepresentation, const std::optional<AffineDimensionClaim>& = std::nullopt);
Result<SetData> make_empty(const Description&);
Result<SetData> make_universal(const Description&);
Result<SetData> make_singleton(const Description&, numeric::VectorView);
Result<SetData> from_handle(const SetHandle&);

} // namespace csl::sets
