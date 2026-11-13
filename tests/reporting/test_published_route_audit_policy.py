"""Tests for reviewed mutable and order-only publication audit changes."""

import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.reports import audit_published_route_preservation as baseline_audit
from scripts.reports import learning_book
from scripts.reports import preserve_published_routes as preservation


class PublishedRouteAuditPolicyTests(unittest.TestCase):
    def test_reviewed_chapter_insertion_preserves_body_and_other_links(self):
        previous = '<a rel="prev" href="controller-composition.html"><span>Previous</span><strong>Compose reachability, recovery, and MPC</strong></a>'
        following = '<a rel="next" href="set-operations.html"><span>Next</span><strong>Convert, map, sum, intersect, and project sets</strong></a>'
        added_previous = '<a rel="prev" href="native-quadcopter-mpc.html"><span>Previous</span><strong>From native model data to 15 observed-state MPC replans</strong></a>'
        added_following = '<a rel="next" href="native-quadcopter-mpc.html"><span>Next</span><strong>From native model data to 15 observed-state MPC replans</strong></a>'
        added_entry = '<li class="book-chapter"><span class="chapter-state">Ready · saved native functional evidence</span> <a href="native-quadcopter-mpc.html">From native model data to 15 observed-state MPC replans</a><p>Browse 35 native model records, then inspect all predictions, the executed 12-state path and four inputs for source21.</p></li>'
        previous_entry = '<li class="book-chapter"><span class="chapter-state">Ready · installed package example</span> <a href="controller-composition.html">Compose reachability, recovery, and MPC</a><p>The complete optimal joint family is (x0,x1,x2,u0,u1)=(0,s,1,s,1-s), 0&lt;=s&lt;=1. The exact-family verifier applies only to its registered profiles. Generic Strategy A/B paths are numerical candidates. Local NLP MPC makes no global optimum claim.</p></li>'
        prefix = '<html><main><p>Saved scientific cost = 1</p><a href="raw.zip">Evidence</a>'
        nav = '<nav class="lesson-neighbors" aria-label="Lesson navigation">'
        suffix = "</main></html>"
        payloads = {
            "learn/controller-composition.html": (
                prefix + nav + previous + following + "</nav>" + suffix
            ).encode(),
            "learn/set-operations.html": (
                prefix + nav + previous + following + "</nav>" + suffix
            ).encode(),
            "learn/index.html": (prefix + "<ol>" + previous_entry + "</ol>" + suffix).encode(),
        }
        updated = {
            "learn/controller-composition.html": payloads[
                "learn/controller-composition.html"
            ].replace(following.encode(), added_following.encode()),
            "learn/set-operations.html": payloads["learn/set-operations.html"].replace(
                previous.encode(), added_previous.encode()
            ),
            "learn/index.html": payloads["learn/index.html"].replace(
                b"</ol>", added_entry.encode() + b"</ol>"
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, site = root / "source", root / "site"
            source.mkdir()
            site.mkdir()
            baseline = root / "baseline.tar"
            with tarfile.open(baseline, "w") as bundle:
                for route, data in payloads.items():
                    member = tarfile.TarInfo(route)
                    member.size = len(data)
                    bundle.addfile(member, io.BytesIO(data))
                    target = site / route
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(updated[route])
            manifest = json.loads((preservation.SOURCE / "manifest.json").read_text())
            manifest["learning_navigation_insertions_reviewed_separately"] = [
                insertion
                for insertion in manifest["learning_navigation_insertions_reviewed_separately"]
                if insertion["chapter_id"] == "native-quadcopter-mpc"
            ]
            manifest["baseline"]["artifact_tar_sha256"] = preservation.digest(baseline.read_bytes())
            (source / "manifest.json").write_text(json.dumps(manifest))
            with patch.object(baseline_audit, "SOURCE", source):
                result = baseline_audit.audit(baseline, site)
                self.assertTrue(result["passed"], result)
                self.assertEqual(set(result["reviewed_learning_navigation_changes"]), set(payloads))
                for route, data in updated.items():
                    for label, bad in {
                        "scientific body": data.replace(b"cost = 1", b"cost = 2"),
                        "unrelated link": data.replace(b"raw.zip", b"other.zip"),
                        "wrong navigation target": data.replace(
                            b"native-quadcopter-mpc.html", b"other-lesson.html"
                        ),
                        "wrong lesson title": data.replace(
                            b"15 observed-state", b"99 observed-state"
                        ),
                    }.items():
                        with self.subTest(route=route, mutation=label):
                            (site / route).write_bytes(bad)
                            result = baseline_audit.audit(baseline, site)
                            self.assertFalse(result["passed"])
                            self.assertIn(route, result["unexpected_changed"])
                            (site / route).write_bytes(data)
                for field in ("chapter_sha256", "previous_chapter_id", "next_chapter_id"):
                    with self.subTest(reviewed_identity=field):
                        changed_manifest = json.loads(json.dumps(manifest))
                        changed_manifest["learning_navigation_insertions_reviewed_separately"][0][
                            field
                        ] = "wrong"
                        (source / "manifest.json").write_text(json.dumps(changed_manifest))
                        result = baseline_audit.audit(baseline, site)
                        self.assertFalse(result["passed"])
                        self.assertEqual(set(result["unexpected_changed"]), set(payloads))
                (source / "manifest.json").write_text(json.dumps(manifest))
                misplaced = payloads["learn/index.html"].replace(
                    b"<ol>", b"<ol>" + added_entry.encode()
                )
                (site / "learn/index.html").write_bytes(misplaced)
                result = baseline_audit.audit(baseline, site)
                self.assertFalse(result["passed"])
                self.assertIn("learn/index.html", result["unexpected_changed"])

    def test_two_independent_chapter_insertions_preserve_actual_book_pages(self):
        root = Path(__file__).resolve().parents[2]
        fixture = Path(__file__).resolve().parents[1] / "fixtures/published-route-baseline"
        routes = (
            "learn/index.html",
            "learn/representation-consumers.html",
            "learn/closed-loop-semantics.html",
            "learn/controller-composition.html",
            "learn/set-operations.html",
        )
        manifest = json.loads((preservation.SOURCE / "manifest.json").read_text())
        provenance = json.loads((fixture / "source.json").read_text())
        self.assertEqual(provenance["schema"], "csl.published-route-baseline-fixture/1")
        self.assertEqual(provenance["baseline"], manifest["baseline"])
        self.assertEqual(set(provenance["routes_sha256"]), set(routes))
        for route in routes:
            self.assertEqual(
                preservation.digest((fixture / route).read_bytes()),
                provenance["routes_sha256"][route],
                route,
            )
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            site = temporary / "site"
            site.mkdir()
            baseline = temporary / "baseline.tar"
            source = temporary / "source"
            source.mkdir()
            with tarfile.open(baseline, "w") as bundle:
                for route in routes:
                    payload = (fixture / route).read_bytes()
                    member = tarfile.TarInfo("./" + route)
                    member.size = len(payload)
                    bundle.addfile(member, io.BytesIO(payload))

            learning_book.build(
                site,
                figure_index_path=root / "docs/examples/closed-loop/figure-index.json",
            )
            manifest["baseline"]["artifact_tar_sha256"] = preservation.digest(baseline.read_bytes())
            self.assertEqual(
                {
                    entry["chapter_id"]
                    for entry in manifest["learning_navigation_insertions_reviewed_separately"]
                },
                {"native-forward-models", "native-quadcopter-mpc"},
            )
            (source / "manifest.json").write_text(json.dumps(manifest))

            with patch.object(baseline_audit, "SOURCE", source):
                result = baseline_audit.audit(baseline, site)
                self.assertTrue(result["passed"], result)
                math_route = "learn/representation-consumers.html"
                self.assertEqual(set(result["reviewed_learning_navigation_changes"]),
                                 set(routes) - {math_route})
                self.assertIn(math_route, result["reviewed_mutable_changes"])
                self.assertEqual(preservation.digest((site / math_route).read_bytes()),
                                 manifest["mutable_copy_reviewed_sha256"][math_route])

                mutated_routes = {
                    "body mutation": (
                        "learn/representation-consumers.html",
                        lambda data: data.replace(b"</main>", b"<p>changed body</p></main>", 1),
                    ),
                    "wrong insertion target": (
                        "learn/index.html",
                        lambda data: data.replace(
                            b'href="native-forward-models.html"',
                            b'href="unreviewed-lesson.html"',
                            1,
                        ),
                    ),
                    "misplaced chapter entry": (
                        "learn/index.html",
                        lambda data: self._move_native_forward_entry_after_closed_loop(data),
                    ),
                }
                for label, (route, mutate) in mutated_routes.items():
                    with self.subTest(mutation=label):
                        path = site / route
                        original = path.read_bytes()
                        path.write_bytes(mutate(original))
                        result = baseline_audit.audit(baseline, site)
                        self.assertFalse(result["passed"])
                        self.assertIn(route, result["unexpected_changed"])
                        path.write_bytes(original)

                wrong_identity = json.loads(json.dumps(manifest))
                wrong_identity["learning_navigation_insertions_reviewed_separately"][-1][
                    "chapter_sha256"
                ] = "0" * 64
                (source / "manifest.json").write_text(json.dumps(wrong_identity))
                result = baseline_audit.audit(baseline, site)
                self.assertFalse(result["passed"])
                self.assertEqual(
                    set(result["unexpected_changed"]),
                    {
                        "learn/index.html",
                        "learn/closed-loop-semantics.html",
                    },
                )
                self.assertNotIn(math_route, result["unexpected_changed"])

    @staticmethod
    def _move_native_forward_entry_after_closed_loop(data):
        import re

        entries = list(re.finditer(rb'<li class="book-chapter">.*?</li>', data, re.DOTALL))
        added = next(
            match for match in entries if b'href="native-forward-models.html"' in match.group()
        )
        destination = next(
            match for match in entries if b'href="closed-loop-semantics.html"' in match.group()
        )
        without_added = data[: added.start()] + data[added.end() :]
        shift = len(added.group()) if added.end() < destination.end() else 0
        destination_end = destination.end() - shift
        return without_added[:destination_end] + added.group() + without_added[destination_end:]

    def test_adjacent_or_repeated_chapter_insertions_fail_closed(self):
        manifest = json.loads((preservation.SOURCE / "manifest.json").read_text())
        forward = {
            "chapter_id": "native-forward-models",
            "chapter_sha256": "b7236c15858c7cd7d0b6fd7cfe4b3122be7f5d034f397e5a4b5b344bae599358",
            "previous_chapter_id": "representation-consumers",
            "next_chapter_id": "closed-loop-semantics",
            "qualification": "Reviewed native forward-models lesson insertion.",
        }
        manifest["learning_navigation_insertions_reviewed_separately"] = [
            forward,
            {
                "chapter_id": "closed-loop-semantics",
                "chapter_sha256": "fb951101429be7caf73b13b72a21ccebe84ee44a03718db45abd7927b88bde8d",
                "previous_chapter_id": "native-forward-models",
                "next_chapter_id": "finite-controller-consumers",
                "qualification": "ambiguous adjacent insertion",
            },
        ]
        with self.assertRaisesRegex(ValueError, "adjacent or overlapping"):
            baseline_audit._learning_navigation_replacements(manifest)

        manifest["learning_navigation_insertions_reviewed_separately"] = [forward, forward]
        with self.assertRaisesRegex(ValueError, "duplicate chapter insertion"):
            baseline_audit._learning_navigation_replacements(manifest)

    def test_only_reviewed_learning_links_and_installed_list_order_are_mutable(self):
        learning_routes = ("learn/install-consumer.html", "learn/chapter-manifest.json")
        receipt = baseline_audit.ORDER_INSENSITIVE_RECEIPT_ROUTE
        package_a = {"metadata": {"name": "alpha", "version": "1.0"}, "requested": True}
        package_b = {"metadata": {"name": "beta", "version": "2.0"}, "requested": False}
        receipt_value = {
            "version": 1,
            "pip_version": "24.0",
            "environment": {"python_full_version": "3.11.14", "platform_system": "Linux"},
            "installed": [package_a, package_a, package_b],
        }
        payloads = {
            learning_routes[0]: b'<a href="source-at-6603">installed consumer</a>',
            learning_routes[1]: b'{"chapters":[{"href":"source-at-6603"}]}',
            receipt: json.dumps(receipt_value, sort_keys=True).encode(),
            "report/raw.json": b'{"cost": 1}',
            "report/raw.zip": b"saved archive",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site, source = root / "site", root / "source"
            site.mkdir()
            source.mkdir()
            baseline = root / "baseline.tar"
            with tarfile.open(baseline, "w") as bundle:
                for name, data in payloads.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    bundle.addfile(member, io.BytesIO(data))
                    target = site / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
            manifest = json.loads((preservation.SOURCE / "manifest.json").read_text())
            manifest["baseline"]["artifact_tar_sha256"] = preservation.digest(baseline.read_bytes())
            (source / "manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(
                set(manifest["order_insensitive_receipts_reviewed_separately"]), {receipt}
            )
            self.assertTrue(
                set(learning_routes) <= set(manifest["mutable_routes_reviewed_separately"])
            )

            (site / learning_routes[0]).write_bytes(
                b'<a href="source-at-main">installed consumer</a>'
            )
            (site / learning_routes[1]).write_bytes(b'{"chapters":[{"href":"source-at-main"}]}')
            reordered = json.loads(json.dumps(receipt_value))
            reordered["installed"] = [package_b, package_a, package_a]
            (site / receipt).write_text(json.dumps(reordered, sort_keys=True))

            with patch.object(baseline_audit, "SOURCE", source):
                result = baseline_audit.audit(baseline, site)
                self.assertTrue(result["passed"], result)
                self.assertEqual(set(result["reviewed_mutable_changes"]), set(learning_routes))
                self.assertIn(receipt, result["reviewed_receipt_order_changes"])

                rejecting_receipts = {
                    "package version": lambda value: value["installed"][0]["metadata"].__setitem__(
                        "version", "changed"
                    ),
                    "package metadata": lambda value: value["installed"][0]["metadata"].__setitem__(
                        "summary", "changed"
                    ),
                    "environment": lambda value: value["environment"].__setitem__(
                        "python_full_version", "3.12.0"
                    ),
                    "missing field": lambda value: value["installed"][0]["metadata"].pop("name"),
                    "missing installed inventory": lambda value: value.pop("installed"),
                    "added duplicate": lambda value: value["installed"].append(package_a),
                    "removed duplicate": lambda value: value["installed"].pop(),
                }
                for label, mutate in rejecting_receipts.items():
                    with self.subTest(receipt_change=label):
                        changed = json.loads(json.dumps(reordered))
                        mutate(changed)
                        (site / receipt).write_text(json.dumps(changed, sort_keys=True))
                        result = baseline_audit.audit(baseline, site)
                        self.assertFalse(result["passed"])
                        self.assertIn(receipt, result["unexpected_changed"])

                (site / receipt).write_text(json.dumps(reordered, sort_keys=True))
                (site / "report/raw.json").write_bytes(b'{"cost": 2}')
                result = baseline_audit.audit(baseline, site)
                self.assertFalse(result["passed"])
                self.assertIn("report/raw.json", result["unexpected_changed"])

                (site / "report/raw.json").write_bytes(payloads["report/raw.json"])
                (site / "report/raw.zip").write_bytes(b"changed saved archive")
                result = baseline_audit.audit(baseline, site)
                self.assertFalse(result["passed"])
                self.assertIn("report/raw.zip", result["changed_or_missing_zips"])

                (site / "report/raw.zip").unlink()
                result = baseline_audit.audit(baseline, site)
                self.assertFalse(result["passed"])
                self.assertIn("report/raw.zip", result["missing"])
                self.assertIn("report/raw.zip", result["changed_or_missing_zips"])

                (site / receipt).unlink()
                result = baseline_audit.audit(baseline, site)
                self.assertFalse(result["passed"])
                self.assertIn(receipt, result["missing"])


if __name__ == "__main__":
    unittest.main()
