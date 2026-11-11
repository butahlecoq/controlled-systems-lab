#pragma once

#include <csl/geometry/hull_reducer.hpp>
#include <csl/registry/provider.hpp>
#include <cstddef>

namespace csl::geometry {

struct HullCandidateGraph {
    std::string id;
    registry::Identity vertex_reducer;
    registry::Identity vertex_lp;
    std::size_t input_dimension{};
    std::string representation{"csl.polyhedron.v"};
    std::string controller{"not_used"};
    std::string supporting_operations{"not_used"};
    std::string terminal_optimizer{"not_used"};
    std::string request_profile;
};

struct PreparedHullCandidate {
    HullCandidateGraph graph;
    registry::PreparedPipeline<registry::HullReducerPort> reducer;
    registry::PreparedProvider<registry::LPPort> vertex_lp;
    std::vector<registry::Provenance> provenance;
};

class HullReducerCatalogue {
    registry::Registry<registry::HullReducerPort> reducers_;
    registry::Registration<registry::LPPort> vertex_lp_;
    HullReducerCatalogue(registry::Registry<registry::HullReducerPort> reducers,
            registry::Registration<registry::LPPort> vertex_lp)
        :reducers_(std::move(reducers)),vertex_lp_(std::move(vertex_lp)) {}
    friend HullReducerCatalogue make_hull_reducer_catalogue(registry::Registration<registry::LPPort>);
    friend std::variant<PreparedHullCandidate,registry::Rejection> prepare_hull_candidate(
        const HullReducerCatalogue&,const HullCandidateGraph&,const PointCloud&);
public:
    std::vector<registry::Identity> reducer_identities() const { return reducers_.identities(); }
    registry::Identity vertex_lp_identity() const { return vertex_lp_.identity; }
};

HullReducerCatalogue make_hull_reducer_catalogue(registry::Registration<registry::LPPort>);
std::vector<HullCandidateGraph> enumerate_hull_candidates(const HullReducerCatalogue&,
    std::size_t input_dimension);
std::variant<PreparedHullCandidate,registry::Rejection> prepare_hull_candidate(
    const HullReducerCatalogue&,const HullCandidateGraph&,const PointCloud&);

struct HullCandidateExecution {
    HullCandidateGraph graph;
    std::vector<registry::Provenance> provenance;
    HullReductionResult reduction;
    std::vector<registry::LPQueryRecord> vertex_lp_queries;
};

HullCandidateExecution run_hull_candidate(PreparedHullCandidate, const ExecutionContext& = {});

} // namespace csl::geometry
