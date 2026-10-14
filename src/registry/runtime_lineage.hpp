#pragma once

#include <csl/registry/registry.hpp>
#include <memory>

namespace csl::sets { class SetData; }
namespace csl::synthesis::strategy_b { struct JointProgram; }
namespace csl::synthesis::strategy_b::detail { class DirectJointExecutionRunner; }
namespace csl::reachability { struct ForwardTube; }
namespace csl::synthesis { struct JointHistoryRelation; struct TerminalMinimizers; }
namespace csl::synthesis::strategy_a::detail { class StrategyAExecutionRunner; }

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

// Private, one-shot evidence that Strategy A's exact T-S01 path executed its
// forward reachability, feasible recovery, terminal minimization, and optimal
// recovery stages before proposing the reviewed analytic family.
class StrategyARuntimeLineageReceipt {
    StrategyRequest binding_;
    std::shared_ptr<const reachability::ForwardTube> forward_;
    std::shared_ptr<const sets::SetData> feasible_terminal_;
    std::shared_ptr<const synthesis::JointHistoryRelation> feasible_recovery_;
    std::shared_ptr<const synthesis::TerminalMinimizers> terminal_;
    std::shared_ptr<const synthesis::JointHistoryRelation> optimal_recovery_;
    StrategyRegistration::CompleteFamilyVerifierKey verifier_binding_;

    StrategyARuntimeLineageReceipt(const StrategyRequest&,
        std::shared_ptr<const reachability::ForwardTube>,
        std::shared_ptr<const sets::SetData>,
        std::shared_ptr<const synthesis::JointHistoryRelation>,
        std::shared_ptr<const synthesis::TerminalMinimizers>,
        std::shared_ptr<const synthesis::JointHistoryRelation>,
        StrategyRegistration::CompleteFamilyVerifierKey);
    friend class ::csl::synthesis::strategy_a::detail::StrategyAExecutionRunner;
public:
    StrategyARuntimeLineageReceipt(const StrategyARuntimeLineageReceipt&)=delete;
    StrategyARuntimeLineageReceipt& operator=(const StrategyARuntimeLineageReceipt&)=delete;
    StrategyARuntimeLineageReceipt(StrategyARuntimeLineageReceipt&&) noexcept=default;
    StrategyARuntimeLineageReceipt& operator=(StrategyARuntimeLineageReceipt&&) noexcept=default;
    ~StrategyARuntimeLineageReceipt()=default;

    bool matches(const StrategyRequest&,const FamilyIdentity&,
        const StrategyRegistration::CompleteFamilyVerifierKey&) const;
};

class StrategyARuntimeReceiptSource {
public:
    virtual ~StrategyARuntimeReceiptSource()=default;
    virtual std::optional<StrategyARuntimeLineageReceipt> take_strategy_a_runtime_receipt() noexcept=0;
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
