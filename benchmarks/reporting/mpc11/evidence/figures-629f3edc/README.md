# Saved MPC-11 trajectory comparisons

Renderer source: `629f3edc`. Three immutable pilot archives supply the data:
affine `b3978a98`, nonlinear replay `0092081b`, and NMPC `55f65110`.
Their accepted records were independently checked before rendering; the receipt
retains three affine checks, two nonlinear replay checks and two NMPC checks
covering all 70 saved transcriptions. No optimization or integration was rerun.

Fuel plots select oxidizer mass/flow and fuel mass/flow by canonical state
names, because stored coordinates place both masses before both flows.
LV plots P/R. The three variants are individually labelled trajectories with
physical times, initial/final markers and terminal targets. State and held
control traces accompany them. Affine segments connect hold-boundary values.
These plots do not establish reachable sets, global optima, minimax control,
continuous safety or comparative timing performance.

`receipt.json` binds plotted record bytes, source/checker/style identities,
checks, manifests and all ten exported files. `SHA256SUMS` additionally binds
this reading layer. See `../../FIGURES.md` for reproduction from the original
archives. This export remains identified by its actual renderer source even
if later checking or publication tools change.
