#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/box_parallelotope.hpp>
#include <csl/geometry/ellipsoidal.hpp>
#include <csl/geometry/generator_adapter.hpp>
#include <csl/geometry/generators.hpp>
#include <csl/geometry/zonotope_reduction.hpp>
#include <csl/optimization/phase_one.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/data.hpp>
#include <csl/sets/generator_sets.hpp>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace {
using namespace csl;
using Json=nlohmann::json;
using csl::geometry::ellipsoidal::FactorEllipsoid;
constexpr std::size_t dimension=4;
constexpr std::size_t control_dimension=2;
// Seven updates with four independent control corners per update yield at
// most 4^7 = 16,384 exact affine candidate rows before hull reduction.
constexpr std::size_t exact_candidate_limit=16384;
constexpr double pi=3.141592653589793238462643383279502884;
const std::string source_case="buryatia-dim4-matlab-literal-affine/1";

template<class T,class... E> T take(std::variant<T,E...> value,const char* what) {
    if(!std::holds_alternative<T>(value))throw std::runtime_error(std::string(what)+" rejected");
    return std::get<T>(std::move(value));
}

template<class Port> registry::PreparedProvider<Port> prepare(
        registry::Registration<Port> registration,registry::Requirements requirements={}) {
    const registry::Method method{registration.identity.id,registration.identity.version};
    registry::Registry<Port> entries;
    if(entries.add(std::move(registration)))throw std::runtime_error("provider registration failed");
    return take(registry::prepare_provider(registry::select_provider(entries,method,requirements)),
        "provider selection");
}

const char* basis_name(geometry::approximation::StructuralBasis basis) {
    using geometry::approximation::StructuralBasis;
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

std::vector<std::string> labels() {return {"deviation x1","deviation x2","deviation x3","deviation x4"};}

SetHandle vertices(std::string id,const std::vector<Vector>& points) {
    Vector flat;
    flat.reserve(points.size()*dimension);
    for(const auto& point:points) {
        if(point.size()!=dimension)throw std::runtime_error("4D point has the wrong dimension");
        flat.insert(flat.end(),point.begin(),point.end());
    }
    const auto v=numeric::snapshot(Matrix{points.size(),dimension,std::move(flat)});
    const auto r=numeric::snapshot(Matrix{0,dimension,{}});
    if(!std::holds_alternative<numeric::MatrixView>(v)||!std::holds_alternative<numeric::MatrixView>(r))
        throw std::runtime_error("4D vertex snapshot failed");
    return take(sets::make_v({{std::move(id)},dimension,labels()},
        {std::get<numeric::MatrixView>(v),std::get<numeric::MatrixView>(r)}),"V set construction").as_handle();
}

SetHandle generator(std::string id,Vector center,Matrix columns,std::vector<sets::FactorId> factors) {
    const auto factor_count=factors.size();
    auto result=sets::make_generator_set({{std::move(id)},std::move(center),std::move(columns),
        std::move(factors),{0,factor_count,{}},{},{}});
    return take(std::move(result),"generator set construction").as_handle();
}

std::vector<Vector> v_points(const SetHandle& handle) {
    const auto data=take(sets::from_handle(handle),"native set import");
    const auto representation=data.representation();
    const auto* v=std::get_if<sets::VRepresentation>(&representation);
    if(!v||v->rays.rows()!=0||v->vertices.cols()!=dimension)
        throw std::runtime_error("expected a bounded 4D V set");
    std::vector<Vector> points;
    points.reserve(v->vertices.rows());
    for(std::size_t row=0;row<v->vertices.rows();++row) {
        Vector point(dimension);
        for(std::size_t column=0;column<dimension;++column)point[column]=v->vertices(row,column);
        points.push_back(std::move(point));
    }
    return points;
}

struct PolyPipeline {
    registry::PreparedProvider<registry::GeometryPort> provider;
    std::size_t call{};
    OperationResult run(GeometryOperation operation,std::string suffix,const ExecutionContext& context={}) {
        OperationRequest request{{{source_case},{"poly/"+std::to_string(call)+"/"+suffix},
            {"poly-output/"+std::to_string(call)+"/"+suffix}},
            {"csl.geometry.affine-sum"},std::move(operation),SetRelation::equivalent,Assurance::numerical};
        auto admitted=provider.prepare(request);
        if(!std::holds_alternative<registry::PreparedPipeline<registry::GeometryPort>>(admitted)) {
            const auto& rejected=std::get<registry::Rejection>(admitted);
            std::string details="affine-sum preparation rejected for "+request.identity.request.value;
            for(const auto& diagnostic:rejected.diagnostics)
                details+="; "+diagnostic.field+": "+diagnostic.explanation;
            throw std::runtime_error(details);
        }
        auto plan=std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(admitted));
        auto workspace=std::get<0>(plan.create());
        const auto outcome=workspace->run(context);
        if(const auto* result=std::get_if<OperationResult>(&outcome)) {
            if(!check_geometry_evidence(result->evidence,request).empty())
                throw std::runtime_error("affine-sum evidence did not match its request");
            ++call;
            return *result;
        }
        std::string details="affine-sum operation "+request.identity.request.value+" did not complete";
        if(const auto* stopped=std::get_if<OperationStopped>(&outcome))
            details+=" (stopped: "+stopped->diagnostics+")";
        else if(const auto* unsupported=std::get_if<Unsupported>(&outcome))
            for(const auto& diagnostic:unsupported->diagnostics)
                details+="; "+diagnostic.field+": "+diagnostic.explanation;
        throw std::runtime_error(details);
    }
};

struct GeneratorPipeline {
    registry::PreparedProvider<registry::GeometryPort> provider;
    std::size_t call{};
    OperationResult run(GeometryOperation operation,std::string suffix,const ExecutionContext& context={}) {
        OperationRequest request{{{source_case},{"generator/"+std::to_string(call)+"/"+suffix},
            {"generator-output/"+std::to_string(call)+"/"+suffix}},
            {"csl.geometry.generators.operations"},std::move(operation),
            SetRelation::equivalent,Assurance::numerical};
        auto admitted=provider.prepare(request);
        if(!std::holds_alternative<registry::PreparedPipeline<registry::GeometryPort>>(admitted))
            throw std::runtime_error("generator operation preparation rejected");
        auto plan=std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(admitted));
        auto workspace=std::get<0>(plan.create());
        const auto outcome=workspace->run(context);
        if(const auto* result=std::get_if<OperationResult>(&outcome)) {
            if(!check_geometry_evidence(result->evidence,request).empty())
                throw std::runtime_error("generator evidence did not match its request");
            ++call;
            return *result;
        }
        throw std::runtime_error("registered generator operation did not complete");
    }
};

std::vector<Vector> materialize_generator_vertices(const SetHandle& input,std::size_t maximum,
        const std::string& suffix,const ExecutionContext& context={}) {
    const auto registration=geometry::generators::make_v_conversion_registration(maximum);
    registry::Requirements requirements;
    requirements.output.representation={"csl.polyhedron.v"};
    requirements.output.relation=SetRelation::equivalent;
    const auto provider=prepare<registry::ConversionPort>(registration,requirements);
    ConversionRequest request{{{source_case},{"generator-v/"+suffix},{"generator-v-output/"+suffix}},
        input,{"csl.polyhedron.v"},Assurance::numerical};
    auto admitted=provider.prepare(request);
    if(!std::holds_alternative<registry::PreparedPipeline<registry::ConversionPort>>(admitted))
        throw std::runtime_error("generator V-conversion preparation rejected");
    auto plan=std::get<registry::PreparedPipeline<registry::ConversionPort>>(std::move(admitted));
    auto workspace=std::get<0>(plan.create());
    const auto outcome=workspace->run(context);
    if(const auto* result=std::get_if<OperationResult>(&outcome)) {
        if(!check_geometry_evidence(result->evidence,request).empty())
            throw std::runtime_error("generator V-conversion evidence did not match its request");
        return v_points(result->output);
    }
    throw std::runtime_error("registered generator V-conversion did not complete");
}

struct Stage {Matrix a;Matrix b;Vector nominal;};

double sind(double degrees) {return std::sin(degrees*pi/180.0);}
double cosd(double degrees) {return std::cos(degrees*pi/180.0);}

std::vector<Stage> literal_stages() {
    constexpr double a=0.15,b=-0.8,c=0.25;
    Vector nominal{1,1,1,1};
    std::vector<Stage> stages;
    for(std::size_t k=0;k<7;++k) {
        Matrix transition{4,4,{1,cosd(nominal[1]),0,0,
            a,1,0,0, 0,b,1,0, 0,0,c,1}};
        Matrix input{4,2,{1+0.5*cosd(nominal[0]),0, 0,1, 1,0, 0,1}};
        stages.push_back({std::move(transition),std::move(input),nominal});
        const Vector next{nominal[0]+0.5*sind(nominal[1])+(1+0.5*cosd(nominal[0]))*0.5,
            nominal[1]+a*nominal[0],nominal[2]+b*nominal[1],nominal[3]+c*nominal[2]+0.5};
        nominal=next;
    }
    return stages;
}

std::vector<Vector> control_vertices(const Matrix& b) {
    std::vector<Vector> points;
    for(const auto& [u1,u2]:std::array<std::array<double,2>,4>{{{-1,-1},{1,1},{-1,1},{1,-1}}}) {
        Vector point(dimension);
        for(std::size_t row=0;row<dimension;++row)
            point[row]=b.values[row*2]*u1+b.values[row*2+1]*u2;
        points.push_back(std::move(point));
    }
    return points;
}

struct PolyStepResult {OperationResult image;OperationResult sum;SetHandle hull;Json materialization;};

PolyStepResult poly_step(PolyPipeline& pipeline,
        const SetHandle& previous,const Stage& stage,
        std::size_t k,const ExecutionContext& context={}) {
    const auto image=pipeline.run(AffineImage{previous,stage.a,Vector(dimension,0.0)},
        "affine-image-"+std::to_string(k),context);
    const auto control=vertices("buryatia-dim4-control-"+std::to_string(k),control_vertices(stage.b));
    const auto sum=pipeline.run(MinkowskiSum{image.output,control},"minkowski-"+std::to_string(k),context);
    // affine-sum already returns the retained V cloud after checking every
    // removed candidate against the complete generated cloud. Re-converting
    // that V result to H and numerically solving its vertices here both repeats
    // the work and can perturb a later recurrence. Carry the actual module
    // output directly; its represented convex hull is the recursive set.
    return {image,sum,sum.output,{{"provider","csl.geometry.affine-sum"},
        {"vertex_materialization","native affine-sum retained V rows"},
        {"candidate_reduction_evidence",sum.evidence.assumptions}}};
}

std::vector<Vector> project_points(const std::vector<Vector>& points,const std::array<std::size_t,3>& axes) {
    std::vector<Vector> projected;
    projected.reserve(points.size());
    for(const auto& point:points)projected.push_back({point[axes[0]],point[axes[1]],point[axes[2]]});
    return projected;
}

Json points_json(const std::vector<Vector>& points) {return Json(points);}

long double determinant4(const std::array<long double,16>& values) {
    auto matrix=values;
    long double determinant=1.0L;
    for(std::size_t column=0;column<4;++column) {
        std::size_t pivot=column;
        for(std::size_t row=column+1;row<4;++row)
            if(std::abs(matrix[row*4+column])>std::abs(matrix[pivot*4+column]))pivot=row;
        if(matrix[pivot*4+column]==0.0L)return 0.0L;
        if(pivot!=column) {
            for(std::size_t j=column;j<4;++j)std::swap(matrix[pivot*4+j],matrix[column*4+j]);
            determinant=-determinant;
        }
        const auto diagonal=matrix[column*4+column];
        determinant*=diagonal;
        for(std::size_t row=column+1;row<4;++row) {
            const auto multiplier=matrix[row*4+column]/diagonal;
            for(std::size_t j=column+1;j<4;++j)matrix[row*4+j]-=multiplier*matrix[column*4+j];
        }
    }
    return determinant;
}

double zonotope_volume(const sets::GeneratorSet& set) {
    const auto count=set.factor_ids().size();
    if(count<dimension)return 0.0;
    long double sum=0.0L;
    for(std::size_t i=0;i<count;++i)for(std::size_t j=i+1;j<count;++j)
        for(std::size_t k=j+1;k<count;++k)for(std::size_t l=k+1;l<count;++l) {
            std::array<long double,16> minor{};
            const std::array<std::size_t,4> columns{i,j,k,l};
            for(std::size_t row=0;row<4;++row)for(std::size_t col=0;col<4;++col)
                minor[row*4+col]=set.generators().values[row*count+columns[col]];
            sum+=std::abs(determinant4(minor));
        }
    return static_cast<double>(16.0L*sum);
}

double ellipsoid_volume(const FactorEllipsoid& set) {
    if(set.factor.rows!=4||set.factor.cols<4)return 0.0;
    std::array<long double,16> gram{};
    for(std::size_t i=0;i<4;++i)for(std::size_t j=0;j<4;++j)
        for(std::size_t k=0;k<set.factor.cols;++k)
            gram[i*4+j]+=static_cast<long double>(set.factor.values[i*set.factor.cols+k])*
                set.factor.values[j*set.factor.cols+k];
    const auto determinant=determinant4(gram);
    if(determinant<=0.0L)return 0.0;
    return static_cast<double>((pi*pi/2.0L)*std::sqrt(determinant));
}

double point_support(const std::vector<Vector>& points,const Vector& direction) {
    if(points.empty())throw std::runtime_error("support of an empty set");
    double maximum=-std::numeric_limits<double>::infinity();
    for(const auto& point:points) {
        double value=0.0;
        for(std::size_t i=0;i<dimension;++i)value+=direction[i]*point[i];
        maximum=std::max(maximum,value);
    }
    return maximum;
}

double generator_support(const sets::GeneratorSet& set,const Vector& direction) {
    const auto count=set.factor_ids().size();
    double value=std::inner_product(direction.begin(),direction.end(),set.center().begin(),0.0);
    for(std::size_t col=0;col<count;++col) {
        double projection=0.0;
        for(std::size_t row=0;row<dimension;++row)
            projection+=direction[row]*set.generators().values[row*count+col];
        value+=std::abs(projection);
    }
    return value;
}

double factor_support(const FactorEllipsoid& set,const Vector& direction) {
    double square=0.0;
    for(std::size_t col=0;col<set.factor.cols;++col) {
        double projection=0.0;
        for(std::size_t row=0;row<dimension;++row)
            projection+=direction[row]*set.factor.values[row*set.factor.cols+col];
        square+=projection*projection;
    }
    return std::inner_product(direction.begin(),direction.end(),set.center.begin(),0.0)+std::sqrt(square);
}

std::vector<Vector> support_directions() {
    std::vector<Vector> directions;
    for(std::size_t mask=0;mask<16;++mask) {
        Vector d(4);
        for(std::size_t i=0;i<4;++i)d[i]=(mask&(std::size_t{1}<<i))?1.0:-1.0;
        directions.push_back(std::move(d));
    }
    for(std::size_t i=0;i<4;++i)for(const double sign:{-1.0,1.0}) {
        Vector d(4);d[i]=sign;directions.push_back(std::move(d));
    }
    return directions;
}

Json support_diagnostics(const std::vector<Vector>& exact,const sets::GeneratorSet* generator_set,
        const FactorEllipsoid* ellipsoid,const std::vector<Vector>* outer_vertices) {
    Json result=Json::array();
    for(const auto& direction:support_directions()) {
        const auto reference=point_support(exact,direction);
        const double approximate=generator_set?generator_support(*generator_set,direction):
            ellipsoid?factor_support(*ellipsoid,direction):point_support(*outer_vertices,direction);
        result.push_back({{"direction",direction},{"exact_support",reference},
            {"approximate_support",approximate},{"support_excess",approximate-reference},
            {"absolute_error",std::abs(approximate-reference)}});
    }
    return result;
}

Json generator_json(const sets::GeneratorSet& set) {
    return {{"kind","zonotope"},{"center",set.center()},
        {"factor_rows",set.generators().rows},{"factor_columns",set.generators().cols},
        {"factor_row_major",set.generators().values}};
}

Json ellipsoid_json(const FactorEllipsoid& set) {
    return {{"kind","factor_ellipsoid"},{"center",set.center},
        {"factor_rows",set.factor.rows},{"factor_columns",set.factor.cols},
        {"factor_row_major",set.factor.values}};
}

Json ellipsoid_projection_json(const FactorEllipsoid& set) {
    const std::array<std::array<std::size_t,3>,3> projections{{{{0,1,2}},{{1,2,3}},{{0,1,3}}}};
    const std::array<const char*,3> names{"x1_x2_x3","x2_x3_x4","x1_x2_x4"};
    Json result=Json::object();
    for(std::size_t p=0;p<projections.size();++p) {
        const auto axes=projections[p];
        Vector center{set.center[axes[0]],set.center[axes[1]],set.center[axes[2]]};
        Matrix factor{3,set.factor.cols,Vector(3*set.factor.cols)};
        for(std::size_t row=0;row<3;++row)
            for(std::size_t column=0;column<set.factor.cols;++column)
                factor.values[row*factor.cols+column]=set.factor.values[axes[row]*set.factor.cols+column];
        result[names[p]]={{"kind","factor_ellipsoid_projection"},{"dimension",3},
            {"axes",{axes[0]+1,axes[1]+1,axes[2]+1}},
            {"center",std::move(center)},{"factor_columns",factor.cols},
            {"factor_row_major",std::move(factor.values)}};
    }
    return result;
}

Json ellipsoid_projection_json_2d(const FactorEllipsoid& set) {
    const std::array<std::array<std::size_t,2>,6> projections{{
        {{0,1}},{{0,2}},{{0,3}},{{1,2}},{{1,3}},{{2,3}}}};
    const std::array<const char*,6> names{"x1_x2","x1_x3","x1_x4","x2_x3","x2_x4","x3_x4"};
    Json result=Json::object();
    for(std::size_t p=0;p<projections.size();++p) {
        const auto axes=projections[p];
        Matrix factor{2,set.factor.cols,Vector(2*set.factor.cols)};
        for(std::size_t row=0;row<2;++row)
            for(std::size_t column=0;column<set.factor.cols;++column)
                factor.values[row*factor.cols+column]=set.factor.values[axes[row]*set.factor.cols+column];
        result[names[p]]={{"kind","factor_ellipsoid_projection"},{"dimension",2},
            {"axes",{axes[0]+1,axes[1]+1}},
            {"center",Vector{set.center[axes[0]],set.center[axes[1]]}},
            {"factor_columns",factor.cols},{"factor_row_major",std::move(factor.values)}};
    }
    return result;
}

Json h_json(const SetHandle& set) {
    const auto imported=take(sets::from_handle(set),"outer H set import");
    const auto representation=imported.representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h)throw std::runtime_error("expected full-state H representation");
    Vector values;
    values.reserve(h->inequalities.rows()*h->inequalities.cols());
    for(std::size_t row=0;row<h->inequalities.rows();++row)
        for(std::size_t column=0;column<h->inequalities.cols();++column)
            values.push_back(h->inequalities(row,column));
    const auto upper_bounds=h->upper_bounds.values();
    return {{"kind","h_polytope"},{"inequality_rows",h->inequalities.rows()},
        {"inequality_columns",h->inequalities.cols()},{"inequalities_row_major",std::move(values)},
        {"upper_bounds",Vector(upper_bounds.begin(),upper_bounds.end())}};
}

Json conversion_attempt(registry::PreparedProvider<registry::ConversionPort>& provider,
        const SetHandle& input,const std::string& output_representation,
        const std::string& request_id,std::size_t stage,SetHandle* successful_output=nullptr) {
    ConversionRequest request{{{source_case},{request_id},{"buryatia-diagnostic-"+request_id}},
        input,{output_representation},Assurance::numerical};
    auto admitted=provider.prepare(request);
    if(!std::holds_alternative<registry::PreparedPipeline<registry::ConversionPort>>(admitted)) {
        const auto& rejected=std::get<registry::Rejection>(admitted);
        Json diagnostics=Json::array();
        for(const auto& item:rejected.diagnostics)
            diagnostics.push_back({{"field",item.field},{"explanation",item.explanation}});
        return {{"stage",stage},{"request",request_id},{"output",output_representation},
            {"status","rejected_before_run"},{"diagnostics",std::move(diagnostics)}};
    }
    auto plan=std::get<registry::PreparedPipeline<registry::ConversionPort>>(std::move(admitted));
    auto workspace=std::get<0>(plan.create());
    const auto outcome=workspace->run({});
    if(const auto* result=std::get_if<OperationResult>(&outcome)) {
        if(successful_output)*successful_output=result->output;
        Json row_stats=Json::object();
        if(output_representation=="csl.polyhedron.h") {
            const auto imported=take(sets::from_handle(result->output),"diagnostic H import");
            const auto representation=imported.representation();
            const auto* h=std::get_if<sets::HRepresentation>(&representation);
            if(!h)throw std::runtime_error("diagnostic V-to-H provider returned non-H output");
            double minimum_nonzero=std::numeric_limits<double>::infinity();
            double maximum=0.0;
            std::size_t sub_threshold=0;
            for(std::size_t row=0;row<h->inequalities.rows();++row)
                for(std::size_t column=0;column<h->inequalities.cols();++column) {
                    const auto magnitude=std::abs(h->inequalities(row,column));
                    maximum=std::max(maximum,magnitude);
                    if(magnitude>0.0)minimum_nonzero=std::min(minimum_nonzero,magnitude);
                    if(magnitude>0.0&&magnitude<=1e-12)++sub_threshold;
                }
            for(const auto value:h->upper_bounds.values()) {
                const auto magnitude=std::abs(value);
                maximum=std::max(maximum,magnitude);
                if(magnitude>0.0)minimum_nonzero=std::min(minimum_nonzero,magnitude);
                if(magnitude>0.0&&magnitude<=1e-12)++sub_threshold;
            }
            row_stats={{"inequality_rows",h->inequalities.rows()},
                {"equality_rows",h->equalities.rows()},
                {"minimum_nonzero_abs_coefficient_or_bound",std::isfinite(minimum_nonzero)?minimum_nonzero:0.0},
                {"maximum_abs_coefficient_or_bound",maximum},
                {"nonzero_entries_at_or_below_1e-12",sub_threshold},
                {"original_unscaled_h_rows",h_json(result->output)}};
        }
        return {{"stage",stage},{"request",request_id},{"output",output_representation},
            {"status","completed"},{"provider_evidence",result->evidence.assumptions},
            {"output_diagnostics",std::move(row_stats)}};
    }
    Json diagnostics=Json::array();
    if(const auto* unsupported=std::get_if<Unsupported>(&outcome))
        for(const auto& item:unsupported->diagnostics)
            diagnostics.push_back({{"field",item.field},{"explanation",item.explanation}});
    const auto stopped=std::get_if<OperationStopped>(&outcome);
    return {{"stage",stage},{"request",request_id},{"output",output_representation},
        {"status",stopped?"stopped":"unsupported"},
        {"stop_diagnostics",stopped?stopped->diagnostics:""},{"diagnostics",std::move(diagnostics)}};
}

std::vector<Vector> box_vertices(const SetHandle& set) {
    const auto imported=take(sets::from_handle(set),"box H import");
    const auto representation=imported.representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h||h->inequalities.rows()!=2*dimension||h->inequalities.cols()!=dimension||
       h->upper_bounds.size()!=2*dimension)
        throw std::runtime_error("expected a bounded 4D box H representation");
    for(std::size_t axis=0;axis<dimension;++axis)
        for(std::size_t coordinate=0;coordinate<dimension;++coordinate) {
            const double positive=axis==coordinate?1.0:0.0;
            const double negative=-positive;
            if(h->inequalities(2*axis,coordinate)!=positive||
               h->inequalities(2*axis+1,coordinate)!=negative)
                throw std::runtime_error("box H rows do not match the registered coordinate-slab format");
        }
    std::vector<Vector> result;
    result.reserve(std::size_t{1}<<dimension);
    for(std::size_t mask=0;mask<(std::size_t{1}<<dimension);++mask) {
        Vector point(dimension);
        for(std::size_t axis=0;axis<dimension;++axis)
            point[axis]=(mask&(std::size_t{1}<<axis))?h->upper_bounds[2*axis]:-h->upper_bounds[2*axis+1];
        result.push_back(std::move(point));
    }
    return result;
}

std::vector<Vector> parallelotope_vertices(const SetHandle& set,const Matrix& orientation) {
    const auto imported=take(sets::from_handle(set),"parallelotope H import");
    const auto representation=imported.representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h||h->inequalities.rows()!=2*dimension||h->inequalities.cols()!=dimension||
       h->upper_bounds.size()!=2*dimension||orientation.rows!=dimension||orientation.cols!=dimension)
        throw std::runtime_error("expected a bounded oriented 4D parallelotope H representation");
    std::vector<Vector> result;
    result.reserve(std::size_t{1}<<dimension);
    for(std::size_t mask=0;mask<(std::size_t{1}<<dimension);++mask) {
        std::array<long double,dimension*(dimension+1)> augmented{};
        for(std::size_t row=0;row<dimension;++row) {
            for(std::size_t column=0;column<dimension;++column)
                augmented[row*(dimension+1)+column]=orientation.values[row*dimension+column];
            augmented[row*(dimension+1)+dimension]=(mask&(std::size_t{1}<<row))?
                h->upper_bounds[2*row]:-h->upper_bounds[2*row+1];
        }
        for(std::size_t pivot=0;pivot<dimension;++pivot) {
            std::size_t best=pivot;
            for(std::size_t row=pivot+1;row<dimension;++row)
                if(std::abs(augmented[row*(dimension+1)+pivot])>
                   std::abs(augmented[best*(dimension+1)+pivot]))best=row;
            if(augmented[best*(dimension+1)+pivot]==0.0L)
                throw std::runtime_error("parallelotope orientation is singular");
            for(std::size_t column=pivot;column<=dimension;++column)
                std::swap(augmented[pivot*(dimension+1)+column],augmented[best*(dimension+1)+column]);
            const auto diagonal=augmented[pivot*(dimension+1)+pivot];
            for(std::size_t column=pivot;column<=dimension;++column)
                augmented[pivot*(dimension+1)+column]/=diagonal;
            for(std::size_t row=0;row<dimension;++row)if(row!=pivot) {
                const auto multiplier=augmented[row*(dimension+1)+pivot];
                for(std::size_t column=pivot;column<=dimension;++column)
                    augmented[row*(dimension+1)+column]-=multiplier*augmented[pivot*(dimension+1)+column];
            }
        }
        Vector point(dimension);
        for(std::size_t coordinate=0;coordinate<dimension;++coordinate)
            point[coordinate]=static_cast<double>(augmented[coordinate*(dimension+1)+dimension]);
        result.push_back(std::move(point));
    }
    return result;
}

double box_volume(const SetHandle& set) {
    const auto h=take(sets::from_handle(set),"box H import");
    const auto rep=h.representation();
    const auto* rows=std::get_if<sets::HRepresentation>(&rep);
    if(!rows||rows->inequalities.rows()!=8)return 0.0;
    double volume=1.0;
    for(std::size_t i=0;i<4;++i)volume*=rows->upper_bounds[2*i]+rows->upper_bounds[2*i+1];
    return volume;
}

double parallelotope_volume(const SetHandle& set,const Matrix& orientation) {
    const auto h=take(sets::from_handle(set),"parallelotope H import");
    const auto rep=h.representation();
    const auto* rows=std::get_if<sets::HRepresentation>(&rep);
    if(!rows||rows->inequalities.rows()!=8)return 0.0;
    std::array<long double,16> basis{};
    long double transformed_volume=1.0L;
    for(std::size_t i=0;i<4;++i) {
        transformed_volume*=rows->upper_bounds[2*i]+rows->upper_bounds[2*i+1];
        for(std::size_t j=0;j<4;++j)basis[i*4+j]=orientation.values[i*4+j];
    }
    const auto determinant=std::abs(determinant4(basis));
    if(determinant==0.0L)return 0.0;
    return static_cast<double>(transformed_volume/determinant);
}

Json projection_json(const std::vector<Vector>& points) {
    const std::array<std::array<std::size_t,3>,3> projections{{{{0,1,2}},{{1,2,3}},{{0,1,3}}}};
    Json result=Json::object();
    const std::array<const char*,3> names{"x1_x2_x3","x2_x3_x4","x1_x2_x4"};
    for(std::size_t i=0;i<projections.size();++i)result[names[i]]=points_json(project_points(points,projections[i]));
    return result;
}

Json projection_json_2d(const std::vector<Vector>& points) {
    const std::array<std::array<std::size_t,2>,6> projections{{
        {{0,1}},{{0,2}},{{0,3}},{{1,2}},{{1,3}},{{2,3}}}};
    const std::array<const char*,6> names{"x1_x2","x1_x3","x1_x4","x2_x3","x2_x4","x3_x4"};
    Json result=Json::object();
    for(std::size_t p=0;p<projections.size();++p) {
        Json rows=Json::array();
        for(const auto& point:points)
            rows.push_back({point[projections[p][0]],point[projections[p][1]]});
        result[names[p]]=std::move(rows);
    }
    return result;
}

Json family_record(std::size_t stage,const std::string& family,double volume,double reference_volume,
        std::size_t vertex_count,std::size_t generator_count,std::size_t constraints,
        std::string inclusion,Json represented,Json projections,Json projections_2d,Json support,Json modules) {
    double max_error=0.0;
    double minimum_support_excess=std::numeric_limits<double>::infinity();
    for(const auto& item:support) {
        max_error=std::max(max_error,item.at("absolute_error").get<double>());
        minimum_support_excess=std::min(minimum_support_excess,item.at("support_excess").get<double>());
    }
    const std::string vertex_semantics=family=="box"||family=="parallelotope"?
        "complete 16-corner representation for this full-dimensional affine slab set":
        family=="ellipsoid"?"not applicable to a factor ellipsoid":
        "stored V rows; redundant/non-extreme rows may remain and minimality is not claimed";
    const std::string volume_method=family=="box"?
        "product of four binary64 slab widths":family=="parallelotope"?
        "binary64 slab-width product divided by absolute determinant of fixed orientation":
        family=="ellipsoid"?"binary64 (pi^2/2)*sqrt(det(F*F^T))":
        "binary64 sum of absolute 4x4 generator minors multiplied by 2^4";
    return {{"stage",stage},{"family",family},{"status","completed"},
        {"volume",volume},{"reference_volume",reference_volume},
        {"excess_volume",volume-reference_volume},{"vertex_count",vertex_count},
        {"vertex_count_semantics",vertex_semantics},
        {"volume_method",volume_method},
        {"volume_assurance","floating-point binary64 evaluation; no certified rounding interval"},
        {"generator_count",generator_count},{"constraint_count",constraints},
        {"max_abs_support_error_sampled_directions",max_error},
        {"minimum_sampled_support_excess",std::isfinite(minimum_support_excess)?minimum_support_excess:0.0},
        {"inclusion_check",std::move(inclusion)},{"represented_set",std::move(represented)},
        {"coordinate_projections",std::move(projections)},
        {"coordinate_projections_2d",std::move(projections_2d)},
        {"support_diagnostics",std::move(support)},{"module_invocations",std::move(modules)}};
}

Json run(bool diagnose_v_h=false) {
    using namespace csl::geometry;
    registry::Requirements poly_req;
    poly_req.output.representation={"csl.polyhedron.v"};
    poly_req.output.relation=SetRelation::equivalent;
    auto lp_registration=take(adapters::lp::make_highs_registration(),"HiGHS registration");
    auto qhull_registration=take(adapters::polyhedral::make_qhull_registration(lp_registration),
        "Qhull registration");
    registry::Requirements conversion_req;
    conversion_req.output.representation={"csl.polyhedron.v"};
    conversion_req.output.relation=SetRelation::equivalent;
    auto conversion=prepare<registry::ConversionPort>(std::move(qhull_registration),conversion_req);
    registry::Requirements h_conversion_req;
    h_conversion_req.output.representation={"csl.polyhedron.h"};
    h_conversion_req.output.relation=SetRelation::equivalent;
    auto diagnostic_v_to_h_registration=take(adapters::polyhedral::make_qhull_registration(lp_registration),
        "diagnostic Qhull V-to-H registration");
    auto diagnostic_v_to_h=prepare<registry::ConversionPort>(
        std::move(diagnostic_v_to_h_registration),h_conversion_req);
    auto diagnostic_h_to_v_registration=take(adapters::polyhedral::make_qhull_registration(lp_registration),
        "diagnostic Qhull H-to-V registration");
    auto diagnostic_h_to_v=prepare<registry::ConversionPort>(
        std::move(diagnostic_h_to_v_registration),conversion_req);
    auto lp=prepare<registry::LPPort>(lp_registration);
    auto hull=prepare<registry::HullReducerPort>(geometry::make_lp_hull_reducer_registration());
    auto poly_registration=geometry::make_affine_sum_registration(
        geometry::AffineSumDependencies{std::move(hull),std::move(lp),std::move(conversion)},
        geometry::AffineSumOptions{exact_candidate_limit,labels()});
    PolyPipeline poly_ops{prepare<registry::GeometryPort>(std::move(poly_registration),poly_req)};

    registry::Requirements generator_req;
    generator_req.output.representation={"csl.zonotope"};
    generator_req.output.relation=SetRelation::equivalent;
    GeneratorPipeline generator_ops{prepare<registry::GeometryPort>(
        geometry::generators::make_operation_registration(),generator_req)};
    const auto stages=literal_stages();
    Json stage_models=Json::array();
    for(const auto& stage:stages)stage_models.push_back({{"nominal_state",stage.nominal},
        {"A_row_major",stage.a.values},{"B_row_major",stage.b.values}});
    const Vector initial{1,-1,1,1};
    auto exact=vertices("buryatia-dim4-exact-initial",{initial});
    std::vector<Vector> box_points{initial};
    std::vector<Vector> para_points{initial};
    auto unreduced=generator("buryatia-dim4-zonotope-initial",initial,Matrix{4,0,{}},{});
    auto reduced=generator("buryatia-dim4-reduced-initial",initial,Matrix{4,0,{}},{});
    auto box_set=exact;
    auto para_set=exact;
    auto ellipsoid=take(ellipsoidal::make_factor_ellipsoid(initial,Matrix{4,0,{}}),
        "initial factor ellipsoid");
    const Matrix orientation{4,4,{1,0.25,0,0,0,1,0.25,0,0,0,1,0.25,0,0,0,1}};
    Json stage_records=Json::array();
    Json conversion_diagnostics=Json::array();

    auto record_stage=[&](std::size_t k,const std::vector<Vector>& exact_points,
            const sets::GeneratorSet& exact_generator,const Json& exact_call,
            const std::vector<Vector>* reduced_points,
            const sets::GeneratorSet* reduced_set,const SetHandle* box_output,
            const std::vector<Vector>* box_points,const std::vector<Vector>* para_points,
            const SetHandle* para_output,const FactorEllipsoid& current_ellipse,
            const Json& module_ledger) {
        const double reference_volume=zonotope_volume(exact_generator);
        Json families=Json::array();
        families.push_back(family_record(k,"exact_affine_polytope",reference_volume,reference_volume,
            exact_points.size(),0,0,"registered full-state affine-sum candidate reduction; retained V rows have the same hull",
            {{"kind","v_polytope"},{"dimension",4},{"vertices_ref","exact_reference.vertices"}},
            {{"derived_from","exact_reference.vertices"}},{{"derived_from","exact_reference.vertices"}},
            support_diagnostics(exact_points,nullptr,nullptr,&exact_points),
            {{"provider","csl.geometry.affine-sum"},{"operations",exact_call}}));
        families.push_back(family_record(k,"unreduced_zonotope",reference_volume,reference_volume,
            exact_points.size(),exact_generator.factor_ids().size(),0,"identical to the independent-control affine polytope",
            generator_json(exact_generator),{{"derived_from","exact_reference.vertices"}},
            {{"derived_from","exact_reference.vertices"}},
            support_diagnostics(exact_points,&exact_generator,nullptr,nullptr),
            {{"provider","csl.geometry.generators.operations"},{"operations",module_ledger.at("unreduced")}}));
        const auto reduced_volume=zonotope_volume(*reduced_set);
        families.push_back(family_record(k,"reduced_zonotope",reduced_volume,reference_volume,
            reduced_points->size(),reduced_set->factor_ids().size(),0,"registered generator axis-cover outer inclusion",
            generator_json(*reduced_set),projection_json(*reduced_points),projection_json_2d(*reduced_points),
            support_diagnostics(exact_points,reduced_set,nullptr,nullptr),
            {{"provider","csl.approximation.axis-cover"},
             {"operation",module_ledger.value("reduced",Json::object())}}));
        const auto box_vertex_count=box_points->size();
        families.push_back(family_record(k,"box",box_volume(*box_output),reference_volume,
            box_vertex_count,0,8,"registered support-slab V-to-H containment",
            h_json(*box_output),projection_json(*box_points),projection_json_2d(*box_points),
            support_diagnostics(exact_points,nullptr,nullptr,box_points),
            {{"provider","csl.approximation.box"},{"operation",module_ledger.at("box")}}));
        families.push_back(family_record(k,"parallelotope",parallelotope_volume(*para_output,orientation),reference_volume,
            para_points->size(),0,8,"registered support-slab V-to-H containment",
            h_json(*para_output),projection_json(*para_points),projection_json_2d(*para_points),
            support_diagnostics(exact_points,nullptr,nullptr,para_points),
            {{"provider","csl.approximation.parallelotope"},
             {"orientation_rows",{{1,0.25,0,0},{0,1,0.25,0},{0,0,1,0.25},{0,0,0,1}}},
             {"operation",module_ledger.at("parallelotope")}}));
        families.push_back(family_record(k,"ellipsoid",ellipsoid_volume(current_ellipse),reference_volume,
            0,current_ellipse.factor.cols,0,"factor-affine-image and outer Minkowski factor witness",
            ellipsoid_json(current_ellipse),ellipsoid_projection_json(current_ellipse),
            ellipsoid_projection_json_2d(current_ellipse),
            support_diagnostics(exact_points,nullptr,&current_ellipse,nullptr),
            {{"provider","csl.geometry.ellipsoidal.factor"},{"operations",module_ledger.at("ellipsoid")}}));
        stage_records.push_back({{"stage",k},{"exact_reference",{{"v_candidate_rows",exact_points.size()},
            {"v_candidate_rows_are_minimal",false},{"volume",reference_volume},
            {"vertices",points_json(exact_points)},{"projections_3d",projection_json(exact_points)},
            {"projections_2d",projection_json_2d(exact_points)}}},
            {"families",std::move(families)}});
    };

    // Stage zero is the common singleton; record its native H enclosures too.
    auto initial_zono=take(sets::from_generator_handle(unreduced),"initial zonotope import");
    auto initial_reduced=take(sets::from_generator_handle(reduced),"initial reduced zonotope import");
    const auto initial_box_registration=approximation::make_box_registration({"buryatia-dim4-box-initial"});
    registry::Registry<registry::ApproximationPort> initial_boxes;
    if(initial_boxes.add(initial_box_registration))throw std::runtime_error("initial box registration failed");
    const registry::Method initial_box_method{initial_box_registration.identity.id,initial_box_registration.identity.version};
    const auto initial_para_registration=approximation::make_parallelotope_registration(
        {"buryatia-dim4-parallelotope-initial"},orientation);
    registry::Registry<registry::ApproximationPort> initial_parallelotopes;
    if(initial_parallelotopes.add(initial_para_registration))throw std::runtime_error("initial parallelotope registration failed");
    const registry::Method initial_para_method{initial_para_registration.identity.id,initial_para_registration.identity.version};
    const auto initial_box_out=approximation::run_registered(initial_boxes,initial_box_method,
        {{{source_case},{"box/0"},{"box-output/0"}},exact,{"csl.polyhedron.h"},SetRelation::outer,8,Assurance::numerical},ExecutionContext{});
    const auto* initial_box_enclosed=std::get_if<approximation::EnclosedApproximation>(&initial_box_out);
    if(!initial_box_enclosed)throw std::runtime_error("initial box enclosure failed");
    const auto initial_para_out=approximation::run_registered(initial_parallelotopes,initial_para_method,
        {{{source_case},{"parallelotope/0"},{"parallelotope-output/0"}},exact,{"csl.polyhedron.h"},SetRelation::outer,8,Assurance::numerical},ExecutionContext{});
    const auto* initial_para_enclosed=std::get_if<approximation::EnclosedApproximation>(&initial_para_out);
    if(!initial_para_enclosed)throw std::runtime_error("initial parallelotope enclosure failed");
    box_set=initial_box_enclosed->result.output;
    para_set=initial_para_enclosed->result.output;
    const std::vector<Vector> initial_points{initial};
    Json initial_modules={{"exact",{{"provider","initial singleton"}}},
        {"unreduced",{"initial singleton"}},
        {"reduced",{{"initial singleton"}}},
        {"box",{{"provider",initial_box_registration.identity.id.value+"/"+initial_box_registration.identity.version},
            {"initial_enclosure",basis_name(initial_box_enclosed->basis)}}},
        {"parallelotope",{{"provider",initial_para_registration.identity.id.value+"/"+initial_para_registration.identity.version},
            {"initial_enclosure",basis_name(initial_para_enclosed->basis)}}},
        {"ellipsoid",{"initial singleton factor"}}};
    record_stage(0,initial_points,initial_zono,"initial singleton",&initial_points,&initial_reduced,
        &box_set,&box_points,&para_points,&para_set,ellipsoid,initial_modules);

    for(std::size_t k=0;k<stages.size();++k) {
        const auto& stage=stages[k];
        const auto exact_step=poly_step(poly_ops,exact,stage,k+1);
        exact=exact_step.hull;
        const auto exact_points=v_points(exact);
        if(diagnose_v_h) {
            SetHandle h_output;
            const auto v_to_h=conversion_attempt(diagnostic_v_to_h,exact,"csl.polyhedron.h",
                "diagnostic-v-to-h/"+std::to_string(k+1),k+1,&h_output);
            Json h_to_v={{"stage",k+1},{"status","skipped_no_h_output"}};
            if(v_to_h.at("status")=="completed")
                h_to_v=conversion_attempt(diagnostic_h_to_v,h_output,"csl.polyhedron.v",
                    "diagnostic-h-to-v/"+std::to_string(k+1),k+1);
            conversion_diagnostics.push_back({{"stage",k+1},{"source_rows",exact_points.size()},
                {"v_to_h",v_to_h},{"h_to_v",h_to_v}});
        }

        const auto exact_gen_image=generator_ops.run(AffineImage{unreduced,stage.a,Vector(4,0.0)},
            "unreduced-image-"+std::to_string(k+1));
        const auto control_gen=generator("buryatia-dim4-control-zono-"+std::to_string(k+1),
            Vector(4,0.0),stage.b,{{"dim4-control-"+std::to_string(k+1)+"-1"},
                {"dim4-control-"+std::to_string(k+1)+"-2"}});
        const auto exact_gen_sum=generator_ops.run(MinkowskiSum{exact_gen_image.output,control_gen},
            "unreduced-sum-"+std::to_string(k+1));
        unreduced=exact_gen_sum.output;
        const auto exact_generator=take(sets::from_generator_handle(unreduced),"exact zonotope import");

        const auto reduced_image=generator_ops.run(AffineImage{reduced,stage.a,Vector(4,0.0)},
            "reduced-image-"+std::to_string(k+1));
        const auto reduced_sum=generator_ops.run(MinkowskiSum{reduced_image.output,control_gen},
            "reduced-sum-"+std::to_string(k+1));
        const auto reduce_registration=approximation::make_axis_cover_registration(
            {"buryatia-dim4-reduced-"+std::to_string(k+1)});
        registry::Registry<registry::ApproximationPort> reducers;
        if(reducers.add(reduce_registration))throw std::runtime_error("axis-cover registration failed");
        const registry::Method reduce_method{reduce_registration.identity.id,reduce_registration.identity.version};
        const ApproximationRequest reduce_request{{{source_case},{"axis-cover/"+std::to_string(k+1)},
            {"reduced-output/"+std::to_string(k+1)}},reduced_sum.output,{"csl.zonotope"},
            SetRelation::outer,8,Assurance::numerical};
        const auto reduced_out=approximation::run_registered(reducers,reduce_method,reduce_request,ExecutionContext{});
        const auto* reduced_enclosed=std::get_if<approximation::EnclosedApproximation>(&reduced_out);
        if(!reduced_enclosed)throw std::runtime_error("registered 4D axis-cover reduction did not complete");
        reduced=reduced_enclosed->result.output;
        const auto reduced_generator=take(sets::from_generator_handle(reduced),"reduced zonotope import");
        // The generator provider materializes every finite cube corner. The
        // affine-sum provider then removes non-extreme points for the saved hull.
        const auto factor_count=reduced_generator.factor_ids().size();
        if(factor_count>=20)throw std::runtime_error("reduced zonotope corner quota exceeded");
        const auto corner_count=std::size_t{1}<<factor_count;
        const auto raw_reduced_points=materialize_generator_vertices(reduced,
            std::max<std::size_t>(1,corner_count),std::to_string(k+1));
        const auto reduced_corner_set=vertices("buryatia-dim4-reduced-corners-"+std::to_string(k+1),raw_reduced_points);
        const auto identity_hull=poly_ops.run(AffineImage{reduced_corner_set,
            Matrix{dimension,dimension,{1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1}},Vector(dimension,0.0)},
            "reduced-corner-hull-"+std::to_string(k+1));
        auto reduced_points=v_points(identity_hull.output);

        const auto box_state=vertices("buryatia-dim4-box-state-"+std::to_string(k),box_points);
        const auto box_step=poly_step(poly_ops,box_state,stage,k+1);
        const auto box_input=box_step.hull;
        const auto box_registration=approximation::make_box_registration({"buryatia-dim4-box-"+std::to_string(k+1)});
        registry::Registry<registry::ApproximationPort> boxes;
        if(boxes.add(box_registration))throw std::runtime_error("box registration failed");
        const registry::Method box_method{box_registration.identity.id,box_registration.identity.version};
        const ApproximationRequest box_request{{{source_case},{"box/"+std::to_string(k+1)},
            {"box-output/"+std::to_string(k+1)}},box_input,{"csl.polyhedron.h"},
            SetRelation::outer,8,Assurance::numerical};
        const auto box_out=approximation::run_registered(boxes,box_method,box_request,ExecutionContext{});
        const auto* box_enclosed=std::get_if<approximation::EnclosedApproximation>(&box_out);
        if(!box_enclosed)throw std::runtime_error("registered 4D box enclosure did not complete");
        box_set=box_enclosed->result.output;
        box_points=::box_vertices(box_set);

        const auto para_state=vertices("buryatia-dim4-parallelotope-state-"+std::to_string(k),para_points);
        const auto para_step=poly_step(poly_ops,para_state,stage,k+1);
        const auto para_input=para_step.hull;
        const auto para_registration=approximation::make_parallelotope_registration(
            {"buryatia-dim4-parallelotope-"+std::to_string(k+1)},orientation);
        registry::Registry<registry::ApproximationPort> parallelotopes;
        if(parallelotopes.add(para_registration))throw std::runtime_error("parallelotope registration failed");
        const registry::Method para_method{para_registration.identity.id,para_registration.identity.version};
        const ApproximationRequest para_request{{{source_case},{"parallelotope/"+std::to_string(k+1)},
            {"parallelotope-output/"+std::to_string(k+1)}},para_input,{"csl.polyhedron.h"},
            SetRelation::outer,8,Assurance::numerical};
        const auto para_out=approximation::run_registered(parallelotopes,para_method,para_request,ExecutionContext{});
        const auto* para_enclosed=std::get_if<approximation::EnclosedApproximation>(&para_out);
        if(!para_enclosed)throw std::runtime_error("registered 4D parallelotope enclosure did not complete");
        para_set=para_enclosed->result.output;
        para_points=parallelotope_vertices(para_set,orientation);

        const auto ellipse_image=take(ellipsoidal::affine_image(ellipsoid,stage.a,Vector(4,0.0)),
            "factor ellipsoid affine image");
        Matrix control_factor{4,2,stage.b.values};
        for(auto& value:control_factor.values)value*=std::sqrt(2.0);
        const auto control_ellipse=take(ellipsoidal::make_factor_ellipsoid(Vector(4,0.0),control_factor),
            "control-box ellipsoid");
        const auto left_norm=std::sqrt(std::inner_product(ellipse_image.factor.values.begin(),
            ellipse_image.factor.values.end(),ellipse_image.factor.values.begin(),0.0));
        const auto right_norm=std::sqrt(std::inner_product(control_factor.values.begin(),
            control_factor.values.end(),control_factor.values.begin(),0.0));
        const double beta=left_norm==0.0||right_norm==0.0?1.0:right_norm/left_norm;
        ellipsoid=take(ellipsoidal::outer_minkowski_sum(ellipse_image,control_ellipse,beta),
            "factor ellipsoid Minkowski sum");

        Json module_ledger={{"unreduced",{{"affine_image","csl.geometry.generators.operations"},
            {"affine_image_evidence",exact_gen_image.evidence.assumptions},
            {"minkowski_sum","csl.geometry.generators.operations"},
            {"minkowski_sum_evidence",exact_gen_sum.evidence.assumptions}}},
            {"box",{{"affine_sum","csl.geometry.affine-sum"},
                {"affine_image_evidence",box_step.image.evidence.assumptions},
                {"minkowski_sum_evidence",box_step.sum.evidence.assumptions},
                {"approximation",box_registration.identity.id.value+"/"+box_registration.identity.version},
                {"inclusion_basis",basis_name(box_enclosed->basis)},
                {"inclusion_evidence",box_enclosed->result.evidence.assumptions},
                {"materialize","csl.geometry.affine-sum"}}},
            {"parallelotope",{{"affine_sum","csl.geometry.affine-sum"},
                {"affine_image_evidence",para_step.image.evidence.assumptions},
                {"minkowski_sum_evidence",para_step.sum.evidence.assumptions},
                {"approximation",para_registration.identity.id.value+"/"+para_registration.identity.version},
                {"inclusion_basis",basis_name(para_enclosed->basis)},
                {"inclusion_evidence",para_enclosed->result.evidence.assumptions},
                {"materialize","csl.geometry.affine-sum"}}},
            {"exact",{{"provider","csl.geometry.affine-sum"},
                {"affine_image_evidence",exact_step.image.evidence.assumptions},
                {"minkowski_sum_evidence",exact_step.sum.evidence.assumptions},
                {"hull_materialization",exact_step.materialization}}},
            {"ellipsoid",{{"affine_image","csl.geometry.ellipsoidal.factor-affine/1"},
                {"control_box_outer","csl.geometry.ellipsoidal.factor-box/1"},
                {"outer_sum","csl.geometry.ellipsoidal.factor-minkowski/1"},
                {"beta",beta},{"beta_policy","Frobenius norm ratio; trace-minimizing within the selected matrix bound"}}}};
        const auto reduced_modules=Json{{"reduced_image","csl.geometry.generators.operations"},
            {"reduced_image_evidence",reduced_image.evidence.assumptions},
            {"minkowski_sum","csl.geometry.generators.operations"},
            {"minkowski_sum_evidence",reduced_sum.evidence.assumptions},
            {"reduction",reduce_registration.identity.id.value+"/"+reduce_registration.identity.version},
            {"budget",8},{"admission_basis",basis_name(reduced_enclosed->basis)},
            {"inclusion_evidence",reduced_enclosed->result.evidence.assumptions},
            {"generator_v_conversion","csl.geometry.generators.v-conversion/1.0.0"},
            {"materialized_corner_count",raw_reduced_points.size()},
            {"hull_materialization",{{"provider","csl.geometry.affine-sum"},
                {"operation_evidence",identity_hull.evidence.assumptions}}}};
        module_ledger["reduced"]=reduced_modules;
        record_stage(k+1,exact_points,exact_generator,module_ledger["exact"],
            &reduced_points,&reduced_generator,&box_set,&box_points,&para_points,&para_set,
            ellipsoid,module_ledger);
        auto& families=stage_records.back()["families"];
        families[2]["module_invocations"]=reduced_modules;
        families[3]["module_invocations"]["operation"]=module_ledger["box"];
        families[4]["module_invocations"]["operation"]=module_ledger["parallelotope"];
    }

    Json report={{"schema","csl.buryatia.recursive-approximation-4d/1"},
        {"case_id","buryatia-dim4-matlab-literal-affine/1"},
        {"source_variant_id","buryatia-dim4-literal-script-affine/1"},
        {"source_sha256","f1b9868dac256a45f144ee5192ec8b789548b34c2be6be094005bcef8dc7293a"},
        {"state_dimension",4},{"control_dimension",2},{"intervals",7},
        {"stage_models",std::move(stage_models)},
        {"state_order",{"deviation x1","deviation x2","deviation x3","deviation x4"}},
        {"coordinate_projections",{{"x1_x2_x3",{"x1","x2","x3"}},
            {"x2_x3_x4",{"x2","x3","x4"}},{"x1_x2_x4",{"x1","x2","x4"}}}},
        {"reference",{{"kind","independent binary64 affine reconstruction"},
            {"terminal_vertex_count",756},{"terminal_volume",40808.165574887396},
            {"assurance","numerical binary64; not a validated rounding certificate"},
            {"reported_manuscript_table",{{"vertices",756},{"volume_rounded",40808.17},
                {"note","The manuscript model is 8-step and has a different printed A coefficient; numeric agreement alone does not establish figure provenance."}}}}},
        {"comparison_scope","literal 7-update affine script recurrence only; no nonlinear enclosure, feedback, minimax or performance claim"},
        {"candidate_policy",{{"exact_affine_sum_candidate_limit",exact_candidate_limit},
            {"derivation","4 control corners per update across 7 updates gives a conservative 4^7 candidate cap."}}},
        {"records",std::move(stage_records)}};
    if(diagnose_v_h)report["conversion_diagnostics"]=std::move(conversion_diagnostics);
    return report;
}
}

int main(int argc,char** argv) try {
    const std::string mode=argc>1?argv[1]:"--dim4-literal-affine";
    if(argc>2||(mode!="--dim4-literal-affine"&&mode!="--diagnose-v-h"))
        throw std::runtime_error("usage: csl_buryatia_dim4_report [--dim4-literal-affine|--diagnose-v-h]");
    std::cout<<std::setprecision(std::numeric_limits<double>::max_digits10)<<run(mode=="--diagnose-v-h").dump(2)<<'\n';
    return 0;
} catch(const std::exception& error) {
    std::cerr<<error.what()<<'\n';
    return 1;
}
