# B04 numerical tables

Date: 2026-10-11. Source: A11, the owner's requested legacy Word file, and the second copy under Publications/TiSU. The numerical table text agrees in both copies. Policy labels were cross-checked visually against A12 PDF p. 20, which contains the same tables. Source hashes are in the [archive register](archive-selected-sources.json). Original documents remain unchanged.

## Table 1: nonlinear-model parameters

| Parameter | Reported value |
|---|---:|
| I | 320 |
| P | 528000 |
| K | 8/3 |
| Nominal oxidizer working stock | 120000 |
| Nominal fuel working stock | 45000 |
| Oxidizer stock perturbation | -500 |
| Fuel stock perturbation | 300 |
| Initial mixture-ratio perturbation | 8/75 |
| c1 | 8/75 |
| c2 | -1675 |
| c3 | 2250 |
| c4 | -15 |
| c5 | -12 |
| Final physical time, seconds | 100 |

Values are transcribed, not inferred from related MATLAB scripts. Preserve the source's parameter definitions and unit conventions when constructing a nonlinear replay; this table alone does not establish a replay/control-timing convention. P is labelled kg in the source table; no SI-force conversion is performed here.

## Table 2: terminal outcomes

State order: oxidizer flow, oxidizer working-stock balance, fuel flow, fuel working-stock balance. Units: kg/s, kg, kg/s, kg.

| Model / policy | x1 | x2 | x3 | x4 | Reported objective |
|---|---:|---:|---:|---:|---:|
| Nominal reference, u(t)=0 | 1200 | 0 | 450 | 0 | 0 |
| Nonlinear, frozen-coefficient regulator u* | 1190.4 | 101.7 | 455.12 | -72.817 | 368.45 |
| Nonlinear, optimal linear witness 1 | 1200.5 | -2.695 | 449.72 | 10.556 | 41.855 |
| Nonlinear, optimal linear witness 2 | 1200.5 | 0.50887 | 449.72 | 17.561 | 65.874 |
| Nonlinear, optimal linear witness 3 | 1200.5 | -6.366 | 449.72 | -1.475 | 7.922 |
| Linear, any of witnesses 1–3 | 1200.7 | -22.929 | 450.2 | -7.709 | 30.899 |

The nominal reference is a separate reference trajectory, not a demonstrated zero-control solution from the perturbed B04 initial state. The three witness policies are optimal for the linear model; this table does not assert global optimality for the nonlinear model.

## What this supplies

The missing tables from the supplied main-text PDF are now recovered. They provide nonlinear parameter values, policy-to-row assignments and reported terminal outcomes. The linear row's objective independently evaluates to 30.898903573 using its displayed coordinates and the printed weighted residual norm.

The table does not list complete control histories or numerical U_t. On 2026-10-11, the owner recalled that the control interval was most likely [-1,1]. Record that as a provisional working hypothesis, supported by related scripts, rather than a quotation from Table 1 or Table 2. This can inform a separately labelled exploratory scenario; it does not silently change the historical manifest's execution status.

Reported objectives and displayed coordinates have different precision. Evaluations at printed coordinates must remain distinct from reported outcomes; do not turn every rounded table entry into an exact equality test. The [displayed linear-model consistency question](b04-restoration.md) remains independent of recovering these tables.

## Architecture consequence

A family of linearly optimal control/trajectory pairs can have different nonlinear replay quality. WitnessSelector should expose different complete histories, and ComparisonRunner should associate each witness with its nominal objective and separately evaluated replay result. The reference plant is a separate simulation model with its own parameters, initial conditions and integration/time conventions.

This supports the owner's requested visual/numerical/runtime comparison of methods. A single terminal optimizer or one selected control cannot communicate the variation shown by the three nonlinear rows. Selecting the best replay witness may become a later query, but is not evidence that the linear optimal-family algorithm solved the nonlinear optimal-control problem.
