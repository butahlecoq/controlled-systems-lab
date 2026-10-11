#include <csl/problem/constraints.hpp>
#include "detail.hpp"
#include <limits>

namespace csl::problem {
namespace detail {
struct ConstraintStorage {
    JointCoordinates coordinates;
    std::size_t state_width, joint_width;
    std::vector<AdmissibleSet> states;
    std::optional<TemporalData> temporal;
};
}
namespace {
std::optional<std::size_t> product(std::size_t left,std::size_t right) {
    if (right && left>std::numeric_limits<std::size_t>::max()/right) return {};
    return left*right;
}
}
Constraints::Constraints(std::shared_ptr<const detail::ConstraintStorage> storage) : storage_(std::move(storage)) {}
JointCoordinates Constraints::coordinates() const noexcept { return storage_->coordinates; }
std::size_t Constraints::joint_dimension() const noexcept { return storage_->joint_width; }
std::shared_ptr<const std::vector<AdmissibleSet>> Constraints::states() const noexcept { return {storage_,&storage_->states}; }
std::optional<TemporalData> Constraints::temporal() const noexcept { return storage_->temporal; }
Result<std::size_t> Constraints::state_offset(StageIndex stage) const {
    if (stage.value>storage_->coordinates.horizon)
        return detail::invalid("problem.state_stage","State stage must lie in [0,T].");
    return stage.value*storage_->coordinates.dimensions.state;
}
Result<std::size_t> Constraints::control_offset(StageIndex stage) const {
    if (stage.value>=storage_->coordinates.horizon)
        return detail::invalid("problem.control_stage","Control stage must lie in [0,T).");
    return storage_->state_width+stage.value*storage_->coordinates.dimensions.control;
}

Result<Constraints> snapshot_constraints(std::span<const AdmissibleSet> states,
    const std::optional<TemporalConstraints>& authored, const model::LinearSystem& model) {
    const auto dimensions=model.dimensions();
    const auto horizon=model.horizon();
    const auto maximum=std::numeric_limits<std::size_t>::max();
    const auto overflow=detail::invalid("problem.temporal.coordinates","Canonical state/control coordinate width overflows size_t.");
    if (horizon==maximum) return overflow;
    const auto state_width=product(horizon+1,dimensions.state);
    const auto control_width=product(horizon,dimensions.control);
    if (!state_width || !control_width || *state_width>maximum-*control_width) return overflow;
    const auto width=*state_width+*control_width;
    if (states.size()!=horizon+1)
        return detail::invalid("problem.states.stages","State constraints must have T+1 entries.");
    for (std::size_t i=0;i<states.size();++i)
        if (auto error=detail::check_set(states[i],dimensions.state,detail::indexed("problem.states",i))) return *error;
    std::optional<TemporalData> temporal;
    if (authored) {
        if (authored->joint_map.cols!=width)
            return detail::invalid("problem.temporal.shape","Temporal columns must match canonical full-history state/control width.");
        auto map=numeric::snapshot(authored->joint_map);
        if (auto error=std::get_if<Diagnostic>(&map))
            return Diagnostic{error->code,"problem.temporal.shape",error->explanation};
        if (authored->bounds.size()!=authored->joint_map.rows)
            return detail::invalid("problem.temporal.bounds","Supply one interval per temporal row.");
        for (std::size_t i=0;i<authored->bounds.size();++i) {
            const auto& bound=authored->bounds[i];
            if ((bound.lower && !std::isfinite(*bound.lower)) || (bound.upper && !std::isfinite(*bound.upper)) ||
                (bound.lower && bound.upper && *bound.lower>*bound.upper))
                return detail::invalid(detail::indexed("problem.temporal.bounds",i),"Present interval endpoints must be finite and ordered.");
        }
        temporal=TemporalData{std::get<numeric::MatrixView>(std::move(map)),
            std::make_shared<const std::vector<Interval>>(authored->bounds)};
    }
    return Constraints(std::make_shared<const detail::ConstraintStorage>(detail::ConstraintStorage{
        {dimensions,horizon},*state_width,width,{states.begin(),states.end()},std::move(temporal)}));
}
} // namespace csl::problem
