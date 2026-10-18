#pragma once

#include <csl/synthesis/contracts.hpp>
#include <csl/sets/data.hpp>
#include <utility>

namespace csl::synthesis {

inline constexpr const char* ts03_singular_integrator_profile = "ts03_singular_integrator";
inline constexpr const char* ts03_singular_integrator_verifier = "csl.verifier.ts03-singular-integrator";
inline constexpr const char* ts03_singular_integrator_proof = "TS03-singular-integrator-v1";

// Exact analytic full-history relation for x[t+1]=u[t], u[t] in [0,1],
// and terminal objective (x2-1)^2. Earlier controls remain free.
class Ts03SingularIntegratorRelation final : public JointRelationPayload {
    sets::SetData h_polyhedron_;
public:
    explicit Ts03SingularIntegratorRelation(sets::SetData h_polyhedron)
        :h_polyhedron_(std::move(h_polyhedron)) {}
    const sets::SetData& h_polyhedron() const noexcept { return h_polyhedron_; }
    const sets::SetData* h_relation_for_recording() const noexcept override { return &h_polyhedron_; }
};

} // namespace csl::synthesis
