#include <csl/synthesis/hybrid_path_program.hpp>
#include "hybrid_family_verifier_internal.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>

namespace csl::synthesis {
namespace {
using namespace model;
using Integer = std::int64_t;

enum class BranchState { feasible, infeasible, unsupported };
struct BranchEvaluation {
    BranchState state{BranchState::unsupported};
    std::vector<Integer> joint_point;
    Integer objective{};
    std::string reason;
};

std::optional<Integer> integer(double value) {
    constexpr double positive_limit=9223372036854775808.0;
    if(!std::isfinite(value)||std::trunc(value)!=value||value< -positive_limit||
       value>=positive_limit) return {};
    const auto result=static_cast<Integer>(value);
    if(static_cast<double>(result)!=value) return {};
    return result;
}

bool add(Integer a,Integer b,Integer& result) {
    if((b>0&&a>std::numeric_limits<Integer>::max()-b)||
       (b<0&&a<std::numeric_limits<Integer>::min()-b)) return false;
    result=a+b;
    return true;
}

bool subtract(Integer a,Integer b,Integer& result) {
    if((b<0&&a>std::numeric_limits<Integer>::max()+b)||
       (b>0&&a<std::numeric_limits<Integer>::min()+b)) return false;
    result=a-b;
    return true;
}

bool multiply(Integer a,Integer b,Integer& result) {
    if(a==0||b==0) { result=0; return true; }
    if((a==-1&&b==std::numeric_limits<Integer>::min())||
       (b==-1&&a==std::numeric_limits<Integer>::min())) return false;
    if(a>0) {
        if((b>0&&a>std::numeric_limits<Integer>::max()/b)||
           (b<0&&b<std::numeric_limits<Integer>::min()/a)) return false;
    } else {
        if((b>0&&a<std::numeric_limits<Integer>::min()/b)||
           (b<0&&a<std::numeric_limits<Integer>::max()/b)) return false;
    }
    result=a*b;
    return true;
}

const HybridMode* find_mode(const HybridSystem& system,const HybridModeId& id) {
    const auto found=std::find_if(system.modes.begin(),system.modes.end(),
        [&](const auto& mode){return mode.id==id;});
    return found==system.modes.end()?nullptr:&*found;
}

const HybridTransitionEdge* find_edge(const HybridSystem& system,const HybridEdgeId& id) {
    const auto found=std::find_if(system.edges.begin(),system.edges.end(),
        [&](const auto& edge){return edge.id==id;});
    return found==system.edges.end()?nullptr:&*found;
}

std::optional<std::size_t> joint_width(const HybridSystem& system,const HybridPath& path) {
    if(path.modes.empty()||path.modes.size()-1!=path.edges.size()) return {};
    const auto* initial=find_mode(system,path.modes.front());
    if(!initial) return {};
    auto width=initial->state_dimension;
    const auto add_width=[&](std::size_t amount) {
        if(amount>std::numeric_limits<std::size_t>::max()-width) return false;
        width+=amount;
        return true;
    };
    for(std::size_t stage=0;stage<path.edges.size();++stage) {
        const auto* source=find_mode(system,path.modes[stage]);
        const auto* target=find_mode(system,path.modes[stage+1]);
        if(!source||!target||!add_width(source->control_dimension)||
           !add_width(source->state_dimension)||!add_width(target->state_dimension)) return {};
    }
    return width;
}

enum class PointCheck { contains, excludes, unsupported };
PointCheck contains(const AdmissibleSet& set,const std::vector<Integer>& point,
    std::stop_token cancellation) {
    return std::visit([&](const auto& value)->PointCheck {
        using T=std::decay_t<decltype(value)>;
        if constexpr(std::is_same_v<T,UniversalSet>) return PointCheck::contains;
        else if constexpr(std::is_same_v<T,EmptySet>) return PointCheck::excludes;
        else if constexpr(std::is_same_v<T,Singleton>) {
            if(value.point.size()!=point.size()) return PointCheck::unsupported;
            for(std::size_t i=0;i<point.size();++i) {
                if(cancellation.stop_requested()) return PointCheck::unsupported;
                const auto coordinate=integer(value.point[i]);
                if(!coordinate) return PointCheck::unsupported;
                if(*coordinate!=point[i]) return PointCheck::excludes;
            }
            return PointCheck::contains;
        } else return PointCheck::unsupported;
    },set);
}

bool integer_vector(const Vector& source,std::vector<Integer>& result,std::stop_token cancellation) {
    result.clear();
    result.reserve(source.size());
    for(const auto value:source) {
        if(cancellation.stop_requested()) return false;
        const auto converted=integer(value);
        if(!converted) return false;
        result.push_back(*converted);
    }
    return true;
}

enum class ResetCheck { point, empty, unsupported };
ResetCheck exact_singleton_reset(const SetHandle& handle,std::vector<Integer>& result,
    std::stop_token cancellation) {
    const auto decoded=sets::from_handle(handle);
    if(std::holds_alternative<Diagnostic>(decoded)) return ResetCheck::unsupported;
    const auto representation=std::get<sets::SetData>(decoded).representation();
    if(std::holds_alternative<sets::EmptyRepresentation>(representation)) return ResetCheck::empty;
    const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation);
    if(!singleton) return ResetCheck::unsupported;
    result.clear();
    result.reserve(singleton->point.size());
    for(const auto value:singleton->point.values()) {
        if(cancellation.stop_requested()) return ResetCheck::unsupported;
        const auto converted=integer(value);
        if(!converted) return ResetCheck::unsupported;
        result.push_back(*converted);
    }
    return ResetCheck::point;
}

BranchEvaluation evaluate(const HybridSystem& system,const HybridRequest& request,
    const HybridPath& path,std::stop_token cancellation) {
    BranchEvaluation result;
    std::vector<Integer> state;
    if(!integer_vector(request.initial.state,state,cancellation)) {
        result.reason="Initial state is outside the verifier's integral domain";
        return result;
    }
    result.joint_point=state;
    const auto initial_mode=find_mode(system,path.modes.front());
    if(!initial_mode) { result.reason="Unknown initial mode"; return result; }
    const auto initial_check=contains(initial_mode->invariants.front(),state,cancellation);
    if(initial_check==PointCheck::unsupported) {
        result.reason="Initial invariant representation is outside the verifier's supported domain";
        return result;
    }
    if(initial_check==PointCheck::excludes) { result.state=BranchState::infeasible; return result; }

    for(std::size_t stage=0;stage<system.horizon;++stage) {
        if(cancellation.stop_requested()) {
            result.reason="Verification cancelled during branch reconstruction";
            return result;
        }
        const auto* mode=find_mode(system,path.modes[stage]);
        const auto* next_mode=find_mode(system,path.modes[stage+1]);
        const auto* edge=find_edge(system,path.edges[stage]);
        if(!mode||!next_mode||!edge) { result.reason="Path references an unknown model identity"; return result; }
        std::vector<Integer> control;
        if(mode->control_dimension!=0) {
            if(stage>=mode->control_sets.size()) { result.reason="Missing control set"; return result; }
            const auto* singleton=std::get_if<Singleton>(&mode->control_sets[stage]);
            if(!singleton||!integer_vector(singleton->point,control,cancellation)) {
                result.reason="Control set is not an integral singleton";
                return result;
            }
        }
        const auto control_check=contains(mode->control_sets[stage],control,cancellation);
        if(control_check==PointCheck::unsupported) {
            result.reason="Control set representation is unsupported"; return result;
        }
        if(control_check==PointCheck::excludes) { result.state=BranchState::infeasible; return result; }
        result.joint_point.insert(result.joint_point.end(),control.begin(),control.end());

        const LinearStage* flow=nullptr;
        if(const auto* stages=std::get_if<std::vector<LinearStage>>(&mode->flow)) {
            if(stage>=stages->size()) { result.reason="Missing flow stage"; return result; }
            flow=&(*stages)[stage];
        } else flow=&std::get<LinearStage>(mode->flow);
        if(flow->A.rows!=mode->state_dimension||flow->A.cols!=state.size()||
           flow->B.rows!=mode->state_dimension||flow->B.cols!=control.size()||
           flow->E.cols!=0||flow->offset.size()!=mode->state_dimension) {
            result.reason="Flow shape is outside the verifier's supported domain"; return result;
        }
        std::vector<Integer> pre(mode->state_dimension);
        for(std::size_t row=0;row<pre.size();++row) {
            if(cancellation.stop_requested()) { result.reason="cancelled"; return result; }
            auto value=integer(flow->offset[row]);
            if(!value) { result.reason="Flow contains nonintegral data"; return result; }
            Integer sum=*value;
            for(std::size_t col=0;col<state.size();++col) {
                if(cancellation.stop_requested()) { result.reason="cancelled"; return result; }
                const auto coefficient=integer(flow->A.values[row*flow->A.cols+col]);
                Integer product,next;
                if(!coefficient||!multiply(*coefficient,state[col],product)||!add(sum,product,next)) {
                    result.reason="Flow arithmetic is nonintegral or overflows"; return result;
                }
                sum=next;
            }
            for(std::size_t col=0;col<control.size();++col) {
                if(cancellation.stop_requested()) { result.reason="cancelled"; return result; }
                const auto coefficient=integer(flow->B.values[row*flow->B.cols+col]);
                Integer product,next;
                if(!coefficient||!multiply(*coefficient,control[col],product)||!add(sum,product,next)) {
                    result.reason="Flow arithmetic is nonintegral or overflows"; return result;
                }
                sum=next;
            }
            pre[row]=sum;
        }
        result.joint_point.insert(result.joint_point.end(),pre.begin(),pre.end());
        const auto pre_check=contains(mode->invariants[stage+1],pre,cancellation);
        if(pre_check==PointCheck::unsupported) { result.reason="Pre-reset invariant is unsupported"; return result; }
        if(pre_check==PointCheck::excludes) { result.state=BranchState::infeasible; return result; }
        const auto guard_check=contains(edge->guards[stage],pre,cancellation);
        if(guard_check==PointCheck::unsupported) { result.reason="Guard representation is unsupported"; return result; }
        if(guard_check==PointCheck::excludes) { result.state=BranchState::infeasible; return result; }

        std::vector<Integer> reset;
        const auto reset_check=exact_singleton_reset(edge->reset_relations[stage],reset,cancellation);
        if(reset_check==ResetCheck::empty) { result.state=BranchState::infeasible; return result; }
        if(reset_check==ResetCheck::unsupported) {
            result.reason="Reset is not represented by an integral singleton relation"; return result;
        }
        if(reset.size()!=pre.size()+next_mode->state_dimension) {
            result.reason="Reset relation dimension disagrees with adjacent modes"; return result;
        }
        if(!std::equal(pre.begin(),pre.end(),reset.begin())) {
            result.state=BranchState::infeasible; return result;
        }
        state.assign(reset.begin()+static_cast<std::ptrdiff_t>(pre.size()),reset.end());
        result.joint_point.insert(result.joint_point.end(),state.begin(),state.end());
        const auto post_check=contains(next_mode->invariants[stage+1],state,cancellation);
        if(post_check==PointCheck::unsupported) { result.reason="Post-reset invariant is unsupported"; return result; }
        if(post_check==PointCheck::excludes) { result.state=BranchState::infeasible; return result; }
    }
    const auto objective=std::find_if(request.terminal_objectives.begin(),request.terminal_objectives.end(),
        [&](const auto& item){return item.mode==path.modes.back();});
    if(objective==request.terminal_objectives.end()) { result.reason="Missing terminal objective"; return result; }
    const auto* linear=std::get_if<LinearTerminal>(&objective->objective);
    if(!linear||linear->coefficients.size()!=state.size()) {
        result.reason="Only linear terminal objectives are supported"; return result;
    }
    const auto offset=integer(linear->offset);
    if(!offset) { result.reason="Objective offset is nonintegral"; return result; }
    result.objective=*offset;
    for(std::size_t i=0;i<state.size();++i) {
        if(cancellation.stop_requested()) { result.reason="cancelled"; return result; }
        const auto coefficient=integer(linear->coefficients[i]);
        Integer product,sum;
        if(!coefficient||!multiply(*coefficient,state[i],product)||!add(result.objective,product,sum)) {
            result.reason="Objective arithmetic is nonintegral or overflows"; return result;
        }
        result.objective=sum;
    }
    result.state=BranchState::feasible;
    return result;
}

enum class RelationCheck { matches, differs, unsupported, cancelled };
RelationCheck relation_is_exact_point(const sets::SetData& data,const std::vector<Integer>& point,
    HybridRelationLimits limits,std::stop_token cancellation) {
    if(cancellation.stop_requested()) return RelationCheck::cancelled;
    if(data.metadata()->set.dimension!=point.size()) return RelationCheck::differs;
    if(point.size()>limits.max_variables) return RelationCheck::unsupported;
    const auto representation=data.representation();
    if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation)) {
        if(singleton->point.size()!=point.size()) return RelationCheck::differs;
        for(std::size_t i=0;i<point.size();++i) {
            if(cancellation.stop_requested()) return RelationCheck::cancelled;
            const auto value=integer(singleton->point[i]);
            if(!value) return RelationCheck::unsupported;
            if(*value!=point[i]) return RelationCheck::differs;
        }
        return RelationCheck::matches;
    }
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h||h->equalities.cols()!=point.size()||h->inequalities.cols()!=point.size()||
       h->equality_values.size()!=h->equalities.rows()||h->upper_bounds.size()!=h->inequalities.rows())
        return RelationCheck::unsupported;
    if(h->inequalities.rows()>std::numeric_limits<std::size_t>::max()-h->equalities.rows())
        return RelationCheck::unsupported;
    const auto rows=h->equalities.rows()+h->inequalities.rows();
    if(rows>limits.max_rows||(point.size()!=0&&rows>limits.max_matrix_elements/point.size()))
        return RelationCheck::unsupported;
    std::vector<std::vector<Integer>> matrix(h->equalities.rows(),std::vector<Integer>(point.size()));
    for(std::size_t row=0;row<h->equalities.rows();++row) {
        if(cancellation.stop_requested()) return RelationCheck::cancelled;
        const auto rhs=integer(h->equality_values[row]);
        if(!rhs) return RelationCheck::unsupported;
        Integer sum=0;
        for(std::size_t col=0;col<point.size();++col) {
            if(cancellation.stop_requested()) return RelationCheck::cancelled;
            const auto value=integer(h->equalities(row,col));
            Integer product,next;
            if(!value||!multiply(*value,point[col],product)||!add(sum,product,next))
                return RelationCheck::unsupported;
            matrix[row][col]=*value;
            sum=next;
        }
        if(sum!=*rhs) return RelationCheck::differs;
    }
    std::size_t rank=0;
    Integer previous_pivot=1;
    for(std::size_t col=0;col<point.size()&&rank<matrix.size();++col) {
        if(cancellation.stop_requested()) return RelationCheck::cancelled;
        auto pivot_row=rank;
        while(pivot_row<matrix.size()&&matrix[pivot_row][col]==0) ++pivot_row;
        if(pivot_row==matrix.size()) continue;
        std::swap(matrix[rank],matrix[pivot_row]);
        const auto pivot=matrix[rank][col];
        for(std::size_t row=rank+1;row<matrix.size();++row) {
            if(cancellation.stop_requested()) return RelationCheck::cancelled;
            for(std::size_t j=col+1;j<point.size();++j) {
                if(cancellation.stop_requested()) return RelationCheck::cancelled;
                Integer first,second,numerator;
                if(!multiply(matrix[row][j],pivot,first)||
                   !multiply(matrix[row][col],matrix[rank][j],second)||
                   !subtract(first,second,numerator)||previous_pivot==0||numerator%previous_pivot!=0)
                    return RelationCheck::unsupported;
                matrix[row][j]=numerator/previous_pivot;
            }
            matrix[row][col]=0;
        }
        previous_pivot=pivot;
        ++rank;
    }
    if(rank!=point.size()) return RelationCheck::unsupported;
    for(std::size_t row=0;row<h->inequalities.rows();++row) {
        if(cancellation.stop_requested()) return RelationCheck::cancelled;
        const auto bound=integer(h->upper_bounds[row]);
        if(!bound) return RelationCheck::unsupported;
        Integer sum=0;
        for(std::size_t col=0;col<point.size();++col) {
            if(cancellation.stop_requested()) return RelationCheck::cancelled;
            const auto coefficient=integer(h->inequalities(row,col));
            Integer product,next;
            if(!coefficient||!multiply(*coefficient,point[col],product)||!add(sum,product,next))
                return RelationCheck::unsupported;
            sum=next;
        }
        if(sum>*bound) return RelationCheck::differs;
    }
    return RelationCheck::matches;
}

} // namespace

HybridFamilyVerificationCapabilities ExactSingletonHybridFamilyVerifier::capabilities() const noexcept {
    return {true,true,true,Assurance::numerical};
}

HybridFamilyVerificationPreflightResult ExactSingletonHybridFamilyVerifier::preflight(
    const HybridSystem& system,const HybridRequest& request,std::span<const HybridPath> paths,
    std::stop_token cancellation) const {
    for(const auto& path:paths) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,
                "Exact singleton verifier admission was cancelled between paths"};
        const auto branch=evaluate(system,request,path,cancellation);
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,
                "Exact singleton verifier admission was cancelled during reconstruction"};
        if(branch.state==BranchState::unsupported)
            return Diagnostics{{DiagnosticCode::unsupported,"hybrid.verification.exact_singleton_domain",
                detail::describe_hybrid_path(path)+": "+branch.reason}};
    }
    return std::monostate{};
}

HybridFamilyVerificationResult ExactSingletonHybridFamilyVerifier::verify(
    const HybridSystem& system,const HybridRequest& request,std::span<const HybridPath> paths,
    std::span<const HybridPathProgram> programs,
    std::span<const HybridPathOptimalFaceCandidate> candidates,NumericalPolicy policy,
    std::stop_token cancellation) const {
    constexpr std::size_t max_visits=1'000'000;
    const auto bounded_product=[](std::size_t a,std::size_t b) {
        if(a!=0&&b>std::numeric_limits<std::size_t>::max()/a)
            return std::numeric_limits<std::size_t>::max();
        return a*b;
    };
    const auto bounded_increment=[](std::size_t value) {
        return value==std::numeric_limits<std::size_t>::max()?value:value+1;
    };
    auto visit_limit=bounded_product(bounded_increment(paths.size()),bounded_increment(system.horizon));
    visit_limit=bounded_product(visit_limit,bounded_increment(system.edges.size()));
    visit_limit=bounded_product(visit_limit,64);
    visit_limit=std::min(visit_limit,max_visits);
    auto inventory=detail::independently_enumerate_paths(system,request,paths.size(),visit_limit,
        [&]{return cancellation.stop_requested();});
    if(cancellation.stop_requested()||inventory.cancelled)
        return OperationStopped{StopReason::cancelled,"Exact singleton hybrid verification was cancelled during path enumeration"};
    if(inventory.resource_limit)
        return Diagnostics{{DiagnosticCode::unsupported,"hybrid.verification.oracle_limit",
            "Independent verifier path traversal exceeded its inventory-derived resource limit"}};
    if(inventory.paths!=std::vector<HybridPath>(paths.begin(),paths.end()))
        return Diagnostics{{DiagnosticCode::evidence_mismatch,"hybrid.verification.oracle_paths",
            "Independent verifier path enumeration disagrees with the admitted inventory"}};
    if(programs.size()!=paths.size())
        return Diagnostics{{DiagnosticCode::evidence_mismatch,"hybrid.verification.programs",
            "Independent verifier requires one program per enumerated path"}};

    std::vector<BranchEvaluation> evaluations;
    evaluations.reserve(paths.size());
    std::optional<Integer> minimum;
    bool unsupported=false;
    for(std::size_t index=0;index<paths.size();++index) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Exact singleton hybrid verification was cancelled between branches"};
        const auto width=joint_width(system,paths[index]);
        if(!width||*width>programs[index].relation_limits.max_variables||
           programs[index].joint_relation.metadata()->set.dimension!=*width) {
            evaluations.push_back({BranchState::unsupported,{},0,
                "Joint path width is invalid, exceeds its recorded limit, or disagrees with the supplied relation"});
        } else evaluations.push_back(evaluate(system,request,paths[index],cancellation));
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Exact singleton hybrid verification was cancelled during branch reconstruction"};
        const auto& value=evaluations.back();
        if(value.state==BranchState::unsupported) unsupported=true;
        if(value.state==BranchState::feasible&&(!minimum||value.objective<*minimum)) minimum=value.objective;
    }

    HybridFamilyVerificationReport report{"csl.hybrid.exact-singleton","1",policy,
        Assurance::numerical,std::vector<HybridPath>(paths.begin(),paths.end()),{},
        HybridVerificationStatus::not_checked,HybridVerificationStatus::not_checked,{}, {}};
    report.branches.reserve(paths.size());
    bool coverage=true;
    bool coverage_unsupported=false;
    for(std::size_t i=0;i<paths.size();++i) {
        const auto& evaluation=evaluations[i];
        HybridPathVerificationRecord record{};
        record.path=paths[i];
        const auto candidate=std::find_if(candidates.begin(),candidates.end(),
            [&](const auto& item){return item.path==paths[i];});
        if(evaluation.state==BranchState::unsupported) {
            record.feasibility=HybridVerificationStatus::unsupported;
            record.objective_optimality=HybridVerificationStatus::unsupported;
            record.continuous_coverage=HybridVerificationStatus::unsupported;
            record.diagnostics.push_back({DiagnosticCode::unsupported,"hybrid.verification.exact_domain",evaluation.reason});
            coverage=false;
        } else if(evaluation.state==BranchState::infeasible) {
            record.feasibility=HybridVerificationStatus::refuted;
            record.objective_optimality=HybridVerificationStatus::refuted;
            record.continuous_coverage=candidate==candidates.end()?HybridVerificationStatus::established:
                HybridVerificationStatus::refuted;
            if(candidate!=candidates.end()) {
                record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,"hybrid.verification.infeasible_face",
                    "Candidate face is supplied for a path that the independent verifier proves infeasible"});
                coverage=false;
            }
        } else {
            const bool optimal=minimum&&evaluation.objective==*minimum;
            record.feasibility=HybridVerificationStatus::established;
            const bool proven_suboptimal=minimum&&evaluation.objective>*minimum;
            const bool unresolved_optimum=unsupported&&!proven_suboptimal;
            record.objective_optimality=unresolved_optimum?HybridVerificationStatus::unsupported:
                (optimal?HybridVerificationStatus::established:HybridVerificationStatus::refuted);
            bool branch_covered=!optimal;
            if(unresolved_optimum) {
                branch_covered=false;
                record.continuous_coverage=HybridVerificationStatus::unsupported;
                record.diagnostics.push_back({DiagnosticCode::unsupported,"hybrid.verification.global_objective",
                    "An unsupported path could change whether this branch is globally optimal"});
                coverage=false;
                coverage_unsupported=true;
            } else if(optimal) {
                branch_covered=candidate!=candidates.end()&&candidate->anchor.size()==evaluation.joint_point.size();
                if(branch_covered) {
                    for(std::size_t j=0;j<candidate->anchor.size();++j) {
                        const auto anchor=integer(candidate->anchor[j]);
                        if(!anchor||*anchor!=evaluation.joint_point[j]) { branch_covered=false; break; }
                    }
                }
                if(branch_covered) {
                    const auto program_check=relation_is_exact_point(programs[i].joint_relation,
                        evaluation.joint_point,programs[i].relation_limits,cancellation);
                    if(program_check==RelationCheck::cancelled)
                        return OperationStopped{StopReason::cancelled,"Exact singleton hybrid verification was cancelled while checking the program relation"};
                    const auto face_check=relation_is_exact_point(candidate->relation,
                        evaluation.joint_point,programs[i].relation_limits,cancellation);
                    if(face_check==RelationCheck::cancelled)
                        return OperationStopped{StopReason::cancelled,"Exact singleton hybrid verification was cancelled while checking the candidate face"};
                    branch_covered=program_check==RelationCheck::matches&&face_check==RelationCheck::matches;
                    if(program_check==RelationCheck::unsupported||face_check==RelationCheck::unsupported) {
                        record.continuous_coverage=HybridVerificationStatus::unsupported;
                        record.diagnostics.push_back({DiagnosticCode::unsupported,"hybrid.verification.relation_domain",
                            "Program or face relation is outside the exact singleton verifier's provable H domain"});
                        coverage=false;
                        coverage_unsupported=true;
                    }
                }
                if(!branch_covered)
                    if(record.continuous_coverage!=HybridVerificationStatus::unsupported)
                        record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,"hybrid.verification.face",
                            "Optimal singleton branch is missing or its program/face relation does not equal the independently reconstructed trajectory"});
            } else if(candidate!=candidates.end()) {
                branch_covered=false;
                record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,"hybrid.verification.suboptimal_face",
                    "Candidate face is supplied for a path that the independent verifier proves globally suboptimal"});
            }
            if(record.continuous_coverage!=HybridVerificationStatus::unsupported)
                record.continuous_coverage=branch_covered?HybridVerificationStatus::established:
                    HybridVerificationStatus::refuted;
            coverage=coverage&&branch_covered;
        }
        report.branches.push_back(std::move(record));
    }
    if(unsupported) {
        report.global_objective_optimality=HybridVerificationStatus::unsupported;
        report.complete_family_coverage=HybridVerificationStatus::unsupported;
    } else if(!minimum) {
        report.global_objective_optimality=HybridVerificationStatus::refuted;
        report.complete_family_coverage=HybridVerificationStatus::refuted;
    } else {
        report.global_objective_optimality=HybridVerificationStatus::established;
        report.complete_family_coverage=coverage?HybridVerificationStatus::established:
            (coverage_unsupported?HybridVerificationStatus::unsupported:HybridVerificationStatus::refuted);
    }
    return report;
}

} // namespace csl::synthesis
