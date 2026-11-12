#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/box_parallelotope.hpp>
#include <csl/geometry/ellipsoidal.hpp>
#include <csl/geometry/generator_adapter.hpp>
#include <csl/geometry/generators.hpp>
#include <csl/geometry/quickhull_2d.hpp>
#include <csl/geometry/zonotope_reduction.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/data.hpp>
#include <csl/sets/generator_sets.hpp>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <variant>

namespace {
using namespace csl;
using Json=nlohmann::json;
using csl::geometry::ellipsoidal::FactorEllipsoid;

template<class T,class... E> T take(std::variant<T,E...> result,const char* what) {
    if(!std::holds_alternative<T>(result))
        throw std::runtime_error(std::string(what)+" was rejected");
    return std::get<T>(std::move(result));
}

std::string rejection_detail(const registry::Rejection& rejection) {
    std::string detail;
    for(const auto& diagnostic:rejection.diagnostics) {
        if(!detail.empty())detail+="; ";
        detail+=diagnostic.field+": "+diagnostic.explanation;
    }
    return detail;
}

template<class Port> registry::PreparedProvider<Port> prepare(
        registry::Registration<Port> registration,registry::Requirements requirements={}) {
    const registry::Method method{registration.identity.id,registration.identity.version};
    registry::Registry<Port> entries;
    if(entries.add(std::move(registration)))throw std::runtime_error("provider registration failed");
    return take(registry::prepare_provider(registry::select_provider(entries,method,requirements)),
        "provider selection");
}

SetHandle vertices(std::string id,const Matrix& points) {
    auto v=numeric::snapshot(points);
    auto r=numeric::snapshot(Matrix{0,points.cols,{}});
    auto result=sets::make_v({{std::move(id)},points.cols,{"deviation x1","deviation x2"}},
        {take(std::move(v),"vertex snapshot"),take(std::move(r),"ray snapshot")});
    return take(std::move(result),"V set construction").as_handle();
}

SetHandle generator(std::string id,Vector center,Matrix columns,
                    std::vector<sets::FactorId> factors) {
    const auto factor_count=factors.size();
    auto result=sets::make_generator_set({{std::move(id)},std::move(center),std::move(columns),
        std::move(factors),{0,factor_count,{}},{},{}});
    return take(std::move(result),"generator-set construction").as_handle();
}

struct PolyStep {
    std::vector<std::array<double,2>> points;
    Json calls;
};

struct PolyPipeline {
    registry::PreparedProvider<registry::GeometryPort> provider;
    std::size_t call{};

    OperationResult run(GeometryOperation operation,std::string request_suffix,
                        std::string output_suffix,const ExecutionContext& context) {
        OperationRequest request{{{"buryatia.volterra.matlab-literal-affine/1"},
            {"poly/"+std::to_string(call)+"/"+request_suffix},
            {"poly-stage/"+std::to_string(call)+"/"+output_suffix}},
            {"csl.geometry.affine-sum.source-index"},std::move(operation),
            SetRelation::equivalent,Assurance::numerical};
        auto admitted=provider.prepare(request);
        if(!std::holds_alternative<registry::PreparedPipeline<registry::GeometryPort>>(admitted))
            throw std::runtime_error("poly operation preparation rejected: "+
                rejection_detail(std::get<registry::Rejection>(admitted)));
        auto prepared=std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(admitted));
        auto workspace=std::get<0>(prepared.create());
        auto outcome=workspace->run(context);
        if(const auto* result=std::get_if<OperationResult>(&outcome)) {
            if(!check_geometry_evidence(result->evidence,request).empty())
                throw std::runtime_error("poly operation evidence did not match its request");
            ++call;
            return *result;
        }
        std::string detail="registered poly operation "+request_suffix+" did not complete";
        if(const auto* rejected=std::get_if<Unsupported>(&outcome))
            for(const auto& diagnostic:rejected->diagnostics)
                detail+="; "+diagnostic.field+": "+diagnostic.explanation;
        if(const auto* stopped=std::get_if<OperationStopped>(&outcome))
            detail+="; stopped: "+stopped->diagnostics;
        throw std::runtime_error(detail);
    }
};

struct GeneratorPipeline {
    registry::PreparedProvider<registry::GeometryPort> provider;
    std::size_t call{};

    OperationResult run(GeometryOperation operation,std::string name,const ExecutionContext& context) {
        OperationRequest request{{{"buryatia.volterra.matlab-literal-affine/1"},
            {"generator/"+std::to_string(call)+"/"+name},
            {"generator-stage/"+std::to_string(call)+"/"+name}},
            {"csl.geometry.generators.operations"},std::move(operation),
            SetRelation::equivalent,Assurance::numerical};
        auto admitted=provider.prepare(request);
        if(!std::holds_alternative<registry::PreparedPipeline<registry::GeometryPort>>(admitted))
            throw std::runtime_error("generator operation preparation rejected: "+
                rejection_detail(std::get<registry::Rejection>(admitted)));
        auto prepared=std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(admitted));
        auto workspace=std::get<0>(prepared.create());
        auto outcome=workspace->run(context);
        if(const auto* result=std::get_if<OperationResult>(&outcome)) {
            if(!check_geometry_evidence(result->evidence,request).empty())
                throw std::runtime_error("generator operation evidence did not match its request");
            ++call;
            return *result;
        }
        throw std::runtime_error("registered generator operation did not complete");
    }
};

struct VolterraStage {
    Matrix a;
    Vector b;
    Vector nominal;
    double h{};
};

std::vector<VolterraStage> literal_volterra_stages() {
    constexpr double a=0.9,b=0.003,c=0.8,d=0.002,e=0.85;
    constexpr std::size_t intervals=60;
    const double h=2*std::acos(-1.0)/(static_cast<double>(intervals)*std::sqrt(a*c));
    Vector nominal{410,300};
    std::vector<VolterraStage> stages;
    stages.reserve(intervals);
    for(std::size_t k=0;k<intervals;++k) {
        const Vector next{nominal[0]+h*(a*nominal[0]-b*nominal[0]*nominal[1]),
            nominal[1]+h*(-c*nominal[1]+d*nominal[0]*nominal[1])};
        Matrix transition{2,2,{1+h*(a-b*next[1]),-h*b*next[0],
            h*d*next[1],1+h*(-c+d*next[0])}};
        stages.push_back({std::move(transition),{h*e,0},next,h});
        nominal=next;
    }
    return stages;
}

std::vector<std::array<double,2>> v_points(const SetHandle& set) {
    const auto data=take(sets::from_handle(set),"native set import");
    const auto representation=data.representation();
    const auto* v=std::get_if<sets::VRepresentation>(&representation);
    if(!v || v->rays.rows()!=0)throw std::runtime_error("expected bounded native V set");
    std::vector<std::array<double,2>> points;
    points.reserve(v->vertices.rows());
    for(std::size_t i=0;i<v->vertices.rows();++i)
        points.push_back({v->vertices(i,0),v->vertices(i,1)});
    return points;
}

double polygon_area(const std::vector<std::array<double,2>>& p) {
    if(p.size()<3)return 0;
    double twice=0;
    for(std::size_t i=0;i<p.size();++i) {
        const auto& a=p[i];const auto& b=p[(i+1)%p.size()];
        twice+=a[0]*b[1]-a[1]*b[0];
    }
    return std::abs(twice)/2;
}

double generator_area(const sets::GeneratorSet& set) {
    const auto count=set.factor_ids().size();
    double area=0;
    for(std::size_t i=0;i<count;++i)for(std::size_t j=i+1;j<count;++j) {
        const double determinant=set.generators().values[i]*set.generators().values[count+j]-
            set.generators().values[j]*set.generators().values[count+i];
        area+=4*std::abs(determinant);
    }
    return area;
}

double generator_support(const sets::GeneratorSet& set,
                         const std::array<double,2>& direction) {
    const auto count=set.factor_ids().size();
    double value=direction[0]*set.center()[0]+direction[1]*set.center()[1];
    for(std::size_t i=0;i<count;++i)
        value+=std::abs(direction[0]*set.generators().values[i]+
                        direction[1]*set.generators().values[count+i]);
    return value;
}

double vertex_support(const std::vector<std::array<double,2>>& points,
                      const std::array<double,2>& direction) {
    if(points.empty())throw std::runtime_error("support of empty polygon");
    double value=direction[0]*points[0][0]+direction[1]*points[0][1];
    for(std::size_t i=1;i<points.size();++i)
        value=std::max(value,direction[0]*points[i][0]+direction[1]*points[i][1]);
    return value;
}

std::vector<std::array<double,2>> h_parallelogram(const SetHandle& set) {
    const auto data=take(sets::from_handle(set),"H set import");
    const auto representation=data.representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h || h->inequalities.rows()!=4 || h->inequalities.cols()!=2)
        throw std::runtime_error("expected a four-row planar parallelotope");
    const double a=h->inequalities(0,0),b=h->inequalities(0,1);
    const double c=h->inequalities(2,0),d=h->inequalities(2,1);
    const double determinant=a*d-b*c;
    if(!std::isfinite(determinant) || determinant==0)
        throw std::runtime_error("parallelotope direction matrix is singular");
    const std::array<double,2> low{-h->upper_bounds[1],-h->upper_bounds[3]};
    const std::array<double,2> high{h->upper_bounds[0],h->upper_bounds[2]};
    std::vector<std::array<double,2>> result;
    if(a==1 && b==0 && c==0 && d==1) {
        for(const double first:{low[0],high[0]})for(const double second:{low[1],high[1]})
            result.push_back({first,second});
        return result;
    }
    if(a==1 && b==0 && c==0.5 && d==1) {
        // This report's fixed shear has x=t1 and y=t2-t1/2. The factor 1/2
        // is exact in binary; step one adjacent float outward around each
        // rounded subtraction so the rematerialized polygon contains the H
        // corner despite the final binary64 operation.
        for(const double first:{low[0],high[0]})for(const double second:{low[1],high[1]}) {
            const double y=second-0.5*first;
            result.push_back({first,std::nextafter(y,-std::numeric_limits<double>::infinity())});
            result.push_back({first,std::nextafter(y,std::numeric_limits<double>::infinity())});
        }
        return result;
    }
    throw std::runtime_error("unsupported report parallelotope orientation");
}

double factor_ellipsoid_area(const FactorEllipsoid& e) {
    // Cauchy-Binet: det(F F^T) is the sum of squared 2x2 minors of F.
    double determinant=0.0;
    for(std::size_t i=0;i<e.factor.cols;++i)
        for(std::size_t j=i+1;j<e.factor.cols;++j) {
            const double minor=e.factor.values[i]*e.factor.values[e.factor.cols+j]-
                e.factor.values[j]*e.factor.values[e.factor.cols+i];
            determinant+=minor*minor;
        }
    return std::acos(-1.0)*std::sqrt(determinant);
}

double factor_frobenius_norm(const Matrix& factor) {
    double result=0.0;
    for(const double value:factor.values)result=std::hypot(result,value);
    return result;
}

double factor_ellipsoid_support(const FactorEllipsoid& e,
                               const std::array<double,2>& direction) {
    double center=direction[0]*e.center[0]+direction[1]*e.center[1];
    double square=0.0;
    for(std::size_t column=0;column<e.factor.cols;++column) {
        const double projected=direction[0]*e.factor.values[column]+
            direction[1]*e.factor.values[e.factor.cols+column];
        square+=projected*projected;
    }
    return center+std::sqrt(square);
}

Json json_points(const std::vector<std::array<double,2>>& points) {
    Json result=Json::array();
    for(const auto& p:points)result.push_back({p[0],p[1]});
    return result;
}

std::vector<std::array<double,2>> factor_ellipsoid_boundary(
        const FactorEllipsoid& e,std::size_t count=96) {
    double q00=0,q01=0,q11=0;
    for(std::size_t column=0;column<e.factor.cols;++column) {
        const double x=e.factor.values[column];
        const double y=e.factor.values[e.factor.cols+column];
        q00+=x*x;q01+=x*y;q11+=y*y;
    }
    const double spread=std::hypot(q00-q11,2*q01);
    const double major=std::sqrt(std::max(0.0,(q00+q11+spread)/2));
    const double minor=std::sqrt(std::max(0.0,(q00+q11-spread)/2));
    std::array<double,2> u{1,0};
    if(std::abs(q01)>std::abs((q00+spread-q11)/2))
        u={q01,(q00+spread-q11)/2};
    else if(q01==0 && q11>q00)u={0,1};
    const double length=std::hypot(u[0],u[1]);
    if(length==0)u={1,0};else {u[0]/=length;u[1]/=length;}
    const std::array<double,2> v{-u[1],u[0]};
    std::vector<std::array<double,2>> points;points.reserve(count);
    for(std::size_t i=0;i<count;++i) {
        const double angle=2*std::acos(-1.0)*static_cast<double>(i)/static_cast<double>(count);
        const double a=major*std::cos(angle),b=minor*std::sin(angle);
        points.push_back({e.center[0]+a*u[0]+b*v[0],e.center[1]+a*u[1]+b*v[1]});
    }
    return points;
}

std::vector<std::array<double,2>> hull(std::vector<std::array<double,2>> points) {
    std::sort(points.begin(),points.end());
    points.erase(std::unique(points.begin(),points.end()),points.end());
    if(points.size()<3)return points;
    const auto cross=[](const auto& o,const auto& a,const auto& b) {
        return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0]);
    };
    std::vector<std::array<double,2>> result;
    for(const auto& p:points) {
        while(result.size()>=2 && cross(result[result.size()-2],result.back(),p)<=0)result.pop_back();
        result.push_back(p);
    }
    const auto lower=result.size();
    for(auto i=points.rbegin()+1;i!=points.rend();++i) {
        while(result.size()>lower && cross(result[result.size()-2],result.back(),*i)<=0)result.pop_back();
        result.push_back(*i);
    }
    result.pop_back();
    return result;
}

std::vector<std::array<double,2>> zonotope_polygon(const sets::GeneratorSet& set) {
    std::vector<std::array<double,2>> corners;
    const auto count=set.factor_ids().size();
    if(count>=20)throw std::runtime_error("reduced zonotope corner quota exceeded");
    corners.reserve(std::size_t{1}<<count);
    for(std::size_t mask=0;mask<(std::size_t{1}<<count);++mask) {
        std::array<double,2> point{set.center()[0],set.center()[1]};
        for(std::size_t factor=0;factor<count;++factor) {
            const double sign=(mask&(std::size_t{1}<<factor))?1.0:-1.0;
            point[0]+=sign*set.generators().values[factor];
            point[1]+=sign*set.generators().values[count+factor];
        }
        corners.push_back(point);
    }
    return hull(std::move(corners));
}

    PolyStep affine_step(PolyPipeline& operations,
        const std::vector<std::array<double,2>>& source,const VolterraStage& stage,
        const std::string& suffix,const ExecutionContext& context) {
    Matrix points{source.size(),2,{}};
    points.values.reserve(2*source.size());
    for(const auto& p:source){points.values.push_back(p[0]);points.values.push_back(p[1]);}
    const auto input=vertices("buryatia-input-"+suffix,points);
    auto image=operations.run(AffineImage{input,stage.a,{0,0}},suffix+"-image",
        suffix+"-image-output",context);
    const std::array<double,2> radius{0.3*stage.b[0],0.3*stage.b[1]};
    const auto control=vertices("buryatia-control-"+suffix,
        Matrix{2,2,{-radius[0],0,radius[0],0}});
    auto sum=operations.run(MinkowskiSum{image.output,control},suffix+"-sum",
        suffix+"-sum-output",context);
    return {v_points(sum.output),Json::array({
        {{"operation","affine-image"},{"implementation","csl.geometry.affine-sum.source-index/1"},
         {"evidence",image.evidence.assumptions}},
        {{"operation","minkowski-sum"},{"implementation","csl.geometry.affine-sum.source-index/1"},
         {"evidence",sum.evidence.assumptions}}})};
}

double maximum_support_error(const sets::GeneratorSet& reference,
        const std::vector<std::array<double,2>>& polygon,
        const FactorEllipsoid* ellipse=nullptr) {
    const std::array<std::array<double,2>,8> directions{{
        {1,0},{-1,0},{0,1},{0,-1},{1,1},{1,-1},{-1,1},{-1,-1}}};
    double error=0;
    for(const auto& d:directions) {
        const double exact=generator_support(reference,d);
        const double approximate=ellipse?
            factor_ellipsoid_support(*ellipse,d):
            vertex_support(polygon,d);
        error=std::max(error,std::abs(approximate-exact));
    }
    return error;
}

Json stage_record(std::size_t stage,std::string family,const std::string& status,
        double area,std::size_t vertices_count,std::size_t generators_count,
        std::size_t constraints,double support_error,std::string inclusion,
        Json modules,Json assumptions={},double reference_area=0,Json drawing=Json::array()) {
    return {{"stage",stage},{"family",std::move(family)},{"status",status},
        {"area",area},{"vertex_count",vertices_count},{"generator_count",generators_count},
        {"constraint_count",constraints},{"max_abs_support_error_8_directions",support_error},
        {"affine_reference_area",reference_area},
        {"excess_area_vs_affine_reference",area-reference_area},
        {"rendering_vertices",std::move(drawing)},
        {"containment_check",inclusion},{"module_invocations",std::move(modules)},
        {"assumptions",std::move(assumptions)}};
}

const char* basis_name(csl::geometry::approximation::StructuralBasis basis) {
    using csl::geometry::approximation::StructuralBasis;
    switch(basis) {
    case StructuralBasis::identical_set:return "identical_set";
    case StructuralBasis::empty_subset:return "empty_subset";
    case StructuralBasis::universal_superset:return "universal_superset";
    case StructuralBasis::h_constraint_containment:return "h_constraint_containment";
    case StructuralBasis::h_point_containment:return "h_point_containment";
    case StructuralBasis::v_h_containment:return "v_h_containment";
    case StructuralBasis::h_v_containment:return "h_v_containment";
    case StructuralBasis::generator_axis_cover:return "generator_axis_cover";
    case StructuralBasis::v_ellipsoid_containment:return "v_ellipsoid_containment";
    }
    return "unknown";
}

Json run_2d() {
    using namespace csl::geometry;
    const auto exact_hull=prepare<registry::SourceIndexHullPort>(make_quickhull_source_index_registration());
    const auto geometry_registration=make_affine_sum_registration(
        SourceIndexAffineSumDependencies{exact_hull,{},HullCheckBudget{std::chrono::milliseconds{30000},4096}},
        AffineSumOptions{4096,{"deviation x1","deviation x2"}});
    registry::Requirements poly_requirements;
    poly_requirements.output.representation={"csl.polyhedron.v"};
    poly_requirements.output.relation=SetRelation::equivalent;
    PolyPipeline poly_ops{prepare<registry::GeometryPort>(geometry_registration,poly_requirements)};

    registry::Requirements generator_requirements;
    generator_requirements.output.representation={"csl.zonotope"};
    generator_requirements.output.relation=SetRelation::equivalent;
    GeneratorPipeline generator_ops{prepare<registry::GeometryPort>(
        generators::make_operation_registration(),generator_requirements)};
    const auto stages=literal_volterra_stages();
    const Vector initial{1,2};
    auto exact_initial=vertices("buryatia-volterra-exact-initial",Matrix{1,2,{initial[0],initial[1]}});
    auto generator_exact=generator("buryatia-volterra-zonotope-initial",initial,{2,0,{}},{});
    auto generator_reduced=generator("buryatia-volterra-reduced-initial",initial,{2,0,{}},{});
    auto box_set=exact_initial;
    auto para_set=exact_initial;
    auto ellipse_state=take(ellipsoidal::make_factor_ellipsoid(initial,{2,0,{}}),
        "initial factor ellipsoid");

    Json records=Json::array();
    records.push_back(stage_record(0,"exact_affine_polytope","completed",0,1,0,0,0,
        "identical_initial_point",Json::array(),Json::object(),0,{{1,2}}));
    records.push_back(stage_record(0,"unreduced_zonotope","completed",0,1,0,0,0,
        "identical_initial_point",Json::array(),Json::object(),0,{{1,2}}));
    records.push_back(stage_record(0,"reduced_zonotope","completed",0,1,0,0,0,
        "identical_initial_point",Json::array(),Json::object(),0,{{1,2}}));
    records.push_back(stage_record(0,"parallelotope","completed",0,1,0,4,0,
        "identical_initial_point",Json::array(),Json::object(),0,{{1,2}}));
    records.push_back(stage_record(0,"box","completed",0,1,0,4,0,
        "identical_initial_point",Json::array(),Json::object(),0,{{1,2}}));
    records.push_back(stage_record(0,"ellipsoid","completed",0,1,0,2,0,
        "identical_initial_point",Json::array(),Json::object(),0,{{1,2}}));

    const auto reduced_registration=approximation::make_axis_cover_registration({"buryatia-reduced"});
    const auto reduced_method=registry::Method{reduced_registration.identity.id,
        reduced_registration.identity.version};
    const auto box_registration_id=registry::Method{{"csl.approximation.box"},"1"};
    const auto para_registration_id=registry::Method{{"csl.approximation.parallelotope"},"1"};
    const registry::Method ellipse_method{{"csl.approximation.ellipsoid.axis2d"},"1"};
    const Matrix orientation{2,2,{1,0,0.5,1}};

    for(std::size_t k=0;k<stages.size();++k) {
        const auto& stage=stages[k];
        const auto exact_step=affine_step(poly_ops,v_points(exact_initial),stage,
            "exact-"+std::to_string(k+1),ExecutionContext{});
        const auto exact_points=hull(exact_step.points);
        Matrix exact_matrix{exact_points.size(),2,{}};
        for(const auto& p:exact_points){exact_matrix.values.push_back(p[0]);exact_matrix.values.push_back(p[1]);}
        exact_initial=vertices("buryatia-volterra-exact-stage-"+std::to_string(k+1),exact_matrix);

        const auto gen_image=generator_ops.run(AffineImage{generator_exact,stage.a,{0,0}},
            "unreduced-image",ExecutionContext{});
        const auto control_generator=generator("buryatia-control-zono-"+std::to_string(k),
            {0,0},{2,1,{0.3*stage.b[0],0.3*stage.b[1]}},
            {{"volterra-control-"+std::to_string(k)}});
        const auto gen_sum=generator_ops.run(MinkowskiSum{gen_image.output,control_generator},
            "unreduced-sum",ExecutionContext{});
        generator_exact=gen_sum.output;
        const auto exact_g=take(sets::from_generator_handle(generator_exact),"exact generator import");
        const double exact_area=generator_area(exact_g);
        const double exact_support_error=maximum_support_error(exact_g,exact_points);
        records.push_back(stage_record(k+1,"exact_affine_polytope","completed",polygon_area(exact_points),
            exact_points.size(),0,exact_points.size(),exact_support_error,"numerical_affine_reference",
            exact_step.calls,
            {{"reference_generator_area",exact_area},{"vertex_source","registered_affine_sum"}},
            exact_area,json_points(exact_points)));
        records.push_back(stage_record(k+1,"unreduced_zonotope","completed",exact_area,
            exact_points.size(),exact_g.factor_ids().size(),0,0,"same_generator_recurrence",
            Json::array({"csl.geometry.generators.operations/1.1.0"}),
            {{"affine_image",gen_image.evidence.assumptions},{"minkowski_sum",gen_sum.evidence.assumptions}},
            exact_area,json_points(exact_points)));

        auto reduced_image=generator_ops.run(AffineImage{generator_reduced,stage.a,{0,0}},
            "reduced-image",ExecutionContext{});
        auto reduced_sum=generator_ops.run(MinkowskiSum{reduced_image.output,control_generator},
            "reduced-sum",ExecutionContext{});
        auto reduce_registration=approximation::make_axis_cover_registration(
            {"buryatia-reduced-stage-"+std::to_string(k+1)});
        registry::Registry<registry::ApproximationPort> reducers;
        if(reducers.add(std::move(reduce_registration)))throw std::runtime_error("axis-cover registration failed");
        const ApproximationRequest reduce_request{{{"buryatia.volterra.matlab-literal-affine/1"},
            {"axis-cover/"+std::to_string(k+1)},{"reduced/"+std::to_string(k+1)}},
            reduced_sum.output,{"csl.zonotope"},SetRelation::outer,8,Assurance::numerical};
        const auto reduced_out=approximation::run_registered(reducers,reduced_method,reduce_request,ExecutionContext{});
        const auto* reduced_enclosed=std::get_if<approximation::EnclosedApproximation>(&reduced_out);
        if(!reduced_enclosed)throw std::runtime_error("registered axis-cover reduction did not admit its enclosure");
        generator_reduced=reduced_enclosed->result.output;
        const auto reduced_g=take(sets::from_generator_handle(generator_reduced),"reduced generator import");
        auto reduced_v=zonotope_polygon(reduced_g);
        records.push_back(stage_record(k+1,"reduced_zonotope","completed",generator_area(reduced_g),
            reduced_v.size(),reduced_g.factor_ids().size(),0,maximum_support_error(exact_g,reduced_v),
            "registered_generator_axis_cover; independent_support_diagnostics",
            Json::array({"csl.geometry.generators.operations/1.1.0",
                         "csl.geometry.zonotope.axis-cover/1.0.0"}),
            {{"reduction_budget_generators",8},{"admission_basis","generator_axis_cover"},
             {"reducer_assumptions",reduced_enclosed->result.evidence.assumptions}},
            exact_area,json_points(reduced_v)));

        const auto box_step=affine_step(poly_ops,v_points(box_set),stage,
            "box-"+std::to_string(k+1),ExecutionContext{});
        Matrix box_input_matrix{box_step.points.size(),2,{}};
        for(const auto& p:box_step.points){box_input_matrix.values.push_back(p[0]);box_input_matrix.values.push_back(p[1]);}
        const auto box_v=vertices("buryatia-box-input-"+std::to_string(k+1),box_input_matrix);
        registry::Registry<registry::ApproximationPort> boxes;
        const auto box_registration=approximation::make_box_registration({"buryatia-box-stage-"+std::to_string(k+1)});
        if(boxes.add(box_registration))throw std::runtime_error("box registration failed");
        const ApproximationRequest box_request{{{"buryatia.volterra.matlab-literal-affine/1"},
            {"box/"+std::to_string(k+1)},{"box-output/"+std::to_string(k+1)}},
            box_v,{"csl.polyhedron.h"},SetRelation::outer,4,Assurance::numerical};
        const auto box_out=approximation::run_registered(boxes,box_registration_id,box_request,ExecutionContext{});
        const auto* box_enclosed=std::get_if<approximation::EnclosedApproximation>(&box_out);
        if(!box_enclosed)throw std::runtime_error("registered box approximation did not admit its enclosure");
        auto box_carried_points=hull(h_parallelogram(box_enclosed->result.output));
        Matrix box_carried_matrix{box_carried_points.size(),2,{}};
        for(const auto& p:box_carried_points){box_carried_matrix.values.push_back(p[0]);box_carried_matrix.values.push_back(p[1]);}
        box_set=vertices("buryatia-box-carried-"+std::to_string(k+1),box_carried_matrix);
        records.push_back(stage_record(k+1,"box","completed",polygon_area(box_carried_points),
            box_carried_points.size(),0,4,maximum_support_error(exact_g,box_carried_points),
            "registered_v_h_containment",Json::array({box_step.calls,
                {{"operation","registered-approximation"},{"implementation",box_registration.identity.id.value+"/"+box_registration.identity.version},
                 {"admission_basis",basis_name(box_enclosed->basis)},
                 {"evidence",box_enclosed->result.evidence.assumptions}}}),
            {{"approximation_basis",basis_name(box_enclosed->basis)},
             {"provider_assumptions",box_enclosed->result.evidence.assumptions}},
            exact_area,json_points(box_carried_points)));

        const auto para_step=affine_step(poly_ops,v_points(para_set),stage,
            "parallelotope-"+std::to_string(k+1),ExecutionContext{});
        Matrix para_input_matrix{para_step.points.size(),2,{}};
        for(const auto& p:para_step.points){para_input_matrix.values.push_back(p[0]);para_input_matrix.values.push_back(p[1]);}
        const auto para_v=vertices("buryatia-parallelotope-input-"+std::to_string(k+1),para_input_matrix);
        registry::Registry<registry::ApproximationPort> parallelotopes;
        const auto para_registration=approximation::make_parallelotope_registration(
            {"buryatia-parallelotope-stage-"+std::to_string(k+1)},orientation);
        if(parallelotopes.add(para_registration))throw std::runtime_error("parallelotope registration failed");
        const ApproximationRequest para_request{{{"buryatia.volterra.matlab-literal-affine/1"},
            {"parallelotope/"+std::to_string(k+1)},{"parallelotope-output/"+std::to_string(k+1)}},
            para_v,{"csl.polyhedron.h"},SetRelation::outer,4,Assurance::numerical};
        const auto para_out=approximation::run_registered(parallelotopes,para_registration_id,
            para_request,ExecutionContext{});
        const auto* para_enclosed=std::get_if<approximation::EnclosedApproximation>(&para_out);
        if(!para_enclosed)throw std::runtime_error("registered parallelotope did not admit its enclosure");
        const auto para_corners=hull(h_parallelogram(para_enclosed->result.output));
        Matrix para_corner_matrix{para_corners.size(),2,{}};
        for(const auto& p:para_corners){para_corner_matrix.values.push_back(p[0]);para_corner_matrix.values.push_back(p[1]);}
        para_set=vertices("buryatia-parallelotope-carried-"+std::to_string(k+1),para_corner_matrix);
        const auto para_carried_points=v_points(para_set);
        records.push_back(stage_record(k+1,"parallelotope","completed",polygon_area(para_carried_points),
            para_carried_points.size(),0,4,maximum_support_error(exact_g,para_carried_points),
            "registered_v_h_containment",Json::array({para_step.calls,
                {{"operation","registered-approximation"},{"implementation",para_registration.identity.id.value+"/"+para_registration.identity.version},
                 {"admission_basis",basis_name(para_enclosed->basis)},
                 {"evidence",para_enclosed->result.evidence.assumptions}}}),
            {{"orientation_rows",{{1,0},{0.5,1}}},
             {"vertex_materialization","fixed shear inverse x=t1,y=t2-t1/2; one binary64 neighbor added on each side of y"},
             {"approximation_basis",basis_name(para_enclosed->basis)},
             {"provider_assumptions",para_enclosed->result.evidence.assumptions}},
            exact_area,json_points(para_carried_points)));

        const auto ellipse_image=take(ellipsoidal::affine_image(ellipse_state,stage.a,{0,0}),
            "factor ellipsoid affine image");
        const auto control_ellipse=take(ellipsoidal::make_factor_ellipsoid({0,0},
            Matrix{2,1,{0.3*stage.b[0],0.3*stage.b[1]}}),"control segment ellipsoid");
        const double previous_norm=factor_frobenius_norm(ellipse_image.factor);
        const double control_norm=factor_frobenius_norm(control_ellipse.factor);
        const double beta=previous_norm==0.0 || control_norm==0.0?
            1.0:control_norm/previous_norm;
        if(!std::isfinite(beta) || beta<=0)
            throw std::runtime_error("trace-tuned ellipsoid beta is not finite and positive");
        ellipse_state=take(ellipsoidal::outer_minkowski_sum(ellipse_image,control_ellipse,beta),
            "factor ellipsoid Minkowski outer sum");

        // Visit the pre-existing registered 2D V→ellipsoid module as a
        // separately labeled per-stage comparison candidate. It is not the
        // carried recurrence; the factor kernel above is the recursive family.
        registry::Registry<registry::ApproximationPort> ellipses;
        const auto ellipse_registration=approximation::make_directional_ellipsoid_registration(
            ellipse_method,{"buryatia-ellipse-stage-"+std::to_string(k+1)},Matrix{2,2,{1,0,0,1}});
        if(ellipses.add(ellipse_registration))throw std::runtime_error("ellipsoid registration failed");
        Matrix provider_input_matrix{exact_points.size(),2,{}};
        for(const auto& p:exact_points) {
            provider_input_matrix.values.push_back(p[0]);
            provider_input_matrix.values.push_back(p[1]);
        }
        const auto provider_input=vertices("buryatia-ellipse-provider-input-"+
            std::to_string(k+1),provider_input_matrix);
        const ApproximationRequest ellipse_request{{{"buryatia.volterra.matlab-literal-affine/1"},
            {"ellipse/"+std::to_string(k+1)},{"ellipse-output/"+std::to_string(k+1)}},
            provider_input,{"csl.ellipsoid.directional2d"},SetRelation::outer,1,Assurance::numerical};
        const auto ellipse_out=approximation::run_registered(ellipses,ellipse_method,
            ellipse_request,ExecutionContext{});
        const auto* ellipse_enclosed=std::get_if<approximation::EnclosedApproximation>(&ellipse_out);
        if(!ellipse_enclosed)throw std::runtime_error("registered ellipsoid did not admit its enclosure");
        const auto provider_candidate=take(ellipsoidal::from_ellipsoid_handle(ellipse_enclosed->result.output),
            "ellipsoid output import");
        const auto provider_area=std::acos(-1.0)*provider_candidate.radii()[0]*
            provider_candidate.radii()[1]/std::abs(provider_candidate.orientation().values[0]*
                provider_candidate.orientation().values[3]-provider_candidate.orientation().values[1]*
                provider_candidate.orientation().values[2]);
        records.push_back(stage_record(k+1,"ellipsoid","completed",factor_ellipsoid_area(ellipse_state),
            0,ellipse_state.factor.cols,0,maximum_support_error(exact_g,{},&ellipse_state),
            "factor_outer_minkowski_sum; numerical_binary64",
            Json::array({{{"operation","factor-affine-image"},
                           {"implementation","csl.geometry.ellipsoidal.factor-affine/1"}},
                          {{"operation","factor-outer-minkowski-sum"},
                           {"implementation","csl.geometry.ellipsoidal.factor-minkowski/1"}},
                          {{"operation","registered-v-ellipsoid-candidate"},
                           {"implementation",ellipse_registration.identity.id.value+"/"+
                                ellipse_registration.identity.version},
                           {"admission_basis",basis_name(ellipse_enclosed->basis)},
                           {"evidence",ellipse_enclosed->result.evidence.assumptions}}}),
            {{"beta",beta},{"beta_policy","||F_control||F / ||A F_previous||F; minimizes output trace within the one-parameter bound family"},
             {"outer_sum_witness","[u/sqrt(1+beta),v/sqrt(1+1/beta)] has norm at most one"},
             {"factor_columns",ellipse_state.factor.cols},
             {"registered_provider_reference_area",provider_area},
             {"provider_reference_basis",basis_name(ellipse_enclosed->basis)},
             {"rounding","numerical binary64; no validated arithmetic certificate"}},
            exact_area,json_points(factor_ellipsoid_boundary(ellipse_state))));
    }

    return {{"schema","csl.buryatia.recursive-approximation/1"},
        {"track","new-comparison/literal-script-affine-variant"},
        {"case_id","buryatia-volterra-matlab-literal-affine/1"},
        {"source_variant_id","buryatia-volterra-literal-script-affine/1"},
        {"canonical_task_comparison","syn-nl-lv-01 is a distinct multiplicative-harvesting model"},
        {"source_sha256","c26fc2424fa8b3325a864d1afbc67920ba1c05665bfdf4562bed79548b60a4f1"},
        {"state_coordinates","deviation x1,x2 around nominal physical state"},
        {"nominal_initial",{410,300}},{"deviation_initial",{1,2}},
        {"parameters",{{"a",0.9},{"b",0.003},{"c",0.8},{"d",0.002},{"e",0.85}}},
        {"intervals",60},{"step",stages.front().h},{"control_bounds",{-0.3,0.3}},
        {"source_index_checker_budget",{{"wall_ms",30000},{"max_points",4096}}},
        {"support_diagnostic_directions",{{1,0},{-1,0},{0,1},{0,-1},
            {1,1},{1,-1},{-1,1},{-1,-1}}},
        {"equations",{"nominal_next=nominal+h*(a*x-b*x*y,-c*y+d*x*y)",
            "A[k]=[[1+h*(a-b*y_next),-h*b*x_next],[h*d*y_next,1+h*(-c+d*x_next)]]",
            "B=[h*e,0]^T","z[k+1]=A[k]z[k]+B*u[k]",
            "u[k] independently selected from [-0.3,0.3]"}},
        {"scope","affine deviation recurrence only; no nonlinear enclosure, feedback or minimax claim"},
        {"families",{"exact_affine_polytope","unreduced_zonotope","reduced_zonotope",
            "parallelotope","box","ellipsoid"}},{"records",std::move(records)}};
}
}

int main(int argc,char** argv) try {
    if(argc>1 && std::string(argv[1])!="--volterra-2d")
        throw std::runtime_error("usage: csl_buryatia_approximation_report [--volterra-2d]");
    std::cout<<std::setprecision(std::numeric_limits<double>::max_digits10)
        <<run_2d().dump(2)<<'\n';
    return 0;
} catch(const std::exception& error) {
    std::cerr<<error.what()<<'\n';
    return 1;
}
