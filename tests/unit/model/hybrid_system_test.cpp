#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/model/hybrid_system.hpp>
#include <csl/sets/data.hpp>

#include <algorithm>
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
    const auto representation=data.representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto h=std::get<sets::HRepresentation>(representation);
    CHECK(h.equalities.rows()==7); // initial, control, flow, guard, and rectangular reset witness
    CHECK(h.equalities.cols()==5);
    const Vector expected_variables{3,0,3,3,2};
    for(std::size_t i=0;i<h.equalities.rows();++i) {
        double value=0;
        for(std::size_t j=0;j<h.equalities.cols();++j) value+=h.equalities(i,j)*expected_variables[j];
        CHECK(value==h.equality_values[i]);
    }
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
