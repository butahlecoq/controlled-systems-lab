# L04 draft uncertainty revision and figure provenance

Date: 2026-11-10. This [issue #1](https://github.com/butahlecoq/controlled-systems-lab/issues/1) follow-up classifies a different uncertainty/table revision in an already identified manuscript. It does not recover a historical MATLAB run. The nonlinear `14.048` discrepancy remains unresolved.

The [existing source trace](issue1-source-version-trace.md) identified the 37,412-byte `Paper/Shorikov_Kalev_AiT.tex` for its Euclidean criterion and nonlinear row. This pass adds a concrete distinction: that draft, its matching 455,509-byte PDF and its embedded figure report linear cost `56.433`, whereas published L04 and the revised TeX report `67.12` with a changed printed disturbance description. The original candidate replay and L13 figure investigations remain separate; no MATLAB code, solver or nonlinear simulation was executed here.

## Source identities distinguish the two versions

The following paths are relative to the owner's supplied `papers/Minimax/Unconstrained for AaRC/` tree. Original private files are not redistributed. The [saved certificate](evidence/issue1-draft-uncertainty.json) records complete byte counts and SHA-256 identities, including the revised figure and both nearby FIG copies.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Known draft `Paper/Shorikov_Kalev_AiT.tex` | 37,412 | `7dfcd12b5f946d459411ba7467d6a176d42ab33c20d56ce860fb8477c6ce956f` |
| Matching draft `Paper/Shorikov_Kalev_AiT.pdf` | 455,509 | `fae5f04fdc7686206d4fdca7dc9891bdf219ed60422a0b1a09e9fc015c449eb9` |
| Draft source figure `Paper/first.png` | 78,648 | `bd528602ab944bc734d7847c7c9aa3106869581edb3896e1d0f3073ebf43da05` |
| Revised `tex/Shorikov_Kalev_AиT_New.tex` | 39,881 | `6bbbf3968862720c6ff90687428a8dac6fe4681998c697ac402650c07be2fa7c` |
| Published L04 `Shorikov_Kalev_AиT_New.pdf` | 390,884 | `6e07c9a2fac2d112885a495c9fe7f13acec9d990d947017b1701a4b95538cd5f` |

The draft/revised labels distinguish the available artifacts. They do not establish revision-control ancestry or a chronological generating-run chain.

The draft numerical section, lines 283–311, has the same displayed four-step `A`, `B`, initial state and five-action catalogue as the later example. Its input-error matrix instead has flow entries `D_11=.2`, `D_32=-.2`. The draft does not numerically instantiate its abstract disturbance polytope `W1` in that example. A unit-box interpretation below is therefore conditional, not a recovered bound.

The revised TeX, lines 344–369, uses unit flow entries `D_11=1`, `D_32=-1` and explicitly states `|w1(t)|<=.1+.1*t`, `|w2(t)|<=.1+.3*t`. Its PDF matches registered L04 exactly. The printed uncertainty descriptions and linear results differ. Their numerical uncertainty images cannot be equated without supplying the draft's missing `W1`; they must retain separate source/result identities.

| Displayed item | Draft | Revised / published L04 |
| --- | --- | --- |
| Chosen plan | `(.6,.6,-.3,0)` | `(.6,.6,-.3,0)` |
| Nonlinear row | `(1200.139,-2.294,450.406,-16.254)` | Same text row; table rounds to `(1200.14,-2.29,450.41,-16.25)` |
| Reported nonlinear cost | `14.048` | `14.048` in text, `14.05` in table |
| Linear row | `(1200.939,-32.294,451.206,-46.254)` | `(1201.14,-27.29,452.61,-61.25)` |
| Reported guaranteed/linear cost | `56.433` | `67.12` |

The unchanged nonlinear numbers survive the uncertainty revision. That is evidence of distinct document versions, not proof that a particular source file generated either table.

## Exact row offsets match the printed error descriptions

For either flow/stock pair, the displayed transition block is `[[1,0],[-25,1]]`. If positive flow-error increments are `e_t`, their four-step image is

`(sum(e_t), -25*sum((3-t)*e_t)), t=0,...,3`.

The [standard-library Fraction certificate](tools/check_issue1_draft_uncertainty.py) checks both pairs independently:

- Draft linear minus draft nonlinear row is exactly `(.8,-30,.8,-30)`. Four increments `(.2,.2)` give that image. With the draft's printed `D`, this is the conditional repeated disturbance `(w1,w2)=(+1,-1)`; no claim about the missing numeric `W1` follows.
- Revised linear minus revised table nonlinear row is exactly `(1,-25,2.2,-45)`. The positive flow increments are `(.1,.1)`, `(.2,.4)`, `(.3,.7)`, `(.4,1)`, exactly the stated time-varying bounds with the fuel disturbance sign reversed by `D`.

These equalities concern literal displayed rows. They do not prove that the displayed nonlinear row is the nominal affine terminal state. The certificate separately propagates the printed initial state, `B` and plan with zero disturbance and obtains `(1200.1397,-2.3275,450.4063,-16.2725)`. This differs from the draft nonlinear row by `(.0007,-.0335,.0003,-.0185)`. No unrounded input, coordinate correction or nonlinear integration is inferred to erase that difference.

The draft linear row's literal Euclidean norm is about `56.4328903123`, which rounds to `56.433`. The nonlinear text row's squared Euclidean cost remains exactly `269639109/1000000`, norm about `16.4206914897`, not `14.048`. The revised coarse linear row's literal norm is about `67.1149633092`; this is not an exact reconstruction of `67.12`. The existing [rounding-box audit](b08-reported-rounding-audit.md) remains the separate authority for uncertainty due to printed coordinate precision.

## The matching PNG is positive asset provenance

The draft PDF contains one 1481-by-675 RGB image on PDF page 10. `pdfimages -png` extracts decoded pixels identical to `Paper/first.png`, with RGB payload SHA-256 `b2f29b56337fb046cade94b9699ebbeda017533b6dcfb513b121f9eeea3e38c0`. The TeX also includes `first.png` at line 315.

The image annotates the same plan, guaranteed value `56.433`, nonlinear terminal coordinates and `14.048` value as the draft text. Its linear zero-disturbance and nonlinear trajectories have the labels described by that text. This binds the available source image to the draft PDF. It does not recover plotted numeric arrays, an optimizer output or a source-controlled MATLAB revision; raster annotations are not unrounded run records.

## Nearby second.fig is a different case

`second.fig` beside the manuscript and `papers/Minimax/Unconstrained/second.fig` are byte-identical: 108,014 bytes, SHA-256 `f0ca6b5a7bf5297a0771284f46e811b04fbf0aba7b4597d23b4f37b95edeea5e`. Read-only MATLAB-v5 decoding finds two 1,001-point stair-series with these first/final pairs:

| Plane | First point | Final point |
| --- | --- | --- |
| First | `(29.375148491328105,302)` | `(30,6.0345294958112055)` |
| Second | `(20.399408674533408,207)` | `(20,4.473053442902353)` |

Their reference lines use flows 30 and 20. They do not store the L04 trajectories in its stated 1200/450 flow coordinates. No source-backed transformation between these cases was recovered, so none is invented. The nearby candidate MATLAB files retain similar 30/20 plotting limits despite their different fuel parameter block; that is another reason not to identify a figure with a driver by its filename alone. This excludes these inspected FIG copies as direct unrounded L04 evidence, not other possible figures or archives.

## Recheck without executing historical software

The public arithmetic certificate and saved record require only Python's standard library:

```sh
python3 -B docs/research/tools/check_issue1_draft_uncertainty.py \
  --verify-record docs/research/evidence/issue1-draft-uncertainty.json
```

With the original private inputs, an existing source-inspection environment can additionally check all eight exact file identities, decode the FIG data, and compare the PDF/PNG pixels:

```sh
<PINNED_EXISTING_ENV>/bin/python -B docs/research/tools/check_issue1_draft_uncertainty.py \
  --private-papers <SUPPLIED_PAPERS_DIRECTORY> --figure-check --pixel-check \
  --verify-record docs/research/evidence/issue1-draft-uncertainty.json
```

The optional data inspection uses existing SciPy/Pillow and Poppler `pdfimages`; it installs nothing and executes no MATLAB, TeX, optimizer or plant code. Generated image extraction stays in temporary private scratch. The note and certificate add no core API, required dependency, public numerical example or release/package action.

The useful new disposition is to distinguish the draft's uncertainty/linear-table revision from published L04 and to retain their shared unresolved nonlinear report. Original unrounded arrays, the generating driver/configuration, its exact objective implementation and its row attribution remain missing. Keep issue #1 open. No scientific result, historical row or earlier source trace is replaced by this classification.
