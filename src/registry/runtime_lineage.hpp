#pragma once

#include <csl/registry/registry.hpp>
#include <memory>

namespace csl::sets { class SetData; }
namespace csl::synthesis::strategy_b { struct JointProgram; }
namespace csl::synthesis::strategy_b::detail { class Ts01ExecutionRunner; }

namespace csl::registry::detail {

// Private, one-shot proof that the compiled T-S01 Strategy B runner completed
// construction and extraction on the same retained feasible artifact.
class StrategyBRuntimeLineageReceipt {
    StrategyRequest binding_;
    std::shared_ptr<const synthesis::strategy_b::JointProgram> build_output_;
    std::shared_ptr<const sets::SetData> feasible_output_;
    std::shared_ptr<const sets::SetData> extraction_input_;
    std::shared_ptr<const sets::SetData> extracted_output_;
    StrategyRegistration::CompleteFamilyVerifierKey verifier_binding_;
    std::uint64_t attempt_id_{};

    StrategyBRuntimeLineageReceipt(const StrategyRequest&,
        std::shared_ptr<const synthesis::strategy_b::JointProgram>,
        std::shared_ptr<const sets::SetData>,std::shared_ptr<const sets::SetData>,
        std::shared_ptr<const sets::SetData>,StrategyRegistration::CompleteFamilyVerifierKey,std::uint64_t);
    friend class ::csl::synthesis::strategy_b::detail::Ts01ExecutionRunner;
public:
    StrategyBRuntimeLineageReceipt(const StrategyBRuntimeLineageReceipt&)=delete;
    StrategyBRuntimeLineageReceipt& operator=(const StrategyBRuntimeLineageReceipt&)=delete;
    StrategyBRuntimeLineageReceipt(StrategyBRuntimeLineageReceipt&&) noexcept=default;
    StrategyBRuntimeLineageReceipt& operator=(StrategyBRuntimeLineageReceipt&&) noexcept=default;
    ~StrategyBRuntimeLineageReceipt()=default;

    bool matches(const StrategyRequest&,const FamilyIdentity&,
        const StrategyRegistration::CompleteFamilyVerifierKey&) const;
};

// Implemented only by the private compiled Strategy B execution workspace.
// The verifier consumes the receipt once; ordinary strategy workspaces have no
// route to supply runtime evidence.
class RuntimeReceiptSource {
public:
    virtual ~RuntimeReceiptSource()=default;
    virtual std::optional<StrategyBRuntimeLineageReceipt> take_runtime_receipt() noexcept=0;
};

} // namespace csl::registry::detail
