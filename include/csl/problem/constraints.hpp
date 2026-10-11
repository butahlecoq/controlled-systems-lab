#pragma once

#include <csl/problem/domains.hpp>

namespace csl::problem {
namespace detail { struct ConstraintStorage; }

struct TemporalData {
    numeric::MatrixView joint_map;
    std::shared_ptr<const std::vector<Interval>> bounds;
};
class Constraints {
public:
    Constraints(const Constraints&) = default;
    Constraints& operator=(const Constraints&) = default;
    JointCoordinates coordinates() const noexcept;
    std::size_t joint_dimension() const noexcept;
    std::shared_ptr<const std::vector<AdmissibleSet>> states() const noexcept;
    std::optional<TemporalData> temporal() const noexcept;
    Result<std::size_t> state_offset(StageIndex) const;
    Result<std::size_t> control_offset(StageIndex) const;
private:
    explicit Constraints(std::shared_ptr<const detail::ConstraintStorage>);
    std::shared_ptr<const detail::ConstraintStorage> storage_;
    friend Result<Constraints> snapshot_constraints(std::span<const AdmissibleSet>,
        const std::optional<TemporalConstraints>&, const model::LinearSystem&);
};
Result<Constraints> snapshot_constraints(std::span<const AdmissibleSet>,
    const std::optional<TemporalConstraints>&, const model::LinearSystem&);
} // namespace csl::problem
