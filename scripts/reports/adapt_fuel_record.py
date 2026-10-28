"""Convert saved B06 or B07 fuel records to csl.plot-document/1."""
from __future__ import annotations
import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


B06_DRIVER_A=[[1,0,0,0],[-2,1,0,0],[0,0,1,0],[0,0,-2,1]]
B06_DRIVER_B=[0.7,0,-1.0/3.0,0]
B06_MANIFEST_A_15=["1","0","0","0","-2","1","0","0","0","0","1","0","0","-2","1"]
B06_MEASURED_DRIVER=Path(__file__).parents[2]/"tests/fixtures/reports/b06-measured-source/b06_finite_minimax.cpp"


def convert_b06(root):
    root=Path(root)
    scenario_path=root/"scenario.json"; geometry_path=root/"geometry.json"
    scenario=json.loads(scenario_path.read_text());geometry=json.loads(geometry_path.read_text())
    if geometry.get("schema") != "csl.issue6-b06-run/1" or geometry.get("status") != "numerical_optimal":
        raise ValueError("unsupported or unsuccessful B06 geometry record")
    states=[{"id":"x1","name":"oxidizer flow x₁","unit":"kg/s"},{"id":"x2","name":"oxidizer stock balance x₂","unit":"kg"},
            {"id":"x3","name":"fuel flow x₃","unit":"kg/s"},{"id":"x4","name":"fuel stock balance x₄","unit":"kg"}]
    points=geometry["winner_terminal_vertices"]
    raw_path=root/"raw-runs.jsonl"
    runs=[json.loads(line) for line in raw_path.read_text().splitlines() if line.strip()]
    driver_path=B06_MEASURED_DRIVER
    if not runs or digest(driver_path)!=runs[0].get("driver_sha256"):
        raise ValueError("B06 source driver does not match the saved run provenance")
    measured=[row["elapsed_ns"] for row in runs if row.get("batch")!=0]
    scenario_id=scenario["id"]
    minimizing=geometry["minimizing_plan_indices"]
    catalogue=[float(x) for x in scenario["model"]["control_catalogue_ordered"]]
    model=scenario["model"]
    manifest_a=model["A_row_major"]
    if manifest_a not in (B06_MANIFEST_A_15,[str(value) for row in B06_DRIVER_A for value in row]):
        raise ValueError("B06 scenario A matrix differs from the hashed source driver")
    input_vector=[float(Fraction(x)) for x in model["B"]]
    if input_vector!=B06_DRIVER_B:
        raise ValueError("B06 scenario B vector differs from the hashed source driver")
    if len(minimizing)!=1 or len(catalogue)!=5 or model["horizon"]!=5 or model["state_dimension"]!=4 or model["control_dimension"]!=1:
        raise ValueError("B06 nominal witness needs one minimizing plan, five controls, and five stages")
    plan_index=minimizing[0];digits=[0]*5
    for stage in reversed(range(5)):
        digits[stage]=plan_index%len(catalogue);plan_index//=len(catalogue)
    if plan_index: raise ValueError("B06 minimizing plan index is outside the declared catalogue")
    controls=[catalogue[d] for d in digits]
    state=[float(x) for x in model["initial_state"]]
    if len(state)!=4: raise ValueError("B06 initial state must have four coordinates")
    history=[state]
    for u in controls:
        state=[sum(B06_DRIVER_A[i][j]*state[j] for j in range(4))+input_vector[i]*u for i in range(4)]
        history.append(state)
    plan_worst_case=geometry["objective_norm"]
    source_hashes={"geometry.json":digest(geometry_path),"scenario.json":digest(scenario_path),"b06_finite_minimax.cpp":digest(driver_path)}
    selected_history={"kind":"trajectory","source":{"kind":"selected_plan_witness","id":f"plan-{minimizing[0]}-zero-disturbance",
            "method_id":"B06 finite-action minimax","method_version":"saved-record","source_files_sha256":source_hashes},"witness_id":f"plan-{minimizing[0]}-zero-disturbance",
            "states":[[v for v in row] for row in history],"controls":[[v] for v in controls],
            "state_coordinate_ids":["x1","x2","x3","x4"],"control_coordinate_ids":["u"],
            "objective":plan_worst_case,"objective_label":"minimax plan worst-case objective norm",
            "objective_evidence":"saved numerical minimax result; see exact-oracle record for the finite-action oracle",
            "evidence":"one zero-disturbance history derived in binary64 from initial state and controls in the saved scenario plus the hashed B06 driver transition; the saved scenario A matrix is malformed (15 entries)",
            "assurance":"numerical trajectory reconstruction for this stated disturbance; plan optimality evidence is separate",
            "approximation":"one selected feasible history; not the full reachable or optimal family"}
    series=[selected_history,
            {"kind":"projection","source":{"kind":"run","id":"b06-owner-confirmed-7df01ba3af5e4c46","method_id":"B06 finite-action minimax","method_version":"saved-record"},
                "title":"B06 terminal reachable set projection: flow","scenario_id":scenario_id,
                "coordinate_ids":["x1","x3"],"points":[[p[0],p[2]] for p in points],"relation":"terminal projection of 4D numeric V-representation",
                "evidence":"saved numerical solver output; binary64 assurance","limitation":"not a validated real-arithmetic enclosure; not a historical reproduction",
                "objective":plan_worst_case,"objective_label":"minimum worst-case objective norm","objective_evidence":"saved numerical minimax result","target":[30.0,20.0]},
            {"kind":"projection","source":{"kind":"run","id":"b06-owner-confirmed-7df01ba3af5e4c46","method_id":"B06 finite-action minimax","method_version":"saved-record"},
                "title":"B06 terminal reachable set projection: stock balance","scenario_id":scenario_id,
                "coordinate_ids":["x2","x4"],"points":[[p[1],p[3]] for p in points],"relation":"terminal projection of 4D numeric V-representation",
                "evidence":"saved numerical solver output; binary64 assurance","limitation":"negative stock balances are displayed; no nonnegativity constraint is modeled",
                "objective":plan_worst_case,"objective_label":"minimum worst-case objective norm","objective_evidence":"saved numerical minimax result","target":[0.0,0.0]},
            {"kind":"timing","source":{"kind":"run","id":"b06-owner-confirmed-7df01ba3af5e4c46","method_id":"B06 finite-action minimax","method_version":"saved-record"},
                "operation":"public minimax solve","metric":"wall","values":measured,"availability":"available","span_semantics":"inclusive"},
            {"kind":"timing","source":{"kind":"run","id":"b06-owner-confirmed-7df01ba3af5e4c46","method_id":"B06 finite-action minimax","method_version":"saved-record"},
                "operation":"worker time","metric":"work","values":[],"availability":"unavailable","span_semantics":"not_applicable"},
            {"kind":"timing","source":{"kind":"run","id":"b06-owner-confirmed-7df01ba3af5e4c46","method_id":"B06 finite-action minimax","method_version":"saved-record"},
                "operation":"CPU time","metric":"cpu","values":[],"availability":"unavailable","span_semantics":"not_applicable"}]
    return {"schema":"csl.plot-document/1","provenance":{"record_schema":geometry["schema"],"record_id":"b06-owner-confirmed-7df01ba3af5e4c46",
            "source_sha256":digest(geometry_path),"source_files_sha256":source_hashes,"scenario_id":scenario["id"],"method_id":"B06 finite-action minimax","method_version":"saved-record"},
            "coordinates":{"states":states,"controls":[{"id":"u","name":"burn command u","unit":"dimensionless"}]},
            "axes":{"states":{"kind":"stage","points":[0,1,2,3,4,5],"label":"stage"},"controls":{"kind":"stage","points":[0,1,2,3,4],"interval_ends":[1,2,3,4,5],"label":"stage"}},
            "series":series}


def convert_b07(root):
    root=Path(root); records=root/"results.jsonl"
    rows=[json.loads(line) for line in records.read_text().splitlines() if line.strip()]
    if len(rows)!=8 or any(row.get("status")!="numerical_optimal" for row in rows):
        raise ValueError("expected eight successful saved B07 cases")
    states=[{"id":"x1","name":"oxidizer flow x₁","unit":"kg/s"},{"id":"x2","name":"oxidizer stock x₂","unit":"kg"},
            {"id":"x3","name":"fuel flow x₃","unit":"kg/s"},{"id":"x4","name":"fuel stock x₄","unit":"kg"}]
    series=[]
    for row in rows:
        pts=row["winner_terminal_vertices_x1_x3_x2_x4"]
        common={"scenario_id":row["case_id"],"relation":"terminal projection of saved 4D disturbance V-representation",
                "evidence":"saved numerical solver output; independently checked objective and plan enumeration",
                "limitation":"not a nonlinear replay trajectory; 10 s model, not the article's 100 s horizon"}
        series.append({"kind":"projection","source":{"kind":"run","id":row["case_id"],"method_id":"B07 fixed-plan minimax","method_version":"saved-record"},
                       "title":f"{row['case_id']} · flow","coordinate_ids":["x1","x3"],"objective":row["value_norm"],
                       "objective_label":"worst-case objective norm","objective_evidence":"saved numerical minimax result",
                       "points":[[p[0],p[1]] for p in pts],**common})
        series.append({"kind":"projection","source":{"kind":"run","id":row["case_id"],"method_id":"B07 fixed-plan minimax","method_version":"saved-record"},
                       "title":f"{row['case_id']} · stock","coordinate_ids":["x2","x4"],"objective":row["value_norm"],
                       "objective_label":"worst-case objective norm","objective_evidence":"saved numerical minimax result",
                       "points":[[p[2],p[3]] for p in pts],**common})
    timings=[row["median_elapsed_ns"] for row in rows]
    shared={"source":{"kind":"comparison","id":"b07-owner-approved-eight-case-v1","method_id":"B07 fixed-plan minimax","method_version":"saved-record"}}
    series.extend([{**shared,"kind":"timing","operation":"public minimax call per case","metric":"wall","values":timings,"availability":"available","span_semantics":"inclusive"},
                   {**shared,"kind":"timing","operation":"worker time","metric":"work","values":[],"availability":"unavailable","span_semantics":"not_applicable"},
                   {**shared,"kind":"timing","operation":"CPU time","metric":"cpu","values":[],"availability":"unavailable","span_semantics":"not_applicable"}])
    return {"schema":"csl.plot-document/1","provenance":{"record_schema":"csl.issue6-b07-results/1","record_id":"b07-owner-approved-eight-case-v1",
            "source_sha256":digest(records),"scenario_id":"eight owner-approved reconstructions","method_id":"B07 fixed-plan minimax","method_version":"saved-record"},
            "coordinates":{"states":states,"controls":[]},"axes":{"states":{"kind":"stage","points":[5],"label":"terminal stage"},"controls":{"kind":"stage","points":[],"interval_ends":[],"label":"stage"}},"series":series}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("format",choices=("b06","b07"));p.add_argument("records",type=Path);p.add_argument("output",type=Path);a=p.parse_args()
    doc=convert_b06(a.records) if a.format=="b06" else convert_b07(a.records)
    a.output.write_text(json.dumps(doc,indent=2,allow_nan=False)+"\n",encoding="utf-8")


if __name__=="__main__":main()
