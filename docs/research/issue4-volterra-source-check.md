# Issue 4: Volterra candidate source check

2026-10-19. This note fixes the source boundary for a corrected-track, same-control calculation. It supplements the [L05 Example 1 dossier](l05-example1-source-dossier.md) and does not identify the historical Table 1 generator.

## Checked sources

The private `Volterra.m` candidate in the local publication archive has SHA-256 `c26fc2424fa8b3325a864d1afbc67920ba1c05665bfdf4562bed79548b60a4f1` (verified from the file bytes on 2026-10-19). It is not copied into this repository. The registered local L05 PDF, SHA-256 `dfc76d4d33dad578567f851ae8169a44af290d2e17ea826cec46271dde2d311d`, was checked at one-based PDF pages 8–10 against the [publisher article page](https://vestnikmi.bsu.ru/?article=1063&issue=34&rus=). L05 cites Shorikov and Goranov 2017 as [5]. The [existing dossier](l05-example1-source-dossier.md#cited-source-and-generator-search) records a prior inspection of the [publisher PDF for that cited article](https://ered.pstu.ru/index.php/amcs/article/download/2225/1690): its flight-model example is separate from this candidate. The publisher PDF returned HTTP 403 on this check, so that finding is inherited from the dossier rather than independently reverified here. The L05 PDF and private MATLAB file remain outside version control.

## Literal candidate inputs and recurrence

The candidate sets `x0(:,1)=(410,300)`, `x_ref=(400,300)`, `a=0.9`, `b=a/300=0.003`, `c=0.8`, `d=c/400=0.002`, `e=0.85`, `n=60`, and `T0=(2*pi/sqrt(a*c))/n`. Its first loop builds a zero-control, forward-Euler reference `x0(:,i+1)` from `x0(:,i)`. An `ode45` call precedes each Euler update, but the sampled value appears only in an expression multiplied by zero to form `U(i)`; the Euler update uses `U(i)=0` for finite values.

The second loop starts **both** `z(:,1)` and `x(:,1)` at `(1,2)`. For one-based loop index `i=1,...,60`, it builds

```text
A_i = [[1 + T0*a - T0*b*x0(2,i+1), -T0*b*x0(1,i+1)],
       [T0*d*x0(2,i+1),          1 - T0*c + T0*d*x0(1,i+1)]]
B_i = (T0*e, 0)^T
z_(i+1) = A_i*z_i + B_i*u_i
x_(i+1) = A_i*x_i + B_i*u_i + T0*(-b,d)^T*x_i,1*x_i,2.
```

The later reachability loop computes `P=(repmat([-15,15],n,1)-[U;U]')/50`, hence each scalar control endpoint is `-0.3` or `0.3` when `U=0`. It branches over those endpoints, calls `ConvSM_mod` on each propagated array, and plots the resulting sections. Its `Approx_mod` calls are commented out. The enclosing `tic`/`toc` does not isolate either algorithm or produce Table 1's reported per-algorithm timings.

## Historical boundary

L05 prints a physical nonlinear start `(410,300)`, a displayed linear start `(1,2)`, and matrix coefficients based on a zero-control reference. It does not print a coordinate map or reference samples. Moreover, its displayed matrix uses the reference at `t`, while the candidate first uses `x0(:,2)` (`i+1`). The script's `x` recurrence is therefore a candidate corrected-coordinate nonlinear map, **not** a demonstrated reproduction of the printed physical recurrence or its Figure 1 and Table 1 outputs. No historical driver identity, full feasible-history enumeration, saved numerical output, independent general-method run, volume calculation, or separate timings were found in this file. An enclosure derived from these literal recurrences can speak only to this candidate's own shared start, controls, and 60-stage recurrence. It cannot establish nonlinear reachable-set inclusion for L05 or validate any Table 1 cell.

A later [saved-figure audit](l05-saved-figure-audit.md) recovered private FIG terminal polygons whose stored vertex counts and areas match all three Table 1 Example 1 rows. This strengthens source-to-number correspondence but does not identify the generating code revision or establish an all-history nonlinear enclosure.
