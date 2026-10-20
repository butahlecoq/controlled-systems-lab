#pragma once

#include <csl/synthesis/hybrid_path_program.hpp>

#include <cstddef>
#include <utility>
#include <vector>

namespace csl::synthesis::detail {

struct IndependentPathEnumeration {
    std::vector<model::HybridPath> paths;
    bool resource_limit{};
    bool cancelled{};
};

template<class IsCancelled>
IndependentPathEnumeration independently_enumerate_paths(
    const model::HybridSystem& system,const model::HybridRequest& request,
    std::size_t expected_paths,std::size_t visit_limit,IsCancelled&& is_cancelled) {
    IndependentPathEnumeration result;
    model::HybridPath prefix{{request.initial.mode},{}};
    struct Frame { std::size_t stage; std::size_t next_edge; bool terminal_processed; };
    std::vector<Frame> stack{{0,0,false}};
    std::size_t visits=1;
    while(!stack.empty()) {
        if(is_cancelled()) { result.cancelled=true; return result; }
        auto& frame=stack.back();
        if(frame.stage==system.horizon) {
            if(!frame.terminal_processed) {
                frame.terminal_processed=true;
                bool allowed=false;
                for(const auto& terminal_mode:request.allowed_terminal_modes) {
                    if(is_cancelled()) { result.cancelled=true; return result; }
                    if(terminal_mode==prefix.modes.back()) { allowed=true; break; }
                }
                if(allowed) {
                    if(result.paths.size()==expected_paths) {
                        result.resource_limit=true;
                        return result;
                    }
                    model::HybridPath recorded;
                    recorded.modes.reserve(prefix.modes.size());
                    recorded.edges.reserve(prefix.edges.size());
                    for(const auto& mode:prefix.modes) {
                        if(is_cancelled()) { result.cancelled=true; return result; }
                        recorded.modes.push_back(mode);
                    }
                    for(const auto& edge:prefix.edges) {
                        if(is_cancelled()) { result.cancelled=true; return result; }
                        recorded.edges.push_back(edge);
                    }
                    result.paths.push_back(std::move(recorded));
                }
            }
            stack.pop_back();
            if(!stack.empty()) { prefix.edges.pop_back(); prefix.modes.pop_back(); }
            continue;
        }
        if(frame.next_edge==system.edges.size()) {
            stack.pop_back();
            if(!stack.empty()) { prefix.edges.pop_back(); prefix.modes.pop_back(); }
            continue;
        }
        const auto& edge=system.edges[frame.next_edge++];
        if(edge.source!=prefix.modes.back()) continue;
        if(visits==visit_limit) {
            result.resource_limit=true;
            return result;
        }
        ++visits;
        prefix.edges.push_back(edge.id);
        prefix.modes.push_back(edge.target);
        stack.push_back({frame.stage+1,0,false});
    }
    return result;
}

} // namespace csl::synthesis::detail
