#include <csl/geometry/box_parallelotope.hpp>
#include <csl/sets/data.hpp>
#include "../exact_dyadic.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <sstream>

namespace csl::geometry::approximation {
namespace {
Diagnostics unsupported(std::string field,const char* reason) {
    return {{DiagnosticCode::unsupported,std::move(field),reason}};
}
bool stopped(const ExecutionContext& context) {
    return context.cancellation.stop_requested() ||
        (context.deadline && std::chrono::steady_clock::now()>=*context.deadline);
}
OperationStopped stop(const ExecutionContext& context) {
    return {context.cancellation.stop_requested()?StopReason::cancelled:StopReason::deadline_expired,
        "Box approximation stopped before publishing an enclosure."};
}
std::string matrix_rows(const Matrix& matrix) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out<<std::setprecision(std::numeric_limits<double>::max_digits10);
    for(std::size_t row=0;row<matrix.rows;++row) {
        if(row)out<<';';
        for(std::size_t column=0;column<matrix.cols;++column) {
            if(column)out<<',';
            out<<matrix.values[row*matrix.cols+column];
        }
    }
    return out.str();
}
registry::Capability outer_capability(const ApproximationRequest& request,
                                      const registry::Requirements& requirements,
                                      const std::string& prefix) {
    if(request.direction!=SetRelation::outer ||
       requirements.output.relation!=SetRelation::outer)
        return unsupported(prefix+".direction","The adapter offers an outer enclosure.");
    if(request.assurance!=Assurance::numerical ||
       requirements.output.assurance!=Assurance::numerical ||
       requirements.scalar!=registry::Scalar::binary64)
        return unsupported(prefix+".assurance","Only binary64 numerical assurance is available.");
    if(request.output.value!="csl.polyhedron.h" ||
       requirements.output.representation!=request.output)
        return unsupported(prefix+".output","A native H representation is required.");
    const auto dimension=request.input.metadata.dimension;
    if(dimension<1 || dimension>2)
        return unsupported(prefix+".dimension","Only one- and two-dimensional outputs are supported.");
    if(request.size_budget<2*dimension)
        return unsupported(prefix+".budget","The budget must admit two H rows per coordinate.");
    const auto native=sets::from_handle(request.input);
    if(const auto* set=std::get_if<sets::SetData>(&native)) {
        const auto representation=set->representation();
        if(const auto* v=std::get_if<sets::VRepresentation>(&representation)) {
            if(v->vertices.rows()==0)
                return unsupported(prefix+".input.empty","An empty input has no finite directional bounds.");
            if(v->rays.rows()!=0)
                return unsupported(prefix+".input.unbounded","A V input with rays is not admitted by this bounded adapter.");
            registry::Output output;
            output.representation=request.output;
            output.relation=SetRelation::outer;
            return registry::Offer{output};
        }
    }
    return unsupported(prefix+".input","A native bounded V set is required.");
}
registry::Capability box_capability(const ApproximationRequest& request,
                                     const registry::Requirements& requirements) {
    return outer_capability(request,requirements,"box");
}
class BoxWorkspace final : public SetApproximatorWorkspace {
    SetId output_id_;
public:
    explicit BoxWorkspace(SetId output_id):output_id_(std::move(output_id)){}
    SetTransformOutcome approximate(const ApproximationRequest& request,
                                     const ExecutionContext& context) override {
        if(stopped(context))return stop(context);
        const auto native=sets::from_handle(request.input);
        if(!std::holds_alternative<sets::SetData>(native))
            return Unsupported{unsupported("box.input","Native input is unavailable.")};
        const auto& data=std::get<sets::SetData>(native);
        const auto rep=data.representation();
        const auto* vertices=std::get_if<sets::VRepresentation>(&rep);
        if(!vertices || vertices->vertices.rows()==0 || vertices->rays.rows()!=0)
            return Unsupported{unsupported("box.input","A nonempty bounded V set is required.")};
        const auto dimension=request.input.metadata.dimension;
        Matrix rows{2*dimension,dimension,Vector(2*dimension*dimension,0.0)};
        Vector bounds(2*dimension);
        for(std::size_t coordinate=0;coordinate<dimension;++coordinate) {
            double low=vertices->vertices(0,coordinate);
            double high=low;
            for(std::size_t vertex=1;vertex<vertices->vertices.rows();++vertex) {
                const double value=vertices->vertices(vertex,coordinate);
                low=std::min(low,value);
                high=std::max(high,value);
            }
            rows.values[(2*coordinate)*dimension+coordinate]=1.0;
            rows.values[(2*coordinate+1)*dimension+coordinate]=-1.0;
            bounds[2*coordinate]=high;
            bounds[2*coordinate+1]=-low;
            if(stopped(context))return stop(context);
        }
        const auto h_rows=numeric::snapshot(rows);
        const auto h_bounds=numeric::snapshot_vector(bounds);
        const auto no_rows=numeric::snapshot(Matrix{0,dimension,{}});
        const auto no_values=numeric::snapshot_vector(Vector{});
        if(!std::holds_alternative<numeric::MatrixView>(h_rows) ||
           !std::holds_alternative<numeric::VectorView>(h_bounds) ||
           !std::holds_alternative<numeric::MatrixView>(no_rows) ||
           !std::holds_alternative<numeric::VectorView>(no_values))
            return Unsupported{unsupported("box.numeric","Finite H output could not be stored.")};
        const auto output=sets::make_h({output_id_,dimension,data.metadata()->coordinate_labels},
            {std::get<numeric::MatrixView>(h_rows),std::get<numeric::VectorView>(h_bounds),
             std::get<numeric::MatrixView>(no_rows),std::get<numeric::VectorView>(no_values)});
        if(!std::holds_alternative<sets::SetData>(output))
            return Unsupported{unsupported("box.output","Native H output could not be constructed.")};
        if(stopped(context))return stop(context);
        GeometryEvidence evidence{{request.identity,{request.input.id}},GeometryClaimScope::set_relation,
            SymbolicArgument{"native V-coordinate bounds","Stored V coordinates define exact binary64 H slabs."},
            {"orientation_rows="+(dimension==1?std::string{"1"}:std::string{"1,0;0,1"}),
             "requested_budget="+std::to_string(request.size_budget)+
                 "; input_vertices="+std::to_string(vertices->vertices.rows())+
                 "; input_rays=0; output_h_rows="+std::to_string(2*dimension),
             "error_bound=unavailable"},
            {}};
        return OperationResult{std::get<sets::SetData>(output).as_handle(),
            SetRelation::outer,std::move(evidence)};
    }
};
bool independent_directions(const Matrix& rows) {
    using namespace detail::exact_detail;
    if(rows.rows!=2 || rows.cols!=2 || rows.values.size()!=4 ||
       !std::all_of(rows.values.begin(),rows.values.end(),
           [](double value){return std::isfinite(value);} ))return false;
    Integer determinant;
    if(!add_product(determinant,decode(rows.values[0]),decode(rows.values[3])))return false;
    auto negative=decode(rows.values[1]);negative.negative=!negative.negative;
    return add_product(determinant,negative,decode(rows.values[2])) && !is_zero(determinant);
}
std::optional<double> exact_dot_upper(const Matrix& directions,std::size_t row,
                                      const numeric::MatrixView& vertices,std::size_t vertex) {
    using namespace detail::exact_detail;
    Integer dot;
    for(std::size_t column=0;column<2;++column)
        if(!add_product(dot,decode(directions.values[row*2+column]),
                        decode(vertices(vertex,column))))return std::nullopt;
    const bool negative=dot.negative;
    dot.negative=false;
    const auto rounded=outward_binary64(dot);
    if(!rounded)return std::nullopt;
    return negative?std::nextafter(-*rounded,std::numeric_limits<double>::infinity()):*rounded;
}
class ParallelotopeWorkspace final : public SetApproximatorWorkspace {
    SetId output_id_;
    Matrix directions_;
public:
    ParallelotopeWorkspace(SetId output_id,Matrix directions)
        :output_id_(std::move(output_id)),directions_(std::move(directions)){}
    SetTransformOutcome approximate(const ApproximationRequest& request,
                                     const ExecutionContext& context) override {
        if(stopped(context))return stop(context);
        const auto native=sets::from_handle(request.input);
        if(!std::holds_alternative<sets::SetData>(native))
            return Unsupported{unsupported("parallelotope.input","Native input is unavailable.")};
        const auto& data=std::get<sets::SetData>(native);
        const auto representation=data.representation();
        const auto* v=std::get_if<sets::VRepresentation>(&representation);
        if(!v || v->vertices.rows()==0 || v->rays.rows()!=0)
            return Unsupported{unsupported("parallelotope.input","A nonempty bounded V set is required.")};
        Matrix rows{4,2,{directions_.values[0],directions_.values[1],
                         -directions_.values[0],-directions_.values[1],
                         directions_.values[2],directions_.values[3],
                         -directions_.values[2],-directions_.values[3]}};
        Vector bounds(4);
        for(std::size_t row=0;row<4;++row) {
            const auto first=exact_dot_upper(rows,row,v->vertices,0);
            if(!first)return Unsupported{unsupported("parallelotope.numeric","A finite support bound is unavailable.")};
            bounds[row]=*first;
            for(std::size_t vertex=1;vertex<v->vertices.rows();++vertex) {
                const auto bound=exact_dot_upper(rows,row,v->vertices,vertex);
                if(!bound)return Unsupported{unsupported("parallelotope.numeric","A finite support bound is unavailable.")};
                bounds[row]=std::max(bounds[row],*bound);
            }
            if(stopped(context))return stop(context);
        }
        const auto h_rows=numeric::snapshot(rows);
        const auto h_bounds=numeric::snapshot_vector(bounds);
        const auto no_rows=numeric::snapshot(Matrix{0,2,{}});
        const auto no_values=numeric::snapshot_vector(Vector{});
        if(!std::holds_alternative<numeric::MatrixView>(h_rows) ||
           !std::holds_alternative<numeric::VectorView>(h_bounds) ||
           !std::holds_alternative<numeric::MatrixView>(no_rows) ||
           !std::holds_alternative<numeric::VectorView>(no_values))
            return Unsupported{unsupported("parallelotope.numeric","Finite H output could not be stored.")};
        const auto output=sets::make_h({output_id_,2,data.metadata()->coordinate_labels},
            {std::get<numeric::MatrixView>(h_rows),std::get<numeric::VectorView>(h_bounds),
             std::get<numeric::MatrixView>(no_rows),std::get<numeric::VectorView>(no_values)});
        if(!std::holds_alternative<sets::SetData>(output))
            return Unsupported{unsupported("parallelotope.output","Native H output could not be constructed.")};
        if(stopped(context))return stop(context);
        GeometryEvidence evidence{{request.identity,{request.input.id}},GeometryClaimScope::set_relation,
            SymbolicArgument{"native directional support","Exact stored binary64 products were rounded outward into H slabs."},
            {"orientation_rows="+matrix_rows(directions_),
             "requested_budget="+std::to_string(request.size_budget)+
                 "; input_vertices="+std::to_string(v->vertices.rows())+
                 "; input_rays=0; output_h_rows=4",
             "error_bound=unavailable"},
            {}};
        return OperationResult{std::get<sets::SetData>(output).as_handle(),
            SetRelation::outer,std::move(evidence)};
    }
};
bool exact_diagonal_match(const Matrix& corners,std::size_t coordinate) {
    using namespace detail::exact_detail;
    Integer difference;
    if(!add_dyadic(difference,decode(corners.values[coordinate])) ||
       !add_dyadic(difference,decode(corners.values[4+coordinate])))return false;
    for(const auto index:{2+coordinate,6+coordinate}) {
        auto negative=decode(corners.values[index]);negative.negative=!negative.negative;
        if(!add_dyadic(difference,negative))return false;
    }
    return is_zero(difference);
}
bool noncollinear_corners(const Matrix& corners) {
    using namespace detail::exact_detail;
    Integer cross;
    const auto& p=corners.values;
    const std::array<std::pair<std::size_t,std::size_t>,6> terms{{
        {2,7},{2,1},{0,7},{3,6},{3,0},{1,6}}};
    for(std::size_t term=0;term<terms.size();++term) {
        auto left=decode(p[terms[term].first]);
        if(term==1 || term==2 || term==3)left.negative=!left.negative;
        if(!add_product(cross,left,decode(p[terms[term].second])))return false;
    }
    return !is_zero(cross);
}
bool valid_corners(const Matrix& corners,bool axis_aligned) {
    if(corners.rows!=4 || corners.cols!=2 || corners.values.size()!=8 ||
       !std::all_of(corners.values.begin(),corners.values.end(),
           [](double value){return std::isfinite(value);} ))return false;
    if(!exact_diagonal_match(corners,0) || !exact_diagonal_match(corners,1) ||
       !noncollinear_corners(corners))return false;
    if(axis_aligned) {
        const auto& p=corners.values;
        if(p[0]!=p[2] || p[3]!=p[5] || p[4]!=p[6] || p[7]!=p[1])return false;
    }
    return true;
}
registry::Capability inner_capability(const ApproximationRequest& request,
                                       const registry::Requirements& requirements,
                                       const Matrix& corners,bool axis_aligned) {
    if(!valid_corners(corners,axis_aligned))
        return unsupported("inner-template.corners","Four finite nondegenerate ordered parallelogram corners are required.");
    if(request.direction!=SetRelation::inner || requirements.output.relation!=SetRelation::inner)
        return unsupported("inner-template.direction","Only an inner enclosure is offered.");
    if(request.assurance!=Assurance::numerical ||
       requirements.output.assurance!=Assurance::numerical ||
       requirements.scalar!=registry::Scalar::binary64)
        return unsupported("inner-template.assurance","Only binary64 numerical assurance is available.");
    if(request.input.metadata.dimension!=2)
        return unsupported("inner-template.dimension","Only two-dimensional inputs are supported.");
    if(request.output.value!="csl.polyhedron.v" ||
       requirements.output.representation!=request.output)
        return unsupported("inner-template.output","A native V representation is required.");
    if(request.size_budget<4)
        return unsupported("inner-template.budget","Four V vertices are required.");
    const auto native=sets::from_handle(request.input);
    if(const auto* set=std::get_if<sets::SetData>(&native)) {
        const auto representation=set->representation();
        if(std::holds_alternative<sets::HRepresentation>(representation)) {
            registry::Output output;
            output.representation=request.output;
            output.relation=SetRelation::inner;
            return registry::Offer{output};
        }
    }
    return unsupported("inner-template.input","A native H reference is required.");
}
class InnerWorkspace final : public SetApproximatorWorkspace {
    SetId output_id_;
    Matrix corners_;
    bool axis_aligned_;
public:
    InnerWorkspace(SetId output_id,Matrix corners,bool axis_aligned)
        :output_id_(std::move(output_id)),corners_(std::move(corners)),axis_aligned_(axis_aligned){}
    SetTransformOutcome approximate(const ApproximationRequest& request,
                                     const ExecutionContext& context) override {
        if(stopped(context))return stop(context);
        const auto native=sets::from_handle(request.input);
        if(!std::holds_alternative<sets::SetData>(native))
            return Unsupported{unsupported("inner-template.input","Native input is unavailable.")};
        const auto& data=std::get<sets::SetData>(native);
        const auto reference=data.representation();
        const auto* h=std::get_if<sets::HRepresentation>(&reference);
        if(!h)return Unsupported{unsupported("inner-template.input","A native H reference is required.")};
        const auto vertices=numeric::snapshot(corners_);
        const auto rays=numeric::snapshot(Matrix{0,2,{}});
        if(!std::holds_alternative<numeric::MatrixView>(vertices) ||
           !std::holds_alternative<numeric::MatrixView>(rays))
            return Unsupported{unsupported("inner-template.numeric","Corners could not be stored.")};
        const auto output=sets::make_v({output_id_,2,data.metadata()->coordinate_labels},
            {std::get<numeric::MatrixView>(vertices),std::get<numeric::MatrixView>(rays)});
        if(!std::holds_alternative<sets::SetData>(output))
            return Unsupported{unsupported("inner-template.output","Native V output could not be constructed.")};
        if(stopped(context))return stop(context);
        GeometryEvidence evidence{{request.identity,{request.input.id}},GeometryClaimScope::set_relation,
            SymbolicArgument{"inscribed native V template","Every stored corner requires independent H-row admission."},
            {"ordered_corners="+matrix_rows(corners_),
             "requested_budget="+std::to_string(request.size_budget)+
                 "; input_h_rows="+std::to_string(h->inequalities.rows()+h->equalities.rows())+
                 "; output_vertices=4; output_rays=0",
             "error_bound=unavailable"},
            {}};
        return OperationResult{std::get<sets::SetData>(output).as_handle(),
            SetRelation::inner,std::move(evidence)};
    }
};
registry::Registration<registry::ApproximationPort> inner_registration(
    SetId output_id,Matrix corners,bool axis_aligned) {
    const char* id=axis_aligned?"csl.approximation.inner-box":"csl.approximation.inner-parallelotope";
    return {{{id},"1"},
        [corners,axis_aligned](const ApproximationRequest& request,
                               const registry::Requirements& requirements) -> registry::Capability {
            return inner_capability(request,requirements,corners,axis_aligned);
        },
        [output_id=std::move(output_id),corners=std::move(corners),axis_aligned](
            const ApproximationRequest&) {
            return std::make_unique<InnerWorkspace>(output_id,corners,axis_aligned);
        }};
}
}

registry::Registration<registry::ApproximationPort> make_box_registration(SetId output_id) {
    return {{{"csl.approximation.box"},"1"},box_capability,
        [output_id=std::move(output_id)](const ApproximationRequest&) {
            return std::make_unique<BoxWorkspace>(output_id);
        }};
}
registry::Registration<registry::ApproximationPort> make_parallelotope_registration(
    SetId output_id,Matrix orientation_rows) {
    return {{{"csl.approximation.parallelotope"},"1"},
        [orientation_rows](const ApproximationRequest& request,
                           const registry::Requirements& requirements) -> registry::Capability {
            if(!independent_directions(orientation_rows))
                return unsupported("parallelotope.orientation","Two independent finite orientation rows are required.");
            if(request.input.metadata.dimension!=2)
                return unsupported("parallelotope.dimension","Only two-dimensional parallelotopes are supported.");
            if(request.size_budget<4)
                return unsupported("parallelotope.budget","Four H rows are required.");
            return outer_capability(request,requirements,"parallelotope");
        },
        [output_id=std::move(output_id),orientation_rows=std::move(orientation_rows)](
            const ApproximationRequest&) {
            return std::make_unique<ParallelotopeWorkspace>(output_id,orientation_rows);
        }};
}
registry::Registration<registry::ApproximationPort> make_inscribed_box_registration(
    SetId output_id,Matrix ordered_corners) {
    return inner_registration(std::move(output_id),std::move(ordered_corners),true);
}
registry::Registration<registry::ApproximationPort> make_inscribed_parallelotope_registration(
    SetId output_id,Matrix ordered_corners) {
    return inner_registration(std::move(output_id),std::move(ordered_corners),false);
}
} // namespace csl::geometry::approximation
