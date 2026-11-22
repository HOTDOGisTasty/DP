"""Validate DP Unreal context exports without requiring Unreal."""

import json
from pathlib import Path
import sys

from layout_audit import audit_graph

SCHEMA = "dp.unreal.context/v1"


def validate(root):
    root = Path(root)
    issues = []
    index_path = root / "assets-index.json"
    if not index_path.is_file():
        return [f"missing: {index_path}"]
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"invalid index JSON: {exc}"]
    if index.get("schemaVersion") != SCHEMA:
        issues.append("index schemaVersion mismatch")
    seen = set()
    for entry in index.get("assets", []):
        path = entry.get("objectPath")
        if not path or path in seen:
            issues.append(f"duplicate or missing objectPath: {path!r}")
        seen.add(path)
        document_path = root / str(entry.get("file", ""))
        if not document_path.is_file():
            issues.append(f"missing document: {document_path}")
            continue
        try:
            document = json.loads(document_path.read_text(encoding="utf-8"))
        except Exception as exc:
            issues.append(f"invalid document JSON {document_path}: {exc}")
            continue
        if document.get("schemaVersion") != SCHEMA:
            issues.append(f"schemaVersion mismatch: {document_path}")
        if document.get("asset", {}).get("objectPath") != path:
            issues.append(f"objectPath mismatch: {document_path}")
        coverage = document.get("graph", {}).get("coverage")
        if not isinstance(coverage, dict):
            issues.append(f"missing graph coverage: {document_path}")
        layout_issues = audit_graph(document)
        if any(item.get("severity") == "error" for item in layout_issues):
            issues.append(f"layout audit error: {document_path}")
    return issues


def main(argv):
    issues = validate(argv[1] if len(argv) > 1 else "context/unreal")
    print(json.dumps({"ok": not issues, "issues": issues}, indent=2))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
