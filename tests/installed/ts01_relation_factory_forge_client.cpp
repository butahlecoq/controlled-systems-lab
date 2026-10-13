#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>

namespace csl::synthesis::strategy_ts01 {
class RelationFactory {
public:
    static std::shared_ptr<const ExactJointRelation> fabricate(sets::SetData data) {
        return std::shared_ptr<const ExactJointRelation>(new ExactJointRelation(std::move(data)));
    }
};
}
int main() { return 0; }