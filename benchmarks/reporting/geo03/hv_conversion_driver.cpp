#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/sets/data.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <variant>
#include <vector>

using namespace csl;
using namespace csl::registry;
using namespace csl::adapters::lp;
using namespace csl::adapters::polyhedral;

namespace {
using Clock = std::chrono::steady_clock;
struct Fixture {
    std::string id;
    std::size_t dimension{};
    Matrix a;
    Vector b;
    Matrix e;
    Vector f;
    Matrix vertices;
    Matrix rays;
    std::vector<std::array<double,2>> interior;
    std::vector<std::array<double,2>> outside;
    std::vector<std::array<double,2>> directions;
    std::vector<double> supports;
    std::size_t expected_vertices{};
};

template<class T,class... Rest> T require(std::variant<T,Rest...> value) {
    if (!std::holds_alternative<T>(value)) throw std::runtime_error("fixture construction failed");
    return std::get<T>(std::move(value));
}
numeric::MatrixView matrix_view(const Matrix& value) { return require<numeric::MatrixView>(numeric::snapshot(value)); }
numeric::VectorView vector_view(const Vector& value) { return require<numeric::VectorView>(numeric::snapshot_vector(value)); }

std::vector<Fixture> fixtures() {
    return {
        {"square",2,{4,2,{1,0,-1,0,0,1,0,-1}},{1,0,1,0},{0,2,{}},{},
         {4,2,{0,0,1,0,0,1,1,1}},{0,2,{}},{{0.5,0.5}},{{2,0},{0,2}},
         {{1,0},{-1,0},{0,1},{0,-1},{1,1}}, {1,0,1,0,2},4},
        {"simplex",2,{3,2,{-1,0,0,-1,1,1}},{0,0,1},{0,2,{}},{},
         {3,2,{0,0,1,0,0,1}},{0,2,{}},{{0.25,0.25}},{{0.75,0.75},{-0.1,0}},
         {{1,0},{0,1},{-1,-1},{1,2}}, {1,1,0,2},3},
        {"embedded-segment",2,{2,2,{1,0,-1,0}},{2,1},{1,2,{0,1}},{0},
         {2,2,{-1,0,2,0}},{0,2,{}},{{0,0}},{{0,1},{-1.125,0},{2.125,0}},
         {{1,0},{-1,0},{0,1},{0,-1}}, {2,1,0,0},2},
        {"singleton",2,{0,2,{}},{},{2,2,{1,0,0,1}},{2,-3},
         {1,2,{2,-3}},{0,2,{}},{{2,-3}},{{2,-2},{3,-3}},
         {{4,1},{-4,-1}}, {5,-5},1}
    };
}

sets::SetData make_input(const Fixture& fixture,bool h_input) {
    const sets::Description description{{fixture.id+(h_input?"-H":"-V")},fixture.dimension,{}};
    if (h_input) return require<sets::SetData>(sets::make_h(description,
        {matrix_view(fixture.a),vector_view(fixture.b),matrix_view(fixture.e),vector_view(fixture.f)}));
    return require<sets::SetData>(sets::make_v(description,{matrix_view(fixture.vertices),matrix_view(fixture.rays)}));
}

ConversionRequest make_request(SetHandle input,std::string output,const Fixture& fixture,
                               bool h_input,std::size_t round,bool warmup) {
    const std::string name=fixture.id+(h_input?"-H-to-V":"-V-to-H");
    const std::string token=name+"-"+(warmup?"warmup":std::to_string(round));
    return {{{"geo03-report"},{token},{"contract-fixture"}},std::move(input),{std::move(output)},Assurance::numerical};
}

Requirements requirements(std::string representation) {
    Requirements result;
    result.output.representation={std::move(representation)};
    result.output.assurance=Assurance::numerical;
    result.output.relation=SetRelation::equivalent;
    return result;
}
ExecutionContext context() { return {{},{},{},{1e-8,1e-8},"geo03-report"}; }

bool member(const sets::HRepresentation& h,const std::array<double,2>& x) {
    constexpr double tolerance=1e-7;
    for (std::size_t i=0;i<h.inequalities.rows();++i) {
        const double value=h.inequalities(i,0)*x[0]+h.inequalities(i,1)*x[1];
        if (value>h.upper_bounds[i]+tolerance) return false;
    }
    for (std::size_t i=0;i<h.equalities.rows();++i) {
        const double value=h.equalities(i,0)*x[0]+h.equalities(i,1)*x[1];
        if (std::abs(value-h.equality_values[i])>tolerance) return false;
    }
    return true;
}

double support(const sets::VRepresentation& v,const std::array<double,2>& direction) {
    double result=-std::numeric_limits<double>::infinity();
    for (std::size_t i=0;i<v.vertices.rows();++i)
        result=std::max(result,direction[0]*v.vertices(i,0)+direction[1]*v.vertices(i,1));
    return result;
}

struct Outcome {
    std::size_t h_rows{},h_equalities{},v_vertices{},v_rays{};
    std::size_t oracle_count{};
    bool oracle_ok{};
};

Outcome verify(const Fixture& fixture,bool h_input,const sets::SetData& output) {
    Outcome result;
    const auto rep=output.representation();
    if (h_input) {
        if (!std::holds_alternative<sets::VRepresentation>(rep)) throw std::runtime_error("unexpected output representation");
        const auto& v=std::get<sets::VRepresentation>(rep);
        result.v_vertices=v.vertices.rows(); result.v_rays=v.rays.rows();
        bool passed=result.v_vertices==fixture.expected_vertices&&result.v_rays==0;
        for (std::size_t i=0;i<v.vertices.rows();++i) {
            const std::array<double,2> point{v.vertices(i,0),v.vertices(i,1)};
            passed=passed&&member(std::get<sets::HRepresentation>(make_input(fixture,true).representation()),point);
            ++result.oracle_count;
        }
        for (std::size_t i=0;i<fixture.directions.size();++i) {
            const double observed=support(v,fixture.directions[i]);
            passed=passed&&std::abs(observed-fixture.supports[i])<=1e-7;
            ++result.oracle_count;
        }
        result.oracle_ok=passed;
    } else {
        if (!std::holds_alternative<sets::HRepresentation>(rep)) throw std::runtime_error("unexpected output representation");
        const auto& h=std::get<sets::HRepresentation>(rep);
        result.h_rows=h.inequalities.rows(); result.h_equalities=h.equalities.rows();
        bool passed=true;
        for (std::size_t i=0;i<fixture.vertices.rows;++i) {
            const std::array<double,2> point{fixture.vertices.values[i*fixture.vertices.cols],fixture.vertices.values[i*fixture.vertices.cols+1]};
            passed=passed&&member(h,point); ++result.oracle_count;
        }
        for (const auto& point:fixture.interior) { passed=passed&&member(h,point); ++result.oracle_count; }
        for (const auto& point:fixture.outside) { passed=passed&&!member(h,point); ++result.oracle_count; }
        for (std::size_t i=0;i<fixture.directions.size();++i) {
            const double from_vertices=support(std::get<sets::VRepresentation>(make_input(fixture,false).representation()),fixture.directions[i]);
            passed=passed&&std::abs(from_vertices-fixture.supports[i])<=1e-7;
            ++result.oracle_count;
            double best=-std::numeric_limits<double>::infinity();
            std::array<double,2> witness{};
            for (std::size_t vertex=0;vertex<fixture.vertices.rows;++vertex) {
                const double x=fixture.vertices.values[vertex*fixture.vertices.cols];
                const double y=fixture.vertices.values[vertex*fixture.vertices.cols+1];
                const double value=fixture.directions[i][0]*x+fixture.directions[i][1]*y;
                if (value>best) { best=value; witness={x,y}; }
            }
            passed=passed&&member(h,witness); ++result.oracle_count;
            const double norm2=fixture.directions[i][0]*fixture.directions[i][0]+fixture.directions[i][1]*fixture.directions[i][1];
            const std::array<double,2> beyond{witness[0]+0.1*fixture.directions[i][0]/norm2,
                                               witness[1]+0.1*fixture.directions[i][1]/norm2};
            passed=passed&&!member(h,beyond); ++result.oracle_count;
        }
        for (const auto& point:fixture.outside) { passed=passed&&!member(h,point); ++result.oracle_count; }
        result.oracle_ok=passed;
    }
    return result;
}

struct Trial {
    std::string fixture,direction;
    std::string input_representation,output_representation;
    std::size_t round{};
    std::size_t ambient_dimension{},input_inequalities{},input_equalities{},input_vertices{},input_rays{};
    std::uint64_t preparation_ns{},workspace_ns{},run_ns{},total_ns{};
    Outcome output;
};

Trial run_one(const Fixture& fixture,bool h_input,std::size_t round,bool warmup,bool verify_output=true) {
    Trial trial;
    trial.fixture=fixture.id;
    trial.direction=h_input?"H-to-V":"V-to-H";
    trial.input_representation=h_input?"H":"V";
    trial.output_representation=h_input?"V":"H";
    trial.round=round;
    trial.ambient_dimension=fixture.dimension;
    trial.input_inequalities=h_input?fixture.a.rows:0;
    trial.input_equalities=h_input?fixture.e.rows:0;
    trial.input_vertices=h_input?0:fixture.vertices.rows;
    trial.input_rays=h_input?0:fixture.rays.rows;
    auto total_start=Clock::now();
    auto conversion=require<Registration<ConversionPort>>(make_qhull_registration(require<Registration<LPPort>>(make_highs_registration())));
    Registry<ConversionPort> registry;
    if (registry.add(std::move(conversion)).has_value()) throw std::runtime_error("conversion registration failed");
    const auto input=make_input(fixture,h_input).as_handle();
    const auto request=make_request(input,h_input?"csl.polyhedron.v":"csl.polyhedron.h",fixture,h_input,round,warmup);
    auto prep_start=Clock::now();
    auto selected=select(registry,{{"csl.conversion.qhull"},{}},request,
                         requirements(h_input?"csl.polyhedron.v":"csl.polyhedron.h"));
    auto prepared=prepare_pipeline(std::move(selected));
    trial.preparation_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-prep_start).count();
    if (!std::holds_alternative<PreparedPipeline<ConversionPort>>(prepared)) throw std::runtime_error("conversion selection/preparation failed");
    auto workspace_start=Clock::now();
    auto [worker]=std::get<PreparedPipeline<ConversionPort>>(prepared).create();
    trial.workspace_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-workspace_start).count();
    auto run_start=Clock::now();
    auto result=worker->run(context());
    trial.run_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-run_start).count();
    trial.total_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-total_start).count();
    if (!std::holds_alternative<OperationResult>(result)) throw std::runtime_error("conversion did not return a supported result");
    auto output=require<sets::SetData>(sets::from_handle(std::get<OperationResult>(result).output));
    if (verify_output) {
        trial.output=verify(fixture,h_input,output);
        if (!trial.output.oracle_ok) throw std::runtime_error("independent membership/support oracle failed");
    } else {
        const auto rep=output.representation();
        if (const auto* v=std::get_if<sets::VRepresentation>(&rep)) {
            trial.output.v_vertices=v->vertices.rows(); trial.output.v_rays=v->rays.rows();
            for (std::size_t i=0;i<v->vertices.rows();++i)
                trial.output.oracle_count+=static_cast<std::size_t>(std::abs(v->vertices(i,0))*1000.0)+1;
        } else if (const auto* h=std::get_if<sets::HRepresentation>(&rep)) {
            trial.output.h_rows=h->inequalities.rows(); trial.output.h_equalities=h->equalities.rows();
            trial.output.oracle_count=h->inequalities.rows()+h->equalities.rows()+1;
        } else throw std::runtime_error("profile output representation was not polyhedral");
        trial.output.oracle_ok=true;
    }
    return trial;
}

void print_csv_header() {
    std::cout << "fixture,direction,round,converter_id,converter_version,lp_backend_id,lp_backend_version,"
                 "ambient_dimension,input_representation,output_representation,input_inequalities,input_equalities,input_vertices,input_rays,"
                 "preparation_ns,workspace_creation_ns,run_ns,total_ns,"
                 "output_inequalities,output_equalities,output_vertices,output_rays,oracle_checks,oracle_passed\n";
}
void print_trial(const Trial& t) {
    std::cout << t.fixture << ',' << t.direction << ',' << t.round << ",csl.conversion.qhull,1.0.0+qhull.8.0.2,"
              << "csl.lp.highs,1.0.0+highs.1.11.0," << t.ambient_dimension << ',' << t.input_representation << ','
              << t.output_representation << ',' << t.input_inequalities << ',' << t.input_equalities << ','
              << t.input_vertices << ',' << t.input_rays << ',' << t.preparation_ns << ','
              << t.workspace_ns << ',' << t.run_ns << ',' << t.total_ns << ',' << t.output.h_rows << ','
              << t.output.h_equalities << ',' << t.output.v_vertices << ',' << t.output.v_rays << ','
              << t.output.oracle_count << ',' << (t.output.oracle_ok?"true":"false") << '\n';
}

std::size_t parse_count(const char* value) {
    const auto number=std::stoull(value);
    if (number==0||number>10000) throw std::runtime_error("count must be in [1,10000]");
    return static_cast<std::size_t>(number);
}
}

int main(int argc,char** argv) {
    try {
        std::size_t repetitions=7,warmups=1,profile_rounds=0;
        for (int i=1;i<argc;++i) {
            const std::string arg=argv[i];
            if (arg=="--repetitions"&&i+1<argc) repetitions=parse_count(argv[++i]);
            else if (arg=="--warmups"&&i+1<argc) warmups=parse_count(argv[++i]);
            else if (arg=="--profile-rounds"&&i+1<argc) profile_rounds=parse_count(argv[++i]);
            else throw std::runtime_error("usage: csl_geo03_conversion_report [--repetitions N --warmups N | --profile-rounds N]");
        }
        const auto cases=fixtures();
        if (profile_rounds) {
            std::uint64_t consumed=0;
            for (std::size_t round=0;round<profile_rounds;++round)
                for (const auto& fixture:cases) for (bool h_input:{true,false}) {
                    const auto trial=run_one(fixture,h_input,round,false,false);
                    consumed+=trial.output.oracle_count+trial.output.v_vertices+trial.output.h_rows;
                }
            std::cerr << "profile_operations=" << profile_rounds*cases.size()*2 << " consumed=" << consumed << '\n';
            return 0;
        }
        print_csv_header();
        for (const auto& fixture:cases) for (bool h_input:{true,false})
            for (std::size_t i=0;i<warmups;++i) (void)run_one(fixture,h_input,i,true);
        for (std::size_t round=0;round<repetitions;++round) {
            const bool reverse=(round%2)!=0;
            for (std::size_t offset=0;offset<cases.size()*2;++offset) {
                const std::size_t index=reverse?cases.size()*2-1-offset:offset;
                const bool h_input=index%2==0;
                const auto& fixture=cases[index/2];
                print_trial(run_one(fixture,h_input,round,false));
            }
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "geo03_report_error=" << error.what() << '\n';
        return 2;
    }
}
