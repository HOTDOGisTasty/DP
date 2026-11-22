"""Run deterministic checks over an exported Unreal context set."""

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path

from layout_audit import audit_graph
from validate_export import validate


def run(root):
    root = Path(root)
    structural = validate(root)
    assets = []
    index_path = root / "assets-index.json"
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for item in index.get("assets", []):
            document_path = root / item.get("file", "")
            if not document_path.is_file():
                continue
            document = json.loads(document_path.read_text(encoding="utf-8"))
            layout = audit_graph(document)
            assets.append({
                "objectPath": item.get("objectPath"),
                "document": item.get("file"),
                "exportErrors": document.get("errors", []),
                "engineValidation": document.get("validation", {}),
                "layoutIssues": layout,
                "counts": {
                    "nodes": len(document.get("graph", {}).get("nodes", [])),
                    "dependencies": len(document.get("dependencies", [])),
                    "referencers": len(document.get("referencers", [])),
                },
            })
    failures = len(structural) + sum(len(item["exportErrors"]) for item in assets)
    missing_engine_validation = sum(
        1 for item in assets
        if item["engineValidation"].get("required", True) is not False
        if str(item["engineValidation"].get("status", "not_run")).lower() in
        {"not_run", "none", "unknown", ""}
    )
    if failures:
        status = "fail"
    elif missing_engine_validation:
        status = "partial"
    else:
        status = "pass"
    return {
        "schemaVersion": "dp.unreal.validation/v1",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "structuralIssues": structural,
        "assets": assets,
        "summary": {
            "assets": len(assets),
            "failures": failures,
            "missingEngineValidation": missing_engine_validation,
            "layoutWarnings": sum(
                1 for item in assets for issue in item["layoutIssues"]
                if issue.get("severity") == "warning"
            ),
            "layoutInformation": sum(
                1 for item in assets for issue in item["layoutIssues"]
                if issue.get("severity") == "info"
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = run(args.root)
    output = Path(args.output) if args.output else Path(args.root) / "validation/latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    raise SystemExit(1 if report["status"] == "fail" else 0)


if __name__ == "__main__":
    main()
