"""Evaluate explicit evidence without turning missing checks into success."""

import json
from pathlib import Path
import sys

GRAPH_CHANGE_GATES = (
    "restorePoint", "compile", "engineValidation", "references",
    "automation", "graphReadability", "visualCapture",
)


def evaluate(evidence, required=GRAPH_CHANGE_GATES):
    gates = []
    for name in required:
        item = evidence.get(name, {})
        status = str(item.get("status", "not_run")).lower()
        if status not in {"pass", "fail", "not_run", "not_applicable"}:
            status = "not_run"
        gates.append({"name": name, "status": status, "evidence": item.get("evidence")})
    if any(item["status"] == "fail" for item in gates):
        status = "fail"
    elif all(item["status"] in {"pass", "not_applicable"} for item in gates):
        status = "pass"
    else:
        status = "partial"
    return {"schemaVersion": "dp.unreal.acceptance/v1", "status": status, "gates": gates}


def main(argv):
    if len(argv) < 2:
        raise SystemExit("Usage: acceptance_gate.py <evidence.json> [output.json]")
    evidence = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    result = evaluate(evidence)
    if len(argv) > 2:
        Path(argv[2]).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
