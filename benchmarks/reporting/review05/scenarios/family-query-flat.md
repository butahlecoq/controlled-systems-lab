# Constant-objective query fixtures

These authored scalar integrators use `x[k+1]=x[k]+u[k]`, `x[0]=0`, and `0<=u[k]<=1`, with constant terminal objective zero. They have distinct IDs from HORIZON01. At horizons 2, 4 and 8 every feasible history is optimal. Their exact joint family is the dynamics equality relation intersected with the control box, without any extra terminal optimum restriction.

Direction optimization can select different histories by minimizing positive/negative control-coordinate directions. Independently replay each selected history and evaluate its constant objective. Distinct selections do not prove family completeness; the registered exact verifier and literal fixture oracle supply that evidence. The existing HORIZON01 objective-one cases separately force the all-zero optimal history. Inputs are committed in preparation for the matched query driver; no capture is claimed by these fixtures.
