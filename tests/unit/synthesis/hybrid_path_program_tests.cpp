#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/synthesis/hybrid_path_program.hpp>
#include <csl/sets/data.hpp>
#include <csl/registry/provider.hpp>
#include "hybrid_family_verifier_internal.hpp"
#include <algorithm>
#include <array>
#include <limits>

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
    HybridDirectTrajectoryCapabilities capabilities() const noexcept override { return {true,true,true,Assurance::numerical}; }
    HybridPathProgramResult build_path(const model::HybridSystem&,
        const model::HybridRequest&, const model::HybridPath&, ProblemId,
        model::HybridRelationLimits, optimization::ObjectivePolicy,
        std::stop_token) const override {
        ++calls;
        return Diagnostics{{DiagnosticCode::unsupported,"fixture.hybrid_adapter","fixture rejection"}};
    }
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
    HybridReachabilityCapabilities capabilities() const noexcept override { return {true,Assurance::numerical}; }
    HybridPathReachabilityResult compose_path(const model::HybridSystem&,
        const model::HybridRequest&,const model::HybridPath& path,
        model::HybridRelationLimits limits,std::stop_token) const override {
        ++calls;
        return model::HybridPathCompositionFailureReport{path,limits,{},
            Diagnostic{DiagnosticCode::unsupported,"fixture.reachability","fixture rejection"}};
    }
};

class MisreportingReachabilityAdapter final : public HybridReachabilityAdapter {
public:
    int corruption{};
    HybridReachabilityCapabilities capabilities() const noexcept override { return {true,Assurance::numerical}; }
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
    bool omit_last_branch{};
    bool claim_established_aggregates{};
    bool claim_coverage_only{};
    bool mark_all_branches_refuted{};
    HybridFamilyVerificationCapabilities capabilities() const noexcept override {
        return {true,true,true,Assurance::numerical};
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
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(over_limit));
    CHECK(std::get<HybridFamilyVerificationReport>(over_limit).complete_family_coverage==
        HybridVerificationStatus::unsupported);

    std::vector<HybridPathOptimalFaceCandidate> extra_worse{
        exact_candidate(programs[0],point),exact_candidate(programs[1],point),
        exact_candidate(programs[2],Vector{2,1,3,1,0})};
    const auto suboptimal=verify_hybrid_portfolio_family(verifier,system,request,programs,extra_worse,
        {1,8},{1e-10,1e-10});
    REQUIRE(std::holds_alternative<HybridFamilyVerificationReport>(suboptimal));
    CHECK(std::get<HybridFamilyVerificationReport>(suboptimal).complete_family_coverage==
        HybridVerificationStatus::refuted);
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
