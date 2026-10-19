#pragma once

#include <csl/sets/data.hpp>
#include <csl/geometry/approximation.hpp>

namespace csl::geometry::ellipsoidal {

// E = {x: sum_i (B_i(x-c)/r_i)^2 <= 1}; r_i=0 requires B_i(x-c)=0.
// Its real-arithmetic shape B^-1 diag(r_i^2) B^-T is PSD by construction.
struct EllipsoidInput {
    SetId id;
    Vector center;
    Matrix orientation;
    Vector projected_bounds; // outward |B_i(v-c)| bounds used by admission
    Vector radii;            // r_i^2 >= 2 * projected_bounds_i^2
    std::vector<std::string> coordinate_labels;
};

namespace detail { struct EllipsoidStorage; }

class EllipsoidSet {
public:
    EllipsoidSet(const EllipsoidSet&) = default;
    EllipsoidSet& operator=(const EllipsoidSet&) = default;
    const SetId& id() const noexcept;
    const Vector& center() const noexcept;
    const Matrix& orientation() const noexcept;
    const Vector& projected_bounds() const noexcept;
    const Vector& radii() const noexcept;
    const std::vector<std::string>& coordinate_labels() const noexcept;
    SetHandle as_handle() const;
    // Numerical support value of the exact set defined by stored coefficients.
    std::variant<double,Diagnostics> support(const Vector& direction) const;
private:
    explicit EllipsoidSet(std::shared_ptr<const detail::EllipsoidStorage> storage);
    std::shared_ptr<const detail::EllipsoidStorage> storage_;
    friend std::variant<EllipsoidSet,Diagnostics> make_ellipsoid(EllipsoidInput);
    friend std::variant<EllipsoidSet,Diagnostics> from_ellipsoid_handle(const SetHandle&);
};

using EllipsoidResult = std::variant<EllipsoidSet,Diagnostics>;
EllipsoidResult make_ellipsoid(EllipsoidInput input);
EllipsoidResult from_ellipsoid_handle(const SetHandle& handle);

enum class FamilyComposition { intersection, union_of_members };
class EllipsoidFamily {
public:
    const SetId& reference_id() const noexcept { return reference_id_; }
    SetRelation relation() const noexcept { return relation_; }
    FamilyComposition composition() const noexcept { return composition_; }
    const std::vector<approximation::EnclosedApproximation>& members() const noexcept {
        return members_;
    }
private:
    EllipsoidFamily(SetId reference_id,SetRelation relation,FamilyComposition composition,
        std::vector<approximation::EnclosedApproximation> members)
        :reference_id_(std::move(reference_id)),relation_(relation),composition_(composition),
         members_(std::move(members)){}
    SetId reference_id_;
    SetRelation relation_;
    FamilyComposition composition_;
    std::vector<approximation::EnclosedApproximation> members_;
    friend std::variant<EllipsoidFamily,registry::Rejection,OperationStopped,Unsupported>
        run_ellipsoid_family(const registry::Registry<registry::ApproximationPort>&,
            const std::vector<registry::Method>&,const ApproximationRequest&,
            const ExecutionContext&);
};
using EllipsoidFamilyOutcome=std::variant<EllipsoidFamily,registry::Rejection,
    OperationStopped,Unsupported>;
EllipsoidFamilyOutcome run_ellipsoid_family(
    const registry::Registry<registry::ApproximationPort>&,
    const std::vector<registry::Method>&,const ApproximationRequest&,
    const ExecutionContext&);

} // namespace csl::geometry::ellipsoidal
