# MPC-11 comparison delivery

Continue #607 from reviewed controller source ce5899e8. Preserve all three pilot
archives and their mathematical identities. The user authorized autonomous
implementation, comparison runs and publication.

1. Generate a saved-data reading layer from the affine, nonlinear replay and
   shrinking-horizon NMPC archives. Verify archive inventories and run the
   existing saved checkers before rendering. Do not optimize in the renderer.
2. Overlay affine prediction, affine controls on the nonlinear plant, and NMPC
   nonlinear execution. LV uses P/R; fuel uses oxidizer mass/flow and fuel mass/flow. Select these by state
   name because the canonical stored order is masses followed by flows.
   Mark initial/terminal states, target and physical time samples. Add state and
   held-control traces. These are trajectories, not reachable sets.
3. Bind exported SVG/PNG and plotted arrays to archive/source/scenario/witness
   identities with hashes. Reuse scripts/reports/figure_style.py and the locked
   Matplotlib environment. Reject changed/missing records before output writes.
4. Check local mesh sensitivity with a separately identified controller
   configuration and retain all outcomes. For timing comparisons use the
   contract's five alternating repetitions and separate limiter profile; retain
   setup, optimization and integration scopes. Until that evidence exists,
   describe pilot times only and make no comparative performance claim.
5. Independently review specification and standards at exact commits. Integrate
   through current-head CI. Add a unique Pages staging hook while coordinating
   shared augmentation/inventory ownership with MPC-06. Verify deployed plots
   and raw downloads before calling publication complete.

No new core API or required dependency is planned; this optional reporting
consumer needs no library release. Existing solver license qualification and
synthetic-model boundaries remain authoritative. No acados execution.
