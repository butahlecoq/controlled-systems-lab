# Complete-family verifier seam blocker

The current complete-family publisher runs inside a strategy workspace and receives only a self-asserted `FamilyIdentity` plus outcome. It cannot select a trusted verifier from the prepared registration or check the authoritative `ResolvedProblem` and frozen effective request. Adding a verifier callback to `StrategyRegistration` is unsafe because downstream registrations can supply their own publisher authority.

A safe seam must carry complete-family proposals to a boundary that owns the prepared problem, effective request, selected strategy ID/version, relation, optimum, lineage, and assurance. That boundary must dispatch through a compiled verifier catalog keyed by trusted strategy ID/version and reject unknown keys. The T-S01 checker must validate the exact resolved profile and canonical relation there. Its present implementation lives with the T-S01 plugin, while `csl_registry` must remain below `csl_resolved_problem`; moving publication and checker code therefore needs a deliberate extraction of the verifier and relation checks into a dependency-compatible module.

The current branch does not meet this boundary: the installed-client regression records the definition-injection exploit and fails because the forged complete family is accepted. Do not treat this PR head as safe to merge until the compiled verifier seam closes the regression.

