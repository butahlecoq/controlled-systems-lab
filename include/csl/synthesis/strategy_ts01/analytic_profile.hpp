#pragma once

#include <csl/registry/registry.hpp>
#include <csl/sets/data.hpp>

namespace csl::synthesis::strategy_ts01 {

inline constexpr const char* strategy_id = "csl.synthesis.ts01-analytic";
inline constexpr const char* strategy_version = "1";
inline constexpr const char* profile_id = "ts01_exact_integrator";

// Exact dyadic membership for the canonical five-coordinate joint history
// (x0,x1,x2,u0,u1): x0=0, x1=u0, x2=1, u0+u1=1, 0<=u0<=1.
class ExactJointRelation final : public JointRelationPayload {
    sets::SetData h_polyhedron_;
    explicit ExactJointRelation(sets::SetData);
public:
    static std::variant<std::shared_ptr<const ExactJointRelation>,Diagnostics> canonical();
    const sets::SetData& h_polyhedron() const noexcept { return h_polyhedron_; }
    bool contains(std::span<const double> canonical_history) const noexcept;
};

// Exact singleton inner subset at s=1/2 in canonical joint coordinates.
class MidpointJointRelation final : public JointRelationPayload {
    sets::SetData h_polyhedron_;
    explicit MidpointJointRelation(sets::SetData);
public:
    static std::variant<std::shared_ptr<const MidpointJointRelation>,Diagnostics> canonical();
    const sets::SetData& h_polyhedron() const noexcept { return h_polyhedron_; }
};

registry::StrategyRegistration make_registration();

} // namespace csl::synthesis::strategy_ts01
