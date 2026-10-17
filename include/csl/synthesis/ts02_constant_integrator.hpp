#pragma once

#include <csl/synthesis/contracts.hpp>
#include <csl/sets/data.hpp>
#include <utility>

namespace csl::synthesis {

inline constexpr const char* ts02_constant_integrator_profile = "ts02_constant_integrator";
inline constexpr const char* ts02_constant_integrator_verifier = "csl.verifier.ts02-constant-integrator";
inline constexpr const char* ts02_constant_integrator_proof = "TS02-constant-integrator-v1";

// Shared payload for the exact T-S02 analytic profile. The compiled verifier
// checks the owned H-representation against its canonical joint-history set.
class Ts02ConstantIntegratorRelation final : public JointRelationPayload {
    sets::SetData h_polyhedron_;
public:
    explicit Ts02ConstantIntegratorRelation(sets::SetData h_polyhedron)
        : h_polyhedron_(std::move(h_polyhedron)) {}
    const sets::SetData& h_polyhedron() const noexcept { return h_polyhedron_; }
    const sets::SetData* h_relation_for_recording() const noexcept override { return &h_polyhedron_; }
};

} // namespace csl::synthesis
