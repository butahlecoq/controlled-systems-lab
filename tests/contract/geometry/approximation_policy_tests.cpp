#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/geometry/approximation.hpp>
#include <csl/sets/data.hpp>
#include <limits>

using namespace csl;
using namespace csl::geometry::approximation;

namespace {
sets::SetData take(sets::Result<sets::SetData> value) {
    REQUIRE(std::holds_alternative<sets::SetData>(value));
    return std::get<sets::SetData>(std::move(value));
}
SetHandle set(const char* kind, const char* id, const char* coordinate="x") {
    sets::Description description{{id},1,{coordinate}};
    if (std::string(kind)=="empty") return take(sets::make_empty(description)).as_handle();
    if (std::string(kind)=="universal") return take(sets::make_universal(description)).as_handle();
    const Vector point{1.0};
    auto view=numeric::snapshot_vector(point);
    REQUIRE(std::holds_alternative<numeric::VectorView>(view));
    return take(sets::make_singleton(description,std::get<numeric::VectorView>(view))).as_handle();
}
SetHandle point_set(const char* id, double value, const char* coordinate="x") {
    auto point=numeric::snapshot_vector(Vector{value});
    REQUIRE(std::holds_alternative<numeric::VectorView>(point));
    return take(sets::make_singleton({{id},1,{coordinate}},
        std::get<numeric::VectorView>(point))).as_handle();
}
SetHandle two_points(const char* id) {
    const auto vertices=numeric::snapshot(Matrix{2,1,{0.0,1.0}});
    const auto rays=numeric::snapshot(Matrix{0,1,{}});
    REQUIRE(std::holds_alternative<numeric::MatrixView>(vertices));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rays));
    return take(sets::make_v({{id},1,{"x"}},
        {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(rays)})).as_handle();
}
class OpaqueFuturePayload final : public SetPayload {};
SetHandle h_set(const char* id, Vector inequality_rows, Vector upper_bounds,
                Vector equality_rows = {}, Vector equality_values = {},
                const char* coordinate = "x") {
    const auto inequalities = numeric::snapshot(Matrix{inequality_rows.size(),1,std::move(inequality_rows)});
    const auto bounds = numeric::snapshot_vector(upper_bounds);
    const auto equalities = numeric::snapshot(Matrix{equality_rows.size(),1,std::move(equality_rows)});
    const auto values = numeric::snapshot_vector(equality_values);
    REQUIRE(std::holds_alternative<numeric::MatrixView>(inequalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(equalities));
    REQUIRE(std::holds_alternative<numeric::VectorView>(values));
    return take(sets::make_h({{id},1,{coordinate}},
        {std::get<numeric::MatrixView>(inequalities),std::get<numeric::VectorView>(bounds),
         std::get<numeric::MatrixView>(equalities),std::get<numeric::VectorView>(values)})).as_handle();
}
ApproximationRequest request(SetHandle input, SetRelation relation, RepresentationId representation) {
    return {{{"problem/a"},{"approx/a"},{"reference/a"}},std::move(input),std::move(representation),relation,2,Assurance::numerical};
}
class FixedWorkspace final : public SetApproximatorWorkspace {
    OperationResult result_;
public:
    explicit FixedWorkspace(OperationResult result):result_(std::move(result)){}
    SetTransformOutcome approximate(const ApproximationRequest&,const ExecutionContext&) override {return result_;}
};
registry::Registry<registry::ApproximationPort> provider(const ApproximationRequest& request,
    SetHandle output, SetRelation offered, SetRelation returned, EvidenceSupport support=Unestablished{},
    std::optional<GeometryErrorBound> error_bound=std::nullopt,
    std::shared_ptr<std::size_t> factory_creations={}) {
    registry::Registry<registry::ApproximationPort> result;
    GeometryEvidence evidence{{request.identity,{request.input.id}},GeometryClaimScope::set_relation,
        std::move(support),{},std::move(error_bound)};
    OperationResult fixed{std::move(output),returned,std::move(evidence)};
    auto added=result.add({{{"fixture.approximation"},"1"},
        [offered](const ApproximationRequest& query,const registry::Requirements&) -> registry::Capability {
            registry::Output output;output.representation=query.output;output.relation=offered;
            return registry::Offer{output};
        },
        [fixed,factory_creations](const ApproximationRequest&) {
            if(factory_creations)++*factory_creations;
            return std::make_unique<FixedWorkspace>(fixed);
        }});
    REQUIRE_FALSE(added.has_value());
    return result;
}
auto execute(const registry::Registry<registry::ApproximationPort>& registry,const ApproximationRequest& query) {
    return run_registered(registry,{{"fixture.approximation"},std::nullopt},query,ExecutionContext{});
}
}

TEST_CASE("registered inner approximation admits a structurally empty subset") {
    auto input=set("singleton","reference");
    auto output=set("empty","inner");
    auto query=request(input,SetRelation::inner,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::inner,SetRelation::inner);
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    const auto& admitted=std::get<EnclosedApproximation>(outcome);
    CHECK(admitted.result.relation==SetRelation::inner);
    CHECK(admitted.basis==StructuralBasis::empty_subset);
    CHECK(admitted.result.output.id==SetId{"inner"});
    CHECK(admitted.result.evidence.reference.identity==query.identity);
    CHECK(admitted.result.evidence.reference.inputs==std::vector<SetId>{input.id});
}

TEST_CASE("registered outer approximation admits a universal superset") {
    auto input=set("singleton","reference");
    auto output=set("universal","outer");
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::outer,SetRelation::outer);
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    const auto& admitted=std::get<EnclosedApproximation>(outcome);
    CHECK(admitted.result.relation==SetRelation::outer);
    CHECK(admitted.basis==StructuralBasis::universal_superset);
    CHECK(admitted.result.evidence.reference.identity==query.identity);
    CHECK(admitted.result.evidence.reference.inputs==std::vector<SetId>{input.id});
}

TEST_CASE("dropping a native H constraint admits a nontrivial outer enclosure") {
    auto input=h_set("reference",{1.0,-1.0},{2.0,1.0}); // [-1,2]
    auto output=h_set("outer",{-1.0},{1.0}); // [-1,+infinity)
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    query.size_budget=1;
    auto outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    CHECK(std::get<EnclosedApproximation>(outcome).result.output.id==SetId{"outer"});
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::h_constraint_containment);
}

TEST_CASE("adding a native H equality admits a nontrivial inner enclosure") {
    auto input=h_set("reference",{1.0,-1.0},{2.0,1.0}); // [-1,2]
    auto output=h_set("inner",{-1.0,1.0},{1.0,2.0},{1.0},{0.0}); // {0}
    auto query=request(input,SetRelation::inner,output.metadata.representation);
    query.size_budget=3;
    auto outcome=execute(provider(query,output,SetRelation::inner,SetRelation::inner),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    CHECK(std::get<EnclosedApproximation>(outcome).result.output.id==SetId{"inner"});
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::h_constraint_containment);
}

TEST_CASE("different H coefficients or coordinate labels do not prove enclosure") {
    auto input=h_set("reference",{1.0,-1.0},{2.0,1.0});
    auto changed=h_set("changed",{1.0},{3.0}); // Not an authored reference row.
    auto query=request(input,SetRelation::outer,changed.metadata.representation);
    auto outcome=execute(provider(query,changed,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");

    auto relabeled=h_set("relabeled",{1.0},{2.0},{},{},"y");
    query=request(input,SetRelation::outer,relabeled.metadata.representation);
    outcome=execute(provider(query,relabeled,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("dropping an H equality supports only the outer direction") {
    auto input=h_set("reference",{1.0},{2.0},{1.0},{0.0}); // {0}
    auto output=h_set("candidate",{1.0},{2.0}); // (-infinity,2]
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome)); // Dropping equality is a sound outer relation.
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::h_constraint_containment);

    query=request(input,SetRelation::inner,output.metadata.representation);
    outcome=execute(provider(query,output,SetRelation::inner,SetRelation::inner),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("a singleton satisfying every H row is an admitted inner enclosure") {
    auto input=h_set("reference",{1.0,-1.0},{2.0,1.0},{1.0},{0.0});
    auto output=point_set("inner",0.0);
    auto query=request(input,SetRelation::inner,output.metadata.representation);
    query.size_budget=1;
    auto outcome=execute(provider(query,output,SetRelation::inner,SetRelation::inner),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::h_point_containment);

    output=point_set("outside",1.0);
    query=request(input,SetRelation::inner,output.metadata.representation);
    outcome=execute(provider(query,output,SetRelation::inner,SetRelation::inner),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("H rows containing the reference singleton are an admitted outer enclosure") {
    auto input=point_set("reference",1.0);
    auto output=h_set("outer",{1.0,-1.0},{2.0,-1.0});
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::h_point_containment);

    output=h_set("outside",{1.0},{0.0});
    query=request(input,SetRelation::outer,output.metadata.representation);
    outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("H point containment uses exact stored binary64 values and ordered coordinates") {
    auto input=point_set("reference",0.3);
    auto output=h_set("rounded",{0.1},{0.03});
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");

    output=h_set("relabeled",{1.0},{1.0},{},{},"y");
    query=request(input,SetRelation::outer,output.metadata.representation);
    outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("exact H point check survives cancellation beyond floating point range") {
    const double huge=std::numeric_limits<double>::max();
    auto point=numeric::snapshot_vector(Vector{huge,huge});
    auto rows=numeric::snapshot(Matrix{1,2,{huge,-huge}});
    auto bounds=numeric::snapshot_vector(Vector{0.0});
    auto no_rows=numeric::snapshot(Matrix{0,2,{}});
    auto no_values=numeric::snapshot_vector(Vector{});
    REQUIRE(std::holds_alternative<numeric::VectorView>(point));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(rows));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bounds));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(no_rows));
    REQUIRE(std::holds_alternative<numeric::VectorView>(no_values));
    auto input=take(sets::make_singleton({{"reference"},2,{"x","y"}},
        std::get<numeric::VectorView>(point))).as_handle();
    auto output=take(sets::make_h({{"outer"},2,{"x","y"}},
        {std::get<numeric::MatrixView>(rows),std::get<numeric::VectorView>(bounds),
         std::get<numeric::MatrixView>(no_rows),std::get<numeric::VectorView>(no_values)})).as_handle();
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto outcome=execute(provider(query,output,SetRelation::outer,SetRelation::outer),query);
    REQUIRE(std::holds_alternative<EnclosedApproximation>(outcome));
    CHECK(std::get<EnclosedApproximation>(outcome).basis==StructuralBasis::h_point_containment);
}

TEST_CASE("an enclosure cannot change the native coordinate system") {
    auto input=set("singleton","reference","x");
    auto output=set("universal","outer","y");
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::outer,SetRelation::outer);
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("an unproved enclosure is rejected after provider execution") {
    auto input=set("singleton","reference");
    auto output=set("singleton","different");
    auto query=request(input,SetRelation::inner,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::inner,SetRelation::inner,
        SymbolicArgument{"provider assertion","no independent verifier"});
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.inclusion");
}

TEST_CASE("elementary enclosure does not authorize a provider error bound") {
    auto input=set("singleton","reference");
    auto output=set("universal","outer");
    auto query=request(input,SetRelation::outer,output.metadata.representation);
    auto methods=provider(query,output,SetRelation::outer,SetRelation::outer,
        SymbolicArgument{"provider bound assertion","unverified"},
        GeometryErrorBound{{"hausdorff"},0.1,"state units"});
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.error_bound");
}

TEST_CASE("native output cannot exceed the requested size budget") {
    auto input=set("singleton","reference");
    auto output=two_points("candidate");
    auto query=request(input,SetRelation::heuristic,output.metadata.representation);
    query.size_budget=1;
    auto methods=provider(query,output,SetRelation::heuristic,SetRelation::heuristic);
    auto outcome=execute(methods,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.budget");
    query.size_budget=2;
    CHECK(std::holds_alternative<HeuristicApproximation>(execute(methods,query)));
}

TEST_CASE("declared and returned approximation relations cannot downgrade") {
    auto input=set("singleton","reference");
    auto output=set("universal","outer");
    auto query=request(input,SetRelation::inner,output.metadata.representation);
    auto wrong_offer=provider(query,output,SetRelation::outer,SetRelation::outer);
    auto admission=execute(wrong_offer,query);
    REQUIRE(std::holds_alternative<registry::Rejection>(admission));
    CHECK(std::get<registry::Rejection>(admission).diagnostics[0].field=="output.relation");
    auto wrong_result=provider(query,output,SetRelation::inner,SetRelation::outer);
    auto outcome=execute(wrong_result,query);
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics[0].field=="approximation.relation");
}

TEST_CASE("equivalent conversion and heuristic approximation stay separate") {
    auto input=set("singleton","reference");
    auto output=set("singleton","candidate");
    auto equivalent=request(input,SetRelation::equivalent,output.metadata.representation);
    auto creations=std::make_shared<std::size_t>(0);
    auto methods=provider(equivalent,output,SetRelation::outer,SetRelation::outer,
        Unestablished{},std::nullopt,creations);
    auto rejected=execute(methods,equivalent);
    REQUIRE(std::holds_alternative<registry::Rejection>(rejected));
    CHECK(std::get<registry::Rejection>(rejected).diagnostics[0].field=="approximation.direction");
    CHECK(*creations==0);
    auto heuristic=request(input,SetRelation::heuristic,output.metadata.representation);
    methods=provider(heuristic,output,SetRelation::heuristic,SetRelation::heuristic);
    auto outcome=execute(methods,heuristic);
    REQUIRE(std::holds_alternative<HeuristicApproximation>(outcome));
    const auto& admitted=std::get<HeuristicApproximation>(outcome);
    CHECK(admitted.result.output.id==SetId{"candidate"});
    CHECK(admitted.result.relation==SetRelation::heuristic);
    CHECK(admitted.result.evidence.reference.identity==heuristic.identity);
    CHECK(admitted.result.evidence.reference.inputs==std::vector<SetId>{input.id});
}

TEST_CASE("future zonotope and ellipsoid representations get no inferred exact route") {
    const SetHandle ellipsoid{{2,{"test.future.ellipsoid"},SetProperty::yes,
        SetProperty::no,SetProperty::yes},std::make_shared<const OpaqueFuturePayload>(),{"ellipsoid"}};
    const SetHandle zonotope{{2,{"test.future.zonotope"},SetProperty::yes,
        SetProperty::yes,SetProperty::yes},std::make_shared<const OpaqueFuturePayload>(),{"zonotope"}};
    auto equivalent=request(ellipsoid,SetRelation::equivalent,zonotope.metadata.representation);
    auto creations=std::make_shared<std::size_t>(0);
    const auto methods=provider(equivalent,zonotope,SetRelation::outer,SetRelation::outer,
        Unestablished{},std::nullopt,creations);
    const auto outcome=execute(methods,equivalent);
    REQUIRE(std::holds_alternative<registry::Rejection>(outcome));
    CHECK(std::get<registry::Rejection>(outcome).diagnostics.front().field=="approximation.direction");
    CHECK(*creations==0);
}

TEST_CASE("set extrema have directed bounds but no optimizer-family claim") {
    CHECK(objective_bound_side(SetRelation::inner,ObjectiveSense::minimize)==BoundSide::upper);
    CHECK(objective_bound_side(SetRelation::outer,ObjectiveSense::minimize)==BoundSide::lower);
    CHECK(objective_bound_side(SetRelation::inner,ObjectiveSense::maximize)==BoundSide::lower);
    CHECK(objective_bound_side(SetRelation::outer,ObjectiveSense::maximize)==BoundSide::upper);
    CHECK(objective_bound_side(SetRelation::equivalent,ObjectiveSense::maximize)==BoundSide::both);
    CHECK(objective_bound_side(SetRelation::heuristic,ObjectiveSense::minimize)==BoundSide::none);
}
