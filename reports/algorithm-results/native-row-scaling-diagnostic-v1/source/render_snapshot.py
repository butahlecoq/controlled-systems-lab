"""Render the source-only report from saved records, without native code or optimization."""
from __future__ import annotations
import argparse
import sys
sys.dont_write_bytecode = True
from html import escape
import json
from pathlib import Path
import site_design_snapshot as design


def render(root: Path) -> str:
    check = json.loads((root/'records/portable-check.json').read_text())
    execution = json.loads((root/'records/execution-manifest.json').read_text())
    toy = json.loads((root/'records/analytic-result.json').read_text())
    if toy['observed_x'] != [1.5,1.5] or check['analytic_check'] != 'passed':
        raise ValueError('Saved analytic check/point changed')
    parts = [design.page_start('Positive row scaling: three retained native QP outcomes', stylesheet_href='examples.css')]
    parts += ['<p class="eyebrow">Native C++ · saved numerical diagnostic · source-only evidence</p>',
              '<h1>Positive row scaling admits the model; it can still fail numerically</h1>',
              '<p>A bounded diagnostic revisited three HiGHS refusals from the 35-model tracking first pass. '
              'Multiplying constraint rows by exact positive powers of two preserved their represented equations. '
              'Model 23 completed a trivial zero-state case; models 27 and 28 still failed numerically. '
              'This is no conditioning, performance, robustness or stability claim.</p>',
              '<p><a href="native-row-scaling-diagnostic-v1.zip">Download the immutable source-only evidence ZIP</a> · '
              '<a href="guide.html">Check or reproduce</a> · <a href="manifest.json">Frozen file manifest</a> · '
              '<a href="../native-model-tracking-first-pass-v1/index.html">Original 35-case first pass</a></p>',
              '<section><h2>What changes, and what stays the same</h2>',
              '<p>For each constraint row, a positive multiplier preserves its feasible half-space:</p>',
              '<p class="equation">aᵢᵀz ≥ bᵢ ⇔ dᵢ aᵢᵀz ≥ dᵢ bᵢ, &nbsp; dᵢ = 2<sup>kᵢ</sup> &gt; 0.</p>',
              '<p>The same equivalence applies to equality and interval rows. The native helper changes only '
              'constraint coefficients and their row bounds. It keeps the quadratic objective and variable bounds. '
              'It rejects overflow, underflow and any coefficient or finite-bound inverse scaling that changes a binary64 bit. '
              'Unbounded optional endpoints remain unbounded.</p>',
              '<p>This profile normalizes only rows with an actual nonzero coefficient at or below 10<sup>−12</sup>. '
              'It chooses kᵢ = max(0, −ilogb(min |aᵢⱼ|)), so their smallest nonzero magnitude lies in [1,2). '
              'It is distinct from merely lifting a coefficient above the threshold; large coefficient ratios can remain.</p>',
              '<p>The original logical model/task identities remain references. Each transformed numerical program '
              'has the distinct suffix <code>/diagnostic-row-min-power2-v1</code>. The mathematical dual relation is '
              'y<sub>original</sub> = D y<sub>scaled</sub>. No public dual vector was emitted, so no actual dual remapping '
              'or dual certificate is asserted.</p></section>',
              '<section><h2>A supported 2D sanity case, in original coordinates</h2>',
              '<p>Before the model attempts, native C++ solved the exact-dyadic toy:</p>',
              '<p class="equation">minimize x² + y², &nbsp; 2<sup>−50</sup>(x+y) = 3·2<sup>−50</sup>.</p>',
              '<p>Multiplication by 2<sup>50</sup> gives x+y=3. The analytic optimum is x=y=1.5, with original '
              'objective 4.5. The marked point comes from saved native stdout; the analytic marker is independent.</p>',
              '<figure><img src="toy.svg" alt="Original feasible line x plus y equals three, with recorded native point and analytic optimum both at one point five, one point five">'
              '<figcaption>Original coordinate geometry, not a plot of scaled row coefficients. Inputs are the represented binary64 dyadic values; '
              'solver and replay evidence is numerical. <a href="records/analytic-result.json">Point and exact inputs</a> · '
              '<a href="records/attempts/analytic-normalized/stdout.log">Native stdout</a> · '
              '<a href="records/attempts/analytic-normalized-output/native.txt">Full native log</a></figcaption></figure></section>',
              '<section><h2>All three outcomes remain in the record</h2>',
              '<table><caption>One bounded diagnostic profile, without a cross-model ranking</caption><thead><tr>'
              '<th scope="col">Model</th><th scope="col">Original compiled matrix</th><th scope="col">Observed outcome</th><th scope="col">Raw evidence</th>'
              '</tr></thead><tbody>']
    descriptions = {
        23: ('38 rows; 6 offending entries; minimum 6.855804411066206×10⁻¹⁷',
             'Three replans completed. Zero initial state and zero nominal input yield a trivial zero optimum. This establishes no nonzero-state control or stabilization result.'),
        27: ('110 rows; 780 offending entries; minimum 2.1740349403908295×10⁻²⁷',
             'LP feasibility reported optimal, but the adapter rejected its start: start.valid=false and qp_run=false. No completed QP control plan; not a claim of original-problem infeasibility.'),
        28: ('220 rows; 4,800 offending entries; minimum 9.298585042071114×10⁻³⁷',
             'Native LP feasibility failed with excessive primal values. No completed QP control plan; not a claim of original-problem infeasibility.')}
    for number,(matrix,outcome) in descriptions.items():
        path=f'records/attempts/model-{number}-row-scale-output'
        links=f'<a href="{path}/replan-0/rows.csv">Rows, stages and exponents</a> · <a href="{path}/replan-0/csr.csv">Original/scaled CSR</a> · <a href="{path}/native-replan-0.txt">Full native log</a> · <a href="records/attempts/model-{number}-row-scale/attempt.json">Attempt receipt</a>'
        parts.append(f'<tr><th scope="row">{number}</th><td>{matrix}</td><td>{outcome}</td><td>{links}</td></tr>')
    parts += ['</tbody></table><p>The resulting whole-matrix magnitude ranges were approximately '
              '[7.93×10<sup>−5</sup>, 1.80×10<sup>16</sup>], [1, 6.19×10<sup>26</sup>] and '
              '[1, 1.33×10<sup>36</sup>], respectively. Large ranges remain; algebraic admission '
              'alone cannot establish a numerically usable solve. No further retry is included.</p></section>',
              '<section><h2>Check the original task, not only a tiny row residual</h2>',
              '<p>The three models retain the first pass’s separately authored nominal tracking task: a three-stage horizon '
              'at each of three observed-state replans, target zero, input bounds [−1,1] in recorded coordinates, '
              'no state bounds, Q diagonal weights 1/max(1,|x₀ᵢ|)², terminal weight 5Q and R=0.02I. '
              'These are task choices, not source calibration. Source matrices, coordinates and external-channel roles are unchanged.</p>',
              '<p>For completed model 23, an independent checker replayed all nine full eight-state predicted transitions, '
              'initial-state binding, applied first controls, executed next states, original input bounds and original objective. '
              'Maximum dynamics residual and objective difference were both zero. Models 27 and 28 have no accepted completed '
              'trajectory to replay. The checks do not reinterpret a numerical failure as mathematical infeasibility.</p>',
              '<p><a href="records/portable-check.json">Portable check results</a> · <a href="records/independent-checks.json">Captured independent checks</a> · '
              '<a href="inputs/models.csv">Saved native model coefficients</a> · <a href="inputs/provenance.json">Input provenance</a></p></section>',
              '<section><h2>Execution and source boundary</h2>',
              '<p>GNU C++ 16.2.1 and CMake 3.31.6 built two small Release consumers against a read-only, 240-file installed snapshot. '
              'HiGHS was version 1.11.0, with one requested native thread. All SDK hashes matched before and after; the history '
              'compiler header/archive matched their earlier source-bound component qualification. This is a new local consumer, '
              'not fresh whole-SDK qualification.</p>',
              '<p>Each attempt used one worker, a 300-second process-group wall timeout, inherited 300-second per-process CPU '
              'limit and 8 GiB per-process virtual-address-space limit. These are Linux RLIMIT_AS/CPU scopes, not aggregate RSS '
              'or cgroup caps. A policy probe read back the limits and received ENOMEM for a 9 GiB mapping. No timeout occurred; '
              'cancellation was configured, not exercised. Post-wait checks found no remaining process groups. '
              'No timing comparison or performance winner is reported.</p>',
              '<p>The exact executed C++ helper sources are included. Host paths in receipts and two local Python text '
              'projections use named location tokens, with original hashes and the projection mapping retained. Portable '
              'checker/reproduction helpers are supporting adaptations, not falsely labelled as the captured executable. '
              'No ELF, static library, vendor source or SDK payload is distributed. Binary licensing and distribution remain outside this unit.</p>',
              '<details><summary>Exact source, compiler, SDK and configuration records</summary><ul>'
              '<li><a href="records/execution-manifest.json">Executed source, binary and compiler hashes; flags and SDK archive references</a></li>'
              '<li><a href="records/curation.json">All 93 captured-file dispositions and hash mappings</a></li>'
              '<li><a href="records/original-local-seal.sha256">Original local seal, including omitted binary hashes</a></li>'
              '<li><a href="records/sdk-inventory.json">240 SDK file hashes, without the SDK</a></li>'
              '<li><a href="source/row_scaling_driver.cpp">Executed native driver source</a> · <a href="source/row_scaling.hpp">Executed native transform source</a></li>'
              '<li><a href="source/check_evidence.py">Portable independent checker</a> · <a href="source/reproduce.py">Optional source-only runner</a></li>'
              '</ul><p>Captured configuration SHA-256: <code>'+escape(execution['configuration_sha256'])+'</code>.</p>'
              '<p>Baseline source parent: <code>'+escape(execution['baseline_source_commit'])+'</code>. '
              'The helper’s actual source hashes are separate and bind its uncommitted local spike at execution time.</p></details></section>',
              '<p>This diagnostic appends evidence to issue #1012. It preserves all 35 original first-pass cases and their '
              'locked ZIP; it neither completes the all-model/formulation matrix nor changes the three canonical comparison task identities.</p>',
              design.page_end()]
    return ''.join(parts)

def render_guide() -> str:
    return (design.page_start('Check or reproduce the source-only row-scaling diagnostic', stylesheet_href='examples.css') +
        '<p class="eyebrow">Source-only reproduction guide</p><h1>Check saved evidence before a new native replay</h1>'
        '<p><a href="index.html">Return to the three-outcome report</a>. The immutable ZIP includes numerical inputs, '
        'original and scaled rows, complete failure logs, exact executed C++ sources and source/hash receipts. '
        'It includes no compiler, ELF executable, static library, vendor source or SDK payload.</p>'
        '<h2>Check the saved data without an SDK</h2><p>Unzip into a fresh directory. Python 3.11 or later is sufficient:</p>'
        '<pre class="lesson-reproduction"><code>python source/check_evidence.py .</code></pre>'
        '<p>This recomputes exact rational row-scaling relations and checks the accepted full-state trajectory and original '
        'cost. It never runs a solver. Compare with <a href="records/portable-check.json">the saved check result</a>.</p>'
        '<h2>Provide a matching installed snapshot for a new attempt</h2>'
        '<p>The optional runner requires Linux and a caller-supplied installed CSL prefix matching all 240 hashes in '
        '<a href="records/sdk-inventory.json">the snapshot inventory</a>. The original consumer used GNU C++ 16.2.1, '
        'CMake 3.31.6, Release and HiGHS 1.11.0. Required CMake targets are CSL::model_catalogue, '
        'CSL::nominal_quadratic_history and CSL::highs_convex. Component/header matches do not qualify a whole SDK.</p>'
        '<pre class="lesson-reproduction"><code>python source/reproduce.py --sdk-prefix /path/to/matching/prefix  --build /path/to/fresh/local-build --output /path/to/fresh/new-attempts  --cmake /path/to/cmake-3.31.6</code></pre>'
        '<p>The build and output directories must be new. The runner verifies the prefix before and after, builds only '
        'the two small consumers with one job, holds an exclusive lock across the sequence and runs the analytic toy '
        'before models 23, 27 and 28. It retains every outcome. A different compiler creates new binary hashes and '
        'must remain a new attempt. The portable runner’s help path was checked during publication; it did not generate '
        'the captured attempts and was not used to repeat the numerical experiment.</p>'
        '<h2>Keep the policy and identities explicit</h2>'
        '<p>Each run uses a 300-second process-group wall timeout, inherited 300-second per-process CPU limit and '
        '8 GiB per-process virtual-address-space limit, with one requested native thread. These are Linux RLIMIT '
        'scopes, not aggregate RSS limits. Numerical failures and timeouts remain records; neither model 27 nor '
        'model 28 in this capture is labelled infeasible.</p>'
        '<p>The task remains the authored N=3, three-replan nominal profile. Only coefficients and intervals of selected '
        'constraint rows receive positive powers of two. Objective and variable bounds stay the same. Derived numerical '
        'program IDs carry a diagnostic suffix and retain the original problem/task reference. Never drop small '
        'coefficients or loosen the native threshold to imitate a successful replay.</p>'
        '<h2>Read the provenance boundary</h2>'
        '<p><a href="records/curation.json">The curation map</a> lists all 93 original-file dispositions and original/public '
        'hashes. The executed C++ files retain exact captured bytes. Two executed local Python scripts are labelled '
        'location-token text projections; they are not portable executables. The portable checker and runner are '
        'supporting adaptations, distinct from those captured scripts. Original compiler, binary, source and SDK '
        'hashes remain in <a href="records/execution-manifest.json">the execution receipt</a>.</p>'
        '<p>Source-only delivery leaves project binary-distribution terms and third-party binary redistribution gates '
        'unresolved. No binary installation or new package release is part of this report.</p>'
        '<h2>Regenerate presentation only</h2>'
        '<p>The shared framing and CSS are frozen snapshots for this version. The saved-data renderer checks HTML '
        'without optimization:</p><pre class="lesson-reproduction"><code>python source/render_snapshot.py --check</code></pre>'
        '<p>Plotting is optional and separate; source/plot_toy.py uses Matplotlib to draw the saved native point and '
        'analytic equality. It does not solve the toy. Library versions can change SVG serialization, so a new plot '
        'does not silently replace this locked version.</p>' + design.page_end())

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    content=render(root).encode()
    if args.check:
        if (root/'index.html').read_bytes()!=content or (root/'guide.html').read_bytes()!=render_guide().encode(): raise SystemExit('Frozen HTML differs from saved-data renderer')
    else:
        (root/'index.html').write_bytes(content)
        (root/'guide.html').write_bytes(render_guide().encode())
