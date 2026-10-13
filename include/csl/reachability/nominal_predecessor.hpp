#pragma once

#include <csl/geometry/polyhedral_projection.hpp>

namespace csl::reachability {

// Ordered operands are [states, controls, target]. All are native H,
// singleton, empty or universal sets; matrices use their authored coordinates.
struct NominalPredecessorRequest {
    GeometryRequestIdentity identity;
    SetHandle states, controls, target;
    Matrix A, B;
    Vector offset;
    SetRelation required_relation{SetRelation::equivalent};
    Assurance assurance{Assurance::numerical};
};

struct NominalPredecessorResult {
    OperationResult result;
    RequestProvenance projection_provider;
    GeometryRequestIdentity projection_request;
    std::vector<std::size_t> state_coordinates;
};
struct NominalPredecessorFailure {
    GeometryReference predecessor;
    GeometryReference projection;
    RequestProvenance projection_provider;
    std::vector<GeometryEvidence> completed_lineage;
    std::variant<Unsupported, OperationStopped> cause;
};
using NominalPredecessorOutcome =
    std::variant<NominalPredecessorResult, NominalPredecessorFailure>;

class PreparedNominalPredecessor {
    NominalPredecessorRequest request_;
    OperationRequest projection_;
    registry::PreparedPipeline<registry::GeometryPort> prepared_;
    PreparedNominalPredecessor(NominalPredecessorRequest, OperationRequest,
        registry::PreparedPipeline<registry::GeometryPort>);
    friend std::variant<PreparedNominalPredecessor, Diagnostics, registry::Rejection>
        prepare_nominal_predecessor(const NominalPredecessorRequest&,
            const registry::PreparedProvider<registry::GeometryPort>&);
public:
    // Creates its exclusive projection workspace only after preparation has
    // admitted the complete concrete operation through the selected provider.
    NominalPredecessorOutcome run(const ExecutionContext&) const;
};
using NominalPredecessorPreparation =
    std::variant<PreparedNominalPredecessor, Diagnostics, registry::Rejection>;
NominalPredecessorPreparation prepare_nominal_predecessor(
    const NominalPredecessorRequest&,
    const registry::PreparedProvider<registry::GeometryPort>&);

} // namespace csl::reachability
