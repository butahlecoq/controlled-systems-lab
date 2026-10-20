#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/model/hybrid_system.hpp>
#include <csl/sets/data.hpp>

#include <algorithm>
#include <array>
#include <type_traits>
#include <utility>

using namespace csl::model;

namespace {
using namespace csl;

HybridSystem parallel_edges() {
    return {
        1,
        {{"idle"}, {"active"}},
        {{"start-a", {"idle"}, {"active"}},
         {"start-b", {"idle"}, {"active"}}}
    };
}

std::vector<HybridPath> exhaustive_path_oracle(const HybridSystem& system,
    const HybridModeId& initial, const std::vector<HybridModeId>& terminals) {
    std::vector<HybridPath> prefixes{{{initial},{}}};
    for (std::size_t stage = 0; stage < system.horizon; ++stage) {
        std::vector<HybridPath> next;
        for (const auto& prefix : prefixes) {
            for (const auto& edge : system.edges) {
                if (edge.source != prefix.modes.back()) continue;
                auto extended = prefix;
                extended.edges.push_back(edge.id);
                extended.modes.push_back(edge.target);
                next.push_back(std::move(extended));
            }
        }
        prefixes = std::move(next);
    }
    prefixes.erase(std::remove_if(prefixes.begin(),prefixes.end(),[&](const HybridPath& path) {
        return std::find(terminals.begin(),terminals.end(),path.modes.back()) == terminals.end();
    }),prefixes.end());
    return prefixes;
}

bool literal_relation_contains(const sets::SetData& relation,const Vector& point) {
    const auto representation=relation.representation();
    if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation))
        return std::equal(singleton->point.values().begin(),singleton->point.values().end(),point.begin(),point.end());
    if(const auto* h=std::get_if<sets::HRepresentation>(&representation)) {
        if(point.size()!=h->inequalities.cols() || point.size()!=h->equalities.cols()) return false;
        for(std::size_t i=0;i<h->inequalities.rows();++i) {
            double value=0;
            for(std::size_t j=0;j<h->inequalities.cols();++j) value+=h->inequalities(i,j)*point[j];
            if(value>h->upper_bounds[i]) return false;
        }
        for(std::size_t i=0;i<h->equalities.rows();++i) {
            double value=0;
            for(std::size_t j=0;j<h->equalities.cols();++j) value+=h->equalities(i,j)*point[j];
            if(value!=h->equality_values[i]) return false;
        }
        return true;
    }
    return std::holds_alternative<sets::UniversalRepresentation>(representation);
}

TEST_CASE("framework operation plans preserve ordered duplicate path obligations") {
    const HybridPath path{{{"idle"},{"active"}},{{"start-a"}}};
    const std::array<HybridPath,2> paths{path,path};
    const auto plan=plan_hybrid_operations(paths);

    REQUIRE(plan.size()==16);
    const auto idle=std::optional<HybridModeId>{HybridModeId{"idle"}};
    const auto active=std::optional<HybridModeId>{HybridModeId{"active"}};
    const auto edge=std::optional<HybridEdgeId>{HybridEdgeId{"start-a"}};
    const std::array<HybridPlannedOperation,8> expected{{
        {0,HybridRelationOperationKind::initial_state,0,idle,{}},
        {0,HybridRelationOperationKind::post_state_invariant,0,idle,{}},
        {0,HybridRelationOperationKind::mode_flow,0,idle,{}},
        {0,HybridRelationOperationKind::continuous_control,0,idle,{}},
        {0,HybridRelationOperationKind::pre_reset_invariant,1,idle,{}},
        {0,HybridRelationOperationKind::transition_guard,0,{},edge},
        {0,HybridRelationOperationKind::reset_relation,0,{},edge},
        {0,HybridRelationOperationKind::post_state_invariant,1,active,{}}
    }};
    for(std::size_t i=0;i<expected.size();++i) {
        CHECK(plan[i]==expected[i]);
        auto duplicate=expected[i];
        duplicate.path_index=1;
        CHECK(plan[i+expected.size()]==duplicate);
    }
}

std::pair<bool,std::size_t> equality_consistency_and_rank(const sets::HRepresentation& h) {
    Matrix augmented{h.equalities.rows(),h.equalities.cols()+1,{}};
    augmented.values.reserve(augmented.rows*augmented.cols);
    for(std::size_t i=0;i<h.equalities.rows();++i) {
        for(std::size_t j=0;j<h.equalities.cols();++j)
            augmented.values.push_back(h.equalities(i,j));
        augmented.values.push_back(h.equality_values[i]);
    }
    std::size_t rank=0;
    for(std::size_t column=0;column<h.equalities.cols() && rank<augmented.rows;++column) {
        auto pivot=rank;
        while(pivot<augmented.rows && augmented.values[pivot*augmented.cols+column]==0) ++pivot;
        if(pivot==augmented.rows) continue;
        for(std::size_t j=0;j<augmented.cols;++j)
            std::swap(augmented.values[rank*augmented.cols+j],augmented.values[pivot*augmented.cols+j]);
        const auto divisor=augmented.values[rank*augmented.cols+column];
        for(std::size_t j=column;j<augmented.cols;++j)
            augmented.values[rank*augmented.cols+j]/=divisor;
        for(std::size_t i=rank+1;i<augmented.rows;++i) {
            const auto factor=augmented.values[i*augmented.cols+column];
            for(std::size_t j=column;j<augmented.cols;++j)
                augmented.values[i*augmented.cols+j]-=factor*augmented.values[rank*augmented.cols+j];
        }
        ++rank;
    }
    bool consistent=true;
    for(std::size_t i=0;i<augmented.rows;++i) {
        bool zero_coefficients=true;
        for(std::size_t j=0;j<h.equalities.cols();++j)
            zero_coefficients=zero_coefficients && augmented.values[i*augmented.cols+j]==0;
        if(zero_coefficients && augmented.values[i*augmented.cols+h.equalities.cols()]!=0)
            consistent=false;
    }
    return {consistent,rank};
}

bool literal_set_contains(const AdmissibleSet& set,const Vector& point) {
    return std::visit([&](const auto& value) {
        using T=std::decay_t<decltype(value)>;
        if constexpr(std::is_same_v<T,UniversalSet>) return true;
        else if constexpr(std::is_same_v<T,EmptySet>) return false;
        else if constexpr(std::is_same_v<T,Singleton>) return value.point==point;
        else {
            const auto data=sets::from_handle(value);
            return std::holds_alternative<sets::SetData>(data) &&
                literal_relation_contains(std::get<sets::SetData>(data),point);
        }
    },set);
}

Vector literal_singleton(const SetHandle& handle) {
    const auto data=sets::from_handle(handle);
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    const auto representation=std::get<sets::SetData>(data).representation();
    REQUIRE(std::holds_alternative<sets::SingletonRepresentation>(representation));
    const auto& point=std::get<sets::SingletonRepresentation>(representation).point;
    return {point.values().begin(),point.values().end()};
}

LinearStage stage(std::size_t state, std::size_t control) {
    return {Matrix{state,state,Vector(state*state,0)},
        Matrix{state,control,Vector(state*control,0)},
        Matrix{state,0,{}}, Vector(state,0)};
}

HybridMode mode(std::string id, std::size_t state, std::size_t control, std::size_t horizon) {
    HybridMode result{{std::move(id)},state,control};
    for(std::size_t i=0;i<state;++i) result.state_coordinate_labels.push_back("x"+std::to_string(i));
    for(std::size_t i=0;i<control;++i) result.control_coordinate_labels.push_back("u"+std::to_string(i));
    result.flow = std::vector<LinearStage>(horizon, stage(state,control));
    result.control_sets.assign(horizon, UniversalSet{control});
    result.invariants.assign(horizon+1, UniversalSet{state});
    return result;
}

SetHandle universal_relation(std::string id, std::size_t dimension) {
    auto result = sets::make_universal({SetId{std::move(id)},dimension,{}});
    REQUIRE(std::holds_alternative<sets::SetData>(result));
    return std::get<sets::SetData>(std::move(result)).as_handle();
}

SetHandle singleton_relation(std::string id, Vector point) {
    auto coordinates= numeric::snapshot_vector(point);
    REQUIRE(std::holds_alternative<numeric::VectorView>(coordinates));
    auto result=sets::make_singleton({SetId{std::move(id)},point.size(),{}},
        std::get<numeric::VectorView>(std::move(coordinates)));
    REQUIRE(std::holds_alternative<sets::SetData>(result));
    return std::get<sets::SetData>(std::move(result)).as_handle();
}

SetHandle vertex_set(std::string id, std::size_t dimension) {
    Matrix vertices{1,dimension,Vector(dimension,0)}, rays{0,dimension,{}};
    auto v=numeric::snapshot(vertices), r=numeric::snapshot(rays);
    REQUIRE(std::holds_alternative<numeric::MatrixView>(v));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(r));
    auto data=sets::make_v({SetId{std::move(id)},dimension,{}},
        {std::get<numeric::MatrixView>(std::move(v)),std::get<numeric::MatrixView>(std::move(r))});
    REQUIRE(std::holds_alternative<sets::SetData>(data));
    return std::get<sets::SetData>(std::move(data)).as_handle();
}

std::pair<HybridSystem,HybridRequest> dimension_changing_example() {
    auto source=mode("source",1,1,1), target=mode("target",2,1,1);
    target.state_coordinate_labels={"p","v"};
    HybridSystem system{1,{std::move(source),std::move(target)},
        {{{"switch"},{"source"},{"target"},{UniversalSet{1}},
            {universal_relation("reset-relation",3)}}}};
    HybridRequest request{{{"source"},{3}},{{"target"}},
        {{{"target"},LinearTerminal{{1,0},0},"energy","J"}}};
    return {std::move(system),std::move(request)};
}
}

TEST_CASE("parallel transition edges remain distinct branches") {
    const auto paths = enumerate_hybrid_paths(parallel_edges(), {"idle"}, {{"active"}}, {4,8});

    REQUIRE(std::holds_alternative<std::vector<HybridPath>>(paths));
    const auto& branches = std::get<std::vector<HybridPath>>(paths);
    REQUIRE(branches.size() == 2);
    const std::vector<HybridModeId> terminals{{"active"}};
    const auto reference = exhaustive_path_oracle(parallel_edges(),{"idle"},terminals);
    CHECK(branches == reference);
    CHECK(branches[0].modes == std::vector<HybridModeId>{{"idle"}, {"active"}});
    CHECK(branches[1].modes == std::vector<HybridModeId>{{"idle"}, {"active"}});
    CHECK(branches[0].edges == std::vector<HybridEdgeId>{{"start-a"}});
    CHECK(branches[1].edges == std::vector<HybridEdgeId>{{"start-b"}});
}

TEST_CASE("independent tiny trajectory oracle matches guarded reset branches and ties") {
    auto source=mode("source",1,1,1);
    source.flow=std::vector<LinearStage>{
        {Matrix{1,1,{1}},Matrix{1,1,{1}},Matrix{1,0,{}},Vector{0}}};
    source.control_sets[0]=Singleton{{1}};
    auto target=mode("target",2,0,1);
    const HybridSystem system{1,{source,target},
        {{{"edge-a"},{"source"},{"target"},{Singleton{{1}}},
            {singleton_relation("reset-a",{1,2,0})}},
         {{"edge-b"},{"source"},{"target"},{Singleton{{1}}},
            {singleton_relation("reset-b",{1,2,1})}},
         {{"edge-c"},{"source"},{"target"},{Singleton{{1}}},
            {singleton_relation("reset-c",{1,3,0})}}}};
    const HybridRequest request{{{"source"},{0}},{{"target"}},
        {{{"target"},LinearTerminal{{1,0},0},"cost","u"}}};

    // The oracle enumerates edge sequences independently, then evaluates the
    // one-stage trajectory equations and set membership directly.
    const auto oracle_paths=exhaustive_path_oracle(system,{"source"},{{"target"}});
    REQUIRE(oracle_paths.size()==3);
    std::vector<std::pair<HybridPath,Vector>> oracle_feasible;
    const auto& source_mode=system.modes[0];
    const auto& flow=std::get<std::vector<LinearStage>>(source_mode.flow)[0];
    const double initial=request.initial.state[0];
    const double control=std::get<Singleton>(source_mode.control_sets[0]).point[0];
    const double pre=flow.A.values[0]*initial+flow.B.values[0]*control+flow.offset[0];
    REQUIRE(literal_set_contains(source_mode.invariants[0],{initial}));
    REQUIRE(literal_set_contains(source_mode.invariants[1],{pre}));
    for(const auto& path:oracle_paths) {
        const auto edge=std::find_if(system.edges.begin(),system.edges.end(),[&](const auto& candidate) {
            return candidate.id==path.edges[0];
        });
        REQUIRE(edge!=system.edges.end());
        if(!literal_set_contains(edge->guards[0],{pre})) continue;
        const auto reset=literal_singleton(edge->reset_relations[0]);
        REQUIRE(reset.size()==3);
        if(reset[0]!=pre) continue;
        const Vector terminal{reset[1],reset[2]};
        if(!literal_set_contains(target.invariants[1],terminal)) continue;
        oracle_feasible.push_back({path,{initial,control,pre,terminal[0],terminal[1]}});
    }
    REQUIRE(oracle_feasible.size()==3);
    CHECK(oracle_feasible[0].first.edges==std::vector<HybridEdgeId>{{"edge-a"}});
    CHECK(oracle_feasible[1].first.edges==std::vector<HybridEdgeId>{{"edge-b"}});
    CHECK(oracle_feasible[2].first.edges==std::vector<HybridEdgeId>{{"edge-c"}});
    CHECK(oracle_feasible[0].second[4]!=oracle_feasible[1].second[4]);
    const auto& objective=std::get<LinearTerminal>(request.terminal_objectives[0].objective);
    Vector oracle_objectives;
    for(const auto& branch:oracle_feasible)
        oracle_objectives.push_back(objective.coefficients[0]*branch.second[3]+
            objective.coefficients[1]*branch.second[4]+objective.offset);
    REQUIRE(oracle_objectives==Vector{2,2,3});
    const auto global_oracle_objective=*std::min_element(oracle_objectives.begin(),oracle_objectives.end());
    std::vector<HybridPath> oracle_optimal_paths;
    for(std::size_t i=0;i<oracle_feasible.size();++i)
        if(oracle_objectives[i]==global_oracle_objective)
            oracle_optimal_paths.push_back(oracle_feasible[i].first);
    CHECK(oracle_optimal_paths==std::vector<HybridPath>{
        oracle_feasible[0].first,oracle_feasible[1].first});

    const auto enumerated=enumerate_hybrid_paths(system,{"source"},{{"target"}},{1,4});
    REQUIRE(std::holds_alternative<std::vector<HybridPath>>(enumerated));
    CHECK(std::get<std::vector<HybridPath>>(enumerated)==oracle_paths);
    for(const auto& path:oracle_paths) {
        const auto relation=compose_hybrid_path_relation(system,request,path,{16,64,1024});
        REQUIRE(std::holds_alternative<sets::SetData>(relation));
        const auto& data=std::get<sets::SetData>(relation);
        const auto feasible=std::find_if(oracle_feasible.begin(),oracle_feasible.end(),[&](const auto& item) {
            return item.first==path;
        });
        REQUIRE(feasible!=oracle_feasible.end());
        CHECK(literal_relation_contains(data,feasible->second));
        const auto representation=data.representation();
        REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
        const auto& h=std::get<sets::HRepresentation>(representation);
        CHECK(h.inequalities.rows()==0);
        const auto [consistent,rank]=equality_consistency_and_rank(h);
        CHECK(consistent);
        CHECK(rank==5); // five independent equalities make the expected tuple the whole branch
    }

    auto guard_exit_request=request;
    guard_exit_request.initial.state={2};
    const double exit_pre=flow.A.values[0]*guard_exit_request.initial.state[0]+
        flow.B.values[0]*control+flow.offset[0];
    CHECK(exit_pre==3);
    CHECK_FALSE(literal_set_contains(system.edges[0].guards[0],{exit_pre}));
    const HybridPath first_edge{{{"source"},{"target"}},{{"edge-a"}}};
    const auto guard_exit=compose_hybrid_path_relation(system,guard_exit_request,first_edge,{16,64,1024});
    REQUIRE(std::holds_alternative<sets::SetData>(guard_exit));
    const auto exit_representation=std::get<sets::SetData>(guard_exit).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(exit_representation));
    const auto& exit_h=std::get<sets::HRepresentation>(exit_representation);
    CHECK(exit_h.inequalities.rows()==0);
    CHECK_FALSE(equality_consistency_and_rank(exit_h).first);
}

TEST_CASE("zero-horizon path is the initial terminal mode and has no edge") {
    const HybridSystem model{0, {{"parked"}}, {}};
    const auto paths = enumerate_hybrid_paths(model, {"parked"}, {{"parked"}}, {0,1});

    REQUIRE(std::holds_alternative<std::vector<HybridPath>>(paths));
    const auto& branches = std::get<std::vector<HybridPath>>(paths);
    REQUIRE(branches.size() == 1);
    CHECK(branches[0].modes == std::vector<HybridModeId>{{"parked"}});
    CHECK(branches[0].edges.empty());
}

TEST_CASE("terminal-mode filter removes paths that do not end in the request set") {
    const HybridSystem model{
        1,
        {{"idle"}, {"active"}, {"fault"}},
        {{"start", {"idle"}, {"active"}}, {"fail", {"idle"}, {"fault"}}}
    };
    const auto paths = enumerate_hybrid_paths(model, {"idle"}, {{"active"}}, {4,8});

    REQUIRE(std::holds_alternative<std::vector<HybridPath>>(paths));
    const auto& branches = std::get<std::vector<HybridPath>>(paths);
    REQUIRE(branches.size() == 1);
    CHECK(branches[0].edges == std::vector<HybridEdgeId>{{"start"}});
}

TEST_CASE("path limit is reported instead of returning a truncated branch family") {
    const auto result = enumerate_hybrid_paths(parallel_edges(), {"idle"}, {{"active"}}, {4,1});

    REQUIRE(std::holds_alternative<csl::Diagnostic>(result));
    CHECK(std::get<csl::Diagnostic>(result).code == csl::DiagnosticCode::unsupported);
    CHECK(std::get<csl::Diagnostic>(result).field == "hybrid.paths.limit");
}

TEST_CASE("path enumeration cancellation returns no partial paths") {
    std::stop_source cancellation;
    cancellation.request_stop();
    const auto result=enumerate_hybrid_paths(parallel_edges(),{"idle"},{{"active"}},
        {4,8},cancellation.get_token());
    REQUIRE(std::holds_alternative<csl::OperationStopped>(result));
    CHECK(std::get<csl::OperationStopped>(result).reason==csl::StopReason::cancelled);
}

TEST_CASE("horizon limits reject the request before any path is returned") {
    const auto result = enumerate_hybrid_paths(parallel_edges(), {"idle"}, {{"active"}}, {0,8});

    REQUIRE(std::holds_alternative<csl::Diagnostic>(result));
    CHECK(std::get<csl::Diagnostic>(result).code == csl::DiagnosticCode::unsupported);
    CHECK(std::get<csl::Diagnostic>(result).field == "hybrid.horizon.limit");
}

TEST_CASE("an absent transition edge is forbidden and yields no path") {
    const HybridSystem model{1,{{"idle"},{"fault"}}, {}};
    const auto result = enumerate_hybrid_paths(model,{"idle"},{{"fault"}},{1,8});

    REQUIRE(std::holds_alternative<std::vector<HybridPath>>(result));
    CHECK(std::get<std::vector<HybridPath>>(result).empty());
}

TEST_CASE("profile admission accepts rectangular reset relations between different mode dimensions") {
    auto [system,request] = dimension_changing_example();

    CHECK(check_hybrid_profile(system,request).empty());
}

TEST_CASE("hybrid capability report records request dimensions and complete path count") {
    const auto [system,request]=dimension_changing_example();
    const auto reported=report_hybrid_capability(system,request,{1,4});
    REQUIRE(std::holds_alternative<HybridCapabilityReport>(reported));
    const auto& report=std::get<HybridCapabilityReport>(reported);
    CHECK(report.profile_admitted);
    CHECK(report.path_enumeration_completed);
    CHECK(report.horizon==1);
    CHECK(report.mode_count==2);
    CHECK(report.edge_count==1);
    CHECK(report.maximum_state_dimension==2);
    CHECK(report.maximum_control_dimension==1);
    REQUIRE(report.modes.size()==2);
    CHECK(report.modes[0].mode==HybridModeId{"source"});
    CHECK(report.modes[0].state_dimension==1);
    CHECK(report.modes[0].control_dimension==1);
    REQUIRE(report.complete_allowed_path_count);
    CHECK(*report.complete_allowed_path_count==1);
    CHECK(report.diagnostics.empty());
}

TEST_CASE("hybrid capability report discloses path-limit failure without a partial count") {
    const auto [system,request]=dimension_changing_example();
    const auto reported=report_hybrid_capability(system,request,{1,0});
    REQUIRE(std::holds_alternative<HybridCapabilityReport>(reported));
    const auto& report=std::get<HybridCapabilityReport>(reported);
    CHECK(report.profile_admitted);
    CHECK_FALSE(report.path_enumeration_completed);
    CHECK_FALSE(report.complete_allowed_path_count);
    REQUIRE(report.diagnostics.size()==1);
    CHECK(report.diagnostics[0].field=="hybrid.paths.limit");
}

TEST_CASE("four-mode capability report matches an independent branching graph and relation budget") {
    auto modes=std::vector<HybridMode>{
        mode("start",1,0,2),mode("upper",1,0,2),
        mode("lower",1,0,2),mode("terminal",1,0,2)};
    const auto make_edge=[](std::string id,std::string source,std::string target) {
        return HybridTransitionEdge{{std::move(id)},{std::move(source)},{std::move(target)},
            {UniversalSet{1},UniversalSet{1}},
            {universal_relation("reset-0",2),universal_relation("reset-1",2)}};
    };
    HybridSystem system{2,std::move(modes),{
        make_edge("to-upper","start","upper"),
        make_edge("to-lower","start","lower"),
        make_edge("upper-to-terminal","upper","terminal"),
        make_edge("lower-to-terminal","lower","terminal")}};
    HybridRequest request{{{"start"},{0}},{{"terminal"}},
        {{{"terminal"},LinearTerminal{{1},0},"terminal-state","units"}}};

    const std::vector<HybridPath> expected{
        {{{"start"},{"upper"},{"terminal"}},{{"to-upper"},{"upper-to-terminal"}}},
        {{{"start"},{"lower"},{"terminal"}},{{"to-lower"},{"lower-to-terminal"}}}};
    const auto oracle=exhaustive_path_oracle(system,request.initial.mode,
        request.allowed_terminal_modes);
    CHECK(oracle==expected);

    const auto reported=report_hybrid_capability(system,request,{2,2});
    REQUIRE(std::holds_alternative<HybridCapabilityReport>(reported));
    const auto& profile=std::get<HybridCapabilityReport>(reported);
    CHECK(profile.profile_admitted);
    CHECK(profile.path_enumeration_completed);
    CHECK(profile.mode_count==4);
    CHECK(profile.edge_count==4);
    REQUIRE(profile.complete_allowed_path_count);
    CHECK(*profile.complete_allowed_path_count==2);

    const auto paths=enumerate_hybrid_paths(system,request.initial.mode,
        request.allowed_terminal_modes,{2,2});
    REQUIRE(std::holds_alternative<std::vector<HybridPath>>(paths));
    CHECK(std::get<std::vector<HybridPath>>(paths)==oracle);
    for(const auto& path:oracle) {
        const auto composed=compose_hybrid_path_relation_with_report(system,request,path,{5,3,15});
        REQUIRE(std::holds_alternative<HybridComposedPathRelation>(composed));
        const auto& relation=std::get<HybridComposedPathRelation>(composed);
        CHECK(relation.relation.metadata()->set.dimension==5);
        REQUIRE_FALSE(relation.operations.empty());
        CHECK(relation.operations.back().cumulative_rows==3);
        CHECK(relation.operations.back().cumulative_matrix_elements==15);

        const auto limited=compose_hybrid_path_relation_with_report(system,request,path,{5,2,15});
        REQUIRE(std::holds_alternative<HybridPathCompositionFailureReport>(limited));
        const auto& failure=std::get<HybridPathCompositionFailureReport>(limited);
        REQUIRE(std::holds_alternative<Diagnostic>(failure.failure));
        CHECK(std::get<Diagnostic>(failure.failure).field=="hybrid.relation.rows");
    }
}

TEST_CASE("higher-mode path enumeration reports the exact limit without a partial family") {
    constexpr std::size_t horizon=8;
    std::vector<HybridMode> modes{mode("resource-start",1,0,horizon)};
    std::vector<HybridModeId> previous{{"resource-start"}};
    std::vector<HybridTransitionEdge> edges;
    for(std::size_t stage=1;stage<=horizon;++stage) {
        const std::vector<HybridModeId> current{
            {"resource-"+std::to_string(stage)+"-a"},
            {"resource-"+std::to_string(stage)+"-b"}};
        for(const auto& id:current)
            modes.push_back(mode(id.value,1,0,horizon));
        for(const auto& source:previous) {
            for(const auto& target:current) {
                const auto edge_id="resource-edge-"+std::to_string(edges.size());
                std::vector<AdmissibleSet> guards(horizon,UniversalSet{1});
                std::vector<SetHandle> resets;
                resets.reserve(horizon);
                for(std::size_t step=0;step<horizon;++step)
                    resets.push_back(universal_relation(edge_id+"-reset-"+
                        std::to_string(step),2));
                edges.push_back({{edge_id},source,target,std::move(guards),std::move(resets)});
            }
        }
        previous=current;
    }
    HybridSystem system{horizon,std::move(modes),std::move(edges)};
    HybridRequest request{{{"resource-start"},{0}},previous,
        {{previous[0],LinearTerminal{{1},0},"terminal-state","units"},
         {previous[1],LinearTerminal{{1},0},"terminal-state","units"}}};

    const auto oracle=exhaustive_path_oracle(system,request.initial.mode,
        request.allowed_terminal_modes);
    REQUIRE(oracle.size()==256);
    const auto complete=enumerate_hybrid_paths(system,request.initial.mode,
        request.allowed_terminal_modes,{horizon,256});
    REQUIRE(std::holds_alternative<std::vector<HybridPath>>(complete));
    CHECK(std::get<std::vector<HybridPath>>(complete)==oracle);

    const auto exact_cap=report_hybrid_capability(system,request,{horizon,256});
    REQUIRE(std::holds_alternative<HybridCapabilityReport>(exact_cap));
    const auto& admitted=std::get<HybridCapabilityReport>(exact_cap);
    CHECK(admitted.profile_admitted);
    CHECK(admitted.path_enumeration_completed);
    CHECK(admitted.mode_count==17);
    CHECK(admitted.edge_count==30);
    REQUIRE(admitted.complete_allowed_path_count);
    CHECK(*admitted.complete_allowed_path_count==256);

    const auto below_cap=report_hybrid_capability(system,request,{horizon,255});
    REQUIRE(std::holds_alternative<HybridCapabilityReport>(below_cap));
    const auto& rejected=std::get<HybridCapabilityReport>(below_cap);
    CHECK(rejected.profile_admitted);
    CHECK_FALSE(rejected.path_enumeration_completed);
    CHECK(rejected.mode_count==17);
    CHECK(rejected.edge_count==30);
    CHECK_FALSE(rejected.complete_allowed_path_count.has_value());
    REQUIRE(rejected.diagnostics.size()==1);
    CHECK(rejected.diagnostics.front().field=="hybrid.paths.limit");
}

TEST_CASE("hybrid capability report preserves profile rejection and cancellation") {
    auto [system,request]=dimension_changing_example();
    system.modes[0].control_sets.clear();
    const auto rejected=report_hybrid_capability(system,request,{1,4});
    REQUIRE(std::holds_alternative<HybridCapabilityReport>(rejected));
    CHECK_FALSE(std::get<HybridCapabilityReport>(rejected).profile_admitted);
    CHECK_FALSE(std::get<HybridCapabilityReport>(rejected).path_enumeration_completed);
    CHECK_FALSE(std::get<HybridCapabilityReport>(rejected).diagnostics.empty());

    std::stop_source cancellation;
    cancellation.request_stop();
    const auto stopped=report_hybrid_capability(system,request,{1,4},cancellation.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(stopped));
    CHECK(std::get<OperationStopped>(stopped).reason==StopReason::cancelled);
}

TEST_CASE("profile admission checks source guard and source-plus-target reset dimensions") {
    auto [system,request] = dimension_changing_example();
    system.edges[0].guards[0] = UniversalSet{2};
    system.edges[0].reset_relations[0] = universal_relation("bad-reset",2);

    const auto diagnostics = check_hybrid_profile(system,request);
    CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const Diagnostic& d) {
        return d.field == "hybrid.edge.guard";
    }));
    CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const Diagnostic& d) {
        return d.field == "hybrid.edge.reset";
    }));
}

TEST_CASE("profile admission requires a mode invariant for every state stage") {
    auto [system,request] = dimension_changing_example();
    system.modes[0].invariants.pop_back();

    const auto diagnostics = check_hybrid_profile(system,request);
    CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const Diagnostic& d) {
        return d.field == "hybrid.mode.invariants";
    }));
}

TEST_CASE("profile admission requires coordinate labels for every nonzero mode dimension") {
    auto [system,request]=dimension_changing_example();
    system.modes[0].state_coordinate_labels.clear();

    const auto diagnostics=check_hybrid_profile(system,request);
    CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const Diagnostic& d) {
        return d.field=="hybrid.mode.coordinates";
    }));
    const HybridPath path{{{"source"},{"target"}},{{"switch"}}};
    const auto relation=compose_hybrid_path_relation(system,request,path,{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostic>(relation));
    CHECK(std::get<Diagnostic>(relation).field=="hybrid.mode.coordinates");
}

TEST_CASE("per-mode terminal objectives must compare the same quantity and units") {
    auto [system,request] = dimension_changing_example();
    system.modes.push_back(mode("alternate",1,1,1));
    request.allowed_terminal_modes.push_back({"alternate"});
    request.terminal_objectives.push_back({{"alternate"},LinearTerminal{{1},0},"energy","kJ"});

    const auto diagnostics = check_hybrid_profile(system,request);
    CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const Diagnostic& d) {
        return d.field == "hybrid.terminal_objectives";
    }));
}

TEST_CASE("terminal objective shape is checked against its own terminal mode") {
    auto [system,request] = dimension_changing_example();
    std::get<LinearTerminal>(request.terminal_objectives[0].objective).coefficients = {1};

    const auto diagnostics = check_hybrid_profile(system,request);
    CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const Diagnostic& d) {
        return d.field == "hybrid.terminal_objectives";
    }));
}

TEST_CASE("zero-horizon profile validates its single initial and terminal stage") {
    HybridMode parked = mode("parked",1,0,0);
    HybridSystem system{0,{std::move(parked)},{}};
    HybridRequest request{{{"parked"},{2}},{{"parked"}},
        {{{"parked"},LinearTerminal{{1},0},"energy","J"}}};

    CHECK(check_hybrid_profile(system,request).empty());
}

TEST_CASE("hybrid joint relation retains flow, controls, resets, and mode-local dimensions") {
    auto [system,request]=dimension_changing_example();
    system.modes[0].flow=LinearStage{Matrix{1,1,{1}},Matrix{1,1,{0}},Matrix{1,0,{}},Vector{0}};
    system.modes[0].control_sets[0]=Singleton{{0}};
    system.edges[0].guards[0]=Singleton{{3}};
    system.edges[0].reset_relations[0]=singleton_relation("rectangular-reset",{3,3,2});
    const HybridPath path{{{"source"},{"target"}},{{"switch"}}};
    const auto relation=compose_hybrid_path_relation(system,request,path,{16,64,1024});
    REQUIRE(std::holds_alternative<sets::SetData>(relation));
    const auto& data=std::get<sets::SetData>(relation);
    CHECK(data.metadata()->set.dimension==5);
    CHECK(data.metadata()->coordinate_labels==std::vector<std::string>{
        "post:0:6:source:2:x0","control:0:6:source:2:u0","pre:1:6:source:2:x0",
        "post:1:6:target:1:p","post:1:6:target:1:v"});
    const auto representation=data.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto h=std::get<sets::HRepresentation>(representation);
    CHECK(h.equalities.rows()==7); // initial, control, flow, guard, and rectangular reset witness
    CHECK(h.equalities.cols()==5);
    const Matrix expected_equalities{7,5,{
         1,0,0,0,0,
        -1,0,1,0,0,
         0,1,0,0,0,
         0,0,1,0,0,
         0,0,1,0,0,
         0,0,0,1,0,
         0,0,0,0,1}};
    const Vector expected_rhs{3,0,0,3,3,3,2};
    CHECK(h.equality_values.size()==expected_rhs.size());
    for(std::size_t i=0;i<expected_equalities.rows;++i) {
        CHECK(h.equality_values[i]==expected_rhs[i]);
        for(std::size_t j=0;j<expected_equalities.cols;++j)
            CHECK(h.equalities(i,j)==expected_equalities.values[i*expected_equalities.cols+j]);
    }
    const Vector expected_variables{3,0,3,3,2};
    for(std::size_t i=0;i<h.equalities.rows();++i) {
        double value=0;
        for(std::size_t j=0;j<h.equalities.cols();++j) value+=h.equalities(i,j)*expected_variables[j];
        CHECK(value==h.equality_values[i]);
    }
    Vector altered_variables{4,0,3,3,2};
    bool altered_satisfies=true;
    for(std::size_t i=0;i<expected_equalities.rows;++i) {
        double value=0;
        for(std::size_t j=0;j<expected_equalities.cols;++j)
            value+=expected_equalities.values[i*expected_equalities.cols+j]*altered_variables[j];
        if(value!=expected_rhs[i]) altered_satisfies=false;
    }
    CHECK_FALSE(altered_satisfies);
}

TEST_CASE("hybrid composition report records mode and transition operations with resource use") {
    auto [system,request]=dimension_changing_example();
    const HybridPath path{{{"source"},{"target"}},{{"switch"}}};
    const auto composed=compose_hybrid_path_relation_with_report(system,request,path,{16,64,1024});
    REQUIRE(std::holds_alternative<HybridComposedPathRelation>(composed));
    const auto& report=std::get<HybridComposedPathRelation>(composed);
    CHECK(report.relation.metadata()->set.dimension==5);
    CHECK(report.limits.max_variables==16);
    CHECK(report.limits.max_rows==64);
    REQUIRE(report.operations.size()==8);
    CHECK(report.operations[0].operation==HybridRelationOperationKind::initial_state);
    CHECK(report.operations[0].mode==HybridModeId{"source"});
    CHECK(report.operations[0].rows_added==1);
    CHECK(report.operations[1].operation==HybridRelationOperationKind::post_state_invariant);
    CHECK(report.operations[2].operation==HybridRelationOperationKind::mode_flow);
    CHECK(report.operations[2].mode==HybridModeId{"source"});
    CHECK(report.operations[2].rows_added==1);
    CHECK(report.operations[3].operation==HybridRelationOperationKind::continuous_control);
    CHECK(report.operations[4].operation==HybridRelationOperationKind::pre_reset_invariant);
    CHECK(report.operations[5].operation==HybridRelationOperationKind::transition_guard);
    CHECK(report.operations[5].edge==HybridEdgeId{"switch"});
    CHECK(report.operations[6].operation==HybridRelationOperationKind::reset_relation);
    CHECK(report.operations[6].edge==HybridEdgeId{"switch"});
    CHECK(report.operations[7].operation==HybridRelationOperationKind::post_state_invariant);
    for(const auto& operation:report.operations) {
        CHECK(operation.implementation_id=="csl.model.hybrid.joint-h-composer");
        CHECK(operation.implementation_version=="1");
        CHECK(operation.joint_variables==5);
        CHECK(operation.cumulative_matrix_elements==operation.cumulative_rows*5);
    }
    CHECK(report.operations.back().cumulative_rows==2);
    CHECK(report.operations.back().cumulative_matrix_elements==10);

    const auto limited=compose_hybrid_path_relation_with_report(system,request,path,{16,1,1024});
    REQUIRE(std::holds_alternative<HybridPathCompositionFailureReport>(limited));
    const auto& limit_report=std::get<HybridPathCompositionFailureReport>(limited);
    CHECK(limit_report.limits.max_rows==1);
    const auto* limit_diagnostic=std::get_if<Diagnostic>(&limit_report.failure);
    REQUIRE(limit_diagnostic);
    CHECK(limit_diagnostic->field=="hybrid.relation.rows");
    REQUIRE(limit_report.operations.size()==2);
    CHECK(limit_report.operations.back().cumulative_rows==1);
    std::stop_source cancellation;
    cancellation.request_stop();
    const auto stopped=compose_hybrid_path_relation_with_report(
        system,request,path,{16,64,1024},cancellation.get_token());
    REQUIRE(std::holds_alternative<HybridPathCompositionFailureReport>(stopped));
    const auto& stop_report=std::get<HybridPathCompositionFailureReport>(stopped);
    CHECK(stop_report.limits.max_rows==64);
    CHECK(std::holds_alternative<OperationStopped>(stop_report.failure));
    CHECK(stop_report.operations.empty());
}

TEST_CASE("hybrid joint relation rejects capacity exhaustion without truncation and observes cancellation") {
    auto [system,request]=dimension_changing_example();
    const HybridPath path{{{"source"},{"target"}},{{"switch"}}};
    const auto limited=compose_hybrid_path_relation(system,request,path,{4,64,1024});
    REQUIRE(std::holds_alternative<Diagnostic>(limited));
    CHECK(std::get<Diagnostic>(limited).code==DiagnosticCode::unsupported);
    std::stop_source source; source.request_stop();
    const auto cancelled=compose_hybrid_path_relation(system,request,path,{16,64,1024},source.get_token());
    REQUIRE(std::holds_alternative<OperationStopped>(cancelled));
    CHECK(std::get<OperationStopped>(cancelled).reason==StopReason::cancelled);
}

TEST_CASE("hybrid joint relation rejects V sets during capability preflight") {
    auto [system,request]=dimension_changing_example();
    system.edges[0].guards[0]=vertex_set("v-guard",1);
    const HybridPath path{{{"source"},{"target"}},{{"switch"}}};
    const auto result=compose_hybrid_path_relation(system,request,path,{16,64,1024});
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).code==DiagnosticCode::unsupported);
    CHECK(std::get<Diagnostic>(result).field=="hybrid.guard.representation");
}

TEST_CASE("hybrid relation IDs distinguish colon-delimited edge-ID sequences") {
    HybridSystem system{2,
        {mode("a",1,0,2),mode("b",1,0,2),mode("c",1,0,2)},
        {{{"a:b"},{"a"},{"b"},{UniversalSet{1},UniversalSet{1}},
            {universal_relation("ab-reset",2),universal_relation("ab-reset-2",2)}},
         {{"c"},{"b"},{"c"},{UniversalSet{1},UniversalSet{1}},
            {universal_relation("c-reset",2),universal_relation("c-reset-2",2)}},
         {{"a"},{"a"},{"b"},{UniversalSet{1},UniversalSet{1}},
            {universal_relation("a-reset",2),universal_relation("a-reset-2",2)}},
         {{"b:c"},{"b"},{"c"},{UniversalSet{1},UniversalSet{1}},
            {universal_relation("bc-reset",2),universal_relation("bc-reset-2",2)}}}};
    HybridRequest request{{{"a"},{0}},{{"c"}},{{{"c"},LinearTerminal{{1},0},"energy","J"}}};
    const HybridPath first{{{"a"},{"b"},{"c"}},{{"a:b"},{"c"}}};
    const HybridPath second{{{"a"},{"b"},{"c"}},{{"a"},{"b:c"}}};
    const auto first_relation=compose_hybrid_path_relation(system,request,first,{32,128,4096});
    const auto second_relation=compose_hybrid_path_relation(system,request,second,{32,128,4096});
    REQUIRE(std::holds_alternative<sets::SetData>(first_relation));
    REQUIRE(std::holds_alternative<sets::SetData>(second_relation));
    CHECK(std::get<sets::SetData>(first_relation).metadata()->id !=
          std::get<sets::SetData>(second_relation).metadata()->id);
}

TEST_CASE("hybrid terminal objective is lifted only onto its branch terminal coordinates") {
    auto [system,request]=dimension_changing_example();
    const HybridPath path{{{"source"},{"target"}},{{"switch"}}};
    const auto lifted=lift_hybrid_terminal_objective(system,request,path,{16,64,1024});
    REQUIRE(std::holds_alternative<TerminalObjective>(lifted));
    const auto* linear=std::get_if<LinearTerminal>(&std::get<TerminalObjective>(lifted));
    REQUIRE(linear);
    CHECK(linear->coefficients==Vector{0,0,0,1,0});
    CHECK(linear->offset==0);
}

TEST_CASE("hybrid quadratic and residual objectives lift onto rectangular terminal blocks") {
    auto [system,request]=dimension_changing_example();
    const HybridPath path{{{"source"},{"target"}},{{"switch"}}};
    request.terminal_objectives[0].objective=QuadraticTerminal{
        Matrix{2,2,{1,0,0,2}},Vector{4,5},7};
    const auto quadratic=lift_hybrid_terminal_objective(system,request,path,{16,64,1024});
    REQUIRE(std::holds_alternative<TerminalObjective>(quadratic));
    const auto& q=std::get<QuadraticTerminal>(std::get<TerminalObjective>(quadratic));
    CHECK(q.Q.rows==5);
    CHECK(q.Q.values==Vector{0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0, 0,0,0,1,0, 0,0,0,0,2});
    CHECK(q.linear==Vector{0,0,0,4,5});
    CHECK(q.offset==7);

    request.terminal_objectives[0].objective=ResidualNormTerminal{Matrix{1,2,{1,2}},Vector{0}};
    const auto residual=lift_hybrid_terminal_objective(system,request,path,{16,64,1024});
    REQUIRE(std::holds_alternative<TerminalObjective>(residual));
    const auto& r=std::get<ResidualNormTerminal>(std::get<TerminalObjective>(residual));
    CHECK(r.map.rows==1);
    CHECK(r.map.cols==5);
    CHECK(r.map.values==Vector{0,0,0,1,2});
}
