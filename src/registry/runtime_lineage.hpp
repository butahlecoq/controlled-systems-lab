#pragma once

#include <csl/registry/registry.hpp>
#include <memory>

namespace csl::sets { class SetData; }
namespace csl::synthesis::strategy_b { struct JointProgram; }
namespace csl::synthesis::strategy_b::detail { class DirectJointExecutionRunner; }

namespace csl::registry::detail {

// Private, one-shot proof that Strategy B's internal direct-joint runner
// completed the selected exact-profile path: T-S01 construction/extraction or
// the approved T-S02 analytic relation from the retained feasible artifact.
class StrategyBRuntimeLineageReceipt {
    StrategyRequest binding_;
    std::shared_ptr<const synthesis::strategy_b::JointProgram> build_output_;
    std::shared_ptr<const sets::SetData> feasible_output_;
    std::shared_ptr<const sets::SetData> extraction_input_;
    std::shared_ptr<const sets::SetData> extracted_output_;
    StrategyRegistration::CompleteFamilyVerifierKey verifier_binding_;

    StrategyBRuntimeLineageReceipt(const StrategyRequest&,
        std::shared_ptr<const synthesis::strategy_b::JointProgram>,
        std::shared_ptr<const sets::SetData>,std::shared_ptr<const sets::SetData>,
        std::shared_ptr<const sets::SetData>,StrategyRegistration::CompleteFamilyVerifierKey);
    friend class ::csl::synthesis::strategy_b::detail::DirectJointExecutionRunner;
public:
    StrategyBRuntimeLineageReceipt(const StrategyBRuntimeLineageReceipt&)=delete;
    StrategyBRuntimeLineageReceipt& operator=(const StrategyBRuntimeLineageReceipt&)=delete;
    StrategyBRuntimeLineageReceipt(StrategyBRuntimeLineageReceipt&&) noexcept=default;
    StrategyBRuntimeLineageReceipt& operator=(StrategyBRuntimeLineageReceipt&&) noexcept=default;
    ~StrategyBRuntimeLineageReceipt()=default;

    bool matches(const StrategyRequest&,const FamilyIdentity&,
        const StrategyRegistration::CompleteFamilyVerifierKey&) const;
};

// Implemented only by the private compiled Strategy B direct-joint runner. The
// verifier consumes the receipt once; ordinary strategy workspaces have no
// route to supply runtime evidence.
class RuntimeReceiptSource {
public:
    virtual ~RuntimeReceiptSource()=default;
    virtual std::optional<StrategyBRuntimeLineageReceipt> take_runtime_receipt() noexcept=0;
};

} // namespace csl::registry::detail
