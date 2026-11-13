#include "native_catalogue_projection.hpp"

#include <csl/geometry/generators.hpp>
#include <csl/model/linear_system.hpp>
#include <csl/model/spatial_flight_catalogue.hpp>

#include <cmath>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <numbers>

namespace {
using namespace csl;
using native_catalogue_example::CapturedCase;
using native_catalogue_example::Cloud;

template<class T, class... Errors> T take(std::variant<T, Errors...> result) {
    if (auto* value=std::get_if<T>(&result)) return std::move(*value);
    throw std::runtime_error("Native spatial-flight operation failed");
}
Matrix own(const numeric::MatrixView& view) {
    Matrix result{view.rows(),view.cols(),{}};
    result.values.reserve(view.rows()*view.cols());
    for (std::size_t i=0;i<view.rows();++i)
        for (std::size_t j=0;j<view.cols();++j) result.values.push_back(view(i,j));
    return result;
}
std::vector<std::pair<std::size_t,std::size_t>> planes() {
    return {{0,1},{1,2},{3,4},{4,5},{6,7},{7,8}};
}
Cloud projection_witnesses(const sets::GeneratorSet& set,std::size_t first,std::size_t second) {
    Cloud witnesses{set.center()};
    const auto& generators=set.generators();
    for (std::size_t j=0;j<generators.cols;++j) {
        Cloud candidates,projected;
        for (const auto& point:witnesses) for (double sign:{-1.0,1.0}) {
            auto next=point;
            for (std::size_t i=0;i<next.size();++i) next[i]+=sign*generators.values[i*generators.cols+j];
            projected.push_back({next[first],next[second]});
            candidates.push_back(std::move(next));
        }
        const auto hull=native_catalogue_example::projected_hull(projected);
        witnesses.clear();
        for (const auto index:hull.vertex_indices) witnesses.push_back(std::move(candidates[index]));
    }
    return witnesses;
}
long double support(const sets::GeneratorSet& set,const Vector& direction) {
    long double value=0;
    for (std::size_t i=0;i<direction.size();++i) value+=direction[i]*set.center()[i];
    const auto& generators=set.generators();
    for (std::size_t j=0;j<generators.cols;++j) {
        long double projection=0;
        for (std::size_t i=0;i<direction.size();++i)
            projection+=direction[i]*generators.values[i*generators.cols+j];
        value+=std::abs(projection);
    }
    return value;
}
long double independent_support(const model::LinearSystem& system,std::size_t stage,
                                const Vector& direction) {
    constexpr double initial_radii[]{0.1,0.02,0.02,0.001,0.001,0.001,0.0002,0.0002,0.0002};
    Vector dual=direction;
    long double value=0;
    for (std::size_t reverse=stage;reverse>0;--reverse) {
        const auto maps=take(system.stage({reverse-1}));
        Vector previous(9,0);
        for (std::size_t column=0;column<9;++column)
            for (std::size_t row=0;row<9;++row) previous[column]+=maps.A(row,column)*dual[row];
        for (std::size_t column=0;column<3;++column) {
            long double coefficient=0;
            for (std::size_t row=0;row<9;++row) coefficient+=maps.B(row,column)*dual[row];
            value+=0.001L*std::abs(coefficient);
        }
        dual=std::move(previous);
    }
    for (std::size_t i=0;i<9;++i) value+=initial_radii[i]*std::abs(dual[i]);
    return value;
}
std::vector<Vector> support_directions() {
    std::vector<Vector> result;
    for (std::size_t i=0;i<9;++i) {
        Vector d(9,0);d[i]=1;result.push_back(d);
    }
    for (std::size_t i=0;i<9;++i) for (std::size_t j=i+1;j<9;++j)
        for (double si:{-1.0,1.0}) for (double sj:{-1.0,1.0}) {
            Vector d(9,0);d[i]=si;d[j]=sj;result.push_back(d);
        }
    return result;
}
void write_capture(const std::filesystem::path& output,const std::vector<CapturedCase>& captures) {
    for (std::size_t i=0;i<captures.size();++i) for (bool print:{false,true}) {
        const auto stem="spatial-flight-plane-"+std::to_string(i+1)+(print?"-print.svg":"-screen.svg");
        native_catalogue_example::write_svg(output/stem,captures,print,std::pair{std::size_t{i},std::size_t{0}});
    }
}
}

int main(int argc,char** argv) try {
    if (argc>2 || (argc==2 && std::string_view(argv[1]).starts_with("--")))
        throw std::runtime_error("Usage: native_spatial_flight [new-output-directory]");
    const auto data=take(model::catalogue::make_spatial_flight_case(
        "spatial-flight/b-consistent-body9-synthetic/1"));
    const auto system=take(model::snapshot(data.reachability.model,data.reachability.time_grid));
    std::vector<sets::GeneratorSet> reachable{data.reachability.initial};
    for (std::size_t k=0;k<system.horizon();++k) {
        const auto stage=take(system.stage({k}));
        const auto prefix=std::string(data.reachability.info.id)+"/stage/"+std::to_string(k+1);
        auto state=take(geometry::generators::affine_image(reachable.back(),own(stage.A),
            Vector(stage.offset.values().begin(),stage.offset.values().end()),{prefix+"/state-image"}));
        auto control=take(geometry::generators::affine_image(data.reachability.controls[k],own(stage.B),
            Vector(9,0),{prefix+"/control-image"}));
        reachable.push_back(take(geometry::generators::minkowski_sum(state,control,{prefix+"/reachable"})));
    }
    std::optional<std::filesystem::path> output;
    std::ofstream supports,generators,projection_output,reference,jacobians,parameter_output,discretization_output;
    if (argc==2) {
        output=std::filesystem::path(argv[1]);
        if (!std::filesystem::create_directory(*output)) throw std::runtime_error("Output directory must be new");
        supports.open(*output/"full-state-support-checks.csv");
        generators.open(*output/"full-state-generators.csv");
        projection_output.open(*output/"projection-boundary-witnesses.csv");
        reference.open(*output/"nonlinear-reference.csv");
        jacobians.open(*output/"endpoint-jacobians.csv");
        parameter_output.open(*output/"synthetic-parameters.csv");
        discretization_output.open(*output/"discretization-receipt.csv");
        for (auto* stream:{&supports,&generators,&projection_output,&reference,&jacobians,&parameter_output,&discretization_output}) {
            stream->exceptions(std::ios::badbit|std::ios::failbit);
            *stream<<std::setprecision(17);
        }
        supports<<"stage,direction,d0,d1,d2,d3,d4,d5,d6,d7,d8,native_support,independent_support,absolute_difference\n";
        generators<<"stage,kind,factor_id,coordinate,value\n";
        projection_output<<"stage,plane,point_id,x0,x1,x2,x3,x4,x5,x6,x7,x8\n";
        reference<<"stage,time,vx,vy,vz,phi,psi,theta,omega_x,omega_y,omega_z\n";
        jacobians<<"stage,kind,row,column,value\n";
        parameter_output<<"name,value\n";
        const auto& p=data.parameters;
        const std::pair<std::string_view,double> parameters[]{
            {"mass_kg",p.mass},{"inertia_x_kg_m2",p.principal_inertia[0]},
            {"inertia_y_kg_m2",p.principal_inertia[1]},{"inertia_z_kg_m2",p.principal_inertia[2]},
            {"density_kg_m3",p.density},{"reference_area_m2",p.reference_area},
            {"reference_length_m",p.reference_length},{"gravity_m_s2",p.gravity},{"thrust_n",p.thrust},
            {"cx0",p.cx0},{"cx_alpha_squared",p.cx_alpha_squared},{"cx_beta_squared",p.cx_beta_squared},
            {"cy0",p.cy0},{"cy_alpha",p.cy_alpha},{"cy_beta",p.cy_beta},{"cy_u1",p.cy_u1},{"cy_u2",p.cy_u2},
            {"cz_beta",p.cz_beta},{"cz_alpha",p.cz_alpha},{"cz_u1",p.cz_u1},{"cz_u2",p.cz_u2},
            {"moment_alpha_x",p.moment_alpha[0]},{"moment_alpha_y",p.moment_alpha[1]},{"moment_alpha_z",p.moment_alpha[2]},
            {"moment_beta_x",p.moment_beta[0]},{"moment_beta_y",p.moment_beta[1]},{"moment_beta_z",p.moment_beta[2]}};
        for (const auto& [name,value]:parameters) parameter_output<<name<<','<<value<<'\n';
        for (std::size_t row=0;row<3;++row) for (std::size_t col=0;col<3;++col) {
            parameter_output<<"moment_rate_"<<row<<col<<','<<p.moment_rate[row*3+col]<<'\n';
            parameter_output<<"moment_control_"<<row<<col<<','<<p.moment_control[row*3+col]<<'\n';
        }
        discretization_output<<"stage,start_time,end_time,accepted_steps,rejected_steps,max_local_error_estimate\n";
        for (std::size_t i=0;i<data.discretization.stages.size();++i) {
            const auto& receipt=data.discretization.stages[i];
            discretization_output<<i<<','<<receipt.start_time<<','<<receipt.end_time<<','
                <<receipt.accepted_steps<<','<<receipt.rejected_steps<<','<<receipt.max_local_error_estimate<<'\n';
        }
        for (std::size_t k=0;k<data.reference.size();++k) {
            const auto& x=data.reference[k];
            reference<<k<<','<<data.reachability.time_grid[k]<<','<<x.vx<<','<<x.vy<<','<<x.vz<<','
                <<x.phi<<','<<x.psi<<','<<x.theta<<','<<x.omega_x<<','<<x.omega_y<<','<<x.omega_z<<'\n';
            const auto m=std::get<model::spatial_flight::Model>(model::spatial_flight::Model::make(data.parameters));
            const auto lin=take(m.linearize(x,data.nominal_control));
            for (std::size_t row=0;row<9;++row) {
                for (std::size_t col=0;col<9;++col)
                    jacobians<<k<<",state,"<<row<<','<<col<<','<<lin.state.values[row*9+col]<<'\n';
                for (std::size_t col=0;col<3;++col)
                    jacobians<<k<<",control,"<<row<<','<<col<<','<<lin.control.values[row*3+col]<<'\n';
            }
        }
        std::ofstream metadata(*output/"run-receipt.txt");
        metadata.exceptions(std::ios::badbit|std::ios::failbit);
        metadata<<"case="<<data.reachability.info.id<<"\nsource_sha256="<<data.reachability.info.source.sha256
            <<"\nsource_qualification="<<data.reachability.info.source.qualification
            <<"\nstate_order=vx,vy,vz,phi,psi,theta,omega_x,omega_y,omega_z\ncontrol_order=u0,u1,u2\n"
            <<"control_allocation=zero_based_u0_moments_only;u1_u2_also_Cy_Cz\n"
            <<"\nnominal_control=0.003,-0.002,0.002\ninitial_state=100,0,0,0,0,0,0,0,0\n"
            <<"\nreference_method="<<data.reference_integration.method
            <<"\nreference_intervals="<<data.reference_integration.intervals
            <<"\nreference_substeps_per_interval="<<data.reference_integration.substeps_per_interval
            <<"\nreference_rhs_evaluations="<<data.reference_integration.rhs_evaluations
            <<"\nlinear_discretizer="<<data.discretization.method
            <<"\nlinear_discretizer_abs_tolerance="<<data.discretization.absolute_tolerance
            <<"\nlinear_discretizer_rel_tolerance="<<data.discretization.relative_tolerance
            <<"\nlinear_discretizer_error_scope="<<data.discretization.error_scope
            <<"\nreachability_scope=linearized deviation model; not a nonlinear enclosure or Euler-domain certificate\n";
    }
    std::vector<CapturedCase> captures;
    if (output) for (std::size_t k=0;k<reachable.size();++k) {
        const auto& set=reachable[k];
        for (std::size_t i=0;i<9;++i)
            generators<<k<<",center,none,"<<i<<','<<set.center()[i]<<'\n';
        for (std::size_t j=0;j<set.generators().cols;++j)
            for (std::size_t i=0;i<9;++i)
                generators<<k<<",generator,"<<set.factor_ids()[j].value<<','<<i<<','
                    <<set.generators().values[i*set.generators().cols+j]<<'\n';
    }
    for (const auto [first,second]:planes()) {
        CapturedCase capture{data.reachability.info,{},{{{first,second},{first,second}}},true};
        capture.stages.reserve(reachable.size());
        for (std::size_t k=0;k<reachable.size();++k) {
            const auto& set=reachable[k];
            if (set.factor_ids().size()!=9+3*k) throw std::runtime_error("Independent factors were lost during 9D propagation");
            const auto boundary=projection_witnesses(set,first,second);
            if (output) capture.stages.push_back(boundary);
            for (std::size_t point=0;point<boundary.size();++point) {
                if (output) {
                    projection_output<<k<<','<<first<<'-'<<second<<','<<point;
                    for (std::size_t coordinate=0;coordinate<9;++coordinate) projection_output<<','<<boundary[point][coordinate];
                    projection_output<<'\n';
                }
            }
        }
        captures.push_back(std::move(capture));
    }
    std::size_t support_checks=0;
    long double maximum_error=0;
    const auto directions=support_directions();
    for (std::size_t k=0;k<reachable.size();++k) for (std::size_t ordinal=0;ordinal<directions.size();++ordinal) {
        const auto actual=support(reachable[k],directions[ordinal]);
        const auto expected=independent_support(system,k,directions[ordinal]);
        const auto error=std::abs(actual-expected);
        maximum_error=std::max(maximum_error,error);
        if (error>2e-10L*(1+std::abs(expected))) throw std::runtime_error("Independent 9D support check failed");
        ++support_checks;
        if (output) {
            supports<<k<<','<<ordinal;
            for (const auto coordinate:directions[ordinal]) supports<<','<<coordinate;
            supports<<','<<actual<<','<<expected<<','<<error<<'\n';
        }
    }
    if (output) write_capture(*output,captures);
    std::cout<<std::setprecision(17)<<"case="<<data.reachability.info.id<<" dimension=9 controls=3 transitions=20 stages="
        <<reachable.size()<<" terminal_generators="<<reachable.back().generators().cols
        <<" support_checks="<<support_checks<<" maximum_support_difference="<<maximum_error<<'\n'
        <<"Native spatial flight: 20 transitions and "<<support_checks<<" full-state support checks passed\n"
        <<"projection_planes=6 full_state_coordinates_covered=9\n"
        <<"scope=numerical forward reachability of native piecewise-linear variational model; no nonlinear enclosure or domain certificate\n";
} catch (const std::exception& error) {
    std::cerr<<error.what()<<'\n';
    return 1;
}
