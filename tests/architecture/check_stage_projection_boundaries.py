"""Keep plant-specific presentation dependencies outside mathematical modules."""
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
MATH_MODULES = (
    "controllers",
    "geometry",
    "model",
    "numeric",
    "optimization",
    "problem",
    "reachability",
    "sets",
    "simulation",
    "synthesis",
    "verification",
)
MATH_ROOTS = tuple(
    root
    for module in MATH_MODULES
    for root in (f"include/csl/{module}", f"src/{module}")
)
PRESENTATION_INCLUDE = re.compile(
    r"#\s*include\s*[<\"]csl/(?:visualization/|artifacts/"
    r"(?:plot_(?:data|document|request)|stage_projection|control_figure))"
)
PLANT_LABEL = re.compile(r"\b(?:fuel|oxidizer|propellant)\b", re.IGNORECASE)
PAIR_FIELD = re.compile(r"\bprojection_x\d+_x\d+\b")
COMMENTS = re.compile(r"//[^\n]*|/\*[\s\S]*?\*/")


def violations():
    for relative_root in MATH_ROOTS:
        directory = ROOT / relative_root
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if path.suffix not in {".cpp", ".hpp"}:
                continue
            source = path.read_text(encoding="utf-8")
            uncommented = COMMENTS.sub("", source)
            for pattern, description in (
                (PRESENTATION_INCLUDE, "presentation include"),
                (PLANT_LABEL, "plant-specific label"),
                (PAIR_FIELD, "hardcoded coordinate-pair field"),
            ):
                if pattern.search(uncommented):
                    yield f"{path.relative_to(ROOT)}: {description}"


if __name__ == "__main__":
    found = list(violations())
    if found:
        sys.exit("mathematical modules depend on plant-specific presentation:\n" +
                 "\n".join(found))
    print("mathematical modules have no plant-specific stage-visualization dependencies")
