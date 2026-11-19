#include <csl/geometry/source_index_hull.hpp>
#include <csl/geometry/quickhull_2d.hpp>
#include <csl/geometry/legacy_btulshor.hpp>
#include <csl/geometry/composition_catalogue.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <memory>

namespace csl::geometry {
namespace {

std::string interruption(const ExecutionContext &context) {
    if (context.cancellation.stop_requested())
        return "cancelled_during_kernel";
    if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
        return "deadline_expired_during_kernel";
    return {};
}

class QuickHullWorkspace final : public SourceIndexHullWorkspace {
  public:
    SourceIndexProposalResult propose(const PointCloud &cloud,
                                      const ExecutionContext &context) override {
        if (context.cancellation.stop_requested())
            return SourceIndexProposal{
                SourceIndexProposalStatus::stopped, {}, "not_started", "cancelled", {}, 0};
        if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
            return SourceIndexProposal{
                SourceIndexProposalStatus::stopped, {}, "not_started", "deadline", {}, 0};
        const auto result =
            quickhull_2d_controlled(cloud.points, {context.cancellation, context.deadline});
        if (const auto reason = interruption(context); !reason.empty()) {
            SourceIndexProposal proposal{
                SourceIndexProposalStatus::stopped,
                {},
                "kernel_returned_after_interruption",
                reason,
                {"QuickHull2D invocation completed before context recheck"},
                1};
            if (const auto *hull = std::get_if<QuickHull2D>(&result))
                proposal.retained_indices = hull->vertex_indices;
            return proposal;
        }
        if (const auto *stopped = std::get_if<QuickHullStopped>(&result))
            return SourceIndexProposal{
                SourceIndexProposalStatus::stopped, {}, stopped->reason, stopped->reason, {}, 1};
        if (const auto *diagnostics = std::get_if<Diagnostics>(&result)) {
            SourceIndexProposal proposal{
                SourceIndexProposalStatus::malformed, {}, "invalid_input", {}, {}, 1};
            for (const auto &diagnostic : *diagnostics)
                proposal.trace.push_back(diagnostic.field + ": " + diagnostic.explanation);
            return proposal;
        }
        return SourceIndexProposal{
            SourceIndexProposalStatus::completed,
            std::get<QuickHull2D>(result).vertex_indices,
            "completed",
            {},
            {"exact represented-binary64 orientation; duplicate coordinates retain the lowest original ID; edge/interior IDs omitted; output order starts lexicographically and proceeds counterclockwise"},
            1};
    }
};

class LegacyKpabepWorkspace final : public SourceIndexHullWorkspace {
    LegacyKpabepOptions options_;

  public:
    explicit LegacyKpabepWorkspace(LegacyKpabepOptions options) : options_(options) {}
    SourceIndexProposalResult propose(const PointCloud &cloud,
                                      const ExecutionContext &context) override {
        if (context.cancellation.stop_requested())
            return SourceIndexProposal{
                SourceIndexProposalStatus::stopped, {}, "not_started", "cancelled", {}, 0};
        if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
            return SourceIndexProposal{
                SourceIndexProposalStatus::stopped, {}, "not_started", "deadline", {}, 0};
        const legacy_btulshor::Limits limits{options_.max_pivots,    options_.max_dense_entries,
                                             options_.capture_trace, options_.max_trace_events,
                                             context.cancellation,   context.deadline};
        const auto result = legacy_btulshor::source_kpabep_port().run(
            cloud.points, legacy_btulshor::source_modif_port(), limits);
        if (const auto reason = interruption(context); !reason.empty()) {
            SourceIndexProposal proposal{SourceIndexProposalStatus::stopped,
                                         {},
                                         "kernel_returned_after_interruption",
                                         reason,
                                         {std::string{legacy_btulshor::reach_source_id},
                                          "BTULSHOR invocation returned before context recheck"},
                                         std::nullopt};
            if (const auto *raw = std::get_if<legacy_btulshor::KpabepResult>(&result)) {
                proposal.retained_indices = raw->retained_indices;
                proposal.trace.push_back("raw legacy result pivots=" + std::to_string(raw->pivots) +
                                         "; modif_calls=" + std::to_string(raw->modif_calls));
            } else {
                proposal.trace.push_back("raw legacy stop=" +
                                         std::get<legacy_btulshor::Stopped>(result).message);
            }
            return proposal;
        }
        if (const auto *stopped = std::get_if<legacy_btulshor::Stopped>(&result))
            return SourceIndexProposal{
                SourceIndexProposalStatus::stopped,
                {},
                "stopped",
                stopped->message,
                {std::string{legacy_btulshor::reach_source_id}, stopped->message},
                std::nullopt};
        const auto &raw = std::get<legacy_btulshor::KpabepResult>(result);
        SourceIndexProposal proposal{
            SourceIndexProposalStatus::completed,
            raw.retained_indices,
            "completed; epsilon=1e-5; MODIF source statuses retained verbatim",
            {},
            {},
            raw.modif_calls + 1};
        proposal.trace.reserve(raw.candidate_trace.size() + 1);
        proposal.trace.push_back(
            "source=" + std::string{legacy_btulshor::reach_source_id} + "; modif_calls=" +
            std::to_string(raw.modif_calls) + "; pivots=" + std::to_string(raw.pivots) +
            "; trace_truncated=" + (raw.trace_truncated ? "true" : "false") +
            "; max_pivots=" + std::to_string(options_.max_pivots) +
            "; max_dense_entries=" + std::to_string(options_.max_dense_entries) +
            "; capture_trace=" + (options_.capture_trace ? "true" : "false") +
            "; max_trace_events=" + std::to_string(options_.max_trace_events) +
            "; source status 2 uses the original retain/swap branch; all other raw MODIF statuses are preserved and are not interpreted as a hull certificate");
        for (const auto &step : raw.candidate_trace)
            proposal.trace.push_back("candidate=" + std::to_string(step.candidate_index) +
                                     "; modif_status=" + std::to_string(step.original_status) +
                                     "; pivots=" + std::to_string(step.pivots));
        return proposal;
    }
};

registry::Capability source_capability(const PointCloud &cloud, const registry::Requirements &) {
    if (!cloud.points.empty() && cloud.points.front().size() != 2)
        return Diagnostics{{DiagnosticCode::unsupported, "source-index.dimension",
                            "Source-index geometry providers support exactly two coordinates."}};
    for (const auto &point : cloud.points) {
        if (point.size() != 2)
            return Diagnostics{
                {DiagnosticCode::unsupported, "source-index.dimension",
                 "Source-index geometry providers support exactly two coordinates."}};
        if (std::any_of(point.begin(), point.end(),
                        [](double value) { return !std::isfinite(value); }))
            return Diagnostics{{DiagnosticCode::invalid_input, "source-index.coordinates",
                                "Source-index geometry providers require finite coordinates."}};
    }
    return registry::Offer{};
}

} // namespace

registry::Registration<registry::SourceIndexHullPort> make_quickhull_source_index_registration() {
    return {{{"csl.hull.source.quickhull-2d"}, "1.0.0"}, source_capability, [](const PointCloud &) {
                return std::make_unique<QuickHullWorkspace>();
            }};
}

registry::Registration<registry::SourceIndexHullPort>
make_legacy_kpabep_source_index_registration(LegacyKpabepOptions options) {
    return {
        {{"csl.hull.source.btulshor-kpabep"}, "1.0.0"},
        source_capability,
        [options](const PointCloud &) { return std::make_unique<LegacyKpabepWorkspace>(options); }};
}

registry::Registry<registry::SourceIndexHullPort>
make_source_index_hull_catalogue(LegacyKpabepOptions legacy_options) {
    registry::Registry<registry::SourceIndexHullPort> providers;
    if (const auto rejection = providers.add(make_quickhull_source_index_registration()))
        throw std::logic_error(
            "Built-in source-index catalogue contains an invalid QuickHull registration: " +
            rejection->diagnostics.front().explanation);
    if (const auto rejection =
            providers.add(make_legacy_kpabep_source_index_registration(legacy_options)))
        throw std::logic_error(
            "Built-in source-index catalogue contains an invalid BTULSHOR registration: " +
            rejection->diagnostics.front().explanation);
    return providers;
}

} // namespace csl::geometry
