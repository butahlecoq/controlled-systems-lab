#include <csl/geometry/approximation.hpp>
#include <csl/geometry/ellipsoidal.hpp>
#include <csl/sets/data.hpp>

#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string_view>

using namespace csl;
using namespace csl::geometry::approximation;
using namespace csl::geometry::ellipsoidal;

namespace {
SetHandle v_set(std::string_view id,Matrix vertices) {
    const auto points=numeric::snapshot(vertices);
    const auto rays=numeric::snapshot(Matrix{0,2,{}});
    if(!std::holds_alternative<numeric::MatrixView>(points) ||
       !std::holds_alternative<numeric::MatrixView>(rays))
        throw std::runtime_error("Invalid APP-04 input matrix");
    const auto made=sets::make_v({{std::string(id)},2,{"x","y"}},
        {std::get<numeric::MatrixView>(points),std::get<numeric::MatrixView>(rays)});
    if(!std::holds_alternative<sets::SetData>(made))
        throw std::runtime_error("Invalid APP-04 V input");
    return std::get<sets::SetData>(made).as_handle();
}
struct Case {
    std::string_view name;
    ApproximationRequest request;
    registry::Registry<registry::ApproximationPort> registry;
    registry::Method method;
    Matrix vertices;
    Matrix orientation;
    Vector center;
    Vector projected_bounds;
    int vertex_count;
};
Case square(bool rotated) {
    const auto name=rotated?"square-diagonal":"square-axis";
    const Matrix vertices{4,2,{-1,-1,1,-1,1,1,-1,1}};
    const Matrix orientation=rotated?Matrix{2,2,{1,1,1,-1}}:Matrix{2,2,{1,0,0,1}};
    const Vector bounds=rotated?Vector{2,2}:Vector{1,1};
    const registry::Method method{{rotated?"app04.report.diagonal":"app04.report.axis"},"1"};
    Case item{name,{{{"app04-report"},{std::string(name)},{"literal-square"}},
        v_set(name,vertices),{"csl.ellipsoid.directional2d"},SetRelation::outer,1,
        Assurance::numerical},{},method,vertices,orientation,{0,0},bounds,4};
    if(item.registry.add(make_directional_ellipsoid_registration(method,
        {std::string(name)+"-ellipse"},orientation)))
        throw std::runtime_error("APP-04 registration failed");
    return item;
}
Case segment() {
    const Matrix vertices{2,2,{-1,0,1,0}};
    const Matrix orientation{2,2,{1,0,0,1}};
    const registry::Method method{{"app04.report.segment"},"1"};
    Case item{"horizontal-segment",{{{"app04-report"},{"horizontal-segment"},{"literal-segment"}},
        v_set("horizontal-segment",vertices),{"csl.ellipsoid.directional2d"},
        SetRelation::outer,1,Assurance::numerical},{},method,vertices,orientation,
        {0,0},{1,0},2};
    if(item.registry.add(make_directional_ellipsoid_registration(method,
        {"segment-ellipse"},orientation)))
        throw std::runtime_error("APP-04 registration failed");
    return item;
}
bool verify(const Case& item,const RunOutcome& outcome,Vector& radii) {
    const auto* enclosed=std::get_if<EnclosedApproximation>(&outcome);
    if(!enclosed || enclosed->basis!=StructuralBasis::v_ellipsoid_containment ||
       enclosed->result.relation!=SetRelation::outer ||
       enclosed->result.evidence.reference.identity!=item.request.identity ||
       enclosed->result.evidence.error_bound)return false;
    const auto imported=from_ellipsoid_handle(enclosed->result.output);
    const auto* ellipse=std::get_if<EllipsoidSet>(&imported);
    if(!ellipse || ellipse->center()!=item.center ||
       ellipse->orientation().values!=item.orientation.values ||
       ellipse->projected_bounds()!=item.projected_bounds ||
       ellipse->coordinate_labels()!=std::vector<std::string>{"x","y"})return false;
    radii=ellipse->radii();
    for(std::size_t row=0;row<2;++row) {
        if(item.projected_bounds[row]==0) {
            if(radii[row]!=0)return false;
        } else if(!std::isfinite(radii[row]) ||
                  static_cast<long double>(radii[row])*radii[row] <
                  2.0L*item.projected_bounds[row]*item.projected_bounds[row])return false;
    }
    // Independent literal oracle: all stored vertices satisfy the implicit
    // equation, including an equality for each zero-radius direction.
    for(std::size_t vertex=0;vertex<item.vertices.rows;++vertex) {
        long double squared=0;
        for(std::size_t row=0;row<2;++row) {
            long double projection=0;
            for(std::size_t column=0;column<2;++column)
                projection+=item.orientation.values[row*2+column]*
                    (item.vertices.values[vertex*2+column]-item.center[column]);
            if(radii[row]==0) {
                if(projection!=0)return false;
            } else {
                const auto term=projection/radii[row];
                squared+=term*term;
            }
        }
        if(squared>1.0L)return false;
    }
    return true;
}
bool batch(const Case& item,std::string_view phase,int repetition,int calls) {
    std::chrono::nanoseconds elapsed{};
    Vector radii;
    for(int index=0;index<calls;++index) {
        const auto start=std::chrono::steady_clock::now();
        const auto result=run_registered(item.registry,item.method,item.request,ExecutionContext{});
        const auto end=std::chrono::steady_clock::now();
        elapsed+=std::chrono::duration_cast<std::chrono::nanoseconds>(end-start);
        if(!verify(item,result,radii))return false;
    }
    std::cout<<phase<<','<<item.name<<','<<repetition<<','<<calls
             <<",enclosed,true,"<<elapsed.count()<<",v_ellipsoid,"<<item.vertex_count
             <<','<<radii[0]<<','<<radii[1]<<'\n';
    return true;
}
}

int main(int argc,char** argv) {
    if(argc!=2 || (std::string_view(argv[1])!="smoke" &&
                   std::string_view(argv[1])!="measure"))return EXIT_FAILURE;
    std::cout<<std::setprecision(std::numeric_limits<double>::max_digits10);
    const std::array<Case,3> cases{square(false),square(true),segment()};
    std::cout<<"phase,case,repetition,calls,status,verified,elapsed_ns,basis,vertices,radius_x,radius_y\n";
    if(std::string_view(argv[1])=="smoke") {
        for(const auto& item:cases)if(!batch(item,"smoke",0,1))return EXIT_FAILURE;
    } else {
        for(const auto& item:cases)if(!batch(item,"warmup",0,100))return EXIT_FAILURE;
        for(int repetition=0;repetition<7;++repetition)
            for(int offset=0;offset<3;++offset)
                if(!batch(cases[(offset+repetition)%3],"trial",repetition,100))
                    return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
