#pragma once

#include <csl/synthesis/contracts.hpp>

#include <csl/registry/provider.hpp>
#include <csl/sets/data.hpp>

namespace csl::synthesis::strategy_b {
enum class RowSource { initial, state, control, transition, temporal };
struct RowLineage {
    RowSource source;
    std::size_t stage, source_row, program_row;
};
struct JointProgram {
    JointCoordinates coordinates;
    std::vector<std::size_t> source_to_program;
    std::vector<RowLineage> rows;
    SparseMatrix constraints;
    std::vector<Interval> bounds;
    TerminalObjective lifted_objective;
    std::variant<LinearProgram, ConvexProgram> program;
};
using JointProgramOutcome = std::variant<JointProgram, Diagnostics, OperationStopped>;
JointProgramOutcome build_joint_program(const problem::ResolvedProblem&, const FamilyRequest&);

// Retains program-scoped evidence without asserting binary64 program/problem
// equivalence or numerical coverage of the optimal relation.
class DirectJointPayload final : public JointRelationPayload {
public:
    JointProgram construction;
    sets::SetData relation;
    std::optional<ProgramResult> optimization;
    std::optional<registry::Provenance> provider;
    Diagnostics diagnostics;
    DirectJointPayload(JointProgram, sets::SetData);
    const sets::SetData* h_relation_for_recording() const noexcept override { return &relation; }
};
class DirectJointWorkspace final : public SynthesisWorkspace {
    registry::PreparedProvider<registry::LPPort> lp_;
    registry::PreparedProvider<registry::ConvexPort> convex_;
public:
    DirectJointWorkspace(registry::PreparedProvider<registry::LPPort>, registry::PreparedProvider<registry::ConvexPort>);
    SynthesisResult solve(const problem::ResolvedProblem&, const FamilyRequest&, const ExecutionContext&) override;
};
// Composes injected registries into the existing StrategyRegistry admission
// path; no owned or fallback registries are created.
registry::StrategyRegistration make_registration(const registry::Registry<registry::LPPort>&,
    const registry::Registry<registry::ConvexPort>&);
} // namespace csl::synthesis::strategy_b
