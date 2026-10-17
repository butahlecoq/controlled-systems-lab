#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/reachability/nominal_predecessor.hpp>
#include <csl/geometry/operation_admission.hpp>
#include <iostream>
#include <limits>
#include <stop_token>

using namespace csl;
using namespace csl::registry;
namespace {
template<class T, class... E> T take(std::variant<T,E...> value) {
    if (!std::holds_alternative<T>(value)) std::visit([](const auto& item) {
        if constexpr (requires { item.explanation; }) std::cerr << item.explanation << '\n';
        if constexpr (requires { item.diagnostics.begin()->field; })
            for (const auto& d : item.diagnostics) std::cerr << d.field << ": " << d.explanation << '\n';
    },value);
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
template<class T,class V> T alternative(V value) {
    REQUIRE(std::holds_alternative<T>(value));
    return std::get<T>(std::move(value));
}
sets::SetData h(std::string id,std::size_t n,Matrix a,Vector b,Matrix e,Vector f,
        std::vector<std::string> labels={}) {
    return take(sets::make_h({{std::move(id)},n,std::move(labels)},
        {take(numeric::snapshot(a)),take(numeric::snapshot_vector(b)),
         take(numeric::snapshot(e)),take(numeric::snapshot_vector(f))}));
}
sets::SetData interval(std::string id,double lo,double hi,std::string label={}) {
    return h(std::move(id),1,{2,1,{1,-1}},{hi,-lo},{0,1,{}},{},
        label.empty()?std::vector<std::string>{}:std::vector<std::string>{label});
}
template<class Port> PreparedProvider<Port> provider(Registration<Port> entry,std::string representation) {
    Registry<Port> registry;
    Method method{entry.identity.id,entry.identity.version};
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    Requirements requirements;
    requirements.output.representation={std::move(representation)};
    requirements.output.relation=SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry,method,requirements)));
}
OperationRequest projection(SetHandle input,std::vector<std::size_t> coordinates) {
    return {{{"fixture"},{"projection"},{"projected"}},
        {"csl.geometry.polyhedral-projection"},Projection{std::move(input),std::move(coordinates)},
        SetRelation::equivalent,Assurance::numerical};
}
OperationOutcome project(const OperationRequest& request,geometry::polyhedral::ProjectionOutput output,
        std::optional<std::size_t> limit={}) {
    auto selected=provider(geometry::polyhedral::make_projection_registration({output,limit}),
        output==geometry::polyhedral::ProjectionOutput::h?"csl.polyhedron.h":
        output==geometry::polyhedral::ProjectionOutput::v?"csl.polyhedron.v":"csl.polyhedron.projection");
    auto prepared=take(selected.prepare(request));
    return std::get<0>(prepared.create())->run({});
}
// Independent row evaluation observes membership; it does not compute an
// expected projection or use elimination helpers from production.
bool contains(const SetHandle& handle,Vector point) {
    auto data=take(sets::from_handle(handle));
    auto rep=data.representation();
    if (std::holds_alternative<sets::EmptyRepresentation>(rep)) return false;
    const auto& rows=std::get<sets::HRepresentation>(rep);
    for(std::size_t r=0;r<rows.inequalities.rows();++r) {
        double sum=0;
        for(std::size_t c=0;c<point.size();++c) sum+=rows.inequalities(r,c)*point[c];
        if(sum>rows.upper_bounds[r]) return false;
    }
    for(std::size_t r=0;r<rows.equalities.rows();++r) {
        double sum=0;
        for(std::size_t c=0;c<point.size();++c) sum+=rows.equalities(r,c)*point[c];
        if(sum!=rows.equality_values[r]) return false;
    }
    return true;
}
reachability::NominalPredecessorRequest predecessor(SetHandle x,SetHandle u,SetHandle s,
        Matrix a,Matrix b,Vector offset) {
    return {{{"integrator-fixture"},{"predecessor"},{"ideal-predecessor"}},
        std::move(x),std::move(u),std::move(s),std::move(a),std::move(b),std::move(offset)};
}
reachability::NominalPredecessorResult run(const reachability::NominalPredecessorRequest& request) {
    auto selected=provider(geometry::polyhedral::make_projection_registration(),"csl.polyhedron.h");
    return take(take(reachability::prepare_nominal_predecessor(request,selected)).run({}));
}
}

TEST_CASE("integrator predecessor includes existential controls and clips X") {
    // x+=x+u+1, u in [-1,1], target [2,3] => x in [0,3]; X=[-5,2.5].
    auto request=predecessor(interval("X",-5,2.5,"x").as_handle(),
        interval("U",-1,1,"u").as_handle(),interval("S",2,3,"x").as_handle(),
        {1,1,{1}},{1,1,{1}},{1});
    auto result=run(request);
    CHECK(contains(result.result.output,{0}));
    CHECK(contains(result.result.output,{1.5}));
    CHECK(contains(result.result.output,{2.5}));
    CHECK_FALSE(contains(result.result.output,{-0.125}));
    CHECK_FALSE(contains(result.result.output,{2.625}));
    CHECK(result.result.evidence.reference.identity==request.identity);
    CHECK(result.result.evidence.reference.inputs==std::vector<SetId>{{"X"},{"U"},{"S"}});
    CHECK(take(sets::from_handle(result.result.output)).metadata()->coordinate_labels==std::vector<std::string>{"x"});
}

TEST_CASE("singular A keeps its unconstrained state direction and target equality") {
    // x+=(x0+u, 0), S={(2,0)}, u in [-1,1] => 1<=x0<=3; x1 is free.
    auto x=take(sets::make_universal({{"X"},2,{"x0","x1"}}));
    auto s=h("S",2,{0,2,{}},{},{2,2,{1,0,0,1}},{2,0},{"x0","x1"});
    auto result=run(predecessor(x.as_handle(),interval("U",-1,1).as_handle(),s.as_handle(),
        {2,2,{1,0,0,0}},{2,1,{1,0}},{0,0}));
    CHECK(contains(result.result.output,{1,-1000}));
    CHECK(contains(result.result.output,{3,1000}));
    CHECK_FALSE(contains(result.result.output,{0.5,0}));
    CHECK_FALSE(contains(result.result.output,{3.5,0}));
}

TEST_CASE("unreachable target remains empty after singular predecessor projection") {
    auto x=take(sets::make_universal({{"X"},2,{}}));
    auto s=h("S",2,{0,2,{}},{},{1,2,{0,1}},{1});
    auto result=run(predecessor(x.as_handle(),interval("U",-1,1).as_handle(),s.as_handle(),
        {2,2,{1,0,0,0}},{2,1,{1,0}},{0,0}));
    const auto representation=take(sets::from_handle(result.result.output)).representation();
    const auto* rows=std::get_if<sets::HRepresentation>(&representation);
    REQUIRE(rows);
    bool contradiction=false;
    for(std::size_t row=0;row<rows->inequalities.rows();++row) {
        bool zero=true;
        for(std::size_t column=0;column<rows->inequalities.cols();++column)
            zero=zero && rows->inequalities(row,column)==0;
        contradiction=contradiction || (zero && rows->upper_bounds[row]<0);
    }
    CHECK(contradiction); // No physical state satisfies 0 <= a negative bound.
    CHECK_FALSE(contains(result.result.output,{0,0}));
    CHECK_FALSE(contains(result.result.output,{100,-100}));
}

TEST_CASE("H projection preserves surviving equalities and coordinate ordering") {
    // z=2x, x+y=3, 0<=y<=1; ordered [z,x] gives 4<=z<=6 and z=2x.
    auto joint=h("joint",3,{2,3,{0,1,0,0,-1,0}},{1,0},
        {2,3,{-2,0,1,1,1,0}},{0,3},{"x","y","z"});
    auto request=projection(joint.as_handle(),{2,0});
    auto result=take(project(request,geometry::polyhedral::ProjectionOutput::h));
    CHECK(contains(result.output,{4,2}));
    CHECK(contains(result.output,{6,3}));
    CHECK_FALSE(contains(result.output,{4,3}));
    CHECK_FALSE(contains(result.output,{7,3.5}));
    auto data=take(sets::from_handle(result.output));
    auto rep=data.representation();
    CHECK(std::get<sets::HRepresentation>(rep).equalities.rows()==1);
    CHECK(data.metadata()->coordinate_labels==std::vector<std::string>{"z","x"});
    CHECK(check_geometry_evidence(result.evidence,request).empty());
}

TEST_CASE("projection of the unit-square slice x+y=1 is the exact interval [0,1]") {
    auto slice=h("unit-square-diagonal",2,
        {4,2,{1,0,-1,0,0,1,0,-1}},{1,0,1,0},
        {1,2,{1,1}},{1});
    auto result=take(project(projection(slice.as_handle(),{0}),
        geometry::polyhedral::ProjectionOutput::h));
    // Rational parameterization (x,y)=(t,1-t), 0<=t<=1.
    CHECK(contains(result.output,{0}));
    CHECK(contains(result.output,{0.5}));
    CHECK(contains(result.output,{1}));
    CHECK_FALSE(contains(result.output,{-0.25}));
    CHECK_FALSE(contains(result.output,{1.25}));
    const auto representation=take(sets::from_handle(result.output)).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& projected=std::get<sets::HRepresentation>(representation);
    CHECK(projected.equalities.rows()==0);
    REQUIRE(projected.inequalities.rows()>=2);
    bool has_lower=false;
    bool has_upper=false;
    for (std::size_t row=0;row<projected.inequalities.rows();++row) {
        const auto coefficient=projected.inequalities(row,0);
        const auto bound=projected.upper_bounds[row];
        // Duplicate rows are allowed; every row must be one of the exact
        // endpoint inequalities defining [0,1].
        const bool lower=coefficient==-1.0 && bound==0.0;
        const bool upper=coefficient==1.0 && bound==1.0;
        CHECK((lower || upper));
        has_lower=has_lower || lower;
        has_upper=has_upper || upper;
    }
    CHECK(has_lower);
    CHECK(has_upper);
}

TEST_CASE("projection of the rational unit-square triangle is the exact interval [0,1]") {
    // The triangle has vertices (0,0), (1,0), and (0,1). Its x projection is [0,1].
    auto triangle=h("unit-square-lower-triangle",2,
        {5,2,{1,0,-1,0,0,1,0,-1,1,1}},{1,0,1,0,1},
        {0,2,{}},{});
    const auto request=projection(triangle.as_handle(),{0});
    const auto result=take(project(request,geometry::polyhedral::ProjectionOutput::h));
    CHECK(contains(result.output,{0}));
    CHECK(contains(result.output,{0.5}));
    CHECK(contains(result.output,{1}));
    CHECK_FALSE(contains(result.output,{-0.25}));
    CHECK_FALSE(contains(result.output,{1.25}));
    const auto representation=take(sets::from_handle(result.output)).representation();
    REQUIRE(std::holds_alternative<sets::HRepresentation>(representation));
    const auto& projected=std::get<sets::HRepresentation>(representation);
    CHECK(projected.equalities.rows()==0);
    REQUIRE(projected.inequalities.rows()>=2);
    bool has_lower=false;
    bool has_upper=false;
    for(std::size_t row=0;row<projected.inequalities.rows();++row) {
        const double coefficient=projected.inequalities(row,0);
        const double bound=projected.upper_bounds[row];
        const bool lower=coefficient==-1.0 && bound==0.0;
        const bool upper=coefficient==1.0 && bound==1.0;
        CHECK((lower || upper));
        has_lower=has_lower || lower;
        has_upper=has_upper || upper;
    }
    CHECK(has_lower);
    CHECK(has_upper);
    CHECK(check_geometry_evidence(result.evidence,request).empty());
}

TEST_CASE("V projection preserves rays including directions annihilated by selection") {
    auto joint=take(sets::make_v({{"V"},2,{"x","y"}},
        {take(numeric::snapshot(Matrix{1,2,{2,3}})),take(numeric::snapshot(Matrix{2,2,{1,0,0,-1}}))}));
    auto result=take(project(projection(joint.as_handle(),{1}),geometry::polyhedral::ProjectionOutput::v));
    auto data=take(sets::from_handle(result.output));
    auto rep=data.representation();
    const auto& v=std::get<sets::VRepresentation>(rep);
    REQUIRE(v.vertices.rows()==1);
    REQUIRE(v.rays.rows()==2);
    CHECK(v.vertices(0,0)==3);
    CHECK(v.rays(0,0)==0);
    CHECK(v.rays(1,0)==-1);
}

TEST_CASE("lazy projection owns its source and materializes only a supported representation") {
    SetHandle lazy;
    {
        auto joint=h("joint",2,{3,2,{1,1,-1,0,0,-1}},{3,0,0},{0,2,{}},{},{"x","y"});
        lazy=take(project(projection(joint.as_handle(),{0}),geometry::polyhedral::ProjectionOutput::lazy)).output;
    }
    CHECK(lazy.metadata.representation.value=="csl.polyhedron.projection");
    auto selected=provider(geometry::polyhedral::make_projection_materializer(),"csl.polyhedron.h");
    ConversionRequest request{{{"fixture"},{"materialize"},{"ideal-materialized"}},lazy,{"csl.polyhedron.h"},Assurance::numerical};
    auto prepared=take(selected.prepare(request));
    auto result=take(std::get<0>(prepared.create())->run({}));
    CHECK(contains(result.output,{0}));
    CHECK(contains(result.output,{3}));
    CHECK_FALSE(contains(result.output,{3.125}));
    CHECK(check_geometry_evidence(result.evidence,request).empty());
    request.output={"csl.polyhedron.v"};
    CHECK(std::holds_alternative<Rejection>(selected.prepare(request)));
}

TEST_CASE("projection fails explicitly at caller row limit without publishing a set") {
    auto joint=h("joint",2,{4,2,{1,1,-1,1,1,-1,-1,-1}},{2,2,2,2},{0,2,{}},{});
    auto result=project(projection(joint.as_handle(),{0}),geometry::polyhedral::ProjectionOutput::h,3);
    CHECK(std::holds_alternative<Unsupported>(result));
}

TEST_CASE("zero-control predecessor preserves a lower-dimensional equality set") {
    // x+=(2*x0,x1), no controls, S={x0=4}; predecessor x0=2, x1 arbitrary.
    auto x=take(sets::make_universal({{"X"},2,{}}));
    auto u=take(sets::make_universal({{"U"},0,{}}));
    auto s=h("S",2,{0,2,{}},{},{1,2,{1,0}},{4});
    auto result=run(predecessor(x.as_handle(),u.as_handle(),s.as_handle(),
        {2,2,{2,0,0,1}},{2,0,{}},{0,0}));
    CHECK(contains(result.result.output,{2,-100}));
    CHECK_FALSE(contains(result.result.output,{1,0}));
    auto data=take(sets::from_handle(result.result.output));
    auto rep=data.representation();
    CHECK(std::get<sets::HRepresentation>(rep).equalities.rows()==1);
    CHECK(std::holds_alternative<Unestablished>(result.result.evidence.support));
    CHECK_FALSE(result.result.evidence.error_bound.has_value());
}

TEST_CASE("projection onto R0 distinguishes nonempty and empty existential fibers") {
    auto feasible=interval("nonempty",2,3);
    auto impossible=interval("empty",3,2);
    auto yes=take(project(projection(feasible.as_handle(),{}),geometry::polyhedral::ProjectionOutput::h));
    auto no=take(project(projection(impossible.as_handle(),{}),geometry::polyhedral::ProjectionOutput::h));
    CHECK(contains(yes.output,{}));
    CHECK_FALSE(contains(no.output,{}));
    CHECK(yes.output.metadata.dimension==0);
    CHECK(no.output.metadata.dimension==0);
}

TEST_CASE("one-sided eliminated variable does not introduce a bound on remaining coordinates") {
    // exists y: x+y<=1 for every real x, since y has no lower bound.
    auto joint=h("joint",2,{1,2,{1,1}},{1},{0,2,{}},{});
    auto result=take(project(projection(joint.as_handle(),{0}),geometry::polyhedral::ProjectionOutput::h));
    CHECK(contains(result.output,{-1e100}));
    CHECK(contains(result.output,{1e100}));
}

TEST_CASE("zero A and offset can make the entire state set feasible") {
    auto request=predecessor(interval("X",-5,7).as_handle(),
        interval("U",-1,1).as_handle(),interval("S",1,2).as_handle(),
        {1,1,{0}},{1,1,{0}},{1.5});
    auto result=run(request);
    CHECK(contains(result.result.output,{-5}));
    CHECK(contains(result.result.output,{7}));
    CHECK_FALSE(contains(result.result.output,{-5.125}));
    CHECK_FALSE(contains(result.result.output,{7.125}));
}

TEST_CASE("predecessor preparation freezes authored dynamics and operands") {
    auto request=predecessor(interval("X",-10,10).as_handle(),
        interval("U",-1,1).as_handle(),interval("S",2,3).as_handle(),
        {1,1,{1}},{1,1,{1}},{0});
    auto selected=provider(geometry::polyhedral::make_projection_registration(),"csl.polyhedron.h");
    auto prepared=take(reachability::prepare_nominal_predecessor(request,selected));
    request.A.values[0]=0;
    request.offset[0]=100;
    request.states=interval("replacement",0,0).as_handle();
    auto first=take(prepared.run({}));
    auto second=take(prepared.run({}));
    CHECK(contains(first.result.output,{1}));
    CHECK(contains(second.result.output,{4}));
    CHECK_FALSE(contains(first.result.output,{0.875}));
    CHECK_FALSE(contains(second.result.output,{4.125}));
    CHECK(first.result.evidence.reference.inputs==std::vector<SetId>{{"X"},{"U"},{"S"}});
    CHECK(first.projection_provider.actual_module==std::optional<ModuleId>{{"csl.geometry.polyhedral-projection"}});
    CHECK(first.projection_provider.request==first.projection_request.request);
}

TEST_CASE("nested lazy projections retain ultimate coordinates and creation lineage") {
    auto joint=h("source",3,{0,3,{}},{},{1,3,{1,2,3}},{6},{"x","y","z"});
    auto first=take(project(projection(joint.as_handle(),{2,0}),geometry::polyhedral::ProjectionOutput::lazy));
    auto request=projection(first.output,{1});
    request.identity.request={"second-projection"};
    request.identity.ideal_output={"second-output"};
    auto second=take(project(request,geometry::polyhedral::ProjectionOutput::lazy));
    auto description=take(geometry::polyhedral::inspect_lazy_projection(second.output));
    CHECK(description.source.id==SetId{"source"});
    CHECK(description.coordinates==std::vector<std::size_t>{0});
    CHECK(description.coordinate_labels==std::vector<std::string>{"x"});
    REQUIRE(description.lineage.size()==1);
    CHECK(description.lineage[0].reference.identity.request==RequestId{"projection"});
    CHECK(description.creation_evidence.reference.identity==request.identity);
    auto selected=provider(geometry::polyhedral::make_projection_materializer(),"csl.polyhedron.h");
    ConversionRequest query{{{"fixture"},{"materialize-nested"},{"nested-output"}},second.output,{"csl.polyhedron.h"},Assurance::numerical};
    auto result=take(std::get<0>(take(selected.prepare(query)).create())->run({}));
    CHECK(contains(result.output,{-100}));
    CHECK(contains(result.output,{100}));
}

TEST_CASE("admission rejects invalid indices envelopes assurance and missing representation capability") {
    auto joint=interval("X",-1,1,"x");
    auto selected=provider(geometry::polyhedral::make_projection_registration(),"csl.polyhedron.h");
    CHECK(std::holds_alternative<Rejection>(selected.prepare(projection(joint.as_handle(),{0,0}))));
    CHECK(std::holds_alternative<Rejection>(selected.prepare(projection(joint.as_handle(),{1}))));
    auto request=projection(joint.as_handle(),{0});
    request.assurance=Assurance::validated;
    CHECK(std::holds_alternative<Rejection>(selected.prepare(request)));
    request=projection(joint.as_handle(),{0});
    std::get<Projection>(request.operation).input.id={"forged"};
    CHECK(std::holds_alternative<Rejection>(selected.prepare(request)));
    auto lazy=take(project(projection(joint.as_handle(),{0}),geometry::polyhedral::ProjectionOutput::lazy)).output;
    lazy.metadata.dimension=2;
    CHECK(std::holds_alternative<Diagnostics>(geometry::polyhedral::inspect_lazy_projection(lazy)));
}

TEST_CASE("predecessor rejects a provider before creating any incompatible workspace") {
    auto entry=geometry::polyhedral::make_projection_registration({geometry::polyhedral::ProjectionOutput::v,{}});
    auto creations=std::make_shared<int>(0);
    auto create=entry.factory;
    entry.factory=[creations,create](const OperationRequest& query) {++*creations;return create(query);};
    auto selected=provider(std::move(entry),"csl.polyhedron.v");
    auto request=predecessor(interval("X",-2,2).as_handle(),interval("U",-1,1).as_handle(),
        interval("S",0,1).as_handle(),{1,1,{1}},{1,1,{1}},{0});
    CHECK(std::holds_alternative<Rejection>(reachability::prepare_nominal_predecessor(request,selected)));
    CHECK(*creations==0);
    request.A.values.clear();
    CHECK(std::holds_alternative<Diagnostics>(reachability::prepare_nominal_predecessor(request,selected)));
    CHECK(*creations==0);
}

TEST_CASE("unavailable geometry operation rejects before creating a projection workspace") {
    auto entry=geometry::polyhedral::make_projection_registration();
    auto creations=std::make_shared<int>(0);
    auto create=entry.factory;
    entry.factory=[creations,create](const OperationRequest& request) {
        ++*creations;
        return create(request);
    };
    auto selected=provider(std::move(entry),"csl.polyhedron.h");
    const auto left=interval("left",-1,1).as_handle();
    const auto right=interval("right",0,2).as_handle();
    const OperationRequest request{{{"test03"},{"intersection-request"},{"intersection-reference"}},
        {"csl.geometry.polyhedral-projection"},Intersection{left,right},
        SetRelation::equivalent,Assurance::numerical};

    const auto admission=selected.prepare(request);
    const auto* rejection=std::get_if<Rejection>(&admission);
    REQUIRE(rejection);
    REQUIRE(rejection->diagnostics.size()==1);
    CHECK(rejection->diagnostics.front().code==DiagnosticCode::unsupported);
    CHECK(rejection->diagnostics.front().field=="projection.operation");
    CHECK(rejection->provenance.requested.id.value=="csl.geometry.polyhedral-projection");
    REQUIRE(rejection->provenance.actual);
    CHECK(rejection->provenance.actual->id.value=="csl.geometry.polyhedral-projection");
    CHECK(*creations==0);
}

TEST_CASE("geometry admission binds an unsupported operation to each complete request") {
    auto entry=geometry::polyhedral::make_projection_registration();
    auto creations=std::make_shared<int>(0);
    auto create=entry.factory;
    entry.factory=[creations,create](const OperationRequest& request) {
        ++*creations;
        return create(request);
    };
    auto conditional=provider(entry,"csl.polyhedron.h");
    Registry<GeometryPort> registry;
    REQUIRE_FALSE(registry.add(std::move(entry)).has_value());
    Requirements requirements;
    requirements.output.representation={"csl.polyhedron.h"};
    requirements.output.relation=SetRelation::equivalent;
    const auto left=interval("left",-1,1).as_handle();
    const auto right=interval("right",0,2).as_handle();
    for(const auto& [request_id,operands]:{
            std::pair{"intersection-a",std::array{left,right}},
            std::pair{"intersection-b",std::array{right,left}}}) {
        const OperationRequest request{{{"test03"},{request_id},{"intersection-reference"}},
            {"csl.geometry.polyhedral-projection"},Intersection{operands[0],operands[1]},
            SetRelation::equivalent,Assurance::numerical};
        const auto check=[&](const auto& admission) {
            const auto* rejected=std::get_if<geometry::GeometryAdmissionRejection>(&admission);
            REQUIRE(rejected);
            CHECK(rejected->reference.identity.problem==ProblemId{"test03"});
            CHECK(rejected->reference.identity.request==RequestId{request_id});
            CHECK(rejected->reference.identity.ideal_output==ReferenceId{"intersection-reference"});
            CHECK(rejected->reference.inputs==std::vector<SetId>{operands[0].id,operands[1].id});
            REQUIRE(rejected->provider.diagnostics.size()==1);
            CHECK(rejected->provider.diagnostics[0].code==DiagnosticCode::unsupported);
            CHECK(rejected->provider.diagnostics[0].field=="projection.operation");
            CHECK(rejected->provider.provenance.requested.id==ModuleId{"csl.geometry.polyhedral-projection"});
            REQUIRE(rejected->provider.provenance.actual);
            CHECK(rejected->provider.provenance.actual->id==ModuleId{"csl.geometry.polyhedral-projection"});
        };
        check(geometry::prepare_geometry_operation(request,conditional));
        check(geometry::prepare_geometry_operation(select(registry,
            Method{{"csl.geometry.polyhedral-projection"},{}},request,requirements)));
    }
    CHECK(*creations==0);
}

TEST_CASE("projection cancellation and arithmetic overflow retain explicit failure") {
    auto joint=h("overflow",2,{2,2,{1,std::numeric_limits<double>::denorm_min(),1,-1}},{1,1},{0,2,{}},{});
    auto outcome=project(projection(joint.as_handle(),{0}),geometry::polyhedral::ProjectionOutput::h);
    CHECK(std::holds_alternative<Unsupported>(outcome));
    auto selected=provider(geometry::polyhedral::make_projection_registration(),"csl.polyhedron.h");
    auto query=projection(interval("X",-1,1).as_handle(),{0});
    auto prepared=take(selected.prepare(query));
    std::stop_source cancellation;
    cancellation.request_stop();
    ExecutionContext context;
    context.cancellation=cancellation.get_token();
    auto result=std::get<0>(prepared.create())->run(context);
    REQUIRE(std::holds_alternative<OperationStopped>(result));
    CHECK(std::get<OperationStopped>(result).reason==StopReason::cancelled);
    context={};context.deadline=std::chrono::steady_clock::now();
    auto expired=std::get<0>(prepared.create())->run(context);
    REQUIRE(std::holds_alternative<OperationStopped>(expired));
    CHECK(std::get<OperationStopped>(expired).reason==StopReason::deadline_expired);
}

TEST_CASE("empty encoding honors zero max_rows for eager and lazy materialization") {
    auto empty=take(sets::make_empty({{"empty"},1,{}}));
    CHECK(std::holds_alternative<Unsupported>(project(projection(empty.as_handle(),{0}),
        geometry::polyhedral::ProjectionOutput::h,0)));
    auto lazy=take(project(projection(empty.as_handle(),{0}),geometry::polyhedral::ProjectionOutput::lazy)).output;
    auto selected=provider(geometry::polyhedral::make_projection_materializer(0),"csl.polyhedron.h");
    ConversionRequest request{{{"fixture"},{"empty-materialize"},{"empty-materialized"}},lazy,{"csl.polyhedron.h"},Assurance::numerical};
    CHECK(std::holds_alternative<Unsupported>(std::get<0>(take(selected.prepare(request)).create())->run({})));
}

namespace {
enum class ProviderReturn { rejected, support, containment };
class WrongProjectionResult final : public SetOperatorWorkspace {
    ProviderReturn return_;
public:
    explicit WrongProjectionResult(ProviderReturn value):return_(value) {}
    OperationOutcome apply(const OperationRequest& request,const ExecutionContext&) override {
        if(return_==ProviderReturn::rejected)
            return Unsupported{{{DiagnosticCode::unsupported,"projection.late","Late projection rejection"}}};
        GeometryEvidence evidence{{request.identity,{std::get<Projection>(request.operation).input.id}},
            GeometryClaimScope::support_value,Unestablished{}, {}, {}};
        if(return_==ProviderReturn::support) return SupportResult{1.0,{},std::move(evidence)};
        evidence.scope=GeometryClaimScope::containment;
        return ContainmentResult{ContainmentDecision::undetermined,{},std::move(evidence)};
    }
};
Registration<GeometryPort> wrong_projection(ProviderReturn value) {
    auto entry=geometry::polyhedral::make_projection_registration();
    entry.factory=[value](const OperationRequest&) {return std::make_unique<WrongProjectionResult>(value);};
    return entry;
}
}

TEST_CASE("predecessor failures retain original request child projection and provider") {
    auto request=predecessor(interval("X",-2,2).as_handle(),interval("U",-1,1).as_handle(),
        interval("S",0,1).as_handle(),{1,1,{1}},{1,1,{1}},{0});
    auto selected=provider(geometry::polyhedral::make_projection_registration(),"csl.polyhedron.h");
    auto prepared=take(reachability::prepare_nominal_predecessor(request,selected));
    ExecutionContext context;context.deadline=std::chrono::steady_clock::now();
    auto stopped=alternative<reachability::NominalPredecessorFailure>(prepared.run(context));
    CHECK(stopped.predecessor.identity==request.identity);
    CHECK(stopped.predecessor.inputs==std::vector<SetId>{{"X"},{"U"},{"S"}});
    CHECK(stopped.projection.identity.problem==request.identity.problem);
    CHECK_FALSE(stopped.projection.identity.request.value.empty());
    CHECK(stopped.projection_provider.request==stopped.projection.identity.request);
    CHECK(stopped.projection_provider.actual_module==std::optional<ModuleId>{{"csl.geometry.polyhedral-projection"}});
    CHECK(std::get<OperationStopped>(stopped.cause).reason==StopReason::deadline_expired);
    std::stop_source cancellation;cancellation.request_stop();context={};context.cancellation=cancellation.get_token();
    auto cancelled=alternative<reachability::NominalPredecessorFailure>(prepared.run(context));
    CHECK(std::get<OperationStopped>(cancelled.cause).reason==StopReason::cancelled);
    for(auto returned:{ProviderReturn::rejected,ProviderReturn::support,ProviderReturn::containment}) {
        auto wrong=provider(wrong_projection(returned),"csl.polyhedron.h");
        auto result=alternative<reachability::NominalPredecessorFailure>(
            take(reachability::prepare_nominal_predecessor(request,wrong)).run({}));
        CHECK(result.predecessor.identity==request.identity);
        CHECK(result.predecessor.inputs==std::vector<SetId>{{"X"},{"U"},{"S"}});
        CHECK(result.projection_provider.request==result.projection.identity.request);
        REQUIRE(std::holds_alternative<Unsupported>(result.cause));
        const auto& reason=std::get<Unsupported>(result.cause).diagnostics;
        REQUIRE_FALSE(reason.empty());
        CHECK(reason[0].code==(returned==ProviderReturn::rejected?DiagnosticCode::unsupported:DiagnosticCode::evidence_mismatch));
    }
}

TEST_CASE("scoped materialization failures retain completed nested lazy lineage") {
    auto source=h("source",3,{0,3,{}},{},{1,3,{1,2,3}},{6},{"x","y","z"});
    auto first=take(project(projection(source.as_handle(),{2,0}),geometry::polyhedral::ProjectionOutput::lazy));
    auto second_request=projection(first.output,{1});
    second_request.identity.request={"second-projection"};second_request.identity.ideal_output={"second-output"};
    auto second=take(project(second_request,geometry::polyhedral::ProjectionOutput::lazy));
    auto selected=provider(geometry::polyhedral::make_projection_materializer(),"csl.polyhedron.h");
    ConversionRequest request{{{"fixture"},{"materialize-scoped"},{"materialized-scoped"}},second.output,{"csl.polyhedron.h"},Assurance::numerical};
    ExecutionContext context;context.deadline=std::chrono::steady_clock::now();
    auto failure=alternative<geometry::polyhedral::ProjectionMaterializationFailure>(
        geometry::polyhedral::materialize_lazy_projection(request,selected,context));
    CHECK(failure.reference.identity==request.identity);
    CHECK(failure.reference.inputs==std::vector<SetId>{second.output.id});
    CHECK(failure.provider.request==request.identity.request);
    CHECK(failure.source_coordinates==std::vector<std::size_t>{0});
    REQUIRE(failure.completed_lineage.size()==2);
    CHECK(failure.completed_lineage[0].reference.identity.request==RequestId{"projection"});
    CHECK(failure.completed_lineage[1].reference.identity==second_request.identity);
    CHECK(std::get<OperationStopped>(failure.cause).reason==StopReason::deadline_expired);
    auto limited=provider(geometry::polyhedral::make_projection_materializer(0),"csl.polyhedron.h");
    auto rejected=alternative<geometry::polyhedral::ProjectionMaterializationFailure>(
        geometry::polyhedral::materialize_lazy_projection(request,limited,{}));
    CHECK(rejected.reference.identity==request.identity);
    CHECK(rejected.provider.actual_module==std::optional<ModuleId>{{"csl.geometry.projection-materializer"}});
    CHECK(rejected.completed_lineage.size()==2);
    CHECK(std::holds_alternative<Unsupported>(rejected.cause));
    auto success=take(geometry::polyhedral::materialize_lazy_projection(request,selected,{}));
    CHECK(contains(success.result.output,{-100}));
    CHECK(contains(success.result.output,{100}));
    CHECK(success.completed_lineage.size()==2);
    CHECK(success.source_coordinates==std::vector<std::size_t>{0});
    CHECK(success.provider.request==request.identity.request);
    request.output={"csl.polyhedron.v"};
    auto admission=alternative<geometry::polyhedral::ProjectionMaterializationFailure>(
        geometry::polyhedral::materialize_lazy_projection(request,selected,{}));
    CHECK(admission.reference.identity==request.identity);
    CHECK(admission.completed_lineage.size()==2);
    CHECK(admission.source_coordinates==std::vector<std::size_t>{0});
    CHECK(std::holds_alternative<Unsupported>(admission.cause));
}
