"""Strict boundary for saved control-system figure documents."""
from __future__ import annotations

import hashlib
import csv
import json
import math
from pathlib import Path
import re
from fractions import Fraction

SCHEMA = "csl.plot-document/1"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"nonfinite JSON token: {value}")


def finite(value, name):
    if type(value) not in (float, int) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def load(path):
    raw = Path(path).read_bytes()
    document = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    validate(document)
    return document, hashlib.sha256(raw).hexdigest()


def add_obs05_tables(document, root):
    root=Path(root)
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"),object_pairs_hook=_pairs,parse_constant=_constant)
    if manifest.get("schema")!="csl.obs05-export/1":raise ValueError("expected csl.obs05-export/1 manifest")
    raw_path=root/manifest.get("raw_record_file","")
    if not raw_path.is_file() or hashlib.sha256(raw_path.read_bytes()).hexdigest()!=manifest.get("raw_record_sha256"):
        raise ValueError("OBS-05 raw comparison record hash mismatch")
    source={"kind":"comparison","id":manifest["comparison_run_id"],"method_id":manifest["comparison_spec_id"],"method_version":"saved-comparison-record"}
    timing=[]
    with (root/"phase-summary.csv").open(encoding="utf-8",newline="") as stream:
        for row in csv.DictReader(stream):
            metric=row["metric"]
            if not metric.endswith("_ns"):continue
            available=int(row["available_values"] or 0)>0 and row["median"]!=""
            metric_kind="cpu" if metric.endswith("_cpu_ns") else "work" if metric=="worker_work_ns" else "wall"
            timing.append({"kind":"timing","source":source,"operation":f"{row['strategy']} · {metric} median", "metric":metric_kind,
                "values":[float(Fraction(row["median"]))] if available else [],"availability":"available" if available else "unavailable",
                "span_semantics":"not_applicable","summary_statistic":"median","unavailable_reason":row.get("tail_statistic","") if not available else ""})
    with (root/"module-summary.csv").open(encoding="utf-8",newline="") as stream:
        for row in csv.DictReader(stream):
            available=int(row["available_durations"] or 0)>0 and row["median_ns"]!=""
            method=row.get("strategy") or "strategy unavailable"
            version=row.get("module_version") or "module version unavailable"
            binding={"kind":"comparison","id":manifest["comparison_run_id"],"method_id":method,"method_version":version}
            timing.append({"kind":"timing","source":binding,"operation":f"{row.get('task')} · {row.get('operation')} · {row.get('module')}",
                "metric":"wall","values":[float(Fraction(row["median_ns"]))] if available else [],
                "availability":"available" if available else "unavailable","span_semantics":"inclusive","summary_statistic":"median",
                "unavailable_reason":"no available span durations" if not available else ""})
    merged={**document,"series":document["series"]+timing}
    validate(merged)
    return merged


def validate(document):
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ValueError(f"expected {SCHEMA}")
    provenance = document.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("provenance object required")
    for key in ("record_schema", "record_id", "scenario_id", "method_id"):
        if not isinstance(provenance.get(key), str) or not provenance[key]:
            raise ValueError(f"provenance.{key} must be a nonempty string")
    if not isinstance(provenance.get("source_sha256"), str) or not SHA256.fullmatch(provenance["source_sha256"]):
        raise ValueError("provenance.source_sha256 must be lowercase SHA-256")
    coords = document.get("coordinates")
    if not isinstance(coords, dict) or not isinstance(coords.get("states"), list) or not isinstance(coords.get("controls"), list):
        raise ValueError("coordinates.states and coordinates.controls arrays required")
    for group in ("states", "controls"):
        ids = []
        for item in coords[group]:
            if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k] for k in ("id", "name")):
                raise ValueError(f"coordinates.{group} entries need id and name")
            ids.append(item["id"])
        if len(ids) != len(set(ids)):
            raise ValueError(f"coordinates.{group} IDs must be unique")
    axes = document.get("axes")
    if not isinstance(axes, dict):
        raise ValueError("axes object required")
    state_axis = axes.get("states")
    control_axis = axes.get("controls")
    if not isinstance(state_axis, dict) or not isinstance(control_axis, dict):
        raise ValueError("state and control axes required")
    for name, axis in (("states", state_axis), ("controls", control_axis)):
        if axis.get("kind") not in ("stage", "physical_time") or not isinstance(axis.get("points"), list):
            raise ValueError(f"axes.{name} needs a supported kind and points")
        for i, value in enumerate(axis["points"]):
            finite(value, f"axes.{name}.points[{i}]")
        ends = axis.get("interval_ends")
        if name == "controls":
            if not isinstance(ends, list) or len(ends) != len(axis["points"]):
                raise ValueError("axes.controls.interval_ends must have one end per control interval")
            for i, value in enumerate(ends):
                if finite(value, f"axes.controls.interval_ends[{i}]") <= axis["points"][i]:
                    raise ValueError("control interval ends must follow their starts")
    series = document.get("series")
    if not isinstance(series, list) or not series:
        raise ValueError("at least one figure series is required")
    state_ids = {c["id"] for c in coords["states"]}
    control_ids = {c["id"] for c in coords["controls"]}
    for i, item in enumerate(series):
        path = f"series[{i}]"
        if not isinstance(item, dict) or item.get("kind") not in ("trajectory", "projection", "support_samples", "timing"):
            raise ValueError(f"{path}.kind is unsupported")
        kind = item["kind"]
        source = item.get("source")
        if not isinstance(source, dict) or any(not isinstance(source.get(k), str) or not source[k]
                                                 for k in ("kind", "id", "method_id", "method_version")):
            raise ValueError(f"{path}.source must bind source kind/id and method identity")
        if kind == "trajectory":
            for field in ("witness_id", "evidence", "assurance", "approximation", "objective_evidence", "objective_label"):
                if not isinstance(item.get(field), str) or not item[field]:
                    raise ValueError(f"{path}.{field} must label the selected witness and its evidence")
            finite(item.get("objective"), f"{path}.objective")
            states, controls = item.get("states"), item.get("controls")
            if not isinstance(states, list) or not isinstance(controls, list) or len(states) != len(state_axis["points"]) or len(controls) != len(control_axis["points"]):
                raise ValueError(f"{path} must bind T+1 states and T controls to saved axes")
            for field, rows, expected in (("states", states, len(coords["states"])), ("controls", controls, len(coords["controls"]))):
                for t, row in enumerate(rows):
                    if not isinstance(row, list) or len(row) != expected:
                        raise ValueError(f"{path}.{field}[{t}] coordinate count mismatch")
                    for c, value in enumerate(row):
                        finite(value, f"{path}.{field}[{t}][{c}]")
            for field in ("state_coordinate_ids", "control_coordinate_ids"):
                allowed = state_ids if field.startswith("state") else control_ids
                if not isinstance(item.get(field), list) or any(x not in allowed for x in item[field]):
                    raise ValueError(f"{path}.{field} must reference declared coordinates")
            if len(item["state_coordinate_ids"]) != len(coords["states"]) or len(item["control_coordinate_ids"]) != len(coords["controls"]):
                raise ValueError(f"{path} coordinate IDs must match the corresponding history dimensions")
        elif kind in ("projection", "support_samples"):
            ids = item.get("coordinate_ids")
            if not isinstance(ids, list) or len(ids) != 2 or any(x not in state_ids for x in ids):
                raise ValueError(f"{path}.coordinate_ids must select two declared state coordinates")
            points = item.get("points")
            if not isinstance(points, list) or (kind == "projection" and not points):
                raise ValueError(f"{path}.points must be a list, and projections need persisted points")
            for n, point in enumerate(points):
                if not isinstance(point, list) or len(point) != 2:
                    raise ValueError(f"{path}.points[{n}] must be a 2D point")
                finite(point[0], f"{path}.points[{n}][0]")
                finite(point[1], f"{path}.points[{n}][1]")
            if not item.get("relation") or not item.get("evidence") or not item.get("limitation"):
                raise ValueError(f"{path} must label relation, evidence, and limitations")
            if kind == "projection":
                if "objective" in item:
                    for field in ("objective_evidence", "objective_label"):
                        if not isinstance(item.get(field), str) or not item[field]:
                            raise ValueError(f"{path}.{field} must label objective context")
                    finite(item["objective"],f"{path}.objective")
                elif not isinstance(item.get("objective_context"),str) or not item["objective_context"]:
                    raise ValueError(f"{path}.objective_context must state why objective data is absent")
            else:
                samples = item.get("samples")
                if not isinstance(samples,list) or not samples:
                    raise ValueError(f"{path}.samples must retain directional support outcomes")
                sample_points=[]
                for n,sample in enumerate(samples):
                    if not isinstance(sample,dict): raise ValueError(f"{path}.samples[{n}] must be an object")
                    direction=sample.get("direction")
                    value=sample.get("value")
                    if not isinstance(sample.get("evidence_support"),str) or not sample["evidence_support"] or not isinstance(sample.get("assumptions"),list):
                        raise ValueError(f"{path}.samples[{n}] must preserve evidence support and assumptions")
                    if not isinstance(direction,list) or len(direction)!=2:
                        raise ValueError(f"{path}.samples[{n}].direction must be 2D")
                    if finite(direction[0],f"{path}.samples[{n}].direction[0]")==0 and finite(direction[1],f"{path}.samples[{n}].direction[1]")==0:
                        raise ValueError(f"{path}.samples[{n}].direction must be nonzero")
                    if not isinstance(value,dict) or value.get("kind") not in ("finite","empty","unbounded"):
                        raise ValueError(f"{path}.samples[{n}].value needs a supported outcome kind")
                    if value["kind"]=="finite": finite(value.get("value"),f"{path}.samples[{n}].value.value")
                    point=sample.get("point")
                    if point is not None:
                        if not isinstance(point,list) or len(point)!=2:
                            raise ValueError(f"{path}.samples[{n}].point must be 2D")
                        finite(point[0],f"{path}.samples[{n}].point[0]");finite(point[1],f"{path}.samples[{n}].point[1]")
                        sample_points.append([float(point[0]),float(point[1])])
                if sample_points!=[[float(x),float(y)] for x,y in points]:
                    raise ValueError(f"{path}.points must match the finite maximizing points in samples")
        else:
            if not isinstance(item.get("values"), list):
                raise ValueError(f"{path}.values array required")
            if item.get("metric") not in ("wall", "work", "cpu"):
                raise ValueError(f"{path}.metric must be wall, work, or cpu")
            if item.get("availability") not in ("available", "unavailable") or item.get("span_semantics") not in ("inclusive", "exclusive", "not_applicable"):
                raise ValueError(f"{path} must preserve metric availability and span semantics")
            if item["availability"] == "available" and not item["values"]:
                raise ValueError(f"{path}.values cannot be empty for an available metric")
            if item["availability"] == "unavailable" and item["values"]:
                raise ValueError(f"{path}.values must be empty for an unavailable metric")
            for n, value in enumerate(item["values"]): finite(value, f"{path}.values[{n}]")
