#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/registry/registry.hpp>
#include <limits>
#include "fixtures.hpp"

using namespace csl;
using namespace csl::registry;
using namespace registry_fixtures;
static_assert(!std::is_default_constructible_v<PreparedPipeline<LPPort>>);
static_assert(!std::is_default_constructible_v<PreparedStrategy>);
static_assert(!std::is_copy_constructible_v<BoundWorkspace<LPPort>>);

TEST_CASE("configuration selects two working bounded LP algorithms") {
    Registry<LPPort> registry;
    REQUIRE_FALSE(registry.add(endpoint_registration()).has_value());
    REQUIRE_FALSE(registry.add(sign_registration()).has_value());
    for (const auto& id : {"endpoint", "sign"}) {
        auto request = interval_lp(3);
        auto result = prepare_pipeline(select(registry, Method{{id}, {}}, request));
        REQUIRE(std::holds_alternative<PreparedPipeline<LPPort>>(result));
        auto plan = std::get<PreparedPipeline<LPPort>>(std::move(result));
        CHECK(plan.provenance()[0].requested.id.value == id);
        REQUIRE(plan.provenance()[0].actual.has_value());
        CHECK(plan.provenance()[0].actual->id.value == id);
        CHECK(plan.provenance()[0].actual->version == (std::string(id) == "endpoint" ? "1.0" : "2.0"));
        auto workspaces = plan.create();
        auto answer = std::get<0>(workspaces)->run(context());
        REQUIRE(std::holds_alternative<ProgramResult>(answer));
        const auto& solved = std::get<ProgramResult>(answer);
        CHECK(solved.primal == std::optional<Vector>{{-1}});
        REQUIRE(solved.objective.upper.has_value());
        CHECK(solved.objective.upper->value == -1);
    }
}

TEST_CASE("negative and zero coefficients and genuinely unsupported LPs") {
    Registry<LPPort> registry;
    registry.add(endpoint_registration()); registry.add(sign_registration());
    for (const auto& id : {"endpoint","sign"}) {
        for (const auto coefficient : {-2.0,0.0}) {
            const auto request = interval_lp(coefficient);
            auto result = prepare_pipeline(select(registry,Method{{id},{}},request));
            REQUIRE(std::holds_alternative<PreparedPipeline<LPPort>>(result));
            auto workers = std::get<PreparedPipeline<LPPort>>(result).create();
            const auto answer = std::get<0>(workers)->run(context());
            REQUIRE(std::holds_alternative<ProgramResult>(answer));
            const auto& solved = std::get<ProgramResult>(answer);
            CHECK(solved.primal == (coefficient < 0 ? std::optional<Vector>{{4}} : std::optional<Vector>{{-1}}));
            CHECK(solved.objective.upper->value == (coefficient < 0 ? -6 : 2));
        }
        auto input = interval_input(3);
        input.variables[0].upper.reset();
        const auto request = publish(input);
        auto result = prepare_pipeline(select(registry,Method{{id},{}},request));
        REQUIRE(std::holds_alternative<Rejection>(result));
        const auto& rejection = std::get<Rejection>(result);
        CHECK(rejection.provenance.actual->id.value == id);
        CHECK(rejection.diagnostics[0].field == "lp.domain");
    }
}

TEST_CASE("bounded LP preflight rejects overflow and rounded unequal endpoint ties before factories") {
    std::array<int,2> factories{};
    Registry<LPPort> registry;
    auto endpoint = endpoint_registration();
    endpoint.factory = [&](const LinearProgram&) { ++factories[0]; return std::make_unique<EndpointWorkspace>(); };
    auto sign = sign_registration();
    sign.factory = [&](const LinearProgram&) { ++factories[1]; return std::make_unique<SignWorkspace>(); };
    registry.add(endpoint); registry.add(sign);
    auto overflow = interval_input(-std::numeric_limits<double>::max());
    overflow.variables[0] = {2,3};
    auto rounded_tie = interval_input(-1); rounded_tie.offset = 1e20;
    auto underflow = interval_input(std::numeric_limits<double>::denorm_min());
    underflow.variables[0] = {0,0.5}; underflow.offset = 0;
    for (const auto& input : {overflow,rounded_tie,underflow}) {
        const auto request = publish(input);
        for (const auto& id : {"endpoint","sign"}) {
            CAPTURE(std::string(id)); CAPTURE(request.objective()[0]); CAPTURE(request.offset());
            auto result = prepare_pipeline(select(registry,Method{{id},{}},request));
            CHECK(std::holds_alternative<Rejection>(result));
            if (!std::holds_alternative<Rejection>(result)) continue;
            const auto& rejection = std::get<Rejection>(result);
            CHECK(rejection.provenance.requested.id.value == id);
            CHECK(rejection.provenance.actual->id.value == id);
            CHECK(rejection.provenance.actual->version == (std::string(id)=="endpoint" ? "1.0" : "2.0"));
            CHECK(rejection.diagnostics[0].code == DiagnosticCode::unsupported);
            CHECK(rejection.diagnostics[0].field == "lp.arithmetic");
            CHECK_FALSE(rejection.diagnostics[0].explanation.empty());
            CHECK(factories == std::array<int,2>{0,0});
        }
    }
}

TEST_CASE("constant objectives and degenerate intervals remain legitimate bounded LP inputs") {
    Registry<LPPort> registry;
    registry.add(endpoint_registration()); registry.add(sign_registration());
    auto constant = interval_input(0); constant.offset = 1e20;
    auto degenerate = interval_input(-1); degenerate.variables[0] = {4,4}; degenerate.offset = 1e20;
    for (const auto& id : {"endpoint","sign"}) {
        for (const auto& input : {constant,degenerate}) {
            const auto request = publish(input);
            auto result = prepare_pipeline(select(registry,Method{{id},{}},request));
            REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
            auto workers = std::get<0>(result).create();
            const auto answer = std::get<ProgramResult>(std::get<0>(workers)->run(context()));
            CHECK(answer.primal == (request.objective()[0] == 0 ? std::optional<Vector>{{-1}} : std::optional<Vector>{{4}}));
            CHECK(answer.objective.upper->value == 1e20);
            CHECK(answer.outcome.value == MathematicalOutcome::optimal);
        }
    }
}

TEST_CASE("snapshots retain full requests after source exit and workspaces mutate independently") {
    auto plan = [] {
        Registry<LPPort> registry;
        registry.add(endpoint_registration());
        auto input = interval_input(3);
        const auto request = publish(input);
        auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request));
        auto prepared = std::get<PreparedPipeline<LPPort>>(std::move(result));
        input.objective[0] = -200;
        input.variables[0] = {100,200};
        return prepared;
    }();
    auto first = plan.create(), second = plan.create();
    auto a = std::get<ProgramResult>(std::get<0>(first)->run(context()));
    auto b = std::get<ProgramResult>(std::get<0>(first)->run(context()));
    auto c = std::get<ProgramResult>(std::get<0>(second)->run(context()));
    CHECK(a.raw_diagnostics == "1"); CHECK(b.raw_diagnostics == "2"); CHECK(c.raw_diagnostics == "1");
    CHECK(b.primal == std::optional<Vector>{{-1}}); CHECK(c.objective.upper->value == -1);
}

TEST_CASE("unsupported requested profiles reject before factories with actual provenance") {
    int factories = 0;
    Registry<LPPort> registry;
    auto entry = endpoint_registration();
    entry.factory = [&](const LinearProgram&) { ++factories; return std::make_unique<EndpointWorkspace>(); };
    registry.add(entry);
    const auto request = interval_lp(3);
    std::vector<std::pair<Requirements,std::string>> cases;
    Requirements scalar; scalar.scalar = Scalar::exact; cases.push_back({scalar,"scalar"});
    Requirements representation; representation.output.representation = {"unsupported"}; cases.push_back({representation,"output.representation"});
    Requirements assurance; assurance.output.assurance = Assurance::validated; cases.push_back({assurance,"output.assurance"});
    Requirements relation; relation.output.relation = SetRelation::equivalent; cases.push_back({relation,"output.relation"});
    Requirements family; family.output.family = FamilyTarget::exact_optimal_relation; cases.push_back({family,"output.family"});
    Requirements basis; basis.basis_diagnostics = true; cases.push_back({basis,"basis"});
    for (const auto& [requirements, field] : cases) {
        auto result = prepare_pipeline(select(registry,Method{{"endpoint"},"1.0"},request,requirements));
        REQUIRE(std::holds_alternative<Rejection>(result));
        const auto& rejection = std::get<Rejection>(result);
        CHECK(rejection.provenance.requested.id.value == "endpoint");
        CHECK(rejection.provenance.actual->id.value == "endpoint");
        CHECK(rejection.provenance.actual->version == "1.0");
        CHECK(rejection.diagnostics[0].field == field);
        CHECK_FALSE(rejection.diagnostics[0].explanation.empty());
        CHECK(factories == 0);
    }
}

TEST_CASE("unknown duplicate and version mismatch retain requested and resolved identities") {
    Registry<LPPort> registry;
    registry.add(endpoint_registration());
    auto duplicate = endpoint_registration(); duplicate.identity.version = "9.0";
    const auto rejected = registry.add(duplicate);
    REQUIRE(rejected.has_value());
    CHECK(rejected->provenance.requested.version == "9.0");
    CHECK(rejected->provenance.actual->version == "1.0");
    const auto request = interval_lp(3);
    auto unknown = prepare_pipeline(select(registry,Method{{"missing"},"7"},request));
    REQUIRE(std::holds_alternative<Rejection>(unknown));
    CHECK_FALSE(std::get<Rejection>(unknown).provenance.actual.has_value());
    CHECK(std::get<Rejection>(unknown).provenance.requested.id.value == "missing");
    auto version = prepare_pipeline(select(registry,Method{{"endpoint"},"2.0"},request));
    REQUIRE(std::holds_alternative<Rejection>(version));
    CHECK(std::get<Rejection>(version).provenance.actual->version == "1.0");
}

TEST_CASE("downstream transition rejects before any workspace exists") {
    int factories = 0;
    Registry<LPPort> registry;
    auto entry = endpoint_registration();
    entry.factory = [&](const LinearProgram&) { ++factories; return std::make_unique<EndpointWorkspace>(); };
    registry.add(entry);
    const auto request = interval_lp(3);
    Output unavailable; unavailable.representation = {"unavailable"};
    auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request),
        select(registry,Method{{"endpoint"},{}},request,{},{{0,unavailable}}));
    REQUIRE(std::holds_alternative<Rejection>(result));
    CHECK(std::get<Rejection>(result).provenance.actual->id.value == "endpoint");
    CHECK(std::get<Rejection>(result).diagnostics[0].field == "transition.representation");
    CHECK(factories == 0);
}

TEST_CASE("registered strategy planners hide tuple types from the configuration-only caller") {
    Registry<LPPort> lp;
    lp.add(endpoint_registration()); lp.add(sign_registration());
    StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add(forward_registration(lp)).has_value());
    REQUIRE_FALSE(strategies.add(forward_registration(lp,"second-forward")).has_value());
    for (const auto& strategy : {"forward","second-forward"}) {
        for (const auto& backend : {"endpoint","sign"}) {
            auto request = strategy_request();
            request.configuration.strategy = {strategy}; request.configuration.lp = {backend};
            auto result = strategies.prepare(request);
            REQUIRE(std::holds_alternative<PreparedStrategy>(result));
            auto plan = std::get<PreparedStrategy>(std::move(result));
            CHECK(plan.provenance()[0].actual->id.value == strategy);
            CHECK(plan.provenance()[1].actual->id.value == backend);
            auto workspace = plan.create();
            auto answer = workspace->run(context());
            REQUIRE(std::holds_alternative<SynthesisResult>(answer));
            const auto& solved = std::get<SynthesisResult>(answer);
            CHECK(solved.incumbents[0].witness.controls == std::vector<Vector>{{-1}});
            CHECK(solved.incumbents[0].witness.original_objective == -1);
            CHECK_FALSE(solved.family.has_value());
        }
    }
}

TEST_CASE("all existing ports execute through typed factories and rejection constructs none") {
    AllPorts ports;
    Requirements invalid; invalid.scalar = Scalar::interval;
    auto rejected = ports.prepare(invalid);
    REQUIRE(std::holds_alternative<Rejection>(rejected));
    CHECK(std::get<Rejection>(rejected).provenance.actual->id.value == "strategy");
    CHECK(std::get<Rejection>(rejected).diagnostics[0].field == "scalar");
    CHECK(ports.factories == std::array<int,7>{0,0,0,0,0,0,0});
    auto result = ports.prepare();
    REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
    auto workers = std::get<0>(result).create();
    CHECK(std::get<ProgramResult>(std::get<0>(workers)->run(context())).objective.upper->value == -1);
    CHECK(std::get<ProgramResult>(std::get<1>(workers)->run(context())).raw_diagnostics == "interval");
    CHECK(std::get<OperationStopped>(std::get<2>(workers)->run(context())).diagnostics == "geometry-request");
    CHECK(std::get<OperationStopped>(std::get<3>(workers)->run(context())).diagnostics == "vertices");
    CHECK(std::get<OperationStopped>(std::get<4>(workers)->run(context())).diagnostics == "17");
    CHECK(std::get<WitnessSelection>(std::get<5>(workers)->run(context())).batch.requested == 3);
    CHECK(std::get<SynthesisResult>(std::get<6>(workers)->run(context())).incumbents[0].witness.original_objective == 2);
    CHECK(ports.factories == std::array<int,7>{1,1,1,1,1,1,1});
}

TEST_CASE("optional basis is executable only when requested") {
    Registry<LPPort> registry;
    auto entry = endpoint_registration();
    entry.basis_factory = [](const LinearProgram&,LPWorkspace&) { return std::make_unique<BasisFixture>(); };
    registry.add(entry);
    Requirements requirements; requirements.basis_diagnostics = true;
    const auto request = interval_lp(3);
    auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request,requirements));
    REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
    auto workers = std::get<0>(result).create();
    REQUIRE(std::get<0>(workers)->basis() != nullptr);
    CHECK(std::get<0>(workers)->basis()->describe_basis() == "fixture basis: column 0");
    CHECK(std::get<ProgramResult>(std::get<0>(workers)->run(context())).primal == std::optional<Vector>{{-1}});
}

TEST_CASE("basis diagnostics observe their own LP workspace after the prepared plan exits") {
    struct StatefulLP final : LPWorkspace {
        int calls{};
        std::shared_ptr<std::vector<std::string>> destruction;
        explicit StatefulLP(std::shared_ptr<std::vector<std::string>> log) : destruction(std::move(log)) {}
        ~StatefulLP() override { destruction->push_back("workspace"); }
        ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext&) override {
            ++calls;
            return ProgramResult{Termination::completed,{p.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},
                {},{},std::to_string(calls)};
        }
    };
    struct BoundBasis final : BasisDiagnostics {
        const StatefulLP& workspace;
        explicit BoundBasis(const StatefulLP& w) : workspace(w) {}
        ~BoundBasis() override { workspace.destruction->push_back("basis@"+std::to_string(workspace.calls)); }
        BasisCapabilities capabilities() const override { return {true,false,false}; }
        BasisSnapshotResult snapshot() const override {
            if(!workspace.last_attempt()) return BasisUnavailable{BasisUnavailableReason::not_solved,"no attempt"};
            return BasisSnapshot{{workspace.last_attempt()->stamp,0},{},{}};
        }
        std::string describe_basis() const override { return "solve "+std::to_string(workspace.calls); }
    };
    struct ConnectBasis {
        std::unique_ptr<BasisDiagnostics> operator()(const LinearProgram&,LPWorkspace& workspace) const {
            return std::make_unique<BoundBasis>(dynamic_cast<const StatefulLP&>(workspace));
        }
    };
    const auto destruction = std::make_shared<std::vector<std::string>>();
    auto workers = [&] {
        Registry<LPPort> registry;
        auto entry = endpoint_registration();
        entry.factory = [destruction](const LinearProgram&) { return std::make_unique<StatefulLP>(destruction); };
        entry.basis_factory = ConnectBasis{};
        registry.add(entry);
        const auto request = interval_lp(3);
        Requirements requirements; requirements.basis_diagnostics = true;
        auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request,requirements));
        REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
        const auto& plan = std::get<0>(result);
        return std::pair{plan.create(),plan.create()};
    }();
    auto& first = std::get<0>(workers.first);
    auto& second = std::get<0>(workers.second);
    REQUIRE(first->basis()); REQUIRE(second->basis());
    CHECK(first->basis()->describe_basis() == "solve 0");
    CHECK(std::get<ProgramResult>(first->run(context())).raw_diagnostics == "1");
    CHECK(first->basis()->describe_basis() == "solve 1");
    CHECK(second->basis()->describe_basis() == "solve 0");
    CHECK(std::get<ProgramResult>(first->run(context())).raw_diagnostics == "2");
    CHECK(first->basis()->describe_basis() == "solve 2");
    first.reset();
    CHECK(*destruction == std::vector<std::string>{"basis@2","workspace"});
    CHECK(std::get<ProgramResult>(second->run(context())).raw_diagnostics == "1");
    CHECK(second->basis()->describe_basis() == "solve 1");
    second.reset();
    CHECK(*destruction == std::vector<std::string>{"basis@2","workspace","basis@1","workspace"});

    destruction->clear();
    Registry<LPPort> throwing_registry;
    auto throwing_entry = endpoint_registration();
    throwing_entry.factory = [destruction](const LinearProgram&) { return std::make_unique<StatefulLP>(destruction); };
    throwing_entry.basis_factory = [](const LinearProgram& request,LPWorkspace& workspace) -> std::unique_ptr<BasisDiagnostics> {
        auto diagnostic = ConnectBasis{}(request,workspace);
        throw std::runtime_error("basis connection failure");
    };
    throwing_registry.add(throwing_entry);
    const auto request = interval_lp(3);
    Requirements requirements; requirements.basis_diagnostics = true;
    auto result = prepare_pipeline(select(throwing_registry,Method{{"endpoint"},{}},request,requirements));
    REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
    CHECK_THROWS_WITH_AS(std::get<0>(result).create(),"basis connection failure",std::runtime_error);
    CHECK(*destruction == std::vector<std::string>{"basis@0","workspace"});
}

TEST_CASE("a null LP factory fails before invoking a basis connection") {
    struct CountConnection {
        int& calls;
        std::unique_ptr<BasisDiagnostics> operator()(const LinearProgram&,LPWorkspace&) const {
            ++calls; return std::make_unique<BasisFixture>();
        }
    };
    int connections = 0;
    Registry<LPPort> registry;
    auto entry = endpoint_registration();
    entry.factory = [](const LinearProgram&) -> std::unique_ptr<LPWorkspace> { return {}; };
    entry.basis_factory = CountConnection{connections};
    registry.add(entry);
    const auto request = interval_lp(3);
    Requirements requirements; requirements.basis_diagnostics = true;
    auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request,requirements));
    REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
    CHECK_THROWS_WITH_AS(std::get<0>(result).create(),"registered factory returned a null workspace",std::logic_error);
    CHECK(connections == 0);
}

TEST_CASE("a custom port extends registry without product dispatch and freezes only after acceptance") {
    const auto snapshots = std::make_shared<int>(0);
    auto plan = [&] {
        Registry<CounterPort> registry;
        int source_configuration = 10;
        const auto configuration = std::make_shared<const int>(source_configuration);
        registry.add({{{"counter"},"3"},[](const CounterRequest&,const Requirements&) -> Capability { return Offer{}; },
            [configuration](const CounterRequest&) { return std::make_unique<CounterFixture>(*configuration); }});
        CounterRequest request{20,snapshots};
        Registry<LPPort> lp; lp.add(endpoint_registration());
        auto input = interval_input(3); input.variables[0].upper.reset();
        const auto unsupported = publish(input);
        auto rejection = prepare_pipeline(select(registry,Method{{"counter"},{}},request),select(lp,Method{{"endpoint"},{}},unsupported));
        REQUIRE(std::holds_alternative<Rejection>(rejection));
        CHECK(std::get<Rejection>(rejection).provenance.actual->id.value == "endpoint");
        CHECK(*snapshots == 0);
        auto result = prepare_pipeline(select(registry,Method{{"counter"},{}},request));
        REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
        source_configuration = 999; request.value = 800;
        CHECK(source_configuration == 999);
        return std::get<0>(std::move(result));
    }();
    CHECK(*snapshots == 1);
    auto first = plan.create(), second = plan.create();
    CHECK(std::get<0>(first)->run(context()) == 31);
    CHECK(std::get<0>(first)->run(context()) == 32);
    CHECK(std::get<0>(second)->run(context()) == 31);
}

TEST_CASE("strategy snapshots copy mutable model aliases and authored objective values") {
    auto plan = [] {
        Registry<StrategyPort> registry;
        registry.add({{{"capture"},"1"},[](const StrategyRequest&,const Requirements&) -> Capability { return Offer{}; },
            [](const StrategyRequest&) { return std::make_unique<StrategyFixture>(); }});
        auto request = strategy_request();
        auto raw = *request.problem.description();
        auto model = std::make_shared<SystemModel>(*raw.model);
        raw.model = model;
        request.problem = std::get<csl::problem::ResolvedProblem>(csl::problem::resolve(raw,{csl::problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
        request.family.objective=request.problem.identity();
        auto result = prepare_pipeline(select(registry,Method{{"capture"},{}},request));
        std::get<LinearStage>(model->dynamics.stages).offset[0] = 999;
        std::get<LinearTerminal>(raw.objective).offset = 888;
        return std::get<0>(std::move(result));
    }();
    auto workers = plan.create();
    const auto solved = std::get<SynthesisResult>(std::get<0>(workers)->run(context()));
    CHECK(solved.incumbents[0].witness.states == std::vector<Vector>{{0},{0}});
    CHECK(solved.incumbents[0].witness.original_objective == 2);
}

TEST_CASE("T-M03 unsupported profiles stay capability rejection rather than infeasibility") {
    Registry<LPPort> lp; lp.add(endpoint_registration());
    StrategyRegistry registry; registry.add(forward_registration(lp));
    auto inverse = forward_registration(lp,"inverse");
    inverse.capabilities = [](const StrategyRequest& r,const Requirements& requirements) -> Capability {
        return check_nominal_profile(*r.problem.description(),true,requirements.output.assurance);
    };
    registry.add(inverse);
    auto request = strategy_request();
    REQUIRE(check_model_shape(request.problem.description()->model->dynamics,1).empty());
    auto forward = registry.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(forward));
    CHECK(std::get<SynthesisResult>(std::get<PreparedStrategy>(forward).create()->run(context())).incumbents[0].witness.original_objective == -1);
    std::vector<std::pair<StrategyRequest,std::string>> cases;
    auto modified = request; modified.configuration.strategy = {"inverse"}; cases.push_back({modified,"dynamics.inverse"});
    auto add_case=[&](const Problem& raw,const char* field) {
        auto resolution=csl::problem::resolve(raw,{csl::problem::UncertaintyStructure::stage_product_uncoupled,{},{}});
        if (auto* diagnostic=std::get_if<Diagnostic>(&resolution)) {
            CHECK((diagnostic->code==DiagnosticCode::unsupported || diagnostic->code==DiagnosticCode::invalid_input));
            CHECK_FALSE(diagnostic->field.empty());
            return;
        }
        auto input=request;
        input.problem=std::get<csl::problem::ResolvedProblem>(std::move(resolution));
        input.family.objective=input.problem.identity();
        cases.push_back({std::move(input),field});
    };
    auto raw=*request.problem.description(); raw.controls = FiniteDomain{1,{{0},{1}}}; add_case(raw,"controls");
    raw=*request.problem.description(); raw.controls = MixedDomain{ContinuousDomain{{UniversalSet{0}}},FiniteDomain{1,{{0}}}}; add_case(raw,"controls");
    raw=*request.problem.description(); raw.information = InformationPattern::feedback; add_case(raw,"information");
    raw=*request.problem.description(); raw.temporal = TemporalConstraints{{1,1,{0,1},{0},{1}},{{0,1}}}; add_case(raw,"temporal");
    raw=*request.problem.description(); auto continuous = std::make_shared<SystemModel>(*raw.model);
    continuous->dynamics.time_domain = TimeDomain::continuous; raw.model = continuous; add_case(raw,"time_domain");
    raw=*request.problem.description(); raw.objective = ResidualNormTerminal{{1,1,{1}},{0}}; add_case(raw,"objective");
    raw=*request.problem.description(); raw.controls = ContinuousDomain{{SetHandle{{1,{"poly"},SetProperty::unknown,SetProperty::yes,SetProperty::unknown},{},{"unknown"}}}}; add_case(raw,"controls");
    for (const auto& [input,field] : cases) {
        auto result = registry.prepare(input);
        REQUIRE(std::holds_alternative<Rejection>(result));
        const auto& rejection = std::get<Rejection>(result);
        CHECK(rejection.provenance.actual->id.value == input.configuration.strategy.value);
        CHECK(rejection.provenance.actual->version == "fixture-1");
        CHECK(rejection.diagnostics[0].field == field);
        CHECK(rejection.diagnostics[0].code == DiagnosticCode::unsupported);
    }
}

TEST_CASE("exact family target and equivalent relation cannot establish completeness") {
    Registry<LPPort> registry;
    auto entry = endpoint_registration();
    entry.capabilities = [](const LinearProgram&,const Requirements&) -> Capability {
        Output output; output.family = FamilyTarget::exact_optimal_relation;
        output.relation = SetRelation::equivalent; output.completeness = Completeness::unestablished;
        return Offer{output};
    };
    registry.add(entry);
    Requirements requirements; requirements.output.family = FamilyTarget::exact_optimal_relation;
    requirements.output.relation = SetRelation::equivalent; requirements.output.completeness = Completeness::established;
    const auto request = interval_lp(3);
    auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request,requirements));
    REQUIRE(std::holds_alternative<Rejection>(result));
    CHECK(std::get<Rejection>(result).provenance.actual->version == "1.0");
    CHECK(std::get<Rejection>(result).diagnostics[0].field == "output.completeness");
}

TEST_CASE("a required unavailable hull execution rejects while unused hull selection stays optional") {
    Registry<LPPort> lp; lp.add(endpoint_registration());
    StrategyRegistry strategies;
    strategies.add(forward_registration(lp));
    auto hull = forward_registration(lp,"needs-hull");
    hull.planner = [](const StrategyRequest& r,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
        return Rejection{{"hull",{r.configuration.hull,{}},{}},
            {{DiagnosticCode::unsupported,"hull","no executable hull port exists in revision 1.1"}}};
    };
    strategies.add(hull);
    auto request = strategy_request();
    auto accepted = strategies.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(accepted));
    CHECK(std::get<SynthesisResult>(std::get<PreparedStrategy>(accepted).create()->run(context())).incumbents[0].witness.original_objective == -1);
    request.configuration.strategy = {"needs-hull"};
    auto rejected = strategies.prepare(request);
    REQUIRE(std::holds_alternative<Rejection>(rejected));
    CHECK(std::get<Rejection>(rejected).provenance.port == "hull");
    CHECK(std::get<Rejection>(rejected).provenance.requested.id.value == "unused-hull");
    CHECK_FALSE(std::get<Rejection>(rejected).provenance.actual.has_value());
    CHECK(std::get<Rejection>(rejected).diagnostics[0].field == "hull");
}

TEST_CASE("workspace creation failure cleans every earlier unique workspace") {
    struct Tracked final : CounterWorkspace {
        int& alive;
        explicit Tracked(int& count) : alive(count) { ++alive; }
        ~Tracked() override { --alive; }
        int evaluate(const CounterRequest& r) override { return r.value; }
    };
    int alive = 0, attempted = 0, observed_alive = 0;
    Registry<CounterPort> registry;
    auto capability = [](const CounterRequest&,const Requirements&) -> Capability { return Offer{}; };
    registry.add({{{"first"},"1"},capability,[&](const CounterRequest&) { return std::make_unique<Tracked>(alive); }});
    registry.add({{{"throws"},"1"},capability,[&](const CounterRequest&) -> std::unique_ptr<CounterWorkspace> {
        ++attempted; observed_alive = alive; throw std::runtime_error("factory failure");
    }});
    const CounterRequest request{7,std::make_shared<int>(0)};
    auto result = prepare_pipeline(select(registry,Method{{"first"},{}},request),select(registry,Method{{"throws"},{}},request));
    REQUIRE_FALSE(std::holds_alternative<Rejection>(result));
    CHECK_THROWS_WITH_AS(std::get<0>(result).create(),"factory failure",std::runtime_error);
    CHECK(attempted == 1); CHECK(observed_alive == 1); CHECK(alive == 0);
}

TEST_CASE("empty diagnostic rejection cannot lose an actionable reason") {
    Registry<LPPort> registry;
    auto entry = endpoint_registration();
    entry.capabilities = [](const LinearProgram&,const Requirements&) -> Capability { return Diagnostics{}; };
    registry.add(entry);
    const auto request = interval_lp(3);
    auto result = prepare_pipeline(select(registry,Method{{"endpoint"},{}},request));
    REQUIRE(std::holds_alternative<Rejection>(result));
    CHECK_FALSE(std::get<Rejection>(result).diagnostics.empty());
}

TEST_CASE("all-port factory counts stay zero across capability and registration rejection classes") {
    AllPorts ports;
    std::vector<std::pair<Requirements,std::string>> cases;
    Requirements r; r.output.representation = {"unavailable"}; cases.push_back({r,"output.representation"});
    r = {}; r.scalar = Scalar::binary32; cases.push_back({r,"scalar"});
    r = {}; r.output.assurance = Assurance::validated; cases.push_back({r,"output.assurance"});
    r = {}; r.output.relation = SetRelation::inner; cases.push_back({r,"output.relation"});
    r = {}; r.output.family = FamilyTarget::exact_optimal_relation; cases.push_back({r,"output.family"});
    r = {}; r.output.completeness = Completeness::established; cases.push_back({r,"output.completeness"});
    r = {}; r.basis_diagnostics = true; cases.push_back({r,"basis"});
    for (const auto& [requirements,field] : cases) {
        auto result = ports.prepare(requirements);
        REQUIRE(std::holds_alternative<Rejection>(result));
        CHECK(std::get<Rejection>(result).provenance.actual->id.value == "strategy");
        CHECK(std::get<Rejection>(result).diagnostics[0].field == field);
        CHECK(ports.factories == std::array<int,7>{0,0,0,0,0,0,0});
    }
    auto raw=*ports.strategy_request_value.problem.description();
    raw.objective = ResidualNormTerminal{{1,1,{1}},{0}};
    ports.strategy_request_value.problem=std::get<csl::problem::ResolvedProblem>(csl::problem::resolve(raw,{csl::problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    ports.strategy_request_value.family.objective=ports.strategy_request_value.problem.identity();
    auto objective = ports.prepare();
    REQUIRE(std::holds_alternative<Rejection>(objective));
    CHECK(std::get<Rejection>(objective).diagnostics[0].field == "objective");
    ports.strategy_request_value = strategy_request();
    auto unknown = ports.prepare({},{{"unknown"},{}});
    REQUIRE(std::holds_alternative<Rejection>(unknown));
    CHECK_FALSE(std::get<Rejection>(unknown).provenance.actual.has_value());
    auto duplicate = ports.lp.add(endpoint_registration());
    REQUIRE(duplicate.has_value()); CHECK(duplicate->provenance.actual->id.value == "endpoint");
    Output mismatch; mismatch.relation = SetRelation::outer;
    auto transition = ports.prepare({},{{"endpoint"},{}},{{3,mismatch}});
    REQUIRE(std::holds_alternative<Rejection>(transition));
    CHECK(std::get<Rejection>(transition).diagnostics[0].field == "transition.relation");
    CHECK(ports.factories == std::array<int,7>{0,0,0,0,0,0,0});
}

TEST_CASE("runtime strategy extension adds a different typed dependency tuple without changing the caller") {
    struct CustomStrategy final : SynthesisWorkspace {
        std::unique_ptr<BoundWorkspace<CounterPort>> counter;
        explicit CustomStrategy(std::unique_ptr<BoundWorkspace<CounterPort>> w) : counter(std::move(w)) {}
        SynthesisResult solve(const csl::problem::ResolvedProblem& p,const FamilyRequest&,const ExecutionContext& c) override {
            const auto id=p.identity();
            SynthesisResult result{Termination::resource_limit,{id,MathematicalOutcome::undetermined,Unestablished{},{}},{},{},
                {{{id,{}, {},static_cast<double>(counter->run(c))},
                    {id,SymbolicArgument{"fixture", "counter sample"}}}}, {}};
            result.stop=ScopedOperationStopped{{StopReason::resource_limit,"counter fixture"},
                RequestProvenance{{"fixture/custom"},"strategy",{"custom-strategy"},std::string{"7"},
                    ModuleId{"custom-strategy"},std::string{"7"}},{false,false,1,false}};
            return result;
        }
    };
    auto prepared = [] {
        Registry<LPPort> lp; lp.add(endpoint_registration());
        Registry<CounterPort> custom;
        custom.add({{{"counter"},"3"},[](const CounterRequest&,const Requirements&) -> Capability { return Offer{}; },
            [](const CounterRequest&) { return std::make_unique<CounterFixture>(10); }});
        const auto operand = std::make_shared<const CounterRequest>(CounterRequest{20,std::make_shared<int>(0)});
        StrategyRegistry strategies; strategies.add(forward_registration(lp));
        strategies.add({{{"custom-strategy"},"7"},[](const StrategyRequest&,const Requirements&) -> Capability { return Offer{}; },
            [&custom,operand](const StrategyRequest&,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
                auto checked = check_pipeline(select(custom,Method{{"counter"},{}},*operand));
                if (auto* rejected = std::get_if<Rejection>(&checked)) return *rejected;
                return compose_strategy(std::get<0>(std::move(checked)),[operand](auto workers,const StrategyRequest&,const Requirements&) {
                    (void)operand; // Keeps the borrowed operand alive through deferred snapshot.
                    return std::make_unique<CustomStrategy>(std::move(std::get<0>(workers)));
                });
            }});
        std::vector<PreparedStrategy> result;
        for (const auto& id : {"forward","custom-strategy"}) {
            auto request = strategy_request(); request.configuration.strategy = {id};
            auto plan = strategies.prepare(request);
            REQUIRE(std::holds_alternative<PreparedStrategy>(plan));
            request.configuration.strategy = {"mutated"};
            request.family.profile = "mutated after snapshot";
            result.push_back(std::get<PreparedStrategy>(std::move(plan)));
        }
        return result;
    }();
    const std::array<double,2> expected{-1,31};
    for (std::size_t i=0;i<prepared.size();++i) {
        auto workspace = prepared[i].create();
        const auto answer = std::get<SynthesisResult>(workspace->run(context()));
        CHECK(answer.incumbents[0].witness.original_objective == expected[i]);
    }
    CHECK(prepared[1].provenance()[1].actual->id.value == "counter");
    CHECK(prepared[1].provenance()[1].actual->version == "3");
}

TEST_CASE("preflight never copies a factory numeric configuration before a downstream rejection") {
    struct Configuration {
        std::shared_ptr<int> copies;
        Vector values{10};
        explicit Configuration(std::shared_ptr<int> count) : copies(std::move(count)) {}
        Configuration(const Configuration& other) : copies(other.copies), values(other.values) { ++*copies; }
    };
    auto copies = std::make_shared<int>(0);
    const Configuration configuration{copies};
    Registry<CounterPort> registry;
    registry.add({{{"counter"},"1"},[](const CounterRequest&,const Requirements&) -> Capability { return Offer{}; },
        [configuration](const CounterRequest&) { return std::make_unique<CounterFixture>(static_cast<int>(configuration.values[0])); }});
    *copies = 0;
    const CounterRequest request{20,std::make_shared<int>(0)};
    auto rejected = prepare_pipeline(select(registry,Method{{"counter"},{}},request),
        select(registry,Method{{"missing"},{}},request));
    REQUIRE(std::holds_alternative<Rejection>(rejected));
    CHECK(std::get<Rejection>(rejected).provenance.requested.id.value == "missing");
    CHECK(*copies == 0);
}

TEST_CASE("erased strategy retains the complete immutable requested output profile") {
    Registry<LPPort> lp; lp.add(endpoint_registration());
    StrategyRegistry registry;
    auto entry = forward_registration(lp);
    entry.capabilities = [](const StrategyRequest&,const Requirements&) -> Capability {
        Output output; output.family = FamilyTarget::partial_relation;
        output.completeness = Completeness::unestablished;
        return Offer{output};
    };
    registry.add(entry);
    auto request = strategy_request();
    request.family.target=FamilyTarget::partial_relation;
    Requirements requirements;
    requirements.output.family = FamilyTarget::partial_relation;
    requirements.output.completeness = Completeness::unestablished;
    auto result = registry.prepare(request,requirements);
    REQUIRE(std::holds_alternative<PreparedStrategy>(result));
    requirements.output.family = FamilyTarget::exact_optimal_relation;
    requirements.output.completeness = Completeness::established;
    const auto& retained = std::get<PreparedStrategy>(result).requirements();
    CHECK(retained.output.family == FamilyTarget::partial_relation);
    CHECK(retained.output.completeness == Completeness::unestablished);
}

TEST_CASE("runtime builder observes retained requirements and request after every source exits") {
    class ProfileFixture final : public SynthesisWorkspace {
        std::unique_ptr<BoundWorkspace<LPPort>> dependency_;
        std::vector<std::string> configuration_;
    public:
        ProfileFixture(std::unique_ptr<BoundWorkspace<LPPort>> dependency,const StrategyRequest& request,const Requirements& requirements)
            : dependency_(std::move(dependency)), configuration_{
                requirements.output.family == FamilyTarget::partial_relation &&
                requirements.output.completeness == Completeness::unestablished ? "partial/unestablished" : "lost profile",
                std::get<LinearTerminal>(request.problem.description()->objective).offset == 2 ? "original request" : "lost request"} {}
        SynthesisResult solve(const csl::problem::ResolvedProblem& p,const FamilyRequest&,const ExecutionContext&) override {
            SynthesisResult result{Termination::resource_limit,
                {p.identity(),MathematicalOutcome::undetermined,Unestablished{},configuration_},{},{},{},{}};
            result.stop=ScopedOperationStopped{{StopReason::resource_limit,"profile fixture"},
                RequestProvenance{{"fixture/profile"},"strategy",{"profile"},std::string{"1"},
                    ModuleId{"profile"},std::string{"1"}}, {}};
            return result;
        }
    };
    auto prepared = [] {
        Registry<LPPort> lp; lp.add(endpoint_registration());
        const auto operand = std::make_shared<const LinearProgram>(interval_lp(3));
        StrategyRegistry registry;
        registry.add({{{"profile"},"1"},[](const StrategyRequest&,const Requirements&) -> Capability {
            Output output; output.family = FamilyTarget::partial_relation; output.completeness = Completeness::unestablished;
            return Offer{output};
        },[&lp,operand](const StrategyRequest&,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
            auto checked = check_pipeline(select(lp,Method{{"endpoint"},{}},*operand));
            if (auto* rejected = std::get_if<Rejection>(&checked)) return *rejected;
            return compose_strategy(std::get<0>(std::move(checked)),[operand](auto workers,const StrategyRequest& request,const Requirements& requirements) {
                (void)operand;
                return std::make_unique<ProfileFixture>(std::move(std::get<0>(workers)),request,requirements);
            });
        }});
        auto request = strategy_request(); request.configuration.strategy = {"profile"};
        request.family.target=FamilyTarget::partial_relation;
        Requirements requirements; requirements.output.family = FamilyTarget::partial_relation;
        requirements.output.completeness = Completeness::unestablished;
        auto result = registry.prepare(request,requirements);
        REQUIRE(std::holds_alternative<PreparedStrategy>(result));
        requirements.output.family = FamilyTarget::exact_optimal_relation;
        requirements.output.completeness = Completeness::established;
        request.family.profile = "mutated after snapshot";
        return std::get<PreparedStrategy>(std::move(result));
    }();
    const auto answer = std::get<SynthesisResult>(prepared.create()->run(context()));
    CHECK(answer.outcome.assumptions == std::vector<std::string>{"partial/unestablished","original request"});
}

TEST_CASE("public strategy outcome keeps candidate, partial, rejection and retained evidence distinct") {
    class Synthetic final : public SynthesisWorkspace {
    public:
        SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest& request,
            const ExecutionContext&) override {
            const auto id=problem.identity();
            const ClaimEvidence support{id,SymbolicArgument{"synthetic fixture assertion","literal fixture only"}};
            FamilyIdentity identity{id,request,problem.constraints().coordinates(),{"synthetic"},"1",{}};
            const JointRelation relation{identity.coordinates,request.representation,std::make_shared<const JointRelationPayload>()};
            SynthesisResult result{Termination::completed,
                {id,MathematicalOutcome::undetermined,Unestablished{},{}},{},{},
                {{{id,{{0},{1}},{{1}},5},support}}, {}};
            if (request.profile=="late-provider-rejection" || request.profile=="malformed-provider-rejection" ||
                request.profile=="malformed-lineage-rejection") {
                result.termination=Termination::operation_rejected;
                result.stop=ScopedRequestRejection{
                    RequestProvenance{{"generated/lp/7"},"lp",{"endpoint"},std::string{"1.0"},
                        ModuleId{"endpoint"},std::string{"1.0"}},
                    {{DiagnosticCode::unsupported,"lp.generated","provider rejected generated request"}},
                    {{{"transform/4"},{"input/set"},{"output/set"},{"converter"},"2"}},
                    {false,false,1,false}};
                if (request.profile=="malformed-lineage-rejection") {
                    auto& lineage=std::get<ScopedRequestRejection>(result.stop).completed_lineage;
                    lineage.push_back({{"transform/5"},{"output/set"},{"final/set"},{"projector"},"3"});
                    lineage.push_back({{"transform/4"},{"other/input"},{"other/output"},{"converter"},"2"});
                }
                if (request.profile=="malformed-provider-rejection") {
                    auto wrong=identity;wrong.strategy={"other-strategy"};
                    result.family=std::get<OptimalFamily>(FamilyPublisher::publish(wrong,CandidateFamily{
                        relation,HeuristicRelationEvidence{"synthetic"},Unestablished{}}));
                }
                return result;
            }
            if (request.profile=="user-cancel" || request.profile=="deadline") {
                const auto reason=request.profile=="deadline"?StopReason::deadline_expired:StopReason::cancelled;
                result.termination=Termination::cancelled;
                result.spans.push_back({0,{},ModuleId{"synthetic"},0,1});
                result.stop=ScopedOperationStopped{{reason,"synthetic stop"},
                    RequestProvenance{{"generated/step/3"},"strategy",{"synthetic"},std::string{"1"},
                        ModuleId{"synthetic"},std::string{"1"}}, {false,false,1,false}};
                return result;
            }
            if (request.target==FamilyTarget::candidate_relaxation) {
                if (request.profile=="outcome-identity-mismatch") result.outcome.subject={"other-problem"};
                auto candidate_identity=identity;
                if (request.profile=="candidate-identity-mismatch") candidate_identity.strategy={"other-strategy"};
                auto published=FamilyPublisher::publish(candidate_identity,CandidateFamily{relation,
                    HeuristicRelationEvidence{"synthetic"},WitnessFeasibilityEvidence{result.incumbents[0].witness,support}});
                result.family=std::get<OptimalFamily>(std::move(published));
            } else if (request.target==FamilyTarget::partial_relation) {
                auto refused=FamilyPublisher::publish(identity,PartialOptimalFamily{relation,{support,{}},
                    {support,"literal subset proof"},{"one supported witness"}});
                result.termination=Termination::contract_rejected;
                result.stop=ContractValidationFailure{std::get<Diagnostics>(std::move(refused)),
                    {false,false,1,false},{}};
            } else {
                result.outcome={id,MathematicalOutcome::optimal,support.support,{}};
                if (request.profile=="lineage-mismatch")
                    identity.lineage.push_back({{"generated/transform/1"},{"input/set"},
                        {"output/set"},{"converter"},"2"});
                auto refused=FamilyPublisher::publish(identity,CompleteOptimalFamily{relation,{support,{}},
                    {FamilyIdentity{id,request,problem.constraints().coordinates(),{"synthetic"},"1",{}},
                        NumericalCoverageEvidence{"unreviewed",request.numerical,{"fixture"},""}},
                    Assurance::numerical});
                result.termination=Termination::contract_rejected;
                result.stop=ContractValidationFailure{std::get<Diagnostics>(std::move(refused)),
                    {false,false,1,false},{}};
            }
            return result;
        }
    };
    StrategyRegistry registry;
    REQUIRE_FALSE(registry.add({{{"synthetic"},"1"},
        [](const StrategyRequest& request,const Requirements&) -> Capability {
            Output output;output.family=request.family.target;return Offer{output};
        },[](const StrategyRequest&,const Requirements&) -> std::variant<StrategyPlan,Rejection> {
            return compose_strategy(std::get<CheckedPipeline<>>(check_pipeline()),
                [](auto,const StrategyRequest&,const Requirements&) {return std::make_unique<Synthetic>();});
        }}));
    for (const auto target:{FamilyTarget::candidate_relaxation,FamilyTarget::partial_relation,
        FamilyTarget::exact_optimal_relation}) {
        auto request=strategy_request();request.configuration.strategy={"synthetic"};request.family.target=target;
        Requirements requirements;requirements.output.family=target;
        auto preparation=registry.prepare(request,requirements);
        REQUIRE(std::holds_alternative<PreparedStrategy>(preparation));
        auto answer=std::get<PreparedStrategy>(std::move(preparation)).create()->run(context());
        REQUIRE(std::holds_alternative<SynthesisResult>(answer));
        const auto& result=std::get<SynthesisResult>(answer);
        REQUIRE(result.incumbents.size()==1);
        CHECK(result.incumbents[0].witness.original_objective==5);
        CHECK(result.incumbents[0].feasibility.problem==request.problem.identity());
        if (target!=FamilyTarget::candidate_relaxation) {
            CHECK(result.termination==Termination::contract_rejected);
            CHECK_FALSE(result.family.has_value());
            REQUIRE(std::holds_alternative<ContractValidationFailure>(result.stop));
            CHECK(std::get<ContractValidationFailure>(result.stop).retained.incumbents==1);
            if (target==FamilyTarget::partial_relation) {
                const auto& diagnostics=std::get<ContractValidationFailure>(result.stop).diagnostics;
                CHECK(std::any_of(diagnostics.begin(),diagnostics.end(),[](const auto& value){
                    return value.field=="family.partial.optimality" && value.code==DiagnosticCode::unsupported;
                }));
            }
        } else {
            CHECK(result.termination==Termination::completed);
            REQUIRE(result.family.has_value());
            CHECK(result.family->target()==target);
            CHECK(result.family->identity().request==request.family);
            const auto& candidate=std::get<CandidateFamily>(result.family->outcome());
            CHECK(std::holds_alternative<WitnessFeasibilityEvidence>(candidate.feasibility));
        }
    }
    auto request=strategy_request();request.configuration.strategy={"synthetic"};
    request.family.profile="late-provider-rejection";
    auto preparation=registry.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(preparation));
    const auto answer=std::get<PreparedStrategy>(std::move(preparation)).create()->run(context());
    REQUIRE(std::holds_alternative<SynthesisResult>(answer));
    const auto& result=std::get<SynthesisResult>(answer);
    CHECK(result.termination==Termination::operation_rejected);
    REQUIRE(std::holds_alternative<ScopedRequestRejection>(result.stop));
    const auto& rejection=std::get<ScopedRequestRejection>(result.stop);
    CHECK(rejection.request.request.value=="generated/lp/7");
    CHECK(rejection.request.port=="lp");
    CHECK(rejection.diagnostics[0].field=="lp.generated");
    CHECK(rejection.completed_lineage[0].request.value=="transform/4");
    CHECK(rejection.retained.incumbents==1);
    CHECK(result.incumbents[0].witness.original_objective==5);
    request.family.profile="malformed-lineage-rejection";
    auto malformed_lineage_prepared=registry.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(malformed_lineage_prepared));
    auto malformed_lineage_answer=
        std::get<PreparedStrategy>(std::move(malformed_lineage_prepared)).create()->run(context());
    REQUIRE(std::holds_alternative<SynthesisResult>(malformed_lineage_answer));
    const auto& malformed_lineage=std::get<SynthesisResult>(malformed_lineage_answer);
    CHECK(malformed_lineage.termination==Termination::contract_rejected);
    CHECK(malformed_lineage.incumbents.size()==1);
    CHECK(malformed_lineage.incumbents[0].witness.original_objective==5);
    REQUIRE(std::holds_alternative<ContractValidationFailure>(malformed_lineage.stop));
    const auto& lineage_failure=std::get<ContractValidationFailure>(malformed_lineage.stop);
    CHECK(std::any_of(lineage_failure.diagnostics.begin(),lineage_failure.diagnostics.end(),[](const auto& d){
        return d.field=="result.stop.rejection.lineage" && d.code==DiagnosticCode::invalid_claim;
    }));
    REQUIRE(std::holds_alternative<ScopedRequestRejection>(lineage_failure.source_stop));
    const auto& preserved=std::get<ScopedRequestRejection>(lineage_failure.source_stop);
    CHECK(preserved.request.request.value=="generated/lp/7");
    CHECK(preserved.request.port=="lp");
    CHECK(preserved.request.requested_module.value=="endpoint");
    CHECK(preserved.request.requested_version==std::optional<std::string>{"1.0"});
    CHECK(preserved.request.actual_module==std::optional<ModuleId>{ModuleId{"endpoint"}});
    CHECK(preserved.request.actual_version==std::optional<std::string>{"1.0"});
    REQUIRE(preserved.completed_lineage.size()==3);
    CHECK(preserved.completed_lineage[0].request.value=="transform/4");
    CHECK(preserved.completed_lineage[0].input.value=="input/set");
    CHECK(preserved.completed_lineage[0].output.value=="output/set");
    CHECK(preserved.completed_lineage[0].module.value=="converter");
    CHECK(preserved.completed_lineage[0].version=="2");
    CHECK(preserved.completed_lineage[1].request.value=="transform/5");
    CHECK(preserved.completed_lineage[1].input.value=="output/set");
    CHECK(preserved.completed_lineage[1].output.value=="final/set");
    CHECK(preserved.completed_lineage[1].module.value=="projector");
    CHECK(preserved.completed_lineage[1].version=="3");
    CHECK(preserved.completed_lineage[2].request.value=="transform/4");
    CHECK(preserved.completed_lineage[2].input.value=="other/input");
    CHECK(preserved.completed_lineage[2].output.value=="other/output");
    CHECK(preserved.completed_lineage[2].module.value=="converter");
    CHECK(preserved.completed_lineage[2].version=="2");
    request.family.profile="malformed-provider-rejection";
    auto malformed_provider=registry.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(malformed_provider));
    auto malformed_answer=std::get<PreparedStrategy>(std::move(malformed_provider)).create()->run(context());
    REQUIRE(std::holds_alternative<SynthesisResult>(malformed_answer));
    const auto& malformed_result=std::get<SynthesisResult>(malformed_answer);
    CHECK(malformed_result.termination==Termination::contract_rejected);
    REQUIRE(std::holds_alternative<ContractValidationFailure>(malformed_result.stop));
    const auto& original_stop=std::get<ContractValidationFailure>(malformed_result.stop).source_stop;
    REQUIRE(std::holds_alternative<ScopedRequestRejection>(original_stop));
    CHECK(std::get<ScopedRequestRejection>(original_stop).request.request.value=="generated/lp/7");
    CHECK(std::get<ScopedRequestRejection>(original_stop).completed_lineage[0].request.value=="transform/4");
    CHECK_FALSE(malformed_result.family.has_value());
    request.family.profile="lineage-mismatch";
    request.family.target=FamilyTarget::exact_optimal_relation;
    Requirements exact;exact.output.family=FamilyTarget::exact_optimal_relation;
    auto malformed=registry.prepare(request,exact);
    REQUIRE(std::holds_alternative<PreparedStrategy>(malformed));
    auto mismatch=std::get<PreparedStrategy>(std::move(malformed)).create()->run(context());
    REQUIRE(std::holds_alternative<SynthesisResult>(mismatch));
    const auto& rejected=std::get<SynthesisResult>(mismatch);
    CHECK(rejected.termination==Termination::contract_rejected);
    CHECK_FALSE(rejected.family.has_value());
    const auto& diagnostic=std::get<ContractValidationFailure>(rejected.stop).diagnostics;
    CHECK(std::any_of(diagnostic.begin(),diagnostic.end(),[](const auto& value){
        return value.field=="family.completeness.binding";
    }));
    request.family.target=FamilyTarget::candidate_relaxation;
    request.family.profile="candidate-identity-mismatch";
    auto candidate_prepared=registry.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(candidate_prepared));
    auto candidate_answer=std::get<PreparedStrategy>(std::move(candidate_prepared)).create()->run(context());
    REQUIRE(std::holds_alternative<SynthesisResult>(candidate_answer));
    const auto& candidate_rejected=std::get<SynthesisResult>(candidate_answer);
    CHECK(candidate_rejected.termination==Termination::contract_rejected);
    CHECK_FALSE(candidate_rejected.family.has_value());
    REQUIRE(std::holds_alternative<ContractValidationFailure>(candidate_rejected.stop));
    CHECK(std::get<ContractValidationFailure>(candidate_rejected.stop).retained.incumbents==1);
    CHECK(std::holds_alternative<std::monostate>(std::get<ContractValidationFailure>(candidate_rejected.stop).source_stop));
    request.family.profile="outcome-identity-mismatch";
    auto outcome_prepared=registry.prepare(request);
    REQUIRE(std::holds_alternative<PreparedStrategy>(outcome_prepared));
    auto outcome_answer=std::get<PreparedStrategy>(std::move(outcome_prepared)).create()->run(context());
    REQUIRE(std::holds_alternative<SynthesisResult>(outcome_answer));
    const auto& outcome_rejected=std::get<SynthesisResult>(outcome_answer);
    CHECK(outcome_rejected.termination==Termination::contract_rejected);
    CHECK(outcome_rejected.outcome.subject==request.problem.identity());
    CHECK(outcome_rejected.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(outcome_rejected.family.has_value());
    CHECK(outcome_rejected.family->identity().request==request.family);
    for (const auto& [profile,reason]:{
        std::pair{"user-cancel",StopReason::cancelled},
        std::pair{"deadline",StopReason::deadline_expired}}) {
        request.family.profile=profile;
        auto prepared=registry.prepare(request);
        REQUIRE(std::holds_alternative<PreparedStrategy>(prepared));
        auto stopped=std::get<PreparedStrategy>(std::move(prepared)).create()->run(context());
        REQUIRE(std::holds_alternative<SynthesisResult>(stopped));
        const auto& value=std::get<SynthesisResult>(stopped);
        CHECK(value.termination==Termination::cancelled);
        REQUIRE(std::holds_alternative<ScopedOperationStopped>(value.stop));
        CHECK(std::get<ScopedOperationStopped>(value.stop).stop.reason==reason);
        CHECK(value.incumbents[0].witness.original_objective==5);
        CHECK(value.spans.size()==1);
    }
}
