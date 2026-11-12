#include <csl/geometry/ellipsoidal.hpp>
#include "../exact_dyadic.hpp"

#include <algorithm>
#include <cmath>
#include <limits>

namespace csl::geometry::ellipsoidal::detail {
struct EllipsoidStorage final : SetPayload {
    explicit EllipsoidStorage(EllipsoidInput input):input(std::move(input)){}
    const EllipsoidInput input;
};
}

namespace csl::geometry::ellipsoidal {
namespace {
Diagnostics invalid(const char* field,const char* message,
                    DiagnosticCode code=DiagnosticCode::invalid_input) {
    return {{code,field,message}};
}
bool finite(const Vector& values) {
    for(const double value:values)if(!std::isfinite(value))return false;
    return true;
}
bool nonsingular(const Matrix& matrix) {
    using namespace geometry::detail::exact_detail;
    if(matrix.rows!=2 || matrix.cols!=2 || matrix.values.size()!=4 ||
       !finite(matrix.values))return false;
    Integer determinant;
    if(!add_product(determinant,decode(matrix.values[0]),decode(matrix.values[3])))
        return false;
    auto negated=decode(matrix.values[1]);
    negated.negative=!negated.negative;
    return add_product(determinant,negated,decode(matrix.values[2])) &&
        !is_zero(determinant);
}
bool radius_covers(double bound,double radius) {
    using namespace geometry::detail::exact_detail;
    if(bound==0)return radius==0;
    if(radius<=0)return false;
    Integer difference;
    if(!add_product(difference,decode(radius),decode(radius)))return false;
    auto negative=decode(bound);
    negative.negative=true;
    return add_product(difference,negative,decode(bound)) &&
        add_product(difference,negative,decode(bound)) &&
        (is_zero(difference) || !difference.negative);
}
bool finite_matrix(const Matrix& matrix) {
    return matrix.values.size()==matrix.rows*matrix.cols && finite(matrix.values);
}
bool zero_factor(const Matrix& matrix) {
    return std::all_of(matrix.values.begin(),matrix.values.end(),
        [](double value){return value==0.0;});
}
}

FactorEllipsoidResult make_factor_ellipsoid(Vector center,Matrix factor) {
    if(center.empty() || !finite(center) || factor.rows!=center.size() ||
       !finite_matrix(factor))
        return invalid("ellipsoid.factor.shape",
            "A finite nonempty center and a finite factor with matching rows are required.");
    return FactorEllipsoid{std::move(center),std::move(factor)};
}

FactorEllipsoidResult affine_image(const FactorEllipsoid& input,
                                    const Matrix& map,const Vector& offset) {
    if(map.cols!=input.center.size() || map.rows==0 || offset.size()!=map.rows ||
       !finite_matrix(map) || !finite(offset) ||
       input.factor.rows!=input.center.size() || !finite_matrix(input.factor))
        return invalid("ellipsoid.factor.affine",
            "Finite map, offset and factor dimensions must agree.");
    Vector center(map.rows,0.0);
    Matrix factor{map.rows,input.factor.cols,
        Vector(map.rows*input.factor.cols,0.0)};
    for(std::size_t row=0;row<map.rows;++row) {
        center[row]=offset[row];
        for(std::size_t column=0;column<map.cols;++column)
            center[row]+=map.values[row*map.cols+column]*input.center[column];
        for(std::size_t column=0;column<input.factor.cols;++column)
            for(std::size_t k=0;k<map.cols;++k)
                factor.values[row*factor.cols+column]+=
                    map.values[row*map.cols+k]*input.factor.values[k*input.factor.cols+column];
    }
    return make_factor_ellipsoid(std::move(center),std::move(factor));
}

FactorEllipsoidResult outer_minkowski_sum(const FactorEllipsoid& left,
        const FactorEllipsoid& right,double beta) {
    if(left.center.empty() || left.center.size()!=right.center.size() ||
       left.factor.rows!=left.center.size() || right.factor.rows!=right.center.size() ||
       !finite(left.center) || !finite(right.center) || !finite_matrix(left.factor) ||
       !finite_matrix(right.factor) || !std::isfinite(beta) || beta<=0)
        return invalid("ellipsoid.factor.sum",
            "Finite factors of matching dimension and positive finite beta are required.");
    const double left_scale=std::sqrt(1.0+beta);
    const double right_scale=std::sqrt(1.0+1.0/beta);
    if(!std::isfinite(left_scale) || !std::isfinite(right_scale))
        return invalid("ellipsoid.factor.sum.beta","Beta scaling overflowed.",
                       DiagnosticCode::unsupported);
    const auto dimension=left.center.size();
    Vector center(dimension);
    for(std::size_t row=0;row<dimension;++row)
        center[row]=left.center[row]+right.center[row];
    // A zero factor is the exact singleton {center}; avoid inflating the other
    // summand by an arbitrary limiting beta.
    if(zero_factor(left.factor))
        return make_factor_ellipsoid(std::move(center),right.factor);
    if(zero_factor(right.factor))
        return make_factor_ellipsoid(std::move(center),left.factor);
    Matrix factor{dimension,left.factor.cols+right.factor.cols,
        Vector(dimension*(left.factor.cols+right.factor.cols),0.0)};
    for(std::size_t row=0;row<dimension;++row) {
        for(std::size_t column=0;column<left.factor.cols;++column)
            factor.values[row*factor.cols+column]=
                left_scale*left.factor.values[row*left.factor.cols+column];
        for(std::size_t column=0;column<right.factor.cols;++column)
            factor.values[row*factor.cols+left.factor.cols+column]=
                right_scale*right.factor.values[row*right.factor.cols+column];
    }
    return make_factor_ellipsoid(std::move(center),std::move(factor));
}

FactorEllipsoidResult outer_box(Vector center,const Matrix& generators) {
    if(center.empty() || generators.rows!=center.size() ||
       !finite(center) || !finite_matrix(generators))
        return invalid("ellipsoid.factor.box",
            "Finite box center and generator rows must have matching dimensions.");
    const double scale=std::sqrt(static_cast<double>(generators.cols));
    if(!std::isfinite(scale))
        return invalid("ellipsoid.factor.box.scale","Box dimension scale overflowed.",
                       DiagnosticCode::unsupported);
    auto factor=generators;
    for(auto& value:factor.values)value*=scale;
    return make_factor_ellipsoid(std::move(center),std::move(factor));
}

EllipsoidSet::EllipsoidSet(std::shared_ptr<const detail::EllipsoidStorage> storage)
    :storage_(std::move(storage)){}
const SetId& EllipsoidSet::id() const noexcept {return storage_->input.id;}
const Vector& EllipsoidSet::center() const noexcept {return storage_->input.center;}
const Matrix& EllipsoidSet::orientation() const noexcept {return storage_->input.orientation;}
const Vector& EllipsoidSet::projected_bounds() const noexcept {
    return storage_->input.projected_bounds;
}
const Vector& EllipsoidSet::radii() const noexcept {return storage_->input.radii;}
const std::vector<std::string>& EllipsoidSet::coordinate_labels() const noexcept {
    return storage_->input.coordinate_labels;
}
SetHandle EllipsoidSet::as_handle() const {
    const auto degenerate=radii()[0]==0 || radii()[1]==0;
    return {{2,{"csl.ellipsoid.directional2d"},SetProperty::yes,
             degenerate?SetProperty::yes:SetProperty::no,SetProperty::yes},
            storage_,id()};
}
std::variant<double,Diagnostics> EllipsoidSet::support(const Vector& direction) const {
    if(direction.size()!=2 || !finite(direction))
        return invalid("ellipsoid.support.direction","A finite planar direction is required.");
    const auto& b=orientation().values;
    const double determinant=b[0]*b[3]-b[1]*b[2];
    if(!std::isfinite(determinant) || determinant==0)
        return invalid("ellipsoid.support.numeric","The stored orientation is numerically singular.",
                       DiagnosticCode::unsupported);
    const double first=(b[3]*direction[0]-b[2]*direction[1])/determinant;
    const double second=(-b[1]*direction[0]+b[0]*direction[1])/determinant;
    const double value=direction[0]*center()[0]+direction[1]*center()[1]+
        std::hypot(radii()[0]*first,radii()[1]*second);
    if(!std::isfinite(value))
        return invalid("ellipsoid.support.numeric","A finite support value could not be stored.",
                       DiagnosticCode::unsupported);
    return value;
}

EllipsoidResult make_ellipsoid(EllipsoidInput input) {
    if(input.id.value.empty())return invalid("ellipsoid.id","Set identity must be nonempty.");
    if(input.center.size()!=2 || !finite(input.center) ||
       input.projected_bounds.size()!=2 || !finite(input.projected_bounds) ||
       input.radii.size()!=2 || !finite(input.radii))
        return invalid("ellipsoid.shape","Finite planar center and radii are required.");
    if(!nonsingular(input.orientation))
        return invalid("ellipsoid.orientation","Two independent finite orientation rows are required.");
    for(std::size_t i=0;i<2;++i)
        if(input.projected_bounds[i]<0 || input.radii[i]<0 ||
           !radius_covers(input.projected_bounds[i],input.radii[i]))
            return invalid("ellipsoid.psd","Radii must cover projected bounds and preserve zero directions.");
    if(!input.coordinate_labels.empty() &&
       (input.coordinate_labels.size()!=2 || input.coordinate_labels[0].empty() ||
        input.coordinate_labels[1].empty() ||
        input.coordinate_labels[0]==input.coordinate_labels[1]))
        return invalid("ellipsoid.labels","Coordinates require two unique nonempty labels.");
    return EllipsoidSet(std::make_shared<const detail::EllipsoidStorage>(std::move(input)));
}

EllipsoidResult from_ellipsoid_handle(const SetHandle& handle) {
    const auto storage=std::dynamic_pointer_cast<const detail::EllipsoidStorage>(handle.payload);
    if(!storage)
        return invalid("ellipsoid.handle","Handle has no native ellipsoid payload.",
                       DiagnosticCode::unsupported);
    EllipsoidSet result(storage);
    const auto expected=result.as_handle();
    if(handle.id!=expected.id ||
       handle.metadata.dimension!=expected.metadata.dimension ||
       handle.metadata.representation!=expected.metadata.representation ||
       handle.metadata.convex!=expected.metadata.convex ||
       handle.metadata.polyhedral!=expected.metadata.polyhedral ||
       handle.metadata.bounded!=expected.metadata.bounded)
        return invalid("ellipsoid.handle","SetHandle envelope differs from immutable payload.");
    return result;
}
} // namespace csl::geometry::ellipsoidal
