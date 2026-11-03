#pragma once

#include <csl/synthesis/hybrid_path_program.hpp>
#include <memory>

namespace csl::synthesis {

enum class HybridOperationKind {
    relation,
    projection,
    linear_optimization,
    convex_optimization,
    family_verification
};

struct HybridOperationKey {
    HybridOperationKind kind{};
    std::optional<std::size_t> path_index;
    std::optional<std::size_t> stage;
    bool operator==(const HybridOperationKey&) const = default;
};

struct HybridOperationDescriptor {
    HybridOperationKey key;
    std::optional<model::HybridPlannedOperation> relation_operation;
    std::optional<std::string> objective;
    std::size_t maximum_rows{};
    std::size_t maximum_columns{};
    std::size_t maximum_elements{};
    Assurance requested_assurance{Assurance::numerical};
};

enum class HybridAdmissionAdapterRole {
    trajectory,
    reachability,
    geometry,
    lp,
    convex,
    verifier
};

struct HybridOperationOffer {
    HybridOperationKey key;
    HybridAdmissionAdapterRole adapter_role{};
    std::optional<registry::Provenance> provider;
    registry::AdmissionStatus decision{registry::AdmissionStatus::unknown};
    Diagnostics diagnostics;
};

struct HybridAdmissionReport {
    std::vector<model::HybridPath> paths;
    std::vector<HybridOperationDescriptor> operations;
    std::vector<HybridOperationOffer> offers;
    Diagnostics diagnostics;
    std::optional<ResourcePolicy> requested_resources;
    bool admitted{};
};

struct HybridAdmissionRefused {
    HybridAdmissionReport report;
};

struct HybridExecutionSelection {
    std::shared_ptr<const HybridDirectTrajectoryAdapter> trajectory;
    std::shared_ptr<const HybridReachabilityAdapter> reachability;
    std::optional<registry::PreparedProvider<registry::LPPort>> lp;
    std::optional<registry::PreparedProvider<registry::ConvexPort>> convex;
    std::shared_ptr<const HybridFamilyVerificationAdapter> verifier;
};

class HybridAdmissionToken {
    struct Storage;
    std::unique_ptr<const Storage> storage_;
    explicit HybridAdmissionToken(std::unique_ptr<const Storage> storage);
    friend class HybridAdmissionAccess;
public:
    HybridAdmissionToken(const HybridAdmissionToken&) = delete;
    HybridAdmissionToken& operator=(const HybridAdmissionToken&) = delete;
    HybridAdmissionToken(HybridAdmissionToken&&) noexcept;
    HybridAdmissionToken& operator=(HybridAdmissionToken&&) noexcept;
    ~HybridAdmissionToken();

    const HybridAdmissionReport& report() const noexcept;
};

using HybridAdmissionResult = std::variant<HybridAdmissionToken,
    HybridAdmissionRefused, OperationStopped>;

// Derives and checks every selected path operation without composing a
// relation, preparing a concrete provider request, or creating a workspace.
HybridAdmissionResult admit_hybrid_request(const model::HybridSystem&,
    const model::HybridRequest&, const HybridExecutionSelection&,
    model::HybridEnumerationLimits, model::HybridRelationLimits,
    optimization::ObjectivePolicy, const ExecutionContext&);

struct HybridConcreteRefinementRejected {
    HybridAdmissionReport admission;
    Diagnostics diagnostics;
};

class HybridPreparedExecution {
    struct Storage;
    std::unique_ptr<const Storage> storage_;
    explicit HybridPreparedExecution(std::unique_ptr<const Storage> storage);
    friend class HybridPreparedAccess;
public:
    HybridPreparedExecution(const HybridPreparedExecution&) = delete;
    HybridPreparedExecution& operator=(const HybridPreparedExecution&) = delete;
    HybridPreparedExecution(HybridPreparedExecution&&) noexcept;
    HybridPreparedExecution& operator=(HybridPreparedExecution&&) noexcept;
    ~HybridPreparedExecution();

    const HybridAdmissionReport& report() const noexcept;
};

using HybridRefinementResult = std::variant<HybridPreparedExecution,
    HybridConcreteRefinementRejected, OperationStopped>;

// Transactionally builds selected trajectory branches, stages reachability
// operations (including concrete projected-geometry preparation), and
// prepares every LP/convex program before returning. Family-verifier
// selections fail closed until their concrete preparation joins this transaction.
HybridRefinementResult refine_hybrid_request(HybridAdmissionToken,
    ProblemId, const ExecutionContext&);

// Consumes staged reachability operations and creates solver workspaces only
// after refinement prepared every selected request successfully.
HybridPortfolioExecution execute_hybrid_request(HybridPreparedExecution,
    const ExecutionContext&);

} // namespace csl::synthesis
