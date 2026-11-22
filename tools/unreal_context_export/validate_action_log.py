"""Validate append-only DP action JSONL records."""

import json
from pathlib import Path
import sys

REQUIRED = {"schemaVersion", "id", "timestampUtc", "actor", "operation", "status",
            "assets", "verification", "details"}


def validate(path):
    issues = []
    seen = set()
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except Exception as exc:
            issues.append(f"line {number}: invalid JSON: {exc}")
            continue
        missing = REQUIRED - set(record)
        if missing:
            issues.append(f"line {number}: missing {sorted(missing)}")
        if record.get("schemaVersion") != "dp.unreal.action/v1":
            issues.append(f"line {number}: schemaVersion mismatch")
        identifier = record.get("id")
        if identifier in seen:
            issues.append(f"line {number}: duplicate id {identifier}")
        seen.add(identifier)
        if not isinstance(record.get("assets"), list):
            issues.append(f"line {number}: assets must be a list")
        if not isinstance(record.get("verification"), dict):
            issues.append(f"line {number}: verification must be an object")
    return issues


def main(argv):
    issues = validate(argv[1])
    print(json.dumps({"ok": not issues, "issues": issues}, indent=2))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
