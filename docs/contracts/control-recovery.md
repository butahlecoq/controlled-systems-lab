# Joint-history control recovery

`recover_joint_history` constructs the feasible preimage of a supplied terminal-state relation as one H-polyhedron over the canonical joint coordinates

`[x_0, ..., x_T, u_0, ..., u_(T-1)]`.

The result contains every state and control variable. Its rows encode the known initial state, each stage-state constraint, each continuous control constraint, every discrete transition equality, and the supplied terminal relation. No state or control coordinate is projected away, so cross-stage dependencies remain present in the returned relation. The implementation writes the equations directly; it does not invert a state-transition matrix and therefore accepts singular transition matrices when the represented relation remains within the supported profile.

The first supported profile is discrete nominal open-loop dynamics with a known point initial condition, continuous controls, no external input, no temporal coupling constraints, and native H, singleton, empty, or universal state/control/terminal sets. Finite and mixed control catalogues, external inputs, temporal constraints, V-representations, and set conversion are rejected explicitly.

The caller supplies the terminal-state relation. This module does not optimize the terminal objective or prove that the supplied relation is the full argmin set. A constant objective must be paired with the full feasible terminal set if every feasible history is to be retained. The output is a feasible-history construction only; H-row assembly and successful set creation do not establish numerical coverage, optimality, or complete-family assurance. The caller must use the shared evidence boundary and preserve `Unestablished` coverage where no reviewed verifier supports a stronger claim.

This module is a recovery primitive, not yet a registered synthesis strategy. It does not replace forward reachability, terminal optimization, strategy admission, provider lineage, or independent trajectory verification.
