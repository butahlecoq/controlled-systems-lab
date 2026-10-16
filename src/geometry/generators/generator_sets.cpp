
#include <csl/geometry/generators.hpp>

#include <cmath>
#include <limits>
#include <unordered_map>
#include <unordered_set>

namespace csl::sets::detail {
struct GeneratorStorage final : SetPayload {
    explicit GeneratorStorage(GeneratorInput data) : data(std::move(data)) {}
    const GeneratorInput data;
};
}

namespace csl::sets {
namespace {
Diagnostics invalid(std::string field, std::string explanation,
                    DiagnosticCode code=DiagnosticCode::invalid_input) {
    return {{code,std::move(field),std::move(explanation)}};
}
bool shape(const Matrix& matrix) {
    return matrix.rows == 0 || matrix.cols <= std::numeric_limits<std::size_t>::max()/matrix.rows
        ? matrix.values.size()==matrix.rows*matrix.cols : false;
}
bool finite(const Vector& values) {
    for (const double value:values) if (!std::isfinite(value)) return false;
    return true;
}
}

GeneratorSet::GeneratorSet(std::shared_ptr<const detail::GeneratorStorage> storage)
    : storage_(std::move(storage)) {}
const SetId& GeneratorSet::id() const noexcept { return storage_->data.id; }
const Vector& GeneratorSet::center() const noexcept { return storage_->data.center; }
const Matrix& GeneratorSet::generators() const noexcept { return storage_->data.generators; }
const std::vector<FactorId>& GeneratorSet::factor_ids() const noexcept { return storage_->data.factor_ids; }
const Matrix& GeneratorSet::equalities() const noexcept { return storage_->data.equalities; }
const Vector& GeneratorSet::equality_values() const noexcept { return storage_->data.equality_values; }
const std::vector<std::string>& GeneratorSet::coordinate_labels() const noexcept {
    return storage_->data.coordinate_labels;
}
SetHandle GeneratorSet::as_handle() const {
    return {{center().size(), {equalities().rows==0 ? "csl.zonotope" : "csl.constrained-zonotope"},
        SetProperty::yes, SetProperty::yes, SetProperty::yes}, storage_, id()};
}

GeneratorResult make_generator_set(GeneratorInput input) {
    if (input.id.value.empty()) return invalid("generators.id","Set identity must be nonempty.");
    if (!shape(input.generators) || input.generators.rows!=input.center.size() ||
        input.generators.cols!=input.factor_ids.size())
        return invalid("generators.shape","Generator rows must match coordinates and columns must match factor IDs.");
    if (!shape(input.equalities) || input.equalities.cols!=input.factor_ids.size() ||
        input.equalities.rows!=input.equality_values.size())
        return invalid("generators.equalities","Equality rows need one factor column and one value per row.");
    if (!finite(input.center) || !finite(input.generators.values) ||
        !finite(input.equalities.values) || !finite(input.equality_values))
        return invalid("generators.finite","All authored binary64 coefficients must be finite.");
    std::unordered_set<std::string> names;
    for (const auto& factor:input.factor_ids)
        if (factor.value.empty() || !names.insert(factor.value).second)
            return invalid("generators.factor_ids","Factor IDs must be nonempty and unique within a set.");
    if (!input.coordinate_labels.empty() && input.coordinate_labels.size()!=input.center.size())
        return invalid("generators.labels","Labels require one name per output coordinate.");
    names.clear();
    for (const auto& label:input.coordinate_labels)
        if (label.empty() || !names.insert(label).second)
            return invalid("generators.labels","Coordinate labels must be nonempty and unique.");
    return GeneratorSet(std::make_shared<const detail::GeneratorStorage>(std::move(input)));
}

GeneratorResult from_generator_handle(const SetHandle& handle) {
    const auto storage=std::dynamic_pointer_cast<const detail::GeneratorStorage>(handle.payload);
    if (!storage) return invalid("generators.handle","Handle has no native generator payload.",DiagnosticCode::unsupported);
    GeneratorSet result(storage);
    const auto expected=result.as_handle();
    if (handle.id!=expected.id || handle.metadata.dimension!=expected.metadata.dimension ||
        handle.metadata.representation!=expected.metadata.representation ||
        handle.metadata.convex!=expected.metadata.convex ||
        handle.metadata.polyhedral!=expected.metadata.polyhedral ||
        handle.metadata.bounded!=expected.metadata.bounded)
        return invalid("generators.handle","SetHandle envelope differs from its immutable payload.");
    return result;
}

std::variant<FactorPolyhedron,Diagnostics> factor_polyhedron(const GeneratorSet& set) {
    const auto count=set.factor_ids().size();
    if (count>std::numeric_limits<std::size_t>::max()/2 ||
        (count!=0 && count>std::vector<double>{}.max_size()/(2*count)))
        return invalid("generators.capacity","Factor H-polyhedron storage exceeds representable capacity.");
    Matrix inequalities{2*count,count,Vector(2*count*count,0)};
    Vector upper(2*count,1);
    for (std::size_t i=0;i<count;++i) {
        inequalities.values[(2*i)*count+i]=1;
        inequalities.values[(2*i+1)*count+i]=-1;
    }
    auto h_view=numeric::snapshot(inequalities);
    auto upper_view=numeric::snapshot_vector(upper);
    auto e_view=numeric::snapshot(set.equalities());
    auto value_view=numeric::snapshot_vector(set.equality_values());
    if (auto error=std::get_if<Diagnostic>(&h_view)) return Diagnostics{*error};
    if (auto error=std::get_if<Diagnostic>(&upper_view)) return Diagnostics{*error};
    if (auto error=std::get_if<Diagnostic>(&e_view)) return Diagnostics{*error};
    if (auto error=std::get_if<Diagnostic>(&value_view)) return Diagnostics{*error};
    auto factors=make_h({{set.id().value+".factors"},count,{}},
        {std::get<numeric::MatrixView>(h_view),std::get<numeric::VectorView>(upper_view),
         std::get<numeric::MatrixView>(e_view),std::get<numeric::VectorView>(value_view)});
    if (auto error=std::get_if<Diagnostic>(&factors)) return Diagnostics{*error};
    return FactorPolyhedron{std::get<SetData>(std::move(factors)),set.generators(),set.center()};
}
} // namespace csl::sets

namespace csl::geometry::generators {
namespace {
using sets::GeneratorResult;
using sets::GeneratorSet;
using sets::GeneratorInput;
using sets::FactorId;
Diagnostics invalid(std::string field, std::string explanation,
                    DiagnosticCode code=DiagnosticCode::invalid_input) {
    return {{code,std::move(field),std::move(explanation)}};
}
bool shape(const Matrix& matrix) {
    return matrix.rows == 0 || matrix.cols <= std::numeric_limits<std::size_t>::max()/matrix.rows
        ? matrix.values.size()==matrix.rows*matrix.cols : false;
}
bool capacity(std::size_t rows,std::size_t cols) {
    return rows==0 || (cols<=std::numeric_limits<std::size_t>::max()/rows &&
        rows*cols<=std::vector<double>{}.max_size());
}
}

GeneratorResult affine_image(const GeneratorSet& input,const Matrix& map,const Vector& offset,
        SetId output_id,std::vector<std::string> output_labels) {
    if (!shape(map) || map.cols!=input.center().size() || map.rows!=offset.size())
        return invalid("generators.affine.shape","Map columns must match input coordinates and offset must match output rows.");
    if (!capacity(map.rows,input.factor_ids().size()))
        return invalid("generators.affine.capacity","Output generator matrix exceeds representable capacity.");
    GeneratorInput output{std::move(output_id),offset,
        {map.rows,input.factor_ids().size(),Vector(map.rows*input.factor_ids().size(),0)},
        input.factor_ids(),input.equalities(),input.equality_values(),std::move(output_labels)};
    for (std::size_t row=0;row<map.rows;++row) {
        for (std::size_t k=0;k<map.cols;++k) {
            output.center[row]+=map.values[row*map.cols+k]*input.center()[k];
            if (!std::isfinite(output.center[row]))
                return invalid("generators.affine.arithmetic","Binary64 center calculation overflowed.");
        }
        for (std::size_t factor=0;factor<input.factor_ids().size();++factor) {
            double value=0;
            for (std::size_t k=0;k<map.cols;++k) {
                value+=map.values[row*map.cols+k]*input.generators().values[k*input.factor_ids().size()+factor];
                if (!std::isfinite(value))
                    return invalid("generators.affine.arithmetic","Binary64 generator calculation overflowed.");
            }
            output.generators.values[row*input.factor_ids().size()+factor]=value;
        }
    }
    return sets::make_generator_set(std::move(output));
}

GeneratorResult dependent_sum(const GeneratorSet& left,const GeneratorSet& right,SetId output_id) {
    if (left.center().size()!=right.center().size() ||
        left.coordinate_labels()!=right.coordinate_labels())
        return invalid("generators.sum.coordinates","Summands need matching dimension and ordered coordinate labels.");
    std::vector<FactorId> ids=left.factor_ids();
    std::unordered_map<std::string,std::size_t> position;
    for (std::size_t i=0;i<ids.size();++i) position.emplace(ids[i].value,i);
    for (const auto& id:right.factor_ids())
        if (!position.contains(id.value)) { position.emplace(id.value,ids.size()); ids.push_back(id); }
    const auto dimension=left.center().size(), factors=ids.size();
    const auto rows=left.equalities().rows+right.equalities().rows;
    if (rows<left.equalities().rows || !capacity(dimension,factors) || !capacity(rows,factors))
        return invalid("generators.sum.capacity","Merged generator or equality storage exceeds representable capacity.");
    GeneratorInput output{std::move(output_id),left.center(),{dimension,factors,Vector(dimension*factors,0)},
        std::move(ids),{rows,factors,Vector(rows*factors,0)},left.equality_values(),left.coordinate_labels()};
    output.equality_values.insert(output.equality_values.end(),right.equality_values().begin(),right.equality_values().end());
    for (std::size_t i=0;i<dimension;++i) {
        output.center[i]+=right.center()[i];
        if (!std::isfinite(output.center[i]))
            return invalid("generators.sum.arithmetic","Binary64 center calculation overflowed.");
        for (std::size_t j=0;j<left.factor_ids().size();++j)
            output.generators.values[i*factors+j]=left.generators().values[i*left.factor_ids().size()+j];
        for (std::size_t j=0;j<right.factor_ids().size();++j) {
            auto& value=output.generators.values[i*factors+position.at(right.factor_ids()[j].value)];
            value+=right.generators().values[i*right.factor_ids().size()+j];
            if (!std::isfinite(value))
                return invalid("generators.sum.arithmetic","Binary64 generator calculation overflowed.");
        }
    }
    for (std::size_t row=0;row<left.equalities().rows;++row)
        for (std::size_t col=0;col<left.factor_ids().size();++col)
            output.equalities.values[row*factors+col]=left.equalities().values[row*left.factor_ids().size()+col];
    for (std::size_t row=0;row<right.equalities().rows;++row)
        for (std::size_t col=0;col<right.factor_ids().size();++col)
            output.equalities.values[(left.equalities().rows+row)*factors+position.at(right.factor_ids()[col].value)]
                =right.equalities().values[row*right.factor_ids().size()+col];
    return sets::make_generator_set(std::move(output));
}

GeneratorResult minkowski_sum(const GeneratorSet& left,const GeneratorSet& right,SetId output_id) {
    std::unordered_set<std::string> left_ids;
    for (const auto& id:left.factor_ids()) left_ids.insert(id.value);
    for (const auto& id:right.factor_ids())
        if (left_ids.contains(id.value))
            return invalid("generators.minkowski.factor_ids",
                "Independent Minkowski sum requires disjoint factor IDs; use dependent_sum for shared factors.",
                DiagnosticCode::unsupported);
    return dependent_sum(left,right,std::move(output_id));
}
} // namespace csl::geometry::generators
