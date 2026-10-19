# B06 primary-source control-sequence audit

Date: 2026-10-19. This audit resolves an OCR ambiguity in the displayed B06 linear minimax control sequence by visual inspection of the registered primary scan. It does not reproduce the linear minimax calculation or the nonlinear simulation.

## Source and reading

L09 is registered in the [source inventory](inventory.json) with SHA-256 `bb32b230e600fd0871322768dbf42d181fa7a0a288b97c717659a6448e3b72aa`. The local source matched that hash. PDF p. 11 was inspected visually at the paragraph that reports the final set of program minimax controls.

The page defines the available actions as `{1, 0.3, 0, -0.3, -1}` and indexes the five controls by `t = 0, …, 4`. It prints the unique reported linear minimax program sequence as

```text
u^e(·) = {u^e(t)}_{t=0}^4 = {-0.3, 1, 0, 0, 0.3}.
```

Thus the first sign is negative and the final action is positive `0.3`. The extracted text's displaced minus signs should not be used to infer a different sequence.

## Scope and unresolved inputs

This reading applies to the linear finite-action minimax result described on p. 11, which reports criterion `10.11`. Table 2 separately reports nonlinear terminal coordinates `(30, 6.03, 20, 4.47)` and criterion `9.049`. The page does not establish, in a way independently recoverable from the extracted table, the exact nonlinear control path or its correspondence to the displayed linear sequence.

The numerical example gives the disturbance matrix and says the disturbance belongs to an admissible set, but the archived text and inspected numerical page do not supply numeric bounds or vertices for that set. The reported worst-case result therefore remains non-reproducible from the transcribed inputs. This source check resolves only the sequence's printed sign and order; it does not supply missing disturbance data, a historical run configuration, or independent validation of either reported result.
