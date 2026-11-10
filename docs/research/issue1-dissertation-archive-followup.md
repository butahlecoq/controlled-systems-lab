# Issue #1 fuller-dissertation archive follow-up

This note records a bounded, read-only comparison of two supplied dissertation trees. It adds source-version evidence for L04. It does not reproduce a publication run or close [issue #1](https://github.com/butahlecoq/controlled-systems-lab/issues/1).

## A distinct manuscript revision contains the published L04 linear row

The `PhD` tree contains the 37,412-byte AaRC manuscript already described in the [source and criterion version trace](issue1-source-version-trace.md). The fuller dissertation tree contains a distinct 38,966-byte file at `Публикации/Минимакс/Unconstrained for AaRC/Paper/Shorikov_Kalev_AiT.tex`, SHA-256 `b1cbcac49b50282784ba9819fa792ae9c09b0049faa0e694da65ec89a9962891`.

The 38,966-byte content variant reports the four-stage control `{0.6, 0.6, -0.3, 0}` with linear result `67.12` and state `(1201.139, -27.294, 452.606, -61.254)`. It also retains nonlinear state `(1200.139, -2.294, 450.406, -16.254)` and reported value `14.048`. The text and Table 2 entry are at lines 338 and 358–360. By comparison, the previously recorded 37,412-byte variant reports linear value `56.433` with state `(1200.939, -32.294, 451.206, -46.254)`. The distinct text identifies two manuscript content variants. File size and hash do not establish their chronological ancestry or identify the code and run behind either row.

The fuller tree also contains `Публикации/Минимакс/Unconstrained for AaRC/tex/Shorikov_Kalev_AиT_New.tex` (39,898 bytes; SHA-256 `6a79451d2be9ca9a9d4caaab288bf3761cfab200f7729e6d7e54662511b948a5`). It retains the same published `67.12` row. This is another manuscript variant, not independent proof of the numerical result.

## Newly located MATLAB files remain candidates

The fuller tree has an L04-scale source pair under `Публикации/Минимакс/Unconstrained for Space Research/`. `Minmaxopenloop.m` (3,689 bytes; SHA-256 `d997f0479413d452e7ef6e1673c4cace47f627b0a4e611ef014480f6070534cd`) uses initial state `(1182.074, 119610, 459.832, 45220)`, four stages, actions `{0.6, 0.3, 0.01, -0.3, -0.6}`, stage-indexed disturbance vertices, and a Euclidean terminal score. `program.m` (1,290 bytes; SHA-256 `3125634e0c60d02e93984de1a37e81c2df9f4504e19925764701aad09b6759fd`) replays a selected control sequence in the nonlinear model. Its printed `J` expression has an unsquared `(mg(end)-450)` term. The files do not include an attributable output or row-to-run record, and their stated initial state and action set differ from the published L04 setup.

The adjacent `second.fig` (514,923 bytes; SHA-256 `a5116458f760dca192f21d5a0091685d2a43717e0329d91c6a660a1862994b02`) stores endpoint `(1200, 7.298699236853281, 450, 12.003255432742662)`. It does not store the printed nonlinear L04 state. This endpoint and the nearby program do not establish that the program generated the figure.

The separate `Публикации/Минимакс/Constrained/Minmaxopenloop.m` file (3,243 bytes; SHA-256 `0f650a7db58028d7479644546094067268d87f79bcad8c9653408c97175d5c9d`) has the published L04 initial state and action set, plus four stages and the Euclidean score. Its input setup therefore matches those published linear inputs more closely. Static source inspection does not show that it generated the published row, and this file does not recover the nonlinear `14.048` calculation.

## Search result and remaining evidence

A read-only scan compared 129 unique `.fig` and `.mat` file identities across the two trees. It summarized trajectories whose first endpoint coordinate was within three units of 1200, 450, 60, or 24. No scanned saved-figure endpoint matched the printed L04 nonlinear state. Two parse errors came from AppleDouble `._` metadata files. The scan used SciPy's MAT reader and binary64 summaries; it was a bounded filename-based scan, not an inspection of every archive, document, or embedded project.

The source update is specific: the fuller tree contains a manuscript variant with the published linear `67.12` row and additional MATLAB candidates. The nonlinear displayed state and `14.048` remain unexplained, and neither the matching manuscript nor the candidate programs link a source revision to a saved optimization run. The next useful evidence is the original criterion implementation with its unrounded run arrays and output, or an attributable author statement linking a source revision and run to the L04 table. The separate L13 Figure 3/A08 candidate chain is already documented in the existing [source trace](issue1-source-version-trace.md) and is not repeated here.

The [machine-readable source record](evidence/issue1-dissertation-archive-followup.json) stores the archive-relative identities and scan limits. It does not contain the private source files.
