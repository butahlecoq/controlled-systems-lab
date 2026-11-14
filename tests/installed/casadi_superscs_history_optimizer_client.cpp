#include <csl/adapters/nlp/casadi_superscs_history_optimizer.hpp>

int main() {
    const auto registration=csl::adapters::nlp::make_casadi_superscs_history_optimizer_registration();
    return registration.identity.id.value=="csl.conic.superscs.history-cost"?0:1;
}
