#include <stdio.h>
#include "acados_c/ocp_qp_interface.h"

int main(void) {
    const int N = 16;
    const int nx_value = 4;
    const double A[] = {1, -6.25, 0, 0, 0, 1, 0, 0, 0, 0, 1, -6.25, 0, 0, 0, 1};
    const double B[] = {17, 0, -12, 0};
    const double affine[] = {0, 0, 0, 0};
    const double Qstage[] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    const double Sstage[] = {0.0, 0.0, 0.0, 0.0};
    const double Rstage[] = {0.0};
    const double qstage[] = {0.0, 0.0, 0.0, 0.0};
    const double rstage[] = {0.0};
    const double initial[] = {1216.904, 119500, 438.78699999999998, 45300};
    const int idxbu[] = {0};
    const int idxbx_initial[] = {0, 1, 2, 3};
    const int idxbx_flow[] = {0, 2};
    const double flow_lower[] = {1176, 432};
    const double flow_upper[] = {1224, 468};
    const double control_lower[] = {-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1};
    const double control_upper[] = {1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1};
    const double Qterminal[] = {2, 0, 0, 0, 0, 4, 0, -5.333333333333333, 0, 0, 14.222222222222221, 0, 0, -5.333333333333333, 0, 28.444444444444443};
    const double qterminal[] = {-2400, 0, -6400, 0};
    ocp_qp_solver_plan_t plan;
    plan.qp_solver = FULL_CONDENSING_HPIPM;
    ocp_qp_xcond_solver_config *config = ocp_qp_xcond_solver_config_create(plan);
    ocp_qp_dims *dims = ocp_qp_dims_create(N);
    for (int stage = 0; stage <= N; ++stage) {
        int nx = nx_value;
        int nu = stage < N ? 1 : 0;
        ocp_qp_dims_set(config, dims, stage, "nx", &nx);
        ocp_qp_dims_set(config, dims, stage, "nu", &nu);
        if (stage < N) {
            int nbu = 1;
            ocp_qp_dims_set(config, dims, stage, "nbu", &nbu);
        }
        int nbx = stage == 0 ? nx_value : 2;
        ocp_qp_dims_set(config, dims, stage, "nbx", &nbx);
    }
    ocp_qp_in *in = ocp_qp_in_create(dims);
    for (int stage = 0; stage < N; ++stage) {
        ocp_qp_in_set(config, in, stage, "A", (void *)A);
        ocp_qp_in_set(config, in, stage, "B", (void *)B);
        ocp_qp_in_set(config, in, stage, "b", (void *)affine);
        ocp_qp_in_set(config, in, stage, "Q", (void *)Qstage);
        ocp_qp_in_set(config, in, stage, "S", (void *)Sstage);
        ocp_qp_in_set(config, in, stage, "R", (void *)Rstage);
        ocp_qp_in_set(config, in, stage, "q", (void *)qstage);
        ocp_qp_in_set(config, in, stage, "r", (void *)rstage);
        ocp_qp_in_set(config, in, stage, "idxbu", (void *)idxbu);
        ocp_qp_in_set(config, in, stage, "lbu", (void *)&control_lower[stage]);
        ocp_qp_in_set(config, in, stage, "ubu", (void *)&control_upper[stage]);
    }
    ocp_qp_in_set(config, in, 0, "idxbx", (void *)idxbx_initial);
    ocp_qp_in_set(config, in, 0, "lbx", (void *)initial);
    ocp_qp_in_set(config, in, 0, "ubx", (void *)initial);
    for (int stage = 1; stage <= N; ++stage) {
        ocp_qp_in_set(config, in, stage, "idxbx", (void *)idxbx_flow);
        ocp_qp_in_set(config, in, stage, "lbx", (void *)flow_lower);
        ocp_qp_in_set(config, in, stage, "ubx", (void *)flow_upper);
    }
    ocp_qp_in_set(config, in, N, "Q", (void *)Qterminal);
    ocp_qp_in_set(config, in, N, "q", (void *)qterminal);
    ocp_qp_xcond_solver_dims *solver_dims = ocp_qp_xcond_solver_dims_create_from_ocp_qp_dims(config, dims);
    void *opts = ocp_qp_xcond_solver_opts_create(config, solver_dims);
    ocp_qp_out *out = ocp_qp_out_create(dims);
    ocp_qp_solver *solver = ocp_qp_create(config, solver_dims, opts);
    const int status = ocp_qp_solve(solver, in, out);
    double residual[4] = {0.0, 0.0, 0.0, 0.0};
    ocp_qp_inf_norm_residuals(dims, in, out, residual);
    printf("case=b04-reference-v1\nsolver=FULL_CONDENSING_HPIPM\nstatus=%d\n", status);
    for (int stage = 0; stage <= N; ++stage) {
        double x[4] = {0.0};
        ocp_qp_out_get(out, stage, "x", x);
        for (int coordinate = 0; coordinate < nx_value; ++coordinate)
            printf("x%d_%d=%.17g\n", stage, coordinate, x[coordinate]);
        if (stage < N) {
            double u[1] = {0.0};
            ocp_qp_out_get(out, stage, "u", u);
            printf("u%d=%.17g\n", stage, u[0]);
        }
    }
    double xN[4] = {0.0};
    ocp_qp_out_get(out, N, "x", xN);
    double variable_objective = 0.0;
    for (int i = 0; i < nx_value; ++i) {
        variable_objective += qterminal[i] * xN[i];
        for (int j = 0; j < nx_value; ++j) variable_objective += 0.5 * xN[i] * Qterminal[i * nx_value + j] * xN[j];
    }
    printf("variable_objective=%.17g\n", variable_objective);
    printf("squared_objective_offset=%.17g\n", (double)(2880000));
    printf("res_stationarity=%.17g\nres_dynamics=%.17g\nres_inequality=%.17g\nres_complementarity=%.17g\n",
        residual[0], residual[1], residual[2], residual[3]);
    return status == ACADOS_SUCCESS ? 0 : 1;
}
