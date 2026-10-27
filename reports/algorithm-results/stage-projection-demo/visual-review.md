# Stage projection demo visual review

Review date: 2026-10-27

## Fuel, four-state model

Reviewed the checked-in offline renderer and its saved projections under
`benchmarks/reporting/stage-projection/bundle-v1/fuel-four-state-figures/`.
The four PNGs are each 3960 × 1980. They show all saved stages R0–R5 as
separate 2D panels for the ordered state-coordinate pairs x0/x2, x1/x3,
x0/x3, and x1/x2. The example depicts fuel flow and stock alongside
oxidizer flow and stock; each plot marks saved V generators and the selected
trajectory. The figures do not reconstruct set boundaries, which is stated in
the caption and bundle metadata.

Inspected asset: `projection-01-x0-x2.png` (3960 × 1980), opened directly
from the bundle. Its six stage panels and physical coordinate labels/units
are legible at native image size. I also rasterized the actual SVG
`projection-01-x0-x2.svg` with `rsvg-convert`; the inspected preview is
`visuals/fuel-svg-preview-1440x720.png` (1440 × 720). The rendered desktop page
capture is `visuals/fuel-desktop.png` (1440 × 1600). The narrow viewport capture
is `visuals/fuel-narrow-390x900.png` (390 × 900); at that viewport, the document
reflows to a single column and the page scrolls vertically. The long evidence
description precedes the plot, so the plot is below the initial mobile
viewport and requires scrolling.

Print review used WeasyPrint 70 against the offline page, with its print media
rules active. The PDF is `visuals/fuel-print-weasyprint-70.pdf`: nine A4 pages
(595.276 × 841.89 pt). The first page is the introduction; the first six-stage
fuel-flow figure appears on page 3 at
`visuals/fuel-print-page3-827x1170.png` (827 × 1170). All four saved figures
appear, but each is split across separate pages: the verbose stage evidence
description occupies one page and the plot with its SVG/PNG links the next.
The plots are small with substantial unused page area. This print layout is
legible when enlarged but is not compact. Chromium's native PDF export could
not be completed: Crashpad reported the environment's temporary disk quota;
the inspected PDF therefore comes from WeasyPrint rather than Chromium.

## Nonfuel control

Inspected the nonfuel planar integrator PNG
`benchmarks/reporting/stage-projection/bundle-v1/nonfuel-integrator-figures/projection-01-x0-x1.png`
(3960 × 990) directly. The four panels show R0–R3 with trajectory overlay. I
also rasterized and inspected the actual SVG
`benchmarks/reporting/stage-projection/bundle-v1/nonfuel-integrator-figures/projection-01-x0-x1.svg`
at `visuals/nonfuel-svg-preview-1440x360.png` (1440 × 360). The offline desktop
page capture is `visuals/nonfuel-desktop.png` (1440 × 1100). At a 390 × 900
mobile viewport, `visuals/nonfuel-narrow-390x900.png` shows single-column reflow; the
graph is below the long evidence text and outside that initial viewport.

The nonfuel print PDF is `visuals/nonfuel-print-weasyprint-70.pdf`: two A4 pages.
The graph appears on page 2 at `visuals/nonfuel-print-page2-827x1170.png`
(827 × 1170), below its long evidence description. It is visible but small
within the printable page area.

## Limits

WeasyPrint 70 warned that it ignores the renderer's screen-only
`@media(max-width:640px)` rule. Its print media rule was applied. Chromium's
native PDF export remains unverified: Crashpad reported the environment's
temporary disk quota. These are saved-bundle display checks; they do not validate the numerical
reachability model. The independent projection integration test provides the
separate geometry oracle. The print CSS exists in the offline renderer, but
the Chromium print path remains unverified, and the inspected WeasyPrint output
shows the current page-break layout wastes paper.
