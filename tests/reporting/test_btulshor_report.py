import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    driver = Path(sys.argv[1])
    source = Path(__file__).resolve().parents[2] / "scripts/reports/btulshor/render.py"
    spec = importlib.util.spec_from_file_location("btulshor_render", source)
    renderer = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(renderer)

    cases = [
        {"id": "render-p2", "operation": "modif", "rows": 3, "cols": 0,
         "a": [], "x": [1, 0, -1], "initial_status": 0, "epsilon": 1e-5},
        {"id": "render-kpabep", "operation": "kpabep",
         "points": [[0, 0], [2, 0], [2, 2], [0, 2], [1, 1]]},
        {"id": "render-reach", "operation": "reach", "a": [[1]], "b": [[1]],
         "initial_points": [[0], [1]], "control_points": [[0], [2]]},
    ]
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "case.json"
        for case in cases:
            path.write_text(json.dumps(case), encoding="utf-8")
            completed = subprocess.run([str(driver), "--case", str(path)],
                                       check=True, text=True, capture_output=True)
            result = json.loads(completed.stdout)
            assert result["schema"] == "csl.btulshor-raw-case/1"
            assert result["case_id"] == case["id"]
            assert result["operation"] == case["operation"]
            assert "status" in result
            if case["operation"] == "modif" and result["status"] == "completed":
                assert {"original_status", "x", "basis"} <= result.keys()
            if case["operation"] == "kpabep" and result["status"] == "completed":
                assert {"points", "retained_indices", "retained_count"} <= result.keys()
            if case["operation"] == "reach" and result["status"] == "completed":
                assert {"points", "source_vertices", "point_count"} <= result.keys()

    document = {"schema": "csl.btulshor-comparison/1", "fixture_id": "square-point-classes",
        "raw_file": "raw/square-point-classes.json",
        "dimension": 2, "input_count": 7,
        "input_points": [[0, 0], [2, 0], [2, 2], [0, 2], [1, 1], [1, 0], [0, 0]],
        "point_classes": ["vertex", "vertex", "vertex", "vertex", "interior", "edge", "duplicate"],
        "provenance": {"source_commit": "<revision&1>", "compiler_id": "GNU",
            "compiler_version": "16.2.1", "build_config": "Release", "driver_id": "driver-v1"},
        "providers": [
            {"method_id": "csl.legacy.btulshor.kpabep.source-v1", "status": "completed",
             "input_count": 7, "retained_count": 5, "retained_indices": [0, 1, 2, 3, 4],
             "elapsed_ns_samples": [500, 100, 400, 200, 300], "pivot_count": 12,
             "modif_calls": 5, "exact_check": {"status": "verified", "hull_equal": True,
                 "irredundancy": False, "extra_indices": [4], "reason": "redundant retained point"},
             "display_boundary_indices": [0, 1, 2, 3]},
            {"method_id": "<untrusted-provider>", "status": "incomplete", "elapsed_ns": 7,
             "retained_indices": [0, 1, 2, 3], "exact_check": {"status": "rejected",
                 "hull_equal": False, "irredundancy": None, "reason": "raw result omitted an extreme"}},
            {"method_id": "csl.hull.lp-membership", "status": "incomplete"},
            {"method_id": "csl.geometry.quickhull-2d", "status": "unsupported_dimension"},
        ]}
    with tempfile.TemporaryDirectory() as temporary:
        output_dir = Path(temporary)
        three_d_comparison = {"fixture_id": "simplex-3d", "dimension": 3, "input_count": 5,
            "input_points": [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [.1, .1, .1]],
            "raw_file": "raw/simplex-3d.json", "provenance": {"source_commit": "revision-1"},
            "providers": [{"method_id": "csl.legacy.btulshor.kpabep.source-v1", "status": "completed",
                "input_count": 5, "retained_count": 4, "retained_indices": [0, 1, 2, 3],
                "elapsed_ns_samples": [10, 20, 30, 40, 50], "pivot_count": 4,
                "exact_check": {"status": "verified", "hull_equal": True,
                    "irredundancy": True, "reason": "hulls equal"}}]}
        four_d_comparison = {"fixture_id": "simplex-4d<script>", "dimension": 4, "input_count": 6,
            "input_points": [[0, 0, 0, 0], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0],
                             [0, 0, 0, 1], [.1, .1, .1, .1]],
            "raw_file": "raw/simplex-4d.json", "providers": [
                {"method_id": "csl.geometry.quickhull-2d", "status": "unsupported_dimension",
                 "exact_check": {"status": "pending", "reason": "not applicable"}}]}
        page = renderer.render(document, output_dir,
                               [three_d_comparison, four_d_comparison], "btulshor-report&v1.zip")
        _, visual_metadata = renderer.make_projection(document)
        svg_path = output_dir / "point-projections.svg"
        svg = svg_path.read_text(encoding="utf-8")
        sys.path.insert(0, str(source.parents[1]))
        import report_data
        report_data.validate_svg(svg.encode("utf-8"))
        assert svg_path.is_file() and "Coordinate 1" in svg and "Coordinate 2" in svg
        assert "Input points; labels are original IDs" in svg
        assert "Extreme vertex" in svg and "Interior point" in svg
        assert "Edge point" in svg and "Duplicate point" in svg
        assert "Saved display-only boundary" in svg
        assert "BTULSHOR retained source IDs" in svg
        assert "independent display boundary" in svg
        assert "Median" in page or "median" in page
        assert "300 ns median (n=5, range 100–500 ns)" in page
        assert "single call: 7 ns" in page
        assert "pending / unavailable" in page
        assert "not applicable (unsupported dimension)" in page
        assert '&quot;irredundancy&quot;: false' in page
        assert '&quot;hull_equal&quot;: false' in page
        assert "pivot_count" in page and "modif_calls" in page
        assert "&lt;script&gt;" in page and "&lt;revision&amp;1&gt;" in page
        assert "&lt;untrusted-provider&gt;" in page
        assert "</head><body>" in page and page.endswith("</body></html>")
        assert "elapsed intervals are reported per method and are not used to rank" in page
        assert "No timing or performance ranking is reported" not in page
        assert "csl-report-quantitative-v1" in page
        assert visual_metadata["aspect"] == "equal"
        assert visual_metadata["point_classes_used"] is True
        assert visual_metadata["coincident_input_ids"] == [[0, 6]]
        assert "GNU" in page and "16.2.1" in page and "Release" in page
        assert "Primary figure for square-point-classes" in page
        assert "Fixture: simplex-3d" in page and "Dimension:</strong> 3" in page
        assert "Fixture: simplex-4d" in page and "Dimension:</strong> 4" in page
        assert "300 ns median (n=5, range 100–500 ns)" in page
        assert "30 ns median (n=5, range 10–50 ns)" in page
        assert 'href="raw/square-point-classes.json"' in page
        assert 'href="raw/simplex-3d.json"' in page
        assert 'href="raw/simplex-4d.json"' in page
        assert 'href="btulshor-report&amp;v1.zip"' in page and "download" in page
        assert list(output_dir.glob("point-projections.svg")) == [svg_path]

        snapshot = output_dir / "offline-bundle"
        snapshot.mkdir()
        shutil.copy2(source, snapshot / "renderer.py")
        shutil.copy2(Path(__file__).resolve().parents[2] / "scripts/reports/figure_style.py",
                     snapshot / "figure_style.py")
        (snapshot / "result.json").write_text(json.dumps(document), encoding="utf-8")
        offline_report = snapshot / "report" / "index.html"
        subprocess.run([sys.executable, str(snapshot / "renderer.py"), str(snapshot / "result.json"),
                        "--output", str(offline_report)], check=True, capture_output=True, text=True)
        assert offline_report.is_file()
        assert (offline_report.parent / "point-projections.svg").is_file()
        assert "&lt;revision&amp;1&gt;" in offline_report.read_text(encoding="utf-8")

    no_saved_boundary = {"fixture_id": "no-boundary", "dimension": 2,
        "input_points": [[0, 0], [1, 0], [0, 1]],
        "providers": [{"method_id": "csl.legacy.btulshor.kpabep.source-v1",
            "retained_indices": [0, 1, 2]}]}
    svg, manifest = renderer.make_projection(no_saved_boundary)
    assert manifest["display_boundary_ids"] is None
    assert "Saved display-only boundary" not in svg.decode("utf-8")
    page = renderer.render(no_saved_boundary)
    assert "No boundary is drawn because saved display-boundary IDs are unavailable" in page

    three_d = {"fixture_id": "simplex", "dimension": 3, "input_count": 2,
               "input_points": [[0, 0, 0], [1, 0, 0]], "providers": []}
    page = renderer.render(three_d)
    assert "No 2D plot is generated for this input dimension." in page
    assert "point-projections.svg" not in page


if __name__ == "__main__":
    main()
