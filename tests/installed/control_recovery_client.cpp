#include <csl/synthesis/control_recovery.hpp>

#include <type_traits>

int main() {
    using Expected = csl::synthesis::ControlRecoveryOutcome (*)(
        const csl::problem::ResolvedProblem&, const csl::sets::SetData&);
    static_assert(std::is_same_v<decltype(&csl::synthesis::recover_joint_history), Expected>);
    return 0;
}
