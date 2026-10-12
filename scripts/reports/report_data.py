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
    if "objective" in value:
        value["objective"] = normalize_objective(value["objective"])
    else:
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
    if "solver" in value:
        value["solver"]["objective"]=normalize_objective(value["solver"]["objective"])
        if ref["solver_objective"] is not None: ref["solver_objective"]=finite(ref["solver_objective"])
        ref["coordinate_constraints"]=[[None if x is None else finite(x) for x in pair] for pair in ref["coordinate_constraints"]]
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
        if "solver" in scenario:
            scenario["solver"]["objective"]=normalize_objective(scenario["solver"]["objective"])
            if ref["solver_objective"] is not None: ref["solver_objective"]=finite(ref["solver_objective"])
            ref["coordinate_constraints"]=[[None if x is None else finite(x) for x in pair] for pair in ref["coordinate_constraints"]]
    for trial in payload["trials"]:
        result=trial.get("result")
        if result is None: continue
        if result.get("primal") is not None:
            result["primal"]=[finite(x) for x in result["primal"]]
        if result.get("original_objective") is not None:
            result["original_objective"]=finite(result["original_objective"])
        if result.get("solver_objective") is not None: result["solver_objective"]=finite(result["solver_objective"])
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
    kind=payload.get("report_kind","lp")
    require(kind in ("lp","convex") and (kind!="lp" or "report_kind" not in payload),"closed schema/kind combination")
    return {"schema": CONVEX_SCHEMA if kind=="convex" else SCHEMA, "report_id": f"{kind}-{stamp}-{sha[:12]}",
            "payload_sha256": sha, "payload": payload}


def identity(value):
    require(isinstance(value, dict) and set(value) == {"problem", "program"}, "program identity required")
    require(all(isinstance(x, str) and x for x in value.values()), "nonempty identity required")


def validate_input(data):
    data = normalize_input(data)
    n = objective_dimension(data["objective"]) if "objective" in data else len(data["linear"])
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
    if "solver" in scenario: return convex_reference_matches(trial,scenario)
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
    require(view["schema"] in (SCHEMA,CONVEX_SCHEMA), "unknown view schema")
    convex=view["schema"]==CONVEX_SCHEMA
    payload = view["payload"]
    require((payload.get("report_kind")=="convex") == convex,"schema/kind mismatch")
    if convex: require(payload["native_phase_policy"]=="csl.convex-native-phases/1","native phase policy mismatch")
    backend_id="csl.convex.highs" if convex else "csl.lp.highs"
    require(payload["purpose"] in {"test","measurement"}, "saved views require test or measurement purpose")
    require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", payload["created_utc"]) is not None, "UTC timestamp required")
    require(view == seal(payload), "payload identity/hash mismatch")
    for name in ("provenance", "environment", "process", "profile"):
        require(isinstance(payload[name], dict), f"{name} required")
    require(payload["historical"] == [], "historical track is separate and empty in v1")
    provenance = payload["provenance"]
    require(re.fullmatch(r"[0-9a-f]{40}", provenance["source_commit"]) is not None, "source SHA required")
    require(type(provenance["tracked_clean"]) is bool and HEX.fullmatch(provenance["executable_sha256"]) is not None, "executable provenance")
    require(provenance["backend"] == {"id": backend_id, "version": "1.0.0+highs.1.11.0"}, "backend identity")
    if convex:
        if payload["purpose"]=="measurement" or "native_archive_sha256" in provenance:
            require(provenance["native_archive_sha256"]==CONVEX_ARCHIVE,"convex provenance archive differs from diagnostic pin")
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
        require(("objective" in scenario["input"]) == convex,"input kind mismatch")
        if convex: validate_convex_scenario(scenario)
        require(scenario["input_sha256"] == input_digest(scenario["input"]), "input hash mismatch")
        require(scenario["scenario_sha256"] == scenario_digest(scenario), "scenario hash mismatch")
        ref = scenario["reference"]
        require(ref["outcome"] in OUTCOMES and bool(ref["derivation"]) and bool(scenario["assumptions"]), "reference required")
        if not convex: require((ref["point"] is not None and ref["objective"] is not None) == (ref["outcome"] == "optimal"), "reference witness mismatch")
        scenarios[key] = scenario
    require(bool(scenarios), "empty scenario catalogue")
    _validate_trial_rows(payload["trials"],scenarios,provenance,clock,environment,convex,backend_id,payload["purpose"],payload["process"]["repetitions"],len(scenarios) if convex and payload["purpose"]=="measurement" else 0)
    if convex:
        warmups=payload["warmup_trials"]
        require(isinstance(warmups,list),"warmup observations required")
        if payload["purpose"]=="test": require(not warmups and payload["process"]["warmups"]==0,"functional views cannot relabel warmups")
        else:
            require(payload["process"]["warmups"]==1 and len(warmups)<=len(scenarios),"one bounded excluded warmup per case required")
            _validate_trial_rows(warmups,scenarios,provenance,clock,environment,convex,backend_id,"warmup",1)
            if payload["process"]["complete"]:require(len(warmups)==len(scenarios),"completed measurement lacks warmups")
        require(payload["process"]["warmup_failures"]==sum(not t["validation"]["passed"] for t in warmups),"warmup failure count differs")
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
    require(re.fullmatch(r"(?:(?:lp|convex)-\d{8}T\d{6}Z-(?:[0-9a-f]{12}|[0-9a-f]{64})|opt05-hull-\d{8}-[0-9a-f]{8}|(?:opt05-hull|geo03)-\d{8}-[0-9a-f]{64}|geo03-\d{8}-[0-9a-f]{12}|geo04-\d{8}T\d{6}Z-(?:[0-9a-f]{12}|[0-9a-f]{64}))",report_id) is not None,"unsafe report identity")
    base="https://github.com/butahlecoq/controlled-systems-lab/"
    path="/reports/algorithm-results/"+report_id
    return base+"tree/"+ref+path,base+"blob/"+ref+path+".zip",label


def publishable(view):
    validate_view(view)
    return not publication_errors(view)


def publication_errors(view):
    p=view["payload"];errors=[]
    if p["purpose"]!="measurement": errors.append("purpose is not measurement")
    if view["schema"]==CONVEX_SCHEMA and p["process"].get("warmup_failures",0):errors.append("failed excluded warmup")
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
        if view["schema"]==SCHEMA: require({"csl_lp_report","csl_report_support","highs","csl_highs_lp","csl_registry","csl_numeric","csl_optimization","csl_contracts"}<=names,"complete compile/link graph required")
        if view["schema"]==CONVEX_SCHEMA:
            require({"csl_convex_report","csl_convex_report_support","csl_report_runtime","csl_highs_convex","csl_convex","csl_objectives","highs","csl_registry","csl_numeric","csl_optimization","csl_contracts"}<=names,"complete convex graph required")
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
    tags = {"svg","g","defs","path","clipPath","use","rect","line","polyline","polygon","circle","ellipse","text","tspan","style","title","desc"}
    attributes = {"id","class","width","height","viewBox","version","x","y","x1","x2","y1","y2","cx","cy","rx","ry","r","d","points","transform","style","clip-path","clipPathUnits","fill","stroke","stroke-width","stroke-linecap","stroke-linejoin","stroke-dasharray","stroke-dashoffset","stroke-opacity","fill-opacity","opacity","font-size","font-family","font-style","font-weight","text-anchor","type","href","role","aria-label","aria-labelledby","{http://www.w3.org/1999/xlink}href"}
    properties = {"fill","fill-opacity","fill-rule","stroke","stroke-width","stroke-linecap","stroke-linejoin","stroke-dasharray","stroke-dashoffset","stroke-opacity","stroke-miterlimit","opacity","font","font-size","font-family","font-style","font-weight","text-anchor","clip-path"}
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
            if key=="class": require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*(?:\s+[A-Za-z_][A-Za-z0-9_-]*)*",value) is not None,"unsafe SVG class")
            if key=="role": require(value in {"img","graphics-document"},"unsupported SVG role")
            if key=="aria-label": require(bool(value.strip()) and len(value)<=256,"invalid SVG accessible label")
            if key=="aria-labelledby":
                tokens=value.split();require(bool(tokens) and all(re.fullmatch(r"[A-Za-z_][\w.-]*",token) for token in tokens),"invalid SVG accessible references");refs.extend(tokens)
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
            rule_pattern = r"(?:\*|text|\.scenario|text\.scenario)\s*\{([^{}]*)\}"
            rules = list(re.finditer(rule_pattern, css))
            require(rules and re.fullmatch(r"\s*(?:(?:\*|text|\.scenario|text\.scenario)\s*\{[^{}]*\}\s*)+",css) is not None, "unsupported SVG stylesheet")
            for rule in rules:
                style(rule.group(1))
    require(all(ref in ids for ref in refs), "missing internal SVG target")
    return text

# Fixed adapter observation policy csl.convex-native-phases/1. No clock or solver.
CONVEX_SCHEMA = 'csl.algorithm-report-view/2'
CONVEX_EVENT_SCHEMA = 'csl.convex-report-events/1'
CONVEX_ARCHIVE = '2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275'
NATIVE_PHASES = ('feasibility', 'qp', 'linear')


def convex_prefix(raw, original, solver):
    require(isinstance(raw, str) and '\nnative.log:\n' in raw, 'complete native prefix required')
    fields = {}
    for line in raw.split('\nnative.log:\n', 1)[0].splitlines():
        require('=' in line, 'malformed convex prefix')
        key, value = line.split('=', 1)
        require(key not in fields, 'duplicate convex prefix key')
        fields[key] = value
    require(fields.get('adapter.version') == '1.0.0+highs.1.11.0' and
            fields.get('native.version') == '1.11.0' and
            fields.get('native.archive_sha256') == CONVEX_ARCHIVE, 'convex diagnostic source profile')
    require(fields.get('program.original') == original and fields.get('program.solver') == solver,
            'convex diagnostic program association')
    return fields


def convex_native_phases(trial, route, solver):
    """Project returned evidence; absent evidence remains unknown, never implicit zero."""
    require(route in ('qp', 'linear', 'constant'), 'closed convex route required')
    result = trial.get('result')
    complete = result is not None and trial['harness']['status'] == 'returned'
    fields = convex_prefix(result['raw_diagnostics'], trial['identity']['program'], solver) if result else {}
    if complete:
        require(trial.get('attempt') == {'number':1,'state':'returned_result','workspace_reuse':False},
                'returned phase evidence requires associated current attempt')
    positions={key:i for i,key in enumerate(fields)}
    phase_evidence=set()
    for key in fields:
        if key.startswith('phase.'):
            require(key in {'phase.'+p+'.'+suffix for p in NATIVE_PHASES for suffix in ('time_limit','api_status','model_status','iterations','info')},'unknown pinned native phase field')
            phase_evidence.add(key.split('.')[1])
    selected={'qp':{'feasibility','qp'},'linear':{'linear'},'constant':set()}[route]
    require(phase_evidence <= selected, 'native route conflict')
    if trial.get('public_run_entered') is False:
        require(result is None and trial.get('attempt') is None and trial['harness']['status']!='returned',
                'before-public-entry boundary conflicts with returned evidence')
    observed = {}
    for phase in NATIVE_PHASES:
        prefix = 'phase.' + phase + '.'
        api, model = fields.get(prefix+'api_status'), fields.get(prefix+'model_status')
        count, info = fields.get(prefix+'iterations'), fields.get(prefix+'info')
        require((api is None) == (model is None), 'half-paired native status')
        require(not (count is not None and info is not None), 'conflicting native iteration dispositions')
        require(api is not None or (count is None and info is None), 'iteration without returned call')
        if api is not None:
            require(complete, 'returned statuses require complete returned observation')
            require(api in ('-1','0','1') and re.fullmatch(r'[0-9]+',model) is not None and int(model)<=18,
                    'invalid pinned native status')
            require((count is not None) != (info is not None), 'missing native iteration disposition')
            if count is not None:
                require(api != '-1' and re.fullmatch(r'[0-9]+',count) is not None and int(count)<=2147483647,
                        'untrusted or invalid native count')
            else: require(info == 'unavailable', 'invalid native info marker')
            disposition=prefix+('iterations' if count is not None else 'info')
            require(prefix+'time_limit' in fields and positions[prefix+'time_limit']<positions[prefix+'api_status']<positions[prefix+'model_status']<positions[disposition], 'native return statement order differs')
            observed[phase] = {'api_status':int(api),'model_status':int(model)}
        if prefix+'time_limit' in fields:
            budget=fields[prefix+'time_limit']
            require(budget == 'inf' or finite(float(budget)) >= 0, 'invalid native budget')
    # Check positive source boundaries before assigning any precedence to them.
    # A configured budget is branch evidence even when the run never started.
    start_evidence=any(key.startswith('start.') for key in fields) or 'qp_run' in fields
    if 'native_run' in fields:
        require(fields['native_run']=='false' and not phase_evidence and not start_evidence and 'setup.error' not in fields,
                'native noncall marker conflicts with phase setup')
    if 'wrapper.decision' in fields:
        require(fields['wrapper.decision']=='constant_rows' and route=='constant' and fields.get('native_run')=='false',
                'constant wrapper boundary conflicts with route')
    feasible=('feasibility' in observed and observed['feasibility']['api_status'] in (0,1) and observed['feasibility']['model_status']==7)
    if start_evidence:
        require(route=='qp' and feasible, 'QP start without successful feasibility return')
        require(fields.get('start.valid') in ('true','false'), 'invalid QP start observation')
        if fields['start.valid']=='false':
            require(fields.get('qp_run')=='false' and 'qp' not in phase_evidence and 'start.default_fallback' not in fields,
                    'invalid start conflicts with QP setup')
            require(positions['phase.feasibility.model_status']<positions['qp_run']<positions['start.valid'],
                    'invalid start boundary order differs')
        else:
            require('qp_run' not in fields and fields.get('start.default_fallback')=='false',
                    'valid start conflicts with QP noncall marker')
            require(positions['phase.feasibility.model_status']<positions['start.valid']<positions['start.default_fallback'],
                    'valid start boundary order differs')
    if 'qp' in phase_evidence:
        require(feasible and fields.get('start.valid')=='true' and fields.get('start.default_fallback')=='false',
                'QP setup without verified feasible start')
        require(positions['start.default_fallback']<positions['phase.qp.time_limit'], 'native feasibility/QP ordering differs')
    stopped = complete and result['termination'] in ('cancelled','resource_limit') and result['outcome']=='undetermined' and 'setup.error' not in fields
    unknown_reason = ('exception_boundary_unobserved' if trial['harness']['status']=='exception' else
                      'aborted_boundary_unobserved' if trial['harness']['status']=='aborted' else 'no_returned_phase_evidence')
    entries={}
    for phase in NATIVE_PHASES:
        prefix='phase.'+phase+'.'
        state, reason = 'unknown', unknown_reason
        if phase in observed: state,reason='observed_return','returned_status_pair'
        elif trial.get('public_run_entered') is False: state,reason='known_not_called','before_public_entry'
        elif complete and fields.get('native_run')=='false':
            if fields.get('wrapper.decision')=='constant_rows':
                require(route=='constant','constant wrapper route mismatch')
                state,reason='known_not_called','constant_rows_wrapper'
            else:
                require(stopped,'pre-entry marker requires stopped result')
                state,reason='known_not_called','explicit_pre_entry_stop'
        elif complete and phase=='qp' and fields.get('qp_run')=='false' and fields.get('start.valid')=='false':
            state,reason='known_not_called','invalid_qp_start'
        elif stopped and prefix+'time_limit' in fields:
            state,reason='known_not_called','stopped_before_phase_call'
        elif complete and route=='qp' and phase=='qp' and (
                entries.get('feasibility',{}).get('execution',{}).get('reason')=='stopped_before_phase_call' or
                ('feasibility' in observed and (observed['feasibility']['api_status']==-1 or observed['feasibility']['model_status']!=7 or
                 (stopped and 'phase.qp.time_limit' not in fields)))):
            state,reason='known_not_called','earlier_phase_exit'
        elif complete and ((route=='qp' and phase=='linear') or (route=='linear' and phase!='linear')):
            state,reason='known_not_called','route_not_selected'
        count=fields.get(prefix+'iterations') if state=='observed_return' else None
        iteration_reason=(None if count is not None else 'native_info_unavailable' if state=='observed_return' else
                          'phase_not_called' if state=='known_not_called' else 'execution_unknown')
        entries[phase]={'execution':{'state':state,'reason':reason,'statuses':observed.get(phase)},
                        'iterations':{'available':count is not None,'kind':'qp' if phase=='qp' else 'simplex',
                                      'value':int(count) if count is not None else None,'reason':iteration_reason},
                        'elapsed':{'available':False,'value':None,'unit':'ns','reason':'not_exposed_by_adapter'}}
    return entries


def normalize_objective(value):
    value=copy.deepcopy(value)
    kind=value['kind']
    expected={'linear':{'kind','coefficients','offset'},'quadratic':{'kind','Q','linear','offset'},
              'residual_norm':{'kind','L','target'}}
    require(kind in expected and set(value)==expected[kind],'closed objective snapshot required')
    for field in ('coefficients','linear','target'):
        if field in value: value[field]=[finite(x) for x in value[field]]
    if 'offset' in value: value['offset']=finite(value['offset'])
    for field in ('Q','L'):
        if field in value:
            matrix=value[field]
            require(set(matrix)=={'rows','cols','values'},'dense matrix shape required')
            rows,cols=integer(matrix['rows']),integer(matrix['cols'])
            require(rows<=4096 and cols<=4096 and len(matrix['values'])==rows*cols,'dense matrix dimensions differ')
            matrix['values']=[finite(x) for x in matrix['values']]
    if kind=='quadratic': require(value['Q']['rows']==value['Q']['cols']==len(value['linear']),'quadratic dimensions differ')
    if kind=='residual_norm': require(value['L']['rows']==len(value['target']),'residual dimensions differ')
    return value


def objective_dimension(value):
    value=normalize_objective(value)
    return len(value['coefficients']) if value['kind']=='linear' else value['Q']['cols'] if value['kind']=='quadratic' else value['L']['cols']


def validate_convex_scenario(s):
    solver=s['solver'];identity(solver['identity'])
    require(set(solver)=={'identity','objective','transformation'},'closed solver snapshot required')
    original=s['input']['objective'];quadratic=normalize_objective(solver['objective'])
    require(quadratic['kind']=='quadratic' and objective_dimension(original)==objective_dimension(quadratic),'solver snapshot dimension')
    require(solver['identity']['problem']==s['identity']['problem'],'solver problem differs')
    if original['kind']=='residual_norm':
        require(solver['transformation']=='residual_norm_squared' and solver['identity']['program']!=s['identity']['program'],'pure norm transformation association')
    else:
        require(solver['transformation'] is None and solver['identity']==s['identity'],'untransformed program association')
        if original['kind']=='quadratic': require(normalize_objective(original)==quadratic,'untransformed quadratic snapshot differs')
    ref=s['reference'];n=objective_dimension(original)
    require(set(ref)=={'outcome','point','coordinate_constraints','objective','solver_objective','derivation'},'closed convex reference')
    if ref['outcome']=='optimal':
        finite(ref['objective']);finite(ref['solver_objective'])
        require((ref['point'] is not None) != bool(ref['coordinate_constraints']),'exactly one minimizer predicate required')
        if ref['point'] is not None:
            require(len(ref['point'])==n,'reference dimension');[finite(x) for x in ref['point']]
        else:
            require(len(ref['coordinate_constraints'])==n,'complete coordinate predicate required')
            for pair in ref['coordinate_constraints']:
                require(len(pair)==2,'coordinate interval shape')
                for x in pair:
                    if x is not None: finite(x)
                require(pair[0] is None or pair[1] is None or pair[0]<=pair[1],'coordinate interval order')
    else: require(ref['point'] is None and not ref['coordinate_constraints'] and ref['objective'] is None and ref['solver_objective'] is None,'nonoptimal reference has no minimizer')


def convex_route(scenario):
    q=scenario['solver']['objective']
    if objective_dimension(q)==0: return 'constant'
    return 'qp' if any(x!=0 for x in q['Q']['values']) else 'linear'


def convex_completed_route(trial,scenario):
    phases=trial['native_phases'];route=convex_route(scenario)
    if route=='constant': return all(v['execution']['reason']=='constant_rows_wrapper' for v in phases.values())
    expected={'optimal':7,'infeasible':8,'unbounded':10}.get(scenario['reference']['outcome'])
    def returned(phase,model):
        e=phases[phase]['execution'];statuses=e['statuses']
        return e['state']=='observed_return' and statuses['api_status'] in (0,1) and statuses['model_status']==model
    if route=='linear': return returned('linear',expected) and all(phases[p]['execution']['reason']=='route_not_selected' for p in ('feasibility','qp'))
    if phases['linear']['execution']['reason']!='route_not_selected': return False
    if scenario['reference']['outcome']=='infeasible': return returned('feasibility',8) and phases['qp']['execution']['reason']=='earlier_phase_exit'
    fields=convex_prefix(trial['result']['raw_diagnostics'],scenario['identity']['program'],scenario['solver']['identity']['program'])
    return returned('feasibility',7) and returned('qp',expected) and fields.get('start.valid')=='true' and fields.get('start.default_fallback')=='false'


def convex_reference_matches(trial,scenario):
    r=trial['result'];ref=scenario['reference']
    if r is None or r['termination']!='completed' or r['outcome']!=ref['outcome']: return False
    if r['support']!={'kind':'unestablished'} or r['bounds']!={'lower':None,'upper':None}: return False
    if ref['outcome']!='optimal': return True
    x=r['primal'];close=lambda a,b: abs(a-b)<=1e-8+1e-8*max(abs(a),abs(b))
    if x is None or r['original_objective'] is None or r['solver_objective'] is None: return False
    if not close(r['original_objective'],ref['objective']) or not close(r['solver_objective'],ref['solver_objective']): return False
    if ref['point'] is not None:
        if len(x)!=len(ref['point']) or not all(close(a,b) for a,b in zip(x,ref['point'])): return False
    else:
        if len(x)!=len(ref['coordinate_constraints']): return False
        for v,(lo,hi) in zip(x,ref['coordinate_constraints']):
            if (lo is not None and v<lo and not close(v,lo)) or (hi is not None and v>hi and not close(v,hi)):return False
    a=scenario['input']['constraints']
    activities=[sum(a['values'][j]*x[a['indices'][j]] for j in range(a['starts'][i],a['starts'][i+1])) for i in range(a['rows'])]
    for v,(lo,hi) in zip(x+activities,scenario['input']['variables']+scenario['input']['rows']):
        if (lo is not None and v<lo and not close(v,lo)) or (hi is not None and v>hi and not close(v,hi)):return False
    return residual_passes(r['primal_residuals'],('rows','variables')) and residual_passes(r['dual_residuals'],('stationarity','signs','complementarity'))


def _validate_trial_rows(trials,scenarios,provenance,clock,environment,convex,backend_id,purpose,repetitions,sequence_offset=0):
    seen, sequences = set(), set()
    repetitions=integer(repetitions,1)
    require(repetitions<=1000,"bounded repetition count required")
    order=[(key,round_) for round_ in range(1,repetitions+1) for key in scenarios]
    for trial_index,trial in enumerate(trials):
        key = trial["case_id"]
        require(key in scenarios and trial["purpose"] == purpose, "trial scenario/purpose mismatch")
        pair = (key, integer(trial["round"],1))
        require(trial_index<len(order) and pair==order[trial_index], "trial round/order differs from declared round robin")
        require(pair not in seen, "duplicate trial")
        seen.add(pair)
        sequence = integer(trial["sequence"],1)
        require(sequence not in sequences, "duplicate sequence")
        sequences.add(sequence)
        if convex: require(sequence==sequence_offset+trial_index+1,"convex sequence differs from round robin")
        require(trial["identity"] == scenarios[key]["identity"], "trial identity mismatch")
        require(trial["registry"]["requested"] == backend_id, "requested method mismatch")
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
                require(len(result["primal"]) == (objective_dimension(scenarios[key]["input"]["objective"]) if convex else len(scenarios[key]["input"]["linear"])), "candidate dimension")
                for value in result["primal"]: finite(value)
            if result["original_objective"] is not None: finite(result["original_objective"])
            _residual(result["primal_residuals"],trial["identity"],("rows","variables"))
            _residual(result["dual_residuals"],trial["identity"],("stationarity","signs","complementarity"))
            if convex:
                for block in (result["primal_residuals"],result["dual_residuals"]):
                    if block is not None:
                        require(all(block['context'][key]==environment[key] for key in ('absolute_tolerance','relative_tolerance')),
                                'convex residual context differs from declared numerical policy')
            require(isinstance(result["raw_diagnostics"],str), "raw diagnostics required")
        if convex:
            require(type(trial["public_run_entered"]) is bool and trial["public_run_entered"]==trial["timings"]["public_run"]["available"],"public entry boundary mismatch")
            require(trial["native_phases"]==convex_native_phases(trial,convex_route(scenarios[key]),scenarios[key]["solver"]["identity"]["program"]),"native phase projection differs")
            if result and result["solver_objective"] is not None: finite(result["solver_objective"])
            if result: validate_convex_result(result,scenarios[key])
        else:
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
            if convex: require(convex_completed_route(trial,scenarios[key]),"required native convex route not observed")
            else: require("\nnative_run=true" in result["raw_diagnostics"].split("\nnative.log:",1)[0] or purpose == "test", "native run not observed")


def validate_convex_result(result,scenario):
    fields=convex_prefix(result['raw_diagnostics'],scenario['identity']['program'],scenario['solver']['identity']['program'])
    profile={'profile.maximum_variables':'4096','profile.highs_int_bits':'32','options.qp_nullspace_limit':'4096',
             'options.qp_regularization_value':'0','options.use_warm_start':'true','options.presolve':'off','options.threads':'1','options.parallel':'off',
             'options.small_matrix_value':'1e-12','options.infinite_bound':'inf','options.infinite_cost':'inf','options.large_matrix_value':'inf',
             'certificates':'unavailable','bounds':'unavailable','basis':'unavailable','families':'unavailable'}
    require(all(fields.get(k)==v for k,v in profile.items()),'fixed convex native profile differs')
    require(finite(float(fields['options.native_tolerance']))==1e-8,'native tolerance differs')
    for name in ('feasibility','qp'):require(fields['options.'+name+'_iteration_limit']=='2147483647','measurement adapter iteration profile differs')
    for name,key in (('original','original_objective'),('solver','solver_objective')):
        text=fields.get('objective.'+name)
        require((text is None)==(result[key] is None),'objective availability differs from returned evidence')
        if text is not None:require(finite(float(text))==finite(result[key]),'objective differs from returned native evidence')
    for block,names in (('primal_residuals',('rows','variables')),('dual_residuals',('stationarity','signs','complementarity'))):
        for name in names:
            metric=result[block][name] if result[block] else None
            for field in ('violation','scale'):
                text=fields.get('check.'+name+'.'+field)
                require((text is None)==(metric is None),'residual availability differs from returned evidence')
                if text is not None:require(finite(float(text))==finite(metric[field]),'residual differs from returned native evidence')
