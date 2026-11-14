#include <csl/reachability/inner_template.hpp>
#include <iostream>
int main() {
    using namespace csl::reachability;
    InnerTemplateInput input{{0, 0},
                             {2, 2, {1, 0, 0, 1}},
                             InnerTemplateNorm::independent_intervals,
                             {4, 2, {1, 0, -1, 0, 0, 1, 0, -1}},
                             {1, 1, 1, 1},
                             {0, 2, {}},
                             {}};
    const auto outcome = inscribe_template(input);
    if (!std::holds_alternative<InnerTemplate>(outcome))
        return 1;
    const auto &set = std::get<InnerTemplate>(outcome);
    if (set.point || set.radius <= 0 || !check_inner_template(input, set).empty())
        return 2;
    std::cout << "Installed ND inner-template client passed\n";
}
