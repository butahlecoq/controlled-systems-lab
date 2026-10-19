#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/synthesis/hybrid_path_program.hpp>
#include <csl/sets/data.hpp>
#include <csl/registry/provider.hpp>
#include "hybrid_family_verifier_internal.hpp"
#include <algorithm>
#include <array>
#include <limits>
#include <string_view>

using namespace csl;
using namespace csl::synthesis;

namespace {
SetHandle universal(std::string id,std::size_t dimension) {
    auto data=sets::make_universal({SetId{std::move(id)},dimension,{}});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

SetHandle singleton_relation(std::string id,Vector point) {
    auto snapshot=numeric::snapshot_vector(point);
    REQUIRE(std::holds_alternative<numeric::VectorView>(snapshot));
    auto data=sets::make_singleton({SetId{std::move(id)},point.size(),{}},
        std::get<numeric::VectorView>(std::move(snapshot)));
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

sets::SetData singleton_data(Vector point) {
    auto snapshot=numeric::snapshot_vector(point);
    REQUIRE(std::holds_alternative<numeric::VectorView>(snapshot));
    auto data=sets::make_singleton({SetId{"fixture.singleton"},point.size(),{}},
        std::get<numeric::VectorView>(std::move(snapshot)));
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data));
}

std::pair<model::HybridSystem,model::HybridRequest> exact_singleton_portfolio() {
    model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={Singleton{{1}}};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"target"},2,0,{"y","z"},{}};
    target.flow=LinearStage{Matrix{2,2,{1,0,0,1}},Matrix{2,0,{}},Matrix{2,0,{}},Vector{0,0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{2},UniversalSet{2}};
    model::HybridSystem system{1,{source,target},
        {{{"tie-a"},{"source"},{"target"},{Singleton{{3}}},{singleton_relation("reset-a",{3,0,0})}},
         {{"tie-b"},{"source"},{"target"},{Singleton{{3}}},{singleton_relation("reset-b",{3,0,0})}},
         {{"worse"},{"source"},{"target"},{Singleton{{3}}},{singleton_relation("reset-worse",{3,1,0})}}}};
    model::HybridRequest request{{{"source"},{2}},{{"target"}},
        {{{"target"},LinearTerminal{{1,0},0},"cost","u"}}};
    return {std::move(system),std::move(request)};
}

struct OneStepOracleBranch {
    model::HybridPath path;
    Vector joint_tuple;
    double objective{};
};

std::size_t equality_rank(const numeric::MatrixView& equalities) {
    std::vector<Vector> reduced(equalities.rows(),Vector(equalities.cols()));
    for(std::size_t row=0;row<equalities.rows();++row)
        for(std::size_t col=0;col<equalities.cols();++col)
            reduced[row][col]=equalities(row,col);
    std::size_t rank=0;
    for(std::size_t col=0;col<equalities.cols() && rank<reduced.size();++col) {
        auto pivot=rank;
        while(pivot<reduced.size() && reduced[pivot][col]==0) ++pivot;
        if(pivot==reduced.size()) continue;
        std::swap(reduced[pivot],reduced[rank]);
        const double scale=reduced[rank][col];
        for(std::size_t j=col;j<equalities.cols();++j) reduced[rank][j]/=scale;
        for(std::size_t row=0;row<reduced.size();++row) {
            if(row==rank) continue;
            const double factor=reduced[row][col];
            for(std::size_t j=col;j<equalities.cols();++j)
                reduced[row][j]-=factor*reduced[rank][j];
        }
        ++rank;
    }
    return rank;
}

bool equality_rows_have_full_column_rank(const numeric::MatrixView& equalities) {
    return equality_rank(equalities)==equalities.cols();
}

bool has_conflicting_equalities(const sets::HRepresentation& relation) {
    std::vector<Vector> augmented(relation.equalities.rows(),Vector(relation.equalities.cols()+1));
    for(std::size_t row=0;row<relation.equalities.rows();++row) {
        for(std::size_t col=0;col<relation.equalities.cols();++col)
            augmented[row][col]=relation.equalities(row,col);
        augmented[row].back()=relation.equality_values[row];
    }
    std::size_t pivot_row=0;
    for(std::size_t col=0;col<relation.equalities.cols() && pivot_row<augmented.size();++col) {
        auto pivot=pivot_row;
        while(pivot<augmented.size() && augmented[pivot][col]==0) ++pivot;
        if(pivot==augmented.size()) continue;
        std::swap(augmented[pivot],augmented[pivot_row]);
        const double scale=augmented[pivot_row][col];
        for(std::size_t j=col;j<=relation.equalities.cols();++j)
            augmented[pivot_row][j]/=scale;
        for(std::size_t row=0;row<augmented.size();++row) {
            if(row==pivot_row) continue;
            const double factor=augmented[row][col];
            for(std::size_t j=col;j<=relation.equalities.cols();++j)
                augmented[row][j]-=factor*augmented[pivot_row][j];
        }
        ++pivot_row;
    }
    return std::any_of(augmented.begin(),augmented.end(),[&](const auto& row) {
        const bool zero_coefficients=std::all_of(row.begin(),row.end()-1,[](double value) { return value==0; });
        return zero_coefficients && row.back()!=0;
    });
}

// Deliberately independent of the production path enumerator, relation
// composer, and verifier. This small exhaustive oracle directly interprets
// the one-step singleton fixture from its raw mode/edge data.
std::vector<OneStepOracleBranch> enumerate_one_step_singleton_oracle(
    const model::HybridSystem& system,const model::HybridRequest& request) {
    REQUIRE(system.horizon==1);
    std::vector<OneStepOracleBranch> branches;
    const auto source=std::find_if(system.modes.begin(),system.modes.end(),[&](const auto& mode) {
        return mode.id==request.initial.mode;
    });
    REQUIRE(source!=system.modes.end());
    const auto* flow=std::get_if<LinearStage>(&source->flow);
    REQUIRE(flow!=nullptr);
    REQUIRE(flow->A.rows==request.initial.state.size());
    REQUIRE(flow->A.cols==request.initial.state.size());
    REQUIRE(flow->B.cols==source->control_dimension);
    REQUIRE(flow->B.rows==flow->A.rows);
    REQUIRE(flow->offset.size()==flow->A.rows);
    REQUIRE(source->control_sets.size()==1);
    const auto* control_singleton=std::get_if<Singleton>(&source->control_sets[0]);
    REQUIRE(control_singleton!=nullptr);
    const Vector control=control_singleton->point;
    Vector pre(flow->A.rows);
    for(std::size_t row=0;row<pre.size();++row) {
        pre[row]=flow->offset[row];
        for(std::size_t col=0;col<request.initial.state.size();++col)
            pre[row]+=flow->A.values[row*flow->A.cols+col]*request.initial.state[col];
        for(std::size_t col=0;col<control.size();++col)
            pre[row]+=flow->B.values[row*flow->B.cols+col]*control[col];
    }

    for(const auto& edge:system.edges) {
        if(edge.source!=request.initial.mode) continue;
        if(std::find(request.allowed_terminal_modes.begin(),request.allowed_terminal_modes.end(),edge.target)==
           request.allowed_terminal_modes.end()) continue;
        REQUIRE(edge.guards.size()==1);
        const auto* guard=std::get_if<Singleton>(&edge.guards[0]);
        REQUIRE(guard!=nullptr);
        if(guard->point!=pre) continue;
        REQUIRE(edge.reset_relations.size()==1);
        const auto reset_data=sets::from_handle(edge.reset_relations[0]);
        REQUIRE(std::holds_alternative<sets::SetData>(reset_data));
        const auto reset_rep=std::get<sets::SetData>(reset_data).representation();
        REQUIRE(std::holds_alternative<sets::SingletonRepresentation>(reset_rep));
        const auto reset_view=std::get<sets::SingletonRepresentation>(reset_rep).point;
        const auto target=std::find_if(system.modes.begin(),system.modes.end(),[&](const auto& mode) {
            return mode.id==edge.target;
        });
        REQUIRE(target!=system.modes.end());
        REQUIRE(reset_view.size()==pre.size()+target->state_dimension);
        bool reset_matches=true;
        for(std::size_t i=0;i<pre.size();++i) reset_matches=reset_matches && reset_view[i]==pre[i];
        if(!reset_matches) continue;
        Vector post(reset_view.size()-pre.size());
        for(std::size_t i=0;i<post.size();++i) post[i]=reset_view[pre.size()+i];
        const auto objective=std::find_if(request.terminal_objectives.begin(),request.terminal_objectives.end(),
            [&](const auto& candidate) { return candidate.mode==edge.target; });
        REQUIRE(objective!=request.terminal_objectives.end());
        const auto* linear=std::get_if<LinearTerminal>(&objective->objective);
        REQUIRE(linear!=nullptr);
        REQUIRE(linear->coefficients.size()==post.size());
        double cost=linear->offset;
        for(std::size_t i=0;i<post.size();++i) cost+=linear->coefficients[i]*post[i];
        Vector joint=request.initial.state;
        joint.insert(joint.end(),control.begin(),control.end());
        joint.insert(joint.end(),pre.begin(),pre.end());
        joint.insert(joint.end(),post.begin(),post.end());
        branches.push_back({{{request.initial.mode,edge.target},{edge.id}},std::move(joint),cost});
    }
    return branches;
}

HybridPathOptimalFaceCandidate exact_candidate(const HybridPathProgram& program,Vector point) {
    const auto& linear=std::get<LinearProgram>(program.program);
    const auto support=SymbolicArgument{"exact singleton fixture","literal exact branch"};
    ProgramResult result{Termination::completed,
        {linear.identity(),MathematicalOutcome::optimal,support,{}},point,{},"exact fixture"};
    return {program.path,program.joint_relation,std::move(point),std::move(result),{},
        "independently specified singleton branch",{}};
}

model::HybridSystem example_system() {
    model::HybridMode source{{"source"},1,1,{"position"},{"thrust"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={UniversalSet{1}};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"target"},2,0,{"position","velocity"},{}};
    target.flow=LinearStage{Matrix{2,2,{1,0,0,1}},Matrix{2,0,{}},Matrix{2,0,{}},Vector{0,0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{2},UniversalSet{2}};
    model::HybridTransitionEdge edge{{"switch"},{"source"},{"target"},
        {UniversalSet{1}},{universal("reset",3)}};
    return {1,{std::move(source),std::move(target)},{std::move(edge)}};
}

model::HybridRequest example_request() {
    return {{{"source"},{2}},{{"target"}},
        {{{"target"},LinearTerminal{{2,-1},0},"energy","J"}}};
}

model::HybridPath example_path() {
    return {{{"source"},{"target"}},{{"switch"}}};
}

class RejectingTrajectoryAdapter final : public HybridDirectTrajectoryAdapter {
public:
    mutable int calls{};
    mutable int capability_calls{};
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&, const model::HybridPath&, ProblemId,
        model::HybridRelationLimits, optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.hybrid_adapter","fixture rejection"}};
    }
};

class LinearOnlyRejectingTrajectoryAdapter final : public HybridDirectTrajectoryAdapter {
public:
    mutable int calls{};
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        return {true,true,false,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&, const model::HybridPath&, ProblemId,
        model::HybridRelationLimits, optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.hybrid_adapter","fixture rejection"}};
    }
};

class RejectingTrajectoryPreflightAdapter final : public HybridDirectTrajectoryAdapter {
public:
    int corruption{2};
    mutable int preflight_calls{};
    mutable int capability_calls{};
    mutable int build_calls{};
    HybridDirectTrajectoryPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath> paths,
        model::HybridRelationLimits limits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++preflight_calls;
        auto path=paths.back();
        auto reported_limits=limits;
        if(corruption==0) path.edges.front().value+="-wrong";
        if(corruption==1) ++reported_limits.max_rows;
        return model::HybridPathCompositionFailureReport{std::move(path),reported_limits,{},
            Diagnostic{DiagnosticCode::unsupported,"fixture.trajectory.preflight",
                "fixture rejects a later path operation"}};
    }
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath&,ProblemId,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++build_calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.trajectory","unexpected build"}};
    }
};

class CancellingTrajectoryPreflightAdapter final : public HybridDirectTrajectoryAdapter {
public:
    explicit CancellingTrajectoryPreflightAdapter(std::stop_source& cancellation)
        : cancellation_(&cancellation) {}
    mutable int capability_calls{};
    mutable int build_calls{};
    HybridDirectTrajectoryPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath>,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        cancellation_->request_stop();
        return std::monostate{};
    }
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath&,ProblemId,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++build_calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.trajectory","unexpected build"}};
    }
private:
    std::stop_source* cancellation_;
};

class AdmittingTrajectoryPreflightAdapter final : public HybridDirectTrajectoryAdapter {
public:
    mutable int preflight_calls{};
    mutable int capability_calls{};
    mutable int build_calls{};
    HybridDirectTrajectoryPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath>,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++preflight_calls;
        return std::monostate{};
    }
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath&,ProblemId,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++build_calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.alternate_representation",
            "fixture stopped after custom operation admission"}};
    }
};

class InventoryOnlyTrajectoryPreflightAdapter final : public HybridDirectTrajectoryAdapter {
public:
    mutable int preflight_calls{};
    mutable int capability_calls{};
    mutable int build_calls{};
    HybridDirectTrajectoryPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath> paths,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++preflight_calls;
        if(paths.size()==2) return std::monostate{};
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.inventory_only",
            "preflight requires the complete path inventory"}};
    }
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath&,ProblemId,
        model::HybridRelationLimits,optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++build_calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.inventory_build",
            "fixture stopped after full inventory admission"}};
    }
};

class CancellingCapabilityTrajectoryAdapter final : public HybridDirectTrajectoryAdapter {
public:
    explicit CancellingCapabilityTrajectoryAdapter(std::stop_source& cancellation)
        : cancellation_(&cancellation) {}
    mutable int calls{};
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override {
        cancellation_->request_stop();
        return {true,true,true,Assurance::numerical};
    }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&, const model::HybridPath&, ProblemId,
        model::HybridRelationLimits, optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.hybrid_adapter","fixture rejection"}};
    }
private:
    std::stop_source* cancellation_;
};

class MismatchingTrajectoryAdapter final : public HybridDirectTrajectoryAdapter {
public:
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override { return {true,true,true,Assurance::numerical}; }
    HybridPathProgramResult build_path(const model::HybridSystem& system,
        const model::HybridRequest& request, const model::HybridPath& path, ProblemId problem,
        model::HybridRelationLimits limits, optimization::ObjectivePolicy policy,
        std::stop_token cancellation) const override {
        JointHDirectTrajectoryAdapter delegate;
        auto built=delegate.build_path(system,request,path,std::move(problem),limits,policy,cancellation);
        if(auto* program=std::get_if<HybridPathProgram>(&built))
            program->path.edges.front().value="wrong-edge";
        return built;
    }
};

class RejectingReachabilityAdapter final : public HybridReachabilityAdapter {
public:
    mutable int calls{};
    mutable int capability_calls{};
    HybridReachabilityCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,Assurance::numerical};
    }
    HybridReachabilityPreflightResult preflight(const model::HybridSystem& system,
        const model::HybridRequest& request,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token cancellation) const override {
        return model::preflight_hybrid_path_relations(system,request,
            std::span<const model::HybridPath>(&path,1),limits,cancellation);
    }
    HybridPathReachabilityResult compose_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token) const override {
        ++calls;
        return model::HybridPathCompositionFailureReport{path,limits,{},
            Diagnostic{DiagnosticCode::unsupported,"fixture.reachability","fixture rejection"}};
    }
};

class DefaultPreflightReachabilityAdapter final : public HybridReachabilityAdapter {
public:
    mutable int calls{};
    mutable int capability_calls{};
    HybridReachabilityCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,Assurance::numerical};
    }
    HybridPathReachabilityResult compose_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token) const override {
        ++calls;
        return model::HybridPathCompositionFailureReport{path,limits,{},
            Diagnostic{DiagnosticCode::unsupported,"fixture.reachability","fixture rejection"}};
    }
};

class MisreportingReachabilityPreflightAdapter final : public HybridReachabilityAdapter {
public:
    int corruption{};
    mutable int capability_calls{};
    mutable int calls{};
    HybridReachabilityCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,Assurance::numerical};
    }
    HybridReachabilityPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token) const override {
        auto reported_path=path;
        auto reported_limits=limits;
        if(corruption==0) reported_path.edges.front().value+="-wrong";
        else ++reported_limits.max_rows;
        return model::HybridPathCompositionFailureReport{std::move(reported_path),
            reported_limits,{},Diagnostic{DiagnosticCode::unsupported,
                "fixture.reachability.preflight","fixture preflight rejection"}};
    }
    HybridPathReachabilityResult compose_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token) const override {
        ++calls;
        return model::HybridPathCompositionFailureReport{path,limits,{},
            Diagnostic{DiagnosticCode::unsupported,"fixture.reachability","not expected"}};
    }
};

class CancellingReachabilityPreflightAdapter final : public HybridReachabilityAdapter {
public:
    explicit CancellingReachabilityPreflightAdapter(std::stop_source& cancellation)
        : cancellation_(&cancellation) {}
    mutable int capability_calls{};
    mutable int calls{};
    HybridReachabilityCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,Assurance::numerical};
    }
    HybridReachabilityPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath&,
        model::HybridRelationLimits,std::stop_token) const override {
        cancellation_->request_stop();
        return std::monostate{};
    }
    HybridPathReachabilityResult compose_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token) const override {
        ++calls;
        return model::HybridPathCompositionFailureReport{path,limits,{},
            Diagnostic{DiagnosticCode::unsupported,"fixture.reachability","not expected"}};
    }
private:
    std::stop_source* cancellation_;
};

class MisreportingReachabilityAdapter final : public HybridReachabilityAdapter {
public:
    int corruption{};
    HybridReachabilityCapabilities capabilities() const noexcept override { return {true,Assurance::numerical}; }
    HybridReachabilityPreflightResult preflight(const model::HybridSystem& system,
        const model::HybridRequest& request,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token cancellation) const override {
        return model::preflight_hybrid_path_relations(system,request,
            std::span<const model::HybridPath>(&path,1),limits,cancellation);
    }
    HybridPathReachabilityResult compose_path(const model::HybridSystem& system,
        const model::HybridRequest& request,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token cancellation) const override {
        JointHReachabilityAdapter delegate;
        auto result=delegate.compose_path(system,request,path,limits,cancellation);
        if(auto* reachable=std::get_if<HybridPathReachability>(&result)) {
            if(corruption==0) reachable->assurance=Assurance::validated;
            else if(corruption==1) ++reachable->relation_limits.max_rows;
            else if(corruption==2) ++reachable->relation_operations.front().rows_added;
            else if(corruption==3) reachable->relation_operations.front().stage=1;
            else {
                for(auto& operation:reachable->relation_operations) {
                    operation.joint_variables=0;
                    operation.cumulative_matrix_elements=0;
                }
            }
        }
        return result;
    }
};

class FixtureHybridFamilyVerifier final : public HybridFamilyVerificationAdapter {
public:
    mutable int calls{};
    mutable int preflight_calls{};
    mutable int capability_calls{};
    bool omit_last_branch{};
    bool claim_established_aggregates{};
    bool claim_coverage_only{};
    bool mark_all_branches_refuted{};
    bool inject_candidate_providers{};
    HybridFamilyVerificationCapabilities capabilities() const noexcept override {
        ++capability_calls;
        return {true,true,true,Assurance::numerical};
    }
    HybridFamilyVerificationPreflightResult preflight(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath>,
        std::stop_token cancellation) const override {
        ++preflight_calls;
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"fixture preflight cancelled"};
        return std::monostate{};
    }
    HybridFamilyVerificationResult verify(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath> paths,
        std::span<const HybridPathProgram>,std::span<const HybridPathOptimalFaceCandidate>,
        NumericalPolicy policy,std::stop_token cancellation) const override {
        ++calls;
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"fixture verifier cancelled"};
        std::vector<model::HybridPath> inventory(paths.begin(),paths.end());
        std::vector<HybridPathVerificationRecord> branches;
        const auto count=omit_last_branch && !paths.empty()?paths.size()-1:paths.size();
        for(std::size_t i=0;i<count;++i) {
            const auto status=mark_all_branches_refuted?HybridVerificationStatus::refuted:
                (claim_coverage_only?HybridVerificationStatus::established:
                    HybridVerificationStatus::unsupported);
            branches.push_back({paths[i],status,status,status,{}});
            if(inject_candidate_providers)
                branches.back().candidate_providers.push_back({"fabricated provider",
                    {"fabricated.id",std::string{"0"}},registry::Identity{{"fabricated.id"},"0"}});
        }
        const auto aggregate=claim_established_aggregates?HybridVerificationStatus::established:
            HybridVerificationStatus::unsupported;
        const auto global=claim_established_aggregates?HybridVerificationStatus::established:
            HybridVerificationStatus::unsupported;
        const auto coverage=claim_coverage_only?HybridVerificationStatus::established:aggregate;
        return HybridFamilyVerificationReport{"fixture.hybrid.verifier","1",policy,
            Assurance::numerical,std::move(inventory),std::move(branches),
            global,coverage};
    }
};

class DefaultPreflightHybridFamilyVerifier final : public HybridFamilyVerificationAdapter {
public:
    HybridFamilyVerificationCapabilities capabilities() const noexcept override {
        return {true,true,true,Assurance::numerical};
    }
    HybridFamilyVerificationResult verify(const model::HybridSystem&,
        const model::HybridRequest&,std::span<const model::HybridPath>,
        std::span<const HybridPathProgram>,std::span<const HybridPathOptimalFaceCandidate>,
        NumericalPolicy,std::stop_token) const override {
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.hybrid.verifier","not used"}};
    }
};

std::pair<model::HybridSystem,model::HybridRequest> variable_size_parallel_profile() {
    auto source=model::HybridMode{{"source"},1,0,{"x"},{}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={UniversalSet{0}};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    auto small=model::HybridMode{{"small"},1,0,{"x"},{}};
    small.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    small.control_sets={UniversalSet{0}};
    small.invariants={UniversalSet{1},UniversalSet{1}};
    auto large=model::HybridMode{{"large"},2,0,{"x","y"},{}};
    large.flow=LinearStage{Matrix{2,2,{1,0,0,1}},Matrix{2,0,{}},Matrix{2,0,{}},Vector{0,0}};
    large.control_sets={UniversalSet{0}};
    large.invariants={UniversalSet{2},UniversalSet{2}};
    model::HybridSystem system{1,{source,small,large},
        {{{"to-small"},{"source"},{"small"},{UniversalSet{1}},{universal("small-reset",2)}},
         {{"to-large"},{"source"},{"large"},{UniversalSet{1}},{universal("large-reset",3)}}}};
    model::HybridRequest request{{{"source"},{0}},{{"small"},{"large"}},
        {{{"small"},LinearTerminal{{1},0},"cost","u"},
         {{"large"},LinearTerminal{{1,0},0},"cost","u"}}};
    return {std::move(system),std::move(request)};
}

SetHandle interval(std::string id,double lower,double upper) {
    auto matrix=numeric::snapshot(Matrix{2,1,{-1,1}});
    auto bounds=numeric::snapshot_vector(Vector{-lower,upper});
    auto equalities=numeric::snapshot(Matrix{0,1,{}});
    auto rhs=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(matrix));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rhs));
    auto data=sets::make_h({SetId{std::move(id)},1,{"guard-coordinate"}},
        {std::get<numeric::MatrixView>(matrix),std::get<numeric::VectorView>(bounds),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

SetHandle vertex_guard(std::string id) {
    const auto vertices=numeric::snapshot(Matrix{1,1,{0}});
    const auto rays=numeric::snapshot(Matrix{0,1,{}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(vertices));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rays));
    auto data=sets::make_v({SetId{std::move(id)},1,{"guard-coordinate"}},
        {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(rays)});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

SetHandle affine_reset() {
    auto inequalities=numeric::snapshot(Matrix{0,3,{}});
    auto upper=numeric::snapshot_vector(Vector{});
    auto equalities=numeric::snapshot(Matrix{1,3,{-1,1,0}});
    auto rhs=numeric::snapshot_vector(Vector{0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(upper));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rhs));
    auto data=sets::make_h({{"affine-reset"},3,{}},
        {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(upper),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

sets::SetData relation_excluding_anchor() {
    auto inequalities=numeric::snapshot(Matrix{0,5,{}});
    auto upper=numeric::snapshot_vector(Vector{});
    auto equalities=numeric::snapshot(Matrix{1,5,{1,0,0,0,0}});
    auto rhs=numeric::snapshot_vector(Vector{0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(upper));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rhs));
    auto data=sets::make_h({{"wrong-joint-relation"},5,{}},
        {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(upper),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data));
}

bool satisfies(const sets::HRepresentation& h,const Vector& point) {
    for(std::size_t i=0;i<h.inequalities.rows();++i) {
        double value=0;
        for(std::size_t j=0;j<h.inequalities.cols();++j) value+=h.inequalities(i,j)*point[j];
        if(value>h.upper_bounds[i]) return false;
    }
    for(std::size_t i=0;i<h.equalities.rows();++i) {
        double value=0;
        for(std::size_t j=0;j<h.equalities.cols();++j) value+=h.equalities(i,j)*point[j];
        if(value!=h.equality_values[i]) return false;
    }
    return true;
}

class RejectingLP final : public LPWorkspace {
    ProgramOutcome do_solve(const LinearProgram&,const ExecutionContext&) override {
        return Unsupported{{{DiagnosticCode::unsupported,"fixture.lp","fixture rejection"}}};
    }
};

class CompletingLP final : public LPWorkspace {
    ProgramOutcome do_solve(const LinearProgram& program,const ExecutionContext&) override {
        return ProgramResult{Termination::completed,
            {program.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},
            {},{},"fixture completed"};
    }
};

class RejectingConvex final : public ConvexWorkspace {
    ProgramOutcome do_solve(const ConvexProgram&,const ExecutionContext&) override {
        return Unsupported{{{DiagnosticCode::unsupported,"fixture.convex","fixture rejection"}}};
    }
};

registry::PreparedProvider<registry::LPPort> lp_provider(std::stop_source* cancel_during_prepare=nullptr,
    std::shared_ptr<int> factory_calls=std::make_shared<int>(0),std::string reject_problem={},
    std::string cancel_problem={}) {
    registry::Registry<registry::LPPort> providers;
    REQUIRE_FALSE(providers.add({{{"reject-lp"},"1"},
        [cancel_during_prepare,reject_problem,cancel_problem](const LinearProgram& program,const registry::Requirements&)->registry::Capability{
            if(cancel_during_prepare && (cancel_problem.empty() || program.identity().problem.value==cancel_problem))
                cancel_during_prepare->request_stop();
            if(program.identity().problem.value==reject_problem && !reject_problem.empty())
                return Diagnostics{{DiagnosticCode::unsupported,"fixture.capability","requested fixture rejection"}};
            return registry::Offer{};
        },
        [factory_calls](const LinearProgram&){++*factory_calls; return std::make_unique<RejectingLP>();}}));
    auto prepared=registry::prepare_provider(registry::select_provider(providers,{{"reject-lp"},{}}));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(prepared));
    return std::get<registry::PreparedProvider<registry::LPPort>>(std::move(prepared));
}

registry::PreparedProvider<registry::LPPort> completing_lp_provider() {
    registry::Registry<registry::LPPort> providers;
    REQUIRE_FALSE(providers.add({{{"completing-lp"},"1"},
        [](const LinearProgram&,const registry::Requirements&)->registry::Capability{return registry::Offer{};},
        [](const LinearProgram&){return std::make_unique<CompletingLP>();}}));
    auto prepared=registry::prepare_provider(registry::select_provider(providers,{{"completing-lp"},{}}));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::LPPort>>(prepared));
    return std::get<registry::PreparedProvider<registry::LPPort>>(std::move(prepared));
}

registry::PreparedProvider<registry::ConvexPort> convex_provider() {
    registry::Registry<registry::ConvexPort> providers;
    REQUIRE_FALSE(providers.add({{{"reject-convex"},"1"},
        [](const ConvexProgram&,const registry::Requirements&)->registry::Capability{return registry::Offer{};},
        [](const ConvexProgram&){return std::make_unique<RejectingConvex>();}}));
    auto prepared=registry::prepare_provider(registry::select_provider(providers,{{"reject-convex"},{}}));
    REQUIRE(std::holds_alternative<registry::PreparedProvider<registry::ConvexPort>>(prepared));
    return std::get<registry::PreparedProvider<registry::ConvexPort>>(std::move(prepared));
}
}

TEST_CASE("hybrid direct path program preserves branch and terminal objective coordinates") {
    const auto result=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(result));
    const auto& built=std::get<HybridPathProgram>(result);
    REQUIRE(std::holds_alternative<LinearProgram>(built.program));
    const auto& program=std::get<LinearProgram>(built.program);
    CHECK(program.identity().problem.value=="hybrid-problem");
    CHECK(program.identity().program.value=="hybrid-path:6:switch");
    CHECK(program.objective().size()==5);
    CHECK(program.objective()[0]==0);
    CHECK(program.objective()[1]==0);
    CHECK(program.objective()[2]==0);
    CHECK(program.objective()[3]==2);
    CHECK(program.objective()[4]==-1);
    const auto constraints=std::get<numeric::CsrInput>(program.constraints().descriptor());
    CHECK(std::vector<std::size_t>(constraints.row_offsets.begin(),constraints.row_offsets.end())==
        std::vector<std::size_t>{0,1,4});
    CHECK(std::vector<std::size_t>(constraints.column_indices.begin(),constraints.column_indices.end())==
        std::vector<std::size_t>{0,0,1,2});
    CHECK(std::vector<double>(constraints.values.begin(),constraints.values.end())==
        std::vector<double>{1,-1,-1,1});
    CHECK(program.rows().size()==2);
    CHECK(program.rows()[0].lower==2);
    CHECK(program.rows()[0].upper==2);
    CHECK(program.rows()[1].lower==0);
    CHECK(program.rows()[1].upper==0);
    CHECK(built.joint_relation.metadata()->set.dimension==5);
    CHECK(built.path==example_path());
    CHECK(built.relation_limits.max_variables==16);
    REQUIRE(built.relation_operations.size()==8);
    CHECK(built.relation_operations[2].operation==model::HybridRelationOperationKind::mode_flow);
    CHECK(built.relation_operations[2].mode==model::HybridModeId{"source"});
    CHECK(built.relation_operations[5].operation==model::HybridRelationOperationKind::transition_guard);
    CHECK(built.relation_operations[5].edge==model::HybridEdgeId{"switch"});
}

TEST_CASE("hybrid program construction preserves cancellation and unsupported limits") {
    std::stop_source cancellation;
    cancellation.request_stop();
    const auto stopped=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024},{},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(stopped));
    CHECK(std::get<OperationStopped>(stopped).reason==StopReason::cancelled);

    const auto limited=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{4,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(limited));
    const auto& failure=std::get<model::HybridPathCompositionFailureReport>(limited);
    CHECK(failure.path==example_path());
    CHECK(failure.limits.max_variables==4);
    const auto* diagnostic=std::get_if<Diagnostic>(&failure.failure);
    REQUIRE(diagnostic);
    CHECK(diagnostic->code==DiagnosticCode::unsupported);
}

TEST_CASE("hybrid direct path programs admit quadratic and residual terminal objectives") {
    auto request=example_request();
    request.terminal_objectives[0].objective=QuadraticTerminal{
        Matrix{2,2,{1,0,0,1}},Vector{0,0},0};
    auto quadratic=build_hybrid_path_program(example_system(),request,example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(quadratic));
    REQUIRE(std::holds_alternative<ConvexProgram>(std::get<HybridPathProgram>(quadratic).program));
    CHECK(std::get<ConvexProgram>(std::get<HybridPathProgram>(quadratic).program).original_objective().dimension()==5);

    request.terminal_objectives[0].objective=ResidualNormTerminal{Matrix{1,2,{1,-1}},Vector{0}};
    auto residual=build_hybrid_path_program(example_system(),request,example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(residual));
    REQUIRE(std::holds_alternative<ConvexProgram>(std::get<HybridPathProgram>(residual).program));
    CHECK(std::get<ConvexProgram>(std::get<HybridPathProgram>(residual).program).original_objective().dimension()==5);
}

TEST_CASE("hybrid portfolio builder returns every parallel edge branch transactionally") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel"};
    system.edges.push_back(std::move(parallel));
    const auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==2);
    CHECK(programs[0].path.modes==programs[1].path.modes);
    CHECK(programs[0].path.edges!=programs[1].path.edges);
    const auto& first=std::get<LinearProgram>(programs[0].program);
    const auto& second=std::get<LinearProgram>(programs[1].program);
    CHECK(first.identity().program!=second.identity().program);

    const auto limited=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{4,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(limited));
    const auto& failure=std::get<model::HybridPathCompositionFailureReport>(limited);
    CHECK(failure.path==example_path());
    const auto* diagnostic=std::get_if<Diagnostic>(&failure.failure);
    REQUIRE(diagnostic);
    CHECK(diagnostic->field=="hybrid.relation.variables");
}

TEST_CASE("hybrid portfolio builder dispatches through the injected direct trajectory adapter") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel"};
    system.edges.push_back(std::move(parallel));
    RejectingTrajectoryAdapter adapter;
    const auto result=build_hybrid_portfolio_programs(adapter,system,example_request(),
        {"hybrid-problem"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="fixture.hybrid_adapter");
    CHECK(adapter.calls==1);
}

TEST_CASE("hybrid portfolio preflights all terminal objective capabilities before adapter dispatch") {
    auto system=example_system();
    auto second_terminal=system.modes.back();
    second_terminal.id={"target-quadratic"};
    system.modes.push_back(std::move(second_terminal));
    auto second_edge=system.edges.front();
    second_edge.id={"switch-quadratic"};
    second_edge.target={"target-quadratic"};
    system.edges.push_back(std::move(second_edge));

    auto request=example_request();
    request.allowed_terminal_modes.push_back({"target-quadratic"});
    request.terminal_objectives.push_back({{"target-quadratic"},
        QuadraticTerminal{Matrix{2,2,{1,0,0,1}},Vector{0,0},0},"energy","J"});

    LinearOnlyRejectingTrajectoryAdapter adapter;
    const auto result=build_hybrid_portfolio_programs(adapter,system,request,
        {"hybrid-problem"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.portfolio.objective");
    CHECK(adapter.calls==0);

    FixtureHybridFamilyVerifier verifier;
    LinearOnlyRejectingTrajectoryAdapter verified_adapter;
    const auto verified=build_hybrid_portfolio_programs_with_verifier(verifier,verified_adapter,
        system,request,{"hybrid-problem"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(verified));
    CHECK(std::get<Diagnostics>(verified).front().code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(verified).front().field=="hybrid.portfolio.objective");
    CHECK(verified_adapter.calls==0);
}

TEST_CASE("hybrid portfolio capability preflight honors cancellation before scanning paths") {
    std::stop_source cancellation;
    CancellingCapabilityTrajectoryAdapter adapter{cancellation};
    const auto result=build_hybrid_portfolio_programs(adapter,example_system(),example_request(),
        {"hybrid-problem"},{1,8},{16,64,1024},{},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
    CHECK(adapter.calls==0);
}

TEST_CASE("hybrid portfolio preflights objective policy before adapter dispatch") {
    RejectingTrajectoryAdapter validated_adapter;
    optimization::ObjectivePolicy validated_policy;
    validated_policy.assurance=Assurance::validated;
    const auto validated=build_hybrid_portfolio_programs(validated_adapter,
        example_system(),example_request(),{"hybrid-problem"},{1,8},{16,64,1024},
        validated_policy);
    REQUIRE(std::holds_alternative<Diagnostics>(validated));
    CHECK(std::get<Diagnostics>(validated).front().code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(validated).front().field=="hybrid.adapter.objective_policy");
    CHECK(validated_adapter.calls==0);
    CHECK(validated_adapter.capability_calls==0);

    FixtureHybridFamilyVerifier verifier;
    RejectingTrajectoryAdapter verified_adapter;
    const auto verified=build_hybrid_portfolio_programs_with_verifier(verifier,verified_adapter,
        example_system(),example_request(),{"hybrid-problem"},{1,8},{16,64,1024},
        validated_policy);
    REQUIRE(std::holds_alternative<Diagnostics>(verified));
    CHECK(std::get<Diagnostics>(verified).front().code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(verified).front().field=="hybrid.adapter.objective_policy");
    CHECK(verified_adapter.calls==0);
    CHECK(verified_adapter.capability_calls==0);
    CHECK(verifier.capability_calls==0);
    CHECK(verifier.preflight_calls==0);

    RejectingTrajectoryAdapter invalid_tolerance_adapter;
    optimization::ObjectivePolicy invalid_tolerance_policy;
    invalid_tolerance_policy.numerical.absolute_tolerance=
        std::numeric_limits<double>::quiet_NaN();
    const auto invalid_tolerance=build_hybrid_portfolio_programs(invalid_tolerance_adapter,
        example_system(),example_request(),{"hybrid-problem"},{1,8},{16,64,1024},
        invalid_tolerance_policy);
    REQUIRE(std::holds_alternative<Diagnostics>(invalid_tolerance));
    CHECK(std::get<Diagnostics>(invalid_tolerance).front().code==DiagnosticCode::invalid_input);
    CHECK(std::get<Diagnostics>(invalid_tolerance).front().field=="hybrid.adapter.objective_policy");
    CHECK(invalid_tolerance_adapter.calls==0);
    CHECK(invalid_tolerance_adapter.capability_calls==0);
}

TEST_CASE("hybrid path builder validates objective policy before adapter dispatch") {
    RejectingTrajectoryAdapter validated_adapter;
    optimization::ObjectivePolicy validated_policy;
    validated_policy.assurance=Assurance::validated;
    const auto validated=build_hybrid_path_program(validated_adapter,example_system(),
        example_request(),example_path(),{"hybrid-problem"},{16,64,1024},validated_policy);
    REQUIRE(std::holds_alternative<Diagnostics>(validated));
    CHECK(std::get<Diagnostics>(validated).front().code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostics>(validated).front().field=="hybrid.adapter.objective_policy");
    CHECK(validated_adapter.calls==0);
    CHECK(validated_adapter.capability_calls==0);

    RejectingTrajectoryAdapter invalid_tolerance_adapter;
    optimization::ObjectivePolicy invalid_tolerance_policy;
    invalid_tolerance_policy.numerical.absolute_tolerance=
        std::numeric_limits<double>::quiet_NaN();
    const auto invalid_tolerance=build_hybrid_path_program(invalid_tolerance_adapter,
        example_system(),example_request(),example_path(),{"hybrid-problem"},
        {16,64,1024},invalid_tolerance_policy);
    REQUIRE(std::holds_alternative<Diagnostics>(invalid_tolerance));
    CHECK(std::get<Diagnostics>(invalid_tolerance).front().code==DiagnosticCode::invalid_input);
    CHECK(std::get<Diagnostics>(invalid_tolerance).front().field=="hybrid.adapter.objective_policy");
    CHECK(invalid_tolerance_adapter.calls==0);
    CHECK(invalid_tolerance_adapter.capability_calls==0);

    RejectingTrajectoryAdapter unknown_assurance_adapter;
    optimization::ObjectivePolicy unknown_assurance_policy;
    unknown_assurance_policy.assurance=static_cast<Assurance>(255);
    const auto unknown_assurance=build_hybrid_path_program(unknown_assurance_adapter,
        example_system(),example_request(),example_path(),{"hybrid-problem"},
        {16,64,1024},unknown_assurance_policy);
    REQUIRE(std::holds_alternative<Diagnostics>(unknown_assurance));
    CHECK(std::get<Diagnostics>(unknown_assurance).front().code==DiagnosticCode::invalid_input);
    CHECK(std::get<Diagnostics>(unknown_assurance).front().field=="hybrid.adapter.objective_policy");
    CHECK(unknown_assurance_adapter.calls==0);
    CHECK(unknown_assurance_adapter.capability_calls==0);
}

TEST_CASE("hybrid path builder stops if adapter capabilities request cancellation") {
    std::stop_source cancellation;
    CancellingCapabilityTrajectoryAdapter adapter{cancellation};
    const auto result=build_hybrid_path_program(adapter,example_system(),example_request(),
        example_path(),{"hybrid-problem"},{16,64,1024},{},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
    CHECK(adapter.calls==0);
}

TEST_CASE("hybrid path builder rejects an adapter result with mismatched branch identity") {
    MismatchingTrajectoryAdapter adapter;
    const auto result=build_hybrid_path_program(adapter,example_system(),example_request(),
        example_path(),{"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.adapter.path");
}

TEST_CASE("hybrid path builder rejects a missing terminal objective before adapter dispatch") {
    auto request=example_request();
    request.terminal_objectives.clear();
    RejectingTrajectoryAdapter adapter;
    const auto result=build_hybrid_path_program(adapter,example_system(),request,
        example_path(),{"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.terminal_objectives");
    CHECK(adapter.calls==0);
}

TEST_CASE("hybrid path builder rejects a path that does not span the system horizon before dispatch") {
    auto request=example_request();
    request.allowed_terminal_modes={{"source"}};
    request.terminal_objectives={{{"source"},LinearTerminal{{1},0},"energy","J"}};
    RejectingTrajectoryAdapter adapter;
    const model::HybridPath short_path{{{"source"}},{}};
    const auto result=build_hybrid_path_program(adapter,example_system(),request,short_path,
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.adapter.path");
    CHECK(adapter.calls==0);
}

TEST_CASE("hybrid path builder preserves pre-cancellation precedence over profile validation") {
    auto request=example_request();
    request.terminal_objectives.clear();
    std::stop_source source;
    source.request_stop();
    RejectingTrajectoryAdapter adapter;
    const auto result=build_hybrid_path_program(adapter,example_system(),request,example_path(),
        {"hybrid-problem"},{16,64,1024},{},source.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
    CHECK(adapter.calls==0);
}

TEST_CASE("hybrid reachability boundary retains a branch-labelled joint relation") {
    JointHReachabilityAdapter adapter;
    const auto result=compute_hybrid_path_reachability(adapter,example_system(),example_request(),
        example_path(),{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathReachability>(result));
    const auto& reachable=std::get<HybridPathReachability>(result);
    CHECK(reachable.path==example_path());
    CHECK(reachable.assurance==Assurance::numerical);
    CHECK_FALSE(reachable.relation_operations.empty());
    CHECK(reachable.relation_limits.max_variables==16);
}

TEST_CASE("hybrid reachability boundary dispatches injected adapters and propagates rejection") {
    RejectingReachabilityAdapter adapter;
    const auto result=compute_hybrid_path_reachability(adapter,example_system(),example_request(),
        example_path(),{16,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(result));
    const auto& failure=std::get<model::HybridPathCompositionFailureReport>(result);
    CHECK(failure.path==example_path());
    CHECK(std::get<Diagnostic>(failure.failure).field=="fixture.reachability");
    CHECK(adapter.calls==1);
}

TEST_CASE("hybrid reachability preflights unsupported relations and limits before adapter calls") {
    auto unsupported_system=example_system();
    unsupported_system.edges.front().guards.front()=vertex_guard("unsupported-reachability-guard");
    RejectingReachabilityAdapter unsupported_adapter;
    const auto unsupported=compute_hybrid_path_reachability(unsupported_adapter,
        unsupported_system,example_request(),example_path(),{16,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(unsupported));
    const auto& unsupported_failure=
        std::get<model::HybridPathCompositionFailureReport>(unsupported);
    REQUIRE(std::holds_alternative<Diagnostic>(unsupported_failure.failure));
    CHECK(std::get<Diagnostic>(unsupported_failure.failure).field=="hybrid.guard.representation");
    CHECK(unsupported_adapter.capability_calls==0);
    CHECK(unsupported_adapter.calls==0);

    RejectingReachabilityAdapter limited_adapter;
    const auto limited=compute_hybrid_path_reachability(limited_adapter,example_system(),
        example_request(),example_path(),{1,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(limited));
    const auto& limited_failure=std::get<model::HybridPathCompositionFailureReport>(limited);
    REQUIRE(std::holds_alternative<Diagnostic>(limited_failure.failure));
    CHECK(std::get<Diagnostic>(limited_failure.failure).field=="hybrid.relation.variables");
    CHECK(limited_adapter.capability_calls==0);
    CHECK(limited_adapter.calls==0);
}

TEST_CASE("reachability adapter default preflight fails closed before capability queries") {
    DefaultPreflightReachabilityAdapter adapter;
    const auto result=compute_hybrid_path_reachability(adapter,example_system(),
        example_request(),example_path(),{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.reachability.preflight");
    CHECK(adapter.capability_calls==0);
    CHECK(adapter.calls==0);
}

TEST_CASE("reachability boundary validates preflight failure path and limits") {
    for(const int corruption : {0,1}) {
        MisreportingReachabilityPreflightAdapter adapter;
        adapter.corruption=corruption;
        const auto result=compute_hybrid_path_reachability(adapter,example_system(),
            example_request(),example_path(),{16,64,1024});
        REQUIRE(std::holds_alternative<Diagnostics>(result));
        const auto& diagnostic=std::get<Diagnostics>(result).front();
        if(corruption==0) CHECK(diagnostic.field=="hybrid.reachability.preflight_path");
        else CHECK(diagnostic.field=="hybrid.reachability.preflight_limits");
        CHECK(diagnostic.code==DiagnosticCode::evidence_mismatch);
        CHECK(adapter.capability_calls==0);
        CHECK(adapter.calls==0);
    }
}

TEST_CASE("reachability boundary stops after a cancelling successful preflight") {
    std::stop_source cancellation;
    CancellingReachabilityPreflightAdapter adapter{cancellation};
    const auto result=compute_hybrid_path_reachability(adapter,example_system(),
        example_request(),example_path(),{16,64,1024},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
    CHECK(adapter.capability_calls==0);
    CHECK(adapter.calls==0);
}

TEST_CASE("hybrid reachability boundary rejects mismatched assurance and resource reports") {
    for(const int corruption : {0,1,2,3,4}) {
        MisreportingReachabilityAdapter adapter;
        adapter.corruption=corruption;
        const auto result=compute_hybrid_path_reachability(adapter,example_system(),example_request(),
            example_path(),{16,64,1024});
        REQUIRE(std::holds_alternative<Diagnostics>(result));
        const auto& field=std::get<Diagnostics>(result).front().field;
        if(corruption==0) CHECK(field=="hybrid.reachability.assurance");
        else if(corruption==1) CHECK(field=="hybrid.reachability.limits");
        else CHECK(field=="hybrid.adapter.operations");
    }
}

TEST_CASE("verifier preflight rejects an unsupported domain before relation construction") {
    OneStepScalarIntervalHybridFamilyVerifier verifier;
    RejectingTrajectoryAdapter trajectory;
    const auto result=build_hybrid_portfolio_programs_with_verifier(verifier,trajectory,
        example_system(),example_request(),{"preflight-rejected"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    const auto& admission_error=std::get<Diagnostics>(result).front();
    CHECK(admission_error.field=="hybrid.verification.scalar_interval_domain");
    CHECK(admission_error.explanation.find("stage 0 edge switch")!=std::string::npos);
    CHECK(trajectory.calls==0);

    model::HybridMode source{{"preflight-source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={interval("preflight-supported-control",0,1)};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"preflight-target"},1,1,{"x"},{"u"}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{0}},Matrix{1,0,{}},Vector{0}};
    target.control_sets={Singleton{{0}}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    const auto inequalities=numeric::snapshot(Matrix{0,2,{}});
    const auto upper_bounds=numeric::snapshot_vector(Vector{});
    const auto equalities=numeric::snapshot(Matrix{1,2,{1,-1}});
    const auto equality_values=numeric::snapshot_vector(Vector{0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(upper_bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(equality_values));
    const auto identity_data=sets::make_h({{"preflight-identity-reset"},2,{"pre","post"}},
        {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(upper_bounds),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(equality_values)});
    REQUIRE(std::holds_alternative<sets::SetData>(identity_data));
    model::HybridSystem supported_system{1,{source,target},
        {{{"preflight-edge"},{"preflight-source"},{"preflight-target"},
          {interval("preflight-supported-guard",0,1)},
          {std::get<sets::SetData>(identity_data).as_handle()}}}};
    model::HybridRequest supported_request{{{"preflight-source"},{0}},{{"preflight-target"}},
        {{{"preflight-target"},LinearTerminal{{1},0},"terminal-state","units"}}};
    const auto accepted=build_hybrid_portfolio_programs_with_verifier(verifier,trajectory,
        supported_system,supported_request,{"preflight-accepted"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(accepted));
    CHECK(std::get<Diagnostics>(accepted).front().field=="fixture.hybrid_adapter");
    CHECK(trajectory.calls==1);

    auto [integral_system,integral_request]=exact_singleton_portfolio();
    ExactSingletonHybridFamilyVerifier exact_verifier;
    RejectingTrajectoryAdapter exact_trajectory;
    const auto exact_accepted=build_hybrid_portfolio_programs_with_verifier(exact_verifier,
        exact_trajectory,integral_system,integral_request,{"exact-preflight-accepted"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(exact_accepted));
    CHECK(std::get<Diagnostics>(exact_accepted).front().field=="fixture.hybrid_adapter");
    CHECK(exact_trajectory.calls==1);

    DefaultPreflightHybridFamilyVerifier default_verifier;
    RejectingTrajectoryAdapter default_trajectory;
    const auto default_rejected=build_hybrid_portfolio_programs_with_verifier(
        default_verifier,default_trajectory,supported_system,supported_request,
        {"default-preflight-rejected"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(default_rejected));
    CHECK(std::get<Diagnostics>(default_rejected).front().field=="hybrid.verification.preflight");
    CHECK(default_trajectory.calls==0);
}

TEST_CASE("portfolio preflights every path before constructing the first relation") {
    auto system=example_system();
    auto unsupported=system.edges.front();
    unsupported.id={"unsupported-switch"};
    unsupported.guards[0]=vertex_guard("unsupported-portfolio-guard");
    system.edges.push_back(std::move(unsupported));

    RejectingTrajectoryAdapter trajectory;
    const auto result=build_hybrid_portfolio_programs(trajectory,system,example_request(),
        {"portfolio-preflight"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(result));
    CHECK(std::get<model::HybridPathCompositionFailureReport>(result).path.edges[0].value==
        "unsupported-switch");
    CHECK(std::get<model::HybridPathCompositionFailureReport>(result).failure.index()==0);
    CHECK(std::get<Diagnostic>(std::get<model::HybridPathCompositionFailureReport>(result).failure).field==
        "hybrid.guard.representation");
    CHECK(std::get<Diagnostic>(std::get<model::HybridPathCompositionFailureReport>(result).failure).
        explanation.find("stage 0 edge unsupported-switch")!=std::string::npos);
    CHECK(trajectory.calls==0);
}

TEST_CASE("hybrid family verification adapter receives the exhaustive path inventory") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel"};
    system.edges.push_back(std::move(parallel));
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    FixtureHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,example_request(),programs,{},
        {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    REQUIRE(report.enumerated_paths.size()==2);
    REQUIRE(report.branches.size()==2);
    CHECK(report.branches[0].path==programs[0].path);
    CHECK(report.branches[1].path==programs[1].path);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::unsupported);
    CHECK(verifier.calls==1);
}

TEST_CASE("hybrid family verification report only retains candidate providers from supplied faces") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel"};
    system.edges.push_back(std::move(parallel));
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    FixtureHybridFamilyVerifier verifier;
    verifier.inject_candidate_providers=true;
    const auto result=verify_hybrid_portfolio_family(verifier,system,example_request(),programs,{},
        {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    REQUIRE(report.branches.size()==programs.size());
    for(const auto& branch:report.branches) CHECK(branch.candidate_providers.empty());
}

TEST_CASE("hybrid family verification rejects a missing program operation trace before dispatch") {
    auto system=example_system();
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    auto programs=std::get<std::vector<HybridPathProgram>>(std::move(built));
    programs[0].relation_operations.clear();
    FixtureHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,example_request(),programs,{},
        {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.adapter.operations");
    CHECK(verifier.calls==0);
}

TEST_CASE("hybrid family verification rejects missing inventory or report branches") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel"};
    system.edges.push_back(std::move(parallel));
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    auto programs=std::get<std::vector<HybridPathProgram>>(built);
    FixtureHybridFamilyVerifier verifier;
    programs.pop_back();
    auto incomplete=verify_hybrid_portfolio_family(verifier,system,example_request(),programs,{},
        {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<Diagnostics>(incomplete));
    CHECK(verifier.calls==0);
    programs=std::get<std::vector<HybridPathProgram>>(built);
    verifier.omit_last_branch=true;
    auto omitted=verify_hybrid_portfolio_family(verifier,system,example_request(),programs,{},
        {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<Diagnostics>(omitted));
    CHECK(std::get<Diagnostics>(omitted).front().field=="hybrid.verification.report");
    CHECK(verifier.calls==1);
}

TEST_CASE("hybrid family verification rejects aggregates unsupported by branch evidence") {
    auto system=example_system();
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    FixtureHybridFamilyVerifier verifier;
    verifier.claim_established_aggregates=true;
    const auto result=verify_hybrid_portfolio_family(verifier,system,example_request(),
        std::get<std::vector<HybridPathProgram>>(built),{}, {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.verification.consistency");
}

TEST_CASE("hybrid family verification requires global optimum before complete coverage") {
    auto system=example_system();
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    FixtureHybridFamilyVerifier verifier;
    verifier.claim_coverage_only=true;
    const auto result=verify_hybrid_portfolio_family(verifier,system,example_request(),
        std::get<std::vector<HybridPathProgram>>(built),{}, {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.verification.consistency");
}

TEST_CASE("hybrid family verification rejects global optimum with no feasible optimal branch") {
    auto system=example_system();
    auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    FixtureHybridFamilyVerifier verifier;
    verifier.claim_established_aggregates=true;
    verifier.mark_all_branches_refuted=true;
    const auto result=verify_hybrid_portfolio_family(verifier,system,example_request(),
        std::get<std::vector<HybridPathProgram>>(built),{}, {1,8},{1e-8,1e-8});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.verification.consistency");
}

TEST_CASE("exact singleton hybrid verifier independently retains every tied edge path") {
    auto [system,request]=exact_singleton_portfolio();
    auto built=build_hybrid_portfolio_programs(system,request,{"exact-hybrid"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==3);
    const Vector point{2,1,3,0,0};
    std::vector<HybridPathOptimalFaceCandidate> candidates{
        exact_candidate(programs[0],point),exact_candidate(programs[1],point)};
    candidates[0].providers.push_back({"fixture LP",{"fixture.lp",std::string{"1.0"}},
        registry::Identity{{"fixture.lp"},"1.0"}});
    ExactSingletonHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.verifier_id=="csl.hybrid.exact-singleton");
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==3);
    CHECK(report.branches[0].feasibility==HybridVerificationStatus::established);
    CHECK(report.branches[0].objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches[0].continuous_coverage==HybridVerificationStatus::established);
    CHECK(report.branches[1].objective_optimality==HybridVerificationStatus::established);
    CHECK(report.branches[2].objective_optimality==HybridVerificationStatus::refuted);
    CHECK(report.branches[2].continuous_coverage==HybridVerificationStatus::established);
    for(std::size_t i=0;i<programs.size();++i) {
        CHECK(report.branches[i].relation_limits.max_variables==programs[i].relation_limits.max_variables);
        CHECK(report.branches[i].relation_limits.max_rows==programs[i].relation_limits.max_rows);
        CHECK(report.branches[i].relation_limits.max_matrix_elements==
            programs[i].relation_limits.max_matrix_elements);
        REQUIRE(report.branches[i].relation_operations.size()==programs[i].relation_operations.size());
        CHECK_FALSE(report.branches[i].relation_operations.empty());
        CHECK(report.branches[i].relation_operations.front().implementation_id==
            programs[i].relation_operations.front().implementation_id);
        CHECK(report.branches[i].relation_operations.front().cumulative_rows==
            programs[i].relation_operations.front().cumulative_rows);
    }
    REQUIRE(report.branches[0].candidate_providers.size()==1);
    CHECK(report.branches[0].candidate_providers[0].actual->id.value=="fixture.lp");
    CHECK(report.branches[0].candidate_providers[0].actual->version=="1.0");
    CHECK(report.branches[1].candidate_providers.empty());
    CHECK(report.branches[2].candidate_providers.empty());
}

TEST_CASE("independent one-step oracle matches exhaustive hybrid portfolio and tied optimum") {
    auto [system,request]=exact_singleton_portfolio();
    system.edges[1].reset_relations[0]=singleton_relation("oracle-reset-b",{3,0,1});
    system.edges.push_back({{"guard-exit"},{"source"},{"target"},{Singleton{{4}}},
        {singleton_relation("reset-guard-exit",{3,0,0})}});
    const auto oracle=enumerate_one_step_singleton_oracle(system,request);
    REQUIRE(oracle.size()==3);
    CHECK(oracle[0].path.edges[0].value=="tie-a");
    CHECK(oracle[0].joint_tuple==Vector{2,1,3,0,0});
    CHECK(oracle[0].objective==0);
    CHECK(oracle[1].path.edges[0].value=="tie-b");
    CHECK(oracle[1].joint_tuple==Vector{2,1,3,0,1});
    CHECK(oracle[1].objective==0);
    CHECK(oracle[2].path.edges[0].value=="worse");
    CHECK(oracle[2].joint_tuple==Vector{2,1,3,1,0});
    CHECK(oracle[2].objective==1);

    // Flow produces pre-reset state 3: one edge allows 3 while this parallel
    // outgoing edge requires 4, so the latter branch must be empty.
    CHECK(oracle[0].joint_tuple[2]==3);
    const auto built=build_hybrid_portfolio_programs(system,request,{"oracle-hybrid"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==system.edges.size());
    std::vector<double> costs;
    for(std::size_t i=0;i<oracle.size();++i) {
        CHECK(programs[i].path==oracle[i].path);
        const auto representation=programs[i].joint_relation.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
        const auto& h=std::get<sets::HRepresentation>(representation);
        CHECK(satisfies(h,oracle[i].joint_tuple));
        CHECK(equality_rows_have_full_column_rank(h.equalities));
        const auto& linear=std::get<LinearProgram>(programs[i].program);
        costs.push_back(linear.offset());
        for(std::size_t j=0;j<linear.objective().size();++j)
            costs.back()+=linear.objective()[j]*oracle[i].joint_tuple[j];
        CHECK(costs.back()==oracle[i].objective);
    }
    CHECK(programs.back().path.edges==std::vector<model::HybridEdgeId>{{"guard-exit"}});
    const auto rejected_representation=programs.back().joint_relation.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(rejected_representation));
    CHECK(has_conflicting_equalities(std::get<sets::HRepresentation>(rejected_representation)));

    // With the same edge guard (pre-state 3), changing the initial state to 3
    // makes the affine flow produce 4 and the branch exits that guard.
    auto exiting_request=request;
    exiting_request.initial.state={3};
    auto exiting_system=system;
    exiting_system.edges.resize(1);
    exiting_system.edges[0].reset_relations[0]=singleton_relation("reset-exiting-flow",{4,0,0});
    const model::HybridPath entering_edge{{{"source"},{"target"}},{{"tie-a"}}};
    CHECK(enumerate_one_step_singleton_oracle(exiting_system,exiting_request).empty());
    const auto exiting=build_hybrid_path_program(exiting_system,exiting_request,entering_edge,
        {"oracle-guard-exit"},{32,128,4096});
    REQUIRE(std::holds_alternative<HybridPathProgram>(exiting));
    const auto exiting_relation=std::get<HybridPathProgram>(exiting).joint_relation.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(exiting_relation));
    CHECK(has_conflicting_equalities(std::get<sets::HRepresentation>(exiting_relation)));

    const auto minimum=std::min_element(oracle.begin(),oracle.end(),[](const auto& left,const auto& right) {
        return left.objective<right.objective;
    })->objective;
    std::vector<std::string> oracle_optima;
    for(const auto& branch:oracle) if(branch.objective==minimum)
        oracle_optima.push_back(branch.path.edges[0].value);
    CHECK(oracle_optima==std::vector<std::string>{"tie-a","tie-b"});
}

TEST_CASE("independent two-stage oracle checks every edge history and tied mode sequence") {
    model::HybridMode first{{"first"},1,1,{"x"},{"u"}};
    first.flow=std::vector<LinearStage>{
        {Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{1}},
        {Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{1}}};
    first.control_sets={Singleton{{0}},Singleton{{0}}};
    first.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridMode middle{{"middle"},1,1,{"y"},{"v"}};
    middle.flow=std::vector<LinearStage>{
        {Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}},
        {Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}}};
    middle.control_sets={Singleton{{0}},Singleton{{0}}};
    middle.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    model::HybridMode terminal{{"terminal"},1,0,{"z"},{}};
    terminal.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    terminal.control_sets={UniversalSet{0},UniversalSet{0}};
    terminal.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
    const auto reset_to_middle=[](std::string id) {
        return singleton_relation(std::move(id),{1,1});
    };
    const auto reset_to_terminal=[](std::string id,double post) {
        return singleton_relation(std::move(id),{1,post});
    };
    model::HybridSystem system{2,{first,middle,terminal},
        {{{"first-a"},{"first"},{"middle"},{Singleton{{1}},Singleton{{1}}},
            {reset_to_middle("first-a-reset-0"),reset_to_middle("first-a-reset-1")}},
         {{"first-b"},{"first"},{"middle"},{Singleton{{1}},Singleton{{1}}},
            {reset_to_middle("first-b-reset-0"),reset_to_middle("first-b-reset-1")}},
         {{"second-a"},{"middle"},{"terminal"},{Singleton{{1}},Singleton{{1}}},
            {reset_to_terminal("second-a-reset-0",0),reset_to_terminal("second-a-reset-1",0)}},
         {{"second-b"},{"middle"},{"terminal"},{Singleton{{1}},Singleton{{1}}},
            {reset_to_terminal("second-b-reset-0",2),reset_to_terminal("second-b-reset-1",2)}}}};
    model::HybridRequest request{{{"first"},{0}},{{"terminal"}},
        {{{"terminal"},LinearTerminal{{1},0},"terminal-cost","J"}}};

    // This oracle traverses the raw edge graph at each stage and directly
    // evaluates the singleton controls, affine flows, guards, resets, and
    // terminal costs. It does not call the production path enumerator,
    // composer, or verifier.
    struct OracleBranch { model::HybridPath path; Vector tuple; double cost; };
    std::vector<OracleBranch> oracle;
    const auto* first_flow=std::get_if<std::vector<LinearStage>>(&first.flow);
    REQUIRE(first_flow!=nullptr);
    for(const auto& first_edge:system.edges) {
        if(first_edge.source!=request.initial.mode) continue;
        const auto& initial_control=std::get<Singleton>(first.control_sets[0]).point;
        const auto& first_stage=(*first_flow)[0];
        const double first_pre=first_stage.A.values[0]*request.initial.state[0]+
            first_stage.B.values[0]*initial_control[0]+first_stage.offset[0];
        if(std::get<Singleton>(first_edge.guards[0]).point[0]!=first_pre) continue;
        const auto first_reset_data=sets::from_handle(first_edge.reset_relations[0]);
        REQUIRE(std::holds_alternative<sets::SetData>(first_reset_data));
        const auto first_reset=std::get<sets::SetData>(first_reset_data).representation();
        REQUIRE(std::holds_alternative<sets::SingletonRepresentation>(first_reset));
        const auto& first_reset_point=std::get<sets::SingletonRepresentation>(first_reset).point;
        if(first_reset_point[0]!=first_pre) continue;
        const double middle_state=first_reset_point[1];
        for(const auto& second_edge:system.edges) {
            if(second_edge.source!=first_edge.target||
               std::find(request.allowed_terminal_modes.begin(),request.allowed_terminal_modes.end(),
                   second_edge.target)==request.allowed_terminal_modes.end()) continue;
            const auto& middle_control=std::get<Singleton>(middle.control_sets[1]).point;
            const auto& second_flow=std::get<std::vector<LinearStage>>(middle.flow)[1];
            const double second_pre=second_flow.A.values[0]*middle_state+
                second_flow.B.values[0]*middle_control[0]+second_flow.offset[0];
            if(std::get<Singleton>(second_edge.guards[1]).point[0]!=second_pre) continue;
            const auto second_reset_data=sets::from_handle(second_edge.reset_relations[1]);
            REQUIRE(std::holds_alternative<sets::SetData>(second_reset_data));
            const auto second_reset=std::get<sets::SetData>(second_reset_data).representation();
            REQUIRE(std::holds_alternative<sets::SingletonRepresentation>(second_reset));
            const auto& second_reset_point=std::get<sets::SingletonRepresentation>(second_reset).point;
            if(second_reset_point[0]!=second_pre) continue;
            const double terminal_state=second_reset_point[1];
            oracle.push_back({{{request.initial.mode,first_edge.target,second_edge.target},
                {first_edge.id,second_edge.id}},
                {request.initial.state[0],initial_control[0],first_pre,middle_state,
                 middle_control[0],second_pre,terminal_state},terminal_state});
        }
    }
    REQUIRE(oracle.size()==4);
    CHECK((oracle[0].path.edges==std::vector<model::HybridEdgeId>{{"first-a"},{"second-a"}}));
    CHECK(oracle[0].tuple==Vector{0,0,1,1,0,1,0});
    CHECK(oracle[0].cost==0);
    CHECK((oracle[1].path.edges==std::vector<model::HybridEdgeId>{{"first-a"},{"second-b"}}));
    CHECK(oracle[1].tuple==Vector{0,0,1,1,0,1,2});
    CHECK(oracle[1].cost==2);
    CHECK((oracle[2].path.edges==std::vector<model::HybridEdgeId>{{"first-b"},{"second-a"}}));
    CHECK(oracle[2].tuple==Vector{0,0,1,1,0,1,0});
    CHECK(oracle[2].cost==0);
    CHECK((oracle[3].path.edges==std::vector<model::HybridEdgeId>{{"first-b"},{"second-b"}}));
    CHECK(oracle[3].tuple==Vector{0,0,1,1,0,1,2});
    CHECK(oracle[3].cost==2);

    const auto built=build_hybrid_portfolio_programs(system,request,{"two-stage-oracle"},
        {2,16},{32,256,8192});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==oracle.size());
    std::vector<bool> matched_oracle(oracle.size(),false);
    for(std::size_t i=0;i<oracle.size();++i) {
        const auto expected=std::find_if(oracle.begin(),oracle.end(),[&](const auto& branch) {
            return branch.path==programs[i].path;
        });
        REQUIRE(expected!=oracle.end());
        const auto oracle_index=static_cast<std::size_t>(std::distance(oracle.begin(),expected));
        REQUIRE_FALSE(matched_oracle[oracle_index]);
        matched_oracle[oracle_index]=true;
        const auto representation=programs[i].joint_relation.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
        const auto& h=std::get<sets::HRepresentation>(representation);
        CHECK(satisfies(h,expected->tuple));
        CHECK(equality_rows_have_full_column_rank(h.equalities));
        const auto& program=std::get<LinearProgram>(programs[i].program);
        double cost=program.offset();
        for(std::size_t j=0;j<program.objective().size();++j)
            cost+=program.objective()[j]*expected->tuple[j];
        CHECK(cost==expected->cost);
    }
    CHECK(std::all_of(matched_oracle.begin(),matched_oracle.end(),[](bool matched) { return matched; }));
    const auto minimum=std::min_element(oracle.begin(),oracle.end(),[](const auto& left,const auto& right) {
        return left.cost<right.cost;
    })->cost;
    std::vector<model::HybridPath> optimal_paths;
    for(const auto& branch:oracle) if(branch.cost==minimum) optimal_paths.push_back(branch.path);
    REQUIRE(optimal_paths.size()==2);
    CHECK(optimal_paths[0].modes==optimal_paths[1].modes);
    CHECK(optimal_paths[0].edges!=optimal_paths[1].edges);
    CHECK(optimal_paths[0].edges[0].value=="first-a");
    CHECK(optimal_paths[1].edges[0].value=="first-b");
}

TEST_CASE("independent interval oracle matches the full continuous hybrid branch") {
    model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={interval("oracle-control",0,1)};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    auto reset_equalities=numeric::snapshot(Matrix{1,2,{-1,1}});
    auto reset_rhs=numeric::snapshot_vector(Vector{0});
    auto reset_inequalities=numeric::snapshot(Matrix{0,2,{}});
    auto reset_bounds=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(reset_rhs));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(reset_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(reset_bounds));
    auto reset_data=sets::make_h({{"oracle-identity-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(reset_equalities),std::get<numeric::VectorView>(reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(reset_data));
    model::HybridSystem system{1,{source,target},
        {{{"switch-wide"},{"source"},{"target"},{interval("oracle-guard-wide",0,0.5)},
          {std::get<sets::SetData>(reset_data).as_handle()}},
         {{"switch-narrow"},{"source"},{"target"},{interval("oracle-guard-narrow",0,0.25)},
          {std::get<sets::SetData>(reset_data).as_handle()}}}};
    model::HybridRequest request{{{"source"},{0}},{{"target"}},
        {{{"target"},LinearTerminal{{0},0},"cost","u"}}};

    // Both paths minimize the same constant objective. Their exact optimal
    // joint relations are (0,t,t,t), with 0<=t<=1/2 and 0<=t<=1/4.
    const std::vector<model::HybridPath> oracle_paths{
        {{{"source"},{"target"}},{{"switch-wide"}}},
        {{{"source"},{"target"}},{{"switch-narrow"}}}};
    const auto built=build_hybrid_portfolio_programs(system,request,{"continuous-oracle"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==oracle_paths.size());

    auto check_branch=[&](const HybridPathProgram& branch,const model::HybridPath& expected_path,
        double expected_upper) {
        CHECK(branch.path==expected_path);
        const auto representation=branch.joint_relation.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
        const auto& h=std::get<sets::HRepresentation>(representation);
        REQUIRE(h.equalities.cols()==4);
        CHECK(equality_rank(h.equalities)==3);
        CHECK(satisfies(h,{0,0,0,0}));
        CHECK(satisfies(h,{0,expected_upper,expected_upper,expected_upper}));

        double lower=-std::numeric_limits<double>::infinity();
        double upper=std::numeric_limits<double>::infinity();
        for(std::size_t row=0;row<h.inequalities.rows();++row) {
            const double intercept=0;
            const double slope=h.inequalities(row,1)+h.inequalities(row,2)+h.inequalities(row,3);
            if(slope>0) upper=std::min(upper,(h.upper_bounds[row]-intercept)/slope);
            else if(slope<0) lower=std::max(lower,(h.upper_bounds[row]-intercept)/slope);
            else CHECK(intercept<=h.upper_bounds[row]);
        }
        CHECK(lower==0);
        CHECK(upper==expected_upper);
        const auto& program=std::get<LinearProgram>(branch.program);
        CHECK(program.objective().size()==4);
        CHECK(program.offset()==0);
        CHECK(program.objective()[0]==0);
        CHECK(program.objective()[1]==0);
        CHECK(program.objective()[2]==0);
        CHECK(program.objective()[3]==0);
    };
    check_branch(programs[0],oracle_paths[0],0.5);
    check_branch(programs[1],oracle_paths[1],0.25);
}

TEST_CASE("one-step scalar interval verifier certifies distinct tied continuous branches") {
    model::HybridMode source{{"source"},1,1,{"x"},{"u"}};
    source.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
    source.control_sets={interval("verifier-control",0,1)};
    source.invariants={UniversalSet{1},UniversalSet{1}};
    model::HybridMode target{{"target"},1,0,{"y"},{}};
    target.flow=LinearStage{Matrix{1,1,{1}},Matrix{1,0,{}},Matrix{1,0,{}},Vector{0}};
    target.control_sets={UniversalSet{0}};
    target.invariants={UniversalSet{1},UniversalSet{1}};
    auto reset_equalities=numeric::snapshot(Matrix{1,2,{-1,1}});
    auto reset_rhs=numeric::snapshot_vector(Vector{0});
    auto reset_inequalities=numeric::snapshot(Matrix{0,2,{}});
    auto reset_bounds=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(reset_rhs));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(reset_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(reset_bounds));
    auto reset=sets::make_h({{"verifier-identity-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(reset_equalities),std::get<numeric::VectorView>(reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(reset));
    auto system=model::HybridSystem{1,{source,target},
        {{{"wide"},{"source"},{"target"},{interval("verifier-wide-guard",0,0.5)},
            {std::get<sets::SetData>(reset).as_handle()}},
         {{"narrow"},{"source"},{"target"},{interval("verifier-narrow-guard",0,0.25)},
            {std::get<sets::SetData>(reset).as_handle()}}}};
    auto request=model::HybridRequest{{{"source"},{0}},{{"target"}},
        {{{"target"},LinearTerminal{{0},0},"cost","u"}}};
    const auto built=build_hybrid_portfolio_programs(system,request,{"interval-family-verifier"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==2);
    std::vector<HybridPathOptimalFaceCandidate> candidates{
        exact_candidate(programs[0],{0,0,0,0}),exact_candidate(programs[1],{0,0,0,0})};
    OneStepScalarIntervalHybridFamilyVerifier verifier;
    const auto capabilities=verifier.capabilities();
    CHECK(capabilities.checks_original_hybrid_feasibility);
    CHECK(capabilities.checks_global_objective_optimality);
    CHECK(capabilities.checks_continuous_branch_coverage);
    CHECK(capabilities.assurance==Assurance::numerical);
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.verifier_id=="csl.hybrid.one-step-scalar-interval");
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==2);
    for(const auto& branch:report.branches) {
        CHECK(branch.feasibility==HybridVerificationStatus::established);
        CHECK(branch.objective_optimality==HybridVerificationStatus::established);
        CHECK(branch.continuous_coverage==HybridVerificationStatus::established);
    }

    auto affine_reset_equalities=numeric::snapshot(Matrix{1,2,{-2,1}});
    auto affine_reset_rhs=numeric::snapshot_vector(Vector{1});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(affine_reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(affine_reset_rhs));
    auto affine_reset=sets::make_h({{"verifier-affine-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),
         std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(affine_reset_equalities),
         std::get<numeric::VectorView>(affine_reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(affine_reset));
    auto affine_reset_system=system;
    affine_reset_system.modes[1].invariants[1]=interval("verifier-affine-reset-target",1,2);
    for(auto& edge:affine_reset_system.edges)
        edge.reset_relations[0]=std::get<sets::SetData>(affine_reset).as_handle();
    const auto affine_reset_built=build_hybrid_portfolio_programs(affine_reset_system,request,
        {"affine-reset-interval-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(affine_reset_built));
    const auto& affine_reset_programs=std::get<std::vector<HybridPathProgram>>(affine_reset_built);
    std::vector<HybridPathOptimalFaceCandidate> affine_reset_candidates{
        exact_candidate(affine_reset_programs[0],{0,0,0,1}),
        exact_candidate(affine_reset_programs[1],{0,0,0,1})};
    const auto affine_reset_result=verify_hybrid_portfolio_family(verifier,affine_reset_system,
        request,affine_reset_programs,affine_reset_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(affine_reset_result));
    CHECK(std::get<HybridFamilyVerificationReport>(affine_reset_result).complete_family_coverage==
        HybridVerificationStatus::established);

    auto negative_reset_equalities=numeric::snapshot(Matrix{1,2,{2,1}});
    auto negative_reset_rhs=numeric::snapshot_vector(Vector{1});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(negative_reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(negative_reset_rhs));
    auto negative_reset=sets::make_h({{"verifier-negative-affine-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),
         std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(negative_reset_equalities),
         std::get<numeric::VectorView>(negative_reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(negative_reset));
    auto negative_reset_system=system;
    negative_reset_system.modes[1].invariants[1]=interval("verifier-negative-reset-target",0,1);
    for(auto& edge:negative_reset_system.edges)
        edge.reset_relations[0]=std::get<sets::SetData>(negative_reset).as_handle();
    const auto negative_reset_built=build_hybrid_portfolio_programs(negative_reset_system,request,
        {"negative-affine-reset-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(negative_reset_built));
    const auto& negative_reset_programs=std::get<std::vector<HybridPathProgram>>(negative_reset_built);
    std::vector<HybridPathOptimalFaceCandidate> negative_reset_candidates{
        exact_candidate(negative_reset_programs[0],{0,0,0,1}),
        exact_candidate(negative_reset_programs[1],{0,0,0,1})};
    const auto negative_reset_result=verify_hybrid_portfolio_family(verifier,negative_reset_system,
        request,negative_reset_programs,negative_reset_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(negative_reset_result));
    CHECK(std::get<HybridFamilyVerificationReport>(negative_reset_result).complete_family_coverage==
        HybridVerificationStatus::established);

    auto constant_reset_equalities=numeric::snapshot(Matrix{1,2,{0,1}});
    auto constant_reset_rhs=numeric::snapshot_vector(Vector{1});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(constant_reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(constant_reset_rhs));
    auto constant_reset=sets::make_h({{"verifier-constant-affine-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),
         std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(constant_reset_equalities),
         std::get<numeric::VectorView>(constant_reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(constant_reset));
    auto constant_reset_system=system;
    constant_reset_system.modes[1].invariants[1]=interval("verifier-constant-reset-target",1,1);
    for(auto& edge:constant_reset_system.edges)
        edge.reset_relations[0]=std::get<sets::SetData>(constant_reset).as_handle();
    const auto constant_reset_built=build_hybrid_portfolio_programs(constant_reset_system,request,
        {"constant-affine-reset-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(constant_reset_built));
    const auto& constant_reset_programs=std::get<std::vector<HybridPathProgram>>(constant_reset_built);
    std::vector<HybridPathOptimalFaceCandidate> constant_reset_candidates{
        exact_candidate(constant_reset_programs[0],{0,0,0,1}),
        exact_candidate(constant_reset_programs[1],{0,0,0,1})};
    const auto constant_reset_result=verify_hybrid_portfolio_family(verifier,constant_reset_system,
        request,constant_reset_programs,constant_reset_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(constant_reset_result));
    CHECK(std::get<HybridFamilyVerificationReport>(constant_reset_result).complete_family_coverage==
        HybridVerificationStatus::established);

    auto inexact_reset_equalities=numeric::snapshot(Matrix{1,2,{-1,3}});
    auto inexact_reset_rhs=numeric::snapshot_vector(Vector{0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inexact_reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(inexact_reset_rhs));
    auto inexact_reset=sets::make_h({{"verifier-inexact-affine-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),
         std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(inexact_reset_equalities),
         std::get<numeric::VectorView>(inexact_reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(inexact_reset));
    auto inexact_reset_system=system;
    for(auto& edge:inexact_reset_system.edges)
        edge.reset_relations[0]=std::get<sets::SetData>(inexact_reset).as_handle();
    const auto inexact_reset_built=build_hybrid_portfolio_programs(inexact_reset_system,request,
        {"inexact-affine-reset-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(inexact_reset_built));
    const auto& inexact_reset_programs=std::get<std::vector<HybridPathProgram>>(inexact_reset_built);
    std::vector<HybridPathOptimalFaceCandidate> inexact_reset_candidates{
        exact_candidate(inexact_reset_programs[0],{0,0,0,0}),
        exact_candidate(inexact_reset_programs[1],{0,0,0,0})};
    const auto inexact_reset_result=verify_hybrid_portfolio_family(verifier,inexact_reset_system,
        request,inexact_reset_programs,inexact_reset_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(inexact_reset_result));
    CHECK(std::get<HybridFamilyVerificationReport>(inexact_reset_result).branches[0].continuous_coverage==
        HybridVerificationStatus::unsupported);

    const double maximum=std::numeric_limits<double>::max();
    auto overflow_reset_equalities=numeric::snapshot(Matrix{1,2,{-maximum,1}});
    auto overflow_reset_rhs=numeric::snapshot_vector(Vector{0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(overflow_reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(overflow_reset_rhs));
    auto overflow_reset=sets::make_h({{"verifier-overflow-affine-reset"},2,{}},
        {std::get<numeric::MatrixView>(reset_inequalities),
         std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(overflow_reset_equalities),
         std::get<numeric::VectorView>(overflow_reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(overflow_reset));
    auto overflow_reset_system=system;
    overflow_reset_system.edges.resize(1);
    overflow_reset_system.edges[0].guards[0]=interval("verifier-overflow-reset-guard",0,1);
    overflow_reset_system.edges[0].reset_relations[0]=std::get<sets::SetData>(overflow_reset).as_handle();
    const auto overflow_reset_built=build_hybrid_portfolio_programs(overflow_reset_system,request,
        {"overflow-affine-reset-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(overflow_reset_built));
    const auto& overflow_reset_programs=std::get<std::vector<HybridPathProgram>>(overflow_reset_built);
    std::vector<HybridPathOptimalFaceCandidate> overflow_reset_candidates{
        exact_candidate(overflow_reset_programs[0],{0,1.0000000001,1.0000000001,maximum})};
    const auto overflow_reset_result=verify_hybrid_portfolio_family(verifier,overflow_reset_system,
        request,overflow_reset_programs,overflow_reset_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(overflow_reset_result));
    CHECK(std::get<HybridFamilyVerificationReport>(overflow_reset_result).branches[0].continuous_coverage==
        HybridVerificationStatus::refuted);

    auto ratio_system=system;
    ratio_system.edges[1].guards[0]=interval("verifier-inexact-row-ratio-guard",0,0.3);
    const auto ratio_built=build_hybrid_portfolio_programs(ratio_system,request,
        {"inexact-row-ratio-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(ratio_built));
    const auto& ratio_programs=std::get<std::vector<HybridPathProgram>>(ratio_built);
    std::vector<HybridPathOptimalFaceCandidate> ratio_candidates{
        exact_candidate(ratio_programs[0],{0,0,0,0}),exact_candidate(ratio_programs[1],{0,0,0,0})};
    auto ratio_inequalities=numeric::snapshot(Matrix{3,4,{0,-1,0,0,0,1,0,0,0,0.1,0,0}});
    auto ratio_bounds=numeric::snapshot_vector(Vector{0,0.3,0.03});
    auto ratio_equalities=numeric::snapshot(Matrix{3,4,{1,0,0,0,0,-1,1,0,0,0,-1,1}});
    auto ratio_rhs=numeric::snapshot_vector(Vector{0,0,0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(ratio_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(ratio_bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(ratio_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(ratio_rhs));
    auto inexact_row_relation=sets::make_h({{"verifier-inexact-row-ratio"},4,{}},
        {std::get<numeric::MatrixView>(ratio_inequalities),std::get<numeric::VectorView>(ratio_bounds),
         std::get<numeric::MatrixView>(ratio_equalities),std::get<numeric::VectorView>(ratio_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(inexact_row_relation));
    ratio_candidates[1].relation=std::get<sets::SetData>(inexact_row_relation);
    const auto inexact_row_result=verify_hybrid_portfolio_family(verifier,ratio_system,request,
        ratio_programs,ratio_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(inexact_row_result));
    CHECK(std::get<HybridFamilyVerificationReport>(inexact_row_result).branches[1].continuous_coverage==
        HybridVerificationStatus::unsupported);

    auto rank_overcount_inequalities=numeric::snapshot(Matrix{2,4,{0,-1,0,0,0,1,0,0}});
    auto rank_overcount_bounds=numeric::snapshot_vector(Vector{0,1});
    auto rank_overcount_equalities=numeric::snapshot(Matrix{3,4,{
        -2,18372082061.0,-42348971870.0,23976889809.0,
        1,-14888587493.0,81823523113.0,-66934935620.0,
        -9,76971822812.0,-129921336237.0,52949513425.0}});
    auto rank_overcount_rhs=numeric::snapshot_vector(Vector{0,0,0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rank_overcount_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rank_overcount_bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rank_overcount_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rank_overcount_rhs));
    auto rank_overcount_relation=sets::make_h({{"verifier-dependent-row-rank"},4,{}},
        {std::get<numeric::MatrixView>(rank_overcount_inequalities),
         std::get<numeric::VectorView>(rank_overcount_bounds),
         std::get<numeric::MatrixView>(rank_overcount_equalities),
         std::get<numeric::VectorView>(rank_overcount_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(rank_overcount_relation));
    auto rank_overcount_system=system;
    rank_overcount_system.edges[1].guards[0]=interval("verifier-dependent-row-rank-guard",0,1);
    auto rank_overcount_programs=programs;
    auto rank_overcount_candidates=std::vector<HybridPathOptimalFaceCandidate>{
        exact_candidate(programs[0],{0,0,0,0}),exact_candidate(programs[1],{0,0,0,0})};
    rank_overcount_programs[1].joint_relation=std::get<sets::SetData>(rank_overcount_relation);
    rank_overcount_candidates[1].relation=std::get<sets::SetData>(rank_overcount_relation);
    const auto rank_overcount_result=verify_hybrid_portfolio_family(verifier,rank_overcount_system,request,
        rank_overcount_programs,rank_overcount_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(rank_overcount_result));
    CHECK(std::get<HybridFamilyVerificationReport>(rank_overcount_result).branches[1].continuous_coverage==
        HybridVerificationStatus::refuted);

    auto inexact_rank_equalities=numeric::snapshot(Matrix{3,4,{1,0,0,0,0,3,0,-3,0,1,2,-3}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inexact_rank_equalities));
    auto inexact_rank_relation=sets::make_h({{"verifier-inexact-elimination-rank"},4,{}},
        {std::get<numeric::MatrixView>(rank_overcount_inequalities),
         std::get<numeric::VectorView>(rank_overcount_bounds),
         std::get<numeric::MatrixView>(inexact_rank_equalities),
         std::get<numeric::VectorView>(rank_overcount_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(inexact_rank_relation));
    auto inexact_rank_programs=programs;
    auto inexact_rank_candidates=std::vector<HybridPathOptimalFaceCandidate>{
        exact_candidate(programs[0],{0,0,0,0}),exact_candidate(programs[1],{0,0,0,0})};
    inexact_rank_programs[1].joint_relation=std::get<sets::SetData>(inexact_rank_relation);
    inexact_rank_candidates[1].relation=std::get<sets::SetData>(inexact_rank_relation);
    const auto inexact_rank_result=verify_hybrid_portfolio_family(verifier,rank_overcount_system,request,
        inexact_rank_programs,inexact_rank_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(inexact_rank_result));
    CHECK(std::get<HybridFamilyVerificationReport>(inexact_rank_result).branches[1].continuous_coverage==
        HybridVerificationStatus::unsupported);

    auto narrow_tied_system=system;
    narrow_tied_system.edges[1].guards[0]=interval("verifier-narrow-tied-guard",0,5e-11);
    const auto narrow_tied_built=build_hybrid_portfolio_programs(narrow_tied_system,request,
        {"narrow-tied-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(narrow_tied_built));
    const auto& narrow_tied_programs=std::get<std::vector<HybridPathProgram>>(narrow_tied_built);
    std::vector<HybridPathOptimalFaceCandidate> narrow_tied_candidates{
        exact_candidate(narrow_tied_programs[0],{0,0,0,0}),
        exact_candidate(narrow_tied_programs[1],{0,0,0,0})};
    narrow_tied_candidates[1].relation=singleton_data({0,0,0,0});
    const auto narrow_tied_result=verify_hybrid_portfolio_family(verifier,narrow_tied_system,request,
        narrow_tied_programs,narrow_tied_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(narrow_tied_result));
    CHECK(std::get<HybridFamilyVerificationReport>(narrow_tied_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto underflow_system=system;
    underflow_system.modes[0].flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{1e-200}},
        Matrix{1,0,{}},Vector{0}};
    auto underflow_request=request;
    underflow_request.terminal_objectives[0].objective=LinearTerminal{{1e-200},0};
    const auto underflow_built=build_hybrid_portfolio_programs(underflow_system,underflow_request,
        {"underflow-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(underflow_built));
    const auto& underflow_programs=std::get<std::vector<HybridPathProgram>>(underflow_built);
    std::vector<HybridPathOptimalFaceCandidate> underflow_candidates{
        exact_candidate(underflow_programs[0],{0,0,0,0}),
        exact_candidate(underflow_programs[1],{0,0,0,0})};
    const auto underflow_result=verify_hybrid_portfolio_family(verifier,underflow_system,underflow_request,
        underflow_programs,underflow_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(underflow_result));
    const auto& underflow_report=std::get<HybridFamilyVerificationReport>(underflow_result);
    CHECK(underflow_report.global_objective_optimality==HybridVerificationStatus::unsupported);
    CHECK(underflow_report.complete_family_coverage==HybridVerificationStatus::unsupported);

    auto subnormal_residual_system=system;
    subnormal_residual_system.modes[0].flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{0x1p-511}},
        Matrix{1,0,{}},Vector{0}};
    auto subnormal_residual_request=request;
    subnormal_residual_request.terminal_objectives[0].objective=LinearTerminal{{0x1p-511},0};
    const auto subnormal_residual_built=build_hybrid_portfolio_programs(subnormal_residual_system,
        subnormal_residual_request,{"subnormal-residual-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(subnormal_residual_built));
    const auto& subnormal_residual_programs=
        std::get<std::vector<HybridPathProgram>>(subnormal_residual_built);
    std::vector<HybridPathOptimalFaceCandidate> subnormal_residual_candidates{
        exact_candidate(subnormal_residual_programs[0],{0,0,0,0}),
        exact_candidate(subnormal_residual_programs[1],{0,0,0,0})};
    const auto subnormal_residual_result=verify_hybrid_portfolio_family(verifier,
        subnormal_residual_system,subnormal_residual_request,subnormal_residual_programs,
        subnormal_residual_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(subnormal_residual_result));
    CHECK(std::get<HybridFamilyVerificationReport>(subnormal_residual_result).global_objective_optimality==
        HybridVerificationStatus::unsupported);

    auto inexact_flow_system=system;
    inexact_flow_system.edges.resize(1);
    inexact_flow_system.modes[0].control_sets[0]=Singleton{{0.3}};
    inexact_flow_system.modes[0].flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{0.1}},
        Matrix{1,0,{}},Vector{0}};
    auto inexact_flow_request=request;
    const auto inexact_flow_built=build_hybrid_portfolio_programs(inexact_flow_system,inexact_flow_request,
        {"inexact-flow-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(inexact_flow_built));
    const auto& inexact_flow_programs=std::get<std::vector<HybridPathProgram>>(inexact_flow_built);
    std::vector<HybridPathOptimalFaceCandidate> inexact_flow_candidates{
        exact_candidate(inexact_flow_programs[0],{0,0.3,0.03,0.03})};
    const auto inexact_flow_result=verify_hybrid_portfolio_family(verifier,inexact_flow_system,
        inexact_flow_request,inexact_flow_programs,inexact_flow_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(inexact_flow_result));
    CHECK(std::get<HybridFamilyVerificationReport>(inexact_flow_result).global_objective_optimality==
        HybridVerificationStatus::unsupported);

    auto sub_ulp_system=system;
    sub_ulp_system.edges[0].guards[0]=interval("verifier-sub-ulp-zero",0,0.5);
    sub_ulp_system.edges[1].guards[0]=interval("verifier-sub-ulp-positive",
        2.7755575615628914e-17,0.25);
    auto sub_ulp_request=request;
    sub_ulp_request.terminal_objectives[0].objective=LinearTerminal{{1},1};
    const auto sub_ulp_built=build_hybrid_portfolio_programs(sub_ulp_system,sub_ulp_request,
        {"sub-ulp-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(sub_ulp_built));
    const auto& sub_ulp_programs=std::get<std::vector<HybridPathProgram>>(sub_ulp_built);
    std::vector<HybridPathOptimalFaceCandidate> sub_ulp_candidates{
        exact_candidate(sub_ulp_programs[0],{0,0,0,0}),
        exact_candidate(sub_ulp_programs[1],{0,2.7755575615628914e-17,2.7755575615628914e-17,
            2.7755575615628914e-17})};
    const auto sub_ulp_result=verify_hybrid_portfolio_family(verifier,sub_ulp_system,sub_ulp_request,
        sub_ulp_programs,sub_ulp_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(sub_ulp_result));
    CHECK(std::get<HybridFamilyVerificationReport>(sub_ulp_result).global_objective_optimality==
        HybridVerificationStatus::unsupported);

    candidates.pop_back();
    const auto missing_tie=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(missing_tie));
    CHECK(std::get<HybridFamilyVerificationReport>(missing_tie).complete_family_coverage==
        HybridVerificationStatus::refuted);

    candidates={exact_candidate(programs[0],{0,0,0,0}),exact_candidate(programs[1],{0,0,0,0})};
    candidates[1].relation=singleton_data({0,0,0,0});
    const auto altered_tie=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(altered_tie));
    CHECK(std::get<HybridFamilyVerificationReport>(altered_tie).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto increasing_request=request;
    increasing_request.terminal_objectives[0].objective=LinearTerminal{{1},0};
    const auto increasing_built=build_hybrid_portfolio_programs(system,increasing_request,
        {"interval-endpoint-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(increasing_built));
    const auto& increasing_programs=std::get<std::vector<HybridPathProgram>>(increasing_built);
    std::vector<HybridPathOptimalFaceCandidate> endpoint_candidates{
        exact_candidate(increasing_programs[0],{0,0,0,0}),
        exact_candidate(increasing_programs[1],{0,0,0,0})};
    endpoint_candidates[0].relation=singleton_data({0,0,0,0});
    endpoint_candidates[1].relation=singleton_data({0,0,0,0});
    const auto endpoint_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,endpoint_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(endpoint_result));
    const auto& endpoint_report=std::get<HybridFamilyVerificationReport>(endpoint_result);
    CHECK(endpoint_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(endpoint_report.complete_family_coverage==HybridVerificationStatus::established);

    auto decreasing_request=request;
    decreasing_request.terminal_objectives[0].objective=LinearTerminal{{-1},0};
    const auto decreasing_built=build_hybrid_portfolio_programs(system,decreasing_request,
        {"decreasing-endpoint-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(decreasing_built));
    const auto& decreasing_programs=std::get<std::vector<HybridPathProgram>>(decreasing_built);
    std::vector<HybridPathOptimalFaceCandidate> decreasing_candidates{
        exact_candidate(decreasing_programs[0],{0,0.5,0.5,0.5}),
        exact_candidate(decreasing_programs[1],{0,0.25,0.25,0.25})};
    decreasing_candidates[0].relation=singleton_data({0,0.5,0.5,0.5});
    decreasing_candidates[1].relation=singleton_data({0,0.25,0.25,0.25});
    const auto decreasing_result=verify_hybrid_portfolio_family(verifier,system,decreasing_request,
        decreasing_programs,decreasing_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(decreasing_result));
    const auto& decreasing_report=std::get<HybridFamilyVerificationReport>(decreasing_result);
    CHECK(decreasing_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(decreasing_report.complete_family_coverage==HybridVerificationStatus::refuted);
    CHECK(decreasing_report.branches[0].continuous_coverage==HybridVerificationStatus::established);
    CHECK(decreasing_report.branches[1].objective_optimality==HybridVerificationStatus::refuted);

    auto enlarged_inequalities=numeric::snapshot(Matrix{2,4,{0,-1,0,0,0,1,0,0}});
    auto enlarged_bounds=numeric::snapshot_vector(Vector{0,5e-11});
    auto line_equalities=numeric::snapshot(Matrix{3,4,{1,0,0,0,0,-1,1,0,0,0,-1,1}});
    auto line_rhs=numeric::snapshot_vector(Vector{0,0,0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(enlarged_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(enlarged_bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(line_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(line_rhs));
    auto enlarged_face=sets::make_h({{"verifier-enlarged-optimal-face"},4,{}},
        {std::get<numeric::MatrixView>(enlarged_inequalities),
         std::get<numeric::VectorView>(enlarged_bounds),std::get<numeric::MatrixView>(line_equalities),
         std::get<numeric::VectorView>(line_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(enlarged_face));
    auto enlarged_candidates=endpoint_candidates;
    enlarged_candidates[0].relation=std::get<sets::SetData>(enlarged_face);
    const auto enlarged_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,enlarged_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(enlarged_result));
    CHECK(std::get<HybridFamilyVerificationReport>(enlarged_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto shifted_singleton_candidates=endpoint_candidates;
    shifted_singleton_candidates[0].relation=singleton_data({0,5e-11,5e-11,5e-11});
    const auto shifted_singleton_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,shifted_singleton_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(shifted_singleton_result));
    CHECK(std::get<HybridFamilyVerificationReport>(shifted_singleton_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto contradictory_inequality=numeric::snapshot(Matrix{1,4,{1,0,0,0}});
    auto contradictory_bound=numeric::snapshot_vector(Vector{-5e-11});
    auto fixed_equalities=numeric::snapshot(Matrix{4,4,{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1}});
    auto fixed_rhs=numeric::snapshot_vector(Vector{0,0,0,0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(contradictory_inequality));
    REQUIRE(std::holds_alternative<numeric::VectorView>(contradictory_bound));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(fixed_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(fixed_rhs));
    auto empty_candidate=sets::make_h({{"verifier-contradictory-face"},4,{}},
        {std::get<numeric::MatrixView>(contradictory_inequality),
         std::get<numeric::VectorView>(contradictory_bound),std::get<numeric::MatrixView>(fixed_equalities),
         std::get<numeric::VectorView>(fixed_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(empty_candidate));
    auto contradictory_candidates=endpoint_candidates;
    contradictory_candidates[0].relation=std::get<sets::SetData>(empty_candidate);
    const auto contradictory_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,contradictory_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(contradictory_result));
    CHECK(std::get<HybridFamilyVerificationReport>(contradictory_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto conflicting_equalities=numeric::snapshot(Matrix{5,4,
        {1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1,1,0,0,0}});
    auto conflicting_rhs=numeric::snapshot_vector(Vector{0,0,0,0,5e-11});
    auto conflicting_inequalities=numeric::snapshot(Matrix{0,4,{}});
    auto conflicting_bounds=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(conflicting_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(conflicting_rhs));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(conflicting_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(conflicting_bounds));
    auto conflicting_face=sets::make_h({{"verifier-conflicting-face"},4,{}},
        {std::get<numeric::MatrixView>(conflicting_inequalities),std::get<numeric::VectorView>(conflicting_bounds),
         std::get<numeric::MatrixView>(conflicting_equalities),std::get<numeric::VectorView>(conflicting_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(conflicting_face));
    auto conflicting_candidates=endpoint_candidates;
    conflicting_candidates[0].relation=std::get<sets::SetData>(conflicting_face);
    const auto conflicting_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,conflicting_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(conflicting_result));
    CHECK(std::get<HybridFamilyVerificationReport>(conflicting_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto rotated_equalities=numeric::snapshot(Matrix{3,4,
        {1,0,0,0,0,1,-(1+5e-11),0,0,0,1,-1}});
    auto rotated_rhs=numeric::snapshot_vector(Vector{0,0,0});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rotated_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(rotated_rhs));
    auto rotated_face=sets::make_h({{"verifier-rotated-singleton-face"},4,{}},
        {std::get<numeric::MatrixView>(conflicting_inequalities),
         std::get<numeric::VectorView>(conflicting_bounds),std::get<numeric::MatrixView>(rotated_equalities),
         std::get<numeric::VectorView>(rotated_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(rotated_face));
    auto rotated_candidates=endpoint_candidates;
    rotated_candidates[0].relation=std::get<sets::SetData>(rotated_face);
    const auto rotated_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,rotated_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(rotated_result));
    CHECK(std::get<HybridFamilyVerificationReport>(rotated_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto insufficient_variable_limits=increasing_programs;
    insufficient_variable_limits[0].relation_limits.max_variables=3;
    const auto variable_limit_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        insufficient_variable_limits,endpoint_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(variable_limit_result));
    CHECK(std::get<Diagnostics>(variable_limit_result).front().field=="hybrid.adapter.operations");

    auto near_tie_system=system;
    near_tie_system.edges[1].guards[0]=interval("verifier-near-tie-guard",5e-11,0.25);
    const auto near_tie_built=build_hybrid_portfolio_programs(near_tie_system,increasing_request,
        {"near-tie-verifier"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(near_tie_built));
    const auto& near_tie_programs=std::get<std::vector<HybridPathProgram>>(near_tie_built);
    std::vector<HybridPathOptimalFaceCandidate> near_tie_candidates{
        exact_candidate(near_tie_programs[0],{0,0,0,0}),
        exact_candidate(near_tie_programs[1],{0,5e-11,5e-11,5e-11})};
    near_tie_candidates[0].relation=singleton_data({0,0,0,0});
    near_tie_candidates[1].relation=singleton_data({0,5e-11,5e-11,5e-11});
    const auto near_tie_result=verify_hybrid_portfolio_family(verifier,near_tie_system,increasing_request,
        near_tie_programs,near_tie_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(near_tie_result));
    const auto& near_tie_report=std::get<HybridFamilyVerificationReport>(near_tie_result);
    CHECK(near_tie_report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(near_tie_report.complete_family_coverage==HybridVerificationStatus::refuted);
    CHECK(near_tie_report.branches[1].objective_optimality==HybridVerificationStatus::refuted);

    auto free_post_equalities=numeric::snapshot(Matrix{3,4,{1,0,0,0,0,1,0,0,0,0,1,0}});
    auto free_post_rhs=numeric::snapshot_vector(Vector{0,0,0});
    auto free_post_inequalities=numeric::snapshot(Matrix{0,4,{}});
    auto free_post_bounds=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(free_post_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(free_post_rhs));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(free_post_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(free_post_bounds));
    auto free_post_data=sets::make_h({{"verifier-free-post"},4,{}},
        {std::get<numeric::MatrixView>(free_post_inequalities),std::get<numeric::VectorView>(free_post_bounds),
         std::get<numeric::MatrixView>(free_post_equalities),std::get<numeric::VectorView>(free_post_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(free_post_data));
    auto malformed_face=endpoint_candidates;
    malformed_face[0].relation=std::get<sets::SetData>(free_post_data);
    const auto malformed_face_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        increasing_programs,malformed_face,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(malformed_face_result));
    CHECK(std::get<HybridFamilyVerificationReport>(malformed_face_result).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto malformed_programs=increasing_programs;
    malformed_programs[0].joint_relation=std::get<sets::SetData>(free_post_data);
    const auto malformed_program_result=verify_hybrid_portfolio_family(verifier,system,increasing_request,
        malformed_programs,endpoint_candidates,{1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(malformed_program_result));
    const auto& malformed_program_report=std::get<HybridFamilyVerificationReport>(malformed_program_result);
    CHECK(malformed_program_report.branches[0].feasibility==HybridVerificationStatus::established);
    CHECK(malformed_program_report.branches[0].continuous_coverage==HybridVerificationStatus::refuted);
    CHECK(malformed_program_report.complete_family_coverage==HybridVerificationStatus::refuted);

    auto malformed_suboptimal_programs=near_tie_programs;
    malformed_suboptimal_programs[1].joint_relation=std::get<sets::SetData>(free_post_data);
    std::vector<HybridPathOptimalFaceCandidate> only_optimal_near_tie_candidate{
        near_tie_candidates[0]};
    const auto malformed_suboptimal_result=verify_hybrid_portfolio_family(verifier,near_tie_system,
        increasing_request,malformed_suboptimal_programs,only_optimal_near_tie_candidate,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(malformed_suboptimal_result));
    const auto& malformed_suboptimal_report=
        std::get<HybridFamilyVerificationReport>(malformed_suboptimal_result);
    CHECK(malformed_suboptimal_report.branches[1].objective_optimality==HybridVerificationStatus::refuted);
    CHECK(malformed_suboptimal_report.branches[1].continuous_coverage==HybridVerificationStatus::refuted);
    CHECK(malformed_suboptimal_report.complete_family_coverage==HybridVerificationStatus::refuted);
}

TEST_CASE("one-step interval verifier accepts a point face fixed by objective equality") {
    const auto reset_equalities = numeric::snapshot(Matrix{1, 2, {-1, 1}});
    const auto reset_rhs = numeric::snapshot_vector(Vector{0});
    const auto reset_inequalities = numeric::snapshot(Matrix{0, 2, {}});
    const auto reset_bounds = numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(reset_equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(reset_rhs));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(reset_inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(reset_bounds));
    const auto reset = sets::make_h({{"point-face-reset"}, 2, {"pre", "post"}},
        {std::get<numeric::MatrixView>(reset_inequalities),
         std::get<numeric::VectorView>(reset_bounds),
         std::get<numeric::MatrixView>(reset_equalities),
         std::get<numeric::VectorView>(reset_rhs)});
    REQUIRE(std::holds_alternative<sets::SetData>(reset));
    auto system = model::HybridSystem{
        1,
        {{{"source"}, 1, 1, {"x"}, {"u"},
          LinearStage{Matrix{1,1,{1}}, Matrix{1,1,{1}}, Matrix{1,0,{}}, Vector{0}},
          {interval("point-face-control", 0, 1)}, {UniversalSet{1}, UniversalSet{1}}},
         {{"target"}, 1, 0, {"y"}, {},
          LinearStage{Matrix{1,1,{1}}, Matrix{1,0,{}}, Matrix{1,0,{}}, Vector{0}},
          {UniversalSet{0}}, {UniversalSet{1}, UniversalSet{1}}}},
        {{{"point-face-edge"}, {"source"}, {"target"}, {interval("point-face-guard", 0, 0.5)},
          {std::get<sets::SetData>(reset).as_handle()}}}};
    auto request = model::HybridRequest{{{"source"}, {0}}, {{"target"}},
        {{{"target"}, LinearTerminal{{1}, 0}, "cost", "units"}}};
    const auto built = build_hybrid_portfolio_programs(system, request, {"point-face-regression"},
        {1, 4}, {16, 64, 1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs = std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size() == 1);
    const auto& linear = std::get<LinearProgram>(programs[0].program);
    ProgramResult solver_result{Termination::completed,
        {linear.identity(), MathematicalOutcome::optimal,
         SymbolicArgument{"literal point optimum", "u=0 minimizes x_terminal=u"}, {}},
        Vector{0, 0, 0, 0}, {}, "independent analytic fixture"};
    const auto candidate_result = build_hybrid_path_optimal_face_candidate(
        programs[0], solver_result, {1e-10, 1e-10});
    REQUIRE(std::holds_alternative<HybridPathOptimalFaceCandidate>(candidate_result));
    const std::array<HybridPathOptimalFaceCandidate, 1> candidates{
        std::get<HybridPathOptimalFaceCandidate>(candidate_result)};
    OneStepScalarIntervalHybridFamilyVerifier verifier;
    const auto verified = verify_hybrid_portfolio_family(verifier, system, request, programs,
        candidates, {1, 4}, {1e-10, 1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report = std::get<HybridFamilyVerificationReport>(verified);
    CHECK(report.global_objective_optimality == HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage == HybridVerificationStatus::established);
    REQUIRE(report.branches.size() == 1);
    CHECK(report.branches[0].continuous_coverage == HybridVerificationStatus::established);
}

TEST_CASE("exact singleton hybrid verifier checks guard entry and rejects forbidden mode paths") {
    auto [system,request]=exact_singleton_portfolio();
    system.edges[0].guards[0]=Singleton{{3}};
    system.edges[1].guards[0]=Singleton{{4}};
    auto built=build_hybrid_portfolio_programs(system,request,{"exact-hybrid-guards"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    ExactSingletonHybridFamilyVerifier verifier;
    const Vector point{2,1,3,0,0};
    std::vector<HybridPathOptimalFaceCandidate> candidates{exact_candidate(programs[0],point)};
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.branches[0].feasibility==HybridVerificationStatus::established);
    CHECK(report.branches[1].feasibility==HybridVerificationStatus::refuted);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);

    auto forbidden_paths=std::vector<model::HybridPath>{programs[0].path,programs[1].path,programs[2].path};
    forbidden_paths[0].modes[1]={"source"};
    const auto rejected=verifier.verify(system,request,forbidden_paths,programs,candidates,
        {1e-10,1e-10},{});
    REQUIRE(std::holds_alternative<Diagnostics>(rejected));
    CHECK(std::get<Diagnostics>(rejected).front().field=="hybrid.verification.oracle_paths");
}

TEST_CASE("exact singleton hybrid verifier bounds independent path expansion") {
    auto [system,request]=exact_singleton_portfolio();
    system.horizon=20;
    system.edges.resize(2);
    for(std::size_t i=0;i<system.edges.size();++i) {
        system.edges[i].id={"loop-"+std::to_string(i)};
        system.edges[i].source={"source"};
        system.edges[i].target={"source"};
    }
    request.allowed_terminal_modes={{"target"}};
    ExactSingletonHybridFamilyVerifier verifier;
    const auto result=verifier.verify(system,request,{}, {}, {},{1e-10,1e-10},{});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="hybrid.verification.oracle_limit");
}

TEST_CASE("independent verifier path enumeration observes cancellation after traversal begins") {
    auto [system,request]=exact_singleton_portfolio();
    std::size_t polls=0;
    const auto result=detail::independently_enumerate_paths(system,request,10,100,[&] {
        return ++polls==7;
    });
    CHECK(result.cancelled);
    CHECK_FALSE(result.resource_limit);
    CHECK(result.paths.size()==1);
    CHECK(polls==7);
}

TEST_CASE("exact singleton hybrid verifier reports missing or altered optimal faces") {
    auto [system,request]=exact_singleton_portfolio();
    auto built=build_hybrid_portfolio_programs(system,request,{"exact-hybrid-face"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    ExactSingletonHybridFamilyVerifier verifier;
    const Vector point{2,1,3,0,0};
    std::vector<HybridPathOptimalFaceCandidate> missing{exact_candidate(programs[0],point)};
    const auto omitted=verify_hybrid_portfolio_family(verifier,system,request,programs,missing,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(omitted));
    CHECK(std::get<HybridFamilyVerificationReport>(omitted).global_objective_optimality==
        HybridVerificationStatus::established);
    CHECK(std::get<HybridFamilyVerificationReport>(omitted).complete_family_coverage==
        HybridVerificationStatus::refuted);

    std::vector<HybridPathOptimalFaceCandidate> altered{
        exact_candidate(programs[0],point),exact_candidate(programs[1],point)};
    altered[1].relation=singleton_data({2,1,3,1,0});
    const auto wrong_face=verify_hybrid_portfolio_family(verifier,system,request,programs,altered,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(wrong_face));
    CHECK(std::get<HybridFamilyVerificationReport>(wrong_face).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto wrong_programs=programs;
    wrong_programs[0].joint_relation=singleton_data({2,1,3,0,1});
    const auto wrong_relation=verify_hybrid_portfolio_family(verifier,system,request,wrong_programs,altered,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(wrong_relation));
    CHECK(std::get<HybridFamilyVerificationReport>(wrong_relation).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto over_limit_programs=programs;
    over_limit_programs[0].relation_limits.max_matrix_elements=1;
    const auto over_limit=verify_hybrid_portfolio_family(verifier,system,request,over_limit_programs,altered,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(over_limit));
    CHECK(std::get<Diagnostics>(over_limit).front().field=="hybrid.adapter.operations");

    std::vector<HybridPathOptimalFaceCandidate> extra_worse{
        exact_candidate(programs[0],point),exact_candidate(programs[1],point),
        exact_candidate(programs[2],Vector{2,1,3,1,0})};
    const auto suboptimal=verify_hybrid_portfolio_family(verifier,system,request,programs,extra_worse,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(suboptimal));
    CHECK(std::get<HybridFamilyVerificationReport>(suboptimal).complete_family_coverage==
        HybridVerificationStatus::refuted);
}

TEST_CASE("independent two-stage singleton oracle matches every mode branch and objective") {
    const auto reset_point=[](double pre,double post) {
        return singleton_relation("two-stage-reset",{pre,post});
    };
    const auto scalar_mode=[](std::string id,double stage_zero_control,double stage_one_control) {
        model::HybridMode mode{{std::move(id)},1,1,{"x"},{"u"}};
        const LinearStage flow{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
        mode.flow=std::vector<LinearStage>{flow,flow};
        mode.control_sets={Singleton{{stage_zero_control}},Singleton{{stage_one_control}}};
        mode.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
        return mode;
    };
    auto start=scalar_mode("start",1,0);
    auto middle=scalar_mode("middle",0,2);
    auto terminal=scalar_mode("terminal",0,0);
    model::HybridSystem system{2,{start,middle,terminal},
        {{{"enter"},{"start"},{"middle"},{Singleton{{1}},UniversalSet{1}},
            {reset_point(1,2),universal("unused-enter-reset",2)}},
         {{"tie-a"},{"middle"},{"terminal"},{UniversalSet{1},Singleton{{4}}},
            {universal("unused-tie-a-reset",2),reset_point(4,5)}},
         {{"tie-b"},{"middle"},{"terminal"},{UniversalSet{1},Singleton{{4}}},
            {universal("unused-tie-b-reset",2),reset_point(4,5)}},
         {{"worse"},{"middle"},{"terminal"},{UniversalSet{1},Singleton{{4}}},
            {universal("unused-worse-reset",2),reset_point(4,7)}}}};
    model::HybridRequest request{{{"start"},{0}},{{"terminal"}},
        {{{"terminal"},LinearTerminal{{1},0},"terminal-state","units"}}};

    struct OracleBranch {
        model::HybridPath path;
        Vector tuple;
        double objective;
    };
    std::vector<OracleBranch> oracle;
    // Exhaustively interpret this two-stage graph from raw input data. This
    // deliberately does not call production path enumeration, composition,
    // objective lifting, or verification.
    const auto find_mode_raw=[&](const model::HybridModeId& id)->const model::HybridMode* {
        const auto found=std::find_if(system.modes.begin(),system.modes.end(),
            [&](const auto& mode){return mode.id==id;});
        return found==system.modes.end()?nullptr:&*found;
    };
    const auto singleton_set=[](const AdmissibleSet& set)->const Singleton* {
        return std::get_if<Singleton>(&set);
    };
    const auto reset_target=[&](const SetHandle& handle,double pre,double& post) {
        const auto decoded=sets::from_handle(handle);
        if(std::holds_alternative<Diagnostic>(decoded)) return false;
        const auto representation=std::get<sets::SetData>(decoded).representation();
        const auto* point=std::get_if<sets::SingletonRepresentation>(&representation);
        if(!point||point->point.size()!=2||point->point[0]!=pre) return false;
        post=point->point[1];
        return true;
    };
    for(const auto& first:system.edges) {
        if(first.source!=request.initial.mode) continue;
        const auto* first_mode=find_mode_raw(first.source);
        const auto* first_control=singleton_set(first_mode->control_sets[0]);
        REQUIRE(first_control!=nullptr);
        REQUIRE(first_control->point.size()==1);
        const auto& first_flow=std::get<std::vector<LinearStage>>(first_mode->flow)[0];
        const double first_pre=first_flow.A.values[0]*request.initial.state[0]+
            first_flow.B.values[0]*first_control->point[0];
        const auto* first_guard=singleton_set(first.guards[0]);
        if(!first_guard||first_guard->point!=Vector{first_pre}) continue;
        double middle_state=0;
        if(!reset_target(first.reset_relations[0],first_pre,middle_state)) continue;
        for(const auto& second:system.edges) {
            if(second.source!=first.target) continue;
            const auto* second_mode=find_mode_raw(second.source);
            const auto* second_control=singleton_set(second_mode->control_sets[1]);
            REQUIRE(second_control!=nullptr);
            REQUIRE(second_control->point.size()==1);
            const auto& second_flow=std::get<std::vector<LinearStage>>(second_mode->flow)[1];
            const double second_pre=second_flow.A.values[0]*middle_state+
                second_flow.B.values[0]*second_control->point[0];
            const auto* second_guard=singleton_set(second.guards[1]);
            if(!second_guard||second_guard->point!=Vector{second_pre}) continue;
            const auto decoded=sets::from_handle(second.reset_relations[1]);
            REQUIRE(std::holds_alternative<sets::SetData>(decoded));
            const auto rep=std::get<sets::SetData>(decoded).representation();
            const auto* point=std::get_if<sets::SingletonRepresentation>(&rep);
            REQUIRE(point!=nullptr);
            REQUIRE(point->point.size()==2);
            REQUIRE(point->point[0]==second_pre);
            const double terminal_state=point->point[1];
            oracle.push_back({{{first.source,first.target,second.target},{first.id,second.id}},
                {request.initial.state[0],first_control->point[0],first_pre,middle_state,
                 second_control->point[0],second_pre,terminal_state},terminal_state});
        }
    }
    REQUIRE(oracle.size()==3);

    const auto built=build_hybrid_portfolio_programs(system,request,{"two-stage-independent-oracle"},
        {2,16},{32,256,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==oracle.size());
    for(const auto& expected:oracle) {
        const auto found=std::find_if(programs.begin(),programs.end(),[&](const auto& program) {
            return program.path==expected.path;
        });
        REQUIRE(found!=programs.end());
        const auto relation_representation=found->joint_relation.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(relation_representation));
        const auto& relation=std::get<sets::HRepresentation>(relation_representation);
        CHECK(satisfies(relation,expected.tuple));
        CHECK(equality_rank(relation.equalities)==expected.tuple.size());
        const auto& linear=std::get<LinearProgram>(found->program);
        REQUIRE(linear.objective().size()==expected.tuple.size());
        double objective=linear.offset();
        for(std::size_t i=0;i<expected.tuple.size();++i)
            objective+=linear.objective()[i]*expected.tuple[i];
        CHECK(objective==expected.objective);
    }
    CHECK(oracle[0].objective==5);
    CHECK(oracle[1].objective==5);
    CHECK(oracle[2].objective==7);

    std::vector<HybridPathOptimalFaceCandidate> optimal_candidates;
    for(const auto& expected:oracle) {
        if(expected.objective!=5) continue;
        const auto found=std::find_if(programs.begin(),programs.end(),[&](const auto& program) {
            return program.path==expected.path;
        });
        REQUIRE(found!=programs.end());
        optimal_candidates.push_back(exact_candidate(*found,expected.tuple));
    }
    REQUIRE(optimal_candidates.size()==2);
    ExactSingletonHybridFamilyVerifier verifier;
    const auto verified=verify_hybrid_portfolio_family(verifier,system,request,programs,
        optimal_candidates,{2,16},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(verified));
    const auto& report=std::get<HybridFamilyVerificationReport>(verified);
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    REQUIRE(report.branches.size()==3);
    const auto branch_record=[&](const std::string& edge_id) {
        return std::find_if(report.branches.begin(),report.branches.end(),[&](const auto& branch) {
            return branch.path.edges.size()==2&&branch.path.edges[1].value==edge_id;
        });
    };
    const auto tie_a=branch_record("tie-a");
    const auto tie_b=branch_record("tie-b");
    const auto worse=branch_record("worse");
    REQUIRE(tie_a!=report.branches.end());
    REQUIRE(tie_b!=report.branches.end());
    REQUIRE(worse!=report.branches.end());
    CHECK(tie_a->feasibility==HybridVerificationStatus::established);
    CHECK(tie_a->objective_optimality==HybridVerificationStatus::established);
    CHECK(tie_b->feasibility==HybridVerificationStatus::established);
    CHECK(tie_b->objective_optimality==HybridVerificationStatus::established);
    CHECK(worse->feasibility==HybridVerificationStatus::established);
    CHECK(worse->objective_optimality==HybridVerificationStatus::refuted);
}

TEST_CASE("two-stage scalar interval verifier checks tied continuous families independently") {
    const auto interval_reset=[](std::string id,double pre,double post,double rhs) {
        auto inequalities=numeric::snapshot(Matrix{0,2,{}});
        auto upper=numeric::snapshot_vector(Vector{});
        auto equalities=numeric::snapshot(Matrix{1,2,{pre,post}});
        auto values=numeric::snapshot_vector(Vector{rhs});
        REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
        REQUIRE(std::holds_alternative<numeric::VectorView>(upper));
        REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
        REQUIRE(std::holds_alternative<numeric::VectorView>(values));
        auto data=sets::make_h({SetId{std::move(id)},2,{"pre","post"}},
            {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(upper),
             std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(values)});
        REQUIRE(std::holds_alternative<sets::SetData>(data));
        return std::get<sets::SetData>(std::move(data)).as_handle();
    };
    const auto scalar_mode=[](std::string id,AdmissibleSet first_control,
        AdmissibleSet second_control) {
        model::HybridMode mode{{std::move(id)},1,1,{"x"},{"u"}};
        const LinearStage flow{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
        mode.flow=std::vector<LinearStage>{flow,flow};
        mode.control_sets={std::move(first_control),std::move(second_control)};
        mode.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1}};
        return mode;
    };
    auto start=scalar_mode("start",interval("two-stage-free-control",0,1),Singleton{{0}});
    auto middle=scalar_mode("middle",Singleton{{0}},Singleton{{0}});
    auto terminal=scalar_mode("terminal",Singleton{{0}},Singleton{{0}});
    struct OracleEdge { std::string id; double lower; double upper; double terminal_value; };
    const std::vector<OracleEdge> second_stage_edges{
        {"tie-a",0,0.5,0},{"tie-b",0,1,0},{"worse",1,1,1}};
    const auto identity=interval_reset("two-stage-identity-reset",-1,1,0);
    std::vector<model::HybridTransitionEdge> edges{
        {{"enter"},{"start"},{"middle"},{interval("two-stage-entry-guard",0,1),UniversalSet{1}},
            {identity,universal("two-stage-unused-entry-reset",2)}}};
    for(const auto& spec:second_stage_edges) {
        edges.push_back({{spec.id},{"middle"},{"terminal"},
            {UniversalSet{1},interval("two-stage-guard-"+spec.id,spec.lower,spec.upper)},
            {universal("two-stage-unused-reset-"+spec.id,2),
             interval_reset("two-stage-terminal-reset-"+spec.id,0,1,spec.terminal_value)}});
    }
    model::HybridSystem system{2,{start,middle,terminal},std::move(edges)};
    model::HybridRequest request{{{"start"},{0}},{{"terminal"}},
        {{{"terminal"},LinearTerminal{{1},0},"terminal-state","units"}}};

    struct OracleBranch { model::HybridPath path; double lower; double upper; double cost; };
    std::vector<OracleBranch> oracle;
    for(const auto& spec:second_stage_edges) {
        // Raw rational fixture equations: x_pre[0]=u[0], x_post[1]=x_pre[0],
        // x_pre[1]=x_post[1], and the selected edge clips u[0] to its guard.
        const double lower=std::max(0.0,spec.lower);
        const double upper=std::min(1.0,spec.upper);
        if(lower<=upper)
            oracle.push_back({model::HybridPath{{model::HybridModeId{"start"},
                    model::HybridModeId{"middle"},model::HybridModeId{"terminal"}},
                {model::HybridEdgeId{"enter"},model::HybridEdgeId{spec.id}}},
                lower,upper,spec.terminal_value});
    }
    REQUIRE(oracle.size()==3);
    CHECK(oracle[0].lower==0);
    CHECK(oracle[0].upper==0.5);
    CHECK(oracle[1].lower==0);
    CHECK(oracle[1].upper==1);
    CHECK(oracle[2].lower==1);
    CHECK(oracle[2].upper==1);
    CHECK(oracle[0].cost==0);
    CHECK(oracle[1].cost==0);
    CHECK(oracle[2].cost==1);

    const auto built=build_hybrid_portfolio_programs(system,request,{"two-stage-continuous-verifier"},
        {2,16},{64,512,8192});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==oracle.size());
    std::vector<HybridPathOptimalFaceCandidate> candidates;
    for(std::size_t i=0;i<2;++i) {
        const auto found=std::find_if(programs.begin(),programs.end(),[&](const auto& program) {
            return program.path.edges.back().value==oracle[i].path.edges.back().value;
        });
        REQUIRE(found!=programs.end());
        candidates.push_back(exact_candidate(*found,{0,0,0,0,0,0,0}));
    }
    TwoStageScalarIntervalHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {2,16},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.verifier_id=="csl.hybrid.two-stage-scalar-interval");
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    const auto record_for=[&](const std::string& edge_id) {
        return std::find_if(report.branches.begin(),report.branches.end(),[&](const auto& branch) {
            return branch.path.edges.back().value==edge_id;
        });
    };
    for(const auto& expected:oracle) {
        const auto program=std::find_if(programs.begin(),programs.end(),[&](const auto& value) {
            return value.path.edges.back().value==expected.path.edges.back().value;
        });
        REQUIRE(program!=programs.end());
        const auto relation_representation=program->joint_relation.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(relation_representation));
        const auto& relation=std::get<sets::HRepresentation>(relation_representation);
        REQUIRE(relation.inequalities.cols()==7);
        const auto joint_at=[&](double parameter) {
            return Vector{0,parameter,parameter,parameter,0,parameter,expected.cost};
        };
        CHECK(satisfies(relation,joint_at(expected.lower)));
        CHECK(satisfies(relation,joint_at(expected.upper)));
        const double excluded=expected.lower>0 ? expected.lower-0.25 :
            (expected.upper<1 ? expected.upper+0.25 : -0.25);
        CHECK_FALSE(satisfies(relation,joint_at(excluded)));

        const auto record=record_for(expected.path.edges.back().value);
        REQUIRE(record!=report.branches.end());
        INFO("branch " << expected.path.edges.back().value << " coverage " <<
            static_cast<int>(record->continuous_coverage));
        for(const auto& diagnostic:record->diagnostics)
            INFO("diagnostic " << diagnostic.field << ": " << diagnostic.explanation);
        CHECK(record->feasibility==HybridVerificationStatus::established);
        CHECK(record->objective_optimality==(expected.cost==0?HybridVerificationStatus::established:
            HybridVerificationStatus::refuted));
        CHECK(record->continuous_coverage==HybridVerificationStatus::established);
    }

    auto disjoint_system=system;
    disjoint_system.edges.push_back({{"infeasible"},{"middle"},{"terminal"},
        {UniversalSet{1},interval("two-stage-disjoint-guard",2,3)},
        {universal("two-stage-disjoint-unused-reset",2),identity}});
    const auto disjoint_built=build_hybrid_portfolio_programs(disjoint_system,request,
        {"two-stage-infeasible-relation"},{2,16},{64,512,8192});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(disjoint_built));
    const auto& disjoint_programs=std::get<std::vector<HybridPathProgram>>(disjoint_built);
    const auto disjoint_result=verify_hybrid_portfolio_family(verifier,disjoint_system,request,
        disjoint_programs,{}, {2,16},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(disjoint_result));
    const auto& disjoint_report=std::get<HybridFamilyVerificationReport>(disjoint_result);
    CHECK(disjoint_report.global_objective_optimality==HybridVerificationStatus::unsupported);
    const auto infeasible_record=std::find_if(disjoint_report.branches.begin(),
        disjoint_report.branches.end(),[](const auto& branch) {
            return branch.path.edges.back().value=="infeasible";
        });
    REQUIRE(infeasible_record!=disjoint_report.branches.end());
    CHECK(infeasible_record->feasibility==HybridVerificationStatus::unsupported);
    CHECK(infeasible_record->continuous_coverage==HybridVerificationStatus::unsupported);
}

TEST_CASE("single-parameter scalar interval verifier covers arbitrary finite horizons") {
    const auto make_reset=[](const std::string& id,double pre,double post,double rhs) {
        auto inequalities=numeric::snapshot(Matrix{0,2,{}});
        auto upper=numeric::snapshot_vector(Vector{});
        auto equalities=numeric::snapshot(Matrix{1,2,{pre,post}});
        auto values=numeric::snapshot_vector(Vector{rhs});
        REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
        REQUIRE(std::holds_alternative<numeric::VectorView>(upper));
        REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
        REQUIRE(std::holds_alternative<numeric::VectorView>(values));
        auto data=sets::make_h({SetId{id},2,{"pre","post"}},
            {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(upper),
             std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(values)});
        REQUIRE(std::holds_alternative<sets::SetData>(data));
        return std::get<sets::SetData>(std::move(data)).as_handle();
    };
    const auto scalar_mode=[](std::string id) {
        model::HybridMode mode{{std::move(id)},1,1,{"x"},{"u"}};
        const LinearStage flow{Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}};
        mode.flow=std::vector<LinearStage>{flow,flow,flow};
        mode.control_sets={interval("multi-horizon-free",0,1),Singleton{{0}},Singleton{{0}}};
        mode.invariants={UniversalSet{1},UniversalSet{1},UniversalSet{1},UniversalSet{1}};
        return mode;
    };
    auto start=scalar_mode("start");
    auto middle=scalar_mode("middle");
    auto late=scalar_mode("late");
    auto terminal=scalar_mode("terminal");
    const auto identity=make_reset("multi-horizon-identity",1,-1,0);
    const auto constant_zero=make_reset("multi-horizon-zero",0,1,0);
    const auto constant_one=make_reset("multi-horizon-one",0,1,1);
    const std::vector<AdmissibleSet> universal_guards(3,UniversalSet{1});
    const std::vector<SetHandle> unused_resets(3,universal("multi-horizon-unused-reset",2));
    std::vector<model::HybridTransitionEdge> edges{
        {{"enter"},{"start"},{"middle"},universal_guards,{identity,unused_resets[1],unused_resets[2]}},
        {{"continue"},{"middle"},{"late"},universal_guards,{unused_resets[0],identity,unused_resets[2]}},
        {{"tie-a"},{"late"},{"terminal"},
            {UniversalSet{1},UniversalSet{1},interval("multi-horizon-guard-a",0,0.5)},
            {unused_resets[0],unused_resets[1],constant_zero}},
        {{"tie-b"},{"late"},{"terminal"},
            {UniversalSet{1},UniversalSet{1},interval("multi-horizon-guard-b",0,1)},
            {unused_resets[0],unused_resets[1],constant_zero}},
        {{"worse"},{"late"},{"terminal"},
            {UniversalSet{1},UniversalSet{1},Singleton{{1}}},
            {unused_resets[0],unused_resets[1],constant_one}}};
    model::HybridSystem system{3,{start,middle,late,terminal},std::move(edges)};
    model::HybridRequest request{{{"start"},{0}},{{"terminal"}},
        {{{"terminal"},LinearTerminal{{1},0},"terminal-state","units"}}};

    struct OracleEdge { const char* id; double lower; double upper; double cost; };
    const std::array<OracleEdge,3> oracle{{
        {"tie-a",0,0.5,0},{"tie-b",0,1,0},{"worse",1,1,1}}};
    for(const auto& expected:oracle) {
        CHECK(expected.lower==(std::string_view(expected.id)=="worse"?1:0));
        CHECK(expected.upper==(std::string_view(expected.id)=="tie-a"?0.5:1));
        CHECK(expected.cost==(std::string_view(expected.id)=="worse"?1:0));
    }
    const auto built=build_hybrid_portfolio_programs(system,request,{"multi-horizon-verifier"},
        {3,32},{64,1024,16384});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==oracle.size());
    for(const auto& expected:oracle) {
        const auto found=std::find_if(programs.begin(),programs.end(),[&](const auto& program) {
            return program.path.edges.back().value==expected.id;
        });
        REQUIRE(found!=programs.end());
        const auto representation=found->joint_relation.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
        const auto& relation=std::get<sets::HRepresentation>(representation);
        const auto tuple_at=[&](double free_control) {
            return Vector{0,free_control,free_control,free_control,0,free_control,
                free_control,0,free_control,expected.cost};
        };
        CHECK(satisfies(relation,tuple_at(expected.lower)));
        CHECK(satisfies(relation,tuple_at(expected.upper)));
        if(std::string_view(expected.id)=="tie-a")
            CHECK_FALSE(satisfies(relation,tuple_at(0.75)));
        if(std::string_view(expected.id)=="worse")
            CHECK_FALSE(satisfies(relation,tuple_at(0.5)));
    }
    std::vector<HybridPathOptimalFaceCandidate> candidates;
    for(std::size_t i=0;i<2;++i) {
        const auto found=std::find_if(programs.begin(),programs.end(),[&](const auto& program) {
            return program.path.edges.back().value==oracle[i].id;
        });
        REQUIRE(found!=programs.end());
        candidates.push_back(exact_candidate(*found,Vector(10,0)));
    }
    SingleParameterScalarIntervalHybridFamilyVerifier verifier;
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {3,32},{0,0});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.verifier_id=="csl.hybrid.scalar-single-parameter-interval");
    CHECK(report.global_objective_optimality==HybridVerificationStatus::established);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    for(const auto& expected:oracle) {
        const auto record=std::find_if(report.branches.begin(),report.branches.end(),[&](const auto& item) {
            return item.path.edges.back().value==expected.id;
        });
        REQUIRE(record!=report.branches.end());
        CHECK(record->feasibility==HybridVerificationStatus::established);
        CHECK(record->objective_optimality==(expected.cost==0?HybridVerificationStatus::established:
            HybridVerificationStatus::refuted));
        CHECK(record->continuous_coverage==HybridVerificationStatus::established);
    }
}

TEST_CASE("exact singleton hybrid verifier handles empty branches and rejects continuous domains") {
    auto [system,request]=exact_singleton_portfolio();
    system.edges[0].guards[0]=EmptySet{1};
    auto built=build_hybrid_portfolio_programs(system,request,{"exact-hybrid-empty"},
        {1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    ExactSingletonHybridFamilyVerifier verifier;
    const Vector point{2,1,3,0,0};
    std::vector<HybridPathOptimalFaceCandidate> candidates{exact_candidate(programs[1],point)};
    const auto result=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(result));
    const auto& report=std::get<HybridFamilyVerificationReport>(result);
    CHECK(report.branches[0].feasibility==HybridVerificationStatus::refuted);
    CHECK(report.branches[0].objective_optimality==HybridVerificationStatus::refuted);
    CHECK(report.complete_family_coverage==HybridVerificationStatus::established);
    candidates.push_back(exact_candidate(programs[0],point));
    const auto infeasible_face=verify_hybrid_portfolio_family(verifier,system,request,programs,candidates,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(infeasible_face));
    CHECK(std::get<HybridFamilyVerificationReport>(infeasible_face).complete_family_coverage==
        HybridVerificationStatus::refuted);

    auto continuous_system=example_system();
    auto continuous_built=build_hybrid_portfolio_programs(continuous_system,example_request(),
        {"continuous-hybrid"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(continuous_built));
    const auto unsupported=verify_hybrid_portfolio_family(verifier,continuous_system,example_request(),
        std::get<std::vector<HybridPathProgram>>(continuous_built),{}, {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(unsupported));
    CHECK(std::get<HybridFamilyVerificationReport>(unsupported).global_objective_optimality==
        HybridVerificationStatus::unsupported);

    auto [mixed_system,mixed_request]=exact_singleton_portfolio();
    mixed_system.edges[0].reset_relations[0]=affine_reset();
    const auto mixed_programs=build_hybrid_portfolio_programs(mixed_system,mixed_request,
        {"mixed-domain-hybrid"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(mixed_programs));
    const auto mixed=verify_hybrid_portfolio_family(verifier,mixed_system,mixed_request,
        std::get<std::vector<HybridPathProgram>>(mixed_programs),{}, {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(mixed));
    const auto& mixed_report=std::get<HybridFamilyVerificationReport>(mixed);
    CHECK(mixed_report.branches[0].feasibility==HybridVerificationStatus::unsupported);
    CHECK(mixed_report.branches[1].objective_optimality==HybridVerificationStatus::unsupported);
    CHECK(mixed_report.branches[1].continuous_coverage==HybridVerificationStatus::unsupported);
    CHECK(mixed_report.branches[2].objective_optimality==HybridVerificationStatus::refuted);
    CHECK(mixed_report.global_objective_optimality==HybridVerificationStatus::unsupported);

    auto [limited_system,limited_request]=exact_singleton_portfolio();
    const auto limited_programs=build_hybrid_portfolio_programs(limited_system,limited_request,
        {"exact-hybrid-limit"},{1,8},{32,128,4096});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(limited_programs));
    const auto path_limit=verify_hybrid_portfolio_family(verifier,limited_system,limited_request,
        std::get<std::vector<HybridPathProgram>>(limited_programs),{}, {1,2},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(path_limit));
    CHECK(std::get<Diagnostics>(path_limit).front().field=="hybrid.paths.limit");

    std::stop_source cancellation;
    cancellation.request_stop();
    const auto cancelled=verify_hybrid_portfolio_family(verifier,limited_system,limited_request,
        std::get<std::vector<HybridPathProgram>>(limited_programs),{}, {1,8},{1e-10,1e-10},
        cancellation.get_token());
    CHECK(std::holds_alternative<OperationStopped>(cancelled));
    std::vector<model::HybridPath> paths;
    for(const auto& program:std::get<std::vector<HybridPathProgram>>(limited_programs))
        paths.push_back(program.path);
    const auto adapter_cancelled=verifier.verify(limited_system,limited_request,paths,
        std::get<std::vector<HybridPathProgram>>(limited_programs),{}, {1e-10,1e-10},
        cancellation.get_token());
    CHECK(std::holds_alternative<OperationStopped>(adapter_cancelled));
}

TEST_CASE("hybrid portfolio objective bounds retain tied possible branches") {
    auto system=example_system();
    auto second=system.edges.front(); second.id={"switch-second"};
    auto third=system.edges.front(); third.id={"switch-third"};
    system.edges.push_back(std::move(second));
    system.edges.push_back(std::move(third));
    const auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==3);

    HybridPortfolioExecution execution;
    execution.all_supplied_branches_completed=true;
    const std::array<double,3> values{5,5,7};
    for(std::size_t i=0;i<programs.size();++i) {
        const auto& program=std::get<LinearProgram>(programs[i].program);
        const auto evidence=ProgramBoundEvidence{program.identity(),
            SymbolicArgument{"literal fixture bounds","synthetic test result"},{}};
        ProgramResult result{Termination::completed,
            {program.identity(),MathematicalOutcome::optimal,
                SymbolicArgument{"literal fixture optimum","synthetic test result"},{}},
            {},{ProgramObjectiveBound{values[i],evidence},ProgramObjectiveBound{values[i],evidence}},
            "literal fixture result"};
        execution.branches.push_back({programs[i].path,Termination::completed,
            MathematicalOutcome::optimal,std::move(result),{}, {}});
    }

    const auto comparison=compare_hybrid_portfolio_objective_bounds(programs,execution,{0,0});
    REQUIRE(std::holds_alternative<HybridPortfolioObjectiveBounds>(comparison));
    const auto& bounds=std::get<HybridPortfolioObjectiveBounds>(comparison);
    CHECK(bounds.global_lower_bound==5);
    CHECK(bounds.global_upper_bound==5);
    REQUIRE(bounds.potentially_optimal_paths.size()==2);
    CHECK(bounds.potentially_optimal_paths[0]==programs[0].path);
    CHECK(bounds.potentially_optimal_paths[1]==programs[1].path);
    REQUIRE(bounds.global_lower_bound_sources.size()==2);
    REQUIRE(bounds.global_upper_bound_sources.size()==2);
    CHECK(bounds.global_lower_bound_sources[0].path==programs[0].path);
    CHECK(bounds.global_lower_bound_sources[0].bound.evidence.subject==
        std::get<LinearProgram>(programs[0].program).identity());

    auto incomplete=execution;
    incomplete.branches[2].result->objective.lower.reset();
    const auto partial=compare_hybrid_portfolio_objective_bounds(programs,incomplete,{0,0});
    REQUIRE(std::holds_alternative<HybridPortfolioObjectiveIncomplete>(partial));
    CHECK(std::get<HybridPortfolioObjectiveIncomplete>(partial).
        branches_without_comparable_bounds==std::vector<std::size_t>{2});

    auto unsupported=execution;
    unsupported.branches[2].result->objective.lower->evidence.support=Unestablished{};
    const auto unestablished=compare_hybrid_portfolio_objective_bounds(programs,unsupported,{0,0});
    REQUIRE(std::holds_alternative<HybridPortfolioObjectiveIncomplete>(unestablished));
    CHECK(std::get<HybridPortfolioObjectiveIncomplete>(unestablished).
        branches_without_comparable_bounds==std::vector<std::size_t>{2});

    auto inconsistent=execution;
    inconsistent.branches[1].result->termination=Termination::cancelled;
    const auto interrupted=compare_hybrid_portfolio_objective_bounds(programs,inconsistent,{0,0});
    REQUIRE(std::holds_alternative<HybridPortfolioObjectiveIncomplete>(interrupted));
    CHECK(std::get<HybridPortfolioObjectiveIncomplete>(interrupted).
        branches_without_comparable_bounds==std::vector<std::size_t>{1});
}

TEST_CASE("hybrid path optimal-face candidates preserve the full minimizer equations") {
    auto check_face=[&](TerminalObjective objective,double objective_value) {
        auto system=example_system();
        system.modes[0].control_sets[0]=interval("bounded-control",-1,1);
        system.edges[0].reset_relations[0]=affine_reset();
        auto request=example_request();
        request.terminal_objectives[0].objective=std::move(objective);
        auto built=build_hybrid_path_program(system,request,example_path(),{"hybrid-face"},{16,64,1024});
        REQUIRE(std::holds_alternative<HybridPathProgram>(built));
        const auto& branch=std::get<HybridPathProgram>(built);
        const ProgramIdentity identity=std::visit([](const auto& program){return program.identity();},branch.program);
        const auto support=SymbolicArgument{"literal face fixture","synthetic global optimum"};
        const ProgramBoundEvidence bound{identity,support,{}};
        ProgramResult solved{Termination::completed,{identity,MathematicalOutcome::optimal,support,{}},
            Vector{2,-1,1,1,0},
            {ProgramObjectiveBound{objective_value,bound},ProgramObjectiveBound{objective_value,bound}},
            "literal feasible optimizer"};
        const auto face=build_hybrid_path_optimal_face_candidate(branch,solved,{1e-10,1e-10});
        REQUIRE(std::holds_alternative<HybridPathOptimalFaceCandidate>(face));
        const auto& candidate=std::get<HybridPathOptimalFaceCandidate>(face);
        CHECK(candidate.path==example_path());
        CHECK(candidate.anchor==Vector{2,-1,1,1,0});
        CHECK(candidate.solver_result.objective.upper->value==objective_value);
        const auto representation=candidate.relation.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
        const auto& h=std::get<sets::HRepresentation>(representation);
        CHECK(satisfies(h,{2,-1,1,1,0}));
        CHECK(satisfies(h,{2,-1,1,1,1}));
        CHECK_FALSE(satisfies(h,{2,0,2,2,0}));
        CHECK(candidate.assumptions.size()==3);
    };

    check_face(LinearTerminal{{1,0},0},1);
    check_face(QuadraticTerminal{Matrix{2,2,{2,0,0,0}},Vector{0,0},0},1);
    check_face(ResidualNormTerminal{Matrix{1,2,{1,0}},Vector{1}},0);

    auto system=example_system();
    system.modes[0].control_sets[0]=interval("bounded-control-mismatch",-1,1);
    system.edges[0].reset_relations[0]=affine_reset();
    auto request=example_request();
    request.terminal_objectives[0].objective=LinearTerminal{{1,0},0};
    auto built=build_hybrid_path_program(system,request,example_path(),{"hybrid-face-mismatch"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    auto mismatched=std::get<HybridPathProgram>(std::move(built));
    const auto& program=std::get<LinearProgram>(mismatched.program);
    const auto support=SymbolicArgument{"literal mismatch fixture","synthetic global optimum"};
    const ProgramBoundEvidence bound{program.identity(),support,{}};
    ProgramResult solved{Termination::completed,{program.identity(),MathematicalOutcome::optimal,support,{}},
        Vector{2,-1,1,1,0},
        {ProgramObjectiveBound{1,bound},ProgramObjectiveBound{1,bound}},"literal feasible optimizer"};
    mismatched.joint_relation=relation_excluding_anchor();
    const auto rejected=build_hybrid_path_optimal_face_candidate(mismatched,solved,{1e-10,1e-10});
    REQUIRE(std::holds_alternative<Diagnostics>(rejected));
    CHECK(std::get<Diagnostics>(rejected)[0].field=="hybrid.optimal_face.source_relation");
}

TEST_CASE("hybrid portfolio assembly retains every tied branch face transactionally") {
    auto system=example_system();
    auto parallel=system.edges.front();
    parallel.id={"switch-parallel-face"};
    system.edges.push_back(std::move(parallel));
    auto request=example_request();
    request.terminal_objectives[0].objective=LinearTerminal{{0,0},0};
    const auto built=build_hybrid_portfolio_programs(system,request,{"hybrid-face-portfolio"},
        {1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<std::vector<HybridPathProgram>>(built));
    const auto& programs=std::get<std::vector<HybridPathProgram>>(built);
    REQUIRE(programs.size()==2);

    HybridPortfolioExecution execution;
    execution.all_supplied_branches_completed=true;
    for(const auto& branch:programs) {
        const auto& program=std::get<LinearProgram>(branch.program);
        const auto support=SymbolicArgument{"constant objective","all feasible points minimize"};
        const ProgramBoundEvidence bound{program.identity(),support,{}};
        ProgramResult result{Termination::completed,
            {program.identity(),MathematicalOutcome::optimal,support,{}},Vector{2,0,2,0,0},
            {ProgramObjectiveBound{0,bound},ProgramObjectiveBound{0,bound}},"constant objective fixture"};
        execution.branches.push_back({branch.path,Termination::completed,MathematicalOutcome::optimal,
            std::move(result),{{"fixture",{ModuleId{"test-provider"},{}},{}}},{}});
    }
    const auto assembled=assemble_hybrid_portfolio_optimal_face_candidates(programs,execution,{0,0});
    REQUIRE(std::holds_alternative<HybridPortfolioOptimalFaceCandidates>(assembled));
    const auto& portfolio=std::get<HybridPortfolioOptimalFaceCandidates>(assembled);
    REQUIRE(portfolio.branches.size()==2);
    CHECK(portfolio.branches[0].path==programs[0].path);
    CHECK(portfolio.branches[1].path==programs[1].path);
    REQUIRE(portfolio.branches[0].providers.size()==1);
    CHECK(portfolio.branches[0].providers[0].port=="fixture");
    CHECK(portfolio.branches[0].providers[0].requested.id.value=="test-provider");
    CHECK(portfolio.branches[0].assumptions.back()=="family completeness and global cross-branch optimality remain unverified");

    auto duplicate_programs=programs;
    duplicate_programs.push_back(programs.front());
    const auto duplicate_paths=assemble_hybrid_portfolio_optimal_face_candidates(
        duplicate_programs,execution,{0,0});
    REQUIRE(std::holds_alternative<Diagnostics>(duplicate_paths));
    CHECK(std::get<Diagnostics>(duplicate_paths)[0].field=="hybrid.optimal_face.path");

    std::stop_source cancellation;
    cancellation.request_stop();
    const auto cancelled=assemble_hybrid_portfolio_optimal_face_candidates(
        programs,execution,{0,0},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(cancelled));
    CHECK(std::get<OperationStopped>(cancelled).reason==StopReason::cancelled);
}

TEST_CASE("hybrid portfolio builder rejects a pre-cancelled request") {
    auto system=example_system();
    std::stop_source source;
    source.request_stop();
    const auto built=build_hybrid_portfolio_programs(system,example_request(),{"hybrid-problem"},
        {1,8},{16,64,1024},{},source.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(built));
    CHECK(std::get<OperationStopped>(built).reason==StopReason::cancelled);
}

TEST_CASE("hybrid portfolio builder rolls back after a later dimension limit failure") {
    auto [system,request]=variable_size_parallel_profile();
    const auto built=build_hybrid_portfolio_programs(system,request,{"hybrid-problem"},
        {1,8},{3,64,4096});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(built));
    const auto& failure=std::get<model::HybridPathCompositionFailureReport>(built);
    CHECK(failure.path.edges==std::vector<model::HybridEdgeId>{{"to-large"}});
    CHECK(failure.limits.max_variables==3);
    const auto* diagnostic=std::get_if<Diagnostic>(&failure.failure);
    REQUIRE(diagnostic);
    CHECK(diagnostic->field=="hybrid.relation.variables");
}

TEST_CASE("direct trajectory adapters preflight the full path inventory before capabilities or builds") {
    auto [system,request]=variable_size_parallel_profile();
    RejectingTrajectoryPreflightAdapter adapter;
    const auto portfolio=build_hybrid_portfolio_programs(adapter,system,
        request,{"hybrid-problem"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(portfolio));
    const auto& failure=std::get<model::HybridPathCompositionFailureReport>(portfolio);
    CHECK(failure.path.edges==std::vector<model::HybridEdgeId>{{"to-large"}});
    CHECK(std::get<Diagnostic>(failure.failure).field=="fixture.trajectory.preflight");
    CHECK(adapter.preflight_calls==1);
    CHECK(adapter.capability_calls==0);
    CHECK(adapter.build_calls==0);

    RejectingTrajectoryPreflightAdapter single_adapter;
    const auto single=build_hybrid_path_program(single_adapter,example_system(),
        example_request(),example_path(),{"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<model::HybridPathCompositionFailureReport>(single));
    CHECK(std::get<model::HybridPathCompositionFailureReport>(single).path==example_path());
    CHECK(single_adapter.preflight_calls==1);
    CHECK(single_adapter.capability_calls==0);
    CHECK(single_adapter.build_calls==0);
}

TEST_CASE("direct trajectory adapters may admit a representation outside the joint-H default") {
    auto system=example_system();
    system.edges.front().guards.front()=vertex_guard("alternate-guard");
    AdmittingTrajectoryPreflightAdapter adapter;
    const auto result=build_hybrid_path_program(adapter,system,example_request(),
        example_path(),{"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="fixture.alternate_representation");
    CHECK(adapter.preflight_calls==1);
    CHECK(adapter.capability_calls==1);
    CHECK(adapter.build_calls==1);
}

TEST_CASE("direct trajectory preflight failures must retain requested path and limits") {
    for(const int corruption : {0,1}) {
        RejectingTrajectoryPreflightAdapter adapter;
        adapter.corruption=corruption;
        const auto result=build_hybrid_path_program(adapter,example_system(),
            example_request(),example_path(),{"hybrid-problem"},{16,64,1024});
        REQUIRE(std::holds_alternative<Diagnostics>(result));
        const auto& diagnostic=std::get<Diagnostics>(result).front();
        CHECK(diagnostic.code==DiagnosticCode::evidence_mismatch);
        CHECK(diagnostic.field==(corruption==0?"hybrid.adapter.preflight_path":
            "hybrid.adapter.preflight_limits"));
        CHECK(adapter.capability_calls==0);
        CHECK(adapter.build_calls==0);
    }
}

TEST_CASE("portfolio uses one inventory-wide trajectory preflight before branch builds") {
    auto [system,request]=variable_size_parallel_profile();
    InventoryOnlyTrajectoryPreflightAdapter adapter;
    const auto result=build_hybrid_portfolio_programs(adapter,system,request,
        {"hybrid-problem"},{1,8},{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostics>(result));
    CHECK(std::get<Diagnostics>(result).front().field=="fixture.inventory_build");
    CHECK(adapter.preflight_calls==1);
    CHECK(adapter.capability_calls==1);
    CHECK(adapter.build_calls==1);
}

TEST_CASE("direct trajectory preflight observes cancellation before capabilities and builds") {
    std::stop_source cancellation;
    CancellingTrajectoryPreflightAdapter adapter{cancellation};
    const auto result=build_hybrid_path_program(adapter,example_system(),
        example_request(),example_path(),{"hybrid-problem"},{16,64,1024},
        {},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
    CHECK(adapter.capability_calls==0);
    CHECK(adapter.build_calls==0);
}

TEST_CASE("hybrid branch execution retains path and solver provenance on rejection") {
    auto built=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    const std::array<HybridPathProgram,1> programs{std::get<HybridPathProgram>(std::move(built))};
    const auto report=execute_hybrid_path_programs(programs,lp_provider(),convex_provider(),{});
    REQUIRE(report.branches.size()==1);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(report.branches[0].path==example_path());
    CHECK(report.branches[0].termination==Termination::operation_rejected);
    REQUIRE(report.branches[0].providers.size()==1);
    REQUIRE(report.branches[0].providers[0].actual);
    CHECK(report.branches[0].providers[0].actual->id.value=="reject-lp");
    REQUIRE(report.branches[0].diagnostics.size()==1);
    CHECK(report.branches[0].diagnostics[0].field=="fixture.lp");
}

TEST_CASE("hybrid branch execution records cancellation without invoking a provider") {
    auto built=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    const std::array<HybridPathProgram,1> programs{std::get<HybridPathProgram>(std::move(built))};
    std::stop_source cancellation;
    cancellation.request_stop();
    const ExecutionContext context{{},{cancellation.get_token()},{},{1e-8,1e-8},{},{}};
    const auto report=execute_hybrid_path_programs(programs,lp_provider(),convex_provider(),context);
    REQUIRE(report.branches.size()==1);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(report.branches[0].termination==Termination::cancelled);
    CHECK(report.branches[0].providers.empty());
    CHECK_FALSE(report.branches[0].result.has_value());
}

TEST_CASE("hybrid branch execution records an expired deadline before provider preparation") {
    auto built=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    const std::array<HybridPathProgram,1> programs{std::get<HybridPathProgram>(std::move(built))};
    auto factory_calls=std::make_shared<int>(0);
    const ExecutionContext context{{},{},std::chrono::steady_clock::now()-std::chrono::milliseconds(1),
        {1e-8,1e-8},{},{}};
    const auto report=execute_hybrid_path_programs(programs,lp_provider(nullptr,factory_calls),
        convex_provider(),context);
    REQUIRE(report.branches.size()==1);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(report.branches[0].termination==Termination::resource_limit);
    CHECK(report.branches[0].providers.empty());
    CHECK(*factory_calls==0);
}

TEST_CASE("hybrid branch execution observes cancellation after provider preparation") {
    auto first=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"first-problem"},{16,64,1024});
    auto second=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"stop-during-prepare"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(first));
    REQUIRE(std::holds_alternative<HybridPathProgram>(second));
    const std::array<HybridPathProgram,2> programs{
        std::get<HybridPathProgram>(std::move(first)),std::get<HybridPathProgram>(std::move(second))};
    std::stop_source cancellation;
    auto factory_calls=std::make_shared<int>(0);
    const ExecutionContext context{{},cancellation.get_token(),{},{1e-8,1e-8},{},{}};
    const auto report=execute_hybrid_path_programs(programs,
        lp_provider(&cancellation,factory_calls,{},"stop-during-prepare"),
        convex_provider(),context);
    REQUIRE(report.branches.size()==2);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(report.branches[0].termination==Termination::cancelled);
    CHECK(*factory_calls==0);
    REQUIRE(report.branches[0].providers.size()==1);
    CHECK_FALSE(report.branches[0].result.has_value());
    CHECK(report.branches[0].diagnostics[0].field=="hybrid.portfolio.preflight_interrupted");
    CHECK(report.branches[1].termination==Termination::cancelled);
    CHECK(report.branches[1].diagnostics.empty());
}

TEST_CASE("hybrid branch execution retains a completed solver result and provenance") {
    auto built=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"hybrid-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(built));
    const std::array<HybridPathProgram,1> programs{std::get<HybridPathProgram>(std::move(built))};
    const auto report=execute_hybrid_path_programs(programs,completing_lp_provider(),convex_provider(),{});
    REQUIRE(report.branches.size()==1);
    CHECK(report.all_supplied_branches_completed);
    CHECK(report.branches[0].path==example_path());
    CHECK(report.branches[0].termination==Termination::completed);
    CHECK(report.branches[0].outcome==MathematicalOutcome::undetermined);
    REQUIRE(report.branches[0].result);
    CHECK(report.branches[0].result->raw_diagnostics=="fixture completed");
    REQUIRE(report.branches[0].providers.size()==1);
    REQUIRE(report.branches[0].providers[0].actual);
    CHECK(report.branches[0].providers[0].actual->id.value=="completing-lp");
}

TEST_CASE("hybrid guard entry and exit constrain the pre-reset state") {
    auto system=example_system();
    system.edges[0].guards[0]=interval("guard-3-to-4",3,4);
    const auto relation=model::compose_hybrid_path_relation(system,example_request(),example_path(),
        {16,64,1024});
    REQUIRE(std::holds_alternative<sets::SetData>(relation));
    const auto representation=std::get<sets::SetData>(relation).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    CHECK(satisfies(h,{2,1,3,0,0}));
    CHECK(satisfies(h,{2,2,4,0,0}));
    CHECK_FALSE(satisfies(h,{2,0,2,0,0}));
    CHECK_FALSE(satisfies(h,{2,3,5,0,0}));
}

TEST_CASE("hybrid empty guard produces an explicitly empty branch relation") {
    auto system=example_system();
    system.edges[0].guards[0]=EmptySet{1};
    const auto relation=model::compose_hybrid_path_relation(system,example_request(),example_path(),
        {16,64,1024});
    REQUIRE(std::holds_alternative<sets::SetData>(relation));
    const auto representation=std::get<sets::SetData>(relation).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& h=std::get<sets::HRepresentation>(representation);
    bool contradictory_row=false;
    for(std::size_t i=0;i<h.inequalities.rows();++i) {
        bool zero=true;
        for(std::size_t j=0;j<h.inequalities.cols();++j) zero=zero && h.inequalities(i,j)==0;
        if(zero && h.upper_bounds[i]<0) contradictory_row=true;
    }
    CHECK(contradictory_row);
}

TEST_CASE("hybrid portfolio admits every branch before creating any solver workspace") {
    auto first=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"accepted-problem"},{16,64,1024});
    auto rejected=build_hybrid_path_program(example_system(),example_request(),example_path(),
        {"rejected-problem"},{16,64,1024});
    REQUIRE(std::holds_alternative<HybridPathProgram>(first));
    REQUIRE(std::holds_alternative<HybridPathProgram>(rejected));
    const std::array<HybridPathProgram,2> programs{
        std::get<HybridPathProgram>(std::move(first)),std::get<HybridPathProgram>(std::move(rejected))};
    auto factory_calls=std::make_shared<int>(0);
    const auto report=execute_hybrid_path_programs(programs,
        lp_provider(nullptr,factory_calls,"rejected-problem"),convex_provider(),{});
    REQUIRE(report.branches.size()==2);
    CHECK_FALSE(report.all_supplied_branches_completed);
    CHECK(*factory_calls==0);
    CHECK(report.branches[0].termination==Termination::operation_rejected);
    CHECK(report.branches[0].diagnostics[0].field=="hybrid.portfolio.admission");
    CHECK(report.branches[1].termination==Termination::operation_rejected);
    CHECK(report.branches[1].diagnostics[0].field=="fixture.capability");
}
