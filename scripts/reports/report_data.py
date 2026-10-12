"""Versioned saved-data boundary. No execution, plotting or native imports."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics as _statistics
import xml.etree.ElementTree as ET

SCHEMA = "csl.algorithm-report-view/1"
EVENT_SCHEMA = "csl.lp-report-events/1"
PHASES = ("input_publication", "registration_preparation", "workspace_creation",
          "public_run", "independent_verification", "end_to_end")
PURPOSES = {"test", "measurement", "profile", "calibration", "warmup"}
OUTCOMES = {"optimal", "infeasible", "unbounded", "infimum_not_attained", "undetermined"}
TERMINATIONS = {"completed", "cancelled", "resource_limit", "numerical_failure"}
HEX = re.compile(r"[0-9a-f]{64}\Z")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(text):
    def invalid(value):
        raise ValueError(f"nonfinite JSON token: {value}")
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=invalid)


def finite(value):
    require(type(value) in (int, float), "finite scalar required")
    try:
        value = float(value)
    except OverflowError as error:
        raise ValueError("binary64 overflow") from error
    require(math.isfinite(value), "nonfinite scalar")
    return value


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, "nonnegative integer required")
    return value


def canonical_bytes(value):
    def transform(item):
        if isinstance(item, float):
            return {"$binary64": finite(item).hex()}
        if isinstance(item, dict):
            require(all(isinstance(k, str) for k in item), "string object keys required")
            return {k: transform(v) for k, v in item.items()}
        if isinstance(item, list):
            return [transform(v) for v in item]
        require(item is None or type(item) in (str, int, bool), "unsupported JSON type")
        return item
    return json.dumps(transform(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize_input(value):
    value = copy.deepcopy(value)
    value["linear"] = [finite(x) for x in value["linear"]]
    value["offset"] = finite(value["offset"])
    value["constraints"]["values"] = [finite(x) for x in value["constraints"]["values"]]
    for name in ("variables", "rows"):
        value[name] = [[None if x is None else finite(x) for x in pair] for pair in value[name]]
    return value


def input_digest(value):
    return digest(normalize_input(value))


def scenario_digest(value):
    value = copy.deepcopy(value)
    value.pop("input_sha256", None)
    value.pop("scenario_sha256", None)
    value["input"] = normalize_input(value["input"])
    ref = value["reference"]
    if ref["point"] is not None:
        ref["point"] = [finite(x) for x in ref["point"]]
    if ref["objective"] is not None:
        ref["objective"] = finite(ref["objective"])
    return digest(value)


def seal(payload):
    payload = copy.deepcopy(payload)
    for scenario in payload["scenarios"]:
        scenario["input"] = normalize_input(scenario["input"])
        ref = scenario["reference"]
        if ref["point"] is not None:
            ref["point"] = [finite(x) for x in ref["point"]]
        if ref["objective"] is not None:
            ref["objective"] = finite(ref["objective"])
    for trial in payload["trials"]:
        result=trial.get("result")
        if result is None: continue
        if result.get("primal") is not None:
            result["primal"]=[finite(x) for x in result["primal"]]
        if result.get("original_objective") is not None:
            result["original_objective"]=finite(result["original_objective"])
        for name,fields in (("primal_residuals",("rows","variables")),("dual_residuals",("stationarity","signs","complementarity"))):
            block=result.get(name)
            if block is None: continue
            for tolerance in ("absolute_tolerance","relative_tolerance"):
                if tolerance in block.get("context",{}): block["context"][tolerance]=finite(block["context"][tolerance])
            for field in fields:
                measure=block.get(field)
                if measure is not None:
                    for key in ("violation","scale"):
                        if key in measure: measure[key]=finite(measure[key])
    for tolerance in ("absolute_tolerance","relative_tolerance"):
        if tolerance in payload.get("environment",{}): payload["environment"][tolerance]=finite(payload["environment"][tolerance])
    sha = digest(payload)
    stamp = payload["created_utc"].replace("-", "").replace(":", "")
    return {"schema": SCHEMA, "report_id": f"lp-{stamp}-{sha[:12]}",
            "payload_sha256": sha, "payload": payload}


def identity(value):
    require(isinstance(value, dict) and set(value) == {"problem", "program"}, "program identity required")
    require(all(isinstance(x, str) and x for x in value.values()), "nonempty identity required")


def validate_input(data):
    data = normalize_input(data)
    n = len(data["linear"])
    matrix = data["constraints"]
    m = integer(matrix["rows"])
    require(integer(matrix["cols"]) == n, "constraint column mismatch")
    require(len(data["variables"]) == n and len(data["rows"]) == m, "bound shape mismatch")
    starts, indices, values = matrix["starts"], matrix["indices"], matrix["values"]
    require(len(starts) == m + 1 and starts[0] == 0 and starts[-1] == len(values) == len(indices), "CSR size mismatch")
    require(all(type(x) is int for x in starts + indices), "CSR integer indices required")
    require(all(a <= b for a, b in zip(starts, starts[1:])), "CSR order")
    for row in range(m):
        cols = indices[starts[row]:starts[row + 1]]
        require(all(0 <= j < n for j in cols) and cols == sorted(set(cols)), "CSR columns")
    for pair in data["variables"] + data["rows"]:
        require(len(pair) == 2, "interval shape")
        require(pair[0] is None or pair[1] is None or pair[0] <= pair[1], "interval order")


def _residual(block, subject, fields):
    if block is None:
        return
    context = block["context"]
    require(context["subject"] == subject, "residual subject mismatch")
    require(bool(context["verifier"]["id"]) and bool(context["verifier"]["version"]), "verifier required")
    for tolerance in ("absolute_tolerance", "relative_tolerance"):
        require(finite(context[tolerance]) >= 0, "negative tolerance")
    for field in fields:
        measure = block[field]
        if measure is not None:
            require(finite(measure["violation"]) >= 0 and finite(measure["scale"]) >= 0, "negative residual")


def residual_passes(block, fields):
    if block is None:
        return False
    c = block["context"]
    return all(block[x] is not None and block[x]["violation"] <=
               c["absolute_tolerance"] + c["relative_tolerance"] * block[x]["scale"] for x in fields)


def reference_matches(trial, scenario):
    result = trial["result"]
    ref = scenario["reference"]
    if result is None or result["termination"] != "completed" or result["outcome"] != ref["outcome"]:
        return False
    if result["support"] != {"kind": "unestablished"} or result["bounds"] != {"lower": None, "upper": None}:
        return False
    if ref["outcome"] != "optimal":
        return True
    point, cost = result["primal"], result["original_objective"]
    if point is None or cost is None or len(point) != len(ref["point"]):
        return False
    close = lambda a, b: abs(a-b) <= 1e-8 + 1e-8 * max(abs(a), abs(b))
    if not all(close(a,b) for a,b in zip(point,ref["point"])) or not close(cost,ref["objective"]):
        return False
    data = scenario["input"]
    if not close(sum(a*b for a,b in zip(data["linear"],point))+data["offset"],cost):
        return False
    matrix = data["constraints"]
    activities = [sum(matrix["values"][j]*point[matrix["indices"][j]]
                      for j in range(matrix["starts"][i],matrix["starts"][i+1])) for i in range(matrix["rows"])]
    for x, (lo, hi) in zip(point+activities, data["variables"]+data["rows"]):
        if (lo is not None and x < lo and not close(x,lo)) or (hi is not None and x > hi and not close(x,hi)):
            return False
    return residual_passes(result["primal_residuals"], ("rows", "variables")) and residual_passes(result["dual_residuals"], ("stationarity", "signs"))


def native_iterations(raw):
    prefix = raw.split("\nnative.log:", 1)[0]
    fields = {}
    for line in prefix.splitlines():
        require("=" in line, "malformed native diagnostic prefix")
        key, value = line.split("=", 1)
        require(key not in fields, "duplicate native diagnostic key")
        fields[key] = value
    require(fields.get("adapter.version") == "1.0.0+highs.1.11.0" and fields.get("native.version") == "1.11.0", "unsupported diagnostic version")
    if fields.get("native.info") != "available":
        return {"available": False, "reason": "native info unavailable"}
    text = fields.get("native.simplex_iterations", "")
    require(re.fullmatch(r"[0-9]+", text) is not None, "native iteration count required")
    return {"available": True, "value": int(text), "unit": "iterations", "scope": "public_run"}


def _validate_view(view):
    require(view["schema"] == SCHEMA, "unknown view schema")
    payload = view["payload"]
    require(payload["purpose"] in {"test","measurement"}, "saved views require test or measurement purpose")
    require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", payload["created_utc"]) is not None, "UTC timestamp required")
    require(view == seal(payload), "payload identity/hash mismatch")
    for name in ("provenance", "environment", "process", "profile"):
        require(isinstance(payload[name], dict), f"{name} required")
    require(payload["historical"] == [], "historical track is separate and empty in v1")
    provenance = payload["provenance"]
    require(re.fullmatch(r"[0-9a-f]{40}", provenance["source_commit"]) is not None, "source SHA required")
    require(type(provenance["tracked_clean"]) is bool and HEX.fullmatch(provenance["executable_sha256"]) is not None, "executable provenance")
    require(provenance["backend"] == {"id": "csl.lp.highs", "version": "1.0.0+highs.1.11.0"}, "backend identity")
    configurations=("Release","Debug","RelWithDebInfo","MinSizeRel","TEST") if payload["purpose"]=="test" else ("Release",)
    require(provenance["build"]["configuration"] in configurations, "configured provenance required")
    if provenance["build"]["configuration"]!="TEST":
        require(provenance["build"]["source_commit"]==provenance["source_commit"],"configured source identity differs")
    environment = payload["environment"]
    require(environment["scalar"] == "binary64" and environment["workspace_reuse"] is False, "unsupported measurement policy")
    require(environment["resources"] == {"total_threads":1,"outer_workers":1,"threads_per_worker":1,"memory_bytes":None}, "resource policy")
    require(finite(environment["absolute_tolerance"])==1e-8 and finite(environment["relative_tolerance"])==1e-8 and environment["seed"]==0, "declared numerical profile required")
    clock = environment["clock"]
    require(clock["is_steady"] is True and integer(clock["period_num"],1) and integer(clock["period_den"],1), "steady clock required")
    scenarios = {}
    require(1<=len(payload["scenarios"])<=100,"bounded scenario catalogue required")
    for scenario in payload["scenarios"]:
        key = scenario["case_id"]
        require(re.fullmatch(r"[a-z0-9-]+", key) is not None and key not in scenarios, "duplicate/unsafe case ID")
        identity(scenario["identity"])
        validate_input(scenario["input"])
        require(scenario["input_sha256"] == input_digest(scenario["input"]), "input hash mismatch")
        require(scenario["scenario_sha256"] == scenario_digest(scenario), "scenario hash mismatch")
        ref = scenario["reference"]
        require(ref["outcome"] in OUTCOMES and bool(ref["derivation"]) and bool(scenario["assumptions"]), "reference required")
        require((ref["point"] is not None and ref["objective"] is not None) == (ref["outcome"] == "optimal"), "reference witness mismatch")
        scenarios[key] = scenario
    require(bool(scenarios), "empty scenario catalogue")
    seen, sequences = set(), set()
    repetitions=integer(payload["process"]["repetitions"],1)
    require(repetitions<=1000,"bounded repetition count required")
    order=[(key,round_) for round_ in range(1,repetitions+1) for key in scenarios]
    for trial_index,trial in enumerate(payload["trials"]):
        key = trial["case_id"]
        require(key in scenarios and trial["purpose"] == payload["purpose"], "trial scenario/purpose mismatch")
        pair = (key, integer(trial["round"],1))
        require(trial_index<len(order) and pair==order[trial_index], "trial round/order differs from declared round robin")
        require(pair not in seen, "duplicate trial")
        seen.add(pair)
        sequence = integer(trial["sequence"],1)
        require(sequence not in sequences, "duplicate sequence")
        sequences.add(sequence)
        require(trial["identity"] == scenarios[key]["identity"], "trial identity mismatch")
        require(trial["registry"]["requested"] == "csl.lp.highs", "requested method mismatch")
        require(trial["registry"]["actual"] in (None,provenance["backend"]), "actual method mismatch")
        require(trial["harness"]["status"] in {"returned","unsupported","exception","aborted"}, "harness status")
        require(isinstance(trial["validation"]["errors"],list) and type(trial["validation"]["passed"]) is bool, "validation required")
        require(trial["validation"]["passed"] == (len(trial["validation"]["errors"]) == 0), "validation errors inconsistent")
        for phase in PHASES:
            interval = trial["timings"][phase]
            require(type(interval["available"]) is bool,"timing availability must be boolean")
            if not interval["available"]:
                require(bool(interval["reason"]), "unavailable timing reason")
                continue
            scopes={phase}
            if phase=="end_to_end" and not trial["validation"]["passed"]: scopes.add("end_to_end_including_unwind")
            require(interval["unit"] == "ns" and interval["scope"] in scopes, "timing unit/scope mismatch")
            require(re.fullmatch(r"[0-9]+",interval["start_tick"]) is not None and re.fullmatch(r"[0-9]+",interval["end_tick"]) is not None, "clock tick integer string")
            start, end = int(interval["start_tick"]), int(interval["end_tick"])
            require(end >= start and integer(interval["duration_ns"]) == (end-start)*clock["period_num"]*1_000_000_000//clock["period_den"], "duration/tick mismatch")
        total = trial["timings"]["end_to_end"]
        if total["available"]:
            for phase in PHASES[:-1]:
                span = trial["timings"][phase]
                if span["available"]:
                    require(int(total["start_tick"]) <= int(span["start_tick"]) <= int(span["end_tick"]) <= int(total["end_tick"]), "phase outside end-to-end")
        reached=[trial["timings"][phase] for phase in PHASES[:-1] if trial["timings"][phase]["available"]]
        require(all(int(a["end_tick"])<=int(b["start_tick"]) for a,b in zip(reached,reached[1:])), "sequential phases overlap or reverse")
        result = trial["result"]
        if result is not None:
            require(result["termination"] in TERMINATIONS and result["outcome"] in OUTCOMES, "unknown result status")
            require(result["support"] == {"kind":"unestablished"}, "unsupported evidence projection")
            require(result["bounds"] == {"lower":None,"upper":None} and result["family"]["available"] is False, "unsupported bounds/family claim")
            if result["primal"] is not None:
                require(len(result["primal"]) == len(scenarios[key]["input"]["linear"]), "candidate dimension")
                for value in result["primal"]: finite(value)
            if result["original_objective"] is not None: finite(result["original_objective"])
            _residual(result["primal_residuals"],trial["identity"],("rows","variables"))
            _residual(result["dual_residuals"],trial["identity"],("stationarity","signs","complementarity"))
            require(isinstance(result["raw_diagnostics"],str), "raw diagnostics required")
        metric=trial["native_iterations"]
        require(type(metric["available"]) is bool,"iteration availability must be boolean")
        if metric["available"]: integer(metric["value"])
        expected_metric=native_iterations(result["raw_diagnostics"]) if result else {"available":False,"reason":"no returned native diagnostic"}
        require(metric==expected_metric,"iteration metric differs from retained native diagnostics")
        if trial["validation"]["passed"]:
            require(all(trial["timings"][p]["available"] for p in PHASES),"successful trial requires all measured phase spans")
            require(trial["registry"]["actual"]==provenance["backend"],"successful trial requires actual method provenance")
            require(trial["harness"]["status"] == "returned" and reference_matches(trial,scenarios[key]), "inconsistent successful validation")
            require(trial["attempt"] == {"number":1,"state":"returned_result","workspace_reuse":False}, "current attempt mismatch")
            require(re.fullmatch(r"[0-9]+",trial["observation_token"]) is not None, "observation token required")
            require("\nnative_run=true" in result["raw_diagnostics"].split("\nnative.log:",1)[0] or payload["purpose"] == "test", "native run not observed")
    process = payload["process"]
    require(integer(process["emitted_trials"]) == len(payload["trials"]), "emitted count mismatch")
    require(integer(process["expected_trials"]) == integer(process["repetitions"],1)*len(scenarios), "expected count mismatch")
    require(type(process["complete"]) is bool and type(process["aborted"]) is bool, "process completion required")
    require(len(payload["trials"]) <= process["expected_trials"], "excess trial count")
    if process["complete"]:
        require(not process["aborted"] and len(payload["trials"]) == process["expected_trials"], "false complete marker")
    canonical_bytes(payload)  # Reject hidden nonfinite/unsupported values, including diagnostics metadata.
    return view


def validate_view(view):
    try:
        return _validate_view(view)
    except (KeyError, TypeError, IndexError, OverflowError) as error:
        raise ValueError(f"malformed report view: {error}") from error


def load_view(path):
    return validate_view(parse_json(Path(path).read_text(encoding="utf-8")))


def statistics(values):
    require(bool(values) and all(type(x) in (int,float) and math.isfinite(x) and x>=0 for x in values), "finite nonempty durations required")
    return {"median":_statistics.median(values),"min":min(values),"max":max(values),"count":len(values)}


def aggregate(view):
    validate_view(view)
    payload = view["payload"]
    groups = []
    for scenario in payload["scenarios"]:
        trials = [t for t in payload["trials"] if t["case_id"] == scenario["case_id"]]
        expected = payload["process"]["repetitions"]
        passed = sum(t["validation"]["passed"] for t in trials)
        valid = passed == expected == len(trials) and payload["process"]["complete"] and payload["process"]["return_code"] == 0
        groups.append({"case_id":scenario["case_id"],"expected":expected,"attempts":len(trials),"matched":passed,
                       "failed":len(trials)-passed,"missing":max(0,expected-len(trials)),
                       "unsupported":sum(t["harness"]["status"]=="unsupported" for t in trials),
                       "cancelled":sum(t["result"] is not None and t["result"]["termination"]=="cancelled" for t in trials),
                       "valid":valid,"phases":{p:statistics([t["timings"][p]["duration_ns"] for t in trials])
                            if valid and len(trials)>=5 and all(t["timings"][p]["available"] for t in trials) else None for p in PHASES}})
    return groups


def figure_series(view):
    groups=aggregate(view)
    return {phase:[{"case_id":g["case_id"],"values":[t["timings"][phase]["duration_ns"] for t in view["payload"]["trials"] if t["case_id"]==g["case_id"] and t["timings"][phase]["available"]],"summary":g["phases"][phase]} for g in groups]
            for phase in ("public_run","end_to_end")}


def validate_figure_metadata(view,metadata):
    require(metadata["schema"]=="csl.report-figure/1" and metadata["payload_sha256"]==view["payload_sha256"],"figure metadata subject/version differs")
    require(metadata["unit"]=="ns" and metadata["series"]==figure_series(view),"figure series or units differ from saved records")
    require(metadata["matplotlib"]=="3.11.2" and metadata["svg_policy"]=="csl.report.svg.mpl-3.11.2/1","figure producer/policy differs")


def artifact_reference(ref):
    require(isinstance(ref,str) and (ref=="main" or re.fullmatch(r"[0-9a-f]{40}",ref) is not None),"artifact reference must be current main or explicit commit SHA")
    return "current main" if ref=="main" else "artifact commit "+ref


def artifact_links(report_id,ref="main"):
    label=artifact_reference(ref)
    require(re.fullmatch(r"lp-\d{8}T\d{6}Z-[0-9a-f]{12}",report_id) is not None,"unsafe report identity")
    base="https://github.com/butahlecoq/controlled-systems-lab/"
    path="/reports/algorithm-results/"+report_id
    return base+"tree/"+ref+path,base+"blob/"+ref+path+".zip",label


def publishable(view):
    validate_view(view)
    return not publication_errors(view)


def publication_errors(view):
    p=view["payload"];errors=[]
    if p["purpose"]!="measurement": errors.append("purpose is not measurement")
    if p["process"]["repetitions"]<5 or not all(g["valid"] for g in aggregate(view)):
        errors.append("incomplete or failed measured groups")
    provenance=p["provenance"];build=provenance["build"]
    if not provenance["tracked_clean"] or build["configuration"]!="Release": errors.append("clean Release source not established")
    if provenance["source_commit"]=="0"*40 or provenance["executable_sha256"]=="0"*64: errors.append("synthetic source/executable identity")
    try:
        require(build["ndebug"] is True and build["cxx_standard"]==20 and bool(build["compiler"]) and bool(build["compiler_version"]),"compiler profile incomplete")
        require(build["source_commit"]==provenance["source_commit"],"embedded source differs")
        require(HEX.fullmatch(provenance["build_log_sha256"]) is not None,"build log hash required")
        require(bool(provenance["build_clean_interval"]["before"]) and bool(provenance["build_clean_interval"]["after"]),"clean build interval missing")
        names={t["name"] for t in provenance["file_api"]["targets"]}
        require({"csl_lp_report","csl_report_support","highs","csl_highs_lp","csl_registry","csl_numeric","csl_optimization","csl_contracts"}<=names,"complete compile/link graph required")
        require(bool(provenance["file_api"]["toolchains"]),"toolchain provenance required")
        for snapshot in ("before","after"):
            machine=p["environment"]["machine_load"][snapshot]
            require(bool(machine["os"]) and bool(machine["cpu"]) and integer(machine["ram_bytes"],1) and integer(machine["logical_processors"],1),"machine provenance unavailable")
        require(bool(p["environment"]["concurrent_work"]),"concurrent-work note missing")
        require(p["process"]["warmups"]==1 and p["environment"]["process_warmup"] is True,"excluded warmup policy missing")
        require(len(p["environment"]["clock_calibration"])==1,"separate clock calibration missing")
        require(p["profile"]["available"] is True and p["profile"]["valid"] is True and HEX.fullmatch(p["profile"]["sha256"]) is not None,"valid separate profile missing")
    except (KeyError,TypeError,ValueError) as error:
        errors.append("publication provenance incomplete: "+str(error))
    return errors


def local_file(root, name):
    require(isinstance(name,str) and re.fullmatch(r"[A-Za-z0-9_.-]+",name) is not None and name not in (".",".."), "unsafe local filename")
    root = Path(root).resolve()
    path = root/name
    require(path.is_file() and not path.is_symlink() and path.resolve().parent == root, "missing/escaping local file")
    return path


def validate_svg(content):
    require(isinstance(content,bytes) and len(content)<=8_000_000, "bounded SVG bytes required")
    text = content.decode("utf-8")
    require(not text.startswith("\ufeff") and re.search(r"<!\s*(?:DOCTYPE|ENTITY)|<\?",text,re.I) is None, "SVG declarations/entities/processing instructions forbidden")
    namespaces = {"http://www.w3.org/2000/svg","http://www.w3.org/1999/xlink"}
    try:
        for _, pair in ET.iterparse(io.StringIO(text),events=("start-ns",)):
            require(pair[1] in namespaces, "unknown SVG namespace")
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError("malformed SVG") from error
    svg = "{http://www.w3.org/2000/svg}"
    require(root.tag == svg+"svg", "SVG root namespace required")
    tags = {"svg","g","defs","path","clipPath","use","rect","line","polyline","polygon","circle","ellipse","text","tspan","style"}
    attributes = {"id","width","height","viewBox","version","x","y","x1","x2","y1","y2","cx","cy","rx","ry","r","d","points","transform","style","clip-path","clipPathUnits","fill","stroke","stroke-width","stroke-linecap","stroke-linejoin","stroke-dasharray","stroke-dashoffset","stroke-opacity","fill-opacity","opacity","font-size","font-family","font-style","font-weight","text-anchor","type","href","{http://www.w3.org/1999/xlink}href"}
    properties = {"fill","fill-opacity","fill-rule","stroke","stroke-width","stroke-linecap","stroke-linejoin","stroke-dasharray","stroke-dashoffset","stroke-opacity","stroke-miterlimit","opacity","font-size","font-family","font-style","font-weight","text-anchor","clip-path"}
    ids, refs = set(), []
    def safe_value(value):
        require(re.search(r"(?:@import|expression|javascript|data:|https?:|file:|\\|[<>])",value,re.I) is None, "unsafe SVG style/value")
        for url in re.findall(r"url\((.*?)\)",value,re.I):
            require(re.fullmatch(r"#[A-Za-z_][\w.-]*",url) is not None, "external CSS reference")
            refs.append(url[1:])
        require("url" not in re.sub(r"url\(#[A-Za-z_][\w.-]*\)","",value,flags=re.I).lower(), "malformed CSS reference")
    def style(value):
        for declaration in value.split(";"):
            if not declaration.strip(): continue
            require(":" in declaration, "malformed SVG style")
            name, val = declaration.split(":",1)
            require(name.strip() in properties, "unknown SVG style property")
            safe_value(val)
    for element in root.iter():
        require(isinstance(element.tag,str) and element.tag.startswith(svg) and element.tag[len(svg):] in tags, "unsafe SVG element")
        for key,value in element.attrib.items():
            require(key in attributes, "unknown/event SVG attribute")
            if key == "id":
                require(value not in ids and re.fullmatch(r"[A-Za-z_][\w.-]*",value) is not None, "duplicate/unsafe SVG id")
                ids.add(value)
            elif key.endswith("href"):
                require(re.fullmatch(r"#[A-Za-z_][\w.-]*",value) is not None, "external SVG reference")
                refs.append(value[1:])
            elif key == "style": style(value)
            else: safe_value(value)
        if element.tag == svg+"style":
            css = element.text or ""
            require(re.fullmatch(r"\s*\*\s*\{[^{}]*\}\s*",css) is not None, "unsupported SVG stylesheet")
            style(css[css.index("{")+1:css.rindex("}")])
    require(all(ref in ids for ref in refs), "missing internal SVG target")
    return text
