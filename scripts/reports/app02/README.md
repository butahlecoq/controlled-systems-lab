# APP-02 saved approximation report

The frozen numerical source is commit `8fecba49e34c37e5e01c40218a8f014a179818fd`
with tree `7754b4c088566225b007c58531a74aae0024d5a1`. Its driver uses the
registered public approximation path for five literal interval or 2D fixtures.
Each call checks the complete H rows and bounds or V corners after timing, plus
the enclosure basis and explicit absence of an error bound.

To make a fresh capture from a separate clean checkout at that commit:

```sh
python scripts/reports/app02/capture.py --source <clean-frozen-checkout> --capture <fresh-capture-directory>
python scripts/reports/app02/collect.py --capture <capture-directory> --source <clean-frozen-checkout> --out reports/algorithm-results
python scripts/reports/app02/render_saved.py --bundle reports/algorithm-results/app02-box-8ff979de60ea9d22 --check
python scripts/reports/stage_app02.py --source reports/algorithm-results/app02-box-8ff979de60ea9d22
```

The committed capture is `app02-box-8ff979de60ea9d22`. The collector checks
clean prebuild and postrun receipts, source commit/tree, executable hash, Release
configuration, literal raw driver rows and exact source bytes. The saved renderer
reconstructs HTML, SVG, summary, manifest and offline ZIP without rerunning the
adapter. The extension catalogue binds renderer and stager bytes. The main-only
site workflow stages the immutable bundle and a separate `app02-example` page.

One excluded 100-call warmup per case precedes seven rotated five-case rounds
of 100 calls each. The 3,500 measured calls had zero recorded failures. Each
timed interval covers one `run_registered` call, including registry selection,
provider execution and independent native containment verification. The
post-call literal oracle, fixture setup and rendering are outside the interval.
These are descriptive single-adapter observations. No comparator, speedup,
source-mapped limiter, finite approximation error bound, or broad performance
claim is supported.
