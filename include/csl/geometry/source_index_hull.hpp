#pragma once

#include <csl/geometry/hull_reducer.hpp>
#include <csl/geometry/bounded_hull_checker.hpp>
#include <csl/registry/provider.hpp>

namespace csl::geometry {

// Algorithms that return source point IDs but do not produce the exact
// barycentric deletion certificates required by HullReducerPort use this
// separate proposal interface. The affine-sum operation checks the proposal
// independently before it applies any retained indices.
enum class SourceIndexProposalStatus { completed, stopped, malformed };

struct SourceIndexProposal {
    SourceIndexProposalStatus status{SourceIndexProposalStatus::malformed};
    std::vector<std::size_t> retained_indices;
    std::string raw_status;
    std::string stop_reason;
    std::vector<std::string> trace;
    std::optional<std::size_t> internal_invocations;
};

struct LegacyKpabepOptions {
    std::size_t max_pivots{100000};
    std::size_t max_dense_entries{1048576};
    bool capture_trace{true};
    std::size_t max_trace_events{4096};
};

using SourceIndexProposalResult = std::variant<SourceIndexProposal, Diagnostics>;

class SourceIndexHullWorkspace : public ExclusiveWorkspace {
public:
    virtual SourceIndexProposalResult propose(const PointCloud&, const ExecutionContext&) = 0;
};

} // namespace csl::geometry

namespace csl::registry {
struct SourceIndexHullPort {
    using Request = geometry::PointCloud;
    using Workspace = geometry::SourceIndexHullWorkspace;
    static constexpr const char* name = "source-index-hull";
    static Request snapshot(const Request& request) { return request; }
    static geometry::SourceIndexProposalResult run(Workspace& workspace, const Request& request,
            const ExecutionContext& context) { return workspace.propose(request, context); }
};
} // namespace csl::registry

namespace csl::geometry {

struct SourceIndexAffineSumDependencies {
    registry::PreparedProvider<registry::SourceIndexHullPort> hull;
    std::optional<registry::PreparedProvider<registry::ConversionPort>> conversion;
    HullCheckBudget checker_budget{};
};

registry::Registration<registry::SourceIndexHullPort> make_quickhull_source_index_registration();
registry::Registration<registry::SourceIndexHullPort> make_legacy_kpabep_source_index_registration(
    LegacyKpabepOptions = {});

} // namespace csl::geometry
